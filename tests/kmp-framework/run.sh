#!/usr/bin/env bash
# Checks the failure paths and the xcframework metadata of
# kmp/build-framework.sh, offline: the script is sourced for its functions,
# Kotlin/Native, its macOS archive, curl and the SDK are stand-ins, and no
# Gradle, download or real link runs. kmp_link is called in an `if`, as
# kmp_main calls it from an OR-list: errexit is off there, so each failure
# must be returned explicitly.
#
# Rows (expected results written before the code):
#   1  download fails:        kmp_link fails before the compiler, nothing cached
#   2  archive lacks a runtime: kmp_link fails, the distribution is not cached,
#                             the next run downloads again
#   3  good archive:          the link succeeds, the distribution is cached and
#                             reused without a download
#   4  resources missing:     kmp_link fails, "framework:" is not reported
#   5  packaging fails:       kmp_link --xcframework fails, no xcframework left
#   6  device xcframework:    slice ios-arm64, no platform variant
#   7  simulator xcframework: slice ios-arm64-simulator, variant simulator,
#                             linked against the simulator SDK
# Mutants (each must fail its row):
#   M1  drop `|| return 1` after kmp_distribution -> row 1 goes on to the link
#   M2  drop the cp check of the Compose resources -> row 4 succeeds
#   M3  always write ios-arm64 -> row 7
# usage: run.sh [path-to-build-framework.sh]   default: ../../kmp/build-framework.sh
set -uo pipefail
here=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
SCRIPT=${1:-$here/../../kmp/build-framework.sh}
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
fail=0
ok() { echo "ok   $*"; }
bad() { echo "FAIL $*"; fail=1; }

V=9.9.9
# Linux distribution, with a compiler stand-in that writes <-o>.framework and
# records the -target and SDK it was given
linux="$tmp/home/.konan/kotlin-native-prebuilt-linux-x86_64-$V"
mkdir -p "$linux/bin" "$linux/konan"
printf 'llvm.linux_x64.user = llvm-x\nlibffiDir.linux_x64 = ffi-x\n' >"$linux/konan/konan.properties"
cat >"$linux/bin/kotlinc-native" <<'SH'
#!/bin/sh
out="" target="" sysroot=""
while [ "$#" -gt 0 ]; do
  case "$1" in
  -o) out="$2"; shift ;;
  -target) target="$2"; shift ;;
  -Xoverride-konan-properties=*) sysroot="$1" ;;
  esac
  shift
done
echo "$target" >>"$KMP_TEST_LOG/kotlinc"
mkdir -p "$out.framework" && echo bin >"$out.framework/$(basename "$out")"
SH
chmod +x "$linux/bin/kotlinc-native"

# macOS archives: a complete one, and one without the simulator runtime
mk_archive() { # $1: archive, then the runtimes it carries
  local archive="$1" root="$tmp/arch/kotlin-native-prebuilt-macos-x86_64-$V" t
  shift
  rm -rf "$tmp/arch" && mkdir -p "$root"
  for t in "$@"; do mkdir -p "$root/konan/targets/$t" && echo rt >"$root/konan/targets/$t/runtime.bc"; done
  tar -czf "$archive" -C "$tmp/arch" "kotlin-native-prebuilt-macos-x86_64-$V"
}
mkdir -p "$tmp/archives"
mk_archive "$tmp/archives/good.tgz" ios_arm64 ios_simulator_arm64
mk_archive "$tmp/archives/partial.tgz" ios_arm64

# curl stand-in: copies $KMP_TEST_ARCHIVE to -o, or fails when it is unset
mkdir -p "$tmp/bin"
cat >"$tmp/bin/curl" <<'SH'
#!/bin/sh
echo curl >>"$KMP_TEST_LOG/curl"
[ -n "${KMP_TEST_ARCHIVE:-}" ] || exit 22
while [ "$#" -gt 0 ]; do [ "$1" = -o ] && { cp "$KMP_TEST_ARCHIVE" "$2"; exit; }; shift; done
SH
chmod +x "$tmp/bin/curl"

# SDK of install-toolchain.sh
bundle="$tmp/cfg/swiftpm/swift-sdks/darwin.artifactbundle"
for p in iPhoneOS iPhoneSimulator; do
  mkdir -p "$bundle/Developer/Platforms/$p.platform/Developer/SDKs/${p}27.1.sdk"
done

export HOME="$tmp/home" XDG_CACHE_HOME="$tmp/cache" XDG_CONFIG_HOME="$tmp/cfg" PATH="$tmp/bin:$PATH"
export KMP_TEST_LOG="$tmp/log"
mkdir -p "$KMP_TEST_LOG" "$tmp/res/composeResources"
# shellcheck source=/dev/null
source "$SCRIPT"
set +e

