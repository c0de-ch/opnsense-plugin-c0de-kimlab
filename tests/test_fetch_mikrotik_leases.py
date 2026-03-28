#!/usr/bin/env python3
"""Tests for fetch_mikrotik_leases.py — MikroTik RouterOS lease fetching."""

import base64
import importlib.util
import io
import json
import os
import ssl
import sys
import unittest
import urllib.error
from unittest.mock import patch, MagicMock

# Load fetch_mikrotik_leases as a module from its file path
SCRIPT_DIR = os.path.join(
    os.path.dirname(__file__), '..', 'net', 'kealeasesync', 'src',
    'opnsense', 'scripts', 'OPNsense', 'KeaLeaseSync'
)
SCRIPT_PATH = os.path.join(SCRIPT_DIR, 'fetch_mikrotik_leases.py')

spec = importlib.util.spec_from_file_location('fetch_mikrotik_leases', SCRIPT_PATH)
mt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mt)

# Reference to the urllib.request used inside the module
_urllib_request = mt.urllib.request

LEASES = [
    {'address': '192.168.88.10', 'mac-address': 'AA:BB:CC:DD:EE:01',
     'host-name': 'Laptop', 'status': 'bound', 'dynamic': 'true', 'disabled': 'false'},
    {'address': '192.168.88.11', 'mac-address': 'AA:BB:CC:DD:EE:02',
     'host-name': 'nas.lan', 'status': 'bound', 'dynamic': 'false', 'disabled': 'false'},
]

BINDINGS = [
    # DUID-LL of the laptop
    {'address': '2001:db8::10/128', 'duid': '0x00030001aabbccddee01',
     'status': 'bound', 'disabled': 'false'},
    # Delegated prefix
    {'address': '2001:db8:100::/56', 'duid': '0x00030001aabbccddee02',
     'status': 'bound', 'disabled': 'false'},
]


def _mock_response(data):
    """Create a mock urllib response (context manager) with JSON data."""
    resp = MagicMock()
    resp.read.return_value = json.dumps(data).encode()
    resp.__enter__.return_value = resp
    return resp


def _urlopen_for(leases, bindings):
    """Build a urlopen side effect serving the two REST endpoints.

    Pass an Exception instance instead of data to make an endpoint fail.
    """
    def _urlopen(req, **kwargs):
        data = bindings if mt.BINDING6_PATH in req.full_url else leases
        if isinstance(data, Exception):
            raise data
        return _mock_response(data)
    return _urlopen


def _run_main(args, password='secret'):
    """Call main() with mocked argv/env. Returns (stdout, stderr, exit code)."""
    captured_out = io.StringIO()
    captured_err = io.StringIO()
    code = 0
    with patch.object(sys, 'argv', ['fetch_mikrotik_leases.py'] + args), \
         patch.dict(os.environ, {'MIKROTIK_PASSWORD': password}), \
         patch('sys.stdout', captured_out), \
         patch('sys.stderr', captured_err):
        try:
            mt.main()
        except SystemExit as e:
            code = e.code
    return captured_out.getvalue(), captured_err.getvalue(), code


ARGS = ['--host', '192.168.88.1', '--user', 'api']


class TestCleanHostname(unittest.TestCase):

    def test_lowercase_and_strip_domain(self):
        self.assertEqual(mt.clean_hostname('MyHost.example.com'), 'myhost')

    def test_removes_invalid_chars(self):
        self.assertEqual(mt.clean_hostname('my_host!'), 'myhost')

    def test_empty(self):
        self.assertIsNone(mt.clean_hostname(''))
        self.assertIsNone(mt.clean_hostname(None))
        self.assertIsNone(mt.clean_hostname('!!!'))

    def test_bare_mac_rejected(self):
        self.assertIsNone(mt.clean_hostname('AABBCCDDEEFF'))

    def test_dhcp_mac_kept(self):
        self.assertEqual(mt.clean_hostname('dhcp-aabbccddeeff'), 'dhcp-aabbccddeeff')


