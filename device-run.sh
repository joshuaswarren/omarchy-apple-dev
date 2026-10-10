#!/usr/bin/env bash
# Run an xtool project on an iPhone from Omarchy Linux.
# Run this from inside your xtool project directory (the one with xtool.yml).
# First run ever: do `xtool auth` once beforehand (interactive Apple ID sign-in).
#
# Modes:
#   ./device-run.sh [--lldb|--attach [--sudo]]      USB (default; the proven path). --lldb then
#       starts LLDB on the app over pymobiledevice3's in-process userspace tunnel
#       (no root, no tunneld; pymobiledevice3 >= 11.26; FINDINGS.md 67). --sudo
#       restores the old path: a kernel tunnel from `sudo lockdown start-tunnel`
#       and `debugserver lldb` (FINDINGS.md 56), e.g. when mount-personalized
#       refuses to run unprivileged.
#       --attach implies --lldb but does not build, stop or reinstall the app: it debugs
#       the app already on the device (attaching to it if running, else launching it
#       suspended). It still needs xtool/<App>.app locally for symbols, and works with
#       and without --sudo.
#       LLDB_CMDS: LLDB commands to run after the attach, one per line. Without
#       --sudo they run in LLDB's synchronous mode, so `continue` returns at the
#       next stop; with --sudo they are typed into an async session.
#       LLDB_LOAD_LEVEL (no --sudo only): minimal (default) reads only section
#       headers of images missing from the sysroot, a ~30 s attach whose system
#       frames show module names only; complete gives full symbols in minutes.
#       LLDB_PYTHONHOME: a CPython of the version lldb links, when the system has none.
#   ./device-run.sh --network [--udid U]   WiFi, phone on the SAME network.
#       TESTED EXHAUSTIVELY 2026-09-16 on iOS 26.6.2: BLOCKED for hosts the
#       phone has no RemotePairing tunnel with. iOS gives every host its own
#       encrypted tunnel (`<uuid>._rp-tunnel._tcp`, ephemeral port), accepts
#       nobody else, and offers no device-side pairing screen to add a host
#       (that flow is iOS 27+). A Mac that once enabled "Connect via Network"
#       keeps a working wireless tunnel; a Linux host cannot get one today.
#       Full evidence in FINDINGS.md 17. Use USB, or the tunneld bridge below
#       through a Mac that holds the tunnel.
#   ./device-run.sh --rsd HOST PORT PKG    install+launch an already-signed
#       .app/.ipa against an explicit RemoteServiceDiscovery address. Works
#       against tunnels you DO hold: the RSD endpoint printed by
#       `sudo pymobiledevice3 lockdown start-tunnel` (USB) or a tunneld
#       instance. Addressing the phone's WiFi interfaces directly does not
#       work on iOS 26 (per-host tunnel gating, FINDINGS.md 17).
#       PKG must be signed with a real certificate: xtool's free-provisioning
#       signing only happens inside `xtool dev run`.
#
#   ./device-run.sh --over-tailnet HOST PKG   install+launch over Tailscale with no cable and
#       no Mac, iOS 27: HOST is the phone's tailnet address (100.x). One-time setup over USB:
#       `tools/tailnet-tunnel.py pair`. tailnet-tunnel.py opens the RemotePairing tunnel (the
#       phone advertises it on port 49152 and accepts it from any routed address; lockdownd
#       does not, and mDNS does not cross the tailnet). Needs sudo for the TUN device and a
#       signed PKG. How-to, limits and receipts: docs/OVER-TAILNET.md.
#
# Without a tailnet pairing record, a phone reachable only via Tailscale can still be reached
# through pymobiledevice3's tunneld WebSocket bridge on a machine that sees the phone (USB or
# same LAN):
#     sudo pymobiledevice3 remote tunneld        # prints its WS port
# then, from the remote host:
#     pymobiledevice3 apps install PKG --tunnel UDID@BRIDGE_HOST:WS_PORT
#     pymobiledevice3 developer core-device launch-application BID "" \
#         --tunnel UDID@BRIDGE_HOST:WS_PORT
set -euo pipefail
# The toolchain's own bin dir (lldb) first: /usr/lib/swift/bin on swift-bin
# 6.3, /usr/lib/swift/usr/bin on 6.4, elsewhere under mise.
PATH="$(dirname "$(readlink -f "$(command -v swift)")"):$PATH"
export PATH

XT="$HOME/.local/bin/xtool"
PMD3="$HOME/pymobile3-venv/bin/pymobiledevice3"