block() { # $1: build dir, $2: resources dir or empty
  printf 'VERSION\t%s\nFRAMEWORK\t:shared\t%s\tShared\tfalse\n' "$V" "$1"
  [ -z "$2" ] || printf 'RESOURCES\t%s\n' "$2"
}
reset_logs() { rm -f "$KMP_TEST_LOG"/*; }
dist="$tmp/cache/omarchy-apple-dev/kmp/kotlin-native-$V"

# 1 download fails
reset_logs
if out=$(KMP_TEST_ARCHIVE="" kmp_link "$(block "$tmp/b1" "")" ios_arm64 "" true 2>&1); then
  bad "row 1: kmp_link succeeded after a failed download"
elif [ -e "$KMP_TEST_LOG/kotlinc" ] || ! grep -q "download failed" <<<"$out" || grep -q "link failed" <<<"$out"; then
  bad "row 1: went on after a failed download: $out"
elif [ -e "$dist" ]; then
  bad "row 1: a distribution was cached"
else ok "row 1: download failure stops before the compiler, nothing cached"; fi

# 2 archive without the simulator runtime
reset_logs
if KMP_TEST_ARCHIVE="$tmp/archives/partial.tgz" kmp_link "$(block "$tmp/b2" "")" ios_arm64 "" true >/dev/null 2>&1; then
  bad "row 2: kmp_link succeeded with an incomplete archive"
elif [ -e "$dist" ] || [ -e "$KMP_TEST_LOG/kotlinc" ]; then
  bad "row 2: the incomplete distribution was cached or used"
else ok "row 2: incomplete archive rejected, not cached"; fi

# 3 good archive, then reuse without download
reset_logs
if ! KMP_TEST_ARCHIVE="$tmp/archives/good.tgz" kmp_link "$(block "$tmp/b3" "")" ios_arm64 "" true >/dev/null 2>&1; then
  bad "row 3: link with a good archive failed"
elif [ ! -f "$dist/.omarchy-kmp-complete" ] || [ ! -f "$tmp/b3/omarchy-kmp/ios_arm64/Shared.framework/Shared" ]; then
  bad "row 3: no cached distribution or no framework"
else
  reset_logs
  if KMP_TEST_ARCHIVE="" kmp_link "$(block "$tmp/b3" "")" ios_arm64 "" true >/dev/null 2>&1 && [ ! -e "$KMP_TEST_LOG/curl" ]; then
    ok "row 3: distribution cached after validation, reused without a download"
  else bad "row 3: the cached distribution was not reused"; fi
fi

# 4 resources missing
if out=$(kmp_link "$(block "$tmp/b4" "$tmp/no-such-resources")" ios_arm64 "" true 2>&1); then
  bad "row 4: kmp_link succeeded with missing Compose resources"
elif grep -q "framework:" <<<"$out"; then
  bad "row 4: the framework was reported after the resource copy failed"
else ok "row 4: missing Compose resources fail the link"; fi

# 5 packaging fails (python3 cannot run)
mkdir -p "$tmp/nopy"
printf '#!/bin/sh\nexit 1\n' >"$tmp/nopy/python3" && chmod +x "$tmp/nopy/python3"
XCFRAMEWORK=true
if PATH="$tmp/nopy:$PATH" kmp_link "$(block "$tmp/b5" "")" ios_arm64 "" true >/dev/null 2>&1; then
  bad "row 5: kmp_link --xcframework succeeded though the Info.plist was not written"
elif [ -e "$tmp/b5/omarchy-kmp/ios_arm64/Shared.xcframework" ]; then
  bad "row 5: a broken xcframework was left"
else ok "row 5: packaging failure fails the link, nothing left"; fi

plist() { python3 -c 'import plistlib,sys,json; print(json.dumps(plistlib.load(open(sys.argv[1],"rb"))["AvailableLibraries"]))' "$1"; }

# 6 device xcframework
if kmp_link "$(block "$tmp/b6" "$tmp/res")" ios_arm64 "" true >/dev/null 2>&1 &&
  libs=$(plist "$tmp/b6/omarchy-kmp/ios_arm64/Shared.xcframework/Info.plist") &&
  [ -f "$tmp/b6/omarchy-kmp/ios_arm64/Shared.xcframework/ios-arm64/Shared.framework/Shared" ] &&
  grep -q '"LibraryIdentifier": "ios-arm64"' <<<"$libs" && ! grep -q SupportedPlatformVariant <<<"$libs"; then
  ok "row 6: device xcframework, slice ios-arm64 without a variant"
else bad "row 6: device xcframework metadata: ${libs:-none}"; fi

# 7 simulator xcframework
reset_logs
if kmp_link "$(block "$tmp/b7" "")" ios_simulator_arm64 "" true >/dev/null 2>&1 &&
  libs=$(plist "$tmp/b7/omarchy-kmp/ios_simulator_arm64/Shared.xcframework/Info.plist") &&
  [ -f "$tmp/b7/omarchy-kmp/ios_simulator_arm64/Shared.xcframework/ios-arm64-simulator/Shared.framework/Shared" ] &&
  grep -q '"LibraryIdentifier": "ios-arm64-simulator"' <<<"$libs" &&
  grep -q '"SupportedPlatformVariant": "simulator"' <<<"$libs" &&
  [ "$(readlink "$tmp/cache/omarchy-apple-dev/kmp/data/dependencies/omarchy-kmp-sdk")" = \
    "$bundle/Developer/Platforms/iPhoneSimulator.platform/Developer/SDKs/iPhoneSimulator27.1.sdk" ] &&
  grep -qx ios_simulator_arm64 "$KMP_TEST_LOG/kotlinc"; then
  ok "row 7: simulator xcframework, slice ios-arm64-simulator, variant simulator, simulator SDK"
else bad "row 7: simulator xcframework metadata: ${libs:-none}"; fi

[ "$fail" = 0 ] && echo "kmp-framework: all rows passed" || echo "kmp-framework: FAILED"
exit "$fail"
