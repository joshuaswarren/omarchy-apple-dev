# device-run.sh --lldb: Swift expressions (p, po, expression) on the device, 2026-11-23

Host: Fedora Linux Asahi Remix 45 on Apple Silicon (aarch64, 16K pages); the toolchain and the
scripts ran in a `fedora-toolbox:45` distrobox (`docs/DISTROS.md`, *Fedora 45*). Swift 6.4.2
(swift.org UBI 9 build; LLDB 21.0.0 with Python 3.13), darwin SDK from Xcode 27.2 (27B52),
pymobiledevice3 11.63.1, iPhone 15 (`iPhone15,4`) on iOS 27.2.1 (24B156) over USB. The app is the
`xtool new` template with two locals in `onAppear`:

```swift
.onAppear {
    let greeting = "Hello from Fedora Asahi"
    let launches = 42
    NSLog("HelloOmarchy: %@ (%d)", greeting, launches)   // line 18
```

## Before: the toolchain's lldb

`LLDB_PLAIN=1 device-run.sh --lldb` (the behaviour before this change), breakpoint on line 18:

```
(lldb) v launches
(Int) launches = 42
(lldb) p launches * 2
error: Error while searching for SDK: HostInfoError
error: Error while searching for SDK: HostInfoError
Could not import Swift modules for translation unit: failed to get module "<App>" from AST context:
error: missing required module 'SwiftShims'
```

`frame variable` works; every Swift expression fails. With `settings set target.sdk-path`
pointing at the iPhoneOS SDK added by hand, the error changes to:

```
error: malformed or corrupted precompiled file: 'could not find file
'<toolchain>/usr/lib/swift/CoreFoundation/Modules/module.modulemap' referenced by AST file
'<app>/.build/out/SDKExplicitPrecompiledModules/CoreFoundation-<hash>.pcm'
```

The PCM is the SDK's CoreFoundation framework module. LLDB resolved `CoreFoundation` against
the Linux toolchain's `usr/lib/swift/CoreFoundation` (swift-corelibs-foundation, which has its
own `module.modulemap`) instead. For an iOS target LLDB looks for an Xcode Swift resource dir,
finds none on Linux (`HostInfoError`), and falls back to the host one. On Linux it is
`<dir of liblldb.so>/swift` (`HostInfoPosix::GetSwiftResourceDir`); no setting or environment
variable overrides it.

## After: the shadow toolchain

`tools/lldb-ios-shadow.sh` builds `~/.cache/omarchy-apple-dev/lldb-ios/<hash>/usr` with `lldb`
and `liblldb.so.21.0.0` hard-linked from the toolchain (copied across filesystems), LLDB's Python
package mirrored with `_lldb.so` pointing at that liblldb, and `lib/swift` holding the darwin SDK's
`XcodeDefault.xctoolchain/usr/lib/swift` entries (the `swiftResourcesPath` xtool builds the app
with) plus the toolchain's `linux/` and `host/` (liblldb's RUNPATH). `device-run.sh --lldb` runs
that lldb and adds `settings set target.sdk-path <iPhoneOS.sdk>` (`SwiftShims` is in the SDK's
`usr/lib/swift/shims`). Same app, same breakpoint, plain `device-run.sh --lldb`:

```
(lldb) settings set target.sdk-path "~/.config/swiftpm/swift-sdks/darwin.artifactbundle/Developer/Platforms/iPhoneOS.platform/Developer/SDKs/iPhoneOS.sdk"
...
* thread #1, stop reason = breakpoint 1.1
(lldb) v launches
(Int) launches = 42
(lldb) p launches * 2
error: Error while searching for Xcode SDK: HostInfoError [x3]
(Int) 84
(lldb) po greeting
Hello from Fedora Asahi
(lldb) expression -- greeting.uppercased()
(String) $R0 = "HELLO FROM FEDORA ASAHI"
(lldb) process detach
Process 949 detached
```

The `HostInfoError` line and `could not execute support code to read Objective-C class data`
still print once, before the first result; they do not stop the evaluation. The first
expression of a session took 20-40 s (LLDB loads the iOS modules); later ones returned at
once. In an earlier session through the same tree, `/proc/<pid>/exe` and `/proc/<pid>/maps`
of the running lldb named `~/.cache/omarchy-apple-dev/lldb-ios/<hash>/usr/bin/lldb` and
`.../usr/lib/liblldb.so.21.0.0`. With `LLDB_PLAIN=1` the same check printed the toolchain's
`usr/bin/lldb`.

`po self` inside that `onAppear` closure reports `cannot find 'self' in scope`: the closure
never captures `self`, as Swift reports on a Mac too.

## Copy mode

A hard link fails when the cache and the toolchain are on different filesystems (for example
btrfs subvolumes, or a toolchain under `/usr` with `/home` separate). The script then copies
`lldb` and liblldb. A copy is a different file from the toolchain's liblldb, so LLDB's Python
package (whose `_lldb.so` links `../../../../../lib/liblldb.so`) would map the toolchain's
copy a second time. The script mirrors the package's directories into the shadow and recreates
that relative link there, so it resolves to the shadow liblldb.

`LLDB_IOS_SHADOW_COPY=1 device-run.sh --lldb`, same breakpoint (stamp `copy 1`, shadow liblldb
with link count 1):

```
(lldb) script import os; print("liblldb mapped:", sorted({l.split()[-1] for l in open("/proc/self/maps") if "liblldb" in l}))
liblldb mapped: ['~/.cache/omarchy-apple-dev/lldb-ios/<hash>/usr/lib/liblldb.so.21.0.0']
(lldb) p launches * 2
(Int) 84
(lldb) po greeting
Hello from Fedora Asahi
```

The next plain run rebuilt the tree with hard links (the stamp records the mode). It showed the
same single mapping (link count 2, the toolchain's inode), `p launches * 2` → `84`, and
`expression -- greeting.uppercased()` → `"HELLO FROM FEDORA ASAHI"`. No `.build.*` or `.old.*`
directories were left in the cache.

## Not run

- `--sudo` (the kernel-tunnel path through `debugserver lldb`): unchanged by this change.
- An x86_64 host and Arch's `swift-bin` layout (`/usr/lib/swift/usr`). The script derives the
  toolchain from the `swift` on PATH and needs `bin/lldb` and `lib/liblldb.so.X.Y.Z` there; it
  was not checked that `swift-bin` names liblldb that way. When the script fails,
  `device-run.sh` prints a note and uses the toolchain's lldb as before.
- A cache and toolchain on different filesystems for real. Copy mode was run on the device with
  `LLDB_IOS_SHADOW_COPY=1` instead (section below).
- `tests/lldb-ios-shadow/check.sh` covers the tree layout, reuse, rebuild after a toolchain
  update and the missing-SDK message with stub files.
