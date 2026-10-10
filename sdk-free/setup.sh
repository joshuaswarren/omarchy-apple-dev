#!/usr/bin/env bash
# Mode "no Xcode download": build the link-and-header sysroot without Xcode.xip anywhere.
#
#   sdk-free/setup.sh          phone source (default when an iPhone is connected): needs it unlocked, paired,
#                              Developer Mode on (sudo for the USB tunnel)
#   sdk-free/setup.sh --ipsw   no phone: pull the shared cache from Apple's public iOS update download instead
#                              (--ipsw[=auto|<build>], --build <build>, --device <model>; env SDKFREE_IPSW, SDKFREE_DEVICE).
#                              Downloads only the cache (several GB) into $SDKFREE_HOME/cache and deletes it once the
#                              stubs are cut. A phone is then only needed to run the apps.
#
# Result under $SDKFREE_HOME (default ~/.local/share/omarchy-apple-dev/sdk-free):
#   iPhoneOS.sdk/   link stubs (.tbd) cut from the shared cache (iPhone or public IPSW), public Objective-C runtime
#                   headers, and the headers this repo ships in sdk-free/headers
#   toolset/        ld64.lld and dsymutil (xtool-org/darwin-tools-linux-llvm, pinned)
#   bin/actool      asset catalog compiler (built from tools/darwin-tools)
# Safe to re-run: finished pieces are skipped.
#
# Test and CI hooks: SDKFREE_TBD_DIR=<dir with ready-made .tbd files> skips the cache entirely; SDKFREE_DSC_DIR=<dir
# with an unpacked dyld_shared_cache_arm64e> skips the download but still cuts the stubs; SDKFREE_ACTOOL=<path> skips
# the actool build.
set -euo pipefail

HERE=$(dirname "$(readlink -f "$0")")
REPO=$(dirname "$HERE")
SDKFREE_HOME=${SDKFREE_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/omarchy-apple-dev/sdk-free}
SR=$SDKFREE_HOME/iPhoneOS.sdk
VENV=${VENV:-$HOME/pymobile3-venv}
PMD3=$VENV/bin/pymobiledevice3
IPSW=$HOME/.local/bin/ipsw
IPSW_SRC=${SDKFREE_IPSW:-}
DEVICE=${SDKFREE_DEVICE:-iPhone16,2}
while [ $# -gt 0 ]; do
  case "$1" in
    --ipsw) IPSW_SRC=auto; shift ;;
    --ipsw=*) IPSW_SRC=${1#--ipsw=}; shift ;;
    --build) IPSW_SRC=${2:?--build needs a build id like 24A446}; shift 2 ;;
    --device) DEVICE=${2:?--device needs a model like iPhone16,2}; shift 2 ;;
    *) echo "unknown option '$1': use --ipsw, --ipsw=<build>, --build <build> or --device <model>" >&2; exit 1 ;;
  esac
done
mkdir -p "$SDKFREE_HOME"

# Images whose link stubs the sysroot carries (install name -> stub file).
IMAGES="/usr/lib/libSystem.B.dylib /usr/lib/libobjc.A.dylib /usr/lib/libc++.1.dylib /usr/lib/libc++abi.dylib
/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation
/System/Library/Frameworks/Foundation.framework/Foundation
/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics
/System/Library/Frameworks/QuartzCore.framework/QuartzCore
/System/Library/Frameworks/UIKit.framework/UIKit
/System/Library/Frameworks/UIKitCore.framework/UIKitCore
/System/Library/Frameworks/SwiftUI.framework/SwiftUI /System/Library/Frameworks/SwiftUICore.framework/SwiftUICore
/System/Library/Frameworks/Combine.framework/Combine /System/Library/Frameworks/CoreTransferable.framework/CoreTransferable
/System/Library/Frameworks/DeveloperToolsSupport.framework/DeveloperToolsSupport
/usr/lib/swift/libswiftCore.dylib /usr/lib/swift/libswiftSwiftOnoneSupport.dylib /usr/lib/swift/libswift_Concurrency.dylib
/usr/lib/swift/libswift_StringProcessing.dylib /usr/lib/swift/libswift_RegexParser.dylib /usr/lib/swift/libswiftDarwin.dylib
/usr/lib/swift/libswiftObjectiveC.dylib /usr/lib/swift/libswiftDispatch.dylib /usr/lib/swift/libswiftCoreFoundation.dylib
/usr/lib/swift/libswiftFoundation.dylib /usr/lib/swift/libswiftCoreGraphics.dylib /usr/lib/swift/libswiftUIKit.dylib
/usr/lib/swift/libswiftQuartzCore.dylib"

