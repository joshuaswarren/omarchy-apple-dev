# Build and deploy iOS apps on Omarchy Linux (Apple Silicon and x86_64)

SwiftUI and Flutter apps built on Omarchy Linux and installed on a physical
iPhone: over USB, or over your tailnet on iOS 27. No Xcode and no macOS in
the loop. A free Apple ID covers device installs; a paid developer account
adds TestFlight and the App Store.

## What was verified, and when

| Date | What ran | Evidence |
|------|----------|----------|
| 2026-10-03 | Fresh-user install on x86_64 Arch: Swift 6.4.0, xtool 1.20.1, Xcode 27.0 SDK | [FINDINGS.md](FINDINGS.md) item 22, [receipt](receipts/2026-10-03-xtool-1.20-swift-6.4-x86_64.md) |
| 2026-10-23 | xtool 1.23.0 with made-up credentials: password auth changed from -80045 to Apple's invalid-credential -20970. No real-Apple-ID sign-in, SDK build, device install or LLDB loop on this version | [receipt](receipts/2026-10-23-xtool-1.23.0-auth.md) |
| 2026-10-25 | Fresh x86_64 Arch install through the SDK-download step, plus interrupted-xtool-install repair with Swift 6.4.1. No SDK build, device install or LLDB loop | [CHANGELOG.md](CHANGELOG.md), *xtool installs again on a fresh machine* |
| 2026-09-09 | Device install and the LLDB loop on an M1, with Swift 6.3.3, xtool 1.19.0 and the iOS 26.5 SDK. Not re-run on the 6.4 set | [FINDINGS.md](FINDINGS.md), *Working sequence* |
| 2026-09-15 | x86_64 flow confirmed by a community report (Jon Kinney); the same flow runs a real client project on a Framework Desktop with an iPhone 16 | none |

