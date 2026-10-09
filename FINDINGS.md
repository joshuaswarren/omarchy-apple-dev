# Findings: getting an iOS build and debug loop working on Omarchy Linux

Everything below came out of one session on 2026-09-09, taking a 13" M1 MacBook Pro
running Omarchy from a bare install to a SwiftUI app running and debuggable on an
iPhone 16 Pro Max (iOS 26.6.1). Fourteen things broke in the first run, and a
fifteenth surfaced on 2026-09-16, with items 16-20 following the same day;
item 21 came from the 2026-09-17 mise retest, and item 22 from the 2026-10-03
retest on xtool 1.20.1, which supersedes items 15 and 16. Item 23 is the App
Store path (build, sign, validate; upload unproven).
Each is recorded with the error text, the root cause where it was found, and the fix. `install-toolchain.sh`
applies every fix that can be automated (items 1 to 7); only Apple ID sign-in and
sudo consent genuinely need a human.

Versions of the first run: Swift 6.3.3 (AUR `swift-bin`), xtool 1.19.0, LLDB 21.0.0,
pymobiledevice3 from PyPI, iPhoneOS SDK 26.5 taken from Xcode 26.6. Current
working set (item 22): swift-bin 6.4.0, xtool 1.20.1, iPhoneOS SDK 27.0 from Xcode 27.0.

Confirmed on x86_64 (community report, Jon Kinney, 2026-09-15): the same flow
works on a Framework Desktop with an iPhone 16, used for a real client project.

## Toolchain

**1. No Swift in the Omarchy or Arch repos.** AUR `swift-bin` is the binary package:
about 3.3 GB installed, roughly 7 minutes. It ships clang and LLDB too.

