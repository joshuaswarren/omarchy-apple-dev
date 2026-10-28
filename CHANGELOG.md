# Changelog

## Unreleased

### A signed-app fixture for the profile, seal and extension checks

- `tests/asc/appex-seal.py` runs the signing steps of `ship.sh` (test identity, then `rcodesign` on the extension and the app) on a synthetic app with one app extension, packages the `.ipa` and runs `asc.py validate` on it. Before, the profile, seal and extension paths of `validate` ran only on real apps, because `tests/asc/golden-validate.py` uses an unsigned app and a stub `rcodesign`. Seven rows: the clean case with all eleven extension lines `ok`; then an edited extension `Info.plist`, a file added to the extension, a changed extension executable, the app's profile put in the extension, an edited app `Info.plist` (the extension's seal stays `ok`) and a deleted app profile each fail the line they should. Three mutants (skip the extensions, always pass either sealed-hash check) fail the rows they name.
- The test skips with exit 0 when `rcodesign` or `cryptography` is missing, so `ubuntu-latest` skips it and it runs on a host that has `rcodesign`. It signs with `--timestamp-url none`, so it needs no network; `ship.sh` signs with Apple's timestamp server. The fixture has no asset catalog, so the two `Assets.car` lines fail on every row and the rows ignore them.

### Signing with a given identity and profile

- `flutter/ship.sh` signs with an Apple Distribution identity and an App Store profile it is given when `ASC_PROFILE` is set, with `ASC_SIGNING_KEY` (the path of the PEM private key file) and `ASC_SIGNING_CERT` (the path of its certificate, DER). The new `asc.py given-identity` makes no App Store Connect call and creates no certificate, so a build machine needs neither the API key nor a certificate of its own; before, `asc.py identity` made one per machine, and a team with three machines hit Apple's limit of distribution certificates. The profile must be for the app's bundle id, in the export options' team, and list the certificate, and the key must be the certificate's. An app with extensions is refused, since each extension needs a profile of its own. `ASC_PROFILE` wins over `ASC_KEY_ID`; `--upload` still needs the API key.
- A value that is not a readable file (the key text put in `ASC_SIGNING_KEY` instead of its path, say) stops signing with `ASC_SIGNING_KEY must be the path of a readable file (…); the value is not shown`. Before, the read error's traceback printed the value, so the private key could reach stderr and CI logs.
- `tests/test_given_identity.py` covers the rules offline, with four mutants (a real key pair check runs when `cryptography` is installed); row 8 puts PEM text in `ASC_SIGNING_KEY` and checks the message does not contain it; `tests/flutter-ship/run.sh` row 8 checks that `ship.sh` picks it. Not yet run in a full build.
- The key and certificate links in `ship-signing` could destroy the key. `given-identity` gave the installer the paths it was given, and the installer unlinked `ship-signing/key.pem` and `cert.der` before linking them. If `ASC_SIGNING_KEY` or `ASC_SIGNING_CERT` was that very file, the key was deleted and the link pointed at itself; a second run over the links of the first left links that pointed at themselves (the key itself stayed where it was); and a relative path (`key.pem` in the working directory) became a link that resolved against `ship-signing` and looped. Now the links are absolute, a destination that already is the given file is left alone, a link to something else is replaced, and a regular file that is not the given key or certificate stops the run with its path, replaced by nothing. This is in the shared installer, so `identity` and `test-identity` follow the same rules: they used to replace such a regular file silently. `tests/test_given_identity_install.py` runs the real installer on a real key, certificate and profile (the earlier tests stub it), with three mutants.

### App icon set and storyboards per configuration

