#!/usr/bin/env bash
# Link the iOS framework of a Kotlin Multiplatform project on Linux.
#   kmp/build-framework.sh [project dir] [--module :path] [--target ios_arm64|ios_simulator_arm64]
#                          [--out dir] [--dynamic] [--xcframework]
#
# Gradle never links an Apple framework on Linux: Kotlin/Native turns Apple
# targets down when the host is not a Mac, and the link task is skipped. The
# klibs build fine though, and the compiler itself can link them once it
# believes it runs on a Mac and finds the Apple parts it expects:
#   - the iOS runtime of Kotlin/Native, which only its macOS distribution
#     carries: taken from Maven Central (about 300 MB, once) and added to a
#     copy of the Linux one (hard links, in ~/.cache/omarchy-apple-dev/kmp);
#   - LLVM and libffi for the host: the Linux ones, public, downloaded by the
#     compiler into its own data directory;
#   - the linker of Xcode: the ld64.lld of the SDK's toolset, behind a wrapper
#     named ld (lld picks its mode from the name it is called by); and its
#     libtool, for a static framework: llvm-libtool-darwin, which the toolset
#     ships as llvm-lib;
#   - the iOS SDK and the clang runtime of the darwin SDK install-toolchain.sh
#     builds from the Xcode .xip.
# KONAN_USE_INTERNAL_SERVER makes the compiler read the toolchain and the SDK
# from its properties instead of asking xcrun; with it, it looks for Xcode
# parts on a JetBrains server that is not public, so they are declared already
# extracted in the data directory and nothing is fetched from there. The build
# is optimized and carries no debug info, whatever the project asks: the Linux
# LLVM asserts on the debug info of Apple targets.
#
# What the framework is made of (base name, exported modules, options,
# Compose resources) comes from the project itself, through the Gradle init
# script ios-kmp.init.gradle next to this one. The app around it: kmp/README.md.
#
# Each step checks its own result and returns non-zero on failure (|| return):
# the frameworks are linked in a `kmp_link ... || ...` list, where Bash turns
# errexit off for the whole call, so set -e alone would let a failed download
# or copy go on and report success.
set -euo pipefail

here=$(dirname "$(readlink -f "$0")")
KMP_INIT="${KMP_INIT:-$here/ios-kmp.init.gradle}"
KMP_CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/omarchy-apple-dev/kmp"
# SwiftPM keeps Swift SDKs under $XDG_CONFIG_HOME/swiftpm when that is set, else ~/.swiftpm (as ship.sh).
SDKS="${XDG_CONFIG_HOME:+$XDG_CONFIG_HOME/swiftpm/swift-sdks}"
SDKS="${SDKS:-$HOME/.swiftpm/swift-sdks}"
XCFRAMEWORK=false

log() { printf '\033[1m[kmp]\033[0m %s\n' "$*"; }
err() { echo "kmp: $*" >&2; }

kmp_usage() {
  cat <<'USAGE'
Usage: kmp/build-framework.sh [project dir] [--module :path] [--target ios_arm64|ios_simulator_arm64] [--out dir] [--dynamic] [--xcframework]

Links the iOS framework a Kotlin Multiplatform project declares
(binaries.framework), on Linux, from the klibs Gradle builds. The project
dir (the root of the Gradle build) defaults to the current one; --module
picks one project of the build (every one that declares a framework
otherwise); --target defaults to ios_arm64, a device; --out defaults to
<module>/build/omarchy-kmp/<target>; --dynamic links a dynamic framework
even when the project declares a static one: swift build loads every member
of a static archive (-all_load, from the toolset), which the static
framework of a Compose Multiplatform app does not survive (Skia objects
twice). --xcframework also wraps it as <Name>.xcframework, for a SwiftPM
binary target. Needs the SDK install-toolchain.sh builds and a JDK.
USAGE
}

# Gradle name of a Kotlin/Native target, and the platform of its SDK.
kmp_gradle_target() {
  case "$1" in
  ios_arm64) echo iosArm64 ;;
  ios_simulator_arm64) echo iosSimulatorArm64 ;;
  *) return 1 ;;
  esac
}

kmp_platform() {
  case "$1" in
  ios_arm64) echo iPhoneOS ;;
  ios_simulator_arm64) echo iPhoneSimulator ;;
  esac
}

