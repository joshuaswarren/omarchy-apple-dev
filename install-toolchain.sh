#!/usr/bin/env bash
# Install the iOS-on-Linux toolchain on Omarchy (Arch, aarch64 or x86_64).
# Verified 2026-10-03 on x86_64 Arch (swift-bin 6.4.0, xtool 1.20.1, iOS 27.0
# SDK from Xcode 27.0); first run 2026-09-09 on aarch64 with 6.3.3 + 1.19.0.
# Safe to re-run: pieces already in place are skipped. Installs into user
# paths plus normal pacman/AUR packages. No system reinstalls.
set -euo pipefail

# Put the active toolchain's own bin dir (clang, lldb) first on PATH. swift-bin
# 6.3 used /usr/lib/swift/bin, 6.4 uses /usr/lib/swift/usr/bin, mise its own
# tree, so derive it from the swift on PATH. A system clang of another version
# breaks SwiftUI builds against the SDK (FINDINGS.md item 5).
toolchain_first_on_path() {
  PATH="$(dirname "$(readlink -f "$(command -v swift)")"):$PATH"
  export PATH
}

# Xcode major whose bundled Swift matches the toolchain (FINDINGS.md 16, 22).
matching_xcode() {
  case "$(swift --version 2>/dev/null)" in
    *"Swift version 6.4"*) echo 27 ;;
    *"Swift version 6.3"*) echo 26 ;;
    *) echo "whose Swift matches $(swift --version 2>/dev/null | head -n1)" ;;
  esac
}

VENV="$HOME/pymobile3-venv"
SDK_SRC="${SDK_SRC:-$HOME/xcode-apple-sdk-src}"
SDK_CACHE="${SDK_CACHE:-$HOME/.cache/xtool}"

# Register the SDK bundle at $1 into whatever toolchain is first on PATH.
# swift sdk install refuses to overwrite an existing bundle, so clear it first.
sdk_install_from() {
  swift sdk remove darwin >/dev/null 2>&1 || true
  "$HOME/.local/bin/xtool" sdk install "$1"
}

REPO_DIR=$(dirname "$(readlink -f "$0")")
DARWIN_SDK_BUNDLE="$HOME/.swiftpm/swift-sdks/darwin.artifactbundle"

# Shallow-fetch one commit of a repo into a cache dir (kept; the build reuses it).
fetch_commit() { # repo sha dir
  if [ ! -d "$3/.git" ]; then
    git init -q "$3"
    git -C "$3" fetch -q --depth 1 "$1" "$2"
    git -C "$3" checkout -q FETCH_HEAD
  fi
}

# xtool 1.20.1 plus fixes not released yet (xtool-org/xtool#290-#293, #295, #302): branch-pinned
# dependencies, `type: .dynamic` package products, extension dylibs kept in the host app
# (FINDINGS.md 24.1, 27.3, 30), and real source paths for SourceKit-LSP (FINDINGS.md 55).
# Built from source with its Swift runtime libraries next to it
# ($ORIGIN only), so a toolchain swap or upgrade cannot break it.
XTOOL_REPO=https://github.com/joshuaswarren/xtool
XTOOL_SHA=f0a1f90efdbb0dc023e276ff529da92618da7a87
install_xtool() {
  local src="$HOME/.cache/omarchy-apple-dev/xtool-$XTOOL_SHA"
  local dest="$HOME/.local/lib/omarchy-apple-dev/xtool-$XTOOL_SHA"
  if [ ! -x "$dest/xtool" ]; then
    fetch_commit "$XTOOL_REPO" "$XTOOL_SHA" "$src"
    echo "Building xtool $XTOOL_SHA (first run: about 7 minutes)"
    (cd "$src" && swift build -c release --product xtool -Xswiftc -no-toolchain-stdlib-rpath >/dev/null)
    local bin runtime
    bin=$(cd "$src" && swift build -c release --show-bin-path)
    runtime="$(dirname "$(dirname "$(readlink -f "$(command -v swift)")")")/lib/swift/linux"
    mkdir -p "$dest"
    install -m755 "$bin/xtool" "$bin/libXADI.so" "$dest/"
    LD_LIBRARY_PATH="$runtime" ldd "$dest/xtool" | awk -v rt="$runtime/" 'index($3, rt) == 1 { print $3 }' |
      xargs -r install -m644 -t "$dest"
  fi
  mkdir -p "$HOME/.local/bin"
  ln -sfn "$dest/xtool" "$HOME/.local/bin/xtool"
}