**2. LLDB will not start: `libpython3.9.so.1.0: cannot open shared object file`.**
`swift-bin` lists a matching `python3xx` as an optional dependency and LLDB is the
thing that needs it; the install script reads that note off the installed package
and installs it (python39 through 6.3.x, python312 from 6.4).

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
`sudo chown -R "$USER:" /usr/lib/clang /usr/lib/swift` (the colon matters:
copyItem restores the group too, so it must be the user's login group). The
install script did this automatically before the SDK install. Obsolete since xtool
1.19.2 (xtool PR #255 copies with `preserveOwner: false`); the script no longer
touches ownership (item 22).

**5. The SDK installs "successfully" and then SwiftUI will not compile.** The error
is `size of '__builtin_bit_cast' source type 'int' does not match destination type
'int64_t'` inside the simd/arm_neon C++ module. Root cause: xtool copies the clang
headers it finds on PATH into the SDK bundle. The system clang here is 22.1.8 while
the Swift compiler's own clang frontend is 21.0.0, and the headers are not
compatible across that gap. Fix: run the SDK install with the toolchain's clang
first on PATH. The install script puts the bin directory of the `swift` on PATH
first (`/usr/lib/swift/bin` on swift-bin 6.3, `/usr/lib/swift/usr/bin` on 6.4).

**6. A poisoned module cache survives the fix.** After rebuilding the SDK correctly,
the same project in the same directory kept failing with the same error. Fix: build
in a clean project directory, or delete `.build/arm64-apple-ios` before rebuilding.
The install script prints this cleanup note after the SDK install.

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
```

## Known regression, 2026-09-16 (superseded 2026-10-03 by item 22)

**15. Swift 6.4.0 cannot build against the xtool darwin SDK.** AUR `swift-bin`
6.4.0 installs fine, the SDK registers fine (`swift sdk list` prints `darwin`),
and then every app build dies at planning with `error: unable to find platform
for 'iphoneos'`. Proven by an isolated A/B on one machine, one user, one SDK
bundle: the build fails under 6.4.0 with both xtool 1.19.0 and 1.19.2, and
succeeds the moment the system runs swift-bin 6.3.3 again. The bundle metadata
is identical in both cases (schemaVersion 4.0, same toolset.json), so the
regression is on the SwiftPM side. Workaround: run swift-bin 6.3.3 (build it
from the AUR package's git history). Confirmed on aarch64 and x86_64 with xtool
1.19.x. xtool 1.20 fixed it (item 22).

**16. The streamed SDK's Xcode must match the Linux Swift version.** The SDK
pieces carry Apple's prebuilt swiftmodules, and the Linux compiler refuses a
module built by a newer Apple Swift: an iOS 27.0 SDK from Xcode 27 (Apple
Swift 6.4) fails under swift 6.3.3 with `this SDK is not supported by the
compiler (the SDK is built with 'Apple Swift version 6.4 ...', while this
compiler is 'Swift version 6.3.3 ...')`. The matrix, all tested 2026-09-16:

| Linux toolchain | SDK source | Result |
|---|---|---|
| swift 6.3.3 | Xcode 26.6 (iOS 26.5) | builds; Mach-O produced |
| swift 6.3.3 | Xcode 27 (iOS 27.0) | rejected: SDK built by Apple Swift 6.4 |
| swift 6.4.0 | Xcode 26.6 (iOS 26.5) | planning failure, item 15 |
| swift 6.4.0 | Xcode 27 (iOS 27.0) | planning failure, item 15 |

Rule: the SDK's Xcode must ship the same Swift minor as the Linux toolchain:
Xcode 26 for Swift 6.3, Xcode 27 for Swift 6.4. On xtool 1.20.1, swift 6.4.0 +
Xcode 27 builds (item 22); swift 6.4.0 + Xcode 26.6 was not retested.

## Toolchain swaps, 2026-09-16

**18. makepkg and SwiftPM can fill /tmp's tmpfs.** On Omarchy, /tmp is a
small tmpfs (4 GB here). Unpacking AUR sources (swift-bin is ~800 MB
compressed, 3.3 GB installed) or building a SwiftUI app dies mid-extract
with `I/O error 122` / `No space left on device` when it fills. Fix: point
TMPDIR at the real disk — `TMPDIR=$HOME/tmp makepkg -si`; the same variable
covers SwiftPM's scratch files.

**19. Toolchain swaps (mise/asdf/manual) used to end in a full multi-GB
reinstall; `install-toolchain.sh --repair` now recovers from cache.**
Tested on a fresh x86_64 Omarchy VM by pinning swift 6.3.3 at /usr/lib/swift
(AUR swift-bin), registering the SDK, then removing that package and running
swift from a second install under
~/.local/share/mise/installs/swift/6.3.3 (the layout mise would create).

What survives a swap by design: USB pairing (`~/.pymobiledevice3/`), Apple
ID auth (`~/.local/share/xtool/`), and even the SDK registration itself —
the bundle in `~/.swiftpm/swift-sdks/darwin.artifactbundle` is user-global
and its metadata uses bundle-relative paths (`toolset.json`:
`"rootPath": "toolset/bin"`, `"linker": {"path": "ld64.lld"}`; the absolute
paths live only in `swift sdk configure --show-configuration` output,
resolved at use time). After the swap, `swift sdk list` still prints
`darwin` and a clean project still builds end to end.

What actually breaks:

1. **mise cannot complete a Swift install on Omarchy** — see item 20.
   As of 2026-09-17 the URL bugs are fixed on mise main; the remaining
   wall is `libncurses.so.6` (Arch ships `libncursesw.so.6` only). A
   "clean mise swap" on Omarchy still means AUR `swift-bin` at a
   different path, or a swift.org tarball plus that soname.
2. **The project-side module cache**: after any toolchain change, building
   in an existing project can die on stale precompiled modules — same
   failure class as item 6. Fix: delete that project's `.build`.
3. **Loss of the SDK registration** (`swift sdk remove darwin`, a wiped
   `~/.swiftpm`, a partial install) used to require the `Xcode.xip` again —
   and users delete the .xip after installing, so recovery meant
   re-downloading 3 GB from Apple behind a sign-in. That was the reinstall
   circus.

The fix in `install-toolchain.sh`: the SDK step now runs `xtool sdk build`
once and keeps the resulting portable bundle at
`~/.cache/xtool/darwin-<xcodever>.xtoolsdk`; the registered copy is made
FROM that cache, so first install and every later repair exercise the same
path. Whenever `swift sdk list` lacks darwin on a re-run, the script
re-registers from the cache — no .xip, no network.
`install-toolchain.sh --repair` does just that part, against whatever
toolchain the current shell resolves (mise included), verifies pairing and
auth, prints a survive-status summary (SDK source used / pairing path /
auth state), and exits nonzero with instructions when the cache is missing
and no XCODE_XIP is given. The version matrix (items 15-16) still applies:
--repair re-registers the same bundle; it cannot make a 6.4.0 toolchain
consume an Xcode 26.x SDK.

## Working sequence

```bash
# once
./install-toolchain.sh          # handles python dep, fuse3, PATH, SDK install
xtool auth                      # mode 1, Apple ID, 2FA, pick team

# per app; the toolchain's own bin dir first (item 5)
export PATH="$(dirname "$(readlink -f "$(command -v swift)")"):$PATH"
xtool new HelloOmarchy && cd HelloOmarchy
xtool dev run

# debugging, phone connected, Developer Mode on
pymobiledevice3 mounter auto-mount
sudo pymobiledevice3 lockdown start-tunnel     # note the RSD address and port
pymobiledevice3 developer debugserver lldb <bundle-id> --rsd <address> <port>
```

## Where it stands

Closed 2026-09-10, after this list was written: the source-level breakpoint.
`ContentView.describe(tick:)` at `ContentView.swift:27` was hit on device, source
lines printed, `p tick` returned `(Int) 1`. A static SwiftUI app still cannot be
breakpointed usefully: instrument the app with a `.task` timer loop so execution
reaches the breakpoint without a physical tap. Single-stepping is untested
(`next` reported an unchanged frame line, inconclusive) and needs the phone
connected for five minutes.

New on 2026-09-16 (Milestone 3): `install-toolchain.sh` applies items 1 to 7 by
itself and was proven end to end by a fresh-user install on a second M1 Omarchy
machine and in a clean x86_64 Arch container, through `swift sdk list` and a
Mach-O sample build. `device-run.sh` gained a `--network` mode (same-LAN
wireless deploy, xtool native) and an `--rsd HOST PORT PKG` mode (install to an
explicit address); both are written from the tool sources and are UNVERIFIED
until run against a phone.

**17. Wireless deploy on iOS 26 requires a host-specific RemotePairing tunnel that only a Mac can currently establish (tested exhaustively 2026-09-16).** With Developer Mode on, USB-paired, unlocked, same SSID/subnet, `EnableWifiConnections` true, an active USB RSD tunnel (`lockdown start-tunnel` succeeded), and DDI mounted, an iPhone on iOS 26.6.2 never becomes wirelessly deployable from Linux: pulling the USB cable kills the tunnel and nothing re-establishes over WiFi.

What the phone actually does on the network: every host that wants wireless debugging gets its OWN encrypted RemotePairing tunnel, advertised per-host as `<uuid>._rp-tunnel._tcp` with an ephemeral port (observed 55518/55520) on IPv6 link-local/ULA addresses. A macOS host that once enabled "Connect via Network" holds a live tunnel (devicectl: Transport `localNetwork`) — the phone accepts only that host; connections from other IPs to the tunnel port are refused. The pre-iOS-17 paths are dead on 26.6.2: `_remoted._tcp` is advertised only over USB; legacy `_apple-mobdev2._tcp` is advertised but its listener (tcp/32498) never binds; tcp/62078 accepts and then resets the lockdown handshake; usbmuxd2's WiFi heartbeat fails on the same wall. `pymobiledevice3 remote pair` needs the device to advertise `_remotepairing-manual-pairing._tcp`, which no iOS 26.6.2 settings screen we could find produces (the `remote pair-host` device-initiated flow is iOS 27+).

Practical guidance: use USB (proven end to end by this repo). Wireless works only for hosts the phone already tunneled with via a Mac/Xcode; for that case `pymobiledevice3 remote tunneld` on a Mac that holds the tunnel, plus `--tunnel UDID@HOST:PORT` from Linux, is the bridge pattern (documented in device-run.sh). The Linux side is otherwise ready: with usbmuxd2 (AUR `usbmuxd2-git` + the -git libimobiledevice stack) and pymobiledevice3, a future iOS that reopens device-side pairing needs zero new plumbing here.

**Update (same day, researched after the verdict):** the iOS 27 door is
already implemented client-side. `pymobiledevice3 remote pair-host`
advertises this machine as a pairable host; on an iOS 27 device with
Developer Mode on, Settings → Developer → **Paired Macs** shows it under
"Other Devices" — tap, enter the printed 6-digit code, and the pairing
record is reused by `remote start-tunnel` for the wireless tunnel. All of
that ships in pymobiledevice3 11.12+ (the version this repo installs).
Untested here only because no iOS 27 device was on hand.


**20. mise's swift backend is broken on Omarchy — two distinct bugs (tested
2026-09-16, mise 2026.8.8).** (1) For distros outside its known map
(ubuntu/amzn/ubi/fedora), `src/plugins/core/swift.rs` builds the artifact
platform as the raw `os-release` `ID`+`VERSION_ID`, producing
`swift-6.3.3-RELEASE-omarchy4.0.1rc2-aarch64.tar.gz` → download.swift.org
404. Omarchy's `ID_LIKE=arch` is ignored. (2) On arm64, the download
directory only gets its required `-aarch64` suffix for ubuntu builds
(`platform_directory()`), so even with `mise settings set swift.platform
ubi9` the URL misses (`ubi9/…` 404s; the artifact lives under
`ubi9-aarch64/`). URL matrix verified against download.swift.org: x64
ubuntu2404/ubi9/fedora39 = 200; arm64 only `ubuntu2404-aarch64` = 200.
With `swift.platform=ubuntu24.04` on arm64 the download succeeds but mise's
runtime verification fails on Arch (`bin/swift` exit 127) and the install
rolls back — likely a shared-library mismatch in the ubuntu build. Filed upstream:
https://github.com/jdx/mise/discussions/13289 (fabricated names, ID_LIKE ignored)
and /13291 (arm64 directory suffix).

**Update 2026-09-17, retest on jwm1 (Omarchy 4.0.1rc2 aarch64).** jdx
merged [#13293](https://github.com/jdx/mise/pull/13293) (directory suffix)
and [#13297](https://github.com/jdx/mise/pull/13297) (release-index +
`ID_LIKE` + UBI fallback). Neither is in a tagged release yet: latest tag
`v2026.9.10` published 2026-09-16 17:25Z, before both merges. Retested
with a git build at `533346cc` (crate still reports 2026.9.10, built
2026-09-17).

Control, system mise 2026.8.8: still 404s on
`swift-6.3.3-RELEASE-omarchy4.0.1rc2-aarch64.tar.gz`.

Git build: warns `swift 6.3.3 publishes no build for omarchy 4.0.1rc2; using ubi9`,
then downloads
`https://download.swift.org/swift-6.3.3-release/ubi9-aarch64/swift-6.3.3-RELEASE/swift-6.3.3-RELEASE-ubi9-aarch64.tar.gz`
(the `-aarch64` directory 13291 asked for). Extract succeeds. Post-install
`swift --version` then fails:
`error while loading shared libraries: libncurses.so.6`. Arch/Omarchy
ships `libncursesw.so.6` only; `/usr/lib/libncurses.so.6` is absent.
mise rolls the install back. This is the third issue jdx asked confirmed
in #13289: the ubi9 artifact does not run on Arch as-is.

Status: 13289 and 13291 are fixed on main. The runtime failure is a
narrow-vs-wide ncurses naming split, not a mise bug — and it is
solvable; see item 21.

**21. mise CAN install and run Swift on Omarchy: the ubi9 build needs three
narrow curses sonames Arch does not ship (proven 2026-09-17, jwm1).**

Every missing soname in the whole ubi9 6.3.3 toolchain, found by `ldd`-ing
all of `usr/bin` and `usr/lib/*.so*`:

| ubi9 binary wants | Arch ships |
|---|---|
| `libncurses.so.6` | `libncursesw.so.6` |
| `libform.so.6` | `libformw.so.6` |
| `libpanel.so.6` | `libpanelw.so.6` |

Three, all with wide-char twins. (`libtinfo.so.6` is already present on
Arch; `/usr/lib/libncurses.so` is an 18-byte linker script, not a runtime
library.) Arch's wide-only ncurses is deliberate policy; Debian/Ubuntu
ship one wide-compiled ncurses that provides *both* sonames, which is why
the vendor tarball runs there and not here.

The substitution is sound, not a gamble: `liblldb.so` imports **zero**
wide-char curses symbols (`_wch`/`_wstr`/`cchar` count = 0) — only the
narrow subset the wide build also exports — it records **no symbol-version
requirement** on any of the three, and `ldd -r` against the wide libs
resolves everything with no undefined symbols and no version warnings.

Shipped as `install-toolchain.sh --curses-compat` (2026-09-17): it aliases
whichever narrow curses sonames the host lacks to their wide twins in
`~/.local/lib/curses-narrow-compat`, optionally verifies an extracted
toolchain root with `ldd -r`, and prints the export line. No root, no
`/usr/lib` mutation.

```bash
./install-toolchain.sh --curses-compat
export LD_LIBRARY_PATH=~/.local/lib/curses-narrow-compat
mise install swift@6.3.3
```

Verified on that path with the `533346cc` build: `mise install swift@6.3.3`
passes its own `swift --version` gate (`Swift version 6.3.3
(swift-6.3.3-RELEASE)`, `Target: aarch64-unknown-linux-gnu`), `mise ls
swift` lists 6.3.3, `lldb --version` reports 21.0.0, and
`mise exec swift@6.3.3 -- swift build` builds a SwiftPM executable in
1.47 s.

`LD_LIBRARY_PATH` must reach the install subprocess. Two supported ways on
mise main (b467f28c, 2026-09-18, all four fixes merged and live-verified on
a second Omarchy arm64 host): the shell export shown above, or the tool
option jdx named as the supported knob —

```toml
[tools]
swift = { version = "6.3.3", install_env = { LD_LIBRARY_PATH = "{{env.HOME}}/.local/lib/curses-narrow-compat" } }
[env]
LD_LIBRARY_PATH = "{{env.HOME}}/.local/lib/curses-narrow-compat"
```

`install_env` covers the install-time verification (its values now render
templates, mise #13314); `[env]` covers runtime exec. `[env]` alone was
never applied to install subprocesses — by design, since `[env]` may depend
on tools that are not installed yet. Bare installs now fail with every
missing soname named at once (`this swift build needs shared libraries
missing from this host: libform.so.6, libncurses.so.6, libpanel.so.6`,
mise #13315/#13319) instead of a bare exit 127. Not in a tagged mise
release yet; main only.

Two more host notes from the second machine: current Arch also needs
`libxml2.so.2` aliased to `.so.16` for `swift-package`/`swift-build`
(resolves clean under `ldd -r`; xml-heavy lldb features unexercised), and
`lldb` needs a real `libpython3.9.so.1.0` — genuinely not aliasable
(`_Py_IsFinalizing` no longer exists in python 3.14); copy it from the
Rocky/Alma 9 `python3-libs` rpm if absent.


Residual risk, closed 2026-09-18: the curses TUI itself was the remaining
unknown and it PASSES. On jw16 (M1 Max, Omarchy arm64) the ubi9 lldb ran
`gui` under the aliases: full chrome rendered (menu bar, Sources/Threads
panes), F1 opened the dropdown menu, arrow+Enter selection worked, and
Exit returned cleanly to the `(lldb)` prompt. Draw, input, and teardown
all run through the wide libraries.

Two host-package notes from that machine, distinct from the ncurses
shim: current Arch ships libxml2 `.so.16` (2.15) so the ubi9 lldb also
needs a `libxml2.so.2` alias — empirically clean (`ldd -r` resolves, no
xml-symbol failures; loader prints harmless "no version information"
warnings) but xml-dependent lldb features are unexercised. And it needs
a REAL `libpython3.9.so.1.0` — no alias works there (`_Py_IsFinalizing`
is gone from python 3.14; genuine ABI break). On this install python39
is already present via swift-bin's dependency chain; machines without it
can copy `libpython3.9.so.1.0` from the Rocky/Alma 9 `python3-libs` rpm
into the compat directory.


This does not change what this repo installs. AUR `swift-bin` already did
the same reconciliation properly at package level — its `swift` links
`libncursesw.so` directly — and it remains `install-toolchain.sh`'s path.
Items 15 and 16 are superseded by item 22 (xtool 1.20.1 + Swift 6.4 + Xcode 27).

## xtool 1.20, 2026-10-03

**22. xtool 1.20.1 + swift-bin 6.4.0 + Xcode 27 builds; the 6.3.3 pin is over.**
xtool 1.20.0 (2026-09-21) added Swift 6.4 support by driving SwiftBuild instead
of SwiftPM's `--swift-sdk` path, which is where item 15's planning failure lived.
Retested in a clean Arch x86_64 root (archlinux-bootstrap, 2026-10-03) with the
repo's own `install-toolchain.sh` as a brand-new user, SDK pieces streamed from
an Xcode 27.0 (27A266a) install:

| Linux toolchain | xtool | SDK source | Result |
|---|---|---|---|
| swift-bin 6.4.0-2 | 1.20.1 | Xcode 27.0 (iOS 27.0) | debug and release build; Mach-O arm64 |

Three install-path changes fell out of the retest:

1. swift-bin 6.4.0-2 moved the toolchain binaries to `/usr/lib/swift/usr/bin`.
   A hardcoded `/usr/lib/swift/bin` leaves clang off PATH, and `xtool sdk
   install` stops with `Error: Could not find executable 'clang' in PATH`.
   Both scripts now derive the directory from `readlink -f $(command -v swift)`,
   which also covers mise installs.
2. The step 3 chown (item 4) is not needed with xtool 1.20.1: the fresh user
   built and registered the SDK while `/usr/lib/swift` stayed `root`-owned.
   The old step also died on hosts without a system clang
   (`chown: cannot access '/usr/lib/clang'`), so it is deleted.
3. The xtool AppImage runtime needs `fusermount3` (`Error: No suitable
   fusermount binary found on the $PATH`); the script installs `fuse3`.

xtool 1.20's SDK builder also reads `Contents/Info.plist`, `version.plist` and
each `Platforms/*.platform/Info.plist`; the Route B piece list now includes them.
The SDK cache is named after the iOS SDK inside it
(`darwin-iPhoneOS27.0.xtoolsdk`) instead of the input file name. The version
rule of item 16 still holds: Xcode 27 for Swift 6.4, Xcode 26 for Swift 6.3.
Device install and LLDB on this pair are not yet re-run on hardware.
Receipt: `receipts/2026-10-03-xtool-1.20-swift-6.4-x86_64.md`.

## App Store path, 2026-10-03

**23. An App Store `.ipa` can be built, signed and validated on Linux; the
upload itself is unproven.** xtool signs only with development profiles and
compiles no asset catalogs, so `ship.sh` adds the rest. Proven in the clean
Arch x86_64 root by a brand-new user: `install-toolchain.sh`, `xtool new`, a
single-size 1024 AppIcon, `ship.sh` → 35/35 offline checks pass. Apple's own
tools on a Mac accept the result: `codesign --verify --deep --strict` reports
`valid on disk` and `satisfies its Designated Requirement`, `codesign -dvvv`
shows `TeamIdentifier`, sealed resources v2 and the entitlements, and
`assetutil --info` parses the `Assets.car`. Each validator check also fails
on a deliberately broken build (no team id, Info.plist edited after
signing, `get-task-allow` true, no Assets.car or profile).

What had to be built, and why:

1. **App icon.** xtool has no `.xcassets` support (xtool#219). AssetKit 1.0.0
   (xtool-org) compiles catalogs, but rejects Xcode 14+'s default
   single-size icon (`AppIcon 'AppIcon' declares size 1024x1024 but no
   source file matched`), and does not resize. The Linux `actool`
   (`tools/darwin-tools`, item 24) expands that form into 60@2x, 60@3x,
   76@2x, 83.5@2x and the 1024 App Store icon (no alpha channel,
   ITMS-90717); `ship.sh` runs it with `--app-icon`, as Xcode does for an
   app target.
2. **iPad Pro icon (fixed, item 26).** AssetKit 1.0.0 set every app icon's
   "Icon Index" to 1, so 76@2x and 83.5@2x collided and iPad apps failed
   the 167 px check.
3. **Build-environment keys.** App Store processing reads `DTXcode`,
   `DTXcodeBuild`, `DTSDKName`, `DTSDKBuild`, `DTPlatform*`, `DTCompiler`;
   xtool writes none. `asc.py stamp` takes the SDK values from the darwin
   bundle and the Xcode values from `Contents/version.plist`, which
   `install-toolchain.sh` now keeps next to the SDK cache. A `.xip` install
   hides that file: set `XCODE_VERSION` and `XCODE_BUILD`.
4. **Distribution signing.** `rcodesign` 0.29.0 (pinned, checksummed) signs
   with any key, certificate and entitlements. Without `--team-name` the
   CodeDirectory carries no team id (`TeamIdentifier=not set` in
   `codesign -dvvv`); `ship.sh` passes it from the profile.
5. **Identity.** With an App Store Connect key, `asc.py identity` creates an
   Apple Distribution certificate from a CSR made on this machine and an
   `IOS_APP_STORE` profile. Without one, `asc.py test-identity` makes a
   self-signed stand-in of the same shape, which is what the run above
   used.
6. **Upload.** The App Store Connect API has a build-upload resource
   (`POST /v1/buildUploads`, `POST /v1/buildUploadFiles`, chunked `PUT`s,
   `PATCH uploaded`, then poll for `COMPLETE`/`FAILED` with Apple's errors),
   so no Transporter and no macOS. `/v1/apps` is GET-only, so the app record
   is a one-time web step. A throwaway key unknown to Apple gets a clean
   `401 NOT_AUTHORIZED`, which proves the token and HTTP path up to auth.

Unproven until a real key and app record exist: certificate and profile
creation, Apple's processing of a Linux-built `.ipa` (DT keys, an
AssetKit `Assets.car`, rcodesign's Apple-certificate signature), and a
TestFlight install.
Receipt: `receipts/2026-10-03-ship-offline-validation.md`.

## A real project: IceCubesApp, 2026-10-03

**24. A real SwiftUI app hits seven walls on xtool 1.20 + Swift 6.4; six are fixed
here, the seventh (SwiftData macros) in item 26.** IceCubesApp
(Dimillian/IceCubesApp at 9efcb16: 13 local packages, 12 remote ones, String
Catalog in 19 languages, 9 asset catalogs, SwiftData, AppIntents) was adapted
without moving any source: one `omarchy-xtool/` directory (Package.swift that
points at the app's folders through symlinks, xtool.yml) and one changed line.
Each wall, in the order the build hit it:

1. **Branch-pinned dependencies fail.** Any `branch:` dependency stops
   `xtool dev build`: `a resolved file is required when automatic dependency
   resolution is disabled ... was resolved to 'main' but now has a different
   revision-based requirement`. Reproduced on the template with one dependency
   (`from:` builds, `branch: "main"` fails). xtool builds a helper package in
   `xtool/.xtool-tmp` with `--disable-automatic-resolution` and no
   `Package.resolved`; copying the root's file in makes the same `swift build`
   pass. Not fixable from outside xtool; IceCubes' DesignSystem package now
   points its `fix-ios26` EmojiText branch at a local checkout (the one
   changed line).
2. **`.xcassets` and `.xcstrings` resources fail** with `failed to launch.
   .../xtool/.xtool-tmp/actool` (and `xcstringstool`): SwiftBuild runs
   Apple's tools, which Linux lacks. SwiftBuild looks for them in the darwin
   SDK's `Platforms/iPhoneOS.platform/Developer/usr/bin` (probed: not `PATH`,
   not the SDK `toolset/bin`). `install-toolchain.sh` now installs two Linux
   stand-ins there:
   - `tools/xcstringstool` (Python, stdlib): `compile` (both formats,
     `--dry-run`, `-l`) and `generate-symbols --language swift`. Checked file
     by file against Xcode 27's xcstringstool: IceCubes' catalog (735 keys,
     19 languages, plural, device and substitution variations) gives 38 of 38
     files and 0 differing keys, `stringsdictOnly` 19 of 19 and 0, an
     edge-case catalog 4 of 4 and 0; the generated Swift symbols are
     identical text for both catalogs (435 and 7 symbols).
   - `actool` (Swift, `tools/darwin-tools`, on AssetKit): `--version`, the
     asset-symbol mode and the compile mode, with the dependency-info file.
     For a light/dark colorset plus a 1x/2x/3x imageset, the generated Swift,
     ObjC header, symbol index, partial Info.plist, stdout and dependency
     records match Apple's actool 27.0, and Xcode's `assetutil --info` lists
     the same renditions for both `Assets.car` files.
3. **AssetKit wrote colors CoreUI cannot read** (`assetutil`: one component,
   `2e-323`, colorspace `generic`) and failed on system-color colorsets
   (`"reference": "labelColor"`). Fixed on
   `joshuaswarren/AssetKit@omarchy/color-csi` to actool's byte layout, with
   tests that pin actool's bytes; `darwin-tools` pins that commit.
4. **`.strings` copies fail**: `no --inputencoding specified and could not
   detect encoding from input file`. SwiftBuild detects text encodings only
   on Darwin. The installer sets `STRINGS_FILE_INPUT_ENCODING = utf-8` in
   the SDK platform's `DefaultProperties`.
5. **`Too many open files`** while building SDK modules. A login shell gets a
   soft limit of 1024 open files; `ulimit -n 65536` (the hard limit is
   524288) before `xtool dev build` clears it.
6. **Asset types AssetKit lacks.** IceCubes' app catalog has 32 alternate app
   icons, two `.symbolset`s, a `.solidimagestack`, HEIC images and an empty
   AccentColor. actool now merges all catalogs of a target, drops color-less
   colorset entries, and leaves out what AssetKit cannot compile with a
   `warning: skipped by the Linux actool` line each (37 for IceCubes). Those
   assets are missing at run time until AssetKit supports them.
7. **Cross-import overlays are off.** `StoreView` (StoreKit + SwiftUI) is
   `cannot find 'StoreView' in scope` on Linux; SwiftPM passes
   `-enable-cross-import-overlays` only for test targets. The installer adds
   `-Xfrontend -enable-cross-import-overlays` to the SDK's
   `toolset-swb.json`; the template repro then builds.

**SwiftData** stopped the build at `@Model`: `external macro implementation
type 'SwiftDataMacros.PersistentModelMacro' could not be found`. Fixed in
item 26. Receipt: `receipts/2026-10-03-icecubes-compat.md`.

## No sudo, no FUSE, 2026-10-03

**25. The whole pipeline runs for a user with no sudo: `install-toolchain.sh
--user-only`.** It skips the pacman/yay steps and uses the Swift on PATH. Run as
a new user with no sudo and with `fuse3` removed (clean Arch x86_64 root), with
the swift.org `swift-6.4.0-RELEASE-ubi10` tarball (the build AUR swift-bin
repackages): template build `Mach-O 64-bit arm64`, a template with `.xcassets` and
`.xcstrings` resources builds (`Assets.car`, `de.lproj/Localizable.strings`), and
`ship.sh` passes 35/35. Two fixes fell out:

1. Without `fusermount3` the xtool AppImage cannot mount; the installer now
   unpacks it (`--appimage-extract`) and links `~/.local/bin/xtool` to its
   `AppRun`.
2. `LD_LIBRARY_PATH` (item 21's curses shim) works for `swift --version` but not
   for builds: SwiftBuild runs swiftc and the linker with a scrubbed
   environment (`swiftc: error while loading shared libraries: libncurses.so.6`
   at the link step). `--curses-compat ROOT` now also links the aliases into
   the toolchain's own RUNPATH directories (`usr/lib`, `usr/lib/swift/linux`;
   every binary there searches one of them), plus `libxml2.so.2` when the host
   has only `.so.16`.

Receipt: `receipts/2026-10-03-user-only-x86_64.md`.

## IceCubesApp builds and validates, 2026-10-04

**26. IceCubesApp now builds end to end on Linux and its App Store `.ipa`
passes 38 of 38 offline checks.** Four more walls after item 24:

1. **SwiftData macros.** Apple's macro plugins are macOS binaries, and xtool's
   OpenAppleMacros server (v1.3.0) has none for SwiftData (xtool#149).
   `joshuaswarren/OpenAppleMacros@omarchy/swiftdata` adds `@Model`,
   `@Attribute`, `@Relationship`, `@Transient`, `#Unique`, `#Index`,
   `@ModelActor`, `@Query` and their helper macros. Its integration tests
   compare each expansion with Xcode 27's: 102 of 102 pass.
2. **`#Predicate` and `#Expression` expand for the wrong module.** With
   `@Model` fixed, `cannot find 'FoundationEssentials' in scope`. The
   toolchain's own `libFoundationMacros.so` is swift-foundation built without
   `FOUNDATION_FRAMEWORK`, so it qualifies names with `FoundationEssentials.`,
   which a Darwin target does not have. `@omarchy/foundation-macros`
   (a517a2a) compiles swift-foundation's macro sources (a211bea) with
   `FOUNDATION_FRAMEWORK` defined: 113 of 113 tests pass against Xcode 27.
   An empty `libFoundationMacros.so` stub in the SDK's plugin directory
   outranks the toolchain plugin, so the compiler sends these macros to the
   OpenAppleMacros server. `install-toolchain.sh` builds the fork (static
   Swift stdlib, so a toolchain swap cannot break it), installs it in the
   SDK, and adds the `SwiftDataMacros` and `FoundationMacros` stubs.
3. **A compiler crash for an Xcode-excluded file.** swift-frontend 6.4 crashed
   in const-value extraction (`ConstExtract.cpp`, `Bad pointer dereference`)
   instead of reporting `cannot find type 'ListsWidgetConfiguration' in
   scope`. The project file excludes `IceCubesAppIntents/ListEntity.swift`
   from the app target (a `PBXFileSystemSynchronizedBuildFileExceptionSet`);
   the compat `Package.swift` now excludes it too. The crash is a compiler
   bug, not a Linux one: a 9-line file (a property wrapper with an unknown
   generic argument on a type in the const-extract protocol list) crashes
   both the Linux swift-6.4-RELEASE and Xcode 27's `swiftc` (6.4.0.34.1).
4. **iPad Pro icon.** `joshuaswarren/AssetKit@omarchy/color-csi` (0521ae7)
   writes one Icon Index per size and the MultiSized Image entries. For the
   same images, `assetutil --info` lists the same 6 icon and 4 MultiSized
   entries as Xcode 27's actool, including pad 167 px. A universal-icon demo
   now passes 38 of 38 checks.

`ship.sh` now compiles the app icon with the Linux `actool --app-icon`, so the
separate `xcassets` tool is gone. IceCubes' iOS icon is an Icon Composer
`AppIcon.icon`, which AssetKit cannot compile; `APP_ICON=Icon` uses its
legacy `Icon.appiconset`, without the dark and tinted variants. On a Mac,
`codesign --verify --deep --strict` reports `valid on disk` and `satisfies its
Designated Requirement` for the IceCubes `.ipa`.

Still missing at run time: `.icon` icons, alternate icons, symbol sets,
solid image stacks, HEIC images, dark and tinted icons (all skipped with a
warning), and App Intents metadata (Apple's `appintentsmetadataprocessor`
is macOS-only).
Receipt: `receipts/2026-10-04-icecubes-ship.md`.

## From .xcodeproj to xtool, 2026-10-04

**27. `tools/xcodeproj2xtool.py` turns an Xcode project into an xtool adapter;
the generated IceCubesApp adapter builds and passes 38 of 38 checks.** xtool
builds SwiftPM packages, so a normal `.xcodeproj` app needs an adapter: a
`Package.swift` for the app target, `xtool.yml`, and symlinks to the target's
folders. The generator (Python stdlib) reads `project.pbxproj` and the target's
xcconfig files, and maps synchronized folder groups with their membership
exceptions, classic groups with the Sources and Resources phases, remote and
local package references, the deployment target, bundle id, Info.plist (or one
built from `INFOPLIST_KEY_*`), Swift language mode, default actor isolation
and upcoming features. A `branch:` requirement becomes the `revision:` from the
project's `Package.resolved` (item 24.1). Xcode lets a target import modules
that reach it only through other packages; SwiftPM does not, so the generator
scans the target's imports and adds those packages. Anything it cannot map
(extensions, Objective-C, storyboards, run scripts, `.icon`) prints one
`warning:` line. `--self-test` runs 18 checks on a synthetic classic-group
project.

IceCubesApp: the generated adapter has the same packages, exclusions and
resources as the hand-written one (`xtool dev build` → `Build complete!`;
`APP_ICON=Icon ship.sh` → `38/38 checks passed`).

Second project, NetNewsWire (Ranchero-Software/NetNewsWire @ 8c322c2, 10k
stars, SPM only): `compat/nnw/setup.sh` runs its prebuild script, replaces one
Objective-C file with Swift, adds two missing `import UIKit` lines, and runs the
generator. It stops at three platform walls, in build order:

1. **No `ibtool`.** xtool probes for it for storyboards and xibs (`ibtool
   --version ... failed to launch`). The generator leaves the 7 Interface
   Builder files out, so the build continues, but a UIKit app that loads them
   cannot run.
2. **Grayscale colorsets crashed the Linux `actool`** (fixed): `Key 'red' not
   found ... components` for a `gray-gamma-22` color with `white`/`alpha`
   components. AssetKit `8ddc2de` decodes all six Xcode color spaces and writes
   them as actool 27.0 does: for one colorset per space (light and dark),
   `assetutil --info` lists the same 12 entries, with bit-identical components.
3. **Dynamic library products do not link (open: needs xtool and SwiftPM
   fixes).** Every module compiles, but the app link fails: all 15 local
   packages declare `type: .dynamic` products, and the app sees `ld64.lld:
   error: undefined symbol: $s2os6LoggerV6RSCoreE12nnwSubsystemSSvau` and 19
   more. A template app with one `.dynamic` local package shows three causes:
   - The dylib link gets no Swift runtime (`undefined symbol:
     swift_errorRetain`, `swift_once`): no `-lswiftCore`, no `-L` to the SDK's
     `usr/lib/swift`. The SDK toolset's `linker.extraCLIOptions` can add both.
   - The dylib exports nothing: SwiftPM compiles the module for static
     linking and links it as an archive, which a dylib never pulls from.
     SwiftPM turns that off for dynamic products only on Windows
     (`PackagePIFProjectBuilder+Products.swift`). `-all_load` in the same
     toolset list works around it.
   - xtool embeds each dylib in `Frameworks/` but never adds `-l<name>` to
     the app link, and embeds a dylib once per dependency edge (`File
     exists` for `libRSWeb.dylib`). Two small patches to xtool's
     `PackLib/Packer.swift` and `Planner.swift` fix both.

   With all three, a patched xtool built from source builds NetNewsWire
   (15 dylibs in `Frameworks/`, `@rpath` install names) and `ship.sh` passes
   38 of 38. The installer does not apply the toolset flags: they help only
   with the patched xtool, and `-all_load` affects every link. Unverified:
   whether App Store processing accepts loose `.dylib` files in
   `Frameworks/` (Xcode packages dynamic SwiftPM products as frameworks).

## aarch64 parity, 2026-10-04

**28. The same no-sudo path works on aarch64 Omarchy.** On jwm1 (M1), as a new
user with no sudo and the swift.org `swift-6.4.0-RELEASE-ubi10-aarch64` tarball:
`install-toolchain.sh --user-only` exits 0 (SDK, actool, xcstringstool, the
OpenAppleMacros build), the template builds to `Mach-O 64-bit arm64`, an app with
`.xcassets`, `.xcstrings`, `@Model` and `#Predicate` builds, and `ship.sh` passes
38 of 38 checks. Apple's `codesign --verify --deep --strict` accepts the `.ipa`.
The whole run, SDK and macro server builds included, took 7 min 20 s.
Receipt: `receipts/2026-10-04-user-only-aarch64.md`.

## Icon Composer icons, 2026-10-04

**29. The Linux `actool` renders Icon Composer `.icon` app icons, flat.** Xcode
26+ icons made in Icon Composer are a folder with `icon.json` and layer images.
Apple's `actool` 27.0 compiles them into 1024 px icon images per appearance plus
the layered iOS 26 icon (IconImageStack, IconGroup, gradients). The Linux
`actool` now paints the background fill (the `system-light` preset is white to
92.5% gray, decoded from Apple's output) and every visible PNG or SVG layer at
its scale and offset onto a 1024 px canvas, then compiles that like a
single-size app icon. `ship.sh` finds `AppIcon.icon` as well as
`AppIcon.appiconset`. IceCubesApp now ships with its real `AppIcon.icon` and no
`APP_ICON` override: 38 of 38 checks, and Apple's `assetutil` lists the same
icon images and MultiSized entries as for an appiconset. Against Apple's
120 px rendering of the same icon, the mean pixel difference is 11.3 of 255:
same composition, but flat. One `warning:` line each names what is not
rendered: Liquid Glass, specular highlights, shadows, translucency, blur,
non-normal blend modes, and the dark and tinted variants.

## The installer builds the fixed xtool, 2026-10-04

**30. `install-toolchain.sh` now builds xtool from source with four fixes, so
NetNewsWire builds with no manual steps.** The fixes are on
`joshuaswarren/xtool@omarchy/1.20.1-fixes` (9cdd470: release 1.20.1 plus
xtool-org/xtool#290 branch-pinned dependencies, #291 a dynamic library embedded
twice, #292 dynamic products linked into the app, #293 the SDK toolset's dylib
link flags). The installer builds it once per commit (about 7 minutes on
x86_64) with `-no-toolchain-stdlib-rpath` and copies the Swift runtime
libraries it uses next to it, so its RUNPATH is `$ORIGIN` only and a toolchain
swap cannot break it. The AppImage, and with it the FUSE requirement, is gone;
the build needs `base-devel`, `git`, `libimobiledevice` and `openssl`. The
installer also adds `-lswiftCore -L/usr/lib/swift -all_load` to the SDK
toolset (ld64 resolves `-L/usr/lib/swift` under `-syslibroot`, so the path
works wherever the SDK lives; without `-all_load` the app link fails with
`undefined symbol: $s6DynLib8dynValueSiyF`), and an `ibtool` that answers
SwiftBuild's `--version` probe and refuses real work (the probe runs for every
iOS target and stops the build when it fails).

A new user in a clean Arch x86_64 root: installer exit 0, xtool RUNPATH
`[$ORIGIN]`, template `Build complete!`. With that toolchain the regression set
passes: a `branch:` dependency and a `.dynamic` product build, the demo apps
ship 35/35 and 38/38, IceCubesApp ships 38/38.

The generator now converts the app extensions an app embeds (one target,
product and `xtool.yml` entry each, with its own Info.plist), honors Xcode's
"add this file to another target" exception sets, and stops re-declaring
products that a declared local product already carries. NetNewsWire builds
with its widget and share extensions: 15 dylibs in `Frameworks/`, two `.appex`
bundles in `PlugIns/`, and Apple's `codesign --verify --deep --strict` accepts
the `.ipa`. The offline validator gained a check that fails it: xtool copies
each extension's dylibs into `PlugIns/<ext>.appex/Frameworks/`, which App
Store processing rejects (ITMS-90206). Open.

Third project, Mastodon for iOS (mastodon/mastodon-ios @ c52a630; widgets,
share, notification-service and intents extensions, Core Data):
`compat/mastodon/setup.sh` generates the adapter. Walls: Core Data needs
`momc` (`Could not determine generated file paths for Core Data code
generation`), and SwiftPM reports `Swift package product 'SwiftSoup-product'
is linked as a static library by 'Mastodon-App-product' and
'MastodonSDKDynamic-product'` (probably a real second path through MastoParse;
unverified).

## Extensions ship, 2026-10-04

**31. IceCubesApp and NetNewsWire ship with all their app extensions, from
generated adapters: 39 of 39 checks each.** Two more fixes made it:

1. **Extension dylibs.** xtool copied each extension's dynamic libraries into
   `PlugIns/<ext>.appex/Frameworks/`, which App Store processing rejects
   (ITMS-90206, item 30). xtool-org/xtool#295 keeps them in the app's
   `Frameworks/` and links extensions with Xcode 27's runpaths
   (`@executable_path/../../Frameworks`, `@executable_path/Frameworks`). The
   installer pins `joshuaswarren/xtool@3cbf66b`.
2. **Widget previews.** IceCubes' WidgetKit extension uses `#Preview(as:
   .systemSmall) { ... } timeline: { ... }`, which expands through
   `PreviewsMacros.Common`; OpenAppleMacros had no such macro. The fork
   (`omarchy/previews-common`, cb003a1) adds it and the SwiftUI and UIKit
   `#Preview` forms, with expansions checked against Xcode 27 (124 of 124
   tests).

With the fixed xtool, `branch:` dependencies resolve, nested ones included,
so the workarounds are gone: `compat/icecubes/setup.sh` is now a clone plus
one generator run (its hand-written `Package.swift` is deleted), and the
generator emits branch requirements as written. In a clean run, IceCubesApp
builds its app and 4 extensions (action, widgets, notifications, share) and
NetNewsWire its app, widget and share extensions with 15 dylibs. Both `.ipa`
files pass the offline checks, and Apple's `codesign --verify --deep
--strict` reports `valid on disk` for both.

## Core Data, 2026-10-04

**32. `tools/momc` compiles Core Data models on Linux.** SwiftBuild runs
Apple's `momc` twice: `momc --dry-run --action generate` lists the Swift files
code generation will write (an unparsable answer is the error `Could not
determine generated file paths for Core Data code generation`), then it
compiles the model into the resource bundle. The Python stand-in does both:
`.xcdatamodeld` to `.momd` (one `.mom` per version plus `VersionInfo.plist`),
`.xcdatamodel` to `.mom`, as NSKeyedArchiver archives in momc 27's layout, and
Swift code generation for `class` and `category` entities with Xcode 27's
text. Checked on a Mac against Apple's `momc` with `NSManagedObjectModel`:
Mastodon's 10-version model loads with 0 differences in every entity,
attribute, relationship, constraint, index and version hash (for example
v10: 385 checks, 0 differences, the same `versionChecksum`), and a SQLite
store written with Apple's model opens with ours, no migration. Mastodon now
gets past Core Data and stops at the duplicate-library check: `SwiftSoup` is
linked statically into both the app (through MastoParse, an app dependency)
and the `MastodonSDKDynamic` dylib. Xcode allows that; SwiftPM does not.

## First App Store upload, 2026-10-04

**33. App Store Connect accepts the upload from Linux and then validates it;
two Apple checks failed.** With a real API key (team Creatuity Corp.), `ship.sh
--upload` created an Apple Distribution certificate and an App Store profile,
signed the demo app, passed the offline checks and uploaded it through the
build-upload API (no Transporter, no Mac). Apple's processing then returned:

1. `error 90725: SDK version issue. This app was built with the iOS 17.0 SDK`.
   The Linux link writes the deployment target into the Mach-O
   `LC_BUILD_VERSION` sdk field. `asc.py stamp` now writes the SDK actually
   used (27.0) into every Mach-O in the bundle, and the validator checks it.
   The next upload passed this check.
2. `error 90562: Invalid Bundle. Invalid Asset Catalog. One of the files named
   Assets.car is not a valid Asset Catalog file`. Apple's `assetutil` reads the
   AssetKit-built `Assets.car`, but App Store processing rejects it. Open.

Nothing was submitted for review.

## aarch64, full pipeline, 2026-10-04

**34. On aarch64 the installer builds the fixed xtool and the macro server,
and NetNewsWire ships with its extensions.** jwm1 (M1), a new user with no
sudo, the swift.org `swift-6.4.0-RELEASE-ubi10-aarch64` tarball, repo at
c7216e9: `install-toolchain.sh --user-only` exits 0 (xtool 3cbf66b with
RUNPATH `[$ORIGIN]`, OpenAppleMacros cb003a1); the template builds to
`Mach-O 64-bit arm64`; the SwiftData resource app passes 39 of 39; NetNewsWire
builds with 15 dylibs and its widget and share extensions and passes 39 of 39.
Apple's `codesign --verify --deep --strict` accepts the NetNewsWire `.ipa`. The
whole run took 14 min 22 s. Receipt: `receipts/2026-10-04-aarch64-full.md`.

## A valid TestFlight build, Linux except one file, 2026-10-04

**35. Apple's processing accepts the Linux-built, Linux-signed app; only the
Linux `Assets.car` is rejected.** Diagnostic upload: the same demo app, Linux
binary and `rcodesign` signature, but with the `Assets.car`, loose icon PNGs
and partial Info.plist that Apple's `actool` 27.0 makes from the same catalog
(on a Mac). Result: `buildUpload ...: COMPLETE`, and App Store Connect lists
build 1.0.0 (202610041830) as `VALID`, `APP_STORE_ELIGIBLE`. The two uploads
with the Linux `Assets.car` (AssetKit, CoreUI 970 header, then a 1010 header)
stay `INVALID` with error 90562. So signing, provisioning, the DT keys, the SDK
stamp and the binary are accepted; the asset catalog is the last Mac
dependency for TestFlight. Apple's own output also corrected the offline
validator: for a single-size AppIcon, `actool` stores only the 1024 icon and
names it inside `CFBundleIcons` (no top-level `CFBundleIconName`), so the
validator now requires the full size set only for multi-size icons. Nothing
was submitted for review.

## Mastodon: a toolchain fix and a dependency wall, 2026-10-04

**36. Mastodon's duplicate-library error is a SwiftPM 6.4.0 bug, fixed in
6.4.2; then old Nuke does not compile with Swift 6.4.** SwiftBuild resolves
"diamond" package graphs by promoting a shared static library to its dynamic
variant. Xcode keeps those variants (its build of a 3-package repro has one
`SLib.framework`, linked by the app and by the dynamic product, and no
diagnostic). The SwiftPM 6.4.0 command line turned the variants off, so the
same graph fails with `Swift package product 'SwiftSoup-product' is linked as
a static library by 'Mastodon-App-product' and 'MastodonSDKDynamic-product'`.
SwiftPM release/6.4.2 restores them (b3613845, "Enable promotion of automatic libraries to dynamic libraries"); with a 6.4.2 `swift-build`
(xtool honors `SWIFTPM_CUSTOM_BIN_DIR`), the graph plans and SwiftSoup is
built once. Turning the diagnostic off instead (`DISABLE_DIAMOND_PROBLEM_DIAGNOSTIC`)
builds, but links SwiftSoup into both binaries, which Xcode does not do. The
next wall is Mastodon's own pin: Nuke 10.11.2 fails with Swift 6.4
(`ImagePipeline.swift:286:47: error: cannot convert value of type
'Result<(data: Data, response: URLResponse?), ImagePipeline.Error>'`). The
installer will pick up the SwiftPM fix with the first 6.4.2 toolchain; no
workaround is shipped.

## Asset catalog: bisecting Apple's rejection, 2026-10-04

**37. Apple accepts our icon pixels, our name identifier and our identity
strings one at a time; the all-Linux `Assets.car` is still rejected.** The
Linux `actool` now writes a single-size app icon the way `actool` 27.0 does:
2 renditions (the 1024 icon image and one MultiSized entry), Apple's BOM block
order and sizes, the single-size BITMAPKEYS descriptor, Apple's loose icon
PNGs (`AppIcon60x60@2x.png`, `AppIcon76x76@2x~ipad.png`) and Apple's partial
Info.plist shape. Apple's `assetutil --info` lists the same two entries for
both cars. Three hybrid uploads each changed Apple's own car in one way:
our LZFSE pixel payload, our NameIdentifier (5444 instead of 6849), and our
identity strings ("omarchy-apple-dev actool (AssetKit)"). All three builds are
`VALID`. The all-Linux car is still `INVALID` with error 90562 (uploads at
20:42Z and 21:14Z); the next step tests the combination of the three.

The generator now maps `SWIFT_ENABLE_BARE_SLASH_REGEX` (Xcode's default for
iOS 16 and later) for Swift 5 targets, excludes storyboards and xibs on every
resource path with one warning, and warns when the launch or main storyboard
is among them. The installer turns off text-based stub generation in the SDK
(`GENERATE_TEXT_BASED_STUBS=NO`; Linux has no `tapi`), which the promoted
dynamic libraries of SwiftPM 6.4.2 need. With those and a 6.4.2 `swift-build`,
Mastodon reaches its SiriKit intents: Xcode generates the intent classes
from `.intentdefinition` files, and Linux has no intent compiler (`cannot find
type 'FollowersCountIntent' in scope`).

## TestFlight from Linux, 2026-10-04

**38. A build made entirely on Linux is VALID in App Store Connect.** Build
1.0.0 (202610042155) of the demo app: xtool binary, Linux `actool`
`Assets.car`, `asc.py stamp` Info.plist keys, `rcodesign` signature with an
API-created Apple Distribution certificate and App Store profile, and the
build-upload API. `buildUpload ...: COMPLETE`, then `VALID`,
`APP_STORE_ELIGIBLE`. The last 90562 rejection was a container bug: AssetKit's
BOM writer declared 256 index entries and wrote only the used ones, so the
file ended inside the index table. Apple's `assetutil` reads such a file; App
Store processing does not. AssetKit 410cf2f writes the full index, and the
Linux car now differs from an accepted hybrid only in content Apple accepts
(item 37). The regression set passes with it: demo 36/36, iPad demo 37/37,
IceCubesApp and NetNewsWire with their extensions 37/37. Nothing was submitted
for review. Receipt: `receipts/2026-10-04-testflight-all-linux.md`.

## SiriKit intents, 2026-10-04

**39. `tools/intentbuilderc` generates SiriKit intent classes on Linux; the
generator runs it, so no SwiftPM change is needed.** Xcode generates Swift
classes for every intent, custom type and enum in an `.intentdefinition`
file. SwiftPM's SwiftBuild backend does not route `.intentdefinition` package
files to the intent compiler at all (it does for Core Data and Core ML
models), so a package build never asks for them. The stand-in (Python
stdlib) writes the same Swift text as Xcode 27's `intentbuilderc`: all 8 files
for Mastodon's two definitions are byte-identical. `xcodeproj2xtool.py` runs
it at conversion time with Xcode's arguments, symlinks the output into the
target's sources, and keeps the `.intentdefinition` as a resource. With it,
Mastodon has no missing intent types; the build stops only at its pinned Nuke
10.11.2, which Xcode 27 cannot compile either (item 36).

## A real app in TestFlight, 2026-10-05

**40. NetNewsWire, built, signed and uploaded entirely on Linux, is VALID in
App Store Connect.** Build 7.1.4 (202610050846) of NetNewsWire with its widget
and share extensions and 15 SwiftPM `.dynamic` products: `buildUpload
ad8849b0: COMPLETE`, then `VALID`, `APP_STORE_ELIGIBLE`. Nothing was submitted
for review. Three App Store processing walls fell on the way:

1. **Icons (ITMS-90022, 90023).** The single-size icon was compiled for iPhone
   only. The Linux `actool` now keys it per `--target-device` and compiles the
   dark and tinted variants (gray `GA8`/`GA16` renditions), as `actool` 27.0
   does; the catalog's other assets are kept. AssetKit 87cd7d6.
2. **Loose dylibs (ITMS-90426, "The SwiftSupport folder is missing").** App
   Store processing rejects `Frameworks/lib<Name>.dylib`. `asc.py frameworks`
   moves each into `<Name>.framework` with an FMWK Info.plist and rewrites the
   install names in every Mach-O of the app, in the header padding.
3. **Processing that never ends.** With the `Assets.car` of NetNewsWire's
   catalog, uploads passed Apple's upload checks and then stayed `PROCESSING`
   for hours with no error. An Xcode-built copy of NetNewsWire, signed and
   uploaded by this pipeline, was VALID; with our executable, Info.plist and
   frameworks swapped in it stayed VALID, and with our `Assets.car` it stuck.
   Car subsets narrowed it to colorsets and tinted icons. Apple's `assetutil`
   reads those cars without complaint. The cause was BITMAPKEYS: each
   descriptor must be `(tokens + 4) * 4` bytes for the car's KEYFORMAT token
   count, with the icon's real group count and all-1 color slots. AssetKit
   1f23d61 and 16c561f write them as `actool` 27.0 does at 8, 9, 10, 13 and 14
   tokens. Processing checks every car in the app: the SwiftPM resource
   bundle's `Assets.car` alone, from the old AssetKit, kept a build with
   Apple's main car in `PROCESSING` (8198e86f); the same bundle from 16c561f
   is VALID (fc19d596).

The Linux `actool` also compiles PDF imagesets now (a vector rendition and
1x/2x/3x bitmaps through poppler's `pdftocairo`; 76 of 76 NetNewsWire PDF
renditions match Apple's `assetutil` output). Symbol sets are still skipped.
The regression set passes: demo 37/37, iPad demo 38/38, IceCubesApp 98/98,
NetNewsWire 83/83. IceCubesApp (without its extensions) is VALID with the same
toolchain. Receipt: `receipts/2026-10-05-netnewswire-testflight.md`.

## Mastodon builds and ships offline, 2026-10-05

**41. Mastodon for iOS builds on Linux with the stock Swift 6.4.0 toolchain and
passes all 114 offline App Store checks.** `compat/mastodon/setup.sh` applies
two documented overlay changes before the generator runs. Nuke moves from
10.11.2, which neither Swift 6.4 nor Xcode 27 compiles (item 36), to 12.9.0;
the one call site moves to the `NukeExtensions` module. The SwiftSoup diamond
(item 36) is removed from the project side instead of with SwiftPM 6.4.2,
which has no release: MastoParse (3 files) is vendored into the MastodonSDK
package as a target of `MastodonSDKDynamic`, so both SwiftSoup users sit in
the dylib and SwiftSoup is linked once, as Xcode's build does (the app binary
has no SwiftSoup strings; the framework has them). A fresh run:
`setup=0`, `Build complete! (96.71 secs)`, `ship.sh`: `114/114 checks passed`
with the TEST identity. The app and its 5 extensions need App Store Connect
records before an upload. The launch and main storyboards are still excluded
(no `ibtool`).

## Storyboards: the format, 2026-10-05

**42. Xcode 27.0 compiles iOS storyboards and xibs to binary NIBArchive nibs,
and a stdlib reader decodes all of them.** For an iOS target `ibtool` writes
version-1 `NIBArchive` files (not keyed-archive plists): one nib per xib, and
one `.storyboardc` directory per storyboard with an Info.plist and one nib per
scene. Xcode runs a storyboard in two steps: `ibtool ... X.storyboard
--compilation-directory DIR`, then `ibtool --link APP DIR/X.storyboardc`, which
keeps the `.lproj` parent. `tests/ibtool/compile-golden.sh` replays those exact
commands on a Mac; its output for 5 NetNewsWire storyboards and 2 xibs is
byte-identical to the 36 files in Xcode's own NetNewsWire.app. `tools/nibarchive.py`
dumps a nib as a readable object graph and diffs two nibs; its self-test
decodes all 33 golden nibs. This is the comparison harness for a Linux `ibtool`;
nothing compiles storyboards on Linux yet.

The generator now replaces a launch storyboard it can express as the
`UILaunchScreen` Info.plist dictionary (one bare view with a background color,
plus at most one centered named image) instead of dropping it. NetNewsWire's
two launch storyboards (system background, nothing else) become
`UILaunchScreen = {}`, and its "launch UI will be missing" warning is gone.
Mastodon's launch storyboard is also its main interface, so it stays excluded
with the warning.

M1 of the Linux `ibtool`: `tools/nibarchive.py` also writes NIBArchive files
(all 33 golden nibs round-trip byte for byte; files end in `LNE\0`; varints
are 7-bit little-endian with the high bit on the last byte), and
`tools/ibtool --compile OUT.nib IN.xib` compiles a first xib subset: the two
tiny test xibs and NetNewsWire's `SettingsTableViewCell.xib` are byte-identical
to Apple's output. Any other element fails with an `error:` line and no output.
One piece is not derived yet: Apple orders the nib's key table by a hash of
the key set, so `tools/ibtool` carries the observed order per known key set.
The generator still excludes storyboards and xibs.

Mastodon's first upload (a diagnostic under the NetNewsWire record, without its
extensions; its own App Store Connect record is not created yet) was refused:
`error 90029: Storyboard file 'Main~ipad.storyboardc' was not found` (and
`~iphone`). Mastodon's Info.plist names `Main` as both `UIMainStoryboardFile`
and `UILaunchStoryboardName`, and the generator excludes storyboards. The
offline validator now fails on this (`UIMainStoryboardFile 'Main' is
compiled in the bundle (ITMS-90029)`). It checks only `UIMainStoryboardFile`:
NetNewsWire build ad8849b0 was VALID although its `UILaunchStoryboardName` and
its scene manifest named storyboards that were not in the bundle. Mastodon's
`Main.storyboard` is one bare view controller, the
same shape as NetNewsWire's launch storyboards, so the Linux `ibtool` storyboard
path (M2) is the fix.

## Mastodon in TestFlight, 2026-10-05

**43. Mastodon for iOS, with all five app extensions, its App Group, 28 custom
SF Symbols and its storyboards, built, signed and uploaded on Linux, is VALID
in App Store Connect.** Build 2026.08 (202610051741), `buildUpload 52016c3b:
COMPLETE`, then `VALID`, `APP_STORE_ELIGIBLE`. Three uploads failed on the way,
each now caught or fixed:

1. `90029: Storyboard file 'Main~ipad.storyboardc' was not found`. The
   generator now try-compiles every storyboard and xib with `tools/ibtool` and
   emits the ones it compiles; Mastodon's `Main.storyboard` is one of them.
2. `90357` (the share extension's `MainInterface.storyboardc` missing) and
   `90362` (`Action.js` not in the action extension). `tools/ibtool` compiles
   navigation-controller scenes, byte-identical to Apple for this storyboard,
   and `ship.sh` moves compiled storyboards, nibs and the JavaScript
   preprocessing file out of each target's SwiftPM resource bundle to the root
   of the app or extension, where Xcode puts them. The validator checks both.
3. Processing that never finished, again. The app's resource bundle held an
   empty `Assets.car`: the adapter symlinks `Preview Assets.xcassets`, and
   Foundation on Linux lists a symlinked directory's children as files, so
   `actool` found no assets. `actool` now resolves symlinked inputs. App Store
   processing also stalls on an empty car, not only on a malformed one.

The large MastodonAsset catalog needed three AssetKit fixes (baf0f98):
multi-page BOM trees (Apple's `assetutil` refused a 778-entry single leaf),
`provides-namespace` folder names, and symbol templates whose guides are
`<path>` elements. Regression: demo 37/37, iPad demo 38/38, IceCubesApp 99/99,
NetNewsWire 84/84. Receipt: `receipts/2026-10-05-mastodon-testflight.md`.

## Icon Composer icons with their layers, 2026-10-05

**44. The Linux `actool` compiles an Icon Composer `.icon` into the same
layered renditions as `actool` 27.0, and IceCubesApp with that icon is VALID.**
Item 29's flat render is gone. For IceCubes' `AppIcon.icon` the car now holds
the icon image stack, its groups, layers, named gradients and colors, with the
glass, shadow, translucency and blend parameters as Apple stores them (the
device renders the glass from this description), plus the pre-rendered icon
per appearance: Apple's `assetutil` lists 30 of 30 renditions identical to
Apple's car for the compared fields, and `partial.plist` is equal. The
pre-rendered pixels differ by a mean of 8.5/255 (light), 10.3 (dark) and 12.6
(tinted), because the Liquid Glass highlights are not reproduced; the layer
bitmap is stored LZFSE where Apple uses its deepmap2 codec. Neither stopped
App Store processing: IceCubesApp (extensions left out, uploaded under the
NetNewsWire record) `buildUpload d71302cc: COMPLETE`, build 202610051832
`VALID`. Code: AssetKit f5502f0 (`IconComposerCompiler`), and `actool` hands
the `--app-icon` `.icon` to it. Regression: demo 37/37, iPad demo 38/38,
IceCubesApp 99/99, NetNewsWire 84/84.

## IceCubesApp with its extensions in TestFlight, 2026-10-05

**45. IceCubesApp with all four extensions, its App Group and its layered
icon is VALID from Linux under its own App Store Connect record.** The five
bundle IDs were registered with the API key; the App Group and the app record
(6819399771) came from the developer and App Store Connect web sessions, as
for Mastodon. `compat/icecubes/setup.sh` now takes `BUNDLE_ID`, which the
generator uses to rebase the extension IDs. `ship.sh` signed all five bundles
with App Store profiles that carry the group; 99/99 offline checks passed;
`buildUpload 157008db: COMPLETE`, build 202610051936 `VALID`. Still left out:
alternate and extension icon sets, the HEIC avatar, and App Intents metadata.
Receipt: `receipts/2026-10-05-icecubes-extensions-testflight.md`.

## App Intents metadata, 2026-10-05

**46. `ship.sh` builds `Metadata.appintents` on Linux, and IceCubesApp with
its App Intents metadata is VALID.** `tools/appintentsmeta.py` replaces
Xcode's `appintentsmetadataprocessor` and the App Shortcuts training step. It
reads the `.swiftconstvalues` files that swift-build already writes, so no new
compiler flags are needed. On a minimal App Intents app built by `xcodebuild`,
all five output files are byte-identical to Xcode 27.0's. For IceCubesApp,
Xcode's processors and ours, run on the same Linux const values, give identical
`extract.actionsdata`, `version.json` and `root.ssu.yaml`; `nlu.lzfse` differs
only in its creation time. Like Xcode, the tool writes nothing for an extension
without App Intents types, and it stops with `error:` on any construct it has
not reproduced. The validator requires the metadata in every bundle that
declares App Intents types. IceCubesApp (app and 4 extensions):
`buildUpload 633e191b: COMPLETE`, build 202610052033 `VALID`.
Receipt: `receipts/2026-10-05-app-intents-metadata.md`.

## Storyboards: NetNewsWire complete, 2026-10-06

**47. The Linux `ibtool` compiles all of NetNewsWire's Interface Builder files
byte-identical to Xcode 27.0, and NetNewsWire with them is VALID.** Main (11
nibs), Settings (10), Inspector (7) and `SettingsComboTableViewCell.xib` equal
the storyboardc trees of NetNewsWire built by Xcode 27.0, and the self-test
now covers them. New encoders: table and collection view controllers with static
and prototype cells, split view controllers, generic scene views, stack views,
text fields, switches, sliders, buttons, bar button items, named and system
colors, and runtime attributes. Rules learned from oracle probes, not from the
app: Apple's constraint order (guides first, then items by frame-origin
distance, then fixed attribute tables); the identifier map in `Info.plist`
follows `__NSSetM` order, and its entry-point string is the same object as the
key only when the initial controller has an explicit `storyboardIdentifier`;
strings are `NSLocalizableString` only when the output sits in a `.lproj`.
Under SwiftPM, ibtool now maps the resource-bundle module
(`<package>_<target>`) to the target's Swift module; before, custom classes in
storyboards would not resolve at run time. NetNewsWire with no IB file
excluded: `buildUpload 256e6e7e: COMPLETE`, build 202610060017 `VALID`.
Receipt: `receipts/2026-10-06-nnw-storyboards-testflight.md`.

## Liquid Glass pre-render, 2026-10-06

**48. The Linux `actool` renders Icon Composer icons the way Apple's
IconRendering does, and IceCubesApp with it is VALID.** The baked light, dark
and tinted images follow display lists recorded from IconRendering on a Mac:
P3 background gradient, plus-darker group shadows, the translucency mask, glow,
glass highlights, and the chiclet rim and border. The mean difference from
actool 27.0 on IceCubes fell from 8.5/10.3/12.6 to 1.05/1.48/1.17 per 255
(light/dark/tinted), and is 1.3 to 2.9 on three held-out icons; no per-icon
tables are used. The rest sits at shape edges inside IconRendering's one
compositing render. Measured and ruled out: the resampling filter, an
anti-aliased distance transform, supersampled coverage, and the distance
field's 10-bit quantization (captured from RenderBox). AssetKit 3177a3e also
fixes vector-layer renditions that crashed Apple's `assetutil`. IceCubesApp:
`buildUpload 9cb09967: COMPLETE`, build 202610060039 `VALID`.
Receipt: `receipts/2026-10-06-liquid-glass-testflight.md`.

## HEIC images and solid image stacks, 2026-10-06

**49. The Linux `actool` compiles HEIC imagesets like actool 27.0 and drops
`.solidimagestack` for iOS, as Apple does.** For a HEIC image Apple writes two
renditions: the decoded bitmap (RGB555, LZFSE) and the original HEIF data kept
as-is. AssetKit 4fc6c5b decodes with libheif's `heif-convert` (the installer
adds `libheif`) and writes both; Apple's `assetutil` fields and `partial.plist`
are equal on a probe catalog. A `.solidimagestack` is a visionOS icon; for
`--platform iphoneos` Apple writes nothing and prints no warning, and so does
ours now. `actool` also omits `Assets.car` when no rendition remains, as Apple
does. IceCubesApp now ships its `avatar` image and builds without either
warning: `buildUpload 56d7cfe2: COMPLETE`, build 202610060246 `VALID`.
Regression: demo 37/37, iPad demo 38/38, IceCubes 101/101, NetNewsWire 85/85.

## Alternate app icons, 2026-10-06

**50. Alternate app icons and extension icons ship from Linux, and IceCubesApp
with all 35 alternates is VALID.** `actool` takes Xcode 27's
`--alternate-app-icon`, `--include-all-app-icons` and
`--standalone-icon-behavior`; the generator reads the matching build settings
into `xtool.env`, and `ship.sh` compiles each extension's own icon set into its
`.appex`. Against actool 27.0 on IceCubes' full catalog, every rendition type
has the same count, 333 of 355 renditions match on 8 `assetutil` fields, and
`partial.plist` is equal. An earlier car with the alternates stayed in
PROCESSING forever; swapping only the car and uploading variants showed the
old 16-bit path was at fault. Apple writes 16-bit renditions only for a
Display P3 source with a pixel more than 3/255 outside sRGB, stored as
extended-sRGB half floats, and ours now does the same. AssetKit 9f509fe also
matches Apple's BITMAPKEYS layout and keeps colored tinted icons in color.
IceCubesApp: `buildUpload d9f36a6e: COMPLETE`, build 202610060406 `VALID`.
Regression: demo 37/37, iPad demo 38/38, IceCubes 101/101, NetNewsWire 85/85.

## Swift macros: same expansions as Xcode, 2026-10-06

**51. Every Apple macro the three apps use expands on Linux to the same code
as Xcode 27.0.** Probes of `@Observable`, `@Model`, `@Query`, `#Predicate`,
`@Entry`, `#Preview` and `@Test` were compiled with the same flags on both
sides with `-dump-macro-expansions`; all match except a 2-space indent inside
`#Preview`, which does not change the compiled code.
Receipt: `receipts/2026-10-06-macro-parity.md`.

## App extension metadata like Xcode, 2026-10-06

**52. App extensions get the Info.plist keys Xcode 27.0 writes, and launch
storyboards ship compiled.** Compared with Xcode-built NetNewsWire, IceCubesApp
and Mastodon, and with a probe app that has a Live Activity widget: each
`.appex` now gets `UIDeviceFamily`, `CFBundleSupportedPlatforms` and the
widget accent and background color names; boolean `INFOPLIST_KEY_*` settings
are booleans; keychain access groups granted by the profile reach the signing
entitlements. The probe's widget extension Info.plist has the same key set as
Xcode's. Launch storyboards now compile with `tools/ibtool` instead of being
replaced by `UILaunchScreen`. Two traps on the way: `TARGETED_DEVICE_FAMILY`
`1,2,7` must become `[1, 2]` (the visionOS 7 failed upload 969d0cfd with
ITMS-90100; the validator now checks it), and moving a SwiftPM resource
bundle's whole contents to the app root made IceCubes stall in PROCESSING
(uploads f40a7e7a, 62aa547f); only storyboards, nibs and the extension
script move. NetNewsWire build 202610060550 and IceCubesApp build
202610060643 `VALID`; Mastodon offline 118/118.

## String Catalogs like Xcode, 2026-10-06

**53. `tools/xcstringstool` compiles String Catalogs to the same files as
Xcode 27.0.** Against Xcode-built apps: NetNewsWire 5 of 5 outputs
byte-identical; IceCubesApp 46 files in 19 languages identical (38 bytes, 8
after decoding, because Apple writes binary-plist dictionaries in random
order) and its generated Swift symbols byte-identical; Mastodon 2,769 files
byte-identical. Twenty probe catalogs compiled by Apple's `xcstringstool`
match ours in file selection, content, diagnostics and exit codes. Rules
from the probes: a source-language string in state `new` emits nothing; the
plural checks apply to the source language only, so drifted translations
compile; named printf arguments (`%(count)lld`) are numbered by first use.
Uploads with it: IceCubesApp 202610060806, NetNewsWire 202610060742 and
Mastodon 202610060753, all `VALID`.

## A packed-atlas key collision stalls processing, 2026-10-06

**54. Two packed-image atlases under one rendition key make App Store
processing hang.** AssetKit writes one `ZZZZPackedAsset` atlas per symbol set,
and two of IceCubes' atlases share the key (element 9, part 181, identifier 0).
Processing takes the first rendition with that key. AssetKit 98ff033 sorted
the catalog walk for byte-stable output, which put the smaller atlas first;
the other set's cached sprites then fall outside it, and upload f3a1784f
stayed in PROCESSING. Swapping only the order of that pair in the same car
processed in 2 minutes (dbad43f2, `VALID`); rewriting rendition names alone
did not help (ac2393f3). Apple writes one atlas per scale
(`ZZZZPackedAsset-1.0.1-gamut0`, `-2.0.1`, `-3.0.1`), so its keys never
collide. The pin stays on AssetKit 9f509fe, whose walk order happens to put
the larger atlas first; a byte-stable car needs Apple's one-atlas-per-scale
layout, and four cars with merged atlases built so far still did not finish
processing. **Final outcome 2026-10-07 (see item 59)**: the per-scale merge
stalls App Store processing for IceCubes (10+ h on three variants — single
shelf, wrapped, wrapped + atlas-first) while the same-night 9f509fe per-set
control goes COMPLETE in minutes; the pin stays at 9f509fe (main 6f9116f).

## Editor support with SourceKit-LSP, 2026-10-06

**55. SourceKit-LSP works on Linux for a generated adapter, but only through
real source paths.** The adapter reaches project files through symlinks
(`Sources/<Target>/iOS -> ../../../iOS`), and SwiftPM 6.4's build server
reports the symlink paths. An editor opens the real file, so definitions,
completion and diagnostics found nothing. SwiftPM also refuses
`textDocument/sourceKitOptions` for a real path with "Found multiple indexing
informations for the same source file". xtool `dev build-server` now sits
between the editor and SwiftPM (xtool-org/xtool#302). It rewrites
source lists to real paths and puts SwiftPM's own spelling back into each
request by byte substitution, so the rest of the request is unchanged. On
this toolchain, Foundation's stdin read and Subprocess's output stream both
lost bytes, so the proxy uses POSIX pipe I/O.
`--package-path` lets the `.bsp/xtool.json` that the generator now writes at
the project root point at `omarchy-xtool`. With these, 8 of 8 editor checks
pass for NetNewsWire and IceCubes from either folder (receipt
`receipts/2026-10-06-sourcekit-lsp.md`).

## LLDB on a device from Linux, 2026-10-06

**56. The swift.org LLDB debugs an iOS 27 app on an iPhone from Linux. A
`String` prints correctly only when LLDB has the device's Swift runtime on
disk.** The path: `xtool install`, Xcode 27's personalized DDI mounted with
pymobiledevice3, a `lockdown start-tunnel` RSD tunnel, and `pymobiledevice3
developer debugserver lldb`. The aarch64 swift.org `lldb` needs
`libpython3.12.so.1.0`, which Arch does not ship; a standalone CPython 3.12 on
`LD_LIBRARY_PATH` and `PYTHONHOME` works. The breakpoint hits and `frame
variable` reads an `Int`. Without on-disk libraries, LLDB reads `libswiftCore`
from process memory, and with an empty Swift metadata cache it pairs `String`
with the field descriptor that follows it in `__swift5_fieldmd`, the one of
`_StringBreadcrumbs` (fields `utf16Length`, `crumbs`), and prints a number. A
warm cache hides this. Linux LLDB never searches `~/Library/Developer/Xcode/iOS
DeviceSupport`: that lookup is inside the check for an Xcode developer
directory. `platform select remote-ios --sysroot "<dir>"` works, where
`<dir>/Symbols/usr/lib/swift/` holds the dylibs extracted (with `ipsw dyld
extract --slide`) from the shared cache of the same iOS build. pymobiledevice3
runs its own `platform select remote-ios`, which drops the sysroot, so the
lldb wrapper adds it to that command. With iOS 27.0.1 (24A446) libraries from
Apple's IPSW (libswiftCore UUID `D65D98D2`, the same as on the phone) and an
empty cache, `frame variable greeting` prints `"Hello from Omarchy Linux"`.
`expr` still fails because LLDB cannot load the app's Swift modules. Receipts
`receipts/2026-10-06-device-lldb.md` (by hand) and
`receipts/2026-10-07-device-run-lldb.md`: `device-run.sh --lldb` does it all
in one command (install, DDI, tunnel, the phone's Swift runtime, sysroot,
attach), and a scripted session hit the breakpoint at `ContentView.swift:7`
and printed `greeting = "Hello from Omarchy Linux"` and `launches = 42`.

## A notarized macOS app from Linux, 2026-10-06

**57. Linux builds, signs and notarizes a macOS app that Gatekeeper accepts.**
The darwin Swift SDK already holds MacOSX27.0.sdk. SwiftBuild compiles for
`arm64-apple-macosx14.0` when it gets the settings xtool gives it for iOS
(`--toolset <bundle>/toolset-swb.json`, `XCODE_EXTRA_PLATFORM_FOLDERS`, the
bundle's `toolset/bin` on PATH); without them it stops with "unable to find
platform for 'macosx'". The API key cannot create a Developer ID certificate
(HTTP 403, "This operation can only be performed by the Account Holder"), so
the certificate came from the developer portal with a CSR made on Linux; the
key never left Linux. `rcodesign sign --for-notarization` adds the hardened
runtime and a timestamp, and `rcodesign notary-submit --staple` uploads with the
App Store Connect API key and staples the ticket. On a Mac, `spctl` says
"accepted, source=Notarized Developer ID". The Mach-O still says `sdk 14.0`
(the deployment target), as iOS builds do before `asc.py stamp`. Receipt
`receipts/2026-10-06-macos-notarized.md`.

## A packed-atlas per scale, sized to process, 2026-10-07

**59. AssetKit now writes Apple's one-atlas-per-scale layout; IceCubes'
merged car still has a processing stall being separated.** The probe (actool
27.0 on macstudio, IceCubes' 2-set catalog and NNW's 2-set `two.xcassets`):
Apple packs every symbol set of a catalog into ONE
`ZZZZPackedAsset-<scale>.0.1-gamut0` per scale (keys element 9/part 181/
identifier 0, never colliding), cached renditions sit at element 85 with
`dimension2` = cached index, and each links its atlas through the 1010 INLK
TVL (key pairs element 9/part 181/scale/deploymentTarget); each scale group
is ordered [atlas, vectors, cached] at 1x and [atlas, cached] at 2x/3x.
Apple's packer is multi-row (the IceCubes 1x atlas places six sprites in two
shelves, 62x44) — its atlases stay tiny because its cached sprites are tiny
(15x16 at 1x), while AssetKit's template-bbox sprites are 199x110
(pre-existing; the VALID 9f509fe car carried the same). Branch
`omarchy/atlas-per-scale` on joshuaswarren/AssetKit merges all sets' sprites
into one shelf-wrapped atlas per scale (wrap at 2048 px: widest first, index
tie-break, max-row-width atlas) and orders atlas-first per scale.

Evidence, all TestFlight. Every merged-atlas variant stalled; the per-set
9f509fe control went COMPLETE in minutes.

| upload | AssetKit | IceCubes atlas layout | result |
|---|---|---|---|
| eb830d06 (202610062021) | bece8b6 | merged, single shelf 1496x150/2976x296/**4454x442** | PROCESSING 10+ h |
| 065dc987 (202610070209) | 9f509fe (control) | per-set, larger first, max dim 2078 | COMPLETE in minutes |
| fb2771bf (202610070230) | 6b10c19 (wrap) | merged, wrapped 1496x150/1664x546/1713x1187 | PROCESSING ~3 h |
| 0062c26c (202610070533) | d9a83f77 (wrap + atlas-first) | as fb2771bf, atlas first per scale | PROCESSING ~70 min |

NNW 202610070306 (c06a0480) and Mastodon 202610070316 (1216a4f5) are VALID
on 6b10c19; neither exercises the merged multi-set atlas (NNW does not
wrap, Mastodon has no symbol sets). Every car that ever processed had max
atlas dimension 2078; the 4454 px single shelf of eb830d06 was the one
measured outlier, but the wrapped (1713) and atlas-first variants still
stall past every historical VALID window, isolating the per-scale merge
as the remaining difference against the per-set 9f509fe control. Apple's
oracle for the same catalog emits per-scale too — so processing accepts
the layout in theory, but the catalog in this program passes App Store
processing only with per-set atlases. Pin stays at 9f509fe (main 6f9116f
reverted c13e459's mixed-commit bump to bece8b6); receipt
`receipts/2026-10-06-atlas-per-scale-testflight.md` records every upload
and verdict. Interim VALIDs on bece8b6: NetNewsWire 8443f8d0, Mastodon
c598be6d.

## NetNewsWire for Mac compiles and links on Linux, 2026-10-07

**58. The generator now writes adapters for macOS app targets, and NetNewsWire's
Mac app links on Linux.** `compat/nnw-mac/setup.sh DIR` clones NetNewsWire
8c322c2 and makes four mechanical changes. ObjC category members from the
bridging header become Swift shims, and Swift files that use AppKit types get
`import Cocoa`: Xcode injects both through the bridging header, SwiftPM does
not. Local package products become dynamic, because the project turns off the
duplicate-module check that SwiftPM has no switch for. AppKit xibs stay out of
the bundle with one `warning:` line each. The SwiftBuild release build for
`arm64-apple-macosx` then writes a 3.7 MB arm64 Mach-O executable. The iOS
adapter for NetNewsWire is byte-identical to the one from the old generator, and
the full regression passes. The app cannot show its windows yet: its 34 AppKit
xibs and MainMenu need a macOS nib compiler.

## A real Mac .app bundle from Linux, 2026-10-07

**60. ship-mac.sh turns a generated Mac adapter into a notarized .app; NetNewsWire
launches and stops one nib short of a window.** The bundle assembles from SwiftPM
products alone: the executable relinks with `-Xlinker -rpath
@executable_path/../Frameworks`, the local `lib*.dylib` products and
Sparkle.framework land in Contents/Frameworks (their `@rpath` install names then
resolve there), the app target's resource bundle also copies flat into
Contents/Resources so both `Bundle.main` and `Bundle.module` resolve, and
tools/ibtool compiles 21 of the Mac target's 35 xibs into
Resources (Base.lproj kept per nib, failures listed and skipped). Info.plist is
the generator's placeholder-expanded copy plus CFBundleExecutable/Identifier.
Two notarization traps: an expanded entitlements file left inside Contents/ makes
the whole bundle "unsealed contents present in the bundle root", and Apple
reports that only as "The signature of the binary is invalid" — rcodesign verify
passes it; `codesign -vvv --deep --strict` on any Mac names the real defect. And
NetNewsWire's entitlements (iCloud, APNs, app groups, kvstore) are
provisioning-restricted: without an embedded.provisionprofile macOS kills the
process at exec (direct exec exits 137/SIGKILL), so the script signs without
entitlements unless ENTITLEMENTS is set. With those fixed, notary says Accepted,
spctl says "accepted, source=Notarized Developer ID", and the app on an M1 Max
macOS 26.6 runs to its main event loop, creates its Application Support
databases, and aborts 1.0 s in: `TimelineContainerViewController` loads
`init(nibName: "TimelineContainerView")` and that nib is one of the 14 ibtool
cannot compile — its connections to in-view NSLayoutConstraints raise
"connection destination not found". A stub TimelineContainerView.nib moves the
same crash two outlets deeper (readFilteredButton, then
containerViewTopToHeaderConstraint), which pins the missing-feature list exactly.
MainMenu.nib is byte-identical to Xcode's golden; the 14 missing nibs are the
only gap between a launch and a window. Receipt
`receipts/2026-10-07-nnw-mac-ship.md`.

Follow-up, same day: ibtool main compiles TimelineContainerView and
AccountStatsWindow (24/35) and the app gets past the timeline nib to MainWindow
toolbar layout, where it aborts on the toolbar's Mark-All-As-Read button
(`-[NSButtonCell _resolvedImage]` ← `NSImageSymbolRepProvider
_bestRepresentationForImage`): its image is a custom catalog symbol
(`Assets.Images.markAllAsRead`), and the Linux actool compiles `.symbolset`
sources as generic "Vector Glyph" entries — assetutil shows the four symbolsets
present under that type but no symbol asset type — so AppKit's symbol provider
finds no symbol and macOS 26 turns the lookup into an `os_crash` abort
("NSImage requested a variant from a symbol that wasn't found in the asset
catalog"). Until actool writes real symbol assets, the four custom symbols
cannot be rendered; every other catalog image is present (225 entries).

## Developer ID provisioning for that Mac app, 2026-10-07

**61. MAC_APP_DIRECT profiles from the API carry team-wildcard app groups, push,
and kvstore — but empty iCloud containers — and the notarized, provisioned
NetNewsWire Mac app runs to its main window with both extensions registered.**
tools/provision-mac.py derives everything from the adapter: it registers each
xtool.yml bundle id (MAC_OS; the registration name must be alphanumeric plus
spaces — dots are refused), reads the capabilities each entitlements file
claims, enables them, creates a MAC_APP_DIRECT profile per bundle id bound to
the Developer ID certificate, writes build/provision/ in the names ship-mac.sh
embeds, and reports which claimed com.apple.* keys the profile does not back.
Capability API facts: the capabilityType enum is PUSH_NOTIFICATIONS (plain
"PUSH" is refused with the full enum list) and grants aps-environment
production even for Developer ID direct distribution; ICLOUD needs
capabilitySettings `[{"key": "ICLOUD_VERSION", "options": [{"key":
"XCODE_6"}]}]` because the bare create fails with "cannot have the CloudkitVersion
'null'"; APP_GROUPS takes no group list and the profile grants only
"9LX44YXXVX.*"-shaped names, so NetNewsWire's `group.com.ranchero.NetNewsWire-Evergreen`
cannot be backed (no source reads the group — dropped); iCloud containers
cannot be attached at all (the profile's icloud-container-identifiers is
empty), so the icloud keys ship dropped; the kvstore identifier
`9LX44YXXVX.com.ranchero.NetNewsWire` matches the team wildcard and ships.
The app id itself cannot be `com.ranchero.NetNewsWire-Evergreen` — explicit
App IDs are globally unique and Ranchero owns it (409 "not available") — so
the adapter ships under the team's ids
(com.joshuaswarren.omarchyappledev.netnewswire + .SubscribeToFeed /
.Mac.ShareExtension). Two ordering traps: ship-mac.sh expands ENTITLEMENTS to
build/<product>.entitlements, so a provisioning run that reads that path after
a ship sees the trimmed set and "backs everything" vacuously; and an app that
claims a key its embedded profile lacks is refused by launchd at spawn
(RBSRequestErrorDomain Code=5, POSIX 163) — regenerate build/provision/ from
the claims file, then ship. Final state on macstudio (M1 Max, macOS 26.6.2):
spctl "accepted, source=Notarized Developer ID", the app runs to its
three-pane main window (Smart Feeds with unread counts, ten real feeds with
favicons — the sandboxed network path works), Sparkle's first-run sheet shows
the actool-built app icon, pluginkit lists both appexes, and the Dock shows
the running app's icon. Receipt
`receipts/2026-10-07-nnw-mac-provision.md`.

## Info.plist placeholders a Linux build must fill, 2026-10-07

**62. Xcode bakes `$(AppIdentifierPrefix)` and `$(TeamIdentifierPrefix)`
(both "<TeamID>.") into every processed Info.plist from the signing team;
xtool expands no build settings, and xcodeproj2xtool.py dropped the
unresolvable key — so the dev-signed NetNewsWire iOS install of 2026-10-07
15:45Z trapped in `AppDelegate.application(_:didFinishLaunchingWithOptions:)`
at `iOS/AppDefaults.swift:47`
(`Bundle.main.object(forInfoDictionaryKey: "AppIdentifierPrefix") as! String`),
and the TestFlight build shipped the same gap (`Secrets/CredentialsManager.swift:25`
reads it too). The drop loop also only saw top-level string values, so
placeholders nested in dictionaries sailed through: the IceCubes ASC build
shipped `NSExtensionPrincipalClass = $(PRODUCT_MODULE_NAME).X` in the action,
notification, and share appexes — principal-class lookups that can only fail.
Fix: the generator resolves `PRODUCT_MODULE_NAME` (the c99extidentifier of the
target name), keeps the two team-prefix placeholders at any depth, and still
drops every other unresolvable value; the step that knows the team fills the
placeholders — `ship.sh` runs `tools/fill-team-prefix.py` with the profile's
`com.apple.developer.team-identifier` right after `asc.py identity` and before
rcodesign seals the plists, and a device install runs it with
`--from-xtool-auth` (or `--profile <development.mobileprovision>`) before
`xtool install`; `asc.py validate` now FAILs an ipa whose Info.plists carry
any surviving `$(...)`. Receipt
`receipts/2026-10-07-app-identifier-prefix.md`.

## A device mode for ship.sh: Xcode's root-level resources, 2026-10-07

**63. `ship.sh --device [TEAMID]` builds the app that the 2026-10-07
NetNewsWire device session had to fix by hand.** A release `xtool dev build`
leaves the target's resources inside the SwiftPM resource bundle
(`<App>_<Target>.bundle`), where only `Bundle.module` finds them — the two
launch traps of that session were exactly this: `Assets.Images.faviconTemplate`
(`RSImage(named:)!`, catalog image not at the app root) and ArticleTheme's
`*.nnwtheme` lookups through `Bundle.main`. Device mode runs the TestFlight
steps 1-3 unchanged, then copies every other entry of each target's resource
bundle to that target's root — the app and every extension — with `cp -an`, the
no-clobber form of the manual fix's `rsync --ignore-existing --exclude
Assets.car --exclude Info.plist`. Step 3's root Assets.car is what the catalogs
become (NNW's app car came out the same 7,116,032 bytes as the ship build's;
IceCubes's 70,251,424), so a car never collides; the one exception proves the
rule — IceCubes's widget had no `EXTENSION_APP_ICONS` entry, step 3 compiled
nothing for it, and its 18 KB bundle car reached the widget root, where Xcode
puts a widget's compiled catalog. Everything App Store-only is skipped (stamp,
framework wrapping, App Intents metadata, signing, package, validate, upload),
because flattening whole bundles into an App Store upload once stalled
processing — the App Store path is untouched. With a team id the mode fills the
team prefix first; without one it fails closed: the device path runs asc.py's
surviving-placeholder FAIL on the .app as its final step, and on the un-teamed
NNW run it exited 1 naming `Info.plist:AppIdentifierPrefix` in the app and both
appexes, then passed after `--device 9LX44YXXVX` filled them. Layout proof
against the TestFlight builds: NNW's root gained 28 entries (eight themes, four
RTF, four keyboard-shortcut plists, ContentRules.json, DefaultFeeds.opml,
PrivacyInfo.xcprivacy, the article js/css/html, en.lproj) and IceCubes's 141
files (fonts and sounds under Embeds, 19 lproj trees, per-appex lproj strings
and xib cells); in both apps every bundle entry sits at a root, and the only
files the TestFlight build has that the device app lacks are the skipped App
Store artifacts — `_CodeSignature`, `embedded.mobileprovision`,
`Metadata.appintents`, and NNW's dylibs still loose in Frameworks/ instead of
wrapped `.framework` bundles. Receipt
`receipts/2026-10-07-device-layout.md`.

**64. Flutter apps build for iOS on Linux; the missing piece was one compiler.**
`flutter build ios` drives Xcode, but under it there are only three things a
Linux host lacks. First, the Dart AOT compiler: Flutter publishes
`gen_snapshot` for iOS as a macOS binary, and its Linux-hosted Android one
(same snapshot version hash) emits `arm64 android compressed-pointers` where
the iOS engine demands `arm64 ios no-compressed-pointers`. Building it from
the Dart SDK at Flutter's `dart_revision` with one added GN argument
(`flutter/patches/dart-ios-target-on-linux.patch`: the host toolchain stays
Linux, `DART_TARGET_OS_MACOS_IOS` is defined) gives a header identical to
Xcode's, and since Flutter 3.47 the compiler writes the Mach-O dylib itself
(`--snapshot_kind=app-aot-macho-dylib`), so no Apple linker is needed.
Second, the Xcode command-line tools `flutter assemble` and the Dart build
hooks shell out to: `flutter/shims/` answers `xcrun --show-sdk-path` from the
darwin SDK bundle and forwards `lipo`, `strip`, `otool`, `install_name_tool`
and `dsymutil` to LLVM, after which `flutter assemble
release_ios_bundle_flutter_assets` runs unmodified, native assets included.
`flutter precache --ios` already works on Linux. Third, the Runner target:
every plugin with native code ships a `Package.swift`, so one generated
SwiftPM package built with SwiftBuild replaces the Xcode project. Two traps on
the way. The Swift toolchain's `ld64.lld` refuses iOS, and clang given the SDK
bundle's linker by path omits `-platform_version` until `-mlinker-version` is
passed. And llvm-strip and llvm-install-name-tool both leave the string pool
4-byte aligned; dyld refuses that for images built against the 27.0 SDK
(`mis-aligned LINKEDIT string pool`) while letting older-SDK images through,
so a prebuilt dylib loads and a locally compiled one does not.
`flutter/tools/macho-align.py` pads it. The stock Flutter storyboards at first
needed two neutral rewrites to fit the Linux ibtool; item 65 made the compiler
take them as they are and removed the rewrite.
Release device builds only. Receipt `receipts/2026-10-08-flutter-ios.md`.

**65. The Linux ibtool compiles Flutter's template storyboards byte-identical
to Xcode's.** `flutter create` still writes the `Main.storyboard` and
`LaunchScreen.storyboard` of the Xcode 7 era, and they use four things no
storyboard in the corpus had. (1) `<layoutGuides>` with
`viewControllerLayoutGuide` top and bottom, the guides that predate the safe
area. ibtool was skipping the element without an error, so the scene view nib
came out 1010 bytes where Apple's is 1863. Each guide is a `_UILayoutGuide`
(class fallback `UIView`) appended to the scene view's subviews after the
document's own, with one `_UILayoutSupportConstraint` (fallback
`NSLayoutConstraint`; width, priority 999) of its own and three constraints
that the view owns and the guide lists again under
`_UILayoutGuideConstraintsToRemove`: top is leading = view.leading, top =
view.top, height; bottom is leading = view.leading, height, view.bottom =
guide.bottom. They lead the view's constraint array, ahead of the document's,
and the view gets a subviews array and a constraint array even when the
document gives it neither. In the objects array the guides follow the view's
constraints and precede its subviews. (2) `<color white= alpha=
customColorSpace="calibratedWhite">` is stored as RGB with the white repeated,
not as a white color. The white passes through float32 and is then rounded to
ten significant digits, the alpha is only rounded (white 1/3 gives
`UIRed-Double` 0.3333333433 and 2/3 gives 0.6666666865, while alpha 0.1 stays
0.1): eight probe values, all identical. An opaque inline sRGB color writes
three `NSRGB` components, not four, the rule system and named colors already
followed. (3) A view saved with no design-time frame is 1000 x 1000 at the
origin, the scene view and an image view alike, and sorts at the origin in the
constraint order. Below a deployment target of 17.0 the scene view alone
becomes 393 x 852 instead: compiled at 13.0, 15.0, 16.6, 17.0 and 26.0, the
boundary is 17.0, so ibtool now reads `--minimum-deployment-target`, which it
had been accepting and ignoring. (4) On a scene image view,
`multipleTouchEnabled` (stored inverted, after `UIDeepDrawRect`) and
`image="Name"` for an asset-catalog image, whose placeholder is 1 x 1 whatever
the document's `<image>` resource says; both were dropped silently. The two
storyboards, three more with other whites and the 16.6 scene nib are in the
self-test. The six files also match, byte for byte, the `Base.lproj` of an app
that Xcode 27.0 itself built from these storyboards at a 16.6 target. With
that, `flutter/tools/storyboard-compat.py` is gone and `flutter/build.sh`
compiles the app's storyboards untouched. Receipt
`receipts/2026-10-08-ibtool-flutter-storyboards.md`.

**66. Newer Flutter plugins name a `FlutterFramework` package next to their
own.** `package_info_plus` 10.2.2 declares `.package(name: "FlutterFramework",
path: "../FlutterFramework")` and links its product. On a Mac, Flutter
generates that package and symlinks every plugin beside it under
`ios/Flutter/ephemeral/Packages/.packages`. `flutter/tools/gen-shell-package.py`
pointed SwiftPM at each plugin inside the pub cache, where no such sibling
exists, and the build stopped with `the package at
'.../package_info_plus-10.2.2/ios/FlutterFramework' cannot be accessed`. It now
copies the plugin packages into `Packages/` in the generated shell and writes a
placeholder `FlutterFramework` package there; the Flutter module itself still
comes from the framework search path. Found when an app gained
`package_info_plus` and `sentry_flutter` (nine native plugins, Sentry linked
statically): it builds, installs and runs on an iPad on iPadOS 27.0, and the
sample with `package_info_plus` added builds in 37 s. Plugins without the
dependency are unaffected.

**67. A multi-size AppIcon appiconset compiled by actool 27.0 wedges App Store
processing; a single-size (1024) one is processed in minutes.** Two TestFlight
uploads of the same no-xcode Flutter app that differ only in the catalog sat
side by side on 2026-10-09: the classic 19-entry appiconset (multi-size car,
dozens of renditions) stayed `PROCESSING` for hours with no error on two app
records, while the single-size catalog (one universal 1024 entry) went
`COMPLETE` and `VALID` in about 2 minutes; swapping only the `Assets.car` into
an otherwise fast xtool build reproduced the hang. Unlike item 35 there is no
error: the upload never finishes. `sdk-free/flutter-build.sh` apps that will be
shipped therefore need a single-size appiconset (the default in current Flutter
templates is multi-size; see `sdk-free/ship.sh` and the 2026-10-09 TestFlight
receipt).
