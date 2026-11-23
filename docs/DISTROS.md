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
sudo tar -xzf swift-6.4.0-RELEASE-ubuntu24.04.tar.gz --strip-components=1 -C /usr/local
export PATH=/usr/local/usr/bin:$PATH
```

(On aarch64 the directory and file name gain `-aarch64`. Both tarballs carry a
top-level `swift-6.4.0-RELEASE-…/` directory; `--strip-components=1` keeps the
`usr/` level itself, which is what SwiftPM walks up from.)

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

## Ubuntu 24.04 (aarch64) — verified on the metal, no Xcode download

Verified 2026-10-19 on an ASUS Ascent GX10 (NVIDIA GB10, 20-core aarch64,
Ubuntu 24.04.5): `install-toolchain.sh --mode no-xcode` end to end (xtool from
source, the rcodesign/ipsw aarch64 release binaries, the pymobiledevice3 venv,
the sysroot cut from the public iPhone16,2 iOS 27.0.1 IPSW, the Swift standard
library and overlays), then `flutter/setup.sh`, then
`sdk-free/flutter-build.sh` on the sample app (`path_provider`,
`shared_preferences`, `sqlite3`, `url_launcher`): an unsigned `Runner.ipa` in
43 s. Notes beyond the x86_64 list above:

- `flutter/setup.sh` works unmodified on an aarch64 host: gclient's DEPS hooks
  fetch linux-arm64 prebuilt clang/gn/ninja, the patch applies cleanly, and
  `gen_snapshot` links in about a minute on a 20-core machine.
- Debian/Ubuntu fuse3 headers refuse to preprocess `fuse3/fuse.h` without
  `-DFUSE_USE_VERSION>=30`, which made the apfs-fuse prerequisite probe a
  false negative (#68); the probe passes the define now.
- Plugins whose pubspec has no `pluginClass:` (pure-Dart or native-assets
  implementations, e.g. `path_provider_foundation` 2.6.0) are skipped by the
  plugin scan instead of aborting the build (#68).

## NixOS (x86_64): reported by the flake author, no receipt here

[nix-apple-dev](https://github.com/m9tdev/nix-apple-dev) packages this repository
as a Nix flake. The flake author reports that on 2026-10-11 on NixOS (nixos-unstable) a SwiftUI app
with an asset catalog and a `#Preview` macro was built, signed with an App Store
Connect API key, installed and launched on an iPhone 12 mini (iOS 27.0). We did not run it; this repository holds no run record for it.

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

## Fedora 44 (x86_64) — SwiftUI iPhone deployment verified (two-stage workaround)

Community report, **2026-10-20**: On Fedora 44 x86_64, the `--mode full`
installer completed with **Swift 6.4.1** from the official UBI 9 tarball and
**Xcode 27.1**. A native SwiftUI counter was **built, signed, installed over
USB, launched and interacted with on a physical iPhone 15 Pro**. This used
**newer upstream xtool** for authentication and deployment, not the pinned
installer binary; LLDB and modified-source redeployment remain unverified.

Install Fedora's dependencies first (consolidated working list, not a proven
minimal set):

```sh
sudo dnf install \
  binutils bzip2-devel ca-certificates cmake curl file \
  gcc-c++ git gnupg2 libstdc++-devel \
  fuse3-devel libcurl-devel libedit-devel \
  libheif libheif-devel libheif-tools \
  libimobiledevice-devel libimobiledevice-utils \
  libxml2-devel libzstd-devel ncurses-libs \
  openssl-devel pkgconf-pkg-config poppler-utils \
  python3 python3-devel python3-pip \
  rsync unzip usbmuxd xz-devel z3-devel zip zlib-devel llvm
```

