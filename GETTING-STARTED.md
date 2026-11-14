# Getting started: from the Omarchy menu to TestFlight

This guide takes a new user from a fresh Omarchy install to an app build in
TestFlight. Each step names the command to run and what you should see. The
README has the details and FINDINGS.md has the reasons.

What you need:

- Omarchy on Apple Silicon or x86_64.
- A free Apple ID, to download Xcode once (no Mac needed).
- For TestFlight: a paid Apple Developer account and an App Store Connect API key.
- For device runs: an iPhone and a USB data cable.

## 1. Install the toolchain

1. Open the Omarchy menu and select **Install > Development > iOS (Swift + xtool)**.
   From a terminal, `omarchy-install-dev-env ios` does the same thing.
2. The installer installs Swift and builds xtool from source (about 7 minutes
   on a 16-core x86_64 machine, about 11 minutes on an M1).
3. The installer then stops at the SDK step and prints a download link. Sign in
   with your Apple ID and download the Xcode `.xip` that it names (Xcode 27 for
   Swift 6.4).
4. Run the installer again with the download:

   ```
   XCODE_XIP=~/Downloads/Xcode_27.0.xip ~/.local/share/omarchy-apple-dev/install-toolchain.sh
   ```

5. This run registers the SDK and builds the Swift macro server (about 5
   more minutes). Check the result: `swift sdk list` prints `darwin`. The Install row in the
   menu is now dimmed and **Remove > Development > iOS** is shown.

No sudo? Clone the repo and run `./install-toolchain.sh --user-only` with a
swift.org toolchain on PATH (README, "Install"). An admin must first install
`base-devel git libimobiledevice openssl zip`.

## 2. Build an app

A new app:

```
xtool new MyApp
cd MyApp
xtool dev build
```

You should see `Build complete!` and `xtool/MyApp.app`.

An existing Xcode project:

```
python3 ~/.local/share/omarchy-apple-dev/tools/xcodeproj2xtool.py MyApp.xcodeproj
cd omarchy-xtool
ulimit -n 65536
xtool dev build
```

The generator writes the xtool adapter next to the project. It prints one
`warning:` line for each thing it cannot convert. Interface Builder files the
Linux `ibtool` compiles ship as normal resources; the rest are excluded with
a warning that names them. Read those lines before you continue.

To edit the code, open the folder of the `.xcodeproj` (or `omarchy-xtool`) in
any editor with SourceKit-LSP, for example VS Code with the Swift extension or
Neovim. The generator writes `.bsp/xtool.json` next to the project, and
`xtool dev build` writes one in `omarchy-xtool`. The editor then gets
diagnostics, completion, hover and go to definition across the app, its
frameworks, the iOS SDK and package dependencies. The first open indexes the
whole project; cross-file results appear when that ends.

## 3. Run it on your iPhone

1. Run `xtool auth` once and sign in with your Apple ID.
2. Plug in the iPhone and tap **Trust**.
3. Run `~/.local/share/omarchy-apple-dev/device-run.sh` from the project
   directory. It installs and starts the app. With `--lldb` it installs the
   app, mounts the developer disk image, copies the phone's Swift runtime once
   (a few GB) and attaches LLDB, so `frame variable` shows Swift values.
   `LLDB_CMDS` (one command per line) scripts the session, and
   `LLDB_PYTHONHOME` names a CPython 3.12 when the system has none
   (FINDINGS.md 56, receipt `receipts/2026-10-07-device-run-lldb.md`).
4. The dev build leaves most resources inside the SwiftPM resource bundle,
   where only `Bundle.module` finds them; an app that reads themes, RTF or JSON
   through `Bundle.main` traps at launch. `ship.sh --device` (with your
   10-character team id when the app reads `$(AppIdentifierPrefix)`) rebuilds
   with every resource at the bundle roots, like Xcode; install the result
   with `xtool install xtool/<App>.app` (FINDINGS.md 63).
   No xtool on the machine that holds the phone? `tools/sign-dev.sh App.app
   out.ipa` signs the result with your development identity and profiles
   (`tools/provision-dev.py`), and `pymobiledevice3 apps install out.ipa`
   installs it. `CONFIGURATION=debug ship.sh --device` builds the debug app
   for LLDB.

## 4. Upload to TestFlight

Do this setup once:

1. In App Store Connect, go to Users and Access > Integrations and create a
   team API key with the App Manager role. Download the `.p8` file and keep it
   in a private directory, for example `~/.appstoreconnect/private_keys/`.
2. Note the Key ID and the Issuer ID from the same page.
3. Create the app record (Apps > + > New App) with your bundle ID. The API
   cannot create apps.