- `flutter/build.sh` passed `--app-icon AppIcon` to actool whatever the configuration. It now passes the configuration's `ASSETCATALOG_COMPILER_APPICON_NAME`, expanded (flutter_flavorizr writes `$(ASSET_PREFIX)AppIcon`, one set per flavor). A set the name points at that is not in `ios/Runner/Assets.xcassets` stops the build. A set that lists several sizes builds, with a warning: App Store processing hung on such a set with no error (FINDINGS.md item 68). Flutter's template set lists every size, so the stock template now prints that warning. An empty name builds with no icon, as in Xcode, with a warning.
- Storyboards were the `ios/Runner/Base.lproj/*.storyboard` files. They are now the ones the Runner target's Copy Bundle Resources phase lists (`xcode_settings.py --storyboards`, through `tools/xcodeproj2xtool.py`'s `phase_files`), so a per-flavor launch screen outside `Base.lproj` (flutter_native_splash writes one) is compiled. As in Xcode, a localized storyboard is compiled inside its `X.lproj` and lands there, and one that is not localized lands at the bundle root. Compiling inside `X.lproj` makes the Linux ibtool write a storyboard's strings as localizable, as Apple's does; Flutter's two template storyboards come out byte for byte as before.
- When `Info.plist`'s `UILaunchStoryboardName` (after expansion, so per configuration) names no compiled storyboard, the build stops instead of shipping an app that launches to a black screen.
- `tests/flutter-assets/run.sh` runs the three blocks from `build.sh` with the real `xcode_settings.py` and `tools/ibtool` on the stock and flavored fixtures, with four mutants; row 5 compares the stock storyboards with what the old glob built. The fixtures gained the template's storyboards, `Info.plist` and icon set manifests (no PNGs). Run on macOS and in a Debian trixie container (`tests/run.sh`); not run in a full build, and actool was not run on a per-flavor set.

### Flavors and Dart entry points in Flutter builds

- `flutter/build.sh` reads `FLAVOR` and `TARGET`, the `flutter build ios --flavor` and `-t` options. `FLAVOR` picks the scheme and its Release configuration as Flutter 3.47.6 does (`XcodeProjectInfo.schemeFor` and `buildConfigurationFor`): the scheme is the flavor in sentence case, else the one scheme equal to it ignoring case; the configuration is `Release-<scheme>` ignoring case, else the one whose name contains both "release" and the scheme. No scheme, or none or several configurations, stops the build with the schemes and configurations the project has. Flutter falls back to plain Release with a warning when no configuration matches; this stops instead, since the flavor's bundle id and display name would be lost. The bundle id, minimum iOS, device families and `Info.plist` values then come from that configuration (see "Build settings from the Release configuration").
- `flutter assemble` gets `-dFlavor=<scheme> -dConfiguration=<configuration>`, as Xcode's build phase passes them, so `appFlavor` and flavor-scoped assets work. On a Mac `appFlavor` comes from the configuration's scheme, so the scheme's spelling is passed; where it differs from `FLAVOR` (`prod` and a `Prod` scheme), the build warns, since a Mac would filter flavor-scoped assets by `FLAVOR` as typed.
- The Dart entry point is `TARGET`, else the configuration's `FLUTTER_TARGET` (flutter_flavorizr's xcconfigs set one per flavor), else `lib/main.dart`; a missing file stops the build. A configuration whose `INFOPLIST_FILE` is not `Runner/Info.plist` stops the build too, rather than building with the template's plist. Without `FLAVOR` and `TARGET` the `flutter assemble` call is the same as before.
- `tests/test_xcode_settings.py` rows 7-12 cover the matching on `tests/flutter-configuration/flavors` (written by `make-flavors.py` from the stock template: a flutter_flavorizr layout plus a capitalised scheme, a fuzzy match, two matches and none), with three mutants. `tests/flutter-configuration/run.sh` rows 5-11 run `build.sh`'s block with `FLAVOR` and `TARGET`, with three more mutants. Run on macOS and in a Debian trixie container (`tests/run.sh`); not run in a full build.

### Build settings from the Release configuration

