#!/usr/bin/env python3
"""Tests for get_hosts.py — ARP/NDP parsing and online status."""

import importlib.util
import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Load get_hosts as a module from its file path
SCRIPT_DIR = os.path.join(
    os.path.dirname(__file__), '..', 'net', 'kealeasesync', 'src',
    'opnsense', 'scripts', 'OPNsense', 'KeaLeaseSync'
)

spec = importlib.util.spec_from_file_location(
    'get_hosts_mod',
    os.path.join(SCRIPT_DIR, 'get_hosts.py'),
    submodule_search_locations=[]
)
# We need to import only the functions, not execute the main block.
# Read the source and exec only the function definitions.
with open(os.path.join(SCRIPT_DIR, 'get_hosts.py')) as f:
    source = f.read()

# Extract function definitions by exec-ing in a controlled namespace
_mod_ns = {}
# Only exec the imports and function defs, skip the main block
lines = source.split('\n')
func_lines = []
in_main = False
for line in lines:
    # Stop before the main block (top-level try)
    if line.startswith('try:') and 'HOSTS_FILE' not in line:
        in_main = True
    if line.startswith('try:') and in_main:
        break
    func_lines.append(line)
exec('\n'.join(func_lines), _mod_ns)

get_arp_ips = _mod_ns['get_arp_ips']
get_ndp_ips = _mod_ns['get_ndp_ips']


class TestGetArpIps(unittest.TestCase):
    """Tests for get_arp_ips() function."""

    @patch('subprocess.run')
    def test_parses_standard_arp_output(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=(
                '? (192.168.1.1) at aa:bb:cc:dd:ee:ff on em0 expires in 1200 seconds [ethernet]\n'
                '? (192.168.1.2) at 11:22:33:44:55:66 on em0 expires in 600 seconds [ethernet]\n'
            )
        )
        result = get_arp_ips()
        self.assertEqual(result, {'192.168.1.1', '192.168.1.2'})

    @patch('subprocess.run')
    def test_skips_incomplete_entries(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=(
                '? (192.168.1.1) at aa:bb:cc:dd:ee:ff on em0 expires in 1200 seconds [ethernet]\n'
                '? (192.168.1.99) at (incomplete) on em0 [ethernet]\n'
            )
        )
        result = get_arp_ips()
        self.assertEqual(result, {'192.168.1.1'})

    @patch('subprocess.run')
    def test_empty_arp_table(self, mock_run):
        mock_run.return_value = MagicMock(stdout='')
        result = get_arp_ips()
        self.assertEqual(result, set())

    @patch('subprocess.run')
    def test_handles_subprocess_error(self, mock_run):
        mock_run.side_effect = FileNotFoundError('arp not found')
        result = get_arp_ips()
        self.assertEqual(result, set())

    @patch('subprocess.run')
    def test_handles_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired('arp', 5)
        result = get_arp_ips()
        self.assertEqual(result, set())

    @patch('subprocess.run')
    def test_skips_lines_without_at(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout='some header line\n? (192.168.1.1) at aa:bb:cc:dd:ee:ff on em0\n'
        )
        result = get_arp_ips()
        self.assertEqual(result, {'192.168.1.1'})

    @patch('subprocess.run')
    def test_skips_incomplete_in_rest(self, mock_run):
        """Entry where 'incomplete' appears after the closing paren."""
        mock_run.return_value = MagicMock(
            stdout='? (192.168.1.5) at ff:ff:ff:ff:ff:ff on em0 incomplete\n'
        )
        result = get_arp_ips()
        self.assertEqual(result, set())

    @patch('subprocess.run')
    def test_multiple_interfaces(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=(
                '? (10.0.0.1) at aa:bb:cc:dd:ee:ff on em0\n'
                '? (172.16.0.1) at 11:22:33:44:55:66 on em1\n'
            )
        )
        result = get_arp_ips()
        self.assertEqual(result, {'10.0.0.1', '172.16.0.1'})


