#!/usr/bin/env python3
"""Tests for fetch_peer_hosts.py — remote peer host fetching."""

import importlib.util
import io
import json
import os
import socket
import sys
import unittest
import urllib.error
from unittest.mock import patch, MagicMock

# Load fetch_peer_hosts as a module from its file path
SCRIPT_DIR = os.path.join(
    os.path.dirname(__file__), '..', 'net', 'kealeasesync', 'src',
    'opnsense', 'scripts', 'OPNsense', 'KeaLeaseSync'
)
SCRIPT_PATH = os.path.join(SCRIPT_DIR, 'fetch_peer_hosts.py')

spec = importlib.util.spec_from_file_location('fetch_peer_hosts', SCRIPT_PATH)
fetch_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch_mod)
fetch = fetch_mod.fetch
main_fn = fetch_mod.main

# Reference to the urllib.request used inside the module
_urllib_request = fetch_mod.urllib.request


def _mock_response(data):
    """Create a mock urllib response with JSON data."""
    body = json.dumps(data).encode()
    resp = MagicMock()
    resp.read.return_value = body
    return resp


def _run_main(args):
    """Call main() with mocked sys.argv, catching SystemExit."""
    captured_out = io.StringIO()
    captured_err = io.StringIO()
    with patch.object(sys, 'argv', args), \
         patch('sys.stdout', captured_out), \
         patch('sys.stderr', captured_err):
        try:
            main_fn()
        except SystemExit:
            pass
    return captured_out.getvalue(), captured_err.getvalue()


