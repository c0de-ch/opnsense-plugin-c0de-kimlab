#!/usr/local/bin/python3
"""Read kea-lease-sync log entries from system log.

Handles both syslog-ng (OPNsense 24.x+ plain text) and legacy clog format.
"""

import subprocess
import sys

LOG_TAG = 'kea-lease-sync'
MAX_LINES = 50


def try_plain(path):
    """Read a plain text log file and filter for our tag."""
    try:
        with open(path, 'r', errors='replace') as f:
            return [l.rstrip() for l in f if LOG_TAG in l][-MAX_LINES:]
    except Exception:
        return None


def try_clog(path):
    """Read a clog binary log file via the clog command."""
    try:
        r = subprocess.run(
            ['/usr/sbin/clog', path],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0:
            return [l for l in r.stdout.splitlines()
                    if LOG_TAG in l][-MAX_LINES:]
    except Exception:
        pass
    return None


# syslog-ng plain text (OPNsense 24.x+)
lines = try_plain('/var/log/system/latest.log')
if lines is not None:
    print('\n'.join(lines))
    sys.exit(0)

# clog binary format (legacy OPNsense)
lines = try_clog('/var/log/system.log')
if lines is not None:
    print('\n'.join(lines))
    sys.exit(0)

# plain /var/log/system.log as last resort
lines = try_plain('/var/log/system.log')
if lines is not None:
    print('\n'.join(lines))
    sys.exit(0)

sys.exit(0)
