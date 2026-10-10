# Build and deploy iOS apps on Omarchy Linux (Apple Silicon and x86_64)

[![Sponsor](https://img.shields.io/badge/Sponsor-%E2%9D%A4-pink)](https://github.com/sponsors/joshuaswarren)

SwiftUI and Flutter apps built on Omarchy Linux, installed on a physical iPhone
over USB, with no Xcode and no macOS in the loop.

Any PC that runs Omarchy works: an x86_64 laptop or desktop, or an Apple Silicon Mac.

Current working set, verified 2026-10-03 on x86_64 Arch with the install
script as a fresh user (FINDINGS.md item 22):

| Tool | Version | Source |
|------|---------|--------|
| Swift | 6.4.0 | AUR `swift-bin` |
| xtool | 1.20.1 + 4 fixes (xtool-org/xtool#290-#293) | built from source by the installer |
| pymobiledevice3 | latest from PyPI at install time | venv |
| LLDB | 21.0.0 (Swift toolchain) | bundled with `swift-bin` |
| iOS SDK | iPhoneOS 27.0 | Xcode 27.0 |

The device install and LLDB loop were proven on 2026-09-09 on an M1 with
Swift 6.3.3, xtool 1.19.0 and the iOS 26.5 SDK; they are not yet re-run on
the 6.4 set. Confirmed on x86_64 (community report, Jon Kinney, 2026-09-15):
the same flow works on a Framework Desktop with an iPhone 16, used for a real
client project.

Works with a free Apple ID. Paid membership not required for device installs.

## Flutter apps

Build a Flutter app for an iPhone on Linux and end with a signed development
`.ipa`. Release mode, arm64, verified on x86_64 with Flutter 3.47.6 (receipts:
`receipts/2026-10-08-flutter-signed-ipa.md`).

```
./install-toolchain.sh                    # once, as for any app in this repo
sudo pacman -S --needed llvm rsync        # the two tools the Flutter build calls
flutter/setup.sh                          # once per Flutter version: about 5 minutes

flutter create --platforms ios counter    # or use your own Flutter app
flutter/build.sh counter                  # 29 s for the counter template
                                          # -> counter/build/ios-linux/Runner.ipa (unsigned)

# Sign it with a development profile for your device (App Store Connect API key;
# see GETTING-STARTED.md), then install:
tools/provision-dev.py --bundle-id dev.omarchy.flutterdemo.counter
tools/sign-dev.sh counter/build/ios-linux/Payload/Runner.app Runner-dev.ipa
```

To skip the signing step on a free Apple ID, run `flutter/build.sh --install
counter` instead: `xtool install` signs the app and puts it on the phone.

- **Produces:** `Runner.ipa` (unsigned) from `build.sh`; `Runner-dev.ipa`
  (development-signed, 6 MB for the counter template) from `sign-dev.sh`.
  `tools/asc.py validate` passes 47 of 50 checks on it (the three that fail are
  the App Store-only ones), and `tools/macho-lint.py` reports every Mach-O
  image clean.
- **Needs:** Flutter 3.47.x on `PATH`, the iPhoneOS SDK from the normal install,
  and about 7 GB of disk for the one-time setup, which builds the iOS
  `gen_snapshot` that Flutter ships only for macOS.
- **Times:** setup 5 min 23 s on a 16-core x86_64 machine; the counter template
  builds in 29 s with one plugin. A laptop took about 12 minutes for setup.
- **Limits:** release builds only (no debug, hot reload or simulator). Plugins
  must ship a `Package.swift`. aarch64 hosts are untested. Details:
  [flutter/README.md](flutter/README.md).

Flutter support is the work of [dl-alexandre](https://github.com/dl-alexandre)
(@agrxculture). Thank you for the build pipeline
([#7](https://github.com/joshuaswarren/omarchy-apple-dev/pull/7)), the Linux
`ibtool` for Flutter's storyboards
([#8](https://github.com/joshuaswarren/omarchy-apple-dev/pull/8)) and plugin
package support ([#9](https://github.com/joshuaswarren/omarchy-apple-dev/pull/9)).

## What you need

- An Apple Silicon or x86_64 Linux box running Omarchy (Arch-based). Both
  architectures are covered: AUR `swift-bin` ships aarch64 and x86_64, and the
  installer builds xtool from source on either. Other distributions can work:
  see [docs/DISTROS.md](docs/DISTROS.md) (Ubuntu 24.04 tested in a container).
- An iOS device and a USB cable.
- An Apple ID (free) for **one download from Apple**: `Xcode.xip` from
  developer.apple.com. The download works from any OS — no Mac, no macOS
  install, and no Xcode install anywhere is needed. The iOS SDK artifacts
  exist only inside Apple's Xcode distribution, so this one download is the
  only external requirement that cannot be automated away.

Version matching matters: the SDK pieces must come from an Xcode whose Swift
matches the installed `swift-bin`: **Xcode 27 for swift-bin 6.4** (the
current AUR version), Xcode 26 for 6.3 (FINDINGS.md items 16 and 22). The
install script prints the matching Xcode when it stops at the SDK step.

## Two install modes

`./install-toolchain.sh` asks which mode to use when it runs in a terminal. Pass `--mode full` or `--mode no-xcode`
to skip the question; the last choice is remembered in `~/.config/omarchy-apple-dev/mode`. Without a terminal and
without a choice it uses `full`.

| | **full** (Xcode download) | **no Xcode download** (experimental) |
|---|---|---|
| Languages | Swift, SwiftUI, Objective-C, C, C++ | Objective-C, C and Swift (standard library, async/await, Foundation), plus a small SwiftUI subset (`App`, `WindowGroup`, `Text`, `VStack`, `Button`, `@State`) |
| Flutter | release builds, any plugin whose source builds | release builds with Objective-C plugins and the Swift plugins `shared_preferences` and `url_launcher` |
| System frameworks | everything in the Xcode SDK | a short list (Foundation, UIKit, CoreGraphics, QuartzCore, CoreFoundation, UserNotifications, libc), growing |
| Extensions, widgets, macOS apps | yes | not yet |
| TestFlight and App Store | yes, with a paid account | TestFlight upload of Flutter apps, with a paid account (`sdk-free/ship.sh --upload`); App Store review not tried |
| Needs | the Xcode archive from Apple (about 3 GB of it is used) | an iPhone only to run the apps; setup needs no phone (it reads a connected iPhone or Apple's public iOS update download) and uses about 7 GB of temporary disk |

Details of the second mode are in [sdk-free/README.md](sdk-free/README.md).

## Install

New here? [GETTING-STARTED.md](GETTING-STARTED.md) walks from the Omarchy
Install menu to a TestFlight upload. On Omarchy, **Install > Development > iOS**
runs the steps below for you.

```
git clone https://github.com/joshuaswarren/omarchy-apple-dev
cd omarchy-apple-dev
./install-toolchain.sh
```

The script installs the toolchain, puts the toolchain's own clang first on
PATH for the SDK install, and tells you exactly what is left if anything is.
Safe to re-run. When it stops at the SDK step, download the matching
`Xcode .xip` from https://developer.apple.com/download/all/?q=Xcode and re-run:

```
XCODE_XIP=/path/to/Xcode.xip ./install-toolchain.sh
```

Verify with `swift sdk list` (should print `darwin`).

Already have a Mac with a matching Xcode? You can stream just the ~3 GB of
SDK pieces xtool needs instead of the full .xip — see Route B in
`install-toolchain.sh` section 5. Optional; the .xip route above needs no Mac.

## Toolchain swaps (mise/asdf/manual)

Note on mise: its two swift-backend URL bugs are fixed on mise main
([#13293](https://github.com/jdx/mise/pull/13293),
[#13297](https://github.com/jdx/mise/pull/13297)) but not in a tagged
release as of 2026-09-17. With a build past those, `mise install swift`
does work on Omarchy once you supply three curses sonames Arch names
differently (FINDINGS 21):

```
./install-toolchain.sh --curses-compat
export LD_LIBRARY_PATH=~/.local/lib/curses-narrow-compat
mise install swift@6.3.3
```

`--curses-compat` aliases every narrow curses soname the host is missing to
its wide twin inside `~/.local/lib/curses-narrow-compat` (nothing under
`/usr/lib` is touched) and prints the export line. Pass an extracted
toolchain directory to have it verify that every soname resolves:
`./install-toolchain.sh --curses-compat /path/to/swift-6.3.3-RELEASE-ubi9-aarch64`.
The variable has to be in the shell — mise does not apply `mise.toml`
`[env]` to its post-extract `swift --version` check.

This repo still installs AUR `swift-bin`, which resolves the same thing at
package level and needs no shim.

Swapping the Swift toolchain — `mise use -g swift@<ver>`, an asdf switch, or a
manual reinstall — moves Swift to a different absolute path. That does not
touch what you actually paid for: USB pairing records, your Apple ID auth,
and the SDK cache all live in user-global paths and survive by design.

What survives a swap:

- **Pairing** — `~/.pymobiledevice3/` (+ `/var/lib/lockdown` records).
- **Apple ID auth** — `~/.local/share/xtool/`.
- **SDK cache** — `~/.cache/xtool/darwin-iPhoneOS<ver>.xtoolsdk`, kept by the
  install script. The SDK bundle references the toolchain that registered it,
  so after a swap it must be **re-registered into the current toolchain**:

```
./install-toolchain.sh --repair
```

`--repair` re-registers the cached SDK (no `.xip`, no network) and prints a
survive-status summary: SDK source used, pairing location, auth state. It
exits nonzero with instructions when the cache is missing and no `XCODE_XIP`
is given.

## First app

```
xtool new HelloOmarchy
cd HelloOmarchy
xtool dev run
```

`xtool dev build` alone produces `xtool/HelloOmarchy.app` (arm64 Mach-O).

## Device

Plug the iPhone in, tap Trust when prompted, then:

```
./device-run.sh
```

> **Try Omarchy on Windows:** If this Omarchy installation runs in the virtual
> machine distributed by [tryomarchy.com](https://tryomarchy.com), complete the
> [Windows VM iPhone USB setup](TRYOMARCHY-WINDOWS-USB.md) first. It provides
> working USB passthrough and a patched `usbmuxd` for reliable app installs.
> Bare-metal Omarchy installations do not need that guide.

Wireless deploy is **blocked on iOS 26** for Linux-only setups, tested
exhaustively (FINDINGS.md 17): iOS gives each host its own encrypted
RemotePairing tunnel and offers no way for a Linux host to claim one — a Mac
that once enabled "Connect via Network" holds a working wireless tunnel,
everyone else is refused. USB deploy works everywhere with no Apple-side
gate. When your phone DOES hold a tunnel with some host, `device-run.sh`
documents the pymobiledevice3 tunneld bridge for that case, and
`device-run.sh --rsd` can drive any tunnel endpoint you hold.

## Ship (App Store / TestFlight)

From an xtool project directory:

```
~/omarchy-apple-dev/ship.sh
```

`ship.sh` builds a release `.app`, compiles the app's `AppIcon` set with the
Linux `actool --app-icon` (Xcode's single-size 1024 icon, with its dark and
tinted variants, is expanded to the App Store sizes; `APP_ICON=<name>` picks
another set), stamps the build-environment keys App Store processing reads
(`DTXcode`, `DTSDKName`, …, and a UTC `CFBundleVersion`), wraps each SwiftPM
`.dynamic` product as a `.framework` (App Store processing rejects a loose
`.dylib`), signs it with `rcodesign`, packages `xtool/<App>.ipa`, and
validates the `.ipa` offline: bundle layout, Info.plist keys and version
formats, Mach-O arch and minimum OS, icons in `Assets.car`, profile type and
app id, entitlements, team id, and every sealed hash. Any `FAIL` stops it.
Without an App Store Connect key it signs with a local TEST identity, so the
output proves the pipeline and Apple will reject that signature.

To upload, once:

1. Create an App Store Connect API team key (role App Manager with access to
   Certificates, Identifiers & Profiles, or Admin) and save the `.p8` file
   anywhere you like.
2. Create the app record in App Store Connect (Apps > + > New App). The API
   cannot create apps.

Then:

```
ASC_KEY_PATH=/path/to/AuthKey_XXXXXXXXXX.p8 ASC_ISSUER_ID=<issuer-uuid> ASC_KEY_ID=XXXXXXXXXX \
  ~/omarchy-apple-dev/ship.sh --upload
```

With the key set, `ship.sh` registers the bundle id, creates an Apple
Distribution certificate (the private key stays in
`~/.config/omarchy-apple-dev/distribution/`) and an App Store profile, then
uploads through the App Store Connect build-upload API and prints Apple's
processing result. Builds made this way, entirely on Linux, are `VALID` and
App Store eligible in App Store Connect: the demo app (FINDINGS.md item 38)
and NetNewsWire with its extensions and 15 frameworks (item 40). `ship.sh`
never submits a build for review.

## Real projects

`install-toolchain.sh` also installs Linux stand-ins for Apple's `actool`,
`xcstringstool` and `momc` into the darwin SDK, so packages that declare
`.xcassets`, `.xcstrings` or Core Data resources build, and an OpenAppleMacros
build with SwiftData (`@Model`, `@Query`, …), Foundation (`#Predicate`,
`#Expression`) and `#Preview` macros. Large projects need more open files than
a login shell allows: run `ulimit -n 65536` before `xtool dev build`.

The Linux `actool` compiles imagesets (PNG, JPEG, SVG, PDF, HEIC), colorsets, custom
SF Symbol sets, app icons and Icon Composer `.icon` icons with their layers and
Liquid Glass pre-render (FINDINGS.md); PDF imagesets need poppler's `pdftocairo` and
HEIC images libheif's `heif-convert`, which the installer adds. `tools/ibtool`
compiles storyboards and xibs byte-identical to Xcode 27.0 (all of NetNewsWire's, Flutter's template pair;
`tests/ibtool`); the generator leaves out any it cannot reproduce, with a warning.
Alternate app icons are left out with a warning. `compat/icecubes/`, `compat/nnw/` and `compat/mastodon/`
reproduce IceCubesApp, NetNewsWire and Mastodon for iOS, which build with
their app extensions and are `VALID` in App Store Connect. Mastodon needs two
overlay changes, applied by its setup script (FINDINGS.md item 41).

For your own Xcode project, `tools/xcodeproj2xtool.py App.xcodeproj` writes an
xtool adapter (`omarchy-xtool/`) next to it and prints a warning for each thing
it cannot map (FINDINGS.md item 27).

## Scripts

- `install-toolchain.sh`: everything up to and including the SDK install;
  `--repair` re-registers the cached SDK into the current toolchain after a
  toolchain swap (see *Toolchain swaps* above); `--curses-compat [ROOT]`
  creates the curses sonames a vendor (mise/swift.org) toolchain needs on
  Arch and optionally verifies ROOT resolves; `--user-only` skips every sudo
  step and uses the Swift already on PATH.
- `device-run.sh`: pair, install, launch, LLDB attach; `--network` and
  `--rsd` modes for wireless deploys (unverified). `--lldb` needs no root
  (userspace tunnel; `--sudo` for the old kernel-tunnel path). `LLDB_CMDS`
  runs LLDB commands after the attach, in synchronous mode; `LLDB_LOAD_LEVEL`
  (default `minimal`) trades system-frame symbols for a ~30 s attach. `--attach`
  attaches to the already-running app without reinstalling. usbmuxd 1.1.1
  can abort after a session ends; a `Restart=on-failure` drop-in recovers it
  (FINDINGS.md item 67).
- `ship.sh`: App Store `.ipa` build, offline validation, and `--upload`.
  Helpers: `tools/asc.py` (stamp, identity, validate, upload) and
  `tools/darwin-tools` (the Linux `actool`, on AssetKit) and
  `tools/xcstringstool` (String Catalogs).
- `ship-mac.sh`: macOS `.app` from a SwiftPM package, Developer ID signing,
  and `--notarize` (Apple's notary service, ticket stapled).
- `tools/xcodeproj2xtool.py`: an xtool adapter for an Xcode project's iOS app
  target (`--self-test` checks it).

## Findings

[FINDINGS.md](FINDINGS.md) records the thirty-nine findings behind the working
run: what broke and how each was fixed (SDK install failures, a clang version
mismatch that breaks SwiftUI, the unstated prerequisites for debugging on
iOS 17+), the Swift/Xcode version matrix (items 15-16), why a toolchain
swap breaks SDK registration and how `--repair` restores it (item 19),
the mise/ncurses soname story (items 20-21), the move to xtool 1.20 +
Swift 6.4 + Xcode 27 (item 22), the App Store path (item 23), the
IceCubesApp compatibility run (items 24 and 26), the no-sudo install
(item 25, and on aarch64 in item 28), and the `.xcodeproj` adapter generator
(item 27).

## Notes

- `clang` on PATH must be the Swift toolchain's own clang, not the system
  clang. The SDK install copies the host clang headers into the bundle; a
  version mismatch between host clang and the Swift compiler produces
  `__builtin_bit_cast` size errors when compiling SwiftUI. Both scripts in
  this repo put it first on PATH themselves; in your own shell use
  `PATH="$(dirname "$(readlink -f "$(command -v swift)")"):$PATH"`.
- Building SwiftUI pulls in simd/arm_neon headers; first build takes about a
  minute on an M1.

## Support

Every bit of support helps keep omarchy-apple-dev alive and free. If you are able, [sponsor on GitHub](https://github.com/sponsors/joshuaswarren) or send a Lightning donation to `joshuaswarren@strike.me` to directly fund continued development and new integrations.

[![Sponsor](https://img.shields.io/badge/Sponsor-%E2%9D%A4-pink?style=for-the-badge)](https://github.com/sponsors/joshuaswarren)

If financial support is not an option, you can still make a big difference: [star the repo](https://github.com/joshuaswarren/omarchy-apple-dev), share it, or recommend it to a colleague. Word of mouth is how most people find omarchy-apple-dev.

## License

MIT