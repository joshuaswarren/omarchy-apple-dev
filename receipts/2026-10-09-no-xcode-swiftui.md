# Receipt: SwiftUI app builds in no-xcode mode, 2026-10-09

Goal: a minimal SwiftUI app (`App`, `WindowGroup`, `View` with `Text`, `VStack`,
`Button`, `@State`) built in the Arch chroot without the Xcode download, staged
for the iPhone (iOS 27.0.1).

## What works (observed in the chroot)

- The hand-written `SwiftUI` module (`sdk-free/swiftui/SwiftUI.swift`, our own
  declarations) compiles with the Swift 6.4 toolchain against the sdk-free
  sysroot and the standard-library/overlay modules from `build-stdlib.sh` and
  `overlays.sh`.
- `sdk-free/swiftui/swiftui-build.sh HelloApp.swift` compiles the demo app,
  checks its SwiftUI symbols against the link stubs, and links:
  `SwiftUI symbols checked, missing 0`, `built .../HelloSwiftUI`.
- The stubs for the check were cut with `ipsw dyld tbd` from the iOS 27.0.1
  dyld shared cache (iPhone16,2 build 24A446) extracted from Apple's public
  IPSW to the QNAP (`dsc27/24A446__iPhone16,2/`): SwiftUI, SwiftUICore,
  Combine, CoreTransferable, DeveloperToolsSupport (+ CoreText, UIFoundation,
  AttributeGraph present in the sysroot).
- `tools/macho-lint.py` on the signed IPA: `1/1 Mach-O images clean`
  (arm64, minos 17.0, sdk 26.0).
- Signed with `tools/sign-dev.sh` after `tools/provision-dev.py
  --bundle-id dev.omarchy.nosdk.swiftui` (profile HNVS6MM84H, 5 devices,
  expires 2027-10-09).
- Staged: `/home/joshuawarren/scratch/apple-free/step2/SwiftUIHello-dev.ipa`
  (executable `HelloSwiftUI`, bundle `dev.omarchy.nosdk.swiftui`).

Not observed: a run on the iPhone. That needs the lead's phone window
(`pymobiledevice3 apps install` + launch). The build proves every referenced
symbol exists in the device stubs; whether the app renders is the next check.

## Two findings that shaped the interface

- The result-builder static methods (`ViewBuilder.buildBlock`,
  `buildExpression`) are not exported by the device's SwiftUI at all: they are
  compile-time. The declarations must be `@inlinable` so the client inlines
  them; otherwise the link fails on symbols the device does not have.
- `TupleView` must be declared `TupleView<T>` (single generic parameter, no
  parameter packs). The pack form mangles to different symbols
  (`TupleView<repeat each T>` vs the device's `TupleView<T>`), and the two-child
  `buildBlock` returns `TupleView<(C0, C1)>`.
