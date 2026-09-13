# Build and deploy iOS apps on Omarchy Linux (Apple Silicon and Intel)

SwiftUI apps built on a Mac running Omarchy Linux (M1, or an Intel/T2 Mac on
the t2linux kernel), installed on a physical iPhone over USB, with no Xcode and
no macOS in the loop.

This branch (`intel`) adds x86_64 support. Toolchain install, SDK install from
`Xcode.xip`, an arm64 SwiftUI build, and the device deploy are verified on a
2019 Intel MacBook Pro with an iPhone 15 Pro Max on iOS 26.6.1 (see the Intel
section below). LLDB attach is verified on aarch64 only so far.

Based on a first successful run on 2026-09-09 with:

| Tool | Version | Source |
|------|---------|--------|
| Swift | 6.3.3 (aarch64- or x86_64-unknown-linux-gnu) | AUR `swift-bin` |
| xtool | 1.19.0 | xtool-org/xtool AppImage |
| pymobiledevice3 | latest from PyPI at install time | venv |
| LLDB | 21.0.0 (Swift toolchain) | bundled with `swift-bin` |
| iOS SDK | iPhoneOS 26.5 | Xcode 26.6 on a Mac, streamed as a directory |

Works with a free Apple ID. Paid membership not required for device installs.

## What you need

- A Mac or Linux box running Omarchy (Arch-based), aarch64 or x86_64. Intel
  Macs with a T2 chip need the t2linux kernel (`uname -r` ends in `-t2`); the
  Omarchy T2 install already provides it.
- An iOS device and a USB cable.
- One of:
  - A Mac with Xcode installed (any host on your network that you can SSH
    into), or
  - `Xcode.xip` downloaded from developer.apple.com (requires an Apple ID).

`xtool sdk install` accepts a path to an `Xcode.xip` **or an extracted
`Xcode.app` directory**. The directory route avoids the multi-GB download.

## Install

Get an SDK source onto the machine first, then run `install-toolchain.sh`.
The script is the same on Apple Silicon and Intel; it picks the Swift package
and xtool AppImage for the host arch and installs the SDK from whichever
source it finds:

- Directory route: stream only the pieces xtool needs from a Mac with Xcode
  (see `install-toolchain.sh`, section 5) into `~/xcode-apple-sdk-src/Xcode.app`.
- XIP route (no second Mac needed): download `Xcode_*.xip` from
  https://developer.apple.com/download/all/?q=Xcode into `~/Downloads/`.

If neither is present the script stops after the toolchain and prints the
`xtool sdk install` command to run once you have one.

Verify with `swift sdk list` (should print `darwin`).

## First app

```
xtool new HelloOmarchy
cd HelloOmarchy
xtool dev run
```

`xtool dev build` alone produces `xtool/HelloOmarchy.app` (arm64 Mach-O). The
output is arm64 on an Intel host too: the SDK cross-compiles for the phone, the
host arch only decides which Swift and xtool binaries you run.

## Device

Plug the iPhone in, tap Trust when prompted, then:

```
./device-run.sh
```

First run needs `xtool auth` (interactive, your Apple ID; password mode works
with free accounts). Pairing happens through usbmuxd on first connect.

## Scripts

- `install-toolchain.sh`: everything up to and including the SDK install.
- `device-run.sh`: pair, install, launch, LLDB attach, with the phone connected.

## Findings

[FINDINGS.md](FINDINGS.md) records the fourteen things that broke on the way to the
first working run, with error text, root cause, and fix for each: SDK install
failures, a clang version mismatch that breaks SwiftUI, and the four unstated
prerequisites for debugging on iOS 17 and later.

## Notes

- `clang` on PATH must be the Swift toolchain's own clang, not the system
  clang. The SDK install copies the host clang headers into the bundle; a
  version mismatch between host clang and the Swift compiler produces
  `__builtin_bit_cast` size errors when compiling SwiftUI. Use
  `PATH=/usr/lib/swift/bin:$PATH` on Arch-based installs.
- Building SwiftUI pulls in simd/arm_neon headers (target headers, so on any
  host). First build: about a minute on an M1, about 95 s on an i7-9750H.

## Intel (x86_64) Macs

What differs from the Apple Silicon setup, checked on a 2019 MacBook Pro
(i7-9750H, T2, Omarchy on the t2linux kernel):

- `swift-bin` declares `arch=('x86_64' 'aarch64')` and fetches the
  swift.org ubi9 x86_64 tarball; nothing to change.
- xtool publishes `xtool-x86_64.AppImage`; `install-toolchain.sh` picks it
  via `uname -m`. xtool 1.19.2 x86_64 starts on Omarchy with only `fuse3`
  installed, no `fuse2` needed.
- `lsusb | grep -i apple` is not a usable "is the phone plugged in" test on
  a T2 Mac: the T2 controller, FaceTime camera, internal keyboard and Touch Bar
  all show as Apple USB devices. `device-run.sh` now matches the iPhone/iPad
  product IDs (`05ac:12a8`, `05ac:12ab`) from sysfs instead, and does not
  need `usbutils`.
- The host clang mismatch (Notes above, FINDINGS #5) applies unchanged: a
  fresh Omarchy x86_64 install has clang 22.1.8 on PATH while the Swift 6.3.3
  toolchain's clang is 21.x.
- usbmuxd is not installed by default; `install-toolchain.sh` step 1 covers it.
- Timings on an i7-9750H: cold SwiftUI build 94 s, warm `xtool dev run` to the
  phone 7 s (11 s on the M1).

## License

MIT
