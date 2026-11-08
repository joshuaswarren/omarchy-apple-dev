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
#       --console [SECONDS] (default 20; --console=SECONDS also works) watches the app's own
#       output: after the install it launches the app with `developer dvt launch <bundle id>
#       --stream`, prints stdout and stderr for SECONDS, then reports
#       `running after N s: yes/no` (developer dvt proclist) and
#       `fatal text seen: yes/no` (the stream holds an `uncaught exception` or
#       `Terminating app` line), then stops the app (developer dvt pkill).
#       Exit code: 0 when the launch started, non-zero when it did not. A
#       fatal line in the stream is a report about the app, not an error of
#       this script. Ctrl-C during the stream stops the app and exits 130.
#       --symbolicate [DIR] (DIR also as --symbolicate=DIR; default
#       ./crash-<utc-timestamp>) pulls the phone's crash reports with
#       `crash pull DIR --rsd` after the launch step, then prints each pulled
#       .ips through tools/ips-symbolicate.py with the app binary and the
#       Mach-O files under the app's Frameworks directory. A report for
#       another app prints too. No report for this app: a note, exit 0.
#       Only a failed pull exits non-zero.
#
#   ./device-run.sh --over-tailnet HOST PKG   install+launch over Tailscale with no cable and
#       no Mac, iOS 27: HOST is the phone's tailnet address (100.x). One-time setup over USB:
#       `tools/tailnet-tunnel.py pair`. tailnet-tunnel.py opens the RemotePairing tunnel (the
#       phone advertises it on port 49152 and accepts it from any routed address; lockdownd
#       does not, and mDNS does not cross the tailnet). Needs sudo for the TUN device and a
#       signed PKG. --console [SECONDS] and --symbolicate [DIR] work here too;
#       see --rsd. How-to, limits and
#       receipts: docs/OVER-TAILNET.md.
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

# install-toolchain.sh puts these in ~/.local/bin and ~/pymobile3-venv. A
# toolchain from a package manager (for example Nix) has them on PATH instead.
XT="$HOME/.local/bin/xtool"
[ -x "$XT" ] || XT=$(command -v xtool || echo "$XT")
PMD3="$HOME/pymobile3-venv/bin/pymobiledevice3"
[ -x "$PMD3" ] || PMD3=$(command -v pymobiledevice3 || echo "$PMD3")
IPSW="$HOME/.local/bin/ipsw"
[ -x "$IPSW" ] || IPSW=$(command -v ipsw || echo "$IPSW")

MODE=usb; UDID=; RSD_HOST=; RSD_PORT=; PKG=; LLDB=0; SUDO=0; ATTACH=0; TAILNET_HOST=
CONSOLE=0; CONSOLE_SECS=20; SYMBOLICATE=0; SYM_DIR=
while [ $# -gt 0 ]; do
  case "$1" in
    --network) MODE=network ;;
    --lldb) LLDB=1 ;;
    --sudo) SUDO=1 ;;
    --attach) LLDB=1; ATTACH=1 ;;
    --console)
      CONSOLE=1
      # An all-digit value is the seconds; anything else is the next flag.
      case "${2:-}" in ''|*[!0-9]*) ;; *) CONSOLE_SECS=$2; shift ;; esac ;;
    --console=*) CONSOLE=1; CONSOLE_SECS="${1#--console=}" ;;
    --symbolicate)
      SYMBOLICATE=1
      # A following word that is not a flag is the pull directory.
      case "${2:-}" in ''|--*) ;; *) SYM_DIR=$2; shift ;; esac ;;
    --symbolicate=*) SYMBOLICATE=1; SYM_DIR="${1#--symbolicate=}" ;;
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
    *) echo "Unknown argument: $1 (modes: [--lldb|--attach [--sudo]] [--network] [--rsd HOST PORT PKG] [--over-tailnet HOST PKG], console: [--console [SECONDS]] or --console=SECONDS, symbolicate: [--symbolicate [DIR]] or --symbolicate=DIR)" >&2; exit 2 ;;
  esac
  shift
