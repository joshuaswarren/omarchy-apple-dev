#!/usr/bin/env bash
# Test entry point for the repo. Exit non-zero on any failure.
#   tests/run.sh
set -uo pipefail
here=$(dirname "$(readlink -f "$0")")
repo=$here/..
cd "$repo"
fail=0
tmp_selftest=$(mktemp)
trap 'rm -f "$tmp_selftest"' EXIT

echo "== tools/xcodeproj2xtool.py --self-test"
if python3 tools/xcodeproj2xtool.py --self-test >"$tmp_selftest" 2>&1; then
  grep -E "self-test passed" "$tmp_selftest" | sed 's/^/ok   /'
else
  echo "FAIL self-test"; sed 's/^/  /' "$tmp_selftest"; fail=1
fi

echo "== tools/xcodeproj2xtool.py fixture golden"
bash tests/xcodeproj2xtool/golden-fixture.sh || fail=1

echo "== tools/asc.py validate golden"
python3 tests/asc/golden-validate.py || fail=1

echo "== tools/asc.py validate on a signed app with an extension (real rcodesign; skips without it)"
python3 tests/asc/appex-seal.py || fail=1

echo "== tests/test_*.py (unittest)"
python3 -m unittest discover -s tests -p 'test_*.py' || fail=1

echo "== tools/ibmac.py mac golden (src-mac vs golden-mac)"
bash tests/ibtool/check-golden.sh || fail=1

echo "== tests/install-mode.sh"
bash tests/install-mode.sh || fail=1

echo "== tests/install-venv/run.sh"
bash tests/install-venv/run.sh || fail=1

echo "== tests/sdk-state/check.sh"
bash tests/sdk-state/check.sh || fail=1

echo "== tests/flutter-dart-symbols/run.sh"
bash tests/flutter-dart-symbols/run.sh || fail=1

echo "== tests/flutter-configuration/run.sh"
bash tests/flutter-configuration/run.sh || fail=1

echo "== tests/flutter-assets/run.sh"
bash tests/flutter-assets/run.sh || fail=1

echo "== tests/ship-root-resources/run.sh"
bash tests/ship-root-resources/run.sh || fail=1

echo "== tests/flutter-ship/run.sh"
bash tests/flutter-ship/run.sh || fail=1

echo "== tests/device-run-console/run.sh"
bash tests/device-run-console/run.sh || fail=1

echo "== tests/ips-symbolicate/run.sh"
bash tests/ips-symbolicate/run.sh || fail=1

echo "== tests/flutter-dsyms/run.sh"
bash tests/flutter-dsyms/run.sh || fail=1

echo "== tests/device-run-symbolicate/run.sh"
bash tests/device-run-symbolicate/run.sh || fail=1

echo "== simview/test.sh"
bash simview/test.sh || fail=1

echo "== simview/test-m3.sh"
bash simview/test-m3.sh || fail=1

echo "== simview/test-m4.sh"
bash simview/test-m4.sh || fail=1

echo "== simview/test-m5.sh"
bash simview/test-m5.sh || fail=1

echo "== simview/test-m6.sh"
bash simview/test-m6.sh || fail=1

echo "== simview/test-m7.sh"
bash simview/test-m7.sh || fail=1

echo "== tests/ibtool/compile-golden.sh"
if command -v xcrun >/dev/null 2>&1; then
  # Regenerates the golden corpus with Apple's ibtool; needs a Mac with Xcode.
  tar -C tests/ibtool -cf - src | bash tests/ibtool/compile-golden.sh >/dev/null || fail=1
else
  echo "SKIP  compile-golden.sh: regenerates goldens with Apple's ibtool and"
  echo "      needs a Mac with Xcode (xcrun not on this host). Run it there:"
  echo "      tar -C tests/ibtool -cf - src | ssh mac \"\$(cat tests/ibtool/compile-golden.sh)\" | tar -C tests/ibtool -xf -"
fi

if [ "$fail" -ne 0 ]; then
  echo "tests/run.sh: FAILED"
  exit 1
fi
echo "tests/run.sh: all checks passed"
