#!/usr/bin/env python3
"""Tailnet-only, password-protected iPad viewer lifecycle (Linux)."""
import argparse
import base64
import http.client
import ssl
import threading
import fcntl
import importlib.metadata
import ipaddress
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import stat
import subprocess
import sys
import time

CONFIG = Path.home() / '.config/omarchy-apple-dev/ipad-screen'
STATE = Path.home() / '.local/state/omarchy-apple-dev/ipad-screen'
PASSWORD = CONFIG / 'password'
SELF = Path(__file__).resolve()


def private_dir(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise RuntimeError(f'{path} must be an owned directory with mode 0700')


def password():
    private_dir(CONFIG)
    try:
        fd = os.open(PASSWORD, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, 'w') as stream:
            stream.write(secrets.token_urlsafe(32) + '\n')
    fd = os.open(PASSWORD, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise RuntimeError('password must be an owned regular file with mode 0600')
        value = stream.read(4097).strip()
    if not value or len(value) > 4096 or '\n' in value or '\r' in value:
        raise RuntimeError('password file must contain one non-empty line (up to 4096 characters)')
    return value


def run(args, timeout=60):
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as child:
        try:
            out, _ = child.communicate(timeout=timeout)
            if child.returncode:
                raise RuntimeError(f'{Path(args[0]).name} check failed (exit {child.returncode}); check the selected tool and connection')
            return out
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=5)


def tailnet_ip():
    value = run(['tailscale', 'ip', '-4']).strip()
    address = ipaddress.IPv4Address(value)
    if address not in ipaddress.IPv4Network((0x64400000, 10)):
        raise RuntimeError('tailscale did not return a single Tailscale IPv4 address')
    return str(address)


def version_ok():
    from packaging.version import Version
    try:
        return Version(importlib.metadata.version('pymobiledevice3')) >= Version('11.55.0') and Version(importlib.metadata.version('pymobiledevice3')) < Version('12')
    except importlib.metadata.PackageNotFoundError:
        return False


def ensure_version(upgrade):
    if version_ok():
        return
    if not upgrade:
        raise RuntimeError('pymobiledevice3 >=11.55,<12 required; run start --upgrade to upgrade this venv')
    if sys.prefix == sys.base_prefix or not Path(sys.prefix).resolve().is_relative_to(Path.home().resolve()):
        raise RuntimeError('refusing upgrade outside a user-owned virtual environment')
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', 'pymobiledevice3>=11.55,<12'], check=True)
    if not version_ok():
        raise RuntimeError('pymobiledevice3 upgrade did not provide a supported version')


def identity(pid):
    # Linux starttime prevents a stale PID file from stopping an unrelated process.
    fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
    if fields[0] == 'Z':
        raise ProcessLookupError('viewer exited')
    return fields[19]


def current():
    try:
        data = json.loads((STATE / 'process.json').read_text())
        if identity(data['pid']) == data['starttime']:
            return data
    except (OSError, ValueError, KeyError, IndexError):
        pass
    return None


def ready(data):
    try:
        with socket.create_connection((data['bind'], data['port']), timeout=0.5):
            return True
    except (OSError, KeyError):
        return False


def auth_status(data, secret=None):
    connection = http.client.HTTPSConnection(data['bind'], data['port'], timeout=2,
                                            context=ssl._create_unverified_context())
    headers = {}
    if secret is not None:
        token = base64.b64encode(('viewer:' + secret).encode()).decode()
        headers['Authorization'] = 'Basic ' + token
    try:
        connection.request('GET', '/', headers=headers)
        return connection.getresponse().status
    except (OSError, http.client.HTTPException):
        return None
    finally:
        connection.close()


def verify_auth(data, secret):
    for attempt in range(3):
        anonymous = auth_status(data)
        authenticated = auth_status(data, secret)
        if anonymous == 401 and authenticated == 200:
            return
        # An actual HTTP mismatch is unsafe; retry only transport startup failures.
        if anonymous is not None and anonymous != 401:
            break
        if authenticated is not None and authenticated != 200:
            break
        if attempt < 2:
            time.sleep(0.25)
    raise RuntimeError('viewer authentication check failed')


def auth_guard(data, secret):
    try:
        for _ in range(400):
            if ready(data):
                verify_auth(data, secret)
                data['verified'] = True
                (STATE / 'process.json').write_text(json.dumps(data))
                return
            time.sleep(1)
    except (RuntimeError, OSError, http.client.HTTPException):
        pass
    # Immediate nonzero exit also releases the lifetime lock; never leave an open viewer.
    os._exit(1)


def worker(args):
    # Lifetime lock serializes starts, including concurrent start/run invocations.
    with open(STATE / 'lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('viewer is already starting/running')
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        data = dict(pid=os.getpid(), starttime=identity(os.getpid()))
        (STATE / 'process.json').write_text(json.dumps(data))
        secret = password()
        bind = tailnet_ip()
        ensure_version(False)
        # Fail before contacting the device if the port is already occupied.
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind((bind, args.port))
        data = dict(pid=os.getpid(), starttime=identity(os.getpid()), bind=bind, port=args.port)
        (STATE / 'process.json').write_text(json.dumps(data))
        try:
            os.environ['PYMOBILEDEVICE3_UDID'] = args.udid
            # Do not inherit a remote target or an alternate tunnel transport.
            for key in list(os.environ):
                if key.startswith('PYMOBILEDEVICE3_') and key != 'PYMOBILEDEVICE3_UDID':
                    del os.environ[key]
            pmd = [sys.executable, '-m', 'pymobiledevice3']
            print('Checking USB trust and Developer Mode', flush=True)
            if run(pmd + ['amfi', 'developer-mode-status', '--udid', args.udid]).strip() != 'true':
                raise RuntimeError('the person holding the iPad must enable Developer Mode on the iPad; no automatic reboot attempted')
            print('Ensuring DDI (rootless userspace tunnel)', flush=True)
            run(pmd + ['mounter', 'auto-mount', '--udid', args.udid, '--userspace'], timeout=300)
            print('Starting HTTPS viewer', flush=True)
            # Supply Click's default in memory: the password never enters argv or the environment.
            # Upstream output is discarded so even an upstream traceback cannot log credentials.
            from pymobiledevice3.__main__ import app
            threading.Thread(target=auth_guard, args=(data, secret), daemon=True).start()
            with open(os.devnull, 'w') as sink:
                os.dup2(sink.fileno(), 1)
                os.dup2(sink.fileno(), 2)
                app(args=['developer', 'core-device', 'display', 'serve-web', '--userspace',
                          '--bind', bind, '--http-port', str(args.port), '--https'],
                    default_map={'developer': {'core-device': {'display': {'serve-web': {'password': secret}}}}})
        finally:
            (STATE / 'process.json').unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['start', 'stop', 'status', 'run', 'install', 'menu'])
    parser.add_argument('--udid', default=os.getenv('IPAD_SCREEN_UDID'), help='USB device UDID (required for start/run)')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--upgrade', action='store_true', help='upgrade only the selected user venv if too old')
    args = parser.parse_args()
    os.umask(0o077)
    if args.command == 'install':
        binary = Path.home() / '.local/bin/ipad-screen'
        binary.parent.mkdir(parents=True, exist_ok=True)
        if binary.exists() and not binary.is_symlink():
            raise RuntimeError('refusing to replace an existing non-symlink ipad-screen')
        binary.unlink(missing_ok=True)
        binary.symlink_to(SELF.with_suffix('.sh'))
        applications = Path.home() / '.local/share/applications'
        applications.mkdir(parents=True, exist_ok=True)
        (applications / 'omarchy-ipad-screen.desktop').write_text(
            '[Desktop Entry]\nType=Application\nName=iPad screen (Tailscale)\n'
            f'Exec="{binary}" menu\nTerminal=true\nCategories=Development;\n')
        units = Path.home() / '.config/systemd/user'
        units.mkdir(parents=True, exist_ok=True)
        (units / 'ipad-screen@.service').write_text((SELF.parent / 'ipad-screen@.service').read_text())
        print('Installed ipad-screen command, application menu entry and disabled user unit template')
        return
    if args.command == 'menu':
        action = input('iPad screen: start / stop / status [status]: ').strip() or 'status'
        if action not in ('start', 'stop', 'status'):
            raise RuntimeError('unknown action')
        argv = [sys.executable, str(SELF), action]
        if action == 'start':
            udid = args.udid or input('USB device UDID: ').strip()
            argv += ['--udid', udid]
        subprocess.run(argv, check=True)
        input('Press Enter to close. Use the printed HTTPS URL in your browser. ')
        return
    private_dir(STATE)
    if args.command == 'stop':
        data = current()
        if data:
            os.kill(data['pid'], signal.SIGTERM)
            for _ in range(100):
                if not current():
                    print('ipad-screen: stopped')
                    return
                time.sleep(0.1)
            raise RuntimeError('viewer has not exited; no forced kill attempted')
        print('ipad-screen: stopped')
        return
    if args.command == 'status':
        data = current()
        print(f"ipad-screen: {'ready' if data.get('verified') and ready(data) else 'starting'} https://{data.get('bind', 'pending')}:{data.get('port', 'pending')}/" if data else 'ipad-screen: stopped')
        return
    if not args.udid:
        parser.error('--udid or IPAD_SCREEN_UDID is required; no implicit first-device selection')
    if not 1024 <= args.port <= 65535:
        parser.error('--port must be between 1024 and 65535')
    ensure_version(args.upgrade)
    if args.command == 'run':
        worker(args)
        return
    if current():
        raise RuntimeError('viewer is already starting/running; use status or stop')
    password()
    tailnet_ip()
    with open(STATE / 'viewer.log', 'w') as log:
        child = subprocess.Popen([sys.executable, str(SELF), 'run', '--udid', args.udid, '--port', str(args.port)],
                                 stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    for _ in range(400):
        if child.poll() is not None:
            raise RuntimeError('startup failed; check private viewer.log. If locked/untrusted, the person holding the iPad must unlock/tap Trust on the iPad, then retry')
        data = current()
        if data and data['pid'] == child.pid and data.get('verified'):
            print(f"ipad-screen: ready https://{data.get('bind', 'pending')}:{data.get('port', 'pending')}/ (password in {PASSWORD})")
            return
        time.sleep(1)
    os.kill(child.pid, signal.SIGTERM)
    raise RuntimeError('startup timed out; stopped viewer. the person holding the iPad may need to unlock/tap Trust on the iPad')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        # Never print command output, environment, or exception repr (may contain credentials).
        print(f'ipad-screen: {error}' if isinstance(error, RuntimeError) else 'ipad-screen: operation failed; check filesystem permissions and the selected command', file=sys.stderr)
        sys.exit(1)
