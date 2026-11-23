# Flutter apps for iOS, built on Linux

`flutter build ios` needs Xcode. These scripts build a Flutter app for a
physical iPhone or iPad on Omarchy with no Mac and no Xcode, on top of the
toolchain `install-toolchain.sh` sets up, and hand the result to
`xtool install`.

Verified 2026-10-08 on x86_64 with Flutter 3.47.6, swift-bin 6.4.0, the
iPhoneOS 27.0 SDK and an iPad on iPadOS 27.0
(receipt `receipts/2026-10-08-flutter-ios.md`). Release mode, arm64 device builds only.
aarch64 hosts are untested.

## Use

```
./install-toolchain.sh            # once, as for any app in this repo
sudo pacman -S --needed llvm      # llvm-strip, llvm-lipo, llvm-otool, llvm-install-name-tool, llvm-ar
flutter/setup.sh                  # once per Flutter version (7 GB, 12 min here)
flutter/build.sh --install /path/to/flutter/app [KEY=VALUE ...]
flutter/ship.sh [--upload] /path/to/flutter/app   # App Store signing, validation, upload
```

The `llvm` package is the one dependency `install-toolchain.sh` does not
bring: the shims forward to its binutils, and neither the Swift toolchain nor
the darwin SDK bundle ships them. `flutter assemble` also calls `rsync`, which
a minimal Arch install lacks. `build.sh` names whatever is missing before it
starts.

`KEY=VALUE` arguments become `--dart-define`s. Without `--install` the result
is `<app>/build/ios-linux/Runner.ipa`, unsigned, for `xtool install` or
`ship.sh`-style signing. The bundle id, minimum iOS and version come from the
Release configuration of the Runner target in `ios/Runner.xcodeproj` (with its
xcconfig) and from `pubspec.yaml`; `BUNDLE_ID`, `MIN_IOS`, `BUILD_NAME` and
`BUILD_NUMBER` override them. `tools/xcode_settings.py` reads the settings in
Xcode's order: the target's, its xcconfig's, the project's, then the project's
xcconfig's.

`FLAVOR=<name>` and `TARGET=<file>` are `flutter build ios --flavor` and
`-t`. `FLAVOR` picks the scheme and its Release configuration with Flutter's
own matching (the flavor in sentence case, then `Release-<scheme>`, ignoring
case, then the one configuration whose name holds both), and the bundle id,
minimum iOS and `Info.plist` values come from that configuration. No match, or
more than one, stops the build with the schemes and configurations the project
has. `flutter assemble` gets `-dFlavor=<scheme>` and
`-dConfiguration=<configuration>`, as on a Mac. The Dart entry point is
`TARGET`, else the configuration's `FLUTTER_TARGET`, else `lib/main.dart`.

The app icon set is the configuration's `ASSETCATALOG_COMPILER_APPICON_NAME`
(a missing set stops the build; one that lists several sizes gets a warning),
and the storyboards are the ones the Runner target's
Copy Bundle Resources phase lists: localized ones in their `X.lproj`, the rest
at the bundle root. A launch screen `Info.plist` names that is not among them
stops the build.

`SPLIT_DEBUG_INFO=<dir>` and `DART_OBFUSCATION=true` are `flutter build
--split-debug-info=<dir>` and `--obfuscate`: they reach `flutter assemble` as
the same `-dSplitDebugInfo` and `-dDartObfuscation` defines Xcode's build
phase passes, so the Dart snapshot is built with `--dwarf-stack-traces` and
`app.ios-arm64.symbols` lands in the directory for `flutter symbolize`. A
relative directory is taken from where `build.sh` runs. Obfuscation without
`SPLIT_DEBUG_INFO` stops the build, as it does in `flutter build`.