MODE=usb; UDID=; RSD_HOST=; RSD_PORT=; PKG=; LLDB=0; SUDO=0; ATTACH=0; TAILNET_HOST=
while [ $# -gt 0 ]; do
  case "$1" in
    --network) MODE=network ;;
    --lldb) LLDB=1 ;;
    --sudo) SUDO=1 ;;
    --attach) LLDB=1; ATTACH=1 ;;
    -u|--udid) UDID="${2:?--udid needs a value}"; shift ;;
    --rsd) MODE=rsd
      RSD_HOST="${2:?usage: --rsd HOST PORT PACKAGE}"
      RSD_PORT="${3:?usage: --rsd HOST PORT PACKAGE}"
      PKG="${4:?usage: --rsd HOST PORT PACKAGE}"
      shift 3 ;;
    --over-tailnet) MODE=tailnet
      TAILNET_HOST="${2:?usage: --over-tailnet PHONE_TAILNET_IP PACKAGE}"
      PKG="${3:?usage: --over-tailnet PHONE_TAILNET_IP PACKAGE}"
      shift 2 ;;
    *) echo "Unknown argument: $1 (modes: [--lldb|--attach [--sudo]] [--network] [--rsd HOST PORT PKG] [--over-tailnet HOST PKG])" >&2; exit 2 ;;
  esac
  shift
done

if [ "$SUDO" = 1 ] && [ "$LLDB" = 0 ]; then
  echo "--sudo only applies to --lldb" >&2; exit 2
fi

UDID_ARGS=()
if [ -n "$UDID" ]; then
  UDID_ARGS=(--udid "$UDID")
  # pymobiledevice3 subcommands that take no --udid (debugserver ...) read it from here.
  export PYMOBILEDEVICE3_UDID="$UDID"
fi

# Xcode 27.0's personalized Developer Disk Image, pinned by checksum. DDI_DIR overrides it, e.g. a
# copy of a Mac's /Library/Developer/DeveloperDiskImages/iOS_DDI.
DDI_URL=https://raw.githubusercontent.com/DeveloperDiskImages/DeveloperDiskImages/136b031cf581985c0663847915fd404d6fec2d5f/PersonalizedImages/iOS_DDI
DDI_FILES="05beb4f7a054ea1d53f49b04aaf0a210814e4cfa7d2ba9790b03b01c48ea8a6e Restore/BuildManifest.plist
c7cbaf4f8a94d4b4c1fe9aad21b7c74a1848cfd0139c3030a4082b8b0f6af9b3 Restore/022-20190-411.dmg
04dd84b0affafedf86c7ada177a5c2289a1ad197caf7cfded9ccf1dc0a310eb0 Restore/Firmware/022-20190-411.dmg.trustcache"

# The --lldb forwarder (userspace path): wait for lldb's connection to close, then SIGINT,
# never SIGKILL (killing a pymobiledevice3 client mid-request can crash usbmuxd).
FWD=; FWDLOG=
stop_forwarder() {
  local rc=$? i
  if [ -n "$FWD" ] && kill -0 "$FWD" 2>/dev/null; then
    if grep -q "connection established" "$FWDLOG" 2>/dev/null; then
      for i in $(seq 50); do grep -q "was closed" "$FWDLOG" && break; sleep 0.1; done
    fi
    kill -INT "$FWD" 2>/dev/null || true
    for i in $(seq 50); do kill -0 "$FWD" 2>/dev/null || break; sleep 0.1; done
    if kill -0 "$FWD" 2>/dev/null; then
      echo "WARNING: debugserver forwarder $FWD ignored SIGINT; sending SIGTERM" >&2
      kill -TERM "$FWD" 2>/dev/null || true
    fi
  fi
  # Its exit status (130 after SIGINT) must not replace ours.
  if [ -n "$FWD" ]; then wait "$FWD" 2>/dev/null || true; fi
  rm -f "$FWDLOG"
  exit "$rc"
}

# xtool may prefix the bundle id (XTL-<team>.<id>); print the installed one, or nothing.
installed_bid() {
  "$PMD3" apps list "${UDID_ARGS[@]}" 2>/dev/null | python3 -c '
import json, sys
b = sys.argv[1]
print(next((k for k in json.load(sys.stdin) if k == b or k.endswith("." + b)), ""))' "$1"
}