# xtool's SDK ships OpenAppleMacros v1.3.0 as the Darwin macro plugin server; it has no
# SwiftData macros, no widget #Preview (PreviewsMacros.Common), and the toolchain's own
# FoundationMacros emit `FoundationEssentials.` (#Predicate fails). Build the fork that adds
# them and register its modules with empty plugin stubs, which outrank the toolchain plugins.
# FINDINGS.md 26, 31.
OAM_REPO=https://github.com/joshuaswarren/OpenAppleMacros
OAM_SHA=cb003a1763b08947dd37376ed8240cbfb4745c32
install_oam() {
  local src="$HOME/.cache/omarchy-apple-dev/oam-$OAM_SHA"
  local plugins="$DARWIN_SDK_BUNDLE/Developer/Platforms/iPhoneOS.platform/Developer/usr/lib/swift/host/plugins"
  fetch_commit "$OAM_REPO" "$OAM_SHA" "$src"
  echo "Building OpenAppleMacrosServer $OAM_SHA (first run: about 5 minutes)"
  (cd "$src" && swift build -c release --build-system native --static-swift-stdlib \
    --product OpenAppleMacrosServer >/dev/null)
  install -m755 "$src/.build/release/OpenAppleMacrosServer" "$DARWIN_SDK_BUNDLE/OpenAppleMacrosServer"
  : > "$plugins/libSwiftDataMacros.so"
  : > "$plugins/libFoundationMacros.so"
}

