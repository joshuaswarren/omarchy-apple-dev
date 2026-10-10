# iOS app simulation on Linux (standing project)

Date: 2026-10-10. Status: research; no simulation code exists yet.

Question: can a Linux host check iPhone app UI behavior with no macOS and no iPhone?

The repo's test routes today are: compile and symbol-check on Linux, run in the iOS
Simulator on a Mac over ssh, ship to TestFlight, or run on the phone over USB. Those are
covered by `receipts/2026-10-10-testing-without-the-phone-plan.md`. This document is about
the longer-term route that needs neither macOS nor a phone: simulate the app on Linux
itself, starting from the Mach-O binaries this repo already produces.

## Two routes

- Route A (user-supplied runtime): the user points the tool at their own downloaded
  simulator runtime; the repo never fetches, stores, or ships any runtime material.
- Route B (reimplementation): we write our own declarations and draw code, so no runtime
  material is involved at all.

## Prior art

### Mach-O loaders on Linux (the Wine pattern)

Wine runs Windows binaries on Linux by loading them and reimplementing the OS around
them ([LWN overview](https://lwn.net/Articles/794871/)). The same pattern exists for
Mach-O:

| Project | What it does | Limits |
|---|---|---|
| [Darling](https://github.com/darlinghq/darling) ([docs](https://docs.darlinghq.org/)) | Loads Mach-O binaries and reimplements the macOS layer: a userspace kernel server for Mach IPC and Darwin syscalls, plus reimplemented Foundation, AppKit (built on Cocotron), CoreAudio, CoreFoundation. Many CLI tools work; GUI is in development behind an AppKit implementation and a Metal-on-Vulkan backend. | Targets macOS, not iOS: no UIKit, no iOS frameworks. Requires 64-bit x86 Linux ([build docs](https://docs.darlinghq.org/build-instructions.html)), so no arm64 path. |
| [maloader](https://github.com/shinh/maloader) | Small userland Mach-O loader for Linux (`ld-mac`). | Old, x86, proof-of-concept scale. |
| [machismo](https://github.com/bmdhacks/machismo) (2026) | Runs Apple Silicon Mach-O binaries on aarch64 Linux with no CPU emulation: maps Mach-O segments, redirects imports to native Linux `.so` files, and bridges ABI differences (constructors return `this`, Apple libc++ SSO layout, pthread signatures, zero-filling `malloc`, `_tlv_bootstrap`, compact unwind to DWARF, LSE atomics emulation). | Built for C/C++ game binaries, not iOS apps: no Objective-C runtime, no UIKit. |
| [osxcross](https://github.com/tpoechtrager/osxcross) | Cross toolchain that builds macOS binaries from Linux; the user supplies their own SDK. | Build-only, no runtime. Same user-supplies-material shape as Route A. |

### QEMU boots of real iOS (research kernels only)

| Project | What it actually runs |
|---|---|
| [xnu-qemu-arm64](https://github.com/alephsecurity/xnu-qemu-arm64) | Boots the iOS 12.1 kernel ([build guide](https://github.com/alephsecurity/xnu-qemu-arm64/wiki/Build-iOS-on-QEMU)). Research kernel, no UI. |
| [qemu-t8030](https://github.com/TrungNguyen1909/qemu-t8030) | A13 device (iPhone 11 class) running iOS 14 through a restore; enough to reach a shell over ssh ([eShard writeup](https://www.eshard.com/blog/emulating-ios-14-with-qemu)). |
| [QEMUAppleSilicon](https://github.com/wangningyi/QEMUAppleSilicon) and its [IOMFB fork](https://github.com/ChefKissInc/QEMUAppleSilicon) | iPhone 11 target; display/framebuffer (IOMFB) work. |
| [Corellium](https://www.corellium.com/platform) | Commercial virtual ARM devices running real iOS. Closed platform, paid. |

What the eShard team hit, and why this lane is hard
([writeup](https://www.eshard.com/blog/emulating-ios-14-with-qemu)):

- iOS rendering goes through Metal to a real GPU. The `gpu=0` software-render bootarg is
  gone in iOS 14; software rendering survives only as a QuartzCore fallback. They proved
  the fallback works by patching QuartzCore on a jailbroken device: slow, with artifacts.
- Kernel patches (checkra1n KPF injected via PongoOS) need per-version maintenance; A13
  pointer-authentication instructions break older patch matching.
- Apple system libraries ship in one dyld shared cache (arm64e), which complicates
  loading and debugging.
- Net result today: kernels boot and shells work; app UI does not. No QEMU project runs
  App Store apps.

An iPod touch 1G emulator exists as a research project
([CCC 2023 talk](https://fahrplan.events.ccc.de/congress/2023/fahrplan/system/event_attachments/attachments/000/004/479/original/ccc_presentation.pdf)).

### Reimplemented UI frameworks

| Project | What it does | Fit here |
|---|---|---|
| [GNUstep](https://gnustep.org/) | Long-running reimplementation of the AppKit/Foundation stack on Linux. | Proof that framework reimplementation is durable work; nothing iOS. |
| [SwiftCrossUI](https://github.com/stackotter/swift-cross-ui) ([docs](https://docs.swiftcrossui.dev/documentation/swiftcrossui/)) | SwiftUI-style code on Linux (GTK backend), with AppKit, UIKit, Android, and WinUI backends. | Closest existing shape for M2/M3: SwiftUI dialect in, pixels out. |
| [OpenSwiftUI](https://github.com/OpenSwiftUIProject/OpenSwiftUI) ([site](https://openswiftuiproject.org/)) | Open-source SwiftUI implementation aiming at Linux, Android, WASI, embedded. | Young; worth watching. |
| [Skip](https://github.com/skiptools/skip) ([architecture](https://skip.dev/docs/architecture)) | Compile-time transpiler: Swift to Kotlin, SwiftUI to Jetpack Compose. | Different lane (no Linux runtime), but its SwiftUI API mapping is useful reference. |

### Cross-compiled app frameworks with a Linux target

- [Flutter](https://docs.flutter.dev/platform-integration/linux/building) runs on Linux
  desktop through its own embedder; the engine rasterizes scenes on CPU or GPU
  ([engine architecture](https://github.com/flutter/flutter/blob/master/docs/about/The-Engine-architecture.md)).
  This repo already builds Flutter apps from Linux with no macOS.
- [React Native](https://reactnative.dev/docs/out-of-tree-platforms) officially supports
  Windows and macOS out of tree; an Ubuntu port existed in 2016-2017
  ([Canonical branch](https://github.com/CanonicalLtd/react-native/tree/ubuntu)). This
  repo keeps an RN lane too (`rn-no-xcode`).

These frameworks prove app logic on Linux. They do not prove iOS UI behavior, because
the iOS UI stack is not in the loop.

### The Android-emulator shape, and why it does not carry over

The Android emulator is QEMU plus bootable Android system images
([emulator sources](https://android.googlesource.com/platform/external/qemu/+/emu-master-dev/android/docs/ANDROID-EMULATION-LIBRARY.TXT));
[Waydroid](https://github.com/waydroid/waydroid) runs a full Android system in a Linux
namespace container. That shape works because Android's system is open and its images
are bootable artifacts anyone can build. iOS has no bootable system image outside
Apple's own signing flow, so the Android shape collapses into Route A (user-supplied
runtime) or the research-kernel QEMU lane above.

### What changes on arm64 Linux on Apple Silicon hardware

On an arm64 Linux host the CPU already runs the app's instruction set, so a loader is
enough: no emulation, no QEMU. [machismo](https://github.com/bmdhacks/machismo) proves
the pattern for C/C++ binaries. Two gaps remain for iOS apps: the Objective-C runtime
and UIKit do not exist on Linux, and Apple's system libraries are arm64e with pointer
authentication while app binaries are plain arm64 (see the dyld cache notes in the
[eShard writeup](https://www.eshard.com/blog/emulating-ios-14-with-qemu)). This lab
already builds and runs arm64 Linux binaries natively on Apple Silicon hardware, so
every rung below has both a `qemu-aarch64-static` option and a native arm64 option.

## Milestone ladder

Each rung lands a receipt in `receipts/` with the commands and outputs actually observed.
A rung is done when its exit check is observed, not argued.

### M1 — a Mach-O arm64 hello from our toolchain runs on Linux

Owned by a sibling lane, in progress on branch `machoload-m1`.

- Entry checks:
  - The chroot toolchain emits a Mach-O arm64 executable. Already proven for device
    builds in `sdk-free/`; `llvm-objdump --macho --all-headers hello` lists
    `LC_SEGMENT_64 __TEXT` and `LC_MAIN`.
  - An arm64 Linux runner exists: `qemu-aarch64-static` on the build host, or the native
    arm64 Linux host.
- Exit demo (expected shape):
  ```
  $ llvm-objdump --macho --all-headers hello | grep -E 'LC_SEGMENT_64|LC_MAIN'
  $ ./loader hello
  hello from arm64 Mach-O
  $ echo $?
  0
  ```
- Cannot prove: dyld shared cache loading, the Objective-C runtime, any framework. A
  C-level hello only proves the loader and its syscall shims.

### M2 — a SwiftUI view renders to a PNG (software draw path, no GPU)

- Entry checks: M1 done; a starting view vocabulary picked from `sdk-free/swiftui/`
  (VStack, Text, Image, Color, padding); a CPU rasterizer plan: RGBA buffer plus PNG
  writer, bitmap font for text first, real font shaping later.
- Exit demo (expected shape):
  ```
  $ ./simview demo1.swift --out demo1.png
  $ file demo1.png
  demo1.png: PNG image data, 390 x 844
  ```
  The PNG matches a golden image within a stated pixel-diff tolerance, and glyphs appear
  where the Text views sit.
- Cannot prove: real SwiftUI layout or state-graph behavior, animations, font shaping,
  Metal or GPU numbers. It proves our draw path and our view vocabulary, nothing about
  Apple's renderer.

### M3 — touch input mapping

- Entry checks: M2 renders in a loop from a state struct; taps arrive first as scripted
  events (a JSON list of tap points); a window is optional, not required.
- Exit demo (expected shape):
  ```
  $ ./simview demo1.swift --taps taps.json --out after.png
  ```
  The tap lands on a button hit area, the state changes, the re-render shows it (the
  button region differs from the no-tap render), and a log line records
  tap -> state change -> re-render.
- Cannot prove: iOS gesture recognizers, multi-touch, timing feel, iOS hit-testing
  edge rules. It proves our hit-testing and the state -> render loop.

### M4 — a real iOS app shell runs

- Entry checks: M3 done; one of this repo's real apps (the SwiftUI demo or RNProbe)
  compiles against our declarations with no Apple-derived material in the build; any
  Route A run stays on the user's machine and never enters the repo.
- Exit demo: the app's own SwiftUI code draws its first screen, a scripted tap navigates
  one level, a screenshot is saved, and the app exits cleanly. The receipt records app
  name, commit, commands, and outputs.
- Cannot prove: parity with a real device (fonts, animation curves, system services such
  as push, camera, Keychain), App Store apps, performance numbers.

## Standing rules

- This project adds Linux-only checks. It does not replace the fallback ladder in
  `receipts/2026-10-10-testing-without-the-phone-plan.md`; the Mac Simulator, TestFlight,
  and phone runs stay the primary test routes.
- Each rung: one receipt file in `receipts/`, commands and observed outputs only, no
  Apple-derived files.
