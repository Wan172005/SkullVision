import io
import unittest
from unittest.mock import Mock, patch

import local_camera_auth as lab


class LocalCameraAuthTests(unittest.TestCase):
    def test_remote_or_incomplete_targets_never_open_connections(self):
        cases = [
            ('ONVIF', 'http://192.0.2.10:8000/onvif/device_service'),
            ('RTSP', 'rtsp://192.0.2.10:8554/profile1'),
            ('RTSP', 'rtsp://localhost:8554/profile1'),
            ('RTSP', 'rtsp://127.0.0.1:8554/'),
            ('ONVIF', 'http://u:p@127.0.0.1:8000/onvif/device_service'),
        ]
        with patch.object(lab, '_onvif_request') as onvif, patch.object(lab, '_rtsp_request') as rtsp:
            for protocol, url in cases:
                with self.subTest(url=url), self.assertRaises(ValueError):
                    lab.check_local_camera_auth(protocol, url, ['u'], ['p'], Mock())
            onvif.assert_not_called()
            rtsp.assert_not_called()

    def test_public_resource_or_invalid_control_cannot_report_success(self):
        for responses in ([True], [False, True]):
            with self.subTest(responses=responses), patch.object(lab, '_rtsp_request', side_effect=responses):
                progress = Mock()
                with self.assertRaises(RuntimeError):
                    lab.check_local_camera_auth('RTSP', 'rtsp://127.0.0.1:8554/profile1',
                                                ['u'], ['p'], progress)
                progress.assert_not_called()

    def test_rtsp_uses_describe_and_handles_auth_challenge(self):
        first = b'RTSP/1.0 401 Unauthorized\r\nWWW-Authenticate: Basic realm="lab"\r\nContent-Length: 0\r\n\r\n'
        sdp = b'v=0\r\ns=lab\r\n'
        second = (b'RTSP/1.0 200 OK\r\nContent-Type: application/sdp\r\nContent-Length: '
                  + str(len(sdp)).encode() + b'\r\n\r\n' + sdp)
        sock = Mock()
        connection = Mock()
        connection.__enter__ = Mock(return_value=sock)
        connection.__exit__ = Mock(return_value=False)
        sock.makefile.return_value = io.BytesIO(first + second)
        with patch.object(lab.socket, 'create_connection', return_value=connection):
            self.assertTrue(lab._rtsp_request('rtsp://127.0.0.1:8554/profile1',
                                             '127.0.0.1', 8554, 'u', 'p'))
        messages = [call.args[0] for call in sock.sendall.call_args_list]
        self.assertEqual(len(messages), 2)
        self.assertTrue(all(m.startswith(b'DESCRIBE rtsp://127.0.0.1:8554/profile1 RTSP/1.0') for m in messages))
        self.assertIn(b'Authorization: Basic dTpw\r\n', messages[1])

    def test_http_200_alone_is_not_onvif_authentication(self):
        session = Mock()
        session.post.return_value = Mock(status_code=200, content=b'<html>Login</html>')
        with self.assertRaises(RuntimeError):
            lab._onvif_request(session, 'http://127.0.0.1:8000/onvif/device_service', 'u', 'p')

    def test_soap_auth_failure_is_distinct_from_other_faults(self):
        session = Mock()
        for code in ('NotAuthorized', 'MessageExpired'):
            payload = (f'<s:Envelope xmlns:s="{lab.SOAP}" xmlns:t="urn:lab"><s:Body><s:Fault>'
                       f'<s:Code><s:Value>s:Sender</s:Value><s:Subcode><s:Value>t:{code}</s:Value>'
                       '</s:Subcode></s:Code></s:Fault></s:Body></s:Envelope>').encode()
            session.post.return_value = Mock(status_code=500, content=payload)
            if code == 'NotAuthorized':
                self.assertFalse(lab._onvif_request(session, 'http://127.0.0.1:8000/onvif/device_service', 'u', 'p'))
            else:
                with self.assertRaisesRegex(RuntimeError, 'MessageExpired'):
                    lab._onvif_request(session, 'http://127.0.0.1:8000/onvif/device_service', 'u', 'p')

    def test_empty_credentials_are_rejected_before_network(self):
        with patch.object(lab, '_rtsp_request') as probe:
            with self.assertRaises(ValueError):
                lab.check_local_camera_auth('RTSP', 'rtsp://127.0.0.1:8554/profile1',
                                            ['u'], [], Mock())
            probe.assert_not_called()


if __name__ == '__main__':
    unittest.main()
