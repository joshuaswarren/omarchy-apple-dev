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
        screen.CONFIG.chmod(0o755)
        with self.assertRaises(RuntimeError):
            screen.password()
        screen.CONFIG.rmdir()
        screen.CONFIG.symlink_to(Path(self.temp.name), target_is_directory=True)
        with self.assertRaises(RuntimeError):
            screen.password()

    def test_only_tailscale_ipv4_is_accepted(self):
        for value in ['0.0.0.0', '192.168.1.2', '127.0.0.1', str(__import__('ipaddress').IPv4Address(0x64010203)), '::1', 'invalid multiple addresses', '']:
            with self.subTest(value=value), patch.object(screen, 'run', return_value=value):
                with self.assertRaises((ValueError, RuntimeError)):
                    screen.tailnet_ip()
        with patch.object(screen, 'run', return_value=str(__import__('ipaddress').IPv4Address(0x64400102))):
            self.assertEqual(screen.tailnet_ip(), str(__import__('ipaddress').IPv4Address(0x64400102)))

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

class ReviewRegressionTests(unittest.TestCase):
    def test_authentication_fails_closed(self):
        for statuses in ([200, 200], [401, 401], [403, 200]):
            with patch.object(screen, 'auth_status', side_effect=statuses):
                with self.assertRaises(RuntimeError):
                    screen.verify_auth({}, 'fixture')
        with patch.object(screen, 'auth_status', side_effect=[401, 200]) as status:
            screen.verify_auth({}, 'fixture')
            self.assertEqual(status.call_args_list[0].args, ({},))
            self.assertEqual(status.call_args_list[1].args, ({}, 'fixture'))

    def test_version_bounds(self):
        for version, accepted in [('11.54', False), ('11.55', True), ('11.99', True), ('12.0', False)]:
            with patch.object(screen.importlib.metadata, 'version', return_value=version):
                self.assertEqual(screen.version_ok(), accepted)

    def test_worker_security_arguments(self):
        import types
        import sys
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            app = Mock()
            module = types.ModuleType('pymobiledevice3.__main__')
            module.app = app
            def preflight():
                self.assertIn('pid', __import__('json').loads((state / 'process.json').read_text()))
                return 'fixture-secret'
            with patch.object(screen, 'STATE', state), patch.object(screen, 'password', side_effect=preflight), patch.object(screen, 'tailnet_ip', return_value='192.0.2.1'), patch.object(screen, 'ensure_version'), patch.object(screen.socket, 'socket') as sock, patch.object(screen, 'run', return_value='true'), patch.object(screen.os, 'dup2'), patch.object(screen.signal, 'signal'), patch.object(screen.threading.Thread, 'start'), patch.dict(sys.modules, {'pymobiledevice3.__main__': module}), patch.dict(os.environ, {}, clear=True):
                screen.worker(types.SimpleNamespace(port=8080, udid='fixture-device'))
                kwargs = app.call_args.kwargs
                argv = kwargs['args']
                self.assertEqual(argv[argv.index('--bind') + 1], '192.0.2.1')
                self.assertIn('--https', argv)
                self.assertNotIn('fixture-secret', repr(argv))
                self.assertNotIn('fixture-secret', repr(dict(os.environ)))
                self.assertEqual(kwargs['default_map'][argv[0]]['core-device']['display']['serve-web']['password'], 'fixture-secret')
                sock.return_value.__enter__.return_value.setsockopt.assert_called_once_with(screen.socket.SOL_SOCKET, screen.socket.SO_REUSEADDR, 1)

    def test_starting_state_is_not_ready(self):
        self.assertFalse(screen.ready({'pid': 1, 'starttime': 'fixture'}))

class InstallEntryTests(unittest.TestCase):
    def test_install_is_explicit_and_creates_disabled_entries(self):
        import sys
        with tempfile.TemporaryDirectory() as directory, patch.object(Path, 'home', return_value=Path(directory)), patch.object(sys, 'argv', ['ipad-screen', 'install']):
            screen.main()
            home = Path(directory)
            self.assertTrue((home / '.local/bin/ipad-screen').is_symlink())
            self.assertTrue((home / '.local/share/applications/omarchy-ipad-screen.desktop').exists())
            self.assertTrue((home / '.config/systemd/user/ipad-screen@.service').exists())
            self.assertFalse((home / '.config/systemd/user/default.target.wants').exists())
        installer = (screen.SELF.parent.parent / 'install-toolchain.sh').read_text()
        self.assertNotIn('"$REPO_DIR/tools/ipad-screen.py" install', installer)

    def test_menu_defaults_to_status(self):
        import sys
        with patch.object(sys, 'argv', ['ipad-screen', 'menu']), patch('builtins.input', return_value=''), patch.object(screen.subprocess, 'run') as run:
            screen.main()
            self.assertEqual(run.call_args.args[0][-1], 'status')

    def test_shell_forwards_arguments_to_selected_interpreter(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            interpreter = Path(directory) / 'python'
            interpreter.write_text('#!/bin/sh\n[ "$2" = status ] && [ "$3" = --port ] && [ "$4" = 8090 ]\n')
            interpreter.chmod(0o700)
            result = subprocess.run(['bash', str(screen.SELF.with_suffix('.sh')), 'status', '--port', '8090'],
                                    env={**os.environ, 'IPAD_SCREEN_PYTHON': str(interpreter)})
            self.assertEqual(result.returncode, 0)

class UpgradeRegressionTests(unittest.TestCase):
    def test_upgrade_uses_bounded_requirement(self):
        with patch.object(screen, 'version_ok', side_effect=[False, True]), patch.object(screen.sys, 'prefix', str(Path.home() / 'fixture-venv')), patch.object(screen.subprocess, 'run') as run:
            screen.ensure_version(True)
            self.assertEqual(run.call_args.args[0][-1], 'pymobiledevice3>=11.55,<12')

    def test_auth_guard_terminates_on_failed_check(self):
        with patch.object(screen, 'ready', return_value=True), patch.object(screen, 'verify_auth', side_effect=RuntimeError('failed')), patch.object(screen.os, '_exit') as terminate:
            screen.auth_guard({}, 'fixture')
            terminate.assert_called_once_with(1)

class AuthRetryTests(unittest.TestCase):
    def test_transient_network_failure_retries(self):
        with patch.object(screen, 'auth_status', side_effect=[None, None, 401, 200]), patch.object(screen.time, 'sleep') as sleep:
            screen.verify_auth({}, 'fixture')
            sleep.assert_called_once_with(0.25)

    def test_network_failure_is_bounded(self):
        with patch.object(screen, 'auth_status', return_value=None) as status, patch.object(screen.time, 'sleep'):
            with self.assertRaises(RuntimeError):
                screen.verify_auth({}, 'fixture')
            self.assertEqual(status.call_count, 6)

    def test_http_network_errors_are_failure(self):
        with patch.object(screen.http.client, 'HTTPSConnection') as connection:
            connection.return_value.request.side_effect = ConnectionRefusedError()
            self.assertIsNone(screen.auth_status({'bind': '192.0.2.1', 'port': 8080}))
            connection.return_value.close.assert_called_once()
