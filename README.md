# Build and deploy iOS apps on Omarchy Linux (Apple Silicon)

SwiftUI apps built on an M1 Mac running Omarchy Linux, installed on a physical
iPhone over USB, with no Xcode and no macOS in the loop.

Based on a first successful run on 2026-09-09 with:

| Tool | Version | Source |
|------|---------|--------|
| Swift | 6.3.3 (aarch64-unknown-linux-gnu) | AUR `swift-bin` |
| xtool | 1.19.0 | xtool-org/xtool AppImage |
| pymobiledevice3 | latest from PyPI at install time | venv |
| LLDB | 21.0.0 (Swift toolchain) | bundled with `swift-bin` |
| iOS SDK | iPhoneOS 26.5 | Xcode 26.6 on a Mac, streamed as a directory |

Works with a free Apple ID. Paid membership not required for device installs.

## What you need

- An Apple Silicon Mac or Linux box running Omarchy (Arch-based), aarch64.
- An iOS device and a USB cable.
- One of:
  - A Mac with Xcode installed (any host on your network that you can SSH
    into), or
  - `Xcode.xip` downloaded from developer.apple.com (requires an Apple ID).

`xtool sdk install` accepts a path to an `Xcode.xip` **or an extracted
`Xcode.app` directory**. The directory route avoids the multi-GB download.

## Install

Run `install-toolchain.sh`, then get an SDK onto the machine:

- Directory route: stream only the pieces xtool needs from a Mac with Xcode
  (see `install-toolchain.sh`, section 5) into `~/xcode-apple-sdk-src/Xcode.app`,
  then `xtool sdk install ~/xcode-apple-sdk-src/Xcode.app`.
- XIP route: download `Xcode.xip` from
  https://developer.apple.com/download/all/?q=Xcode and run
  `xtool sdk install /path/to/Xcode.xip`.

Verify with `swift sdk list` (should print `darwin`).

## First app

```
xtool new HelloOmarchy
cd HelloOmarchy
xtool dev run
```

`xtool dev build` alone produces `xtool/HelloOmarchy.app` (arm64 Mach-O).

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
- Building SwiftUI pulls in simd/arm_neon headers; first build takes about a
  minute on an M1.

## License

MIT