class TestMacHelpers(unittest.TestCase):

    def test_clean_mac_lowercases(self):
        self.assertEqual(mt.clean_mac('AA:BB:CC:DD:EE:FF'), 'aa:bb:cc:dd:ee:ff')

    def test_clean_mac_dashes(self):
        self.assertEqual(mt.clean_mac('AA-BB-CC-DD-EE-FF'), 'aa:bb:cc:dd:ee:ff')

    def test_clean_mac_invalid(self):
        self.assertEqual(mt.clean_mac('not-a-mac'), '')
        self.assertEqual(mt.clean_mac('aa:bb:cc|dd:ee:ff'), '')
        self.assertEqual(mt.clean_mac(None), '')

    def test_duid_ll(self):
        self.assertEqual(mt.mac_from_duid('0x00030001aabbccddeeff'), 'aa:bb:cc:dd:ee:ff')

    def test_duid_llt(self):
        self.assertEqual(
            mt.mac_from_duid('0x000100012a3b4c5daabbccddeeff'), 'aa:bb:cc:dd:ee:ff')

    def test_duid_colon_separated(self):
        self.assertEqual(
            mt.mac_from_duid('00:03:00:01:AA:BB:CC:DD:EE:FF'), 'aa:bb:cc:dd:ee:ff')

    def test_duid_without_mac(self):
        # DUID-EN and DUID-UUID carry no link-layer address
        self.assertEqual(mt.mac_from_duid('0x00020000ab11deadbeef0001'), '')
        self.assertEqual(mt.mac_from_duid('0x0004' + '11' * 16), '')

    def test_duid_invalid(self):
        self.assertEqual(mt.mac_from_duid(''), '')
        self.assertEqual(mt.mac_from_duid(None), '')
        self.assertEqual(mt.mac_from_duid('0xzz'), '')


class TestParseLeases(unittest.TestCase):

    def test_bound_leases(self):
        lines, names = mt.parse_leases(LEASES)
        self.assertEqual(lines, [
            'A|laptop|192.168.88.10|mikrotik|aa:bb:cc:dd:ee:01',
            'A|nas|192.168.88.11|mikrotik|aa:bb:cc:dd:ee:02',
        ])
        self.assertEqual(names, {
            'aa:bb:cc:dd:ee:01': 'laptop',
            'aa:bb:cc:dd:ee:02': 'nas',
        })

    def test_skips_unbound(self):
        lines, _ = mt.parse_leases([
            {'address': '192.168.88.10', 'host-name': 'waiting', 'status': 'waiting'},
            {'address': '192.168.88.11', 'host-name': 'nostatus'},
        ])
        self.assertEqual(lines, [])

    def test_skips_disabled(self):
        lines, _ = mt.parse_leases([
            {'address': '192.168.88.10', 'host-name': 'off', 'status': 'bound', 'disabled': 'true'},
            {'address': '192.168.88.11', 'host-name': 'off2', 'status': 'bound', 'disabled': True},
        ])
        self.assertEqual(lines, [])

    def test_hostname_from_mac(self):
        lines, _ = mt.parse_leases([
            {'address': '192.168.88.10', 'mac-address': 'AA:BB:CC:DD:EE:01', 'status': 'bound'},
        ])
        self.assertEqual(lines, ['A|dhcp-aabbccddee01|192.168.88.10|mikrotik|aa:bb:cc:dd:ee:01'])

    def test_skips_without_hostname_and_mac(self):
        lines, _ = mt.parse_leases([{'address': '192.168.88.10', 'status': 'bound'}])
        self.assertEqual(lines, [])

    def test_skips_invalid_address(self):
        lines, _ = mt.parse_leases([
            {'address': '', 'host-name': 'a', 'status': 'bound'},
            {'address': '1.2.3.4; reboot', 'host-name': 'b', 'status': 'bound'},
            {'address': '2001:db8::1', 'host-name': 'c', 'status': 'bound'},
        ])
        self.assertEqual(lines, [])

    def test_invalid_mac_dropped_from_output(self):
        lines, names = mt.parse_leases([
            {'address': '192.168.88.10', 'mac-address': 'x|y', 'host-name': 'pc', 'status': 'bound'},
        ])
        self.assertEqual(lines, ['A|pc|192.168.88.10|mikrotik|'])
        self.assertEqual(names, {})