`STRIP_FRAMEWORKS="Name Other"` leaves `Name.framework` and
`Other.framework` out of the app (names without `.framework`, separated by
spaces or commas): the step a Mac build does with an archive strip and an
`xcodebuild -exportArchive`. Here the app is signed afterwards, so
`tools/strip-frameworks.py` only removes the directories. It refuses a
framework that the rest of the app still loads (a non-weak `LC_LOAD_DYLIB`,
`LC_REEXPORT_DYLIB` or `LC_LOAD_UPWARD_DYLIB`), since dyld would stop the
app at launch, and it names the image that loads it. The check resolves
`@loader_path` from the loading image and `@executable_path` from its app
or extension bundle. Shared app frameworks are checked against all app and
extension executable directories, so a possible hard load blocks removal.
`@rpath` loads are checked against the app `Frameworks` directory.
A name that is not in the app is reported and skipped.

`build/ios-linux/dSYMs` holds a dSYM for each Mach-O image in the app, as
an Xcode archive's `dSYMs` folder does, for Crashlytics, Sentry or App Store
Connect symbolication: `App.framework` from `flutter assemble`,
`Flutter.framework` from the engine artifacts, native assets from their
build, and Runner and the SwiftPM frameworks from SwiftBuild or `dsymutil` on
the unstripped products. A prebuilt binary with no debug map (a binary
target such as an `.xcframework`) gets none; the build names it in a warning
and goes on. `dsymutil` output is in `build/ios-linux/dsymutil.log`.

`ship.sh` takes the bundle `build.sh` left in `build/ios-linux/Payload` and
runs the App Store steps of the top-level `ship.sh` on a copy of it: `asc.py
stamp` (the version `build.sh` wrote is kept unless `BUILD_NUMBER` is set),
`asc.py frameworks`, the Apple Distribution identity and App Store profile,
rcodesign inside-out, then `asc.py validate` on
`build/ios-linux/Runner-store.ipa`. With `--upload` it uploads through the
App Store Connect build-upload API. It needs the same `ASC_KEY_ID`,
`ASC_ISSUER_ID` and `ASC_KEY_PATH` as `ship.sh --upload` and the app record
created once in App Store Connect; without `ASC_KEY_ID` it signs with the
TEST identity, which Apple rejects. `ASC_ENTITLEMENTS_PATH` requests push,
Sign in with Apple and Associated Domains as for `ship.sh`; when it is unset,
the `CODE_SIGN_ENTITLEMENTS` file of the configuration `build.sh` built does
(`build/ios-linux/configuration` records it), so each flavor signs with its own.
`ASC_SIGNING_KEY` (the path of the PEM private key file), `ASC_SIGNING_CERT`
(the path of its certificate, DER) and `ASC_PROFILE` (the path of the App Store
profile) sign with an identity and profile made elsewhere instead (`asc.py
given-identity`), for a build machine that must not hold the API key or create
certificates: no App Store Connect call is made, and an app with extensions is
refused. A value that is not a readable file stops signing without printing it.
`tests/flutter-ship/run.sh` checks the steps with stubbed tools.

A clean build of the stock template with four plugins takes 47 s on a 2018
laptop (i7-8650U).

## What `setup.sh` fetches and changes

- **Network.** depot_tools from chromium.googlesource.com and the Dart SDK
  from dart.googlesource.com, pinned to the `dart_revision` in the installed
  Flutter's `DEPS`: 7 GB on disk. `gclient sync` also runs the Dart SDK's DEPS
  hooks, which download prebuilt build tools from Google storage (the clang,
  gn and ninja the build runs, sysroots, a bootstrap Dart SDK). Those
  prebuilts execute on your machine during the build. `flutter precache --ios`
  then fetches Flutter's own iOS engine artifacts.
- **It modifies the Flutter install.** `gen_snapshot_arm64` under
  `bin/cache/artifacts/engine/ios-release` is replaced by the Linux build; the
  original is kept beside it as `gen_snapshot_arm64.macos`. To undo, move that
  file back over `gen_snapshot_arm64`. A Flutter upgrade restores the macOS
  binary by itself, after which `build.sh` stops with "not the Linux build"
  until `setup.sh` runs again.

## How it works

