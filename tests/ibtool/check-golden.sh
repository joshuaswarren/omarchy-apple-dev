#!/usr/bin/env bash
# Compile tests/ibtool/src-mac with the repo's Linux ibtool (which dispatches
# MacOSX.Cocoa xibs to tools/ibmac.py) and require byte-identical output
# against the committed golden-mac corpus. The goldens themselves are
# regenerated with Apple's ibtool on a Mac: tests/ibtool/compile-golden.sh.
set -euo pipefail
here=$(dirname "$(readlink -f "$0")")
repo=$here/../..
fail=0
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
for f in "$repo"/tests/ibtool/src-mac/*.xib "$repo"/tests/ibtool/src-mac/Base.lproj/*.xib; do
  [ -f "$f" ] || continue
  name=$(basename "${f%.xib}")
  out="$tmp/$name.nib"
  if ! python3 "$repo/tools/ibtool" --compile "$out" "$f" >"$tmp/$name.log" 2>&1; then
    echo "FAIL $name: ibtool --compile failed"; sed 's/^/  /' "$tmp/$name.log"; fail=1; continue
  fi
  if cmp -s "$out" "$repo/tests/ibtool/golden-mac/$name.nib"; then
    echo "ok   $name (byte-identical to golden-mac)"
  else
    echo "FAIL $name: differs from tests/ibtool/golden-mac/$name.nib"; fail=1
  fi
done
exit $fail