# SwiftBuild (xtool 1.20 on Swift 6.4) runs actool for .xcassets and xcstringstool
# for .xcstrings package resources, and looks for both in the iPhoneOS platform's
# Developer/usr/bin. Install the Linux stand-ins there, give .strings copies an
# input encoding (SwiftBuild detects encodings only on macOS), and turn on Swift
# cross-import overlays (StoreKit + SwiftUI = StoreView, ...). FINDINGS.md 24.
# Dylib links of `type: .dynamic` products need the Swift runtime (-L/usr/lib/swift
# resolves under ld64's -syslibroot, the iPhoneOS SDK) and -all_load (SwiftPM builds
# their modules as archives). FINDINGS.md 27.3; also in xtool-org/xtool#293.
install_darwin_tools() {
  local bin="$DARWIN_SDK_BUNDLE/Developer/Platforms/iPhoneOS.platform/Developer/usr/bin"
  (cd "$REPO_DIR/tools/darwin-tools" && swift build -c release --product actool >/dev/null)
  mkdir -p "$bin"
  install -m755 "$REPO_DIR/tools/darwin-tools/.build/release/actool" "$bin/actool"
  install -m755 "$REPO_DIR/tools/xcstringstool" "$REPO_DIR/tools/ibtool" "$bin/"
  install -m644 "$REPO_DIR/tools/nibarchive.py" "$REPO_DIR/tools/keyorder.py" "$bin/"
  install -m755 "$REPO_DIR/tools/momc" "$bin/momc"
  install -m644 "$REPO_DIR/tools/xcstrings_symbols.py" "$bin/xcstrings_symbols.py"
  # macOS builds (swiftbuild --triple arm64-apple-macosx) look in the MacOSX
  # platform's Developer/usr/bin instead.
  local macbin="$DARWIN_SDK_BUNDLE/Developer/Platforms/MacOSX.platform/Developer/usr/bin"
  mkdir -p "$macbin"
  install -m755 "$REPO_DIR/tools/darwin-tools/.build/release/actool" "$macbin/actool"
  install -m755 "$REPO_DIR/tools/xcstringstool" "$REPO_DIR/tools/ibtool" "$macbin/"
  # The Mac nib compiler: the SDK ibtool dispatches MacOSX.Cocoa xibs to the
  # ibmac module and imports it from its own directory (SwiftBuild does not
  # pass PYTHONPATH through to build tasks).
  install -m644 "$REPO_DIR/tools/ibmac.py" "$macbin/"
  install -m644 "$REPO_DIR/tools/nibarchive.py" "$REPO_DIR/tools/keyorder.py" "$macbin/"
  install -m755 "$REPO_DIR/tools/momc" "$macbin/momc"
  install -m644 "$REPO_DIR/tools/xcstrings_symbols.py" "$macbin/xcstrings_symbols.py"
  python3 - "$DARWIN_SDK_BUNDLE" <<'PY'
import json, os, plistlib, sys
bundle = sys.argv[1]
for platform_name in ("iPhoneOS.platform", "MacOSX.platform"):
    platform = os.path.join(bundle, "Developer/Platforms", platform_name, "Info.plist")
    if not os.path.isfile(platform):
        continue
    with open(platform, "rb") as f:
        plist = plistlib.load(f)
    plist.setdefault("DefaultProperties", {})["STRINGS_FILE_INPUT_ENCODING"] = "utf-8"
    with open(platform + ".tmp", "wb") as f:
        plistlib.dump(plist, f)
    os.replace(platform + ".tmp", platform)
toolset = os.path.join(bundle, "toolset-swb.json")
with open(toolset) as f:
    data = json.load(f)
data.setdefault("swiftCompiler", {})["extraCLIOptions"] = ["-Xfrontend", "-enable-cross-import-overlays"]
data.setdefault("linker", {})["extraCLIOptions"] = ["-lswiftCore", "-L/usr/lib/swift", "-all_load"]
with open(toolset + ".tmp", "w") as f:
    json.dump(data, f, indent=4)
os.replace(toolset + ".tmp", toolset)
# Linux has no `tapi`, so swift-build cannot generate eager-linking stubs for
# promoted dylibs; its non-Darwin platforms hardcode the same DefaultProperties.
for platform_name in ("iPhoneOS.platform", "MacOSX.platform"):
    sdks = os.path.join(bundle, "Developer/Platforms", platform_name, "Developer/SDKs")
    for sdk in sorted(os.listdir(sdks)) if os.path.isdir(sdks) else []:
        if os.path.islink(os.path.join(sdks, sdk)):
            continue
        p = os.path.join(sdks, sdk, "SDKSettings.json")
        if os.path.isfile(p):
            d = json.load(open(p))
            dp = d.setdefault("DefaultProperties", {})
            dp["STRINGS_FILE_INPUT_ENCODING"] = "utf-8"
            dp["STRINGS_FILE_OUTPUT_ENCODING"] = "binary"
            dp.setdefault("GENERATE_INTERMEDIATE_TEXT_BASED_STUBS", "NO")
            dp.setdefault("GENERATE_TEXT_BASED_STUBS", "NO")
            json.dump(d, open(p, "w"))
        p = os.path.join(sdks, sdk, "SDKSettings.plist")
        d = plistlib.load(open(p, "rb")) if os.path.isfile(p) else {"DefaultProperties": {}}
        dp = d.setdefault("DefaultProperties", {})
        if dp.get("GENERATE_INTERMEDIATE_TEXT_BASED_STUBS") == "NO":
            continue
        dp["GENERATE_INTERMEDIATE_TEXT_BASED_STUBS"] = "NO"
        dp["GENERATE_TEXT_BASED_STUBS"] = "NO"
        plistlib.dump(d, open(p + ".tmp", "wb"))
        os.replace(p + ".tmp", p)
# The CopyStrings task cannot re-encode strings outside Darwin:
# FileTextEncoding.stringEncoding is `#if canImport(Darwin)`. Only the binary
# plist output works on Linux, and the input encoding must be spelled out
# (BOM detection sees only UTF-8/16 BOMs). Patch the spec defaults.
import re, shutil
swift_bin = shutil.which("swift")
if not swift_bin:
    sys.exit("install_darwin_tools: swift not on PATH")
# realpath ends in usr/bin/<driver>; the toolchain root is everything before
# that usr/bin (may be a plain prefix, not exactly four levels up).
toolchain_root = re.sub(r"/usr/bin/[^/]+$", "",
                        os.path.realpath(swift_bin))
for rel, fixes in (
    ("usr/share/pm/SwiftBuild_SWBUniversalPlatform.bundle/CopyStringsFile.xcspec",
     [("STRINGS_FILE_INPUT_ENCODING", "utf-8")]),
    ("usr/share/pm/SwiftBuild_SWBCore.bundle/CoreBuildSystem.xcspec",
     [("STRINGS_FILE_OUTPUT_ENCODING", "binary")]),
    ("usr/share/pm/SwiftBuild_SWBCore.bundle/NativeBuildSystem.xcspec",
     [("STRINGS_FILE_OUTPUT_ENCODING", "binary")]),
):
    p = os.path.join(toolchain_root, rel)
    if not os.path.isfile(p):
        continue
    old = open(p).read()
    lines = old.split("\n")
    for setting, value in fixes:
        for i, line in enumerate(lines):
            if f'Name = "{setting}";' in line or f'Name = {setting};' in line:
                for j in range(i + 1, min(i + 12, len(lines))):
                    if "DefaultValue =" in lines[j]:
                        lines[j] = re.sub(r'"[^"]*"\s*;', f'"{value}";', lines[j])
                        break
    new = "\n".join(lines)
    if new == old:
        continue
    # A package-managed toolchain (AUR swift-bin under /usr/lib/swift) is
    # root-owned: say what to patch instead of aborting the rest of the install.
    if not os.access(p, os.W_OK):
        print(f"WARNING: {p} is not writable; set its {', '.join(s for s, _ in fixes)} "
              f"DefaultValue to {', '.join(v for _, v in fixes)} as root", file=sys.stderr)
        continue
    open(p, "w").write(new)
PY
  echo "Installed actool, xcstringstool, momc and ibtool (version probe; compiles a small xib subset) into $bin"
}

