# SwiftUI wide surface and the App Store signing pipeline, proven on Linux

Date: 2026-11-03. Container: `omarchy-apple` (Ubuntu 24.04, 4 vCPU / 8 GiB), repo at
`/root/omarchy-apple-dev`, no-xcode mode, no Apple account, no phone.

## What was checked

1. `sdk-free/swiftui/swiftui-build.sh` on a source that uses the row
   `docs/TEST-MATRIX.md` marks "built, phone not yet": `Color`, `Font`,
   `Image(systemName:)`, `padding`, `foregroundStyle`.
   Result: module builds, **symbol check: 0 missing**, links to
   `Mach-O 64-bit arm64 executable`.
2. The whole release path on that artifact: `tools/mkapp.py` -> `asc.py stamp`
   (App Store build keys) -> `actool` icon catalog -> `Assets.car` + `CFBundleIcons`
   -> `asc.py test-identity` -> `rcodesign sign` -> `Payload/` zip ->
   `asc.py validate`.

## Result

    ok  Info.plist has the required keys
    ok  built against the device SDK: iphoneos26.0      DTXcode 2700 / 27A266a
    ok  Assets.car present (2 rendition sizes)          structural check passed
    ok  Assets.car has the App Store 1024 icon (1024x1024)
    ok  CFBundleIcons names the primary icon
    ok  rcodesign verify / every bundle file sealed / entitlements subset of the profile
    40/40 checks passed

The 1024 icon was generated in-container (pure-Python PNG, no Pillow) and compiled by
the repo actool, so the icon checks exercised the real path.

## Two defects found and fixed

1. `foregroundStyle(Color.primary)` did not compile: `ShapeStyle` was declared but
   `Color` did not conform, so the documented wide surface was unusable. Fix:
   `@frozen public struct Color: ShapeStyle` in `sdk-free/swiftui/SwiftUI.swift`.
2. `asc.py stamp` crashed in no-xcode mode: it reads
   `$DARWIN_SDK/Developer/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS.sdk`
   (the xtool layout), and no-xcode has `$SDKFREE_HOME/iPhoneOS.sdk` only. Fix: that
   path is now a symlink to the sysroot and `DARWIN_SDK=$SDKFREE_HOME` is exported.
   This also blocked `sdk-free/ship.sh`, whose step 1 is the same stamp.

Reproduce: `/root/build/smoke.sh` (exits non-zero on any FAIL).