| Piece | On a Mac | Here |
|---|---|---|
| Dart code to arm64 | `gen_snapshot_arm64`, shipped as a macOS binary only | The same compiler built from the Dart SDK at Flutter's pinned revision, hosted on Linux and targeting iOS (`patches/dart-ios-target-on-linux.patch`, one GN argument). Since Flutter 3.47 it writes the Mach-O dylib itself, so no Apple linker is involved. |
| Assets, engine framework, native assets (`sqlite3`, `objective_c`, ...) | `flutter assemble` from an Xcode build phase | The same `flutter assemble release_ios_bundle_flutter_assets`, unmodified, with `shims/` first on PATH. |
| `xcrun`, `xcodebuild`, `codesign`, `lipo`, `strip`, `otool`, `install_name_tool`, `dsymutil`, `ld` | Xcode | `shims/`: SDK queries answered from the darwin SDK bundle, tools forwarded to LLVM, `codesign` a no-op (xtool signs the finished app). |
| Runner and plugins | Xcode project plus Swift packages | `tools/gen-shell-package.py` writes one SwiftPM package from `.flutter-plugins-dependencies`; SwiftBuild compiles it against `Flutter.framework`. |
| App extensions (widgets, share, ...) the Runner embeds | Xcode builds each extension target into `PlugIns/<name>.appex` | `tools/gen-extensions.py` reads the extension targets out of `Runner.xcodeproj` and writes a second SwiftPM package: one executable per extension, linked with the extension entry point `_NSExtensionMain` and its own `Info.plist`. `build.sh` compiles it, runs the extension's catalogs through `actool` and its string catalogs through `tools/xcstringstool`, and embeds every `PlugIns/<name>.appex`. Signing covers them: `sign-dev.sh` with a dev profile per extension bundle id (`provision-dev.py --bundle-id ...`), `ship.sh` with the App Store profiles `asc.py identity` already makes per extension. Extensions need packages of their own are not supported yet: their build fails on the unresolved imports. |
| Icons | `actool` | This repo's Linux `actool`. |
| Storyboards | `ibtool` | This repo's Linux `ibtool`. Flutter's two template storyboards compile byte-identical to Xcode's. |
| `Info.plist` | Xcode | `tools/gen-info-plist.py`. It expands Flutter's own `$(VAR)`s and the Runner target's build settings in the configuration being built, including its xcconfig (`Flutter/Release.xcconfig`) and the files it includes. |

## Things that would otherwise bite

- **dyld rejects what llvm-strip and llvm-install-name-tool write.** Both
  re-lay out `__LINKEDIT` and can leave the string pool on a 4-byte boundary.
  An image built against the iOS 27 SDK then fails to load with `mis-aligned
  LINKEDIT string pool`; older-SDK images are let through, which hides the
  problem until a locally compiled native asset hits it.
  `tools/macho-align.py` pads the pool to 8 bytes; the `strip` and
  `install_name_tool` shims run it on everything they touch.
- **The Swift toolchain's `ld64.lld` refuses iOS.** `shims/clang-darwin` links
  with the SDK bundle's `ld64.lld` and passes `-mlinker-version`, without
  which clang omits `-platform_version`.
- **`xtool install` waits forever while the app being replaced is running.**
  Quit it first.

## Limits

- Release mode only: no debug build, no hot reload, no profile `gen_snapshot`.
- Every plugin with native iOS code must ship a `Package.swift`; a
  CocoaPods-only plugin stops the build with its name.
- A storyboard edited beyond Flutter's template may use something the Linux
  ibtool does not compile yet; it stops with an `error:` line naming it.
- Not tried: an App Store upload with `ship.sh` from this directory (the
  steps are the ones `sdk-free/ship.sh` takes to TestFlight; no receipt yet),
  app extensions, entitlements beyond the defaults, simulator builds.
- `Info.plist` values from an xcconfig ignore conditional settings
  (`KEY[sdk=iphoneos*] = …`); the unconditional value is used.
- With `FLAVOR`, a configuration with its own `INFOPLIST_FILE` stops the
  build, and the icon set must be in `ios/Runner/Assets.xcassets`. Flavor-scoped assets follow the
  scheme's spelling, where a Mac follows `FLAVOR` as typed; `build.sh` warns
  when the two differ.
- A Flutter upgrade needs `flutter/setup.sh` again: the snapshot format is
  tied to the exact Dart revision.
