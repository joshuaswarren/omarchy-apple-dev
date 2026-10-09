# SwiftUI in no-xcode mode

A SwiftUI app builds, links and runs on an iPhone (iOS 27.0.1) without the
Xcode download. The module started as the minimal subset (`App`,
`WindowGroup`, `View` with `Text`, `VStack`, `Button`, `@State`; receipt
`receipts/2026-10-09-no-xcode-swiftui.md`) and now carries the wider surface
listed under "What is supported". The first build is
`sdk-free/swiftui/swiftui-build.sh HelloApp.swift`; the app source next to
this script is the demo.

## What is supported

- Minimal subset, verified on the phone 2026-10-09: `App`, `WindowGroup`,
  `VStack(alignment:spacing:)`, `Text`, `Button`, `@State`, `EmptyView`,
  `TupleView` (2 and 4 children).
- Declared for step (a), symbol check clean, **builds, phone unchecked**:
  `Color` (statics `red/green/blue/orange/gray/primary`), `Font`
  (`largeTitle/title/headline/body`), `Image(systemName:)`, `View.padding(_
  length: CGFloat)`, `View.font(_ font: Font?)`,
  `View.foregroundColor(_ color: Color?)`,
  `View.foregroundStyle(_ style: some ShapeStyle)`, `ShapeStyle`.
  Staged app: `SwiftUIWide1-dev.ipa`.
- Declared for step (b), symbol check clean, **builds, phone unchecked**:
  `List` (two generic parameters, `Selection` first; `List { }` is
  `extension List where Selection == Never`), `ForEach` over `Range<Int>`,
  `NavigationLink(destination:label:)`, `View.navigationTitle(_:
  LocalizedStringKey)`, `LocalizedStringKey`. Staged app:
  `SwiftUIWide2-dev.ipa`.
- **Blocker (b)**: `NavigationStack` cannot be linked — the device's
  SwiftUI/SwiftUICore stubs export zero `_$s7SwiftUI13NavigationStack`
  symbols (only internal helpers like `NavigationStackContext` appear in
  the reflection dump). Navigation bars without a host also render nothing;
  the staged app shows whether `List`/`navigationTitle` need it.
- **Blocker (c)**, from stub/dump reads, not yet attempted in code:
  `@Observable` needs the `Observation` module built from the Swift source
  tag plus the device exporting `libswiftObservation`; `@Environment` and
  `@Binding` declarations follow the same recipe as `State` once the device
  symbols for `Environment`/`EnvironmentValues` keyed paths are mapped.

## How it works

- `SwiftUI.swift` here is our own declaration file for a `SwiftUI` module: the
  types (`App`, `Scene`, `View`, `WindowGroup`, `VStack`, `Text`, `Button`,
  `State`, `Binding`, `TupleView`, `EmptyView`, `ViewBuilder`, `SceneBuilder`,
  `HorizontalAlignment`) with the signatures the app needs. No Apple file is
  committed; the declarations were checked against the mangled symbols that the
  iPhone's SwiftUI exports.
- The module builds with library evolution on, so the app does not get code from
  it: the app references the implementations in the SwiftUI framework binary on
  the iPhone. The result-builder static methods are `@inlinable`: the compiler
  runs them at compile time and must not emit runtime references to them.
- `TupleView` must stay a single-generic (`TupleView<T>`) type: the parameter-pack
  form mangles differently and would not match the device's symbols. Two children
  in a builder go through the two-parameter `buildBlock` and `TupleView<(C0, C1)>`.
- `swiftui-build.sh` compiles the module into `$SDKFREE_HOME/swift/swiftui`
  (re-runs only when `SwiftUI.swift` changes), compiles the app against it,
  checks every SwiftUI symbol the app object needs against the sysroot stubs,
  and links with `-framework SwiftUI -framework SwiftUICore -framework Combine`.
  A symbol that misses the stubs fails the build before the link.

## Setup

`sdk-free/setup.sh` cuts the SwiftUI, SwiftUICore, Combine, CoreTransferable and DeveloperToolsSupport link stubs
together with the other stubs. An older sysroot needs `sdk-free/setup.sh --repair`.

## Layout rule that decides whether it runs

The iPhone's SwiftUI types are frozen and the device code passes small values in registers. A declaration that is
resilient (no `@frozen`, no stored fields) makes the app pass a result slot that the device code never writes, and the
device then frees garbage. `Text`, `HorizontalAlignment`, `State` and `TupleView` therefore carry the device layout
(read with `ipsw dyld macho --swift` / `ipsw swift-dump` from the cache). `Text` is 32 bytes: a two-word payload, a tag
byte, and the modifier array. Generic returns such as `VStack` and `WindowGroup` stay layout-safe through runtime
metadata. Check any new type's size with `MemoryLayout` against the device layout before you trust it.

## How to add a type

1. Dump the device layout:
   `python3 sdk-free/swiftui/dumpgen.py Color --cache <dsc> --scratch <dir>`
   prints the stored fields, nested types, conformances and how many
   exported symbols mention it (keep the scratch dir out of the repo).
2. Declare it in `SwiftUI.swift` with the dumped field structure; mark it
   `@frozen` only when the fields are the device's real frozen layout
   (one-word class-reference payloads for `Color`/`Font`/`Image`; result
   builders stay `@inlinable`; everything else is a `fatalError()` body that
   links the device's exported symbol).
3. Probe the size: add a `take(MemoryLayout<T>.size)` line to
   `sdk-free/swiftui/layout-probe.swift`, build it with
   `swiftui-build.sh`, and read the immediate stores out of
   `llvm-objdump -d` of the linked probe — -O folds them into constants in
   `main`. Compare with the field count/types from step 1.
4. Build the app with `swiftui-build.sh`: `SwiftUI symbols checked,
   missing 0` is the signature gate; a MISS line names the exact mangled
   symbol that does not exist on the device.
5. Stage a signed ipa and get a phone run; do not call it working until the
   phone run confirms.

## What is next

- Conditionals in content closures need `buildOptional`/`buildEither` and
  `Optional: View`; `buildBlock` arities 3 and 5+; `TextField`.
- Step (c): build the `Observation` module from the Swift source tag the way
  `build-stdlib.sh` builds the stdlib (the macro plugin is in the toolchain
  at `lib/swift/host/plugins/libObservationMacros.so`, and the device
  exports `usr/lib/libswiftObservation.dylib`), then declare
  `@Observable`, `@Environment` and the `Binding` projections.
- Generating wider declarations from the cache metadata is semi-automatic:
  `sdk-free/swiftui/dumpgen.py` wraps `ipsw swift-dump` and reports a type's
  stored fields, nested types, conformances and exported-symbol count; the
  symbol check rejects any signature that does not exist on the device.
