# SwiftUI in no-xcode mode

A minimal SwiftUI app (`App` protocol, `WindowGroup`, `View` with `Text`, `VStack`,
`Button`, `@State`) builds and links here without the Xcode download. The first
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

## One-time setup (per connected iPhone)

The SwiftUI and Combine stubs are not part of `sdk-free/setup.sh` yet. Cut them
from the phone's system-library cache with `ipsw` (paths shown for the cache
copied by `dl-dsc27.sh` into `dsc27/24A446__iPhone16,2/`):

    ipsw dyld tbd <dsc> /System/Library/Frameworks/SwiftUI.framework/SwiftUI -o tbds
    ipsw dyld tbd <dsc> /System/Library/Frameworks/SwiftUICore.framework/SwiftUICore -o tbds
    ipsw dyld tbd <dsc> /System/Library/Frameworks/Combine.framework/Combine -o tbds
    ipsw dyld tbd <dsc> /System/Library/Frameworks/CoreTransferable.framework/CoreTransferable -o tbds
    ipsw dyld tbd <dsc> /System/Library/Frameworks/DeveloperToolsSupport.framework/DeveloperToolsSupport -o tbds

and copy each `.tbd` into the sysroot at
`$SDKFREE_HOME/iPhoneOS.sdk/System/Library/Frameworks/<Name>.framework/<Name>`.

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
