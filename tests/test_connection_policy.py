import json
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from notesync.ConnectionPolicy import ConnectionPolicy, websocket_origin_allowed


class ConnectionPolicyTests(unittest.TestCase):
    def test_only_loopback_bypasses_without_tailscale(self):
        with patch('notesync.ConnectionPolicy.shutil.which', return_value=None):
            policy = ConnectionPolicy()
            for host in ['127.0.0.1', '::1']:
                self.assertTrue(policy.passwordless(host))
            for host in ['192.168.3.168', '8.8.8.8', '100.81.103.50', 'hostname', 'fd7a:115c:a1e0::1']:
                self.assertFalse(policy.passwordless(host))

    @patch('notesync.ConnectionPolicy.shutil.which', return_value='/usr/bin/tailscale')
    @patch('notesync.ConnectionPolicy.subprocess.run')
    def test_verified_node_is_cached(self, run, which):
        run.return_value = SimpleNamespace(returncode=0, stdout=json.dumps({'Node': {'ID': 123}}))
        policy = ConnectionPolicy()
        self.assertTrue(policy.passwordless('100.81.103.50'))
        self.assertTrue(policy.passwordless('100.81.103.50'))
        run.assert_called_once_with(['/usr/bin/tailscale', 'whois', '--json', '100.81.103.50'],
                                    capture_output=True, text=True, timeout=2)

    @patch('notesync.ConnectionPolicy.shutil.which', return_value='/usr/bin/tailscale')
    @patch('notesync.ConnectionPolicy.subprocess.run')
    def test_range_alone_and_failed_verification_do_not_bypass(self, run, which):
        for identity in [{}, {'Node': {}}, {'Node': {'ID': 123, 'Expired': True}}, [], None]:
            run.return_value = SimpleNamespace(returncode=0, stdout=json.dumps(identity))
            self.assertFalse(ConnectionPolicy().passwordless('100.81.103.50'))
        run.return_value = SimpleNamespace(returncode=1, stdout='permission denied')
        self.assertFalse(ConnectionPolicy().passwordless('100.81.103.50'))
        run.side_effect = subprocess.TimeoutExpired('tailscale', 2)
        self.assertFalse(ConnectionPolicy().passwordless('100.81.103.50'))

    def test_websocket_origin_must_match_the_page_host_and_http_port(self):
        for host, origin in [('100.81.103.50:8765', 'http://100.81.103.50:8080'),
                             ('[::1]:8765', 'http://[::1]:8080')]:
            self.assertTrue(websocket_origin_allowed(origin, host, 8080))
        for origin in ['http://evil.example:8080', 'http://100.81.103.50:80', 'null',
                       'http://100.81.103.50:8080/path', 'http://x@100.81.103.50:8080',
                       'http://100.81.103.50:bad', 'http://[broken']:
            self.assertFalse(websocket_origin_allowed(origin, '100.81.103.50:8765', 8080))
        self.assertTrue(websocket_origin_allowed(None, '100.81.103.50:8765', 8080))


if __name__ == '__main__':
    unittest.main()