echo "== 1. linker toolset (ld64.lld, dsymutil)"
TOOLSET_VERSION=v1.1.0
case "$(uname -m)" in
  x86_64) ts_arch=x86_64 ts_sha=a5166f2d56ac45707e5ef2f3c20a41a94af8ef0c0456354224dd08656e874188 ;;
  aarch64) ts_arch=aarch64 ts_sha=a6fc628a1db47ff6f209d32e66aec72eb77112d3f0b1ac1fcf5f6af7f34a9d08 ;;
  *) echo "unsupported architecture $(uname -m)" >&2; exit 1 ;;
esac
if [ ! -x "$SDKFREE_HOME/toolset/ld64.lld" ]; then
  tmp=$(mktemp -d)
  curl -fsSL "https://github.com/xtool-org/darwin-tools-linux-llvm/releases/download/$TOOLSET_VERSION/toolset-$ts_arch.tar.gz" \
    -o "$tmp/toolset.tar.gz"
  echo "$ts_sha  $tmp/toolset.tar.gz" | sha256sum -c --quiet
  tar -xzf "$tmp/toolset.tar.gz" -C "$tmp"
  mkdir -p "$SDKFREE_HOME/toolset"
  install -m755 "$tmp"/bin/ld64.lld "$tmp"/bin/dsymutil "$SDKFREE_HOME/toolset/"
fi
echo "toolset in $SDKFREE_HOME/toolset"

echo "== 2. Objective-C runtime headers (public source, pinned commit)"
OBJC4_REPO=https://github.com/apple-oss-distributions/objc4
OBJC4_SHA=fb265098298302243cd7eeaa1f63f0ba7786dd9a
OBJC4=$HOME/.cache/omarchy-apple-dev/objc4-$OBJC4_SHA
if [ ! -d "$OBJC4/.git" ]; then
  git init -q "$OBJC4"
  git -C "$OBJC4" fetch -q --depth 1 "$OBJC4_REPO" "$OBJC4_SHA"
  git -C "$OBJC4" checkout -q FETCH_HEAD
fi

echo "== 3. link stubs (phone or public IPSW)"
tbd=$SDKFREE_HOME/cache/tbd
if [ -n "${SDKFREE_TBD_DIR:-}" ]; then
  tbd=$SDKFREE_TBD_DIR
