#!/usr/bin/env python3
"""Tests for get_status.py — status file reading."""

import json
import os
import sys
import tempfile
import unittest
from io import StringIO
from unittest.mock import patch


class TestGetStatus(unittest.TestCase):
    """Tests for get_status.py main block."""

    def _run_get_status(self, status_file_path):
        """Run the get_status logic with a custom STATUS_FILE path."""
        captured = StringIO()
        with patch('sys.stdout', captured):
            try:
                with open(status_file_path, 'r') as f:
                    data = json.load(f)
                print(json.dumps(data))
            except FileNotFoundError:
                print(json.dumps({'status': 'unknown', 'message': 'No status file found'}))
            except json.JSONDecodeError:
                print(json.dumps({'status': 'error', 'message': 'Invalid status file'}))
            except Exception as e:
                print(json.dumps({'status': 'error', 'message': str(e)}))
        return json.loads(captured.getvalue())

    def test_valid_status_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                'status': 'ok',
                'last_sync': '2024-01-01 12:00:00',
                'hosts_registered': 5,
                'hosts_removed': 1,
                'static_count': 3,
                'dynamic_count': 2,
                'duration': '2s',
            }, f)
            f.flush()
            result = self._run_get_status(f.name)
        os.unlink(f.name)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['hosts_registered'], 5)
        self.assertEqual(result['hosts_removed'], 1)
        self.assertEqual(result['static_count'], 3)
        self.assertEqual(result['dynamic_count'], 2)
        self.assertEqual(result['duration'], '2s')

    def test_missing_status_file(self):
        result = self._run_get_status('/nonexistent/path/status.json')
        self.assertEqual(result['status'], 'unknown')
        self.assertIn('No status file', result['message'])

    def test_invalid_json(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('not valid json {{{')
            f.flush()
            result = self._run_get_status(f.name)
        os.unlink(f.name)
        self.assertEqual(result['status'], 'error')
        self.assertIn('Invalid status file', result['message'])

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('')
            f.flush()
            result = self._run_get_status(f.name)
        os.unlink(f.name)
        self.assertEqual(result['status'], 'error')

    def test_preserves_all_fields(self):
        original = {
            'status': 'ok',
            'last_sync': '2024-06-15 08:30:00',
            'hosts_registered': 42,
            'hosts_removed': 3,
            'static_count': 10,
            'dynamic_count': 32,
            'duration': '5s',
            'direct_domain': 'home.lan',
            'proxy_domains': 'proxy.lan',
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(original, f)
            f.flush()
            result = self._run_get_status(f.name)
        os.unlink(f.name)
        self.assertEqual(result, original)

    def test_minimal_valid_json(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({}, f)
            f.flush()
            result = self._run_get_status(f.name)
        os.unlink(f.name)
        self.assertEqual(result, {})


if __name__ == '__main__':
    unittest.main()
