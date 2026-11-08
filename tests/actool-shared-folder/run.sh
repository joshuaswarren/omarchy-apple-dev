#!/usr/bin/env bash
# Checks that actool merges a folder two catalogs both have, as Apple's does:
# WfpColors.xcassets/Wfp and WfpIcons.xcassets/Wfp, each with its own
# Contents.json (provides-namespace). Before, the second Contents.json copy
# crashed actool ("A file with the same name already exists").
#
# Rows (expected results written before the code):
#   1  shared folder:  exit 0, Assets.car written
#   2  same asset in both catalogs: still refused (DuplicateEntry), exit != 0
#   3  the folder provides a namespace in one catalog only: refused, exit != 0
# Mutants (each must fail its row; checked by hand when the test was written):
#   M1  copy the folder Contents.json unconditionally -> row 1
#   M2  keep the first Contents.json without comparing properties -> row 3
# usage: run.sh [actool]   default: tools/darwin-tools/.build/release/actool
# Skipped (exit 0) when no actool is built.
set -uo pipefail
here=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
ACTOOL=${1:-$here/../../tools/darwin-tools/.build/release/actool}
[ -x "$ACTOOL" ] || { echo "skip: no actool at $ACTOOL (swift build -c release --product actool in tools/darwin-tools)"; exit 0; }
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
fail=0

# catalog <dir> <colorset name>: a catalog with a namespaced Wfp folder holding one color
catalog() {
  mkdir -p "$1/Wfp/$2.colorset"
  echo '{"info":{"author":"xcode","version":1}}' >"$1/Contents.json"
  echo '{"info":{"author":"xcode","version":1},"properties":{"provides-namespace":true}}' >"$1/Wfp/Contents.json"
  echo '{"colors":[{"color":{"color-space":"srgb","components":{"red":"1.000","green":"0.000","blue":"0.000","alpha":"1.000"}},"idiom":"universal"}],"info":{"author":"xcode","version":1}}' \
    >"$1/Wfp/$2.colorset/Contents.json"
}
compile() { # $1: out dir, then the catalogs
  local out="$1"
  shift
  mkdir -p "$out"
  "$ACTOOL" "$@" --compile "$out" --platform iphoneos --minimum-deployment-target 17.0 \
    --output-partial-info-plist "$out/partial.plist" >"$out/log" 2>&1
}

# 1 shared folder
catalog "$tmp/Colors.xcassets" red
catalog "$tmp/Icons.xcassets" blue
if compile "$tmp/out1" "$tmp/Colors.xcassets" "$tmp/Icons.xcassets" 2>/dev/null && [ -s "$tmp/out1/Assets.car" ]; then
  echo "ok   row 1: a folder in two catalogs merges"
else
  echo "FAIL row 1: $(tail -n 3 "$tmp/out1/log")"
  fail=1
fi

# 2 the same asset in both catalogs is still refused
catalog "$tmp/Other.xcassets" red
# (actool stops on its top-level error with a trap; the shell's report of it is silenced)
if compile "$tmp/out2" "$tmp/Colors.xcassets" "$tmp/Other.xcassets" 2>/dev/null ||
  ! grep -q 'red.colorset is defined in more than one asset catalog' "$tmp/out2/log"; then
  echo "FAIL row 2: a duplicate asset was accepted, or refused for another reason"
  fail=1
else
  echo "ok   row 2: the same asset in two catalogs is still refused"
fi

# 3 the same folder, namespaced in one catalog only, is refused
catalog "$tmp/Plain.xcassets" green
echo '{"info":{"author":"xcode","version":1}}' >"$tmp/Plain.xcassets/Wfp/Contents.json"
if compile "$tmp/out3" "$tmp/Colors.xcassets" "$tmp/Plain.xcassets" 2>/dev/null ||
  ! grep -q 'Wfp is a folder in more than one asset catalog with different properties' "$tmp/out3/log"; then
  echo "FAIL row 3: folders with different properties were merged, or refused for another reason"
  fail=1
else
  echo "ok   row 3: a folder with different properties in two catalogs is refused"
fi

[ "$fail" = 0 ] && echo "actool-shared-folder: all rows passed" || echo "actool-shared-folder: FAILED"
exit "$fail"