# A copy of the Linux distribution with the iOS runtime of the macOS one.
# Built in a scratch directory and moved into the cache only once the
# download, the copy and the extraction succeeded and both iOS runtimes are
# there; a cached copy counts only with the mark written then.
kmp_distribution() {
  local version="$1" linux dist archive partial target url
  linux="$HOME/.konan/kotlin-native-prebuilt-linux-x86_64-$version"
  dist="$KMP_CACHE/kotlin-native-$version"
  if [ ! -d "$linux" ]; then
    err "Kotlin/Native $version is not in ~/.konan: Gradle downloads it on its first iOS build"
    return 1
  fi
  if [ -f "$dist/.omarchy-kmp-complete" ]; then
    echo "$dist"
    return 0
  fi
  log "Kotlin/Native $version: the iOS runtime of its macOS distribution, from Maven Central (about 300 MB, once)" >&2
  mkdir -p "$KMP_CACHE" || return 1
  archive="$KMP_CACHE/kotlin-native-macos-$version.tar.gz"
  partial="$KMP_CACHE/.kotlin-native-$version.partial"
  url="${KMP_MAVEN:-https://repo.maven.apache.org/maven2}/org/jetbrains/kotlin/kotlin-native-prebuilt/$version/kotlin-native-prebuilt-$version-macos-x86_64.tar.gz"
  rm -rf "$partial" "$archive" || return 1
  if ! curl -fL --progress-bar -o "$archive" "$url"; then
    rm -f "$archive"
    err "download failed: $url"
    return 1
  fi
  if ! cp -al "$linux" "$partial"; then
    rm -rf "$partial" "$archive"
    err "could not copy $linux into $KMP_CACHE"
    return 1
  fi
  if ! tar -xzf "$archive" --strip-components=1 -C "$partial" \
    "kotlin-native-prebuilt-macos-x86_64-$version/konan/targets/ios_arm64" \
    "kotlin-native-prebuilt-macos-x86_64-$version/konan/targets/ios_simulator_arm64"; then
    rm -rf "$partial" "$archive"
    err "the macOS distribution of Kotlin/Native $version could not be extracted (archive kept out of the cache)"
    return 1
  fi
  rm -f "$archive"
  for target in ios_arm64 ios_simulator_arm64; do
    if [ -z "$(ls -A "$partial/konan/targets/$target" 2>/dev/null)" ]; then
      rm -rf "$partial"
      err "the macOS distribution of Kotlin/Native $version has no $target runtime"
      return 1
    fi
  done
  touch "$partial/.omarchy-kmp-complete" || { rm -rf "$partial"; return 1; }
  rm -rf "$dist" && mv "$partial" "$dist" || { rm -rf "$partial"; return 1; }
  echo "$dist"
}

# The data directory of the compiler: the Apple parts declared extracted.
kmp_data() {
  local sdk="$1" bundle="$2" data toolchain dep
  toolchain="$KMP_CACHE/toolchain"
  mkdir -p "$toolchain/usr/bin" || return 1
  printf '#!/bin/sh\n# lld in its Mach-O mode (ld64): it picks the mode from the name it is called by\nexec %s "$@"\n' \
    "$bundle/toolset/bin/ld64.lld" >"$toolchain/usr/bin/ld" || return 1
  chmod +x "$toolchain/usr/bin/ld" || return 1
  # A static framework is archived by libtool: llvm-libtool-darwin, the llvm-lib of the toolset
  printf '#!/bin/sh\n# libtool of Xcode: llvm-libtool-darwin of the SDK toolset\nexec %s "$@"\n' \
    "$bundle/toolset/bin/llvm-lib" >"$toolchain/usr/bin/libtool" || return 1
  chmod +x "$toolchain/usr/bin/libtool" || return 1
  ln -sfn "$bundle/Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib" "$toolchain/usr/lib" || return 1
  data="$KMP_CACHE/data"
  mkdir -p "$data/dependencies" || return 1
  ln -sfn "$toolchain" "$data/dependencies/omarchy-kmp-toolchain" || return 1
  ln -sfn "$sdk" "$data/dependencies/omarchy-kmp-sdk" || return 1
  touch "$data/dependencies/.extracted" || return 1
  for dep in omarchy-kmp-toolchain omarchy-kmp-sdk; do
    grep -qx "$dep" "$data/dependencies/.extracted" || echo "$dep" >>"$data/dependencies/.extracted" || return 1
  done
  echo "$data"
}

