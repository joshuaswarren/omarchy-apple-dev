#!/usr/bin/env bash
# Run an xtool project on a USB-connected iPhone from Omarchy Linux.
# Run this from inside your xtool project directory (the one with xtool.yml).
# First run ever: do `xtool auth` once beforehand (interactive Apple ID sign-in).
set -euo pipefail
export PATH="/usr/lib/swift/bin:$PATH"

XT="$HOME/.local/bin/xtool"
PMD3="$HOME/pymobile3-venv/bin/pymobiledevice3"

echo "== 1. Device visible over USB? =="
# usbmuxd is started by udev when a device is plugged in. Nothing to enable.
lsusb | grep -i apple || echo "WARNING: no Apple USB device found by lsusb."

echo "== 2. Trust and pair =="
# The phone shows a 'Trust This Computer' prompt on first connect. Accept it.
$PMD3 lockdown info >/dev/null 2>&1 \
  && echo "Lockdown reachable, pairing OK." \
  || { echo "Pairing needed: run '$PMD3 lockdown pair' and accept the prompt on the phone."; }

echo "== 3. List devices via xtool =="
$XT devices

echo "== 4. Build, sign, install, launch =="
# xtool dev run does all four. Signing uses your Apple ID (free tier works);
# the first deploy creates a free provisioning profile for your device.
$XT dev run

echo "== 5. LLDB attach =="
# The Swift toolchain lldb has the remote-ios platform. Attach workflow,
# from an interactive lldb session (untested without hardware on the first
# run; adjust as needed):
#   lldb
#   (lldb) platform select remote-ios
#   (lldb) platform connect <lockdown service or connect:// URL printed by xtool>
#   (lldb) process attach --name HelloOmarchy
#   (lldb) b ContentView.swift:12
#   (lldb) c
# pymobiledevice3 can also reach the developer services:
#   $PMD3 developer dvt lldb     # interactive DVT LLDB session (iOS 16 and below)
#   $PMD3 remote tunneld         # RemoteXPC tunnel needed on iOS 17+
