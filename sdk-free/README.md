# No Xcode download (experimental)

This mode builds apps without the Xcode archive. The build files come from an iPhone you connect (link stubs cut from
its system libraries), or from Apple's public iOS update download when no iPhone is connected. Both routes also get
the headers kept in `sdk-free/headers` (written for this repo) and the public Objective-C
runtime headers. Choose it with `./install-toolchain.sh --mode no-xcode` (or answer 2 at the prompt).

## What works

- Objective-C and C apps with UIKit, built with clang and linked with `ld64.lld`.
- Swift programs that import Foundation (`sdk-free/swiftc.sh`), and Flutter apps with Swift plugins
  (`shared_preferences_foundation`, `url_launcher_ios`) built by `sdk-free/flutter-build.sh`
  (sdk-free/swift/README.md, receipts/2026-10-09).
- Flutter apps: release builds, with an Objective-C runner and Objective-C plugins (for example `sqflite`,
  `path_provider`, `geolocator`, `image_picker`, `permission_handler`). `sdk-free/flutter-build.sh <app dir>`.
- Asset catalogs (icons) and storyboards, compiled by this repo's `actool` and `ibtool`.
- Signing with a development profile (`tools/provision-dev.py`, `tools/sign-dev.sh`). `xtool install` with a free Apple
  ID is the intended route and is not yet checked in this mode.

## What it gives up (for now)

- SwiftUI, and Swift code that imports frameworks without an overlay (Combine, WebKit, ...): the overlay list is
  ObjectiveC, Darwin, Dispatch, CoreGraphics and Foundation.
- System frameworks beyond the ones in the list: Foundation, UIKit, CoreGraphics, QuartzCore, CoreFoundation,
  UserNotifications, and the C library. The list grows by release; a plugin that needs another framework needs its
  headers first.
- App extensions and widgets, macOS apps.
- Debug builds run on a device only under a debugger (iOS 26 and later refuse the debug engine otherwise).

## What it needs

- The same toolchain as the full mode (`./install-toolchain.sh` does it): Swift, `xtool`, `pymobiledevice3`, `ipsw`.
- An iPhone connected over USB, unlocked, trusted, with Developer Mode on, only if you cut the stubs from the phone
  (the default when one is connected). Setup copies the phone's system-library cache (about 7 GB) once, cuts the
  stubs, and the copy can then be deleted.
- No phone: `sdk-free/setup.sh --ipsw` pulls the cache from Apple's public iOS update download instead
  (`--ipsw=<build>` or `--build <build>` pins the build, `--device <model>` or `SDKFREE_DEVICE` picks the model,
  default `iPhone16,2`; `SDKFREE_IPSW=auto` is the same as `--ipsw`). Setup builds the small cache reader
  `apfs-fuse` from a pinned source commit (`pacman -S --needed fuse3 cmake git gcc bzip2 zlib` if it cannot).
  The download lands in `$SDKFREE_HOME/cache` (`SDKFREE_TMP` moves it) and is deleted once the stubs are cut. A
  phone is then only needed to run the apps.
- For Flutter: `flutter/setup.sh` once, and the `llvm` and `rsync` packages (`flutter/README.md`).

## Files

| Path | What it is |
|---|---|
| `setup.sh` | builds `~/.local/share/omarchy-apple-dev/sdk-free` (`iPhoneOS.sdk`, `toolset`, `bin/actool`); safe to re-run |
| `cc.sh` | clang for arm64 iOS against that sysroot: `sdk-free/cc.sh -c main.m -o main.o` |
| `flutter-build.sh` | Flutter app to an unsigned `Runner.ipa` in `<app>/build/ios-sdkfree/<mode>/` |
| `ship.sh` | the release `Runner.app` signed for the App Store and uploaded to TestFlight with `--upload` (`sdk-free/ship.sh --upload <app dir>`; the app record must exist once for the bundle id, web UI) |
| `headers/` | the headers this mode adds to the sysroot |
| `shims/` | stand-ins for the Xcode command-line tools that `flutter assemble` calls |
| `runner/` | the Objective-C Runner (app delegate, scene delegate, `main.m`) |

Status: the Flutter build, link and signing steps are checked on Linux. A run on a device is the open check.