# Build the portable darwin.xtoolsdk from an Xcode.xip or Xcode.app ($1),
# keep it in the cache, and register it. Building instead of installing
# directly costs the same extraction plus one local copy, but the result is
# toolchain-independent: it survives toolchain swaps (mise/asdf/manual) and
# re-registers with no .xip and no network (see README, Toolchain swaps).
sdk_build_and_install() {
  mkdir -p "$SDK_CACHE"
  tmpd=$(mktemp -d "$SDK_CACHE/.build.XXXXXX")
  "$HOME/.local/bin/xtool" sdk build "$1" "$tmpd"
  # Name the cache after the iOS SDK inside it; works for .xip and Xcode.app input.
  ver=unknown
  for sdk in "$tmpd"/darwin.xtoolsdk/Developer/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS[0-9]*.sdk; do
    if [ -e "$sdk" ]; then ver=$(basename "$sdk" .sdk); fi
  done
  cached="$SDK_CACHE/darwin-$ver.xtoolsdk"
  rm -rf "$cached"
  mv "$tmpd/darwin.xtoolsdk" "$cached"
  rmdir "$tmpd"
  echo "SDK cache kept at: $cached"
  # ship.sh stamps DTXcode/DTXcodeBuild from this. A .xip hides it; set
  # XCODE_VERSION and XCODE_BUILD for ship.sh instead.
  if [ -f "$1/Contents/version.plist" ]; then cp "$1/Contents/version.plist" "$cached.version.plist"; fi
  # ship.sh trains App Shortcuts (Metadata.appintents/nlu) with Xcode's phrase lists from here. A
  # .xip hides them too; set SSU_RESOURCES for ship.sh to a copy of this directory instead.
  ssu_src="$1/Contents/Frameworks/SiriSSUKitModel.framework/Versions/A/Resources"
  if [ -d "$ssu_src" ]; then rm -rf "$cached.SiriSSUKitModel"; cp -R "$ssu_src" "$cached.SiriSSUKitModel"; fi
  sdk_install_from "$cached"
}

