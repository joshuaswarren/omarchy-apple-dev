# Findings: getting an iOS build and debug loop working on Omarchy Linux

Everything below came out of one session on 2026-09-09, taking a 13" M1 MacBook Pro
running Omarchy from a bare install to a SwiftUI app running and debuggable on an
iPhone 16 Pro Max (iOS 26.6.1). Fourteen things broke. Each one is recorded with the
error text, the root cause where it was found, and the fix.

Versions: Swift 6.3.3 (AUR `swift-bin`), xtool 1.19.0, LLDB 21.0.0, pymobiledevice3
from PyPI, iPhoneOS SDK 26.5 taken from Xcode 26.6.

## Toolchain

**1. No Swift in the Omarchy or Arch repos.** AUR `swift-bin` is the binary package:
about 3.3 GB installed, roughly 7 minutes. It ships clang and LLDB too.

**2. LLDB will not start: `libpython3.9.so.1.0: cannot open shared object file`.**
`swift-bin` lists `python39` as an optional dependency and LLDB is the thing that
needs it. Install AUR `python39`.

**3. `usbmuxd.socket` does not exist on Arch.** Guides tell you to enable it.
`usbmuxd.service` is static here and udev starts it when a device is plugged in.
Nothing to enable; `systemctl is-active usbmuxd` reads `active` once the phone is
connected.

## SDK

**4. `xtool sdk install` dies partway through copying.** It failed at 76,600 files
with `NSCocoaErrorDomain Code=513 "You don't have permission to save the file"`
while copying `/usr/lib/clang/22/include/fuzzer`. Root cause: swift-corelibs
`FileManager.copyItem` preserves ownership, so it calls `lchown` to root, which is
EPERM for a normal user. Fix: take ownership of the toolchain trees first,
`sudo chown -R "$USER" /usr/lib/clang /usr/lib/swift`.

**5. The SDK installs "successfully" and then SwiftUI will not compile.** The error
is `size of '__builtin_bit_cast' source type 'int' does not match destination type
'int64_t'` inside the simd/arm_neon C++ module. Root cause: xtool copies the clang
headers it finds on PATH into the SDK bundle. The system clang here is 22.1.8 while
the Swift compiler's own clang frontend is 21.0.0, and the headers are not
compatible across that gap. Fix: run the SDK install with the toolchain's clang
first on PATH, `PATH=/usr/lib/swift/bin:$PATH xtool sdk install ...`.

**6. A poisoned module cache survives the fix.** After rebuilding the SDK correctly,
the same project in the same directory kept failing with the same error. Fix: build
in a clean project directory, or delete `.build/arm64-apple-ios` before rebuilding.

**7. No `.xip` and no Apple ID are needed for the SDK.** xtool 1.19.0 accepts a path
to an extracted `Xcode.app` directory, not only an `Xcode.xip`
(`SDKCommand.swift`: "Path to Xcode.xip, Xcode.app, or darwin.xtoolsdk"). If any
machine on your network has Xcode installed, stream the pieces xtool wants (about
3 GB) instead of downloading a multi-gigabyte archive behind a sign-in.

## Signing and install

**8. `xtool auth` password mode works with a free Apple ID.** Mode 1 uses private
APIs; mode 0 wants a paid membership and an API key. 2FA is prompted once. If your
Apple ID belongs to more than one team, it asks which team to sign under.

**9. `xtool dev run` is the whole loop.** Build, unpack, prepare device, provision,
sign, package, connect, install, verify. It took 11 seconds on this M1 with a warm
build, and the app launched on the phone with no further steps.

## Debugging, iOS 17 and later

These four are the ones that cost the most time, because the tools report the same
generic error for several different unmet prerequisites.

**10. `pymobiledevice3 developer debugserver start-server` fails on iOS 26**, even
with `--rsd` passed correctly. It prints a five-item list of possible causes, none
of which applies. Use `pymobiledevice3 developer debugserver lldb <bundle-id>
--rsd <address> <port>` instead: it starts debugserver and drives LLDB itself.

**11. The same generic error appears when the personalized developer image is not
mounted.** Check with `pymobiledevice3 mounter list` (an empty `[]` means nothing is
mounted), then `pymobiledevice3 mounter auto-mount`. It fetches a personalized image
through TSS and mounts it in a few seconds.

**12. `debugserver lldb` takes the bundle id as a positional argument.** There is no
`--bundle-id` option; passing one exits 2.

**13. The RemoteXPC tunnel needs root.** `sudo pymobiledevice3 lockdown start-tunnel`
creates `tun0` and prints the RSD address and port to pass to every later
`--rsd` call. Without sudo it cannot create the interface.

**14. Expect a long wait on attach, not a hang.** LLDB parses symbol tables out of
the device's shared cache before the process stops. On this 16 GB M1 that took about
90 seconds, printing a long stream of "Reading binary from memory" lines. The
successful result looks like this:

```
Attaching to pid 45977
platform select remote-ios
process connect connect://[fd57:f2c9:d44a::1]:63592
process attach --pid 45977
* thread #1, queue = 'com.apple.main-thread', stop reason = signal SIGSTOP
    frame #0: 0x000000023ddbdcd4 libsystem_kernel.dylib`mach_msg2_trap + 8
```

## Working sequence

```bash
# once
./install-toolchain.sh
PATH=/usr/lib/swift/bin:$PATH xtool sdk install ~/xcode-apple-sdk-src/Xcode.app
xtool auth                      # mode 1, Apple ID, 2FA, pick team

# per app
xtool new HelloOmarchy && cd HelloOmarchy
PATH=/usr/lib/swift/bin:$PATH xtool dev run

# debugging, phone connected, Developer Mode on
pymobiledevice3 mounter auto-mount
sudo pymobiledevice3 lockdown start-tunnel     # note the RSD address and port
PATH=/usr/lib/swift/bin:$PATH pymobiledevice3 developer debugserver lldb \
  <bundle-id> --rsd <address> <port>
```

## Still open

A source-level breakpoint in app code, hit on a tap. The attach above proves the
debugger controls the process and symbolicates frames; the breakpoint is the last
piece not yet demonstrated.