elif [ ! -f "$tbd/UIKit.tbd" ]; then
  [ -x "$IPSW" ] || { echo "ipsw is missing: run ./install-toolchain.sh first" >&2; exit 1; }
  dsc=$SDKFREE_HOME/cache/dsc
  dsc_tmp=${SDKFREE_TMP:-$SDKFREE_HOME/cache/tmp}
  if [ -n "${SDKFREE_DSC_DIR:-}" ]; then dsc=$SDKFREE_DSC_DIR; fi
  cache=$(find "$dsc" -name dyld_shared_cache_arm64e -print -quit 2>/dev/null || true)
  cleanup=
  if [ -n "$IPSW_SRC" ]; then
    # The build also decides the iOS version recorded in the sysroot's SystemVersion.plist.
    ver=
    if [ "$IPSW_SRC" = auto ]; then
      ver=$("$IPSW" download ipsw --device "$DEVICE" --latest --show-latest-version)
      build=$("$IPSW" download ipsw --device "$DEVICE" --latest --show-latest-build)
    else
      build=$IPSW_SRC
    fi
    url=$("$IPSW" download ipsw --device "$DEVICE" --build "$build" --urls | grep -o 'https://[^[:space:]]*Restore\.ipsw' | head -n1)
    [ -n "$url" ] || { echo "no IPSW found for $DEVICE build $build" >&2; exit 1; }
    if [ -z "$ver" ]; then
      ver=$(printf '%s\n' "$url" | sed -nE "s#.*/${DEVICE}_([^/]*)_${build}_Restore\\.ipsw#\\1#p")
      [ -n "$ver" ] || { echo "cannot read the iOS version for build $build from $url" >&2; exit 1; }
    fi
    mkdir -p "$SDKFREE_HOME/cache"
    printf '{"ProductVersion":"%s","BuildVersion":"%s"}\n' "$ver" "$build" >"$SDKFREE_HOME/cache/device-info.json"
  fi
  if [ -z "$cache" ]; then
    if [ -n "$IPSW_SRC" ] || ! "$PMD3" lockdown info >/dev/null 2>&1; then
      # No usable phone: the shared cache comes from Apple's public iOS update download instead.
      if [ -z "$IPSW_SRC" ]; then
        build=$("$IPSW" download ipsw --device "$DEVICE" --latest --show-latest-build)
        url=$("$IPSW" download ipsw --device "$DEVICE" --build "$build" --urls | grep -o 'https://[^[:space:]]*Restore\.ipsw' | head -n1)
        [ -n "$url" ] || { echo "no IPSW found for $DEVICE build $build" >&2; exit 1; }
        ver=$(printf '%s\n' "$url" | sed -nE "s#.*/${DEVICE}_([^/]*)_${build}_Restore\\.ipsw#\\1#p")
        [ -n "$ver" ] || { echo "cannot read the iOS version for build $build from $url" >&2; exit 1; }
        mkdir -p "$SDKFREE_HOME/cache"
        printf '{"ProductVersion":"%s","BuildVersion":"%s"}\n' "$ver" "$build" >"$SDKFREE_HOME/cache/device-info.json"
      fi
      fuse=${IPSW_APFS_FUSE_PATH:-$SDKFREE_HOME/bin/apfs-fuse}
      if [ ! -x "$fuse" ]; then
        fuse=$SDKFREE_HOME/bin/apfs-fuse
        # ipsw mounts the iOS update's system image with apfs-fuse to pull the cache out.
        if ! command -v cmake >/dev/null 2>&1 || ! command -v git >/dev/null 2>&1 || ! command -v cc >/dev/null 2>&1 ||
          ! echo '#include <fuse3/fuse.h>' | cc -E - >/dev/null 2>&1; then
          echo "apfs-fuse is missing and cannot be built: install the fuse3 headers, cmake, a C/C++ compiler, bzip2 and zlib (docs/DISTROS.md lists the package names per distribution)" >&2
          exit 1
        fi
        APFS_PIN=66b86bd525e8cb90f9012543be89b1f092b75cf3
        APFS_DIR=$HOME/.cache/omarchy-apple-dev/apfs-fuse-$APFS_PIN
        if [ ! -d "$APFS_DIR/.git" ]; then
          git init -q "$APFS_DIR"
          git -C "$APFS_DIR" fetch -q --depth 1 https://github.com/sgan81/apfs-fuse "$APFS_PIN"
          git -C "$APFS_DIR" checkout -q FETCH_HEAD
          git -C "$APFS_DIR" submodule update -q --init --recursive
        fi
        echo "Building apfs-fuse (ipsw uses it to read the iOS update)"
        # Newer GCC and libstdc++ no longer leak uint32_t into every translation unit.
        cmake -S "$APFS_DIR" -B "$APFS_DIR/build" -DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DCMAKE_CXX_FLAGS="-include cstdint" >/dev/null
        cmake --build "$APFS_DIR/build" -j >/dev/null
        mkdir -p "$SDKFREE_HOME/bin"
        install -m755 "$APFS_DIR/build/apfs-fuse" "$fuse"
      fi
      echo "Downloading the shared cache of $DEVICE iOS ${ver:-?} ($build) from Apple (several GB, once; it is deleted after the stubs are cut)"
      rm -rf "$dsc_tmp"
      mkdir -p "$dsc_tmp"
      # TMPDIR keeps ipsw's partial download off /tmp.
      TMPDIR=$dsc_tmp IPSW_APFS_FUSE_PATH=$fuse "$IPSW" extract --dyld --dyld-arch arm64e --remote "$url" -o "$dsc"
      cleanup=1
    else
      echo "Copying the shared cache from the iPhone (about 7 GB, once; it is deleted after the stubs are cut)"
      log=$(mktemp)
      sudo "$PMD3" lockdown start-tunnel >"$log" 2>&1 &
      trap 'sudo pkill -f "lockdown start-tunne[l]" || true' EXIT
      for _ in $(seq 30); do grep -q "RSD Port" "$log" && break; sleep 1; done
      host=$(grep -o "RSD Address: [^ ]*" "$log" | awk '{print $3}')
      port=$(grep -o "RSD Port: [0-9]*" "$log" | awk '{print $3}')
      [ -n "$port" ] || { cat "$log" >&2; exit 1; }
      "$PMD3" developer fetch-symbols download "$dsc" --rsd "$host" "$port"
      printf '%s\n' "$("$PMD3" lockdown info)" >"$SDKFREE_HOME/cache/device-info.json"
    fi
  fi
  cache=$(find "$dsc" -name dyld_shared_cache_arm64e -print -quit)
  mkdir -p "$tbd"
  for image in $IMAGES; do
    # iOS 27 folds UIKitCore into the UIKit stub, and Swift overlay libraries differ by release: only the
    # C/Objective-C images are required
    "$IPSW" dyld tbd "$cache" "$image" -o "$tbd" >/dev/null 2>&1 || {
      case "$image" in */UIKitCore | /usr/lib/swift/* | */SwiftUI | */SwiftUICore | */Combine | */CoreTransferable | */DeveloperToolsSupport) echo "note: $image is not in this cache" ;; *) echo "failed: $image" >&2; exit 1 ;; esac
    }
  done
  echo "stubs written to $tbd"
  if [ -n "$cleanup" ] && [ "$dsc" = "$SDKFREE_HOME/cache/dsc" ]; then
    rm -rf "$SDKFREE_HOME/cache/dsc" "$dsc_tmp"
  fi
