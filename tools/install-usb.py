#!/usr/bin/env python3
"""Install an .ipa on a USB-connected iOS 17+ device, no root, no Xcode, no macOS.

Why this exists: `pymobiledevice3 apps install --udid` is rejected by modern iOS (the
installation service moved behind CoreDevice), and `remote start-tunnel --connection-type usb`
finds nothing on Linux when the phone does not bring its USB NCM link up. The userspace tunnel
bridges both: it reaches the device's CoreDeviceProxy over plain usbmux and serves the install.

Requires pymobiledevice3 >= 11.38 (UserspaceRsdTunnel, python 3.13+ for TCP tunnels on iOS 18.2+).

The tunnel's RSD address lives only inside this process (its PyTCP stack is process-global),
so the tunnel and the install must share one process — that is what this script is.

usage: install-usb.py UDID IPA.ipa
"""
import asyncio
import sys
from pathlib import Path

from pymobiledevice3.remote.userspace_tunnel import UserspaceRsdTunnel
from pymobiledevice3.services.installation_proxy import InstallationProxyService


async def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    udid, ipa = sys.argv[1], Path(sys.argv[2])
    async with UserspaceRsdTunnel(serial=udid) as rsd:
        address, port = rsd.service.address
        print(f"tunnel up via [{address}]:{port}", flush=True)
        await InstallationProxyService(lockdown=rsd).install_from_local(ipa)
        print("INSTALL OK", flush=True)


asyncio.run(main())
