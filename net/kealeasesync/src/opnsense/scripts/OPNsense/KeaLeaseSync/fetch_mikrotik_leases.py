#!/usr/local/bin/python3
"""Fetch DHCP leases from MikroTik RouterOS REST API.

Outputs lines in format: A|hostname|ip|type
Reads MIKROTIK_PASSWORD from environment variable.
"""

import argparse
import base64
import json
import os
import re
import ssl
import sys
import urllib.request
import urllib.error


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', default='443')
    parser.add_argument('--user', required=True)
    parser.add_argument('--verify-ssl', default='0')
    args = parser.parse_args()

    password = os.environ.get('MIKROTIK_PASSWORD', '')
    url = 'https://{}:{}/rest/ip/dhcp-server/lease'.format(args.host, args.port)

    credentials = base64.b64encode(
        '{}:{}'.format(args.user, password).encode()
    ).decode()
    req = urllib.request.Request(url)
    req.add_header('Authorization', 'Basic {}'.format(credentials))

    ctx = ssl.create_default_context()
    if args.verify_ssl != '1':
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        print('Error fetching MikroTik leases: {}'.format(e), file=sys.stderr)
        sys.exit(1)

    for lease in data:
        if lease.get('status') != 'bound':
            continue
        if lease.get('disabled') in (True, 'true'):
            continue

        address = lease.get('address', '')
        if not address:
            continue

        hostname = lease.get('host-name', '')
        mac = lease.get('mac-address', '')

        if not hostname and mac:
            hostname = 'dhcp-' + mac.replace(':', '')

        hostname = clean_hostname(hostname)
        if not hostname:
            continue

        lease_type = 'static' if lease.get('dynamic') in (False, 'false') else 'dynamic'
        print('A|{}|{}|{}'.format(hostname, address, lease_type))


if __name__ == '__main__':
    main()