# Links one framework. $1: the dump of omarchyKmpFrameworks for one project.
kmp_link() {
  local block="$1" target="$2" out="$3" dynamic="$4" version path build name static dist data sdk bundle props llvm ffi
  version="$(awk -F'\t' '$1 == "VERSION" { print $2 }' <<<"$block")"
  IFS=$'\t' read -r _ path build name static < <(grep $'^FRAMEWORK\t' <<<"$block") || {
    err "no FRAMEWORK line in the Gradle dump"
    return 1
  }
  out="${out:-$build/omarchy-kmp/$target}"
  bundle="$SDKS/darwin.artifactbundle"
  sdk="$(find "$bundle/Developer/Platforms/$(kmp_platform "$target").platform/Developer/SDKs" \
    -maxdepth 1 -name "$(kmp_platform "$target")[0-9]*.sdk" 2>/dev/null | sort -V | tail -n 1)"
  if [ -z "$sdk" ]; then
    err "no $(kmp_platform "$target") SDK in $bundle: install-toolchain.sh first"
    return 1
  fi
  dist="$(kmp_distribution "$version")" || return 1
  data="$(kmp_data "$sdk" "$bundle")" || { err "could not set up the compiler data in $KMP_CACHE"; return 1; }
  props="$dist/konan/konan.properties"
  llvm="$(sed -n 's/^llvm\.linux_x64\.user *= *//p' "$props")"
  ffi="$(sed -n 's/^libffiDir\.linux_x64 *= *//p' "$props")"
  local overrides="llvmHome.macos_x64=$llvm;libffiDir.macos_x64=$ffi;dependencies.macos_x64=$llvm $ffi"
  overrides+=";dependencies.macos_x64-$target=;targetToolchain.macos_x64-$target=omarchy-kmp-toolchain"
  overrides+=";additionalToolsDir.macos_x64=omarchy-kmp-toolchain;targetSysRoot.$target=omarchy-kmp-sdk"

  # An exported library is a library too: given once, whichever line names it first
  local args=() line kind value
  local -A given=()
  while IFS=$'\t' read -r kind value; do
    case "$kind" in
    INCLUDE | LIBRARY | EXPORT)
      [ -n "${given[$value]:-}" ] || args+=(-library "$value")
      given[$value]=1
      ;;
    esac
    case "$kind" in
    INCLUDE) args+=("-Xinclude=$value") ;;
    EXPORT) args+=("-Xexport-library=$value") ;;
    ARG) args+=("$value") ;;
    LINKER) args+=(-linker-option "$value") ;;
    esac
  done <<<"$block"
  [ "$static" = true ] && [ "$dynamic" != true ] && args+=(-Xstatic-framework)

  log "$path: $name.framework for $target (Kotlin/Native $version, $(basename "$sdk"), several minutes)"
  mkdir -p "$out" || return 1
  rm -rf "${out:?}/$name.framework" || return 1
  if ! KONAN_USE_INTERNAL_SERVER=1 "$dist/bin/kotlinc-native" "-Dos.name=Mac OS X" -Dos.arch=x86_64 \
    "-Xoverride-konan-properties=$overrides" "-Xkonan-data-dir=$data" -opt -Xadd-light-debug=disable \
    -produce framework -target "$target" -module-name "$name" -o "$out/$name" "${args[@]}" >"$out/kotlinc.log" 2>&1; then
    grep -v '^[[:space:]]*at ' "$out/kotlinc.log" | grep -iE 'error|exception' | head -n 20 >&2
    err "the link failed, the whole output is in $out/kotlinc.log"
    return 1
  fi
  line="$(awk -F'\t' '$1 == "RESOURCES" { print $2 }' <<<"$block")"
  if [ -n "$line" ]; then
    rm -rf "$out/compose-resources" || return 1
    if [ ! -d "$line" ] || ! cp -r "$line" "$out/compose-resources"; then
      rm -rf "$out/compose-resources"
      err "could not copy the Compose resources from $line"
      return 1
    fi
    log "Compose resources: $out/compose-resources, to copy into the .app as compose-resources/"
  fi
  log "framework: $out/$name.framework"
  [ "$XCFRAMEWORK" != true ] || kmp_xcframework "$out/$name.framework" "$target"
}

