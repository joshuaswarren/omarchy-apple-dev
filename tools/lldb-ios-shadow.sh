#!/usr/bin/env bash
# Prints two lines: an lldb that evaluates Swift expressions (expression, p, po) for an iOS
# app, and the iPhoneOS.sdk path for `settings set target.sdk-path`. device-run.sh --lldb uses
# both. Creates or refreshes the shadow toolchain the lldb runs from; safe to re-run, also
# concurrently.
#
# Why: for an iOS target, Linux LLDB looks for an Xcode Swift resource dir, finds none
# ("Error while searching for SDK: HostInfoError"), and falls back to its own Linux
# usr/lib/swift. That dir's CoreFoundation module shadows the SDK's, so every Swift expression
# fails with "missing required module 'SwiftShims'" or "malformed or corrupted precompiled
# file". LLDB takes the resource dir from <dir of liblldb.so>/swift, after resolving symlinks,
# and offers no setting for it. So the shadow toolchain holds a real liblldb file:
#   usr/bin/lldb            the toolchain's lldb (its RUNPATH is $ORIGIN/../lib)
#   usr/lib/liblldb.so.*    the toolchain's liblldb
#   usr/lib/swift/          the entries of the SDK's XcodeDefault.xctoolchain/usr/lib/swift
#                           (what xtool builds the app against), plus linux/ and host/ from
#                           the toolchain, which liblldb loads its own libraries from
#   .../site-packages/lldb/ LLDB's Python package, its _lldb.so re-pointed at the shadow
#                           liblldb, so Python does not map the toolchain's copy a second time
#   everything else         symlinks to the toolchain
# lldb and liblldb are hard links when the cache and the toolchain share a filesystem, else
# copies (about 230 MB; LLDB_IOS_SHADOW_COPY=1 forces copies). The toolchain is the one the
# swift on PATH resolves to. The tree lives in
# ${XDG_CACHE_HOME:-~/.cache}/omarchy-apple-dev/lldb-ios/<hash of the toolchain path>/. A stamp
# written last records what it was built from; any difference (toolchain update, other SDK,
# interrupted build) rebuilds it in a temp dir that then replaces it.
set -euo pipefail
STAMP_VERSION=1

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
# LLDB's Python package (site-packages or dist-packages), relative to the toolchain's usr: the
# one whose _lldb*.so is this liblldb. None found: no mirror (Python then maps the toolchain's
# liblldb, which only matters for a copy).
pkg=
real_lib=$(readlink -f "$real/lib/$lib")
while IFS= read -r init; do
  d=${init%/__init__.py}
  for so in "$real/$d"/_lldb*.so; do
    if [ "$(readlink -f "$so")" = "$real_lib" ]; then pkg=$d; break 2; fi
  done
done < <(cd "$real" && find . -maxdepth 6 -path ./lib/swift -prune -o \
  -path '*-packages/lldb/__init__.py' -print 2>/dev/null | sed 's|^\./||' | sort)

cache="${XDG_CACHE_HOME:-$HOME/.cache}/omarchy-apple-dev/lldb-ios"
key=$(printf '%s' "$real" | sha256sum | cut -c1-12)
shadow="$cache/$key"
stamp=$(printf '%s\n' "version $STAMP_VERSION" "toolchain $real" "resources $darwin_rd" \
  "python ${pkg:-none}" "copy ${LLDB_IOS_SHADOW_COPY:-0}" \
  "lldb $(stat -L -c '%s %Y' "$real/bin/lldb")" "$lib $(stat -L -c '%s %Y' "$real/lib/$lib")")

current() { [ -f "$shadow/.stamp" ] && [ "$(cat "$shadow/.stamp")" = "$stamp" ]; }
emit() { printf '%s\n%s\n' "$shadow/usr/bin/lldb" "$ios_sdk"; }

current && { emit; exit 0; }

