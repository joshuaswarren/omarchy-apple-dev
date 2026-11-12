#!/usr/bin/env bash
# Checks the step-4 loop of ship.sh --device (root-level resources) on the
# Info.plist of the resource bundles: code built as a package (SWIFT_PACKAGE,
# the PlistFiles of SwiftGen) reads Bundle.module's Info.plist and traps on a
# key it lacks. The loop is extracted verbatim from ship.sh; nothing else of
# the script runs.
#
# Rows (expected results written before the code):
#   1  app:       the bundle's Info.plist gains the app's CFBundleShortVersionString
#     and a custom key, keeps its own CFBundleIdentifier and CFBundlePackageType
#   2  appex:     the extension's bundle gains the extension's keys, not the app's
#   3  no plist:  a bundle without an Info.plist is left without one, no error
#   4  rerun:     a second run leaves the merged plist byte-identical
# Mutants (each must fail its row):
#   M1  merge {**own, **target} (target wins) -> row 1: the bundle takes the
#       app's CFBundleIdentifier
#   M2  drop the [ -f "$resbundle/Info.plist" ] guard -> row 3 errors out
# usage: run.sh [path-to-ship.sh]   default: ../../ship.sh (repo checkout)
set -uo pipefail
here=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
SHIP=${1:-$here/../../ship.sh}
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
fail=0
ok() { echo "ok   $*"; }
bad() { echo "FAIL $*"; fail=1; }

plist() { # plist <path> <python dict literal>
  python3 -c 'import plistlib, sys; plistlib.dump(eval(sys.argv[2]), open(sys.argv[1], "wb"))' "$1" "$2"
}
key() { # key <plist> <key>
  python3 -c 'import plistlib, sys; print(plistlib.load(open(sys.argv[1], "rb")).get(sys.argv[2], ""))' "$1" "$2"
}

# drive <app>: runs the step-4 loop of $SHIP on xtool/<app>. Called on its own
# line, never under if or &&, where bash would turn set -e off inside it.
drive() {
  (
    set -euo pipefail
    loop=$(mktemp)
    awk '/^  for target in "\$app" "\$app"\/PlugIns\/\*\.appex; do$/,/^  done$/' "$SHIP" >"$loop"
    [ -s "$loop" ] || { echo "no step-4 loop found in $SHIP" >&2; exit 9; }
    cd "$tmp/proj"
    PY=python3
    app=xtool/$1
    source "$loop"
  )
}

app=$tmp/proj/xtool/Demo.app
mkdir -p "$app/Demo_Demo.bundle" "$app/PlugIns/Widget.appex/Demo_Widget.bundle" "$app/Other_Other.bundle"
plist "$app/Info.plist" '{"CFBundleIdentifier": "net.example.demo", "CFBundleShortVersionString": "2.0", "ApiKey": "k"}'
plist "$app/Demo_Demo.bundle/Info.plist" '{"CFBundleIdentifier": "demo.resources", "CFBundlePackageType": "BNDL"}'
plist "$app/PlugIns/Widget.appex/Info.plist" '{"CFBundleIdentifier": "net.example.demo.widget", "CFBundleShortVersionString": "2.1"}'
plist "$app/PlugIns/Widget.appex/Demo_Widget.bundle/Info.plist" '{"CFBundleIdentifier": "widget.resources"}'
mkdir -p "$tmp/proj/xtool/Plain.app/Plain_Plain.bundle"
echo data >"$tmp/proj/xtool/Plain.app/Plain_Plain.bundle/data.json"
plist "$tmp/proj/xtool/Plain.app/Info.plist" '{"CFBundleIdentifier": "net.example.plain"}'

drive Demo.app
rc=$?
if [ "$rc" = 0 ]; then ok "step-4 loop ran"; else bad "step-4 loop failed ($rc)"; fi
b=$app/Demo_Demo.bundle/Info.plist
if [ "$(key "$b" CFBundleShortVersionString)" = 2.0 ] && [ "$(key "$b" ApiKey)" = k ] &&
  [ "$(key "$b" CFBundleIdentifier)" = demo.resources ] && [ "$(key "$b" CFBundlePackageType)" = BNDL ]; then
  ok "1 app bundle gains the app's keys, keeps its own"
else bad "1 app bundle plist: $(python3 -c 'import plistlib,sys; print(plistlib.load(open(sys.argv[1],"rb")))' "$b")"; fi
w=$app/PlugIns/Widget.appex/Demo_Widget.bundle/Info.plist
if [ "$(key "$w" CFBundleShortVersionString)" = 2.1 ] && [ -z "$(key "$w" ApiKey)" ] &&
  [ "$(key "$w" CFBundleIdentifier)" = widget.resources ]; then
  ok "2 appex bundle gains the extension's keys"
else bad "2 appex bundle plist"; fi
drive Plain.app 2>/dev/null
rc=$?
if [ "$rc" = 0 ] && [ ! -e "$tmp/proj/xtool/Plain.app/Plain_Plain.bundle/Info.plist" ]; then
  ok "3 bundle without an Info.plist left alone"
else bad "3 bundle without an Info.plist"; fi
before=$(sha256sum "$b")
drive Demo.app
rc=$?
if [ "$rc" = 0 ] && [ "$(sha256sum "$b")" = "$before" ]; then ok "4 rerun leaves the plist unchanged"
else bad "4 rerun changed the plist"; fi
exit $fail