class TestFetch(unittest.TestCase):
    """Tests for the fetch() function."""

    @patch.object(_urllib_request, 'urlopen')
    def test_successful_fetch(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({
            'hosts': [
                {'hostname': 'host-a', 'ip': '192.168.1.10', 'type': 'static', 'rtype': 'A'},
                {'hostname': 'host-b', 'ip': '192.168.1.11', 'type': 'dynamic', 'rtype': 'A'},
                {'hostname': 'host-c', 'ip': '2001:db8::10', 'type': 'static', 'rtype': 'AAAA'},
            ]
        })
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            fetch('https://10.0.0.1', 'mykey')
        lines = captured.getvalue().strip().split('\n')
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0], 'A|host-a|192.168.1.10|peer')
        self.assertEqual(lines[1], 'A|host-b|192.168.1.11|peer')
        self.assertEqual(lines[2], 'AAAA|host-c|2001:db8::10|peer')

    @patch.object(_urllib_request, 'urlopen')
    def test_skips_peer_type_hosts(self, mock_urlopen):
        """Hosts with type=peer should be skipped to prevent loops."""
        mock_urlopen.return_value = _mock_response({
            'hosts': [
                {'hostname': 'local-host', 'ip': '192.168.1.10', 'type': 'dynamic', 'rtype': 'A'},
                {'hostname': 'remote-peer', 'ip': '10.0.0.50', 'type': 'peer', 'rtype': 'A'},
            ]
        })
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            fetch('https://10.0.0.1', 'mykey')
        lines = [l for l in captured.getvalue().strip().split('\n') if l]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0], 'A|local-host|192.168.1.10|peer')

    @patch.object(_urllib_request, 'urlopen')
    def test_empty_hosts_list(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({'hosts': []})
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            fetch('https://10.0.0.1', 'mykey')
        self.assertEqual(captured.getvalue().strip(), '')

    @patch.object(_urllib_request, 'urlopen')
    def test_missing_hosts_key(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({})
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            fetch('https://10.0.0.1', 'mykey')
        self.assertEqual(captured.getvalue().strip(), '')

    @patch.object(_urllib_request, 'urlopen')
    def test_skips_hosts_missing_hostname(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({
            'hosts': [
                {'hostname': '', 'ip': '192.168.1.10', 'type': 'dynamic', 'rtype': 'A'},
                {'ip': '192.168.1.11', 'type': 'dynamic', 'rtype': 'A'},
                {'hostname': 'valid', 'ip': '192.168.1.12', 'type': 'dynamic', 'rtype': 'A'},
            ]
        })
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            fetch('https://10.0.0.1', 'mykey')
        lines = [l for l in captured.getvalue().strip().split('\n') if l]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0], 'A|valid|192.168.1.12|peer')

    @patch.object(_urllib_request, 'urlopen')
    def test_skips_hosts_missing_ip(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({
            'hosts': [
                {'hostname': 'noip', 'ip': '', 'type': 'dynamic', 'rtype': 'A'},
                {'hostname': 'valid', 'ip': '192.168.1.12', 'type': 'static', 'rtype': 'A'},
            ]
        })
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            fetch('https://10.0.0.1', 'mykey')
        lines = [l for l in captured.getvalue().strip().split('\n') if l]
        self.assertEqual(len(lines), 1)

    @patch.object(_urllib_request, 'urlopen')
    def test_defaults_rtype_to_A(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({
            'hosts': [
                {'hostname': 'nortype', 'ip': '192.168.1.10', 'type': 'dynamic'},
            ]
        })
        captured = io.StringIO()
        with patch('sys.stdout', captured):
            fetch('https://10.0.0.1', 'mykey')
        self.assertIn('A|nortype|192.168.1.10|peer', captured.getvalue())

    @patch.object(_urllib_request, 'urlopen')
    def test_url_trailing_slash_stripped(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({'hosts': []})
        fetch('https://10.0.0.1/', 'mykey')
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.full_url, 'https://10.0.0.1/api/kealeasesync/peer/hosts')

    @patch.object(_urllib_request, 'urlopen')
    def test_api_key_header(self, mock_urlopen):
        mock_urlopen.return_value = _mock_response({'hosts': []})
        fetch('https://10.0.0.1', 'my-shared-secret')
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.get_header('X-api-key'), 'my-shared-secret')


class TestFetchErrors(unittest.TestCase):
    """Tests for error handling — all errors should be silent on stdout."""

    @patch.object(_urllib_request, 'urlopen')
    def test_connection_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError('Connection refused')
        out, err = _run_main(['fetch_peer_hosts.py', 'https://10.0.0.1', 'key'])
        self.assertEqual(out.strip(), '')
        self.assertIn('Peer fetch error', err)

    @patch.object(_urllib_request, 'urlopen')
    def test_http_403(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            'https://10.0.0.1/api/kealeasesync/peer/hosts',
            403, 'Forbidden', {}, None
        )
        out, err = _run_main(['fetch_peer_hosts.py', 'https://10.0.0.1', 'key'])
        self.assertEqual(out.strip(), '')
        self.assertIn('Peer fetch error', err)

    @patch.object(_urllib_request, 'urlopen')
    def test_timeout(self, mock_urlopen):
        mock_urlopen.side_effect = socket.timeout('timed out')
        out, err = _run_main(['fetch_peer_hosts.py', 'https://10.0.0.1', 'key'])
        self.assertEqual(out.strip(), '')
        self.assertIn('Peer fetch error', err)

    @patch.object(_urllib_request, 'urlopen')
    def test_invalid_json_response(self, mock_urlopen):
        resp = MagicMock()
        resp.read.return_value = b'not json at all'
        mock_urlopen.return_value = resp
        out, err = _run_main(['fetch_peer_hosts.py', 'https://10.0.0.1', 'key'])
        self.assertEqual(out.strip(), '')
        self.assertIn('Peer fetch error', err)


class TestMainArgs(unittest.TestCase):
    """Tests for main() argument handling."""

    def test_wrong_arg_count(self):
        out, err = _run_main(['fetch_peer_hosts.py'])
        self.assertEqual(out.strip(), '')
        self.assertIn('Usage', err)

    def test_too_many_args(self):
        out, err = _run_main(['fetch_peer_hosts.py', 'a', 'b', 'c'])
        self.assertEqual(out.strip(), '')
        self.assertIn('Usage', err)


if __name__ == '__main__':
    unittest.main()
