#!/usr/local/bin/python3
"""Fetch hosts from a remote OPNsense peer's KeaLeaseSync API.

Usage: fetch_peer_hosts.py <url> <api_key>

Outputs pipe-delimited lines to stdout: RTYPE|hostname|ip|peer
Only includes hosts with type=static or type=dynamic (skips type=peer
to prevent transitive propagation between peers).

On any error: prints warning to stderr, outputs nothing to stdout, exits 0.
"""

import json
import ssl
import sys
import urllib.error
import urllib.request


def fetch(url, api_key):
    endpoint = url.rstrip('/') + '/api/kealeasesync/peer/hosts'

    req = urllib.request.Request(endpoint)
    req.add_header('X-API-Key', api_key)

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
        mac = host.get('mac', '')
        if hostname and ip:
            print('{}|{}|{}|peer|{}'.format(rtype, hostname, ip, mac))


def main():
    if len(sys.argv) != 3:
        print('Usage: fetch_peer_hosts.py <url> <api_key>',
              file=sys.stderr)
        sys.exit(0)

    url, api_key = sys.argv[1], sys.argv[2]

    try:
        fetch(url, api_key)
    except Exception as e:
        print('Peer fetch error: {}'.format(e), file=sys.stderr)


if __name__ == '__main__':
    main()
