#!/usr/bin/env bash
# Checks tools/lldb-ios-shadow.sh against a stub toolchain and a stub darwin SDK bundle: the
# shadow layout (iOS resource dir in lib/swift, the toolchain's linux/ and host/ kept, its
# CoreFoundation left out), LLDB's Python package re-pointed at the shadow liblldb, reuse while
# the stamp matches, rebuild after a toolchain update, an interrupted build or another SDK,
# copy mode, concurrent runs, and a clear failure without the SDK. No Swift, no device.
set -uo pipefail
here=$(dirname "$(readlink -f "$0")")
script=${SHADOW:-$here/../../tools/lldb-ios-shadow.sh}
fail=0
ok() { echo "ok   $1"; }
bad() { echo "FAIL $1: $2"; fail=1; }
check() { # NAME COMMAND...
  local name=$1; shift
  if "$@"; then ok "$name"; else bad "$name" "$*"; fi
}

w=$(mktemp -d)
trap 'rm -rf -- "$w"' EXIT
tc=$w/toolchain/usr
py=local/lib64/python3.13/site-packages
mkdir -p "$tc/bin" "$tc/lib/swift/linux" "$tc/lib/swift/host/compiler" \
  "$tc/lib/swift/CoreFoundation" "$tc/lib/clang/21" "$tc/$py/lldb/formatters" "$tc/share/doc"
printf '#!/bin/sh\necho stub swift\n' >"$tc/bin/swift"
printf '#!/bin/sh\necho stub lldb\n' >"$tc/bin/lldb"
chmod +x "$tc/bin/swift" "$tc/bin/lldb"
echo lldb-v1 >"$tc/lib/liblldb.so.21.0.0"
ln -s liblldb.so.21.0.0 "$tc/lib/liblldb.so.21.0"
ln -s liblldb.so.21.0 "$tc/lib/liblldb.so"
echo clang >"$tc/lib/libclang.so.21.0.0"
touch "$tc/lib/swift/CoreFoundation/module.modulemap" "$tc/$py/lldb/__init__.py" "$tc/$py/six.py"
# As in the swift.org toolchain: _lldb.so is a relative link to usr/lib/liblldb.so
ln -s ../../../../../lib/liblldb.so "$tc/$py/lldb/_lldb.cpython-313-aarch64-linux-gnu.so"
# swift on PATH is a symlink, as mise and the AUR package install it
mkdir -p "$w/path"
ln -s "$tc/bin/swift" "$w/path/swift"

sdk_bundle() { # CONFIG_DIR: a stub darwin SDK bundle under it
  local b=$1/swiftpm/swift-sdks/darwin.artifactbundle
  mkdir -p "$b/Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/swift/"{iphoneos,clang,host,apinotes} \
    "$b/Developer/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS.sdk/usr/lib/swift/shims"
}
cfg=$w/config
sdk_bundle "$cfg"
rd=$cfg/swiftpm/swift-sdks/darwin.artifactbundle/Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/swift
sdk=$cfg/swiftpm/swift-sdks/darwin.artifactbundle/Developer/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS.sdk

run() { PATH="$w/path:/usr/bin:/bin" XDG_CONFIG_HOME="${CFG:-$cfg}" XDG_CACHE_HOME="$w/cache" HOME="$w/home" "$script"; }

out=$(run) || { bad "first run" "exit $?: $out"; exit 1; }
lldb=$(sed -n 1p <<<"$out")
s=$(dirname "$(dirname "$lldb")") # shadow usr
check "prints the shadow lldb under XDG_CACHE_HOME" test "${lldb#"$w/cache/omarchy-apple-dev/lldb-ios/"}" != "$lldb"
check "prints the iPhoneOS SDK" test "$(sed -n 2p <<<"$out")" = "$sdk"
check "lldb hard-linked" test "$lldb" -ef "$tc/bin/lldb"
check "liblldb hard-linked" test "$s/lib/liblldb.so.21.0.0" -ef "$tc/lib/liblldb.so.21.0.0"
check "liblldb.so.21.0 points inside the shadow" test "$(readlink "$s/lib/liblldb.so.21.0")" = liblldb.so.21.0.0
check "liblldb.so points inside the shadow" test "$(readlink "$s/lib/liblldb.so")" = liblldb.so.21.0
check "lib/swift/iphoneos is the SDK's" test "$(readlink "$s/lib/swift/iphoneos")" = "$rd/iphoneos"
check "lib/swift/clang is the SDK's" test "$(readlink "$s/lib/swift/clang")" = "$rd/clang"
check "lib/swift/linux is the toolchain's" test "$(readlink "$s/lib/swift/linux")" = "$tc/lib/swift/linux"
check "lib/swift/host is the toolchain's" test "$(readlink "$s/lib/swift/host")" = "$tc/lib/swift/host"
check "the toolchain's CoreFoundation is left out" test ! -e "$s/lib/swift/CoreFoundation"
check "other libraries are symlinked" test "$(readlink "$s/lib/libclang.so.21.0.0")" = "$tc/lib/libclang.so.21.0.0"
check "lib/clang is the toolchain's" test "$(readlink "$s/lib/clang")" = "$tc/lib/clang"
check "usr/share is the toolchain's" test "$(readlink "$s/share")" = "$tc/share"
check "the Python package dir is a real dir" test -d "$s/$py/lldb" -a ! -L "$s/$py/lldb"
check "its other files link to the toolchain" test "$(readlink "$s/$py/lldb/__init__.py")" = "$tc/$py/lldb/__init__.py"
check "siblings on the way link to the toolchain" test "$(readlink "$s/$py/six.py")" = "$tc/$py/six.py"
check "_lldb.so resolves to the shadow liblldb" \
  test "$(readlink -f "$s/$py/lldb/_lldb.cpython-313-aarch64-linux-gnu.so")" = "$s/lib/liblldb.so.21.0.0"
