# Flutter iOS build and App Store signing, on Linux, proven in this container

Date: 2026-11-03. Container: `omarchy-apple` (Ubuntu 24.04, 4 vCPU / 8 GiB), repo at
`/root/omarchy-apple-dev`, no-xcode mode, no Apple account, no phone, no macOS.

## What was run

    flutter create --platforms=ios --org dev.innotel --project-name hello /root/flutter-apps/hello
    sdk-free/flutter-build.sh --debug /root/flutter-apps/hello
    sdk-free/ship.sh /root/flutter-apps/hello        # TEST identity, no ASC key

Result: the debug bundle builds (`Runner.app/Runner` is a thin arm64 Mach-O), and
`ship.sh` stamps, signs and validates it: **44/44 checks passed**, including the
storyboard (`UIMainStoryboardFile 'Main' is compiled in the bundle`), the 1024 icon in
`Assets.car`, the iPad orientations, and every sealed hash.

`ship.sh` reads `build/ios-sdkfree/release` unconditionally, so the debug run is pointed
at by a `release` symlink; nothing else in the path is special-cased.

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
source (~7 GB on disk, ~12 min). This host had ~11 GB free, and the `gclient sync` had
already taken the filesystem to 3.6 GB free (97% used) on a host that also runs `aidev`;
it was stopped and the partial checkout (5.9 GB) removed. Debug is the furthest this
container's disk allows. Give the VM more space and re-run
`flutter/setup.sh && sdk-free/flutter-build.sh <app> && sdk-free/ship.sh <app>` for the
release path; no code change should be needed.