# Survive-status summary: what a toolchain swap leaves behind.
survive_status() {
  echo "-- Survive status --"
  echo "SDK: re-registered from $1"
  if ls "$HOME/.pymobiledevice3"/*.plist >/dev/null 2>&1; then
    echo "pairing: intact at $HOME/.pymobiledevice3"
  else
    echo "pairing: no records yet (plug the iPhone once; nothing is lost here by a swap)"
  fi
  if [ -n "$(ls -A "$HOME/.local/share/xtool" 2>/dev/null)" ]; then
    echo "auth: present at $HOME/.local/share/xtool"
  else
    echo "auth: missing — run: $HOME/.local/bin/xtool auth"
  fi
}

# Vendor Swift tarballs (the swift.org ubi9/ubuntu builds, which is what mise
# installs) link the narrow curses sonames RHEL and Debian ship. Arch builds
# ncurses wide-only, so libncurses.so.6, libform.so.6 and libpanel.so.6 do not
# exist here and the toolchain dies at load with "error while loading shared
# libraries"; mise reports a bare exit 127 and rolls the install back
# (FINDINGS.md item 21). The wide libraries serve these callers: the Swift
# toolchain imports no wide-char curses symbols and records no symbol-version
# requirement, so ldd -r resolves clean against them.
#
# The aliases go in a private directory, never /usr/lib: pacman owns that, an
# unowned alias there survives ncurses updates silently, and it would shadow
# the narrow ABI for every other binary on the system.
CURSES_COMPAT_DIR="${CURSES_COMPAT_DIR:-$HOME/.local/lib/curses-narrow-compat}"

curses_compat() {
  mkdir -p "$CURSES_COMPAT_DIR"
  echo "== curses compat aliases in $CURSES_COMPAT_DIR =="
  linked=0
  for stem in ncurses form panel menu tinfo; do
    narrow="lib${stem}.so.6"
    wide="/usr/lib/lib${stem}w.so.6"
    [ -e "/usr/lib/$narrow" ] && continue   # host ships the narrow name already
    [ -e "$wide" ] || continue              # no wide twin to alias
    ln -sfn "$wide" "$CURSES_COMPAT_DIR/$narrow"
    echo "  $narrow -> $wide"
    linked=$((linked + 1))
  done
  if [ "$linked" -eq 0 ]; then echo "  nothing to alias (host already complete)"; fi

  # Optional: an extracted toolchain root ($1). SwiftBuild runs swiftc and the
  # linker with a scrubbed environment, so LD_LIBRARY_PATH never reaches them
  # (FINDINGS.md item 25). Link the aliases into the toolchain's own RUNPATH
  # directories as well, which every binary there searches first.
  if [ -n "${1:-}" ]; then
    if [ ! -d "$1" ]; then
      echo "Not a directory: $1" >&2
      return 1
    fi
    if [ ! -e /usr/lib/libxml2.so.2 ] && [ -e /usr/lib/libxml2.so.16 ]; then
      ln -sfn /usr/lib/libxml2.so.16 "$CURSES_COMPAT_DIR/libxml2.so.2"
    fi
    for dir in "$1/usr/lib" "$1/usr/lib/swift/linux"; do
      [ -d "$dir" ] || continue
      for alias in "$CURSES_COMPAT_DIR"/*.so*; do
        [ -e "$alias" ] && ln -sfn "$(readlink "$alias")" "$dir/$(basename "$alias")"
      done
    done
    echo "  aliases also linked into $1/usr/lib and $1/usr/lib/swift/linux"
    echo "-- verifying $1 --"
    unresolved=$(
      export LD_LIBRARY_PATH="$CURSES_COMPAT_DIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
      { find "$1" -path '*/bin/*' -type f -perm -u+x
        find "$1" -name '*.so*' -type f; } 2>/dev/null |
        while read -r f; do ldd -r "$f" 2>/dev/null | grep -E 'not found' || true; done |
        awk '{print $1}' | sort -u
    )
    if [ -n "$unresolved" ]; then
      echo "still unresolved (no wide twin on this host):"
      echo "$unresolved" | sed 's/^/  /'
      return 1
    fi
    echo "  all sonames resolve"
  fi

  cat <<EOF

Put the directory on the loader path for both the install and runtime:

Shell (simplest — works everywhere):

  export LD_LIBRARY_PATH="$CURSES_COMPAT_DIR\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}"
  mise install swift@6.3.3

Or mise.toml (mise main, 2026-09-18: install_env renders templates now):

  [tools]
  swift = { version = "6.3.3", install_env = { LD_LIBRARY_PATH = "{{env.HOME}}/$CURSES_COMPAT_DIR" } }
  [env]
  LD_LIBRARY_PATH = "{{env.HOME}}/$CURSES_COMPAT_DIR"

install_env covers the install-time check; [env] covers mise exec.
Plain mise.toml [env] alone never reaches the install subprocess by design.

On current Arch the toolchain also needs libxml2.so.2 aliased to
libxml2.so.16 (same directory) and a real libpython3.9.so.1.0 for lldb —
see FINDINGS.md item 21.

This repo's own install path (AUR swift-bin) does not need any of this; the
package links the wide libraries directly.
EOF
}

if [ "${1:-}" = "--curses-compat" ]; then
  curses_compat "${2:-}"
  exit 0
fi

if [ "${1:-}" = "--repair" ]; then
  # Toolchain swapped out from under a working setup (mise, asdf, manual
  # reinstall): repair runs against whatever toolchain the current shell
  # resolves, so the SDK is re-registered into THAT toolchain. Pairing and
  # Apple ID auth live in user-global paths and were never affected.
  if ! command -v swift >/dev/null 2>&1; then
    echo "No swift on PATH. Activate your toolchain first — for mise:"
    echo '  eval "$(mise activate bash)"   # or reopen your shell'
    exit 1
  fi
  swift --version | head -n1
  toolchain_first_on_path
  cached=$(ls -dt "$SDK_CACHE"/darwin-*.xtoolsdk 2>/dev/null | head -n1 || true)
  if [ -n "$cached" ]; then
    sdk_install_from "$cached"
  elif [ -n "${XCODE_XIP:-}" ] && [ -f "$XCODE_XIP" ]; then
    cached="XCODE_XIP=$XCODE_XIP"
    sdk_build_and_install "$XCODE_XIP"
  else
    echo "No cached SDK in $SDK_CACHE and no XCODE_XIP given."
    echo "Nothing to repair from. Either point XCODE_XIP at an Xcode $(matching_xcode) .xip,"
    echo "or run once with XCODE_XIP to build the cache for next time."
    exit 1
  fi
  swift sdk list   # must print: darwin
  install_darwin_tools
  install_oam
  survive_status "$cached"
  exit 0
fi

# --user-only: no sudo and no system packages. Bring your own Swift on PATH (a
# swift.org tarball or mise; see --curses-compat) and the system tools below.
if [ "${1:-}" = "--user-only" ]; then
  echo "== 1-2. User-only install: using $(command -v swift || echo 'no swift on PATH')"
  swift --version | head -n1
  for tool in zip python3 git cc pkg-config pdftocairo heif-convert; do
    command -v "$tool" >/dev/null || echo "WARNING: $tool is missing; ask an admin for it"
  done
  pkg-config --exists libimobiledevice-1.0 openssl ||
    echo "WARNING: libimobiledevice or openssl headers are missing (xtool build); ask an admin for them"
  # lldb links one libpython3.x (3.12 for Swift 6.4); device-run.sh --lldb needs it.
  lldb_missing=$(ldd "$(dirname "$(readlink -f "$(command -v swift)")")/../lib/liblldb.so"* 2>/dev/null |
    awk '/not found/ {print $1}' | sort -u)
  if [ -n "$lldb_missing" ]; then echo "WARNING: lldb needs $lldb_missing; ask an admin for it"; fi
else
echo "== 1. usbmuxd (device multiplexer; udev starts it on plug), zip, xtool build deps =="
# zip packages the .ipa in ship.sh. base-devel, git, libimobiledevice and openssl
# build xtool from source (step 3). poppler provides pdfinfo/pdftocairo for the
# actool PDF imageset path (AssetKit's PdftoCairoRasterizer), libheif heif-convert for HEIC images.
sudo pacman -S --needed --noconfirm usbmuxd zip base-devel git libimobiledevice openssl poppler libheif
# usbmuxd.service is static on Arch: it is triggered by udev, do not enable it.

echo "== 2. Swift toolchain (AUR binary package: swift, clang, lldb) =="
yay -S --needed --noconfirm swift-bin
# lldb links a specific libpython3.x, and swift-bin's own optional-dep note
# names the right one (python39 through 6.3.x, python312 from 6.4). Install
# whatever the installed package asks for; without it lldb fails to start
# with "libpython3.9.so.1.0: cannot open shared object file".
pydep=$(pacman -Qi swift-bin | grep -oE 'python3[0-9]+' | head -n1)
if [ -n "$pydep" ]; then yay -S --needed --noconfirm --asdeps "$pydep"; fi
fi

echo "== 3. xtool (built from source) and rcodesign (aarch64 and x86_64 releases) =="
toolchain_first_on_path
install_xtool
"$HOME/.local/bin/xtool" --version
# rcodesign (apple-codesign) signs App Store builds for ship.sh; pinned + checksummed.
RCODESIGN_VERSION=0.29.0
case "$(uname -m)" in
  aarch64) rcs_sha=4af92c87ddf52f5f2d1258a3b4e56c7dcb8f1b2468df744976c5f139e031961f ;;
  x86_64) rcs_sha=dbe85cedd8ee4217b64e9a0e4c2aef92ab8bcaaa41f20bde99781ff02e600002 ;;
esac
if ! "$HOME/.local/bin/rcodesign" --version 2>/dev/null | grep -q "$RCODESIGN_VERSION"; then
  rcs=apple-codesign-$RCODESIGN_VERSION-$(uname -m)-unknown-linux-musl
  rcs_tmp=$(mktemp -d)
  curl -fsSL "https://github.com/indygreg/apple-platform-rs/releases/download/apple-codesign%2F$RCODESIGN_VERSION/$rcs.tar.gz" \
    -o "$rcs_tmp/rcs.tar.gz"
  echo "$rcs_sha  $rcs_tmp/rcs.tar.gz" | sha256sum -c --quiet
  tar -xzf "$rcs_tmp/rcs.tar.gz" -C "$rcs_tmp"
  install -m755 "$rcs_tmp/$rcs/rcodesign" "$HOME/.local/bin/rcodesign"
  rm -rf "$rcs_tmp"
fi
"$HOME/.local/bin/rcodesign" --version
# ipsw extracts the Swift runtime dylibs from an iPhone's shared cache for LLDB (device-run.sh
# --lldb, FINDINGS.md 56); pinned + checksummed.
IPSW_VERSION=3.1.731
case "$(uname -m)" in
  aarch64) ipsw_arch=arm64 ipsw_sha=a8d373966d79d24537aa17ec8b9a61bbc73964e6200383f7708c53400ad9f42a ;;
  x86_64) ipsw_arch=x86_64 ipsw_sha=98e5b127641be3511242a5ba9c5872ef34010e5171318b616e5aa80a607749ff ;;
esac
if ! "$HOME/.local/bin/ipsw" version 2>/dev/null | grep -q "$IPSW_VERSION"; then
  ipsw_tmp=$(mktemp -d)
  curl -fsSL "https://github.com/blacktop/ipsw/releases/download/v$IPSW_VERSION/ipsw_${IPSW_VERSION}_linux_$ipsw_arch.tar.gz" \
    -o "$ipsw_tmp/ipsw.tar.gz"
  echo "$ipsw_sha  $ipsw_tmp/ipsw.tar.gz" | sha256sum -c --quiet
  tar -xzf "$ipsw_tmp/ipsw.tar.gz" -C "$ipsw_tmp" ipsw
  install -m755 "$ipsw_tmp/ipsw" "$HOME/.local/bin/ipsw"
  rm -rf "$ipsw_tmp"
fi
"$HOME/.local/bin/ipsw" version | head -n1

echo "== 4. pymobiledevice3 in a venv =="
python3 -m venv "$VENV"
"$VENV/bin/pip" install pymobiledevice3
"$VENV/bin/pip" show pymobiledevice3 | sed -n 's/^Version: /pymobiledevice3 /p'

echo "== 5. iOS SDK source =="
# The SDK artifacts exist only inside Apple's Xcode distribution; there is no
# standalone iOS SDK download. The public route needs no Mac and no macOS
# anywhere: download Xcode.xip from Apple on any OS, hand the file to this
# script. (An already-extracted Xcode.app tree also works via SDK_SRC.)
echo "-- Route A (default): Xcode.xip downloaded from Apple --"
# 1. Sign in at https://developer.apple.com/download/all/?q=Xcode (free Apple ID)
# 2. Download the Xcode .xip whose Swift matches swift-bin: Xcode 27 for 6.4,
#    Xcode 26 for 6.3 (FINDINGS.md items 16 and 22)
# 3. Re-run:  XCODE_XIP=/path/to/Xcode.xip $0

echo "-- Route B (optional): an extracted Xcode.app tree --"
# If you already have a Mac with a matching Xcode, only these pieces are
# needed (about 3 GB) in $SDK_SRC/Xcode.app/Contents (xtool 1.20 SDKBuilder):
#   ssh MAC_HOST 'cd /Applications/Xcode.app/Contents && tar -cf - \
#     Info.plist version.plist \
#     Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/swift \
#     Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/swift_static \
#     Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/clang \
#     Developer/Platforms/iPhoneOS.platform/Info.plist \
#     Developer/Platforms/iPhoneOS.platform/Developer/SDKs \
#     Developer/Platforms/iPhoneOS.platform/Developer/Library \
#     Developer/Platforms/iPhoneOS.platform/Developer/usr/lib \
#     Developer/Platforms/MacOSX.platform/Info.plist \
#     Developer/Platforms/MacOSX.platform/Developer/SDKs \
#     Developer/Platforms/MacOSX.platform/Developer/Library \
#     Developer/Platforms/MacOSX.platform/Developer/usr/lib \
#     Developer/Platforms/iPhoneSimulator.platform/Info.plist \
#     Developer/Platforms/iPhoneSimulator.platform/Developer/SDKs \
#     Developer/Platforms/iPhoneSimulator.platform/Developer/Library \
#     Developer/Platforms/iPhoneSimulator.platform/Developer/usr/lib' \
#   | tar -xf - -C "$SDK_SRC/Xcode.app/Contents"

echo "== 6. Darwin SDK registration =="
toolchain_first_on_path
if swift sdk list 2>/dev/null | grep -q darwin; then
  echo "Darwin SDK already registered; skipping install."
elif [ -n "${XCODE_XIP:-}" ] && [ -f "$XCODE_XIP" ]; then
  sdk_build_and_install "$XCODE_XIP"
elif [ -d "$SDK_SRC/Xcode.app" ]; then
  sdk_build_and_install "$SDK_SRC/Xcode.app"
else
  echo
  echo "==================================================================="
  echo " One download left: the iOS SDK comes from Apple, inside Xcode.xip."
  echo " No Mac needed — the download works from any OS with a browser."
  echo
  echo " 1. Sign in (free Apple ID):"
  echo "      https://developer.apple.com/download/all/?q=Xcode"
  echo " 2. Download Xcode $(matching_xcode) (.xip). The SDK's Swift must match"
  echo "      swift-bin's (FINDINGS.md items 16 and 22)."
  echo " 3. Re-run:"
  echo "      XCODE_XIP=/path/to/Xcode.xip $0"
  echo
  echo " Already installed before with this script? The SDK cache in"
  echo " $SDK_CACHE may still have the bundle — try: $0 --repair"
  echo "==================================================================="
  exit 1
fi
swift sdk list   # must print: darwin
install_darwin_tools
install_oam

# If an app that failed against an earlier or broken SDK still fails now, the
# stale module cache is the cause: delete that project's .build directory (or
# build in a fresh copy of the project) and rebuild.

echo "== 7. Apple ID sign-in (interactive, needed before device deploys) =="
echo "Run: $HOME/.local/bin/xtool auth"
echo "Done. Next: plug in the iPhone and run ./device-run.sh"
