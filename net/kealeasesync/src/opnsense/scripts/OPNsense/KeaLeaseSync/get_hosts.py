#!/usr/local/bin/python3
"""Read hosts JSON and cross-reference with ARP table for online status."""

import json
import subprocess
import sys

HOSTS_FILE = '/var/run/kealeasesync/hosts.json'


def get_arp_ips():
    """Parse ARP table to get set of IPs that are reachable."""
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


try:
    with open(HOSTS_FILE, 'r') as f:
        data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    print(json.dumps({'hosts': []}))
    sys.exit(0)

arp_ips = get_arp_ips()

hosts = data.get('hosts', [])
for host in hosts:
    host['online'] = host.get('ip', '') in arp_ips

print(json.dumps({'hosts': hosts}))
sys.exit(0)
