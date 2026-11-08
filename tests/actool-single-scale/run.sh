#!/usr/bin/env bash
# Checks that actool keys a bitmap with no scale (Xcode's "Single Scale"
# imageset: one universal entry, no "scale") at 1x, as Apple's actool does.
# Keyed at scale 0, UIKit never finds it: "No image named 'X' found in asset
# catalog", seen on an iPhone under iOS 26.5 for single-scale PNG and JPEG sets.
#
# Rows (expected results written before the code):
#   1  single-scale PNG: every rendition key of the car has scale 1, none 0
#   2  vector SVG:       still compiles (its source has no scale either)
# Mutants (each must fail its row; checked by hand when the test was written):
#   M1  drop keyBitmapsAtOneX -> row 1 (a key at scale 0)
# usage: run.sh [actool]   default: tools/darwin-tools/.build/release/actool
# Skipped (exit 0) when no actool is built.
set -uo pipefail
here=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
ACTOOL=${1:-$here/../../tools/darwin-tools/.build/release/actool}
[ -x "$ACTOOL" ] || { echo "skip: no actool at $ACTOOL (swift build -c release --product actool in tools/darwin-tools)"; exit 0; }
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
fail=0

compile() { # $1: out dir, $2: catalog
  mkdir -p "$1"
  "$ACTOOL" "$2" --compile "$1" --platform iphoneos --minimum-deployment-target 17.0 \
    --output-partial-info-plist "$1/partial.plist" >"$1/log" 2>&1
}
# scales <car>: the scale token of every rendition key, one a line
scales() {
  python3 -I - "$here/../../tools" "$1" <<'PY'
import struct, sys
sys.path.insert(0, sys.argv[1])
import car_check
bom = car_check._Bom(open(sys.argv[2], "rb").read())
at = car_check._key_format(bom).index(12)
for key_block, _ in bom.leaves("RENDITIONS"):
    key = bom.block(key_block)
    print(struct.unpack(f"<{len(key) // 2}H", key)[at])
PY
}

# 1 single-scale PNG
set1="$tmp/A.xcassets/Photo.imageset"
mkdir -p "$set1"
echo '{"info":{"author":"xcode","version":1}}' >"$tmp/A.xcassets/Contents.json"
echo '{"images":[{"filename":"photo.png","idiom":"universal"}],"info":{"author":"xcode","version":1}}' >"$set1/Contents.json"
python3 -I - "$set1/photo.png" <<'PY'
import struct, sys, zlib
w = h = 4
raw = b"".join(b"\0" + b"\xff\x00\x00\xff" * w for _ in range(h))
chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
open(sys.argv[1], "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                              + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
PY
if ! compile "$tmp/out1" "$tmp/A.xcassets"; then
  echo "FAIL row 1: actool failed: $(tail -n 3 "$tmp/out1/log")"
  fail=1
elif ! got=$(scales "$tmp/out1/Assets.car") || [ -z "$got" ]; then
  echo "FAIL row 1: could not read the rendition keys"
  fail=1
elif grep -qvx 1 <<<"$got"; then
  echo "FAIL row 1: rendition scales $(sort -u <<<"$got" | tr '\n' ' ')(want 1)"
  fail=1
else
  echo "ok   row 1: a single-scale PNG is keyed at 1x"
fi

# 2 vector SVG still compiles (needs rsvg-convert, as actool does for SVG)
if command -v rsvg-convert >/dev/null; then
  set2="$tmp/B.xcassets/Glyph.imageset"
  mkdir -p "$set2"
  echo '{"info":{"author":"xcode","version":1}}' >"$tmp/B.xcassets/Contents.json"
  echo '{"images":[{"filename":"g.svg","idiom":"universal"}],"info":{"author":"xcode","version":1},"properties":{"preserves-vector-representation":true}}' >"$set2/Contents.json"
  echo '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><rect width="24" height="24"/></svg>' >"$set2/g.svg"
  if compile "$tmp/out2" "$tmp/B.xcassets" && [ -s "$tmp/out2/Assets.car" ]; then
    echo "ok   row 2: a vector SVG still compiles"
  else
    echo "FAIL row 2: $(tail -n 3 "$tmp/out2/log")"
    fail=1
  fi
else
  echo "skip row 2: no rsvg-convert"
fi

[ "$fail" = 0 ] && echo "actool-single-scale: all rows passed" || echo "actool-single-scale: FAILED"
exit "$fail"