class TestGetNdpIps(unittest.TestCase):
    """Tests for get_ndp_ips() function."""

    @patch('subprocess.run')
    def test_parses_reachable_neighbors(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=(
                'Neighbor                   Linklayer Address  Netif Expire    S Flags\n'
                'fe80::1                    aa:bb:cc:dd:ee:ff  em0   23h59m57s R R\n'
                '2001:db8::10               11:22:33:44:55:66  em0   22h30m00s R R\n'
            )
        )
        result = get_ndp_ips()
        self.assertEqual(result, {'fe80::1', '2001:db8::10'})

    @patch('subprocess.run')
    def test_includes_stale_entries(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout='fe80::1                    aa:bb:cc:dd:ee:ff  em0   23h59m57s S R\n'
        )
        result = get_ndp_ips()
        self.assertEqual(result, {'fe80::1'})

    @patch('subprocess.run')
    def test_includes_delay_and_probe(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=(
                'fe80::1  aa:bb:cc:dd:ee:ff  em0  1s  D R\n'
                'fe80::2  11:22:33:44:55:66  em0  2s  P R\n'
            )
        )
        result = get_ndp_ips()
        self.assertEqual(result, {'fe80::1', 'fe80::2'})

    @patch('subprocess.run')
    def test_skips_unknown_states(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout=(
                'fe80::1  aa:bb:cc:dd:ee:ff  em0  1s  R R\n'
                'fe80::2  11:22:33:44:55:66  em0  2s  N R\n'
            )
        )
        result = get_ndp_ips()
        self.assertEqual(result, {'fe80::1'})

    @patch('subprocess.run')
    def test_skips_header_line(self, mock_run):
        """Header line has no colons in first field."""
        mock_run.return_value = MagicMock(
            stdout='Neighbor                   Linklayer Address  Netif Expire    S Flags\n'
        )
        result = get_ndp_ips()
        self.assertEqual(result, set())

    @patch('subprocess.run')
    def test_empty_ndp_table(self, mock_run):
        mock_run.return_value = MagicMock(stdout='')
        result = get_ndp_ips()
        self.assertEqual(result, set())

    @patch('subprocess.run')
    def test_handles_subprocess_error(self, mock_run):
        mock_run.side_effect = FileNotFoundError('ndp not found')
        result = get_ndp_ips()
        self.assertEqual(result, set())

    @patch('subprocess.run')
    def test_short_line_no_state(self, mock_run):
        """Line with fewer than 5 parts — state is empty string."""
        mock_run.return_value = MagicMock(
            stdout='fe80::1  aa:bb:cc:dd:ee:ff  em0  1s\n'
        )
        result = get_ndp_ips()
        self.assertEqual(result, set())


class TestOnlineStatusMerge(unittest.TestCase):
    """Test the online status merge logic (main block of get_hosts.py)."""

    def _run_merge(self, hosts_data, arp_ips, ndp_ips):
        """Simulate the main block logic."""
        reachable = arp_ips | ndp_ips
        hosts = hosts_data.get('hosts', [])
        for host in hosts:
            host['online'] = host.get('ip', '') in reachable
        return hosts

    def test_ipv4_host_online(self):
        hosts = self._run_merge(
            {'hosts': [{'hostname': 'pc1', 'ip': '192.168.1.10', 'rtype': 'A'}]},
            {'192.168.1.10'}, set()
        )
        self.assertTrue(hosts[0]['online'])

    def test_ipv4_host_offline(self):
        hosts = self._run_merge(
            {'hosts': [{'hostname': 'pc1', 'ip': '192.168.1.10', 'rtype': 'A'}]},
            {'192.168.1.99'}, set()
        )
        self.assertFalse(hosts[0]['online'])

    def test_ipv6_host_online_via_ndp(self):
        hosts = self._run_merge(
            {'hosts': [{'hostname': 'srv1', 'ip': '2001:db8::10', 'rtype': 'AAAA'}]},
            set(), {'2001:db8::10'}
        )
        self.assertTrue(hosts[0]['online'])

    def test_ipv6_host_offline(self):
        hosts = self._run_merge(
            {'hosts': [{'hostname': 'srv1', 'ip': '2001:db8::10', 'rtype': 'AAAA'}]},
            set(), set()
        )
        self.assertFalse(hosts[0]['online'])

    def test_mixed_hosts(self):
        hosts = self._run_merge(
            {'hosts': [
                {'hostname': 'pc1', 'ip': '192.168.1.10', 'rtype': 'A'},
                {'hostname': 'srv1', 'ip': '2001:db8::10', 'rtype': 'AAAA'},
                {'hostname': 'pc2', 'ip': '192.168.1.20', 'rtype': 'A'},
            ]},
            {'192.168.1.10'}, {'2001:db8::10'}
        )
        self.assertTrue(hosts[0]['online'])
        self.assertTrue(hosts[1]['online'])
        self.assertFalse(hosts[2]['online'])

    def test_empty_hosts(self):
        hosts = self._run_merge({'hosts': []}, {'192.168.1.1'}, set())
        self.assertEqual(hosts, [])

    def test_host_missing_ip_field(self):
        hosts = self._run_merge(
            {'hosts': [{'hostname': 'noip'}]},
            {'192.168.1.1'}, set()
        )
        self.assertFalse(hosts[0]['online'])

    def test_no_hosts_key(self):
        hosts = self._run_merge({}, {'192.168.1.1'}, set())
        self.assertEqual(hosts, [])


if __name__ == '__main__':
    unittest.main()
