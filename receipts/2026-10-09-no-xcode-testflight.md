# No-Xcode TestFlight upload — 2026-10-09

Branch `no-xcode-testflight`, rebased onto main after the phone-free setup merge.

## Outcome

The Flutter counter built by `sdk-free/flutter-build.sh` (no Xcode download) reached
App Store Connect TestFlight with `processingState VALID`:

- App record `6821068345` ("Omarchy NoSDK Counter"), bundle id
  `com.joshuawarren.omarchyappledev.nosdkcounter`, SKU `NOSDKCOUNTER01`
- build id `7a80ffe2-9252-4f87-9eb2-382a055a5fd8`, marketing version 1.0.1, build
  `202610092142`, `minOsVersion 15.0`, `buildAudienceType APP_STORE_ELIGIBLE`,
  `uploadedDate 2026-10-09T14:43:20-07:00`, `processingState VALID`
- upload `7a80ffe2-…` (buildUpload id equals the build id) went `COMPLETE` about
  2 minutes after the upload; the offline validation passed 44/44 checks.
- Nothing was submitted for review.

## What the no-xcode build lacked, and what ship.sh adds

`tools/asc.py` needed nothing new. `sdk-free/ship.sh --upload <app dir>` mirrors
`ship.sh` steps 4/6/7/8/9 on the `flutter-build.sh` output:

- `asc.py stamp`: DTPlatformVersion 27.0, DTSDKName iphoneos27.0,
  DTPlatformBuild/DTSDKBuild 24A430, DTXcode 2700, DTXcodeBuild 27A266a,
  CFBundleVersion 202610092142; LC_BUILD_VERSION sdk of every Mach-O (Runner,
  Flutter, App — 3 files) raised from the link's 26.0 to 27.0 (ITMS-90725).
- `asc.py identity`: the existing Apple Distribution certificate
  (the test team's Apple Distribution identity), a new IOS_APP_STORE profile
  for the bundle id (`052868ab-…`, expires 2027-10-04), embedded.mobileprovision,
  get-task-allow false.
- rcodesign inside-out (Frameworks, then the app), package, offline validate, upload.
- ASC's own banner on 2026-10-09 requires an iOS 27.1 SDK only for a screenshots rule
  starting April 2027, so 27.0 remains accepted (same day IceCubes shipped VALID on it).

## App Store Connect setup

- Bundle id registered through the API (`POST /v1/bundleIds`, id `5P874NK37D`).
- The app record was created through the ASC web UI (the API refuses app records):
  Apps > New App, then the app name, language, registered bundle ID, SKU,
  iOS platform and access setting. Create the record before uploading.

## The processing wedge, and the fix (measured)

The first counter uploads never failed — they never finished. `buildUpload` state
`PROCESSING` with no errors for hours, on two app records, while known-good xtool
builds of the same records went `COMPLETE` in about 2 minutes the same day
(demo app `6819062752`: 05:56:28 upload → VALID; 14:29 control upload → COMPLETE
inside its own upload call, 115 s wall for build+sign+validate+upload).

| upload | app record | bits | result |
|---|---|---|---|
| `b3c67514` 1.0.0/202610091635 | 6821068345 | counter, multi-size catalog | PROCESSING 4 h+, no error |
| `089caeb9` 1.0.1/202610091812 | 6821068345 | counter, new marketing version | PROCESSING 3 h+, no error |
| `23e73a2d` 1.0.1/202610091849 | 6819062752 | same binary on the healthy record | PROCESSING 2 h+, no error |
| `ba54a654` 1.0.2/202610091930 | 6819062752 | xtool control (SwiftUI demo) | COMPLETE ~2 min → VALID |
| `a7c3b127` 1.0.1/202610091942 | 6819062752 | no-xcode UIKit probe (no Flutter), multi-size car | PROCESSING 35 min+, no error |
| `1ded887c` 1.0.1/202610092018 | 6819062752 | same probe, privacy manifest removed | PROCESSING 33 min+, no error |
| `4eaaa16e` 1.0.0/202610092054 | 6819062752 | no-xcode binary + demo's single-size icons | COMPLETE within its poll |
| `14c37719` 1.0.0/202610092057 | 6819062752 | xtool binary + the no-xcode multi-size car | PROCESSING through its poll |
| `7a80ffe2` 1.0.1/202610092142 | 6821068345 | counter rebuilt with the single-size catalog | COMPLETE ~2 min → **VALID** |

The swap pair isolates it: the no-xcode binary, storyboards, plist, signing and
packaging all process fine — the `Assets.car` that actool 27.0 compiles from the
classic multi-size (19-entry) appiconset never finishes App Store processing, while
the single-size (one universal 1024 entry) catalog from the same tool is accepted in
minutes. A privacy manifest at
the app root was exonerated as the sole cause (probe with none still wedged) and
`ship.sh` no longer adds one; Flutter.framework still carries the engine's own.

The shipped counter used: catalog with one `AppIcon.appiconset` entry
(1024x1024, universal), `LaunchImage.imageset` emptied; rebuild, then
`sdk-free/ship.sh --upload`.

## Build inputs

- Build in an Arch chroot as a non-root user: `sdk-free/flutter-build.sh` release on
  `$WORK/nosdk-ship/sdkfree-counter`, env `SDKFREE_HOME=$WORK/sdkfree-swift`,
  `SDKFREE_TBD_DIR=$WORK/tbd27`, `BUNDLE_ID=com.joshuawarren.omarchyappledev.nosdkcounter`;
  first build 204 s, fixed rebuild 378 s. `Runner-store.ipa` 6.76 MB (6,762,980 bytes
  uploaded in 2 parts).
