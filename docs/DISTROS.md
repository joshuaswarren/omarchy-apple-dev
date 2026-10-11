# Other Linux distributions

The tested distribution is Omarchy (Arch-based): `install-toolchain.sh` installs
its packages with pacman and the AUR. Everything else in this repository is
plain shell, Python and Swift, so other distributions work once you install the
same tools by hand. This file lists what to install and what is known to work.

On a system without pacman, `install-toolchain.sh` skips the Arch package steps,
prints a warning for anything missing, and continues. Put a Swift toolchain on
PATH first (see below).

## Ubuntu 24.04 (x86_64) — tested in a container

Verified in a clean Ubuntu 24.04 container on 2026-10-09, no-xcode mode:

| Step | Result |
|---|---|
| Swift 6.4.0 toolchain from swift.org | works; see the install path note below |
| `install-toolchain.sh` package steps | skipped with a warning (no pacman) |
| xtool build from source | works, after the libimobiledevice step below |
| rcodesign + ipsw binary downloads | work |
| pymobiledevice3 in a venv | works (11.26.0) |
| `sdk-free/setup.sh` (toolset, objc4 headers, stub cut from a dyld cache, sysroot, actool) | works |
| `sdk-free/swift/build-stdlib.sh` | works (Swift, SwiftOnoneSupport, _Concurrency, _RegexParser, _StringProcessing) |
| `sdk-free/swiftc.sh` on a hello program | links an arm64 iOS binary |
| apfs-fuse build (the no-phone IPSW path) | builds from the pinned commit |
| `sdk-free/swift/overlays.sh`, `sdk-free/flutter-build.sh` | not yet run on Ubuntu; verified on Arch with the same scripts |

Install the packages:

```
sudo apt install binutils build-essential ca-certificates cmake curl file git \
  gnupg2 libc6-dev libcurl4-openssl-dev libedit2 libfuse3-dev libbz2-dev \
  libgcc-13-dev libheif-dev libheif-examples libimobiledevice-dev liblzma-dev \
  libncurses6 libncursesw6 libpython3-dev libssl-dev libstdc++-13-dev \
  libtinfo6 libxml2-dev libz3-dev llvm pkg-config poppler-utils python3 \
  python3-venv rsync unzip usbmuxd zip zlib1g-dev
```

Swift toolchain: download the swift.org tarball and keep the `usr/` level of
the archive — SwiftPM finds the toolchain by walking up from the binary to a
`usr/lib/swift` directory, so a `--strip-components` install into `/usr/local`
breaks `swift build`:

```
curl -fLO https://download.swift.org/swift-6.4.0-release/ubuntu2404/swift-6.4.0-RELEASE/swift-6.4.0-RELEASE-ubuntu24.04.tar.gz
sudo tar -xzf swift-6.4.0-RELEASE-ubuntu24.04.tar.gz -C /usr/local
export PATH=/usr/local/usr/bin:$PATH
```

(On aarch64 the directory and file name gain `-aarch64`.)

libimobiledevice: the 24.04 package (1.3.0) is too old to build xtool — it has
no `idevice_events_subscribe`. Build the current stack from source into a
prefix (about 3 minutes) and point pkg-config at it:

```
sudo apt install autoconf automake libtool
export PREFIX=/usr/local/usr
git clone --depth 1 https://github.com/libimobiledevice/libplist
git clone --depth 1 https://github.com/libimobiledevice/libimobiledevice-glue
git clone --depth 1 https://github.com/libimobiledevice/libtatsu
git clone --depth 1 https://github.com/libimobiledevice/libimobiledevice
for r in libplist libimobiledevice-glue libtatsu libimobiledevice; do
  (cd $r && ./autogen.sh --prefix=$PREFIX && make -j$(nproc) && sudo make install)
done
echo $PREFIX/lib | sudo tee /etc/ld.so.conf.d/usrlocalusr.conf
sudo ldconfig
export PKG_CONFIG_PATH=$PREFIX/lib/pkgconfig
```

Then run `./install-toolchain.sh` as usual.

Status note: every step above ran in the container under a normal user
account. The dyld shared cache was read from a prepared cache directory
(`SDKFREE_DSC_DIR`), so no IPSW download was needed; `ipsw dyld tbd` and the
apfs-fuse build were verified separately. `overlays.sh` and `flutter-build.sh`
are plain shell over the same tools and were verified on Arch with the same
sysroot contents. Receipt with the quoted outputs:
`receipts/2026-10-09-ubuntu-2404.md`.

## NixOS — tested (x86_64)

[nix-apple-dev](https://github.com/m9tdev/nix-apple-dev) packages this repository
as a Nix flake. Verified on 2026-10-11 on NixOS (nixos-unstable): a SwiftUI app
with an asset catalog and a `#Preview` macro was built, signed with an App Store
Connect API key, installed and launched on an iPhone 12 mini (iOS 27.0).

| Piece | How the flake provides it |
|---|---|
| Swift 6.4.0 | the swift.org Ubuntu 24.04 tarball, patched with `autoPatchelfHook` |
| xtool, OpenAppleMacrosServer, actool | built from source at the revisions `install-toolchain.sh` pins |
| pymobiledevice3, rcodesign, ipsw | Nix packages |
| iOS SDK | built in the Nix sandbox from `Xcode_27.xip`, which the user adds to the Nix store once |
| usbmuxd | NixOS module option, or `sudo nix run github:m9tdev/nix-apple-dev#usbmuxd` |

The scripts run in a small FHS environment (`apple-dev`), because SwiftBuild
calls some tools by fixed path (`/usr/bin/touch`). xtool, pymobiledevice3 and
ipsw are on `PATH` there, not in `~/.local/bin`. `install-toolchain.sh` is not
used: Nix builds every piece it installs.

## Fedora — untested

Not tested. swift.org publishes no Fedora toolchain; the nearest builds are
ubi9/ubi10, which need the ncurses compatibility shim
(`install-toolchain.sh --curses-compat`). Package names differ from Debian
(`dnf install gcc-c++ git libcurl-devel libedit-devel libxml2-devel
libzstd-devel zlib-devel pkgconf unzip zip rsync file llvm cmake
libfuse3-devel libimobiledevice-devel poppler-utils heif-lib`); treat this as
a starting point, not a recipe.

## Arch-based distributions

Tested (the home target). `install-toolchain.sh` installs `usbmuxd zip
base-devel git libimobiledevice openssl poppler libheif` with pacman and Swift
from the AUR (`swift-bin`). Other Arch distributions should behave the same
when they have pacman and an AUR helper.