class TestParseBindings(unittest.TestCase):

    def test_hostname_from_ipv4_lease(self):
        lines = mt.parse_bindings(BINDINGS[:1], {'aa:bb:cc:dd:ee:01': 'laptop'})
        self.assertEqual(lines, ['AAAA|laptop|2001:db8::10|mikrotik|aa:bb:cc:dd:ee:01'])

    def test_skips_delegated_prefix(self):
        self.assertEqual(mt.parse_bindings(BINDINGS[1:], {}), [])

    def test_address_without_prefix_length(self):
        lines = mt.parse_bindings([
            {'address': '2001:db8::10', 'duid': '0x00030001aabbccddee01', 'status': 'bound'},
        ], {})
        self.assertEqual(lines, ['AAAA|dhcp-aabbccddee01|2001:db8::10|mikrotik|aa:bb:cc:dd:ee:01'])

    def test_hostname_from_mac_when_no_ipv4_lease(self):
        lines = mt.parse_bindings(BINDINGS[:1], {})
        self.assertEqual(
            lines, ['AAAA|dhcp-aabbccddee01|2001:db8::10|mikrotik|aa:bb:cc:dd:ee:01'])

    def test_hostname_from_duid_without_mac(self):
        lines = mt.parse_bindings([
            {'address': '2001:db8::20/128', 'duid': '0x00020000ab11deadbeef0001', 'status': 'bound'},
        ], {})
        self.assertEqual(lines, ['AAAA|dhcp-deadbeef0001|2001:db8::20|mikrotik|'])

    def test_skips_unbound_and_disabled(self):
        lines = mt.parse_bindings([
            {'address': '2001:db8::10/128', 'duid': '0x00030001aabbccddee01', 'status': 'waiting'},
            {'address': '2001:db8::11/128', 'duid': '0x00030001aabbccddee02',
             'status': 'bound', 'disabled': 'true'},
        ], {})
        self.assertEqual(lines, [])

    def test_skips_invalid_address(self):
        lines = mt.parse_bindings([
            {'address': '', 'duid': '0x00030001aabbccddee01', 'status': 'bound'},
            {'address': '192.168.88.10', 'duid': '0x00030001aabbccddee01', 'status': 'bound'},
            {'address': 'garbage', 'duid': '0x00030001aabbccddee01', 'status': 'bound'},
        ], {})
        self.assertEqual(lines, [])

    def test_skips_without_duid(self):
        lines = mt.parse_bindings([{'address': '2001:db8::10/128', 'status': 'bound'}], {})
        self.assertEqual(lines, [])


