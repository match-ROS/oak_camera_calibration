"""Transaction boundary tests. These never connect to the physical camera."""
import fcntl
import importlib.util
import json
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

source = Path(__file__).resolve().parents[1] / 'tools/oak4_photo_service.py'
spec = importlib.util.spec_from_file_location('oak4_photo_service', source)
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.capture = service.PhotoCapture(Path(self.temp.name))

    def configure(self):
        ws = self.capture.workspace
        inventory = ws / 'src/multi_arm_manipulation_UWA/config/hardware_inventory.yaml'
        inventory.parent.mkdir(parents=True)
        inventory.write_text('cameras:\n  oak4:\n    ip: 192.168.8.238\n    device_id: "1479883285"\n')
        for name in ('.venvs/oak4/bin/python', 'setup/oak4/bin/oakctl'):
            p = ws / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('#!/bin/sh\nexit 0\n')
            p.chmod(0o755)

    def test_invalid_request_creates_no_transaction(self):
        for kwargs in (dict(frames=0), dict(frames=33), dict(iso=99), dict(mode='raw'),
                       dict(focus=-1), dict(focus=256), dict(focus=True),
                       dict(mode='depth_hq', focus=116)):
            with self.assertRaises(ValueError):
                self.capture.capture(**kwargs)
        self.assertFalse(self.capture.root.exists())

    def test_busy_thread_preserves_running_status(self):
        self.capture.update(phase='CAPTURING')
        self.capture.mutex.acquire()
        try:
            with self.assertRaisesRegex(RuntimeError, 'active'):
                self.capture.capture()
            self.assertEqual(self.capture.status()['phase'], 'CAPTURING')
        finally:
            self.capture.mutex.release()

    def test_cli_service_lock_is_nonblocking(self):
        self.capture.root.mkdir(parents=True)
        with (self.capture.root / '.capture.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(RuntimeError, 'CLI/service'):
                self.capture.capture()
        self.assertFalse(self.capture.mutex.locked())

    def test_live_view_is_preserved(self):
        with patch.object(service.subprocess, 'run', return_value=Mock(returncode=0)):
            with self.assertRaisesRegex(RuntimeError, 'live view is active'):
                self.capture.capture()
        self.assertFalse(list(self.capture.root.glob('*-hq-*')))

    def test_depth_rejects_rgb_only_controls_and_short_burst(self):
        for kwargs in (dict(mode='depth_hq', iso=200), dict(mode='depth_hq', frames=3)):
            with self.assertRaises(ValueError):
                self.capture.capture(**kwargs)
        self.assertFalse(self.capture.root.exists())

    def test_depth_and_rgb_share_thread_exclusion(self):
        self.capture.update(phase='CAPTURING', mode='depth_hq')
        self.capture.mutex.acquire()
        try:
            for mode in ('hq', 'depth_hq'):
                with self.assertRaisesRegex(RuntimeError, 'active'):
                    self.capture.capture(mode)
            self.assertEqual(self.capture.status()['mode'], 'depth_hq')
        finally:
            self.capture.mutex.release()

    def test_worker_failure_is_not_accepted(self):
        self.configure()
        child = Mock()
        child.wait.return_value = 1
        with patch.object(service.subprocess, 'run', return_value=Mock(returncode=3)), \
             patch.object(service.subprocess, 'Popen', return_value=child):
            with self.assertRaisesRegex(RuntimeError, 'worker exited 1'):
                self.capture.capture()
        self.assertEqual(self.capture.status()['phase'], 'FAILED')
        failures = list(self.capture.root.glob('*/failure.json'))
        self.assertEqual(len(failures), 1)
        self.assertIn('worker exited', json.loads(failures[0].read_text())['error'])
        self.assertFalse(list(self.capture.root.glob('*/result.json')))

    def test_rgbd_uses_shared_lock_and_preserves_active_preview(self):
        self.capture.root.mkdir(parents=True)
        with (self.capture.root / '.capture.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(RuntimeError, 'CLI/service'):
                self.capture.capture(mode='rgbd')
        with patch.object(service.subprocess, 'run', return_value=Mock(returncode=0)):
            with self.assertRaisesRegex(RuntimeError, 'live view is active'):
                self.capture.capture(mode='rgbd')
        self.assertFalse((self.capture.workspace / 'setup/oak4/rgbd').exists())

    def test_rgbd_dispatch_accepts_focus_and_preserves_mode_arguments(self):
        self.configure()
        calls = []
        def start(command, **kwargs):
            calls.append(command)
            output = Path(command[command.index('--output') + 1])
            (output / 'metadata.json').write_text(json.dumps(dict(success=True,
                standard=dict(path='preview.png'), data_files=dict(intrinsics='cam_K.txt'))))
            return Mock(wait=Mock(return_value=0))
        with patch.object(service.subprocess, 'run', return_value=Mock(returncode=3)), \
             patch.object(service.subprocess, 'Popen', side_effect=start):
            result = self.capture.capture(mode='rgbd', frames=4)
        self.assertIn('setup/oak4/rgbd', result['directory'])
        self.assertTrue(any('oak4_rgbd_capture.py' in part for part in calls[0]))
        self.assertNotIn('--mode', calls[0])
        self.assertNotIn('--iso', calls[0])
        self.assertEqual(calls[0][calls[0].index('--focus') + 1], '116')
        self.assertEqual(self.capture.status()['phase'], 'READY')

    def test_timeout_cleans_worker_group_and_releases_lock(self):
        self.configure()
        child = Mock(pid=123456)
        child.wait.side_effect = [subprocess.TimeoutExpired('worker', 300), 0]
        with patch.object(service.subprocess, 'run', return_value=Mock(returncode=3)), \
             patch.object(service.subprocess, 'Popen', return_value=child), \
             patch.object(service.os, 'killpg') as kill:
            with self.assertRaises(subprocess.TimeoutExpired):
                self.capture.capture()
        kill.assert_called_once_with(child.pid, signal.SIGTERM)
        self.assertFalse(self.capture.mutex.locked())
        with (self.capture.root / '.capture.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.assertEqual(self.capture.status()['phase'], 'FAILED')


if __name__ == '__main__':
    unittest.main()