# Mount the DDI, open an RSD tunnel, give LLDB the phone's Swift runtime on disk, stop the app,
# install the build, attach to the app.
lldb_session() {
  local bid ddi info sym log host port wrap rsd
  ddi=${DDI_DIR:-$HOME/.cache/omarchy-apple-dev/iOS_DDI}
  if [ -z "${DDI_DIR:-}" ]; then
    while read -r sha f; do
      if ! echo "$sha  $ddi/$f" | sha256sum -c --status 2>/dev/null; then
        mkdir -p "$(dirname "$ddi/$f")"
        curl -fsSL "$DDI_URL/$f" -o "$ddi/$f"
        echo "$sha  $ddi/$f" | sha256sum -c --quiet
      fi
    done <<<"$DDI_FILES"
  fi
  info=$("$PMD3" lockdown info "${UDID_ARGS[@]}")
  # Userspace tunnel by default: no root. --sudo uses the kernel tunnel below instead.
  local us=(--userspace) pre=()
  if [ "$SUDO" = 1 ]; then us=(); pre=(sudo); fi
  if ! "${pre[@]}" "$PMD3" mounter list "${UDID_ARGS[@]}" "${us[@]}" 2>/dev/null | grep -qi personalized; then
    # The image and trust cache of a build identity for this phone's chip.
    read -r dmg tc < <(python3 -c '
import json, plistlib, sys
d = json.loads(sys.argv[2])
m = plistlib.load(open(sys.argv[1], "rb"))
for b in m["BuildIdentities"]:
    if "PersonalizedDMG" in b["Manifest"] and int(b["ApChipID"], 16) == d["ChipID"]:
        print(b["Manifest"]["PersonalizedDMG"]["Info"]["Path"], b["Manifest"]["LoadableTrustCache"]["Info"]["Path"])
        break' "$ddi/Restore/BuildManifest.plist" "$info")
    "${pre[@]}" "$PMD3" mounter mount-personalized "${UDID_ARGS[@]}" "${us[@]}" \
      "$ddi/Restore/$dmg" "$ddi/Restore/$tc" "$ddi/Restore/BuildManifest.plist" \
      || { echo "mount-personalized failed$([ "$SUDO" = 1 ] || echo '; retry with --sudo')" >&2; exit 1; }
  fi
  # How the remaining commands reach the device: the in-process userspace tunnel,
  # or an RSD address from a root-owned kernel tunnel (--sudo).
  rsd=("${us[@]}")
  if [ "$SUDO" = 1 ]; then
    log=$(mktemp)
    sudo "$PMD3" lockdown start-tunnel "${UDID_ARGS[@]}" >"$log" 2>&1 &
    trap 'sudo pkill -f "lockdown start-tunne[l]"' EXIT
    for _ in $(seq 30); do grep -q "RSD Port" "$log" && break; sleep 1; done
    host=$(grep -o "RSD Address: [^ ]*" "$log" | awk '{print $3}')
    port=$(grep -o "RSD Port: [0-9]*" "$log" | awk '{print $3}')
    [ -n "$port" ] || { cat "$log"; exit 1; }
    rsd=(--rsd "$host" "$port")
  fi
  # Linux LLDB reads the Swift runtime from process memory unless it has the dylibs of the
  # phone's exact iOS build on disk, and then misreads String (FINDINGS.md 56).
  sym="$HOME/.cache/omarchy-apple-dev/DeviceSupport/$(python3 -c '
import json, sys
d = json.loads(sys.argv[1])
print(d["ProductVersion"] + " (" + d["BuildVersion"] + ")")' "$info")"
  if [ ! -f "$sym/Symbols/usr/lib/swift/libswiftCore.dylib" ]; then
    echo "Copying the shared cache from the iPhone (once per iOS build, a few GB)"
    "$PMD3" developer fetch-symbols download "$sym/dsc" "${rsd[@]}"
    dsc=$(find "$sym/dsc" -name dyld_shared_cache_arm64e | head -n1)
    "$HOME/.local/bin/ipsw" dyld info "$dsc" --dylibs 2>/dev/null | grep -o '/[^ ]*$' |
      grep -E '^/usr/lib/(swift/|libobjc)' | while read -r p; do
        mkdir -p "$sym/Symbols$(dirname "$p")"
        "$HOME/.local/bin/ipsw" dyld extract "$dsc" "$(basename "$p")" --slide -o "$sym/Symbols$(dirname "$p")" >/dev/null
      done
  fi
  # Stop the running app (needs the DDI), then install over it. --attach leaves it alone.
  bid=$(installed_bid "$(grep -E '^bundleID:' xtool.yml | awk '{print $2}')")
  if [ "$ATTACH" != 1 ]; then
    if [ -n "$bid" ]; then
      "$PMD3" developer dvt pkill --bundle "$bid" "${rsd[@]}" >/dev/null 2>&1 || true
    fi
    $XT install "${UDID_ARGS[@]}" "$(ls -d xtool/*.app | head -n1)"
  fi
  bid=$(installed_bid "$(grep -E '^bundleID:' xtool.yml | awk '{print $2}')")
  [ -n "$bid" ] || { echo "app not found on the device after install" >&2; exit 1; }
  # LLDB_CMDS: LLDB commands to run after the attach, one per line (for scripted sessions).
  local cmds=() line
  while IFS= read -r line; do [ -z "$line" ] || cmds+=("$line"); done <<<"${LLDB_CMDS:-}"
  if [ "$SUDO" = 1 ]; then
    # pymobiledevice3 sends its own "platform select remote-ios"; add the sysroot to it.
    # LLDB_PYTHONHOME: a CPython of the version lldb links (3.12 for Swift 6.4), when the system
    # has none. It goes to lldb only; pymobiledevice3 and python3 here use their own Python.
    wrap=$(mktemp)
    {
      echo '#!/bin/bash'
      if [ -n "${LLDB_PYTHONHOME:-}" ]; then
        printf 'export PYTHONHOME=%q LD_LIBRARY_PATH=%q\n' "$LLDB_PYTHONHOME" "$LLDB_PYTHONHOME/lib"
      fi
      printf 'exec lldb "$@" < <(sed -u "s|^platform select remote-ios\\$|platform select remote-ios --sysroot \\"%s\\"|")\n' "$sym"
    } >"$wrap"
    chmod +x "$wrap"
    local c=()
    for line in "${cmds[@]}"; do c+=(-c "$line"); done
    sudo env PATH="$PATH" "$PMD3" developer debugserver lldb "$bid" "${rsd[@]}" \
      --lldb-command "$wrap" "${c[@]}"
    rm -f "$wrap" "$log"
    return
  fi
  # Userspace tunnel: `debugserver lldb` refuses it (its lldb could not reach the in-process
  # tunnel address), so forward debugserver to a localhost port and drive lldb ourselves.
  # The same steps `debugserver lldb` sends, with two changes:
  #  - `process connect` runs async. Synchronous, lldb waits for a stop from a debugserver
  #    that has no process yet, forever (Platform::DoConnectProcess).
  #  - memory-module-load-level minimal: every image not in the sysroot is otherwise parsed
  #    from process memory in 512-byte reads, minutes over the tunnel. System frames show
  #    only module names; the app (from disk) and the sysroot's Swift runtime keep symbols.
  #    LLDB_LOAD_LEVEL=complete restores full symbols.
  local remote pid app exe launched=0 rc=0
  remote=$("$PMD3" apps list "${UDID_ARGS[@]}" 2>/dev/null | python3 -c '
import json, sys
print(json.load(sys.stdin)[sys.argv[1]]["Path"])' "$bid")
  app=$(ls -d xtool/*.app | head -n1)
  exe=$(python3 -c 'import plistlib, sys; print(plistlib.load(open(sys.argv[1], "rb"))["CFBundleExecutable"])' \
    "$app/Info.plist")
  # The forwarder first, so a suspended launch is attached quickly (launch watchdog).
  port=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
  FWDLOG=$(mktemp)
  trap stop_forwarder EXIT
  # setsid: its own session, so Ctrl-C at the lldb prompt (lldb's foreground group) does not
  # reach it. A background job is not a group leader, so setsid execs without forking and $!
  # stays its pid. env --default-signal=INT: a background job of a non-interactive shell
  # starts with SIGINT ignored, which would leave stop_forwarder only SIGTERM.
  setsid env --default-signal=INT "$PMD3" developer debugserver start-server --local-port "$port" \
    "${us[@]}" >"$FWDLOG" 2>&1 &
  FWD=$!
  for _ in $(seq 60); do
    kill -0 "$FWD" 2>/dev/null || break
    grep -q "Started port forwarding" "$FWDLOG" && ss -Hltn "sport = :$port" | grep -q . && break
    sleep 1
  done
  if ! ss -Hltn "sport = :$port" | grep -q .; then
    echo "debugserver forwarder did not start:" >&2; cat "$FWDLOG" >&2; exit 1
  fi
  pid=$("$PMD3" developer dvt process-id-for-bundle-id "$bid" "${us[@]}" | tail -n1)
  if ! [ "${pid:-0}" -gt 0 ] 2>/dev/null; then
    # Not running (stopped before the install): launch it suspended, so startup breakpoints hit.
    pid=$("$PMD3" developer dvt launch "$bid" --suspended --no-kill-existing "${us[@]}" |
      sed -n 's/^Process launched with pid \([0-9][0-9]*\)$/\1/p') || true
    [ -n "$pid" ] || { echo "dvt launch --suspended printed no pid" >&2; exit 1; }
    launched=1
  fi
  echo "Attaching to pid $pid"
  # The same steps `debugserver lldb` sends, with two changes (FINDINGS.md 67):
  #  - `process connect` runs async. Synchronous, lldb waits for a stop from a debugserver
  #    that has no process yet, forever (Platform::DoConnectProcess). The next line waits for
  #    the connection and, if there is none, stops lldb with exit 1.
  #  - memory-module-load-level minimal (LLDB_LOAD_LEVEL, see the header).
  local lcmds=(
    -o "settings set target.memory-module-load-level ${LLDB_LOAD_LEVEL:-minimal}"
    -o "platform select remote-ios --sysroot \"$sym\""
    -o "target create \"$PWD/$app/$exe\""
    -o "script lldb.target.module[0].SetPlatformFileSpec(lldb.SBFileSpec(\"$remote/$exe\"))"
    -o "script lldb.debugger.SetAsync(True)"
    -o "process connect connect://127.0.0.1:$port"
    -o "script import time; ok = any(lldb.target.GetProcess().IsValid() or time.sleep(0.1) for _ in range(100)); ok or lldb.debugger.HandleCommand('quit 1'); assert ok, 'process connect: no debugserver connection'"
    -o "script lldb.debugger.SetAsync(False)"
    -o "process attach --pid $pid"
  )
  for line in "${cmds[@]}"; do lcmds+=(-o "$line"); done
  (
    if [ -n "${LLDB_PYTHONHOME:-}" ]; then
      export PYTHONHOME="$LLDB_PYTHONHOME" LD_LIBRARY_PATH="$LLDB_PYTHONHOME/lib"
    fi
    exec lldb "${lcmds[@]}"
  ) || rc=$?
  if [ "$rc" != 0 ] && [ "$launched" = 1 ]; then
    echo "lldb exited with $rc; pid $pid may be left suspended (relaunch the app)" >&2
  fi
  return "$rc"
}

rsd_run() {
  echo "== Install/launch via RSD $RSD_HOST:$RSD_PORT =="
  $PMD3 apps install "$PKG" --rsd "$RSD_HOST" "$RSD_PORT"
  BID=$(grep -E '^bundleID:' xtool.yml | awk '{print $2}')
  if [ -z "$BID" ]; then echo "No bundle_id in xtool.yml; launch it by hand:"; else
    $PMD3 developer core-device launch-application "$BID" "" --rsd "$RSD_HOST" "$RSD_PORT"
  fi
}

case "$MODE" in
usb)
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
  # Signing uses your Apple ID (free tier works); the first deploy creates a free
  # provisioning profile for your device.
  if [ "$ATTACH" = 1 ]; then
    # --attach: the app is already installed (for example a debug build copied from another host);
    # only the LLDB session runs. The bundle id comes from xtool.yml.
    echo "== 5. LLDB =="
    lldb_session
  elif [ "$LLDB" = 0 ]; then
    $XT dev run "${UDID_ARGS[@]}"
  else
    # lldb_session stops the app, installs, then launches it suspended and attaches, so
    # breakpoints in startup code hit.
    $XT dev build
    echo "== 5. LLDB =="
    lldb_session
  fi
  ;;
network)
  echo "== WiFi deploy (phone on the same network) -- UNVERIFIED =="
  echo "Expects: paired over USB once, Developer Mode on, same LAN segment."
  $XT devices --network
  $XT dev run --network "${UDID_ARGS[@]}"
  ;;
rsd)
  rsd_run
  ;;
tailnet)
  # The tunnel lives as long as tailnet-tunnel.py (sudo relays the signal to it): stopped when this script exits.
  TT=$(mktemp)
  "$(dirname "$PMD3")/python" "$(dirname "$0")/tools/tailnet-tunnel.py" "$TAILNET_HOST" "${UDID_ARGS[@]}" >"$TT" 2>&1 &
  TTPID=$!
  trap 'kill "$TTPID" 2>/dev/null || true; rm -f "$TT"' EXIT
  for _ in $(seq 30); do grep -q '^RSD ' "$TT" && break; sleep 1; done
  read -r _ RSD_HOST RSD_PORT < <(grep '^RSD ' "$TT") || { cat "$TT" >&2; exit 1; }
  echo "== Tunnel to $TAILNET_HOST up: RSD $RSD_HOST $RSD_PORT =="
  rsd_run
  ;;
esac
