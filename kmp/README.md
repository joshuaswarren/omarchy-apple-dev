# Kotlin Multiplatform apps for iOS, built on Linux

A Kotlin Multiplatform (or Compose Multiplatform) app ships its shared code to
iOS as a framework, which Gradle links only on a Mac: Kotlin/Native turns
Apple targets down on Linux and skips the link task. `build-framework.sh`
links that framework on Linux anyway, from the klibs Gradle does build, with
the toolchain and SDK `install-toolchain.sh` sets up. The Swift app around it
then builds like any other xtool package.

Verified 2026-11-05 on x86_64 (Arch container, Swift 6.4.1, iPhoneOS 27.1 SDK)
with a Compose Multiplatform app (Kotlin 2.4.21, Android and iOS targets): the
framework linked, embedded with its Compose resources, the app run on an
iPhone 11 Pro under iOS 27. aarch64 hosts are untested.

## Use

```
./install-toolchain.sh                         # once, as for any app in this repo
# a JDK on the PATH; for a build with Android targets, the Android SDK sdk.dir points at
kmp/build-framework.sh /path/to/gradle/root --module :shared --dynamic --xcframework
```

It reads the framework the project declares (`binaries.framework` of the
`iosArm64` target: base name, static or not, exported modules, options,
Compose resources) through `ios-kmp.init.gradle`, and writes
`<module>/build/omarchy-kmp/ios_arm64/<Name>.framework` (`--out` elsewhere),
with `compose-resources/` next to it when the project has some, and
`<Name>.xcframework` with `--xcframework`. `--target ios_simulator_arm64`
links for the simulator (xcframework slice `ios-arm64-simulator`). The first run takes the iOS runtime of the macOS
Kotlin/Native distribution from Maven Central (about 300 MB, kept in
`~/.cache/omarchy-apple-dev/kmp`); the link itself takes a few minutes.

- The build is optimized and has no debug info: the Linux LLVM asserts on the
  debug info of Apple targets.
- A failed step (download, extraction, link, copy of the resources, xcframework)
  stops with a non-zero status; the iOS runtime is cached only once it is
  extracted complete. `tests/kmp-framework/run.sh` checks these paths offline.
- `--dynamic` links a dynamic framework even when the project declares a
  static one. `swift build` loads every member of a static archive
  (`-all_load` of the toolset), and the static framework of a Compose
  Multiplatform app carries some Skia objects twice: it then fails on
  duplicate symbols. A dynamic one links and is embedded in `Frameworks/`.

## The app around it

The Xcode project of the app links the framework with `OTHER_LDFLAGS` /
`FRAMEWORK_SEARCH_PATHS` and a run-script phase calling Gradle, which
`tools/xcodeproj2xtool.py` does not carry over. After converting it, declare
the framework as a binary target of the package:

```
python3 tools/xcodeproj2xtool.py iosApp/App.xcodeproj --out omarchy-xtool
mkdir -p omarchy-xtool/Frameworks
cp -a <module>/build/omarchy-kmp/ios_arm64/Shared.xcframework omarchy-xtool/Frameworks/
```

```swift
// omarchy-xtool/Package.swift: in targets, and in the app target's dependencies
.binaryTarget(name: "Shared", path: "Frameworks/Shared.xcframework"),
.target(name: "App", dependencies: ["Shared", ...], ...)
```

A project described by an XcodeGen `project.yml` needs its `.xcodeproj`
generated first (`xcodegen generate`, XcodeGen builds on Linux with
`swift build -c release --product xcodegen`).

Then build, and put the Compose resources where Compose Multiplatform reads
them, `compose-resources/` at the root of the `.app`, before signing:

```
cd omarchy-xtool
CONFIGURATION=debug ../ship.sh --device
cp -a ../<module>/build/omarchy-kmp/ios_arm64/compose-resources xtool/App.app/
```

Sign and install as for any app: `xtool install xtool/App.app`, or
`tools/sign-dev.sh` and `pymobiledevice3 apps install`. `tools/sign-dev.sh`
signs the framework in `Frameworks/` with the app.

Compose Multiplatform checks `CADisableMinimumFrameDurationOnPhone` in the
app's `Info.plist` at launch (`PlistSanityCheck`) and stops the app without
it: keep it in the project's `Info.plist`, which the converter carries over.
