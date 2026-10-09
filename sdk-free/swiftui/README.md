# SwiftUI in no-xcode mode

A minimal SwiftUI app (`App` protocol, `WindowGroup`, `View` with `Text`, `VStack`,
`Button`, `@State`) builds, links and runs on an iPhone (iOS 27.0.1) without the Xcode download. The first
build is `sdk-free/swiftui/swiftui-build.sh HelloApp.swift`; the app source next to
this script is the demo. Receipt: `receipts/2026-10-09-no-xcode-swiftui.md`.

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

## What is next

- Conditionals in content closures need `buildOptional`/`buildEither` and
  `Optional: View`; more children per builder need wider `buildBlock` arities.
- `Color`, `Font`, `Image`, `padding`, `ForEach`, `List`, `TextField`,
  `Observable`/`@Observable` (the Observation macro plugin is in the toolchain at
  `lib/swift/host/plugins/libObservationMacros.so`) are undeclared.
- Generating wider declarations from the cache metadata is semi-automatic:
  `ipsw swift-dump <dsc> SwiftUI` prints types, fields and protocols with
  demangled names; a generator would map those onto declaration text and the
  symbol check would reject any signature that does not exist on the device.