Use the official [Swift UBI 9 Linux release](https://www.swift.org/install/linux/ubi/9/)
(6.4.1 for this test); preserve the tarball's `usr/` hierarchy and prepend
`<swift-root>/usr/bin` to `PATH`. Obtain the matching Xcode `.xip` from Apple.
Then run the installer:

```sh
git clone https://github.com/joshuaswarren/omarchy-apple-dev.git
cd omarchy-apple-dev
env XCODE_XIP="$HOME/apple-dev/Xcode_27.1.xip" ./install-toolchain.sh --mode full
```

Fedora-specific gotchas: `fuse3-devel` (not `libfuse3-devel`), `xz-devel`
(`lzma.h`), `gcc-c++` / `libstdc++-devel` (C++ headers), `python3-devel`
(`Python.h` for the `pylzss` build), and `libheif-tools` (`heif-convert`).
The `No pacman` message is expected. No manual ncurses compatibility shim
was required for **installation on this host**, but LLDB still reported a
missing `libpython3.9.so.1.0` and was not tested.

**Deployment workaround used in this 2026-10-20 run:** the installer then pinned a patched xtool at
`f0a1f90efdbb0dc023e276ff529da92618da7a87`; it compiled SwiftUI but
Apple ID authentication failed with `-80045`. Upstream xtool's newer `aa6ba75e7df759a84560885a86822dd119da8c55`
authenticated successfully after a separate source build:

```sh
mkdir -p "$HOME/src"
git clone https://github.com/xtool-org/xtool.git "$HOME/src/xtool-main"
cd "$HOME/src/xtool-main"
git checkout --detach aa6ba75e7df759a84560885a86822dd119da8c55
swift run -c release xtool auth
"$HOME/src/xtool-main/.build/release/xtool" sdk install "$HOME/apple-dev/Xcode_27.1.xip" # full, NOT --slim
```

The upstream tool rejected the installer's old slim-style Darwin SDK until a
full SDK was installed. Its login was separate from the installed fork; if
necessary authenticate again using the same upstream executable. Add a unique
`bundleID` to the Swift package's `xtool.yml`, then run the upstream binary's
`dev` subcommand with the iPhone connected. An initial 409 device provisioning
error disappeared on retry after an explicit bundle ID was added; **the reason
for that success is unconfirmed**.

See [`receipts/2026-10-20-fedora-44.md`](../receipts/2026-10-20-fedora-44.md)
for the exact dependency/setup commands, observed warnings, successful
provisioning/signing/install log, and outstanding limitations.

## Fedora 45 (aarch64, Asahi) — full install in a distrobox

Verified 2026-11-23 on Fedora Linux Asahi Remix 45 (kernel
`7.3.4-401.asahi.fc45.aarch64+16k`, 16K pages): `install-toolchain.sh --mode
full` ran to `Done.` with Swift 6.4.1 for steps 1-4 and 6.4.2 for the SDK
step (swift.org UBI 9 builds, installed with mise) and Xcode 27.2 (27B52). It built xtool, registered the iOS, simulator and
macOS 27.2 SDKs, and installed `actool`, `xcstringstool`, `momc`, `ibtool` and
OpenAppleMacrosServer. No Apple ID sign-in, app build or device install has
been run on this setup yet.

The build dependencies live in a distrobox, so the host gets no `-devel`
packages. distrobox shares `$HOME`, so everything the installer writes
(`~/.local/bin/xtool`, `rcodesign`, `ipsw`, `~/pymobile3-venv`, the SDK) lands
in your home directory. The tools run on the host too, because the container
and the host are the same Fedora release.

```sh
distrobox create --name apple-dev --image registry.fedoraproject.org/fedora-toolbox:45
distrobox enter apple-dev -- sudo dnf install -y --setopt=install_weak_deps=False \
  gcc gcc-c++ make cmake git binutils file pkgconf-pkg-config \
  libimobiledevice-devel libimobiledevice-utils usbmuxd openssl-devel \
  libheif-tools poppler-utils python3 python3-devel python3-pip \
  zip unzip rsync xz-devel bzip2-devel zlib-devel libzstd-devel libxml2-devel \
  libcurl-devel libedit-devel fuse3-devel z3-devel ncurses-libs llvm \
  autoconf automake libtool libxml2_2.13 lld
distrobox enter apple-dev -- sudo alternatives --install /usr/bin/ld ld /usr/bin/ld.lld 100
# from your checkout (distrobox keeps the current directory):
distrobox enter apple-dev -- env XCODE_XIP="$HOME/Downloads/Xcode_27.2.xip" ./install-toolchain.sh --mode full
```

Put a swift.org toolchain on PATH before running the installer (mise's `swift`
plugin installs the UBI 9 build). Two Fedora 45 problems break it otherwise,
on the host and in a container alike:

- **`libxml2_2.13`.** The UBI 9 toolchain's `swift-build` and `liblldb.so` link
  `libxml2.so.2`. Fedora 45 ships libxml2 2.15 (`libxml2.so.16`), so the xtool
  build stops with `swift-build: error while loading shared libraries:
  libxml2.so.2`. Fedora's `libxml2_2.13` package installs the real 2.13
  library beside it, which is cleaner than a soname alias.
- **`ld` must be an LLD.** In Swift 6.4, `swift build` uses SwiftBuild, which
  identifies the linker by running `/usr/sbin/ld -version_details` and, when
  that fails, `ld -v`. It accepts only Apple's JSON, `LLD <version>`, `GNU ld
  version <X.Y>-…` or `GNU ld (GNU Binutils…) <X.Y>`. binutils 2.47 prints
  `GNU ld version 2.47.20260726`, with no hyphen, so every build stops with
  ``Could not parse output of `/usr/sbin/ld -version_details` as JSON: GNU ld
  version 2.47.20260726``. Making Fedora's `ld.lld` the `ld` alternative fixes
  it (`LLD 23.1.5 (compatible with GNU linkers)` matches). The probe always
  uses `/usr/sbin/ld`. Putting another `ld` first on PATH or passing
  `-Xswiftc -use-ld=lld` does not change what it runs. `--build-system native`
  avoids the probe but is deprecated.
- After a failed probe, delete the package's `.build/out` before retrying.
  SwiftBuild keeps the failed result in its cached build description, so the
  same error comes back even after `ld` is fixed. For the installer's xtool
  build that directory is
  `~/.cache/omarchy-apple-dev/xtool-<sha>/.build/out`.

Two more things to know:

- distrobox sets `XDG_CONFIG_HOME=$HOME/.config`, so the installer registers
  the SDK in `~/.config/swiftpm/swift-sdks`. A host shell without
  `XDG_CONFIG_HOME` looks in `~/.swiftpm/swift-sdks` and lists no SDK. Run
  builds inside the container, where `ld` is also fixed, or export the same
  `XDG_CONFIG_HOME` on the host.
- The container does not see the host's `usbmuxd` socket, so `idevice_id -l`
  prints `ERROR: Unable to retrieve device list!` there. distrobox mounts the
  host root at `/run/host`. Link the socket once (the link survives
  `distrobox stop`):

  ```sh
  distrobox enter apple-dev -- sudo ln -sfn /run/host/run/usbmuxd /run/usbmuxd
  ```

  `usbmuxd` itself stays on the host, where udev starts it when the iPhone is
  plugged in.

Receipt with the quoted errors and versions:
[`receipts/2026-11-23-fedora-45-asahi-distrobox.md`](../receipts/2026-11-23-fedora-45-asahi-distrobox.md).

## Arch-based distributions

Tested (the home target). `install-toolchain.sh` installs `usbmuxd zip
base-devel git libimobiledevice openssl poppler libheif` with pacman and Swift
from the AUR (`swift-bin`). Other Arch distributions should behave the same
when they have pacman and an AUR helper.
