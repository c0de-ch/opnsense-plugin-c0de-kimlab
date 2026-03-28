#!/usr/local/bin/python3
"""Read and return kea-lease-sync status JSON."""

import json
import sys

STATUS_FILE = '/var/run/kealeasesync/status.json'

try:
    with open(STATUS_FILE, 'r') as f:
        data = json.load(f)
    print(json.dumps(data))
except FileNotFoundError:
    print(json.dumps({'status': 'unknown', 'message': 'No status file found'}))
except json.JSONDecodeError:
    print(json.dumps({'status': 'error', 'message': 'Invalid status file'}))
except Exception as e:
    print(json.dumps({'status': 'error', 'message': str(e)}))

sys.exit(0)
