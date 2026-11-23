#!/usr/bin/env bash
# Prints two lines: an lldb that evaluates Swift expressions (expression, p, po) for an iOS
# app, and the iPhoneOS.sdk path for `settings set target.sdk-path`. device-run.sh --lldb uses
# both. Creates or refreshes the shadow toolchain the lldb runs from; safe to re-run.
#
# Why: for an iOS target, Linux LLDB looks for an Xcode Swift resource dir, finds none
# ("Error while searching for SDK: HostInfoError"), and falls back to its own Linux
# usr/lib/swift. That dir's CoreFoundation module shadows the SDK's, so every Swift expression
# fails with "missing required module 'SwiftShims'" or "malformed or corrupted precompiled
# file". LLDB takes the resource dir from <dir of liblldb.so>/swift and offers no setting for
# it, so the shadow toolchain puts the darwin SDK's resource dir there:
#   usr/bin/lldb            hard link to the toolchain's lldb (its RUNPATH is $ORIGIN/../lib)
#   usr/lib/liblldb.so.*    hard link to the toolchain's liblldb. Same inode, so LLDB's Python
#                           module, which links the real path, does not load a second copy.
#   usr/lib/swift/          the entries of the SDK's XcodeDefault.xctoolchain/usr/lib/swift
#                           (what xtool builds the app against), plus linux/ and host/ from
#                           the toolchain, which liblldb loads its own libraries from
#   everything else         symlinks to the toolchain
# The toolchain is the one the swift on PATH resolves to. The tree lives in
# ${XDG_CACHE_HOME:-~/.cache}/omarchy-apple-dev/lldb-ios/<hash of the toolchain path>/ and is
# rebuilt when its hard links no longer match the toolchain (an update replaced the files).
set -euo pipefail

command -v swift >/dev/null || { echo "lldb-ios-shadow: no swift on PATH" >&2; exit 1; }
real=$(dirname "$(dirname "$(readlink -f "$(command -v swift)")")") # the toolchain's usr
# Where install-toolchain.sh registers the SDK (SwiftPM's location for Swift SDKs).
bundle="${XDG_CONFIG_HOME:+$XDG_CONFIG_HOME/swiftpm}"
bundle="${bundle:-$HOME/.swiftpm}/swift-sdks/darwin.artifactbundle"
darwin_rd="$bundle/Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/swift"
ios_sdk="$bundle/Developer/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS.sdk"
[ -d "$darwin_rd" ] || { echo "lldb-ios-shadow: no SDK resource dir at $darwin_rd" >&2; exit 1; }
[ -d "$ios_sdk" ] || { echo "lldb-ios-shadow: no iPhoneOS SDK at $ios_sdk" >&2; exit 1; }
[ -x "$real/bin/lldb" ] || { echo "lldb-ios-shadow: no lldb in $real/bin" >&2; exit 1; }
lib=$(cd "$real/lib" && ls liblldb.so.*.*.* 2>/dev/null | head -n1) || true
[ -n "$lib" ] || { echo "lldb-ios-shadow: no liblldb.so.X.Y.Z in $real/lib" >&2; exit 1; }

key=$(printf '%s' "$real" | sha256sum | cut -c1-12)
shadow="${XDG_CACHE_HOME:-$HOME/.cache}/omarchy-apple-dev/lldb-ios/$key"

if [ -x "$shadow/usr/bin/lldb" ] && [ "$shadow/usr/bin/lldb" -ef "$real/bin/lldb" ] &&
  [ "$shadow/usr/lib/$lib" -ef "$real/lib/$lib" ] && [ -e "$shadow/usr/lib/swift/iphoneos" ]; then
  printf '%s\n%s\n' "$shadow/usr/bin/lldb" "$ios_sdk"
  exit 0
fi

rm -rf -- "$shadow"
mkdir -p "$shadow/usr/bin" "$shadow/usr/lib/swift"
# A hard link needs the cache and the toolchain on one filesystem. A copy works as well (liblldb
# is about 230 MB); LLDB's Python module then maps a second copy of liblldb.
ln "$real/bin/lldb" "$shadow/usr/bin/lldb" 2>/dev/null || cp "$real/bin/lldb" "$shadow/usr/bin/lldb"
ln "$real/lib/$lib" "$shadow/usr/lib/$lib" 2>/dev/null || cp "$real/lib/$lib" "$shadow/usr/lib/$lib"
mid=${lib%.*} # liblldb.so.21.0.0 -> liblldb.so.21.0 -> liblldb.so, all inside the shadow
ln -s "$lib" "$shadow/usr/lib/$mid"
ln -s "$mid" "$shadow/usr/lib/liblldb.so"
for e in "$real"/lib/*; do
  n=${e##*/}
  case $n in swift | liblldb.so*) ;; *) ln -s "$e" "$shadow/usr/lib/$n" ;; esac
done
for e in "$darwin_rd"/*; do
  n=${e##*/}
  case $n in host | linux) ;; *) ln -s "$e" "$shadow/usr/lib/swift/$n" ;; esac
done
ln -s "$real/lib/swift/linux" "$shadow/usr/lib/swift/linux"
ln -s "$real/lib/swift/host" "$shadow/usr/lib/swift/host"
for n in local share include libexec; do
  if [ -e "$real/$n" ]; then ln -s "$real/$n" "$shadow/usr/$n"; fi
done
printf '%s\n%s\n' "$shadow/usr/bin/lldb" "$ios_sdk"