done

if [ "$CONSOLE" = 1 ]; then
  case "$CONSOLE_SECS" in ''|*[!0-9]*|0)
    echo "--console needs a number of seconds of 1 or more" >&2; exit 2 ;;
  esac
  if [ "$MODE" != rsd ] && [ "$MODE" != tailnet ]; then
    echo "--console works with --rsd or --over-tailnet; they hold the RSD address" >&2; exit 2
  fi
fi

if [ "$SYMBOLICATE" = 1 ]; then
  if [ "$MODE" != rsd ] && [ "$MODE" != tailnet ]; then
    echo "--symbolicate works with --rsd or --over-tailnet; they hold the RSD address" >&2; exit 2
  fi
fi

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
# Extra arguments are the connection: --rsd HOST PORT for rsd and tailnet mode.
installed_bid() {
  local b=$1; shift
  "$PMD3" apps list "${UDID_ARGS[@]}" "$@" 2>/dev/null | python3 -c '
import json, sys
b = sys.argv[1]
try:
    apps = json.load(sys.stdin)
except ValueError:
    sys.exit("apps list did not return JSON; check the --rsd or --udid arguments")
print(next((k for k in apps if k == b or k.endswith("." + b)), ""))' "$b"
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
    "$IPSW" dyld info "$dsc" --dylibs 2>/dev/null | grep -o '/[^ ]*$' |
      grep -E '^/usr/lib/(swift/|libobjc)' | while read -r p; do
        mkdir -p "$sym/Symbols$(dirname "$p")"
        "$IPSW" dyld extract "$dsc" "$(basename "$p")" --slide -o "$sym/Symbols$(dirname "$p")" >/dev/null
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

# --console: stream the app's own output after the install, then report and stop it. A fatal
# line in the stream is a report about the app, not an error of this script; a launch that
# never started is (exit non-zero).
console_run() {
  local bid=$1 ibid stream lrc rc pid run fatal
  # Our own app only: stream the app this run installed, not a same-named app already there.
  ibid=$(installed_bid "$bid" --rsd "$RSD_HOST" "$RSD_PORT")
  if [ -z "$ibid" ]; then
    echo "Refusing to stream: $bid is not the bundle id this run installed." >&2
    return 1
  fi
  stream=$(mktemp)
  echo "== Console stream of $ibid for ${CONSOLE_SECS} s =="
  # PYTHONUNBUFFERED: the pid line is a plain print() into the pipe; buffered, timeout's
  # SIGTERM ends the tool with no flush and the line never reaches the stream file.
  lrc=0
  # timeout cuts the stream at CONSOLE_SECS (status 124): the app streamed the whole window.
  PYTHONUNBUFFERED=1 timeout "$CONSOLE_SECS" "$PMD3" developer dvt launch "$ibid" --stream --rsd "$RSD_HOST" "$RSD_PORT" 2>&1 |
    tee "$stream" || lrc=$?
  rc=$lrc
  if [ "$rc" = 130 ]; then
    # Ctrl-C during the stream: stop the app, say so, pass the status through.
    timeout 30 "$PMD3" developer dvt pkill --bundle "$ibid" --rsd "$RSD_HOST" "$RSD_PORT" >/dev/null 2>&1 || true
    rm -f "$stream"
    echo "interrupted" >&2
    return 130
  fi
  if [ "$rc" = 124 ]; then rc=0; fi
  pid=$(sed -n 's/^Process launched with pid \([0-9][0-9]*\)$/\1/p' "$stream" | head -n1)
  if [ -z "$pid" ]; then
    # No pid line means the launch never started: a locked phone refuses launches, an
    # install-address mismatch refuses silently. Report it as a failed launch, not as
    # an app that ran and died.
    echo "launch did not start: no 'Process launched with pid' line within ${CONSOLE_SECS} s (phone locked or app refused?)" >&2
    echo "running after ${CONSOLE_SECS} s: unknown"
    echo "fatal text seen: unknown"
    if [ "$rc" = 0 ]; then rc=1; fi
  else
    run=no
    if timeout 30 "$PMD3" developer dvt proclist --rsd "$RSD_HOST" "$RSD_PORT" 2>/dev/null |
        python3 -c '
import json, sys
ps = json.load(sys.stdin)
print("yes" if int(sys.argv[1]) in [p.get("pid", 0) for p in ps] else "no")' "$pid" | grep -q yes; then
      run=yes
    fi
    if grep -Eq 'uncaught exception|Terminating app' "$stream"; then fatal=yes; else fatal=no; fi
    echo "running after ${CONSOLE_SECS} s: $run"
    echo "fatal text seen: $fatal"
  fi
  timeout 30 "$PMD3" developer dvt pkill --bundle "$ibid" --rsd "$RSD_HOST" "$RSD_PORT" >/dev/null 2>&1 || true
  rm -f "$stream"
  if [ "$lrc" != 0 ] && [ "$lrc" != 124 ]; then
    echo "launch failed: developer dvt launch exited with $lrc" >&2
  fi
  return "$rc"
}

# --symbolicate: after the launch step, pull the crash reports, then print
# each pulled .ips under its file name through tools/ips-symbolicate.py, with
# the app binary and the Mach-O files under the app's Frameworks directory as
# --binary. Only a failed pull is an error; a run with no report for this app
# says so and exits 0.
symbolicate_run() {
  local dir=${SYM_DIR:-} app_root tmpapp= exe fw name got=0
  local tool="$(dirname "$0")/tools/ips-symbolicate.py"
  local bins=() args=()
  if [ -z "$dir" ]; then dir="./crash-$(date -u +%Y%m%dT%H%M%SZ)"; fi
  # The package is an .app directory or a signed .ipa. An .ipa is unpacked to
  # a temp dir that every exit path below removes again.
  case "$PKG" in
    *.ipa)
      tmpapp=$(mktemp -d)
      if ! unzip -q "$PKG" -d "$tmpapp"; then
        rm -rf "$tmpapp"
        echo "cannot unpack $PKG" >&2; return 1
      fi
      app_root=$(printf '%s\n' "$tmpapp"/Payload/*.app | head -n1)
      ;;
    *) app_root=$PKG ;;
  esac
  cleanup() {
    if [ -n "$tmpapp" ]; then rm -rf "$tmpapp" || true; fi
  }
  exe=$(python3 -c 'import plistlib, sys; print(plistlib.load(open(sys.argv[1], "rb"))["CFBundleExecutable"])' \
    "$app_root/Info.plist") || { cleanup; echo "cannot read Info.plist of $app_root" >&2; return 1; }
  [ -f "$app_root/$exe" ] || { cleanup; echo "no executable $exe in $app_root" >&2; return 1; }
  bins=("$app_root/$exe")
  for fw in "$app_root"/Frameworks/*.framework "$app_root"/Frameworks/*.dylib; do
    [ -e "$fw" ] || continue
    if [ -d "$fw" ]; then fw="$fw/$(basename "$fw" .framework)"; fi
    [ -f "$fw" ] && bins+=("$fw")
  done
  mkdir -p "$dir"
  echo "== Pulling crash reports into $dir"
  if ! "$PMD3" crash pull "$dir" --rsd "$RSD_HOST" "$RSD_PORT"; then
    cleanup
    echo "crash pull failed" >&2
    return 1
  fi
  for fw in "${bins[@]}"; do args+=(--binary "$fw"); done
  for name in "$dir"/*.ips; do
    if [ ! -e "$name" ]; then echo "no .ips report in $dir"; break; fi
    echo "== Crash report: $(basename "$name")"
    python3 "$tool" "$name" "${args[@]}" \
      || echo "warning: could not symbolicate $(basename "$name")" >&2
    # Line 1 of a report is a JSON header; its app_name names the app.
    if head -n 1 "$name" | grep -q "\"app_name\": *\"$exe\""; then got=1; fi
  done
  cleanup
  if [ "$got" = 0 ]; then
    echo "no crash report matches app $exe in $dir"
  fi
  return 0
}

rsd_run() {
  echo "== Install/launch via RSD $RSD_HOST:$RSD_PORT =="
  $PMD3 apps install "$PKG" --rsd "$RSD_HOST" "$RSD_PORT"
  BID=$(grep -E '^bundleID:' xtool.yml | awk '{print $2}')
  if [ -z "$BID" ]; then
    echo "No bundle_id in xtool.yml; launch it by hand:"
    if [ "$CONSOLE" = 1 ]; then echo "--console needs a bundle_id in xtool.yml" >&2; return 1; fi
  elif [ "$CONSOLE" = 1 ]; then
    console_run "$BID"
  else
    $PMD3 developer core-device launch-application "$BID" "" --rsd "$RSD_HOST" "$RSD_PORT"
  fi
  if [ "$SYMBOLICATE" = 1 ]; then
    symbolicate_run
  fi
}

# xtool dev run installs without the app icon (xtool has no asset catalog support), so every
# dev build goes build, icon, install: tools/compile-app-icon.sh, as ship.sh. ios-run runs a copy
# of this script from a temp file; the repo is then found as ios-run finds it.
dev_build() {
  $XT dev build
  local apps=(xtool/*.app)
  APP=${apps[0]}
  [ -d "$APP" ] || { echo "ERROR: xtool dev build left no xtool/*.app" >&2; exit 1; }
  local dir icon_sh=
  for dir in "$(dirname "$(readlink -f "$0")")" "${APPLE_DEV_REPO:-$HOME/Tools/omarchy-apple-dev}"; do
    [ -x "$dir/tools/compile-app-icon.sh" ] && { icon_sh=$dir/tools/compile-app-icon.sh; break; }
  done
  if [ -z "$icon_sh" ]; then
    echo "WARNING: tools/compile-app-icon.sh not found; the app installs without its icon" >&2
  elif ! "$icon_sh" "$APP"; then
    echo "WARNING: the app icon did not compile; the app installs without it" >&2
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
    dev_build
    $XT install "${UDID_ARGS[@]}" "$APP"
  else
    # lldb_session stops the app, installs, then launches it suspended and attaches, so
    # breakpoints in startup code hit.
    dev_build
    echo "== 5. LLDB =="
    lldb_session
  fi
  ;;
network)
  echo "== WiFi deploy (phone on the same network) -- UNVERIFIED =="
  echo "Expects: paired over USB once, Developer Mode on, same LAN segment."
  $XT devices --network
  dev_build
  $XT install --network "${UDID_ARGS[@]}" "$APP"
  ;;
rsd)
  rsd_run
  ;;
tailnet)
  # The tunnel lives as long as tailnet-tunnel.py (sudo relays the signal to it): stopped when this script exits.
  sudo -v || { echo "--over-tailnet needs sudo for the TUN device" >&2; exit 1; }
  TT=$(mktemp)
  "$(dirname "$PMD3")/python" "$(dirname "$0")/tools/tailnet-tunnel.py" "$TAILNET_HOST" "${UDID_ARGS[@]}" >"$TT" 2>&1 &
  TTPID=$!
  trap 'kill "$TTPID" 2>/dev/null || true; rm -f "$TT"' EXIT
  for _ in $(seq 30); do grep -q '^RSD ' "$TT" && break; kill -0 "$TTPID" 2>/dev/null || break; sleep 1; done
  read -r _ RSD_HOST RSD_PORT < <(grep '^RSD ' "$TT") || { cat "$TT" >&2; exit 1; }
  echo "== Tunnel to $TAILNET_HOST up: RSD $RSD_HOST $RSD_PORT =="
  rsd_run
  ;;
esac
