#!/usr/bin/env bash
# Checks that device-run.sh compiles the app icon into every dev install, with stub xtool,
# actool, lsusb and pymobiledevice3 and no phone. xtool dev run has no asset catalog support,
# so a dev install went on the phone without its icon.
#
# Rows (expected results written before the code):
#   1  usb:      xtool dev build, then actool --app-icon AppIcon into xtool/Demo.app with the
#                project's catalog, then xtool install xtool/Demo.app; no xtool dev run; the
#                app's Info.plist gains the icon keys of actool's partial plist
#   2  network:  the same, with xtool install --network
#   3  ios-run:  a copy of device-run.sh outside the repo (as ios-run runs it) still finds
#                tools/compile-app-icon.sh through APPLE_DEV_REPO
#   4  failure:  actool exiting 1 gives a warning, and the app is still installed
#   5  no app:   xtool dev build leaving no xtool/*.app exits non-zero with an error naming it,
#                and runs neither actool nor xtool install
# Mutants: the usb path back on xtool dev run -> row 1 fails; no .app check -> row 5 fails.
set -uo pipefail
here=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
repo=$(cd "$here/../.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
fail=0
ok() { echo "ok   $*"; }
bad() { echo "FAIL $*"; fail=1; }
has() { case "$1" in *"$2"*) ok "$3";; *) bad "$3 (missing: $2)";; esac; }
not_has() { case "$1" in *"$2"*) bad "$3 (unexpected: $2)";; *) ok "$3";; esac; }

mkdir -p "$tmp/bin" "$tmp/home/.local/bin"
cat >"$tmp/home/.local/bin/xtool" <<'STUB'
#!/usr/bin/env bash
echo "xtool $*" >>"$STUB_LOG"
if [ "$1 $2" = "dev build" ]; then
  [ -z "${STUB_NO_APP:-}" ] || { rm -rf xtool; exit 0; }
  rm -rf xtool && mkdir -p xtool/Demo.app
  python3 -c 'import plistlib,sys; plistlib.dump({"CFBundleIdentifier": "com.example.demo", "MinimumOSVersion": "17.0"}, open(sys.argv[1], "wb"))' xtool/Demo.app/Info.plist
fi
STUB
cat >"$tmp/bin/actool" <<'STUB'
#!/usr/bin/env bash
echo "actool $*" >>"$STUB_LOG"
[ "${STUB_ACTOOL_RC:-0}" = 0 ] || exit "$STUB_ACTOOL_RC"
while [ $# -gt 0 ]; do
  case "$1" in
    --compile) : >"$2/Assets.car" ;;
    --output-partial-info-plist)
      python3 -c 'import plistlib,sys; plistlib.dump({"CFBundleIcons": {"CFBundlePrimaryIcon": {"CFBundleIconName": "AppIcon"}}}, open(sys.argv[1], "wb"))' "$2" ;;
  esac
  shift
done
STUB
printf '#!/bin/sh\necho "Bus 001 Device 002: ID 05ac:12a8 Apple, Inc. iPhone"\n' >"$tmp/bin/lsusb"
printf '#!/bin/sh\necho "pmd3 $*" >>"$STUB_LOG"\n' >"$tmp/bin/pymobiledevice3"
chmod +x "$tmp/home/.local/bin/xtool" "$tmp/bin/"*

proj=$tmp/proj
mkdir -p "$proj/Sources/Demo/Assets.xcassets/AppIcon.appiconset"
printf 'bundleID: com.example.demo\n' >"$proj/xtool.yml"
echo '{"images":[{"filename":"icon.png","idiom":"universal","platform":"ios","size":"1024x1024"}],"info":{"author":"xcode","version":1}}' \
  >"$proj/Sources/Demo/Assets.xcassets/AppIcon.appiconset/Contents.json"