check "the shadow lldb runs" test "$("$lldb")" = "stub lldb"
check "no build dirs left behind" test -z "$(find "$w/cache/omarchy-apple-dev/lldb-ios" -maxdepth 1 -name '.build.*' -o -maxdepth 1 -name '.old.*')"

touch "$s/marker"
out2=$(run) || bad "second run" "exit $?"
check "same output on re-run" test "$out2" = "$out"
check "current tree is reused" test -e "$s/marker"

# A build that stopped before writing its stamp is not reused.
rm "$(dirname "$s")/.stamp"
run >/dev/null || bad "run after a lost stamp" "exit $?"
check "rebuilt without a stamp" test ! -e "$s/marker"

# A toolchain update replaces liblldb (new size): rebuilt, new file in place.
touch "$s/marker"
rm "$tc/lib/liblldb.so.21.0.0"
echo lldb-v2-longer >"$tc/lib/liblldb.so.21.0.0"
out3=$(run) || bad "run after update" "exit $?"
check "rebuilt after a toolchain update" test ! -e "$s/marker"
check "new liblldb in place" test "$s/lib/liblldb.so.21.0.0" -ef "$tc/lib/liblldb.so.21.0.0"
check "same paths after rebuild" test "$out3" = "$out"

# Another SDK bundle (other XDG_CONFIG_HOME): rebuilt against it.
touch "$s/marker"
sdk_bundle "$w/config2"
CFG=$w/config2 run >/dev/null || bad "run with another SDK" "exit $?"
check "rebuilt for another SDK" test ! -e "$s/marker"
check "lib/swift follows the other SDK" test "$(readlink "$s/lib/swift/iphoneos")" = \
  "$w/config2/swiftpm/swift-sdks/darwin.artifactbundle/Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/swift/iphoneos"

# Copy mode (a cache on another filesystem): real copies, reused while current, and Python
# still reaches the shadow's liblldb rather than mapping the toolchain's as well.
cp_out=$(LLDB_IOS_SHADOW_COPY=1 run) || bad "copy mode" "exit $?"
check "copy mode: liblldb is a separate file" test ! "$s/lib/liblldb.so.21.0.0" -ef "$tc/lib/liblldb.so.21.0.0"
check "copy mode: same content" cmp -s "$s/lib/liblldb.so.21.0.0" "$tc/lib/liblldb.so.21.0.0"
check "copy mode: _lldb.so resolves to the shadow copy" \
  test "$(readlink -f "$s/$py/lldb/_lldb.cpython-313-aarch64-linux-gnu.so")" = "$s/lib/liblldb.so.21.0.0"
touch "$s/marker"
LLDB_IOS_SHADOW_COPY=1 run >/dev/null || bad "copy mode re-run" "exit $?"
check "copy mode: reused on re-run" test -e "$s/marker"
check "copy mode: same output" test "$cp_out" = "$out"

# Concurrent runs on a cold cache all succeed and agree.
rm -rf "$w/cache"
for i in 1 2 3 4 5 6 7 8; do (run >"$w/par.$i" 2>&1; echo $? >"$w/par.$i.rc") & done
wait
rcs=$(cat "$w"/par.?.rc | sort -u | tr '\n' ' ')
check "8 concurrent runs exit 0" test "$rcs" = "0 "
check "8 concurrent runs print the same" test "$(cat "$w"/par.? | sort -u | wc -l)" = 2

rm -rf "$sdk"
if msg=$(run 2>&1); then
  bad "fails without the iPhoneOS SDK" "exit 0"
else
  check "names the missing SDK" grep -q "no iPhoneOS SDK at $sdk" <<<"$msg"
fi

exit "$fail"
