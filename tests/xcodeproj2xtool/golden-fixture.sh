#!/usr/bin/env bash
# Golden test for tools/xcodeproj2xtool.py on the committed hand-made fixture
# project (fixture/): classic Sources phase under iOS/, a synced group, an
# INFOPLIST_FILE with $(...) placeholders, and a local SwiftPM package.
# Compares the generated adapter (xtool.yml, Package.swift, xtool.env,
# Info.plist, Sources/ symlinks, stdout, warnings) against golden/.
set -euo pipefail
here=$(dirname "$(readlink -f "$0")")
repo=$here/../..
golden=$here/golden
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cp -a "$here/fixture" "$tmp/proj"
python3 "$repo/tools/xcodeproj2xtool.py" "$tmp/proj/FixtureApp.xcodeproj" \
  --out "$tmp/gen" >"$tmp/stdout.txt" 2>"$tmp/stderr.txt"
fail=0
for f in xtool.yml Package.swift xtool.env Info.plist; do
  if cmp -s "$tmp/gen/$f" "$golden/$f"; then
    echo "ok   $f"
  else
    echo "FAIL $f differs from golden"; diff "$golden/$f" "$tmp/gen/$f" | sed 's/^/  /'; fail=1
  fi
done
links=$(cd "$tmp/gen/Sources" && find . -type l | sort | while read -r l; do
  printf '%s -> %s\n' "$l" "$(readlink "$l")"; done)
if [ "$links" = "$(cat "$golden/symlinks.txt")" ]; then
  echo "ok   Sources/ symlinks"
else
  echo "FAIL Sources/ symlinks differ from golden"; fail=1
fi
sed "s|$tmp|@ROOT@|g" "$tmp/stdout.txt" | sort >"$tmp/stdout.norm"
if cmp -s "$tmp/stdout.norm" "$golden/stdout.txt"; then
  echo "ok   stdout"
else
  echo "FAIL stdout differs from golden"; diff "$golden/stdout.txt" "$tmp/stdout.norm" | sed 's/^/  /'; fail=1
fi
sed "s|$tmp|@ROOT@|g" "$tmp/stderr.txt" | sort >"$tmp/stderr.norm"
if cmp -s "$tmp/stderr.norm" "$golden/stderr.txt"; then
  echo "ok   warnings"
else
  echo "FAIL warnings differ from golden"; diff "$golden/stderr.txt" "$tmp/stderr.norm" | sed 's/^/  /'; fail=1
fi
# --configuration: the settings of another configuration (bundle ID, conditions),
# and a clear stop for a name the target does not have.
python3 "$repo/tools/xcodeproj2xtool.py" "$tmp/proj/FixtureApp.xcodeproj" \
  --out "$tmp/gen-debug" --configuration Debug >/dev/null 2>&1
if grep -qx 'bundleID: net.omarchy.fixture.debug' "$tmp/gen-debug/xtool.yml" &&
  grep -q '\.define("DEBUG")' "$tmp/gen-debug/Package.swift"; then
  echo "ok   --configuration Debug"
else
  echo "FAIL --configuration Debug: bundle ID or DEBUG condition missing"
  sed 's/^/  /' "$tmp/gen-debug/xtool.yml"; fail=1
fi
if python3 "$repo/tools/xcodeproj2xtool.py" "$tmp/proj/FixtureApp.xcodeproj" \
  --out "$tmp/gen-none" --configuration Staging >/dev/null 2>"$tmp/none.txt"; then
  echo "FAIL --configuration Staging: accepted a configuration the target lacks"; fail=1
elif grep -q "no configuration 'Staging' (have: Debug, Release)" "$tmp/none.txt"; then
  echo "ok   --configuration unknown name refused"
else
  echo "FAIL --configuration Staging: unexpected error"; sed 's/^/  /' "$tmp/none.txt"; fail=1
fi
exit $fail
