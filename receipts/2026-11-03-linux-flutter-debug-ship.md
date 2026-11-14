# Flutter iOS build and App Store signing: historical Linux container report

Date: 2026-11-03. Contributor-reported Ubuntu 24.04 container (4 vCPU / 8 GiB),
no-xcode mode, no Apple account, no phone, no macOS. Not independently reproduced.

## What was run

    flutter create --platforms=ios --org dev.innotel --project-name hello <app>
    <repo>/sdk-free/flutter-build.sh --debug <app>
    <repo>/sdk-free/ship.sh <app>        # TEST identity, no ASC key

Reported result: the debug bundle builds (`Runner.app/Runner` is a thin arm64 Mach-O),
and `ship.sh` stamps, signs and validates it: **44/44 checks passed**, including the
storyboard (`UIMainStoryboardFile 'Main' is compiled in the bundle`), the 1024 icon in
`Assets.car`, the iPad orientations, and every sealed hash.

`ship.sh` reads `build/ios-sdkfree/release` unconditionally. This historical debug run
used a manually created `release` symlink; that workaround is not part of the code fix.

## Defect found and fixed

`sdk-free/flutter-build.sh` could not finish a build at all. `gen-info-plist.py` derives
the iOS project directory as `dirname(dirname(Info.plist))`, which is correct for
`flutter/build.sh` (it passes `$app/ios/Runner/Info.plist`) but three levels too shallow
for the sdk-free path, which stages a copy at
`<app>/build/ios-sdkfree/<mode>/Info.src.plist`. The build died with

    FileNotFoundError: '<app>/build/ios-sdkfree/Runner.xcodeproj/project.pbxproj'

Fix: `gen-info-plist.py` honours an `IOS_DIR` override (default unchanged) and
`sdk-free/flutter-build.sh` sets `IOS_DIR="$APP/ios"` and passes the build configuration
(`Debug`/`Release`) instead of always reading `Release`.

## Not proven: release builds here

Release needs `flutter/setup.sh`, which builds the iOS `gen_snapshot` from the Dart SDK
source (~7 GB on disk, ~12 min). The reported container had ~11 GB free; `gclient sync`
left 3.6 GB free (97% used), so it was stopped and the partial checkout (5.9 GB) removed.
Release build/signing remains unverified; the debug result does not establish it.