| Tool | Version | Source |
|------|---------|--------|
| Swift | 6.4.1 in the latest fresh-install check | AUR `swift-bin` |
| xtool | 1.23.0 + 10 fixes (fork pin `f300489`; xtool-org/xtool #290-#293, #295, #302 still open upstream) | built from source by the installer |
| pymobiledevice3 | latest from PyPI at install time | venv |
| cryptography | 42 or later; a dependency of pymobiledevice3, in the same venv. `tools/asc.py identity` and `test-identity` stop with a message naming the version if it is older | venv |
| LLDB | bundled with the installed Swift toolchain | `swift-bin` |
| iOS SDK | iPhoneOS 27.0 | Xcode 27.0 (full mode); in no-Xcode mode, link stubs cut from a connected iPhone or Apple's public iOS update |

## Two install modes

`./install-toolchain.sh` asks which mode to use when it runs in a terminal.
Pass `--mode full` or `--mode no-xcode` to skip the question; the choice is
remembered in `~/.config/omarchy-apple-dev/mode`. Without a terminal and
without a choice it uses `full`.

| | **full** (Xcode download) | **no Xcode download** (experimental) |
|---|---|---|
| Languages | Swift, SwiftUI, Objective-C, C, C++ | Objective-C, C and Swift (standard library, async/await, Foundation), plus a small SwiftUI subset (`App`, `WindowGroup`, `Text`, `VStack`, `Button`, `@State`) |
| Flutter | release builds, any plugin whose source builds | release builds with Objective-C plugins and the Swift plugins `shared_preferences` and `url_launcher` |
| System frameworks | everything in the Xcode SDK | Foundation, UIKit, CoreGraphics, QuartzCore, CoreFoundation, UserNotifications, libc; a short list, growing |
| Extensions, widgets, macOS apps | yes | not yet |
| TestFlight and App Store | yes, with a paid account | TestFlight upload of Flutter apps, with a paid account (`sdk-free/ship.sh --upload`); App Store review not tried |
| Needs | the Xcode archive from Apple (about 3 GB of it is used) | an iPhone only to run the apps; setup reads a connected iPhone or Apple's public iOS update download and uses about 7 GB of temporary disk |

What has run on an iPhone and what only builds (no-Xcode mode):
[docs/TEST-MATRIX.md](docs/TEST-MATRIX.md). Mode internals:
[sdk-free/README.md](sdk-free/README.md).

## Requirements

- Omarchy or another Arch-based Linux on Apple Silicon or x86_64. Other
  distributions: Ubuntu 24.04 and Fedora 44 have verified runs, NixOS a
  reported one. See [docs/DISTROS.md](docs/DISTROS.md).
- An iPhone and a USB data cable.
- A free Apple ID for **one download from Apple**: the `Xcode.xip` from
  developer.apple.com (full mode). The download works from any OS; no Mac, no
  macOS and no Xcode install anywhere. The iOS SDK artifacts exist only inside
  Apple's Xcode distribution, so this one download cannot be automated away.
- For TestFlight and App Store: a paid developer account.

Version matching matters. The SDK must come from an Xcode whose Swift matches
the installed `swift-bin`: **Xcode 27 for swift-bin 6.4**, Xcode 26 for 6.3
(FINDINGS.md items 16 and 22). The installer prints the matching Xcode when it
stops at the SDK step.

## Install

New here? [GETTING-STARTED.md](GETTING-STARTED.md) walks from the Omarchy
Install menu to a TestFlight upload. On Omarchy, **Install > Development >
iOS** runs these steps for you.

```
git clone https://github.com/joshuaswarren/omarchy-apple-dev
cd omarchy-apple-dev
./install-toolchain.sh
```

The script installs Swift and builds xtool, then stops at the SDK step and
names the Xcode to download. Download that `.xip` from
<https://developer.apple.com/download/all/?q=Xcode> and re-run:

```
XCODE_XIP=/path/to/Xcode.xip ./install-toolchain.sh
```

`swift sdk list` should print `darwin` when the SDK is registered. Re-run the
installer after toolchain changes: it checks the SDK stamp, not just that name.

- No sudo? `./install-toolchain.sh --user-only` with a swift.org toolchain on
  PATH.
- Already have a Mac with a matching Xcode? Route B in `install-toolchain.sh`
  step 5 copies just the ~3 GB of SDK pieces instead of the whole `.xip`.
  Optional; the `.xip` route needs no Mac.
- After a Swift toolchain swap (mise/asdf/manual), run
  `./install-toolchain.sh --repair`. See
  [GETTING-STARTED.md](GETTING-STARTED.md), *Toolchain swaps*.

### Optional Tomacco frontend

Tomacco is a separate application. This repository does not download, bundle,
install, or start it. The optional registration accepts the evaluated
Tomacco 1.0.0 x86_64 binaries from source commit
`84f877eb34fb202384010afb5f54c0da7fea892f`; other builds fail the hash check.
Keep its dependencies, license notices, and corresponding source available
under its own installation procedure.

After installing that version separately, run these commands from this checkout:

```sh
python3 tools/tomacco-frontend.py enable "$HOME/.local/lib/tomacco"
python3 tools/tomacco-frontend.py status
```

This adds **iOS development (Tomacco)** to the application menu. It does not
change **Install > Development > iOS** or either toolchain install mode.
The menu command checks both binary hashes again before launch. It preserves
your HOME and XDG directories, and uses the PATH from registration.
Keep this checkout in place; register again if you move it.

Registration writes each file through an exclusive temporary file in the same
directory. It sets permissions before publication and uses atomic replacement.
If publication stops between config and menu updates, rerun `enable` or use
`disable`. Recovery accepts the original menu file only while its identity,
timestamps, size and hash remain unchanged. Restoring old bytes after replacement
does not restore ownership. Unrelated or edited entries stop the operation.

Use Tomacco's ordinary xtool project workflow with the existing toolchain and
sign-in. Existing explicit Tomacco executable settings still take precedence.
Do not use `ios.toolkit_install`: that separate upstream adapter creates a
private toolkit and HOME. Its Flutter, Xcode-import and store adapters are
not connected to this registration. No device, SDK build, sign-in, or desktop
rendering has been qualified by the registration tests.

To remove only this registration:

```sh
python3 tools/tomacco-frontend.py disable
```

Removal preserves Tomacco, its data, the toolchain, SDKs, and credentials.
It refuses to overwrite or remove a desktop entry you changed.
This option supplies no Apple SDK, firmware, emulator, or Apple-terms acceptance.
Optional registration does not establish permission to use or distribute
Apple materials. No emulator-engine distribution is approved here.

## First app

```
xtool new HelloOmarchy
cd HelloOmarchy
xtool dev run
```

`xtool dev build` alone produces `xtool/HelloOmarchy.app` (arm64 Mach-O).
An existing Xcode project: `tools/xcodeproj2xtool.py App.xcodeproj` writes an
xtool adapter next to it, with SourceKit-LSP support. See
[GETTING-STARTED.md](GETTING-STARTED.md), step 2.

## Run on your iPhone

Plug the iPhone in, tap **Trust** when prompted, then, from the project
directory:

```
./device-run.sh
```

`device-run.sh` pairs, installs and launches the app. `--lldb` attaches LLDB
without root. With `--rsd` or `--over-tailnet`, `--console [SECONDS]` streams
the app's own output and `--symbolicate` pulls and resolves crash reports
([docs/CRASH-SYMBOLICATION.md](docs/CRASH-SYMBOLICATION.md)).

Use USB for initial pairing. The Linux wireless RemotePairing path is
blocked on iOS 26 (FINDINGS.md item 17). On iOS 27, pair once over USB and
copy the pairing record to the host on your tailnet. With Wi-Fi and
Tailscale connected on the phone, that host can install, launch, screenshot
and read logs without a cable
([docs/OVER-TAILNET.md](docs/OVER-TAILNET.md), measured 2026-10-10).

Pairing records are device credentials. Keep them private and copy them
only to hosts you trust.

> Running Omarchy in the [tryomarchy.com](https://tryomarchy.com) Windows VM?
> Do the [Windows VM iPhone USB setup](TRYOMARCHY-WINDOWS-USB.md) first.
> Bare-metal installs do not need it.

## Flutter apps

Verified on x86_64 with Flutter 3.47.6
([receipt](receipts/2026-10-08-flutter-signed-ipa.md)). Release mode, arm64
device builds only: no debug, hot reload or simulator. Plugins must ship a
`Package.swift`. aarch64 hosts are untested. Details:
[flutter/README.md](flutter/README.md).

```
./install-toolchain.sh                    # once, as for any app in this repo
sudo pacman -S --needed llvm rsync        # the two tools the Flutter build calls
flutter/setup.sh                          # once per Flutter version: ~7 GB, 5-12 min

flutter create --platforms ios counter    # or use your own Flutter app
flutter/build.sh counter                  # -> build/ios-linux/Runner.ipa (unsigned), 29 s for the template

flutter/build.sh --install counter        # free Apple ID route: xtool signs and installs
```

For a signed development `.ipa` for a specific device:
`tools/provision-dev.py --bundle-id <id>` then
`tools/sign-dev.sh <App>.app out.ipa`. For the App Store and TestFlight:
`flutter/ship.sh --upload counter` (same key variables as `ship.sh --upload`
below).

Flutter support is the work of
[dl-alexandre](https://github.com/dl-alexandre) (@agrxculture). Thank you for
the build pipeline ([#7](https://github.com/joshuaswarren/omarchy-apple-dev/pull/7)),
the Linux `ibtool` for Flutter's storyboards
([#8](https://github.com/joshuaswarren/omarchy-apple-dev/pull/8)) and plugin
package support ([#9](https://github.com/joshuaswarren/omarchy-apple-dev/pull/9)).

## Ship to TestFlight and the App Store

Once: create an App Store Connect API team key (role App Manager with access
to Certificates, Identifiers & Profiles) and keep the `.p8` private; create
the app record in App Store Connect (Apps > + > New App; the API cannot
create apps). Then, from an xtool project directory:

```
ASC_KEY_PATH=/path/to/AuthKey_XXXXXXXXXX.p8 ASC_ISSUER_ID=<issuer-uuid> ASC_KEY_ID=XXXXXXXXXX \
  ~/omarchy-apple-dev/ship.sh --upload
```

`ship.sh` builds a release `.app`, compiles the app icon, registers the bundle
id, creates an Apple Distribution certificate (the private key stays in
`~/.config/omarchy-apple-dev/distribution/`) and an App Store profile, signs
with `rcodesign`, validates the `.ipa` offline (any `FAIL` stops it), uploads
and prints Apple's processing result. It never submits a build for review.

Without a key it signs with a local TEST identity. That proves the pipeline
only; Apple rejects the signature.

Proven: builds made entirely on Linux are `VALID` in App Store Connect, for
the demo app (FINDINGS.md item 38) and for NetNewsWire with its extensions and
15 frameworks (item 40). Signing details, covering entitlements (Associated
Domains, push, Sign in with Apple), `ROOT_RESOURCES` and Xcode
`ExportOptions.plist`, are in [docs/SHIPPING.md](docs/SHIPPING.md).

## Real projects

The installer puts Linux stand-ins for Apple's `actool`, `xcstringstool` and
`momc` into the SDK, so packages declaring `.xcassets`, `.xcstrings` or Core
Data resources build. The Linux `ibtool` compiles NetNewsWire's storyboards
and Flutter's two template storyboards byte-identical to Xcode 27.0.
[compat/icecubes/](compat/icecubes/), [compat/nnw/](compat/nnw/) and
[compat/mastodon/](compat/mastodon/) build IceCubesApp, NetNewsWire and
Mastodon for iOS with their app extensions, all `VALID` in App Store Connect.
Large projects need `ulimit -n 65536` before `xtool dev build`.

## Scripts

- `install-toolchain.sh`: toolchain and SDK install. `--repair`,
  `--user-only`, `--curses-compat`.
- `device-run.sh`: pair, install, launch, LLDB, console, crash pull; `--rsd`
  and `--over-tailnet` for tunnel installs.
- `ship.sh`: App Store `.ipa`, offline validation, `--upload`. Helpers:
  `tools/asc.py`, `tools/darwin-tools`, `tools/xcstringstool`.
- `ship-mac.sh`: macOS `.app` from a SwiftPM package, Developer ID signing,
  `--notarize`.
- `tools/xcodeproj2xtool.py`: xtool adapter for an Xcode project.
- `tools/ips-symbolicate.py`: resolve a pulled `.ips` crash report on Linux.

## Documentation

- [GETTING-STARTED.md](GETTING-STARTED.md): from the Omarchy menu to
  TestFlight, including toolchain swaps and common failures.
- [docs/TEST-MATRIX.md](docs/TEST-MATRIX.md): what ran on an iPhone vs what
  only builds.
- [docs/OVER-TAILNET.md](docs/OVER-TAILNET.md): cable-free deploys on iOS 27.
- [docs/SHIPPING.md](docs/SHIPPING.md): `ship.sh` signing options.
- [docs/DISTROS.md](docs/DISTROS.md): Ubuntu, Fedora, NixOS.
- [docs/CRASH-SYMBOLICATION.md](docs/CRASH-SYMBOLICATION.md): reading crash
  reports on Linux.
- [sdk-free/README.md](sdk-free/README.md): the no-Xcode mode.
- [flutter/README.md](flutter/README.md): the Flutter pipeline.
- [FINDINGS.md](FINDINGS.md): dated findings and fixes, with supporting
  test records under `receipts/`.

## Notes

- The `clang` on PATH must be the Swift toolchain's own, not the system clang;
  a version mismatch breaks SwiftUI with `__builtin_bit_cast` errors. Both
  scripts in this repo put it first on PATH themselves. In your own shell:
  `PATH="$(dirname "$(readlink -f "$(command -v swift)")"):$PATH"`.

## Support

omarchy-apple-dev is free. If it helps you,
[sponsor the project](https://github.com/sponsors/joshuaswarren) or send
Lightning to `joshuaswarren@strike.me`.

## License

MIT
