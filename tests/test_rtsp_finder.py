import contextlib
import io
import unittest
from unittest.mock import Mock, patch

import local_camera_auth as lab


SDP = (b'v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\ns=Lab camera\r\nt=0 0\r\n'
       b'm=video 0 RTP/AVP 96\r\na=rtpmap:96 H264/90000\r\n')


class RTSPFinderTests(unittest.TestCase):
    def probe(self, status=200, content_type='application/sdp', body=SDP):
        response = (f'RTSP/1.0 {status} Result\r\nContent-Type: {content_type}\r\n'
                    f'Content-Length: {len(body)}\r\n\r\n').encode() + body
        sock = Mock()
        connection = Mock()
        connection.__enter__ = Mock(return_value=sock)
        connection.__exit__ = Mock(return_value=False)
        sock.makefile.return_value = io.BytesIO(response)
        with patch.object(lab.socket, 'create_connection', return_value=connection):
            result = lab.probe_rtsp_url('rtsp://127.0.0.1:8554/profile1?channel=1')
        return result, sock

    def test_describe_targets_the_exact_path_and_query(self):
        result, sock = self.probe()
        self.assertTrue(result['verified'])
        self.assertIn(b'DESCRIBE rtsp://127.0.0.1:8554/profile1?channel=1 RTSP/1.0\r\n',
                      sock.sendall.call_args.args[0])
        self.assertNotIn(b'OPTIONS', sock.sendall.call_args.args[0])

    def test_401_403_and_404_are_not_verified(self):
        for status in (401, 403, 404):
            with self.subTest(status=status):
                result, _ = self.probe(status, body=b'')
                self.assertFalse(result['verified'])
                self.assertEqual(result['status'], status)
                if status in (401, 403):
                    self.assertIn('not confirmed', result['reason'])

    def test_http_200_or_incomplete_sdp_does_not_verify_a_stream(self):
        for content_type, body in [('text/html', b'<html>Login</html>'),
                                   ('application/sdp', b''),
                                   ('application/sdp', b'v=0\r\ns=Not a stream\r\n'),
                                   ('application/sdp', SDP.replace(b'm=video', b'm=application'))]:
            with self.subTest(content_type=content_type, body=body):
                result, _ = self.probe(content_type=content_type, body=body)
                self.assertFalse(result['verified'])

    def test_redirect_is_not_followed(self):
        result, sock = self.probe(302, body=b'')
        self.assertFalse(result['verified'])
        self.assertEqual(sock.sendall.call_count, 1)

    def test_remote_authenticated_probe_is_blocked(self):
        with patch.object(lab.socket, 'create_connection') as connect:
            with self.assertRaises(ValueError):
                lab.probe_rtsp_url('rtsp://192.0.2.10:554/stream1', 'lab-user', 'lab-pass')
            connect.assert_not_called()

    def test_connection_failure_is_visible_and_not_verified(self):
        with patch.object(lab.socket, 'create_connection', side_effect=ConnectionRefusedError('lab offline')):
            result = lab.probe_rtsp_url('rtsp://127.0.0.1:8554/profile1')
        self.assertFalse(result['verified'])
        self.assertIn('lab offline', result['reason'])

    def test_finder_only_records_verified_results_without_duplicates(self):
        from skullvision import SkullVision
        tool = SkullVision.__new__(SkullVision)
        tool.vis = Mock()
        tool.detected_streams = {}
        def probe(url, username, password):
            verified = url.endswith('/profile1')
            return {'url': url, 'port': 8554, 'verified': verified,
                    'status': 200 if verified else 401, 'reason': 'test fixture'}
        with patch.object(lab, 'probe_rtsp_url', side_effect=probe) as check:
            with contextlib.redirect_stdout(io.StringIO()):
                results = tool.exploit_rtsp_complete('127.0.0.1', [8554, 8554],
                                                   paths=['/profile1', '/missing', '/profile1'])
        self.assertEqual(check.call_count, 2)
        self.assertEqual(len(results), 1)
        self.assertEqual(tool.detected_streams['rtsp'], ['rtsp://127.0.0.1:8554/profile1'])


if __name__ == '__main__':
    unittest.main()
