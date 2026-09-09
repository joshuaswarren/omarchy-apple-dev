#!/usr/bin/env bash
# Install the iOS-on-Linux toolchain on Omarchy (Arch, aarch64).
# Verified 2026-09-09: swift 6.3.3, xtool 1.19.0, lldb 21.0.0, pymobiledevice3.
# Installs into user paths plus normal pacman/AUR packages. No system reinstalls.
set -euo pipefail

SWIFT_BIN_DIR=/usr/lib/swift/bin
VENV="$HOME/pymobile3-venv"
SDK_SRC="$HOME/xcode-apple-sdk-src"

echo "== 1. usbmuxd (device multiplexer; udev starts it on plug) =="
sudo pacman -S --needed --noconfirm usbmuxd
# usbmuxd.service is static on Arch: it is triggered by udev, do not enable it.

echo "== 2. Swift 6.3 toolchain (AUR binary package, includes lldb and clang) =="
yay -S --needed --noconfirm swift-bin
# lldb needs libpython3.9: the package lists python39 as an optional dep.
sudo pacman -S --needed --noconfirm --asdeps python39 || yay -S --noconfirm python39

echo "== 3. xtool AppImage =="
mkdir -p "$HOME/.local/bin"
curl -fL "https://github.com/xtool-org/xtool/releases/latest/download/xtool-$(uname -m).AppImage" \
  -o "$HOME/.local/bin/xtool"
chmod +x "$HOME/.local/bin/xtool"
"$HOME/.local/bin/xtool" --version

echo "== 4. pymobiledevice3 in a venv =="
python3 -m venv "$VENV"
"$VENV/bin/pip" install pymobiledevice3
"$VENV/bin/pymobiledevice3" --version

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
# IMPORTANT: the Swift toolchain's own clang must come first in PATH.
# A system clang of a different version causes __builtin_bit_cast size errors
# when compiling SwiftUI against the SDK.
export PATH="$SWIFT_BIN_DIR:$PATH"
# Route A:
"$HOME/.local/bin/xtool" sdk install "$SDK_SRC/Xcode.app" || true
# Route B (comment the line above, uncomment this one):
# "$HOME/.local/bin/xtool" sdk install "$HOME/Downloads/Xcode.xip"

swift sdk list   # must print: darwin

echo "== 7. Apple ID sign-in (interactive, needed before device deploys) =="
echo "Run: $HOME/.local/bin/xtool auth"
echo "Done. Next: plug in the iPhone and run ./device-run.sh"