fi

echo "== 4. assemble the sysroot"
mkdir -p "$SR/usr/include/objc" "$SR/usr/lib" "$SR/System/Library/Frameworks"
for h in objc.h objc-api.h NSObject.h NSObjCRuntime.h runtime.h message.h Protocol.h; do
  cp "$OBJC4/runtime/$h" "$SR/usr/include/objc/"
done
cp "$OBJC4/APPLE_LICENSE" "$SR/usr/include/objc/APPLE_LICENSE"
# ipsw writes arm64e stubs; third-party apps are arm64, which exports the same names.
cut_stub() { sed 's/\[ arm64e-ios \]/[ arm64-ios, arm64e-ios ]/g' "$1" >"$2"; }
cut_stub "$tbd/libSystem.B.dylib.tbd" "$SR/usr/lib/libSystem.tbd"
cut_stub "$tbd/libobjc.A.dylib.tbd" "$SR/usr/lib/libobjc.tbd"
cut_stub "$tbd/libc++.1.dylib.tbd" "$SR/usr/lib/libc++.tbd"
cut_stub "$tbd/libc++abi.dylib.tbd" "$SR/usr/lib/libc++abi.tbd"
for f in UIKit UIKitCore Foundation CoreFoundation CoreGraphics QuartzCore SwiftUI SwiftUICore Combine CoreTransferable DeveloperToolsSupport; do
  [ -f "$tbd/$f.tbd" ] || continue
  mkdir -p "$SR/System/Library/Frameworks/$f.framework"
  cut_stub "$tbd/$f.tbd" "$SR/System/Library/Frameworks/$f.framework/$f.tbd"
done
# Swift runtime stubs (libswiftCore and the overlay libraries the connected iPhone has)
mkdir -p "$SR/usr/lib/swift"
for f in "$tbd"/libswift*.dylib.tbd; do
  [ -f "$f" ] || continue
  name=$(basename "$f" .dylib.tbd)
  cut_stub "$f" "$SR/usr/lib/swift/$name.tbd"
done
cp -R "$HERE/headers/." "$SR/"
# Flutter reads the platform and build from the SDK directory
if [ -f "$SDKFREE_HOME/cache/device-info.json" ]; then
  python3 - "$SDKFREE_HOME/cache/device-info.json" "$SR/System/Library/CoreServices/SystemVersion.plist" <<'PY'
import json, plistlib, sys
info = json.load(open(sys.argv[1]))
plist = {"ProductName": "iPhone OS", "ProductVersion": info["ProductVersion"], "ProductBuildVersion": info["BuildVersion"]}
with open(sys.argv[2], "wb") as f:
    plistlib.dump(plist, f)
PY
fi
echo "sysroot: $SR ($(du -sh "$SR" | cut -f1))"

echo "== 5. asset catalog compiler"
mkdir -p "$SDKFREE_HOME/bin"
if [ -n "${SDKFREE_ACTOOL:-}" ]; then
  install -m755 "$SDKFREE_ACTOOL" "$SDKFREE_HOME/bin/actool"
elif [ ! -x "$SDKFREE_HOME/bin/actool" ]; then
  command -v swift >/dev/null || { echo "swift is not on PATH: run ./install-toolchain.sh first" >&2; exit 1; }
  (cd "$REPO/tools/darwin-tools" && swift build -c release --product actool >/dev/null)
  install -m755 "$REPO/tools/darwin-tools/.build/release/actool" "$SDKFREE_HOME/bin/actool"
fi
echo "Done. Build a Flutter app with: $HERE/flutter-build.sh <flutter app dir>"