class TestMain(unittest.TestCase):

    @patch.object(_urllib_request, 'urlopen')
    def test_ipv4_and_ipv6(self, mock_urlopen):
        mock_urlopen.side_effect = _urlopen_for(LEASES, BINDINGS)
        out, err, code = _run_main(ARGS)
        self.assertEqual(out.strip().split('\n'), [
            'A|laptop|192.168.88.10|mikrotik|aa:bb:cc:dd:ee:01',
            'A|nas|192.168.88.11|mikrotik|aa:bb:cc:dd:ee:02',
            'AAAA|laptop|2001:db8::10|mikrotik|aa:bb:cc:dd:ee:01',
        ])
        self.assertEqual(err, '')
        self.assertEqual(code, 0)

    @patch.object(_urllib_request, 'urlopen')
    def test_urls_and_auth_header(self, mock_urlopen):
        mock_urlopen.side_effect = _urlopen_for([], [])
        _run_main(ARGS + ['--port', '8443'], password='p@ss:word')
        urls = [c[0][0].full_url for c in mock_urlopen.call_args_list]
        self.assertEqual(urls, [
            'https://192.168.88.1:8443/rest/ip/dhcp-server/lease',
            'https://192.168.88.1:8443/rest/ipv6/dhcp-server/binding',
        ])
        expected = 'Basic ' + base64.b64encode(b'api:p@ss:word').decode()
        for call in mock_urlopen.call_args_list:
            self.assertEqual(call[0][0].get_header('Authorization'), expected)

    @patch.object(_urllib_request, 'urlopen')
    def test_ipv6_host_is_bracketed(self, mock_urlopen):
        mock_urlopen.side_effect = _urlopen_for([], [])
        _run_main(['--host', 'fd00::1', '--user', 'api'])
        self.assertEqual(
            mock_urlopen.call_args_list[0][0][0].full_url,
            'https://[fd00::1]:443/rest/ip/dhcp-server/lease')

    @patch.object(_urllib_request, 'urlopen')
    def test_ssl_verification_off_by_default(self, mock_urlopen):
        mock_urlopen.side_effect = _urlopen_for([], [])
        _run_main(ARGS)
        ctx = mock_urlopen.call_args_list[0][1]['context']
        self.assertEqual(ctx.verify_mode, ssl.CERT_NONE)
        self.assertFalse(ctx.check_hostname)

    @patch.object(_urllib_request, 'urlopen')
    def test_ssl_verification_enabled(self, mock_urlopen):
        mock_urlopen.side_effect = _urlopen_for([], [])
        _run_main(ARGS + ['--verify-ssl', '1'])
        ctx = mock_urlopen.call_args_list[0][1]['context']
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(ctx.check_hostname)

    @patch.object(_urllib_request, 'urlopen')
    def test_ipv4_failure_exits_1(self, mock_urlopen):
        mock_urlopen.side_effect = _urlopen_for(
            urllib.error.HTTPError('https://x', 401, 'Unauthorized', {}, None), BINDINGS)
        out, err, code = _run_main(ARGS)
        self.assertEqual(out, '')
        self.assertIn('Error fetching DHCPv4 leases', err)
        self.assertIn('401', err)
        self.assertEqual(code, 1)

    @patch.object(_urllib_request, 'urlopen')
    def test_ipv6_failure_keeps_ipv4(self, mock_urlopen):
        mock_urlopen.side_effect = _urlopen_for(
            LEASES, urllib.error.URLError('no such command prefix'))
        out, err, code = _run_main(ARGS)
        self.assertEqual(len(out.strip().split('\n')), 2)
        self.assertIn('Warning: DHCPv6 bindings not fetched', err)
        self.assertEqual(code, 0)

    @patch.object(_urllib_request, 'urlopen')
    def test_non_list_response_is_error(self, mock_urlopen):
        mock_urlopen.side_effect = _urlopen_for({'error': 404, 'message': 'Not Found'}, [])
        out, err, code = _run_main(ARGS)
        self.assertEqual(out, '')
        self.assertIn('unexpected response', err)
        self.assertEqual(code, 1)

    @patch.object(_urllib_request, 'urlopen')
    def test_invalid_json_is_error(self, mock_urlopen):
        resp = MagicMock()
        resp.read.return_value = b'not json'
        resp.__enter__.return_value = resp
        mock_urlopen.return_value = resp
        out, err, code = _run_main(ARGS)
        self.assertEqual(out, '')
        self.assertEqual(code, 1)

    @patch.object(_urllib_request, 'urlopen')
    def test_password_not_leaked_in_errors(self, mock_urlopen):
        mock_urlopen.side_effect = _urlopen_for(urllib.error.URLError('refused'), [])
        out, err, code = _run_main(ARGS, password='topsecret')
        self.assertNotIn('topsecret', err)

    def test_missing_required_args(self):
        out, err, code = _run_main(['--host', '192.168.88.1'])
        self.assertEqual(code, 2)


if __name__ == '__main__':
    unittest.main()