# drive SCRIPT ARGS...: runs SCRIPT in the project; sets OUT, RC and LOG.
drive() {
  local script=$1; shift
  : >"$tmp/log"
  OUT=$(cd "$proj" && env HOME="$tmp/home" PATH="$tmp/bin:$PATH" STUB_LOG="$tmp/log" \
    ACTOOL="$tmp/bin/actool" PY=python3 STUB_ACTOOL_RC="${STUB_ACTOOL_RC:-0}" STUB_NO_APP="${STUB_NO_APP:-}" \
    APPLE_DEV_REPO="${APPLE_DEV_REPO:-}" timeout 60 bash "$script" "$@" 2>&1)
  RC=$?
  LOG=$(cat "$tmp/log")
}
# in_order LABEL PATTERN...: the log lines matching each PATTERN come in this order.
in_order() {
  local label=$1 line=0 n p; shift
  for p in "$@"; do
    n=$(grep -n -- "$p" "$tmp/log" | head -n1 | cut -d: -f1)
    if [ -z "$n" ] || [ "$n" -le "$line" ]; then bad "$label (order at: $p)"; return; fi
    line=$n
  done
  ok "$label"
}
icon_keys() {
  python3 -c 'import plistlib,sys; print("CFBundleIcons" in plistlib.load(open(sys.argv[1], "rb")))' \
    "$proj/xtool/Demo.app/Info.plist"
}

echo "== row 1: usb"
drive "$repo/device-run.sh"
[ "$RC" = 0 ] && ok "row 1 exit 0" || bad "row 1 exit $RC: $OUT"
in_order "row 1 build, icon, install" "^xtool dev build" "^actool .*--compile xtool/Demo.app .*--app-icon AppIcon" "^xtool install xtool/Demo.app"
has "$LOG" "Assets.xcassets --compile" "row 1 actool gets the project's catalog"
not_has "$LOG" "xtool dev run" "row 1 no xtool dev run"
[ "$(icon_keys)" = True ] && ok "row 1 Info.plist has CFBundleIcons" || bad "row 1 Info.plist has no CFBundleIcons"

echo "== row 2: --network"
drive "$repo/device-run.sh" --network
in_order "row 2 build, icon, install --network" "^xtool dev build" "^actool .*--app-icon AppIcon" "^xtool install --network xtool/Demo.app"
not_has "$LOG" "xtool dev run" "row 2 no xtool dev run"

echo "== row 3: a copy outside the repo, as ios-run runs it"
cp "$repo/device-run.sh" "$tmp/dr-copy"
APPLE_DEV_REPO=$repo drive "$tmp/dr-copy"
in_order "row 3 icon still compiled" "^xtool dev build" "^actool .*--app-icon AppIcon" "^xtool install xtool/Demo.app"
not_has "$OUT" "not found" "row 3 no not-found warning"

echo "== row 4: actool fails"
STUB_ACTOOL_RC=1 drive "$repo/device-run.sh"
has "$OUT" "WARNING: the app icon did not compile" "row 4 warning"
has "$LOG" "xtool install xtool/Demo.app" "row 4 still installed"
[ "$RC" = 0 ] && ok "row 4 exit 0" || bad "row 4 exit $RC"

echo "== row 5: xtool dev build leaves no .app"
STUB_NO_APP=1 drive "$repo/device-run.sh"
[ "$RC" != 0 ] && ok "row 5 exit $RC" || bad "row 5 exit 0"
has "$OUT" "ERROR: xtool dev build left no xtool/*.app" "row 5 error"
not_has "$LOG" "actool" "row 5 no icon compiled"
not_has "$LOG" "xtool install" "row 5 nothing installed"

echo "== mutant: usb path back on xtool dev run (row 1 must fail)"
mkdir -p "$tmp/mut"
cp -r "$repo/tools" "$tmp/mut/"
awk '/^    dev_build$/ && !done { getline nxt; if (nxt ~ /XT install "\$\{UDID_ARGS/) { print "    $XT dev run \"${UDID_ARGS[@]}\""; done=1; next } print; print nxt; next } { print }' \
  "$repo/device-run.sh" >"$tmp/mut/device-run.sh"
if cmp -s "$repo/device-run.sh" "$tmp/mut/device-run.sh"; then
  bad "mutant could not be built"
else
  drive "$tmp/mut/device-run.sh"
  case "$LOG" in *"--app-icon AppIcon"*) bad "mutant still compiled the icon";; *) ok "mutant: no icon, row 1 fails";; esac
fi

[ "$fail" = 0 ] && echo "device-run-app-icon: all checks passed"
exit "$fail"
