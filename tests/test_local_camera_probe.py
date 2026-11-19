import contextlib
import io
import socket
import threading
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

import local_camera_probe as lab


class LocalCameraProbeTests(unittest.TestCase):
    def test_requested_wsl_ip_must_belong_to_the_current_machine(self):
        with patch.object(lab, '_local_ipv4_addresses', return_value={'172.27.100.182'}):
            self.assertTrue(lab.is_local_lab_address('172.27.100.182'))
            self.assertFalse(lab.is_local_lab_address('172.27.100.183'))
        with patch.object(lab, '_local_ipv4_addresses', return_value={'172.27.100.183'}):
            self.assertFalse(lab.is_local_lab_address('172.27.100.182'))

    def test_unassigned_wsl_ip_is_rejected_before_network_io(self):
        with patch.object(lab, '_local_ipv4_addresses', return_value=set()), \
                patch.object(lab.asyncio, 'open_connection') as connect:
            with self.assertRaises(ValueError):
                lab.probe_local_camera('172.27.100.182', 8000)
            with self.assertRaises(ValueError):
                lab.scan_local_tcp_ports('172.27.100.182')
            connect.assert_not_called()

    def test_wsl_ip_with_port_uses_bounded_single_port_branch(self):
        from skullvision import SkullVision
        tool = SkullVision.__new__(SkullVision)
        tool.vis = Mock()
        tool.detect_local_camera = Mock()
        tool.scan_ports_complete = Mock(side_effect=AssertionError('Shared scan must not run'))
        with patch.object(lab, '_local_ipv4_addresses', return_value={'172.27.100.182'}), \
                patch('builtins.input', return_value='172.27.100.182:8000'):
            tool.mode_camera_detector()
        tool.detect_local_camera.assert_called_once_with('172.27.100.182', 8000)
        tool.scan_ports_complete.assert_not_called()

    def serve(self, handler):
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(3)
        self.addCleanup(listener.close)
        def run():
            with listener.accept()[0] as connection:
                connection.settimeout(2)
                handler(connection)
        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        return listener.getsockname()[1]

    def test_unauthenticated_response_is_reported_without_retry(self):
        received = []
        def reply(connection):
            received.append(connection.recv(4096))
            connection.sendall(b'HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\n\r\n')
        result = lab.probe_local_camera('127.0.0.1', self.serve(reply))
        self.assertEqual(result['status'], 401)
        self.assertIsNone(result['error'])
        self.assertTrue(received[0].startswith(b'GET / HTTP/1.1\r\n'))
        self.assertNotIn(b'Authorization:', received[0])

    def test_stalled_headers_respect_total_deadline(self):
        release = threading.Event()
        self.addCleanup(release.set)
        port = self.serve(lambda connection: release.wait(2))
        started = time.monotonic()
        result = lab.probe_local_camera('127.0.0.1', port, timeout=0.1)
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertIn('Timeout', result['error'])

    def test_non_loopback_is_rejected_before_connect(self):
        with patch.object(lab.asyncio, 'open_connection') as connect:
            with self.assertRaises(ValueError):
                lab.probe_local_camera('192.0.2.1', 8001)
            connect.assert_not_called()

    def test_root_404_can_still_confirm_onvif(self):
        body = (f'<s:Envelope xmlns:s="{lab.SOAP}" xmlns:d="{lab.DEVICE}">'
                '<s:Body><d:GetCapabilitiesResponse><d:Capabilities/>'
                '</d:GetCapabilitiesResponse></s:Body></s:Envelope>')
        root = {'status': 404, 'headers': {}, 'sample': '', 'error': None}
        soap = {'status': 200, 'headers': {}, 'sample': body, 'error': None}
        with patch.object(lab, '_read_http', new_callable=AsyncMock, side_effect=[root, soap]) as probe:
            result = lab.probe_local_camera('127.0.0.1', 8001)
        self.assertTrue(result['onvif_verified'])
        self.assertEqual(result['status'], 404)
        self.assertEqual(probe.await_args_list[1].args[2], '/onvif/device_service')
        self.assertIn(b'GetCapabilities', probe.await_args_list[1].args[3])

    def test_http_200_html_or_soap_fault_does_not_confirm_onvif(self):
        for body in ('<html>Login</html>', 'invalid XML',
                     f'<s:Envelope xmlns:s="{lab.SOAP}"><s:Body><s:Fault/></s:Body></s:Envelope>'):
            with self.subTest(body=body):
                responses = [{'status': 404, 'headers': {}, 'sample': '', 'error': None},
                             {'status': 200, 'headers': {}, 'sample': body, 'error': None}]
                with patch.object(lab, '_read_http', new_callable=AsyncMock, side_effect=responses):
                    result = lab.probe_local_camera('127.0.0.1', 8001)
                self.assertFalse(result['onvif_verified'])

    def test_onvif_fallback_is_covered_by_total_deadline(self):
        async def stalled(host, port, path='/', payload=None):
            if payload is not None:
                await lab.asyncio.sleep(2)
            return {'status': 404, 'headers': {}, 'sample': '', 'error': None}
        with patch.object(lab, '_read_http', side_effect=stalled):
            started = time.monotonic()
            result = lab.probe_local_camera('127.0.0.1', 8001, timeout=0.1)
        self.assertLess(time.monotonic() - started, 1)
        self.assertIn('Timeout', result['error'])

    def test_mode_17_uses_only_the_explicit_local_port(self):
        from skullvision import SkullVision
        tool = SkullVision.__new__(SkullVision)
        tool.vis = Mock()
        tool.scan_ports_complete = Mock(side_effect=AssertionError('Broad scan must not run'))
        tool.detect_local_camera = Mock()
        with patch('builtins.input', return_value='127.0.0.1:8001'):
            with contextlib.redirect_stdout(io.StringIO()):
                tool.mode_camera_detector()
        tool.detect_local_camera.assert_called_once_with('127.0.0.1', 8001)
        tool.scan_ports_complete.assert_not_called()

    def test_local_scan_checks_each_port_and_reaches_final_progress(self):
        async def connect(host, port, timeout):
            if port == 8002:
                raise ConnectionRefusedError()
            if port == 8003:
                raise lab.asyncio.TimeoutError()
        progress = Mock()
        with patch.object(lab, 'TCP_PORTS', [8001, 8002, 8003]), \
                patch.object(lab, '_connect_local_port', side_effect=connect) as probe:
            result = lab.scan_local_tcp_ports('127.0.0.1', on_progress=progress)
        self.assertEqual(probe.await_count, 3)
        self.assertEqual(result['open_ports'], [8001])
        self.assertEqual(result['timeout_ports'], [8003])
        self.assertEqual(result['unchecked'], 0)
        progress.assert_called_with(3, 3)

    def test_scan_deadline_cancels_unfinished_connections(self):
        cancelled = []
        async def stalled(host, port, timeout):
            try:
                await lab.asyncio.sleep(10)
            finally:
                cancelled.append(port)
        with patch.object(lab, 'TCP_PORTS', [8001, 8002]), \
                patch.object(lab, '_connect_local_port', side_effect=stalled):
            started = time.monotonic()
            result = lab.scan_local_tcp_ports('127.0.0.1', timeout=0.05)
        self.assertLess(time.monotonic() - started, 1)
        self.assertTrue(result['deadline_reached'])
        self.assertEqual(result['unchecked'], 2)
        self.assertCountEqual(cancelled, [8001, 8002])

    def test_all_port_scan_rejects_non_loopback(self):
        with patch.object(lab, '_connect_local_port') as connect:
            with self.assertRaises(ValueError):
                lab.scan_local_tcp_ports('192.0.2.1')
            connect.assert_not_called()

    def test_mode_17_ip_only_uses_local_discovery(self):
        from skullvision import SkullVision
        tool = SkullVision.__new__(SkullVision)
        tool.vis = Mock()
        tool.discover_local_cameras = Mock()
        tool.scan_ports_complete = Mock(side_effect=AssertionError('Shared scan must not run'))
        with patch('builtins.input', return_value='127.0.0.1'):
            tool.mode_camera_detector()
        tool.discover_local_cameras.assert_called_once_with('127.0.0.1')
        tool.scan_ports_complete.assert_not_called()

    def test_discovery_stops_on_total_deadline_and_reports_unchecked_onvif_port(self):
        from skullvision import SkullVision
        tool = SkullVision.__new__(SkullVision)
        tool.vis = Mock()
        summary = {'checked': 65535, 'total': 65535, 'open_ports': [8001, 8002],
                   'unchecked': 0, 'timeout_ports': []}
        with patch.object(lab, 'scan_local_tcp_ports', return_value=summary), \
                patch.object(lab, 'probe_local_camera', return_value={'onvif_verified': True}) as probe, \
                patch('skullvision.time.monotonic', side_effect=[0, 1, 31]):
            tool.discover_local_cameras('127.0.0.1')
        probe.assert_called_once_with('127.0.0.1', 8001, timeout=3)
        self.assertIn('8002', tool.vis.warning.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
