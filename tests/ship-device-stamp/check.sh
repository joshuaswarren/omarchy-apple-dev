#!/usr/bin/env bash
# issue 170 regression guard: the --device path must call asc.py stamp-sdk
# before the install hint, and stamp-sdk must exist as a command.
# (Behavioral coverage lives in test_asc_stamp_sdk.py; this checks the wire.)
set -u
here=$(dirname "$(readlink -f "$0")")
repo=$here/../..
fail=0

# 1. The command exists and is registered.
grep -q '"stamp-sdk": stamp_sdk' "$repo/tools/asc.py" || {
	echo "FAIL: asc.py does not register stamp-sdk"; fail=1; }

# 2. The device else-arm calls stamp-sdk before the install hint.
dev_branch=$(awk '/if \[ "\$simulator" = 1 \]; then/{sim=1} sim && /else/{dev=1; next}
	dev && /exit 0/{exit} dev{print}' "$repo/ship.sh")
grep -q 'stamp-sdk "\$app"' <<<"$dev_branch" || {
	echo "FAIL: ship.sh --device branch never calls stamp-sdk"; fail=1; }
stamp_line=$(grep -n 'stamp-sdk "\$app"' <<<"$dev_branch" | head -1 | cut -d: -f1)
install_line=$(grep -n 'xtool install' <<<"$dev_branch" | head -1 | cut -d: -f1)
if [ -z "$stamp_line" ] || [ -z "$install_line" ] || [ "$stamp_line" -ge "$install_line" ]; then
	echo "FAIL: stamp-sdk must run before the xtool install hint"; fail=1
fi

[ "$fail" = 0 ] && echo "ok   ship.sh --device wires stamp-sdk (issue 170)"
exit "$fail"