- `flutter/build.sh` read the bundle id, minimum iOS and device families from the first matching line of `project.pbxproj`, whatever its configuration or target, and `flutter/tools/gen-info-plist.py` took the first value in the file for a `$(VAR)` in `Info.plist`. In a project with more configurations (flavors), that could be another configuration's bundle id, silently. Both now read the Runner target's Release configuration through the new `flutter/tools/xcode_settings.py`. It reads `project.pbxproj` with `tools/xcodeproj2xtool.py`'s parser (its `config_layers` takes the configuration name) and applies Xcode's order: the target's settings, then the target's xcconfig, then the project's settings, then the project's xcconfig, with `$(inherited)` taken from the level below and `$(VAR)`s expanded. The xcconfig rules are the ones in "Info.plist values from the app's own xcconfig" below (the reader moved into `xcode_settings.py`), and the xcconfig is the one the configuration names (`Flutter/Release.xcconfig` in Flutter's template).
- What changes for an existing project: only the Release configuration is read, so a value only Debug, Profile or the RunnerTests target set no longer leaks in, and a target's xcconfig now overrides a project-level build setting (before, any build setting won over every xcconfig). A Runner target without a Release configuration stops the build and lists the ones it has. The stock template reads the same values as before: `tests/test_xcode_settings.py` row 1 compares them with the old grep.
- `tests/test_xcode_settings.py` covers the stock template, the four levels, `$(inherited)`, the configuration name, a missing configuration and expansion, with three mutants. `tests/test_gen_info_plist.py` now runs on the `project.pbxproj` `flutter create` writes (Flutter 3.47.6, `tests/flutter-configuration/stock`) and adds four rows. `tests/flutter-configuration/run.sh` runs `build.sh`'s settings block on that template, with one mutant. Run on macOS and in a Debian trixie container (`tests/run.sh`); not run in a full build.

### Info.plist values from the app's own xcconfig

- `flutter/tools/gen-info-plist.py` expands `$(VAR)`s an app defines in an xcconfig that `ios/Flutter/Release.xcconfig` includes, such as the Google Sign-In client id and its reversed URL scheme. Before, they had no value and became empty strings, so `GIDClientID` and the URL scheme were blank and Google sign-in failed at run time. As in Xcode, `//` starts a comment and `$()` is empty (so `https:/$()/host` writes a URL), a later assignment wins, a missing `#include?` file is skipped, an include cycle is cut by file (so `./A.xcconfig` and a symlink count as `A.xcconfig`), a file included again later is read again, `$(inherited)` is dropped, and a build setting in the project overrides the xcconfig, even when it is empty. A setting that refers to itself (`A = $(A)`, or `A = $(B)` with `B = $(A)`) becomes empty with a warning; before, it stopped the tool with a `RecursionError`. An xcconfig that is not UTF-8 is read with replacement characters instead of stopping the tool. Conditional settings (`KEY[sdk=iphoneos*] = …`) are skipped; `flutter/README.md` lists this under Limits.
- `tests/test_gen_info_plist.py` covers includes, comments, precedence (including an empty project setting), an include cycle, value cycles, `$()`, a Latin-1 file and a conditional setting. Checked in a full build on x86_64 Arch: a real app's Google Sign-In ids came out filled in, the build reached VALID in App Store Connect, and sign-in worked from TestFlight.

### xtool installs again on a fresh machine

- `install-toolchain.sh` step 3 stopped with `install: cannot stat '…/libXADI.so'`. The xtool 1.23.0 pin (`f300489`, v0.4.1) no longer has XADI: xtool replaced it with Omnisette ("gsa: use macOS Omnisette", #380). The installer now copies `xtool` alone, then its Swift runtime libraries as before.
- A run that stopped there had already copied `xtool`, so the next run skipped the step and `xtool` failed with `libswiftCore.so: cannot open shared object file`. Step 3 now also rebuilds when `libswiftCore.so` is missing next to `xtool`, which repairs those installs without removing anything by hand.
- Checked on a fresh x86_64 Arch EC2 instance (Swift 6.4.1 from AUR `swift-bin`): a full install to the SDK step, and a re-run with only `xtool` left in the install directory.

## v0.4.2

### A stale Darwin SDK is rebuilt, not skipped

- After the xtool pin moved to 1.23.0 (v0.4.1), a Darwin SDK built by the older xtool stayed registered, and `xtool dev` stopped with "Darwin SDK is out of date, and was installed in 'slim' mode" (reported on issue #78). `install-toolchain.sh` step 6 skipped the SDK whenever `swift sdk list` showed `darwin`, and `--repair` re-registered the cached bundle without looking at it.
- Both now read the SDK stamp (`darwin-sdk-version.txt`) and compare it with `XTOOL_SDK_VERSION`, the stamp the pinned xtool writes. A stale SDK is rebuilt from `XCODE_XIP` or `~/xcode-apple-sdk-src/Xcode.app`. Without either, the script prints why and what to download, and exits 1. A stale cache is no longer re-registered by `--repair`.
- `tests/sdk-state/check.sh` runs the real step 6 and `--repair` blocks against stubs, with two mutants, and with `XTOOL_SRC` set compares `XTOOL_SDK_VERSION` with the pinned xtool source. Not run: a full installer run on Arch, or an SDK rebuild from a real `.xip`.
- When you move `XTOOL_SHA`, move `XTOOL_SDK_VERSION` with it. The test fails if they disagree and `XTOOL_SRC` is set.

## v0.4.1

### xtool 1.23.0 and the password login error

- The installer pins xtool 1.23.0 plus our ten fixes (`joshuaswarren/xtool`, branch `omarchy/1.23.0-fixes`, commit `f300489`). `xtool auth` in password mode no longer fails with `-80045` (issue #78). With a made-up Apple ID the old pin answered `-80045` and the new pin answers `-20970`. The installer was not re-run from scratch on Arch for this change.

### Dart split debug info and obfuscation in Flutter builds

- `flutter/build.sh` reads `SPLIT_DEBUG_INFO=<dir>` and `DART_OBFUSCATION=true`, the `flutter build --split-debug-info` and `--obfuscate` options. They reach `flutter assemble` as the `-dSplitDebugInfo` and `-dDartObfuscation` defines that Flutter's `xcode_backend.dart` passes on a Mac. `app.ios-arm64.symbols` lands in the directory for `flutter symbolize`. Obfuscation without a symbols directory stops the build, as in `flutter build`.
- `tests/flutter-dart-symbols/run.sh` checks the defines with the option block extracted from `build.sh`, with three mutants. Not yet run in a full build.

### Xcode export options for signing

- `ASC_EXPORT_OPTIONS` points `asc.py identity` (so `ship.sh`, `sdk-free/ship.sh` and any script that calls it) at an Xcode `ExportOptions.plist`. `method` must be `app-store-connect` or `app-store`; another method, or none (Xcode's default is `development`), stops signing before any App Store Connect call. `teamID` is checked against each profile's team. `signingCertificate` must name a distribution certificate or be the local certificate's SHA-1.
- `provisioningProfiles` (bundle id to profile name or UUID) picks existing active App Store profiles instead of the ones `asc.py` creates. A picked profile must be for the bundle id, wildcards included, and must list the local Apple Distribution certificate, since rcodesign signs with the local key. Keys that only steer Xcode's export are reported and ignored. `test-identity` checks the method only.
- `tests/test_export_options.py` covers the rules and the identity flow offline, with three mutants.

### Leaving frameworks out of a Flutter build

- `flutter/build.sh` reads `STRIP_FRAMEWORKS`, frameworks to leave out of the app (names without `.framework`, separated by spaces or commas). On a Mac this is an archive strip and an `xcodebuild -exportArchive`; here signing comes later, so `flutter/tools/strip-frameworks.py` removes the directories before `Runner.ipa` is zipped.
- The tool reads the load commands of every image left in the app, thin or fat, and refuses a framework that is still loaded through a non-weak `LC_LOAD_DYLIB`, `LC_REEXPORT_DYLIB` or `LC_LOAD_UPWARD_DYLIB`, naming the loader: dyld would stop the app at launch. A weak load is allowed, and a name that is not in the app is skipped. `tests/test_strip_frameworks.py` covers it with synthetic Mach-O images and three mutants.
- An empty field in `STRIP_FRAMEWORKS` (`A,,B`, `A B,`) is dropped instead of passed on: the tool refuses an empty name, so a trailing separator stopped the build. `tests/test_strip_frameworks.py` runs the parsing block from `build.sh` in bash to hold that.
- Framework checks now resolve `@loader_path` and `@executable_path` loads as well as `@rpath`. Each extension uses its own executable directory. Shared app frameworks are checked against every app and extension executable directory. Regression tests cover both missed load prefixes and shared framework dependencies.

### dSYMs for Flutter builds

- `flutter/build.sh` step 5 writes `build/ios-linux/dSYMs`, one dSYM per Mach-O image in the app, as an Xcode archive does: `App.framework` from `flutter assemble`, `Flutter.framework` from assemble's output or the engine's `Flutter.xcframework`, native assets from their build, Runner and the SwiftPM frameworks and dylibs from SwiftBuild's own dSYM or `dsymutil` on the unstripped product. Before, Runner was stripped and no dSYM was kept, so crashes in native code could not be symbolicated.
- An image with no debug map gets no dSYM and a warning that names it; the build still succeeds. `tests/flutter-dsyms/run.sh` runs the step extracted from `build.sh` on synthetic trees with a stub `dsymutil`, with three mutants. Not yet run in a full build.

### App Store signing for Flutter builds

- `flutter/ship.sh [--upload] <app>` takes the bundle `flutter/build.sh` left in `build/ios-linux/Payload` and runs the App Store steps on a copy: `asc.py stamp` with the build's own `CFBundleVersion` (or `BUILD_NUMBER`), `asc.py frameworks`, the Apple Distribution identity and App Store profile, team-prefix fill, rcodesign inside-out, `asc.py validate` and, with `--upload`, `asc.py upload`. It writes `build/ios-linux/Runner-store.ipa`. The built bundle is not changed.
- `tests/flutter-ship/run.sh` checks the order of the steps, their arguments, the untouched build, a read-only build and a bad team id, with stubbed python and rcodesign. No upload from this script has a receipt yet.

### Offline Assets.car check before any upload

- `tools/car_check.py` checks every `Assets.car` in an `.ipa`: the app, nested `*.bundle` directories, extensions and frameworks. It refuses a car with no renditions. It reads the BOM structure, compares each BITMAPKEYS descriptor with the value Apple derives from the asset's renditions, and compares the TVL row stride with the decoded size of each pixel chunk. It uses only the Python standard library.
- `tools/asc.py upload` runs the check first and stops before any App Store Connect call when a car fails. A direct `asc.py upload` is covered, not only `ship.sh`. `asc.py validate` reports each car as one check.
- The check is not Apple's validator. It matched `assetutil --validate-file` on 55 of 55 retained IceCubes cars. It is stricter in one direction: after `assetutil -U` it still flags retained cars that `assetutil` accepts, for a chunk whose decoded size does not match the TVL stride and for the empty car, so a flag is not an Apple rejection. See `tests/car/README.md`.

## v0.4.0

### Signing with requested capabilities

- Set `ASC_ENTITLEMENTS_PATH` to the app's requested entitlements plist when you run `ship.sh`. The signer copies the exact `applinks:` and `webcredentials:` Associated Domains values, never the profile's wildcard. An App Store profile grants the wildcard as the string `"*"`, and the signer accepts both that form and a list. Signing fails when the profile does not grant the requested domains.
- The same file can request push and Sign in with Apple. Push signs with the environment the profile grants. Sign in with Apple must be requested as `["Default"]` and is signed only when the profile grants `Default`, compared as a whole value. A missing grant stops the signing and names the capability to enable. Only the main app gets these values. Offline verification checks the signed values against the profile and the request. Tests with synthetic profiles are in `tests/test_associated_domains.py`. Not checked on a device: the README says to confirm the HTTPS callback on a signed device build.

### Resource layout in ship.sh

- Step 2 moves the app's `PrivacyInfo.xcprivacy` to the bundle root, next to the storyboards and nibs.
- `ROOT_RESOURCES` is opt-in. It takes space-separated patterns, for example `'*.lproj *.wav'`, and moves only the matching top-level entries of each resource bundle to the app root. It applies to the app and to each extension bundle. Unset, nothing else changes. `tests/ship-root-resources/run.sh` checks this on a synthetic bundle, with three mutants.

### Localized string symbols

- `tools/xcstrings_symbols.py` escapes Swift keywords with backticks, so a key such as `CONTINUE` gives a symbol that compiles. Keys that differ only in case or punctuation get no symbol, and the tool prints one warning per name. The strings stay in the compiled table. Covered by `tests/test_xcstrings_symbols.py`.

### simview M6: keys and text field focus

- The simview frame file gains `key` records (a USB keyboard usage number, page 7) and `text` records (one
  character), and the module gains `TextField` with focus, a caret, and optional `onSubmit`. A completed tap focuses
  a field, a tap elsewhere blurs, and keys with no focus are dropped with a warning line. `simview/test-m6.sh` runs
  seventeen rows and nine mutation checks; see `simview/TESTS-M6.md` and `receipts/2026-10-14-simview-m6.md`.
- The suite now also covers the button case of the end-inside rule: `focusbuttondemo` adds rows 14 to 17, so a
  button tap that lifts outside its target is proven to change neither focus nor state.

### Xcode version from a .xip

- `install-toolchain.sh` reads `Xcode.app/Contents/version.plist` from the `.xip` stream with
  `tools/xip_version.py` (Python standard library only) and records it next to the cached SDK, so `ship.sh`
  stamps `DTXcode` and `DTXcodeBuild` without `XCODE_VERSION` and `XCODE_BUILD`. A missing member or a
  malformed archive records nothing and keeps the old `XCODE_VERSION`/`XCODE_BUILD` message. Covered by
  `tests/test_xip_version.py`, which builds a synthetic `.xip` in the test.

### Tests

- `tests/run.sh` now runs every `tests/test_*.py` unittest file. Before, CI ran none of them, so
  `tests/test_associated_domains.py` and `tests/test_xcstrings_symbols.py` never ran there.

### Findings

- FINDINGS.md gains an entry on linking a Rust static library into an xtool app. The archive holds C members that duplicate symbols in `libclang_rt.ios.a`, and `ld64.lld` rejects the duplicates. The entry gives an `llvm-ar` and `llvm-nm` filter that deletes a member only when every symbol it defines is also defined in `libclang_rt.ios.a`. Reported by a user, not reproduced here. The filter was checked on scratch archives only.

### Venv repair

- `install-toolchain.sh` creates the pymobiledevice3 venv from the resolved interpreter path, not from a
  `latest` symlink, and both step 4 and `--repair` rebuild the venv when its packages no longer import. The
  rebuild removes only the venv directory after a path guard. Covered by stub tests in
  `tests/install-venv/run.sh`; see `receipts/2026-10-13-venv-resolve.md`.

### Device console

- `device-run.sh --rsd` and `--over-tailnet` take `--console [SECONDS]`. After the install it streams the
  app's own output, reports `running after N s: yes/no` and `fatal text seen: yes/no`, then stops the app.
  A fatal line is a report, not an error of the script. A stream from a running app through `--console`
  is not yet proven on a phone. Covered by stub tests in `tests/device-run-console/run.sh`; see
  `receipts/2026-10-12-device-run-console.md`.

### Crash symbolication

- `tools/ips-symbolicate.py` reads a pulled `.ips` crash report on Linux. It matches local Mach-O files by `LC_UUID` and resolves stripped frames from the symbol table. It prints the exception, the termination reason, and the backtraces of the faulting thread and the last exception. See `docs/CRASH-SYMBOLICATION.md` and `receipts/2026-10-12-ips-symbolicate.md`.
- Review fixes for the same tool: frames resolve only against symbols in sections flagged as holding machine instructions, so a data or STAB entry can no longer shadow the nearest function. A fat file can carry arm64 and arm64e slices, and the report UUID is matched against every slice. `swift-demangle` runs once per distinct symbol instead of once per frame. The section count is read from `nsects`, not from `maxprot`, so the last sections of a real library are not dropped. See `receipts/2026-10-12-ips-symbolicate-review.md`.
- `device-run.sh --rsd` and `--over-tailnet` take `--symbolicate [DIR]`. After the launch step it pulls the phone's crash reports and prints each pulled `.ips` through `tools/ips-symbolicate.py` with the app binary and its frameworks. No report for the app: a note and exit 0. A failed pull is the only error. The live run is not yet proven on a phone. Covered by stub tests in `tests/device-run-symbolicate/run.sh`; see `receipts/2026-10-12-device-run-symbolicate.md`.

## v0.3.0

### Simulation research and simview

- M5 adds scripted vertical scrolling. A scripted drag changes the `ScrollView` content offset in our own SwiftUI-like module. The offset clamps at the content bounds. A drag past eight points cancels the row tap.
- This is our scroll model. It does not match Apple's scroll implementation.
- `receipts/2026-10-11-simview-m5.md` records the measurements. The viewport is 390 by 844 points. The demo content is 1103 points high. The offset clamps at 259 points. A 200 point drag matched its golden image with 0 differing pixels.
- The M5 suite passed 7 test rows and 5 mutation checks. Fling, pinch, rotate, and keyboard input stay outside this milestone.

### Continuous integration

- A GitHub Actions workflow runs `bash tests/run.sh` on ubuntu-latest. It runs on pushes to main and on pull requests. The job gets read-only contents permission and no secrets.
- The runner has a Swift compiler, so the four simview suites run and pass there, about 90 seconds in all. Only `compile-golden.sh` skips, because it needs Apple's ibtool. On a host without a Swift compiler, each simview suite skips with exit 0. See `.github/workflows/tests.yml`.

### Tools and distros

- `device-run.sh` and the Flutter install step look up xtool, pymobiledevice3, and ipsw on `PATH`. The lookup runs only when the pinned path holds no executable file. The pinned path stays first when it is executable.
- The Darwin SDK registration check now matches the exact line `darwin`. A broken SDK bundle makes `swift sdk list` print a warning with the same word. The old substring match could wrongly pass on it. See `install-toolchain.sh`.
- `docs/DISTROS.md` adds a NixOS section. The section reports the flake author's own run. This repository holds no run record for it.

### React Native probe

- The abort listed under v0.2.0 happens with the first ipa's JS bundle (built from an older `App.tsx`) and not with a rebuild from the current `App.tsx`. The mechanism is not proven. The rebuild stayed running for 25 seconds in 5 of 5 phone launches. Nobody checked the screen. See `receipts/2026-10-12-rnprobe-stale-bundle.md`.

## v0.2.0

### Build routes

- The README separates no-Xcode and full-mode needs. No-Xcode needs Linux. It needs an iPhone to run apps and an Apple ID to sign them. Setup needs about 7 GB of temporary disk space.
- A run in an Ubuntu 24.04 container now has setup and build results.

### Device run and over-tailnet

- `device-run.sh --over-tailnet` installs and launches an app over the tailnet without a cable. Screenshot and system log need separate `pymobiledevice3` commands. Pair once over USB first. The phone needs Wi-Fi. Cellular-only access failed.
- One debugger run stopped at the app's `main` breakpoint. It took 220 seconds. Earlier tries did not stop there.

### Simulation research and simview

- M1 ran a small arm64 C program through the Linux loader on an arm64 Linux laptop. This proves the loader and its syscall shims. It does not prove Objective-C or Swift support.
- M2 draws a 390 by 844 frame on Linux. It compares the frame with a saved image. This checks one frame. The saved image is the goal.
- M3 adds scripted touch frames and hit testing. It updates `@State` and draws the frame again. It does not support scrolling, gestures, or windows.
- M4 adds a simulated navigation stack. Scripted actions push and pop screens. The recorded run passed seven test rows and five mutation checks.
- Simview uses our own SwiftUI-like module. It does not match Apple's renderer or navigation behavior. This is not full SwiftUI.
- The four stages add one capability at a time. Each stage has limits. All four run on Linux. None uses a Mac.

### React Native probe

- Seven phone launches with no debugger ended in the same abort. The five crash reports show an abort within one second of launch. The Hermes bundle loaded and ran. See `receipts/2026-10-11-rnprobe-launch.md`.
- React Native reported: "Failed to call into JavaScript module method RCTEventEmitter.receiveEvent(). Module has not been registered as callable." The cause is unknown.
- With a debugger attached from launch, the app was still running after 220 seconds. Nobody checked the screen.

### Documentation

- Added `docs/SIM-INPUT-MODEL.md` for scripted input and `docs/OVER-TAILNET.md` for remote device use. `docs/PHONE-NODE.md` is a parked note.
- Updated `docs/IOS-SIMULATION-LINUX.md` with host needs and M1 through M4 findings. `docs/DISTROS.md` links the Ubuntu run at `receipts/2026-10-09-ubuntu-2404.md`.
- The wider device-side SwiftUI declarations include `Color`, `Font`, `padding`, `List`, `ForEach`, and `NavigationLink`. None ran on a phone. The phone SwiftUI stubs do not export `NavigationStack`.

## v0.1.0

First tagged release of omarchy-apple-dev. It added Linux builds for iOS apps without Xcode. It added a portable toolchain, resource tools, project setup, Flutter support, and macOS builds. The release included app and device-run records. The first tag set a baseline.

Five of five files matched the same Xcode output in each of three metadata tests. Some other parts have device records and no offline test suite.
