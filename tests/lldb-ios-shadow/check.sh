#!/usr/bin/env bash
# Checks tools/lldb-ios-shadow.sh against a stub toolchain and a stub darwin SDK bundle: the
# shadow layout (iOS resource dir in lib/swift, the toolchain's linux/ and host/ kept, its
# CoreFoundation left out), hard links sharing inodes, reuse while current, rebuild after a
# toolchain update, and a clear failure without the SDK. No Swift, no device.
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
mkdir -p "$tc/bin" "$tc/lib/swift/linux" "$tc/lib/swift/host/compiler" \
  "$tc/lib/swift/CoreFoundation" "$tc/lib/clang/21" "$tc/local/lib64"
printf '#!/bin/sh\necho stub swift\n' >"$tc/bin/swift"
printf '#!/bin/sh\necho stub lldb\n' >"$tc/bin/lldb"
chmod +x "$tc/bin/swift" "$tc/bin/lldb"
echo lldb-v1 >"$tc/lib/liblldb.so.21.0.0"
ln -s liblldb.so.21.0.0 "$tc/lib/liblldb.so.21.0"
ln -s liblldb.so.21.0 "$tc/lib/liblldb.so"
echo clang >"$tc/lib/libclang.so.21.0.0"
touch "$tc/lib/swift/CoreFoundation/module.modulemap"
# swift on PATH is a symlink, as mise and the AUR package install it
mkdir -p "$w/path"
ln -s "$tc/bin/swift" "$w/path/swift"

cfg=$w/config
b=$cfg/swiftpm/swift-sdks/darwin.artifactbundle
rd=$b/Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/swift
sdk=$b/Developer/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS.sdk
mkdir -p "$rd/iphoneos" "$rd/clang" "$rd/host" "$rd/apinotes" "$sdk/usr/lib/swift/shims"

run() { PATH="$w/path:/usr/bin:/bin" XDG_CONFIG_HOME="$cfg" XDG_CACHE_HOME="$w/cache" HOME="$w/home" "$script"; }

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
check "usr/local is the toolchain's" test "$(readlink "$s/local")" = "$tc/local"
check "the shadow lldb runs" test "$("$lldb")" = "stub lldb"

touch "$s/marker"
out2=$(run) || bad "second run" "exit $?"
check "same output on re-run" test "$out2" = "$out"
check "current tree is reused" test -e "$s/marker"

# A toolchain update replaces liblldb with a new file (new inode): the tree is rebuilt.
rm "$tc/lib/liblldb.so.21.0.0"
echo lldb-v2 >"$tc/lib/liblldb.so.21.0.0"
out3=$(run) || bad "run after update" "exit $?"
check "rebuilt after a toolchain update" test ! -e "$s/marker"
check "new liblldb hard-linked" test "$s/lib/liblldb.so.21.0.0" -ef "$tc/lib/liblldb.so.21.0.0"
check "same paths after rebuild" test "$out3" = "$out"

rm -rf "$sdk"
if msg=$(run 2>&1); then
  bad "fails without the iPhoneOS SDK" "exit 0"
else
  check "names the missing SDK" grep -q "no iPhoneOS SDK at $sdk" <<<"$msg"
fi

exit "$fail"
