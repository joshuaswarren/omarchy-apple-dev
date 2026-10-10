# Test matrix: what runs on an iPhone and what only builds

All rows are the no-Xcode mode (`./install-toolchain.sh --mode no-xcode`) built on Linux. "Ran" means the app was installed
on an iPhone (iOS 27.0.1, iPhone16,2) and launched, and a screenshot or program output was taken. "Built" means it
compiled, linked, and signed, and a Mach-O lint passed, but no phone ran it. Receipts are in `receipts/`.

| Item | Built on Linux | Ran on the iPhone | Receipt and notes |
|---|---|---|---|
| Objective-C UIKit hello | yes | yes (label drawn) | `2026-10-09-no-xcode-on-iphone.md` |
| Swift console programs (stdlib, async/await, `Foundation`) | yes | yes: output seen for 3 of 6; 2 printed nothing in a 20 s window and left no crash report | same |
| Flutter counter, release | yes | yes (UI draws) | same |
| Flutter with `sqflite` and `path_provider` (Objective-C plugins) | yes | yes (UI draws) | same |
| Flutter with `shared_preferences` and `url_launcher` (Swift plugins) | yes, with Swift 6.4 from the installer scripts | yes: launch #1, then #2 after a relaunch, `canLaunchUrl: true`; buttons not tapped | same |
| Flutter debug builds | yes | no (iOS 26 and later need a debugger for the debug engine) | `sdk-free/README.md` |
| Flutter app to TestFlight | yes (`sdk-free/ship.sh --upload`) | processing finished `VALID` (build 202610092142); not installed from TestFlight | `2026-10-09-no-xcode-testflight.md` |
| SwiftUI subset: `App`, `WindowGroup`, `Text`, `VStack`, `Button`, `@State` | yes | yes: draws `taps: 0` and a button; tap not tested | `2026-10-09-no-xcode-swiftui.md` |
| SwiftUI `Color`, `Font`, `Image(systemName:)`, `padding`, `foregroundStyle` | yes (symbol check: 0 missing) | not yet | `sdk-free/swiftui/README.md` |
| SwiftUI `List`, `ForEach`, `NavigationLink` | yes (symbol check: 0 missing) | not yet | same |
| SwiftUI `NavigationStack` | no: iOS 27.0.1 does not export it | no | same |
| SwiftUI `Binding` from `@State` | no: no exported symbol on iOS 27.0.1 | no | same |
| React Native 0.87 with Hermes, release | yes (signed, `macho-lint` 4 of 4 clean) | not yet | `2026-10-09-rn.md`, `sdk-free/react-native/README.md` |
| React Native third-party Fabric pods (`react-native-safe-area-context`) | no | no | same |
| Setup without an iPhone (Apple's public iOS update) | yes: 22 stubs match the phone-cut ones byte for byte | same builds as above | `2026-10-09-phone-free-setup.md` |
| Ubuntu 24.04 container | `setup.sh`, `build-stdlib.sh`, `swiftc.sh` pass | n/a | `docs/DISTROS.md` |
| Ubuntu: overlays, Flutter build, full (Xcode) mode, aarch64, Fedora | not tested | n/a | `docs/DISTROS.md` |
| Install with a free Apple ID in this mode | not checked | not checked | `sdk-free/README.md` |
| App extensions, widgets, macOS apps | not supported | n/a | `sdk-free/README.md` |

When a row moves from "not yet" to "yes", add the screenshot to `receipts/` and change this table in the same commit.
