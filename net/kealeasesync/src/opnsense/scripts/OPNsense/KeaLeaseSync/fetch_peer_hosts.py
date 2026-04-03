#!/usr/local/bin/python3
"""Fetch hosts from a remote OPNsense peer's KeaLeaseSync API.

Usage: fetch_peer_hosts.py <url> <api_key> <api_secret>

Outputs pipe-delimited lines to stdout: RTYPE|hostname|ip|peer
Only includes hosts with type=static or type=dynamic (skips type=peer
to prevent transitive propagation between peers).

On any error: prints warning to stderr, outputs nothing to stdout, exits 0.
"""

import base64
import json
import ssl
import sys
import urllib.error
import urllib.request


def fetch(url, api_key, api_secret):
    endpoint = url.rstrip('/') + '/api/kealeasesync/service/hosts'

    credentials = base64.b64encode(
        '{}:{}'.format(api_key, api_secret).encode()
    ).decode()

    req = urllib.request.Request(endpoint)
    req.add_header('Authorization', 'Basic ' + credentials)

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    resp = urllib.request.urlopen(req, timeout=10, context=ctx)
    data = json.loads(resp.read().decode())

    for host in data.get('hosts', []):
        htype = host.get('type', '')
        # Only take local hosts from the peer — skip peer-of-peer to avoid loops
        if htype not in ('static', 'dynamic'):
            continue
        hostname = host.get('hostname', '')
        ip = host.get('ip', '')
        rtype = host.get('rtype', 'A')
        if hostname and ip:
            print('{}|{}|{}|peer'.format(rtype, hostname, ip))


def main():
    if len(sys.argv) != 4:
        print('Usage: fetch_peer_hosts.py <url> <api_key> <api_secret>',
              file=sys.stderr)
        sys.exit(0)

    url, api_key, api_secret = sys.argv[1], sys.argv[2], sys.argv[3]

    try:
        fetch(url, api_key, api_secret)
    except Exception as e:
        print('Peer fetch error: {}'.format(e), file=sys.stderr)


if __name__ == '__main__':
    main()
