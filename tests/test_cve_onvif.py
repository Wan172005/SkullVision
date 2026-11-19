import unittest
from unittest.mock import Mock, patch

import local_camera_auth as lab


class CveOnvifTests(unittest.TestCase):
    def test_device_metadata_requires_namespaced_soap_response(self):
        session = Mock()
        session.post.return_value = Mock(status_code=200, content=(
            f'<s:Envelope xmlns:s="{lab.SOAP}" xmlns:t="{lab.DEVICE}">'
            '<s:Body><t:GetDeviceInformationResponse>'
            '<t:Manufacturer>Hikvision</t:Manufacturer><t:Model>Lab</t:Model>'
            '<t:FirmwareVersion>simulated</t:FirmwareVersion>'
            '</t:GetDeviceInformationResponse></s:Body></s:Envelope>').encode())
        result = lab._onvif_request(session, 'http://127.0.0.1:8000/onvif/device_service',
                                    'admin', 'fixture', return_information=True)
        self.assertEqual(result, {'Manufacturer': 'Hikvision', 'Model': 'Lab',
                                  'FirmwareVersion': 'simulated'})
        kwargs = session.post.call_args.kwargs
        self.assertFalse(kwargs['allow_redirects'])
        self.assertEqual(kwargs['timeout'], (2, 3))
        self.assertIn(b'UsernameToken', kwargs['data'])
        session.post.return_value.content = b'<html>Hikvision</html>'
        with self.assertRaises(RuntimeError):
            lab._onvif_request(session, 'http://127.0.0.1:8000/onvif/device_service',
                               'admin', 'fixture', return_information=True)

    def test_denied_account_is_not_metadata(self):
        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        with patch.object(lab.requests, 'Session', return_value=session), \
                patch.object(lab, '_onvif_request', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'denied'):
                lab.get_onvif_device_information('http://127.0.0.1:8000/onvif/device_service',
                                                 'admin', 'wrong')

    def test_menu_falls_back_and_labels_results_as_unverified(self):
        from skullvision import SkullVision
        tool = SkullVision.__new__(SkullVision)
        tool.vis = Mock()
        tool.detect_camera_complete = Mock(return_value=(False, None))
        with patch('builtins.input', side_effect=['127.0.0.1:8000', 'y', 'admin']), \
                patch('getpass.getpass', return_value='fixture'), \
                patch.object(lab, 'get_onvif_device_information', return_value={
                    'Manufacturer': 'Hikvision', 'Model': 'Lab', 'FirmwareVersion': 'simulated'
                }) as read:
            tool.mode_cve_scanner()
        read.assert_called_once_with('http://127.0.0.1:8000/onvif/device_service', 'admin', 'fixture')
        warnings = [str(call.args[0]) for call in tool.vis.warning.call_args_list]
        self.assertTrue(any('NOT verified' in message for message in warnings))
        tool.vis.cve_found.assert_called()


if __name__ == '__main__':
    unittest.main()