kmp_main() {
  local dir="." module="" target="ios_arm64" out="" dynamic=false gradle_target task dump block
  while [ "$#" -gt 0 ]; do
    case "$1" in
    --module) module="${2:?--module needs a project path, like :shared}"; shift 2 ;;
    --target) target="${2:?--target needs ios_arm64 or ios_simulator_arm64}"; shift 2 ;;
    --out) out="${2:?--out needs a directory}"; shift 2 ;;
    --dynamic) dynamic=true; shift ;;
    --xcframework) XCFRAMEWORK=true; shift ;;
    -h | --help) kmp_usage; return 0 ;;
    -*) err "unknown option $1"; kmp_usage >&2; return 2 ;;
    *) dir="$1"; shift ;;
    esac
  done
  gradle_target="$(kmp_gradle_target "$target")" || {
    err "unknown target $target: ios_arm64 or ios_simulator_arm64"
    return 2
  }
  [ -x "$dir/gradlew" ] || { err "$dir has no gradlew: give the root of a Gradle build"; return 1; }
  [ "$(uname -m)" = x86_64 ] || { err "linux x86_64 only, like the ios environment"; return 1; }
  if ! command -v java >/dev/null 2>&1; then
    err "Gradle needs a JDK on the PATH (java)"
    return 1
  fi
  dir="$(cd "$dir" && pwd)"
  task="${module:+$module:}omarchyKmpFrameworks"
  log "Gradle: the klibs of the iOS framework and what it exports ($gradle_target)"
  dump="$(cd "$dir" && ./gradlew -q --console=plain -I "$KMP_INIT" "-PomarchyKmpTarget=$gradle_target" "$task")" || {
    err "Gradle failed, see above"
    return 1
  }
  if ! grep -q $'^FRAMEWORK\t' <<<"$dump"; then
    err "no framework declared for $gradle_target${module:+ in $module} (kotlin { $gradle_target { binaries.framework { } } })"
    return 1
  fi
  # One file a framework, from its VERSION line to the next one
  local blocks status=0
  blocks="$(mktemp -d)"
  awk -v dir="$blocks" '/^VERSION\t/ { n++ } n { print > (dir "/" n) }' <<<"$dump"
  for block in "$blocks"/*; do
    kmp_link "$(cat "$block")" "$target" "$out" "$dynamic" || { status=1; break; }
  done
  rm -rf "$blocks"
  return "$status"
}

# <Name>.framework wrapped as <Name>.xcframework next to it, the layout a
# SwiftPM .binaryTarget(path:) takes, with the slice of its target: ios-arm64
# for a device, ios-arm64-simulator (platform variant simulator) for the
# simulator.
kmp_xcframework() {
  local framework="$1" target="${2:-ios_arm64}" name xc id variant
  case "$target" in
  ios_arm64) id=ios-arm64 variant="" ;;
  ios_simulator_arm64) id=ios-arm64-simulator variant=simulator ;;
  *) err "no xcframework slice for $target"; return 1 ;;
  esac
  name=$(basename "$framework" .framework)
  xc="$(dirname "$framework")/$name.xcframework"
  [ -d "$framework" ] || { err "no $framework to wrap"; return 1; }
  rm -rf "$xc" || return 1
  if ! { mkdir -p "$xc/$id" && cp -a "$framework" "$xc/$id/" &&
    python3 - "$xc/Info.plist" "$name" "$id" "$variant" <<'PY'
import plistlib, sys

path, name, ident, variant = sys.argv[1:]
library = {
    "LibraryIdentifier": ident,
    "LibraryPath": f"{name}.framework",
    "BinaryPath": f"{name}.framework/{name}",
    "SupportedArchitectures": ["arm64"],
    "SupportedPlatform": "ios",
}
if variant:
    library["SupportedPlatformVariant"] = variant
with open(path, "wb") as f:
    plistlib.dump({
        "AvailableLibraries": [library],
        "CFBundlePackageType": "XFWK",
        "XCFrameworkFormatVersion": "1.0",
    }, f)
PY
  }; then
    rm -rf "$xc"
    err "could not write $xc"
    return 1
  fi
  log "xcframework: $xc"
}

# Sourced (tests/kmp-framework/run.sh), only the functions are defined.
[ "${BASH_SOURCE[0]}" = "$0" ] || return 0

case " $* " in
*" -h "* | *" --help "*) kmp_usage ;;
*) kmp_main "$@" ;;
esac
