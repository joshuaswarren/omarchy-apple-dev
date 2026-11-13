"""Security boundaries for the mirror wrapper, without a device or pymobiledevice3."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('ipad_screen', Path(__file__).parents[1] / 'tools/ipad-screen.py')
screen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(screen)


class ScreenSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        config = Path(self.temp.name) / 'config'
        self.config_patch = patch.multiple(screen, CONFIG=config, PASSWORD=config / 'password')
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)

    def test_generated_password_is_private_and_persistent(self):
        first = screen.password()
        self.assertGreaterEqual(len(first), 32)
        self.assertEqual(first, screen.password())
        self.assertEqual(screen.PASSWORD.stat().st_mode & 0o777, 0o600)
        self.assertEqual(screen.CONFIG.stat().st_mode & 0o777, 0o700)

    def test_refuses_empty_or_insecure_password(self):
        screen.password()
        screen.PASSWORD.write_text('\n')
        with self.assertRaises(RuntimeError):
            screen.password()
        screen.PASSWORD.write_text('test-secret')
        screen.PASSWORD.chmod(0o644)
        with self.assertRaises(RuntimeError):
            screen.password()

    def test_refuses_password_symlink_without_touching_target(self):
        screen.private_dir(screen.CONFIG)
        target = Path(self.temp.name) / 'target'
        target.write_text('untouched')
        screen.PASSWORD.symlink_to(target)
        with self.assertRaises(OSError):
            screen.password()
        self.assertEqual(target.read_text(), 'untouched')

    def test_refuses_shared_or_symlink_config_directory(self):
        screen.CONFIG.mkdir(mode=0o755)
        with self.assertRaises(RuntimeError):
            screen.password()
        screen.CONFIG.rmdir()
        screen.CONFIG.symlink_to(Path(self.temp.name), target_is_directory=True)
        with self.assertRaises(RuntimeError):
            screen.password()

    def test_only_tailscale_ipv4_is_accepted(self):
        for value in ['0.0.0.0', '192.168.1.2', '127.0.0.1', '100.1.2.3', '::1', '100.70.1.2\n100.70.1.3', '']:
            with self.subTest(value=value), patch.object(screen, 'run', return_value=value):
                with self.assertRaises((ValueError, RuntimeError)):
                    screen.tailnet_ip()
        with patch.object(screen, 'run', return_value='100.114.95.95\n'):
            self.assertEqual(screen.tailnet_ip(), '100.114.95.95')

    def test_upgrade_never_uses_system_python(self):
        with patch.object(screen, 'version_ok', return_value=False), patch.object(screen.sys, 'prefix', screen.sys.base_prefix), patch.object(screen.subprocess, 'run') as run:
            with self.assertRaises(RuntimeError):
                screen.ensure_version(True)
            run.assert_not_called()

    def test_old_version_requires_explicit_upgrade(self):
        with patch.object(screen, 'version_ok', return_value=False), patch.object(screen.subprocess, 'run') as run:
            with self.assertRaises(RuntimeError):
                screen.ensure_version(False)
            run.assert_not_called()

    def test_stale_pid_cannot_stop_reused_process(self):
        state = Path(self.temp.name) / 'state'
        state.mkdir()
        (state / 'process.json').write_text('{"pid":123,"starttime":"old"}')
        with patch.object(screen, 'STATE', state), patch.object(screen, 'identity', return_value='new'):
            self.assertIsNone(screen.current())


if __name__ == '__main__':
    unittest.main()
