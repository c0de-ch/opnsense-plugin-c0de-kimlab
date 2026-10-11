#!/usr/local/bin/python3
"""Fetch DHCP leases from a MikroTik RouterOS device via its REST API.

Usage: fetch_mikrotik_leases.py --host <host> --user <user>
                                [--port 443] [--verify-ssl 0|1]

Reads the password from the MIKROTIK_PASSWORD environment variable.

Outputs pipe-delimited lines to stdout: RTYPE|hostname|ip|mikrotik|mac
  A     — bound DHCPv4 leases     (/rest/ip/dhcp-server/lease)
  AAAA  — bound DHCPv6 addresses  (/rest/ipv6/dhcp-server/binding)

DHCPv6 bindings carry no hostname, so the name is taken from the DHCPv4
lease with the same MAC address (derived from the client DUID, or from the
client's link-local address when that is EUI-64 based). Delegated prefixes
are skipped.

If the DHCPv4 fetch fails: prints the error to stderr and exits 1.
If only the DHCPv6 fetch fails: prints a warning to stderr, still outputs
the DHCPv4 leases and exits 0.
"""

import argparse
import base64
import ipaddress
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request

LEASE4_PATH = '/rest/ip/dhcp-server/lease'
BINDING6_PATH = '/rest/ipv6/dhcp-server/binding'

MAC_RE = re.compile(r'^[0-9a-f]{2}(:[0-9a-f]{2}){5}$')


def clean_hostname(name):
    """Normalize hostname: lowercase, strip domain, remove invalid chars."""
    if not name:
        return None
    name = name.split('.')[0].lower()
    name = re.sub(r'[^a-z0-9-]', '', name)
    if not name:
        return None
    if re.fullmatch(r'[0-9a-f]{12}', name):
        return None
    return name


def clean_mac(mac):
    """Normalize a MAC address to lowercase aa:bb:cc:dd:ee:ff, or '' if invalid."""
    mac = (mac or '').strip().lower().replace('-', ':')
    return mac if MAC_RE.match(mac) else ''


def duid_hex(duid):
    """Return a DUID as a plain lowercase hex string ('0x' prefix and colons removed)."""
    duid = (duid or '').strip().lower()
    if duid.startswith('0x'):
        duid = duid[2:]
    duid = duid.replace(':', '')
    return duid if re.fullmatch(r'[0-9a-f]*', duid) else ''


def mac_from_duid(duid):
    """Extract the MAC address from an Ethernet DUID-LLT or DUID-LL, or ''."""
    duid = duid_hex(duid)
    # DUID-LLT: type 1, hw type 1, 4-byte time, MAC — DUID-LL: type 3, hw type 1, MAC
    if (duid.startswith('00010001') and len(duid) == 28) or \
            (duid.startswith('00030001') and len(duid) == 20):
        raw = duid[-12:]
        return ':'.join(raw[i:i + 2] for i in range(0, 12, 2))
    return ''


def mac_from_link_local(address):
    """Extract the MAC address from an EUI-64 based link-local address, or ''."""
    try:
        addr = ipaddress.IPv6Address(address or '')
    except ValueError:
        return ''
    raw = addr.packed
    if not addr.is_link_local or raw[11:13] != b'\xff\xfe':
        return ''
    # EUI-64: MAC split around ff:fe, with the universal/local bit flipped
    mac = bytes([raw[8] ^ 0x02]) + raw[9:11] + raw[13:16]
    return ':'.join('{:02x}'.format(b) for b in mac)


def is_true(value):
    """RouterOS REST returns booleans as the strings 'true'/'false'."""
    return value in (True, 'true')


def is_active(entry):
    return entry.get('status') == 'bound' and not is_true(entry.get('disabled'))


def parse_leases(data):
    """Convert DHCPv4 leases to output lines and a MAC → hostname map."""
    lines = []
    names_by_mac = {}
    for lease in data:
        if not is_active(lease):
            continue

        try:
            address = str(ipaddress.IPv4Address(lease.get('address', '')))
        except ValueError:
            continue

        mac = clean_mac(lease.get('mac-address', ''))
        hostname = lease.get('host-name', '')
        if not hostname and mac:
            hostname = 'dhcp-' + mac.replace(':', '')

        hostname = clean_hostname(hostname)
        if not hostname:
            continue

        if mac:
            names_by_mac.setdefault(mac, hostname)
        lines.append('A|{}|{}|mikrotik|{}'.format(hostname, address, mac))
    return lines, names_by_mac


def parse_bindings(data, names_by_mac):
    """Convert DHCPv6 address bindings to output lines."""
    lines = []
    for binding in data:
        if not is_active(binding):
            continue

        try:
            iface = ipaddress.IPv6Interface(binding.get('address', ''))
        except ValueError:
            continue
        # Only single addresses — skip delegated prefixes
        if iface.network.prefixlen != 128:
            continue

        duid = duid_hex(binding.get('duid', ''))
        mac = mac_from_duid(duid) or mac_from_link_local(binding.get('client-address', ''))
        hostname = names_by_mac.get(mac) if mac else None
        if not hostname and mac:
            hostname = 'dhcp-' + mac.replace(':', '')
        elif not hostname and duid:
            hostname = 'dhcp-' + duid[-12:]

        hostname = clean_hostname(hostname)
        if not hostname:
            continue

        lines.append('AAAA|{}|{}|mikrotik|{}'.format(hostname, iface.ip, mac))
    return lines


def fetch_json(base_url, path, user, password, ctx):
    credentials = base64.b64encode(
        '{}:{}'.format(user, password).encode()
    ).decode()
    req = urllib.request.Request(base_url + path)
    req.add_header('Authorization', 'Basic {}'.format(credentials))

    with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
        data = json.loads(resp.read().decode())
    if not isinstance(data, list):
        raise ValueError('unexpected response from {}'.format(path))
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', default='443')
    parser.add_argument('--user', required=True)
    parser.add_argument('--verify-ssl', default='0')
    args = parser.parse_args()

    password = os.environ.get('MIKROTIK_PASSWORD', '')
    # Bracket bare IPv6 literals
    host = '[{}]'.format(args.host) if ':' in args.host else args.host
    base_url = 'https://{}:{}'.format(host, args.port)

    ctx = ssl.create_default_context()
    if args.verify_ssl != '1':
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    try:
        leases = fetch_json(base_url, LEASE4_PATH, args.user, password, ctx)
    except Exception as e:
        print('Error fetching DHCPv4 leases: {}'.format(e), file=sys.stderr)
        sys.exit(1)

    lines, names_by_mac = parse_leases(leases)

    try:
        bindings = fetch_json(base_url, BINDING6_PATH, args.user, password, ctx)
        lines += parse_bindings(bindings, names_by_mac)
    except Exception as e:
        print('Warning: DHCPv6 bindings not fetched: {}'.format(e), file=sys.stderr)

    for line in lines:
        print(line)


if __name__ == '__main__':
    main()
