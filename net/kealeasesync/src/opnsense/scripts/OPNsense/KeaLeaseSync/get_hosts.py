#!/usr/local/bin/python3
"""Read hosts JSON and cross-reference with ARP/NDP tables for online status."""

import json
import subprocess
import sys

HOSTS_FILE = '/var/run/kealeasesync/hosts.json'


def get_arp_ips():
    """Parse ARP table to get set of IPv4 addresses that are reachable."""
    arp_ips = set()
    try:
        result = subprocess.run(
            ['/usr/sbin/arp', '-an'],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            # Format: ? (192.168.1.1) at aa:bb:cc:dd:ee:ff on em0 ...
            if ' at ' in line and '(incomplete)' not in line:
                start = line.find('(')
                end = line.find(')')
                if start != -1 and end != -1:
                    ip = line[start + 1:end]
                    # Skip entries with "(incomplete)" MAC
                    rest = line[end:]
                    if 'incomplete' not in rest:
                        arp_ips.add(ip)
    except Exception:
        pass
    return arp_ips


def get_ndp_ips():
    """Parse NDP table to get set of IPv6 addresses that are reachable."""
    ndp_ips = set()
    try:
        result = subprocess.run(
            ['/usr/sbin/ndp', '-an'],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            # Format: Neighbor                   Linklayer Address  Netif Expire    S Flags
            #         fe80::1                    aa:bb:cc:dd:ee:ff  em0   23h59m57s R R
            parts = line.split()
            if len(parts) >= 4 and ':' in parts[0] and ':' in parts[1]:
                state = parts[4] if len(parts) >= 5 else ''
                # R=reachable, S=stale, D=delay, P=probe — all indicate a known neighbor
                if state in ('R', 'S', 'D', 'P'):
                    ndp_ips.add(parts[0])
    except Exception:
        pass
    return ndp_ips


try:
    with open(HOSTS_FILE, 'r') as f:
        data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    print(json.dumps({'hosts': []}))
    sys.exit(0)

reachable_ips = get_arp_ips() | get_ndp_ips()

hosts = data.get('hosts', [])
for host in hosts:
    if host.get('type') == 'peer':
        host['online'] = None
    else:
        host['online'] = host.get('ip', '') in reachable_ips

print(json.dumps({'hosts': hosts}))
sys.exit(0)