Then, from the project directory:

```
ASC_KEY_PATH=~/.appstoreconnect/private_keys/AuthKey_XXXXXXXXXX.p8 \
ASC_ISSUER_ID=<issuer id> ASC_KEY_ID=XXXXXXXXXX \
  ~/.local/share/omarchy-apple-dev/ship.sh --upload
```

`ship.sh` builds a release `.app` and compiles the app icon. It creates your
Apple Distribution certificate and an App Store profile on the first run. It
then signs the app and checks it offline, and any `FAIL` stops it. Last, it
uploads the `.ipa` and prints Apple's processing result. When the result is
`COMPLETE`, the build appears in TestFlight after Apple's processing. `ship.sh`
never submits a build for review.

This path is proven: a demo app and NetNewsWire, with its widget and share
extensions, were built, signed and uploaded this way on Linux, and both are
`VALID` in App Store Connect (FINDINGS.md items 38 and 40).

## 5. A Mac app

For a SwiftPM package with one executable product (a SwiftUI or AppKit app),
from the package directory:

```
ASC_KEY_PATH=~/.appstoreconnect/private_keys/AuthKey_XXXXXXXXXX.p8 \
ASC_ISSUER_ID=<issuer id> ASC_KEY_ID=XXXXXXXXXX BUNDLE_ID=com.example.MyMacApp \
  ~/.local/share/omarchy-apple-dev/ship-mac.sh --notarize
```

It builds `build/MyMacApp.app` for Apple Silicon, signs it with your Developer
ID Application certificate, and notarizes it. Only the Account Holder can
create that certificate in the developer portal: upload a CSR, and put the
key and certificate as `key.pem` and `cert.pem` in
`~/.config/omarchy-apple-dev/developer-id/`. Without `--notarize` and without
the certificate, the app is signed ad hoc and is not notarized for distribution.
FINDINGS.md item 57 has the details.

## Toolchain swaps (mise, asdf, manual)

A toolchain swap changes Swift's path. Pairing, auth and the SDK cache are
stored outside that toolchain: USB pairing in `~/.pymobiledevice3/` (plus
`/var/lib/lockdown` records), Apple ID auth in `~/.local/share/xtool/`, and
the SDK in `~/.cache/xtool/darwin-iPhoneOS<ver>.xtoolsdk`. Re-register a
current SDK cache into the new toolchain:

```
~/.local/share/omarchy-apple-dev/install-toolchain.sh --repair
```

`--repair` re-registers a current cached SDK without an `.xip` and prints
SDK, pairing and auth status. Missing tools or dependencies may be downloaded.
It exits nonzero with instructions when the cache is missing and no `XCODE_XIP`
is given. An SDK built by an older xtool is stale (xtool stamps each SDK it
builds, and `xtool dev` refuses a different stamp), so it is rebuilt from
`XCODE_XIP` or `~/xcode-apple-sdk-src/Xcode.app`, not re-registered; the
script stops with instructions if neither exists. `--repair` also rebuilds the
pymobiledevice3 venv in `~/pymobile3-venv` when its packages no longer import.

On mise specifically: `mise install swift` needs the curses compat shim on
Arch. Its two swift-backend URL bugs are fixed on mise main
([#13293](https://github.com/jdx/mise/pull/13293),
[#13297](https://github.com/jdx/mise/pull/13297)) but not in a tagged release
as of 2026-09-17:

```
~/.local/share/omarchy-apple-dev/install-toolchain.sh --curses-compat
export LD_LIBRARY_PATH=~/.local/lib/curses-narrow-compat
mise install swift@<version>
```

`--curses-compat` aliases every narrow curses soname the host is missing to
its wide twin inside `~/.local/lib/curses-narrow-compat` (nothing under
`/usr/lib` is touched) and prints the export line, which has to be set in the
shell that runs mise; mise's own `[env]` never reaches its post-extract
`swift --version` check. Pass an extracted toolchain directory to have it
verify that every soname resolves. This repo's own route, AUR `swift-bin`,
needs none of this.

## If something fails

- `Too many open files`: run `ulimit -n 65536` first.
- After a Swift toolchain swap (mise, asdf), run `install-toolchain.sh --repair`.
- Search FINDINGS.md for the exact error text. Most of the errors met so far
  are listed there with their cause and fix.

## Remote iPad screen and control

For a USB iPad on another tailnet host, use [ipad-screen](docs/IPAD-SCREEN.md)
for a password-protected HTTPS viewer, start/stop/status, and an optional user
service. It mirrors and controls without building on the device host.