mkdir -p "$cache"
# One builder at a time; a waiting run rechecks and reuses what the first one built.
if command -v flock >/dev/null; then
  exec 9>"$cache/.lock"
  flock 9
  current && { emit; exit 0; }
  # Holding the lock, no other build is running: clear what killed builds left behind.
  rm -rf -- "$cache"/.build.* "$cache"/.old.*
fi

tmp=$(mktemp -d "$cache/.build.XXXXXX")
trap 'rm -rf -- "$tmp"' EXIT
u=$tmp/usr
mkdir -p "$u/bin" "$u/lib/swift"
place() { # SRC DST: a hard link, or a copy across filesystems (or when forced)
  if [ "${LLDB_IOS_SHADOW_COPY:-0}" != 1 ] && ln "$1" "$2" 2>/dev/null; then return; fi
  cp -p "$1" "$2"
}
place "$real/bin/lldb" "$u/bin/lldb"
place "$real/lib/$lib" "$u/lib/$lib"
mid=${lib%.*} # liblldb.so.21.0.0 -> liblldb.so.21.0 -> liblldb.so, all inside the shadow
ln -s "$lib" "$u/lib/$mid"
ln -s "$mid" "$u/lib/liblldb.so"
for e in "$real"/lib/*; do
  n=${e##*/}
  case $n in swift | liblldb.so*) ;; *) ln -s "$e" "$u/lib/$n" ;; esac
done
for e in "$darwin_rd"/*; do
  n=${e##*/}
  case $n in host | linux) ;; *) ln -s "$e" "$u/lib/swift/$n" ;; esac
done
ln -s "$real/lib/swift/linux" "$u/lib/swift/linux"
ln -s "$real/lib/swift/host" "$u/lib/swift/host"

# Everything else at the top of usr links to the toolchain, except the directories on the way
# to the Python package: those are real directories whose other entries link to the toolchain.
mirror() { # REL: make $u/REL a directory mirroring $real/REL with symlinks
  local e n
  mkdir -p "$u/$1"
  for e in "$real/$1"/* "$real/$1"/.[!.]*; do
    [ -e "$e" ] || [ -L "$e" ] || continue
    n=${e##*/}
    [ -e "$u/$1/$n" ] || [ -L "$u/$1/$n" ] || ln -s "$e" "$u/$1/$n"
  done
}
if [ -n "$pkg" ]; then
  path=
  IFS=/ read -ra parts <<<"$pkg"
  for part in "${parts[@]}"; do
    path=${path:+$path/}$part
    [ -L "$u/$path" ] && rm "$u/$path" # created as a symlink one level up: replace it
    mirror "$path"
  done
  # _lldb*.so links to liblldb by a relative path: recreate it inside the shadow.
  for so in "$real/$pkg"/_lldb*.so; do
    [ -L "$so" ] || continue
    rm -f "$u/$pkg/${so##*/}"
    ln -s "$(readlink "$so")" "$u/$pkg/${so##*/}"
  done
fi
for e in "$real"/*; do
  n=${e##*/}
  [ -e "$u/$n" ] || [ -L "$u/$n" ] || ln -s "$e" "$u/$n"
done

printf '%s\n' "$stamp" >"$tmp/.stamp"
# Replace the old tree. An lldb still running from it keeps its mapped files.
# Without flock another run may have replaced or moved it meanwhile: if this rename loses,
# use the winner's tree when it is current.
if [ -e "$shadow" ]; then
  old=$(mktemp -d "$cache/.old.XXXXXX")
  mv -T "$shadow" "$old/tree" 2>/dev/null || true
  rm -rf -- "$old"
fi
if ! mv -T "$tmp" "$shadow" 2>/dev/null; then
  for _ in $(seq 50); do
    current && { emit; exit 0; }
    sleep 0.1
  done
  echo "lldb-ios-shadow: could not put the tree in place at $shadow" >&2
  exit 1
fi
trap - EXIT
emit
