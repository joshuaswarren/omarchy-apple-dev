#!/usr/bin/env python3
"""Open an iOS 27 RemotePairing tunnel to a phone over Tailscale (or any routed IP).

  tailnet-tunnel.py pair                    one time, phone on USB: write a host-independent pairing record
  tailnet-tunnel.py HOST [--port P] [--hold SECONDS] [--udid U]
                                            tunnel to HOST (the phone's 100.x address); prints one line
                                            "RSD <address> <port>" for `--rsd` options and holds the tunnel

The tunnel needs a TUN device, so the tunnel command runs as root (it re-executes itself with sudo).
Run it with pymobiledevice3's Python (the venv that has `pymobiledevice3` installed).
"""
import argparse
import asyncio
import os
import plistlib
import sys
from pathlib import Path

PORT_SCAN = range(49152, 49168)
RECORD_DIR = Path.home() / ".local/share/pymobiledevice3"


def records():
    return sorted(RECORD_DIR.glob("remote_*.plist"))


def pick_udid(udid):
    if udid:
        return udid
    found = [p.stem.removeprefix("remote_") for p in records()]
    if len(found) != 1:
        sys.exit(f"need --udid: {len(found)} RemotePairing records in {RECORD_DIR}")
    return found[0]


def pair():
    """`lockdown remotepairing --pair` over USB, then pin the host identifier into the record.

    pymobiledevice3 derives the host identifier from this machine's hostname and the phone ties the
    pairing key to it. Without the pinned value the record works only on the machine that made it.
    """
    import subprocess

    from pymobiledevice3.pair_records import generate_host_id

    exe = Path(sys.executable).with_name("pymobiledevice3")
    subprocess.run([str(exe), "lockdown", "remotepairing", "--pair"], check=True, stdout=subprocess.DEVNULL)
    for p in records():
        d = plistlib.loads(p.read_bytes())
        d.setdefault("host_identifier", generate_host_id())
        p.write_bytes(plistlib.dumps(d))
        p.chmod(0o600)
        print(f"pairing record ready: {p} (copy this file to any host that should reach the phone)")


async def connect(udid, host, port):
    from pymobiledevice3.remote.tunnel_service import RemotePairingTunnelService

    svc = RemotePairingTunnelService(udid, host, port)
    await asyncio.wait_for(svc.connect(autopair=False), timeout=20)
    return svc


async def find_service(udid, host, port):
    last = None
    for p in [port] if port else PORT_SCAN:
        try:
            return await connect(udid, host, p)
        except (OSError, TimeoutError, asyncio.TimeoutError) as e:
            last = e
    sys.exit(f"no RemotePairing service answered on {host}: {last!r}")


async def tunnel(args):
    from pymobiledevice3.remote.common import TunnelProtocol
    from pymobiledevice3.remote.tunnel_service import start_tunnel_over_remotepairing

    udid = pick_udid(args.udid)
    svc = await find_service(udid, args.host, args.port)
    # TCP needs TLS-PSK ciphers (Python 3.13+ with sslpsk); older Pythons use QUIC, as pymobiledevice3 does.
    proto = TunnelProtocol.TCP if sys.version_info >= (3, 13) else TunnelProtocol.QUIC
    async with start_tunnel_over_remotepairing(svc, protocol=proto) as t:
        print(f"RSD {t.address} {t.port}", flush=True)
        await asyncio.sleep(args.hold)


def main():
    if sys.argv[1:2] == ["pair"]:
        return pair()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("host")
    ap.add_argument("--port", type=int, help="RemotePairing port (default: scan 49152-49167)")
    ap.add_argument("--hold", type=int, default=3600, help="seconds to keep the tunnel open")
    ap.add_argument("--udid")
    args = ap.parse_args()
    if os.geteuid() != 0:
        os.execvp("sudo", ["sudo", "-n", "env", f"HOME={Path.home()}", sys.executable, *sys.argv])
    asyncio.run(tunnel(args))


if __name__ == "__main__":
    main()
