#!/usr/bin/env bash
# Install the iOS-on-Linux toolchain on Omarchy (Arch, aarch64 or x86_64).
# Verified 2026-09-09 on an M1 (aarch64) and 2026-09-13 on a T2 Intel MacBook Pro
# (x86_64): swift 6.3.3, xtool 1.19.x, lldb 21.0.0, pymobiledevice3. Every
# arch-specific choice (swift-bin tarball, xtool AppImage) keys off uname -m.
# Installs into user paths plus normal pacman/AUR packages. No system reinstalls.
set -euo pipefail

case "$(uname -m)" in
  aarch64|x86_64) ;;
  *) echo "Unsupported host arch: $(uname -m) (need aarch64 or x86_64)"; exit 1 ;;
esac
echo "Host: $(uname -m). Apps are cross-compiled to arm64 iOS regardless of host."

SWIFT_BIN_DIR=/usr/lib/swift/bin
VENV="$HOME/pymobile3-venv"
SDK_SRC="$HOME/xcode-apple-sdk-src"

echo "== 1. usbmuxd (device multiplexer; udev starts it on plug) =="
sudo pacman -S --needed --noconfirm usbmuxd
# usbmuxd.service is static on Arch: it is triggered by udev, do not enable it.

echo "== 2. Swift 6.3 toolchain (AUR binary package, includes lldb and clang) =="
# swift-bin has arch=('x86_64' 'aarch64') and picks the matching swift.org
# ubi9 tarball for the host, so this line is the same on Intel and Apple Silicon.
yay -S --needed --noconfirm swift-bin
# lldb needs libpython3.9: the package lists python39 as an optional dep.
sudo pacman -S --needed --noconfirm --asdeps python39 || yay -S --noconfirm python39

echo "== 3. xtool AppImage (xtool-x86_64 or xtool-aarch64, picked by uname -m) =="
mkdir -p "$HOME/.local/bin"
curl -fL "https://github.com/xtool-org/xtool/releases/latest/download/xtool-$(uname -m).AppImage" \
  -o "$HOME/.local/bin/xtool"
chmod +x "$HOME/.local/bin/xtool"
"$HOME/.local/bin/xtool" --version

echo "== 4. pymobiledevice3 in a venv =="
python3 -m venv "$VENV"
"$VENV/bin/pip" install pymobiledevice3
"$VENV/bin/pymobiledevice3" version   # 11.x has no --version flag

echo "== 5. iOS SDK =="
# xtool sdk install accepts an Xcode.xip OR an extracted Xcode.app directory.
# Pick ONE of the routes below.

echo "-- Route A: Xcode.app directory streamed from a Mac with Xcode --"
# On the Mac, only these pieces are needed (about 3 GB):
#   Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/lib/{swift,swift_static,clang}
#   Contents/Developer/Platforms/{iPhoneOS,MacOSX,iPhoneSimulator}.platform/Developer/{SDKs,Library,usr/lib}
# From a host that can SSH to the Mac:
#   ssh MAC_HOST 'cd /Applications/Xcode.app/Contents/Developer && tar -cf - \
#     Toolchains/XcodeDefault.xctoolchain/usr/lib/swift \
#     Toolchains/XcodeDefault.xctoolchain/usr/lib/swift_static \
#     Toolchains/XcodeDefault.xctoolchain/usr/lib/clang \
#     Platforms/iPhoneOS.platform/Developer/SDKs \
#     Platforms/iPhoneOS.platform/Developer/Library \
#     Platforms/iPhoneOS.platform/Developer/usr/lib \
#     Platforms/MacOSX.platform/Developer/SDKs \
#     Platforms/MacOSX.platform/Developer/Library \
#     Platforms/MacOSX.platform/Developer/usr/lib \
#     Platforms/iPhoneSimulator.platform/Developer/SDKs \
#     Platforms/iPhoneSimulator.platform/Developer/Library \
#     Platforms/iPhoneSimulator.platform/Developer/usr/lib' \
#   | tar -xf - -C "$SDK_SRC/Xcode.app/Contents/Developer"
# (mkdir -p "$SDK_SRC/Xcode.app/Contents/Developer" first.)

echo "-- Route B: Xcode.xip from developer.apple.com --"
# Download from https://developer.apple.com/download/all/?q=Xcode (Apple ID
# required), then point xtool sdk install at the .xip path directly.

echo "== 6. Darwin SDK registration =="
# xtool's file copy preserves ownership (swift-corelibs FileManager.copyItem
# calls lchown), which is EPERM for a normal user on the root-owned swift-bin
# tree. Take ownership of it first. Needed on aarch64 and x86_64 alike.
sudo chown -R "$USER" /usr/lib/swift
# IMPORTANT: the Swift toolchain's own clang must come first in PATH.
# A system clang of a different version causes __builtin_bit_cast size errors
# when compiling SwiftUI against the SDK.
export PATH="$SWIFT_BIN_DIR:$PATH"
# Pick whichever SDK source is present: Route A directory, else the newest
# Xcode*.xip in ~/Downloads, else stop here with instructions.
XIP=$(ls -t "$HOME"/Downloads/Xcode*.xip 2>/dev/null | head -n1 || true)
if [ -d "$SDK_SRC/Xcode.app" ]; then
  "$HOME/.local/bin/xtool" sdk install "$SDK_SRC/Xcode.app"
elif [ -n "$XIP" ]; then
  "$HOME/.local/bin/xtool" sdk install "$XIP"
else
  echo "No SDK source found. Either stream Xcode.app into $SDK_SRC (Route A) or"
  echo "download Xcode.xip into ~/Downloads (Route B), then run:"
  echo "  PATH=$SWIFT_BIN_DIR:\$PATH $HOME/.local/bin/xtool sdk install <Xcode.app or Xcode.xip>"
  exit 0
fi

swift sdk list   # must print: darwin

echo "== 7. Apple ID sign-in (interactive, needed before device deploys) =="
echo "Run: $HOME/.local/bin/xtool auth"
echo "Done. Next: plug in the iPhone and run ./device-run.sh"
