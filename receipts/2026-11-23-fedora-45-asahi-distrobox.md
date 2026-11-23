# Fedora 45 (aarch64, Asahi): full install in a distrobox, 2026-11-23

`install-toolchain.sh --mode full` at `4b5b9f5` ran to `Done.` inside a
Fedora 45 distrobox on an Apple Silicon Mac running Fedora Linux Asahi Remix
45. Nothing was installed on the host with dnf. Two Fedora 45 problems had to
be fixed first; both are quoted below. Guide: `docs/DISTROS.md`, *Fedora 45*.

## Machine and versions

| | |
|---|---|
| Host | Fedora Linux Asahi Remix 45, kernel `7.3.4-401.asahi.fc45.aarch64+16k`, page size 16384 |
| Container | distrobox 1.8.2.5, podman 6.2.0, `registry.fedoraproject.org/fedora-toolbox:45` |
| Swift | swift.org UBI 9 build installed with mise: 6.4.1 for steps 1-4, 6.4.2 for the SDK step |
| Xcode | `Xcode_27.2.xip`, recorded as `27.2 27B52` |
| xtool | `7cc56c391a67652e86d164eddbbd62065a26599f` (the installer's pin) |
| binutils | `binutils-2.47-1.fc45` |
| lld | `lld-23.1.5-2.fc45` |
| libxml2 | `libxml2-2.15.4-1.fc45` plus `libxml2_2.13-2.13.9-4.fc45` |
| libimobiledevice | `libimobiledevice-1.4.0-7.fc45` (host and container) |
| Python | 3.15.2; pymobiledevice3 11.63.1 in the venv |

## Failure 1: libxml2.so.2

First run, step 3, before `libxml2_2.13` was installed:

```
WARNING: lldb needs libxml2.so.2; ask an admin for it
== 3. xtool (built from source) and rcodesign (aarch64 and x86_64 releases) ==
Building xtool 7cc56c391a67652e86d164eddbbd62065a26599f (first run: about 7 minutes)
/home/user/.local/share/mise/installs/swift/6.4.1/usr/bin/swift-build: error while loading shared libraries: libxml2.so.2: cannot open shared object file: No such file or directory
```

`dnf provides 'libxml2.so.2()(64bit)'` names `libxml2_2.13-2.13.9-4.fc45`.
After installing it, `ldd liblldb.so` reports nothing missing and
`swift-build --version` prints `Swift Package Manager - Swift 6.4.1`.

## Failure 2: SwiftBuild cannot identify GNU ld 2.47

Second run, the xtool build (the same line once per target, then `error: Build failed`):

```
error: Could not parse output of `/usr/sbin/ld -version_details` as JSON: GNU ld version 2.47.20260726
```

A one-file `swift package init --type executable` package fails the same way
with plain `swift build`, so the problem is not specific to xtool. The patterns
SwiftBuild accepts, from `strings` on the toolchain's `swift-package`:

```
#/LLD (?<version>[\d.]+).*/#
#/GNU ld version (?<version>[\d.]+)-.*/#
#/GNU ld \(GNU Binutils.*\) (?<version>[\d.]+)/#
```

binutils 2.47 prints `GNU ld version 2.47.20260726`, which has no `-` after
the version, so neither GNU pattern matches.

What was tried on the hello package (fresh `.build` each time):

| Attempt | Result |
|---|---|
| `swift build` | fails, error above |
| `swift build --build-system native` | builds (deprecation warning) |
| `swift build -Xswiftc -use-ld=lld` | fails, error above |
| `ld` -> toolchain `ld.lld` first on PATH, with a wrapper that logs every call | fails: the wrapper was never called; SwiftBuild runs `/usr/sbin/ld` |
| `ld` alternative -> `ld.lld`, with a wrapper that logs every call | builds |

The calls logged by that last wrapper, in order:

```
ARGS: -version_details
ARGS: -v
ARGS: -EL --hash-style=gnu --eh-frame-hdr -m aarch64linux -export-dynamic -pie -dynamic-linker /lib/ld-linux-aarch64.so.1 -o ...
```

So `-version_details` fails, `-v` prints `LLD ...`, the LLD pattern matches,
and the real link follows through the same `ld`. With Fedora's own package
(`alternatives --install /usr/bin/ld ld /usr/bin/ld.lld 100`):

```
$ /usr/sbin/ld -v
LLD 23.1.5 (compatible with GNU linkers)
```

The hello package builds and runs (`Hello, world!`). A fresh release build of
`tools/darwin-tools` (`swift build -c release --product actool`) prints
`Build complete! (34.26 secs)`, and `readelf -p .comment` on the binary shows
`Linker: LLD 23.1.5`.

Cached probe: the third run still failed with the GNU ld text after `ld` was
fixed. SwiftBuild had kept the failed result in the build description under
`~/.cache/omarchy-apple-dev/xtool-7cc56c3.../.build/out/Intermediates.noindex/XCBuildData/`.
Deleting `.build/out` (the checkouts stay) let the next run build.

## The completed install

Steps 1-4 (6.4.1), quoted from the run log:

```
== 3. xtool (built from source) and rcodesign (aarch64 and x86_64 releases) ==
xtool commit 7cc56c391a67652e86d164eddbbd62065a26599f
apple-codesign 0.29.0
Version: 3.1.743, BuildCommit: b2c156960c79b0eefe0885dbb32cce7eef77cf2d
== 4. pymobiledevice3 in a venv ==
pymobiledevice3 11.63.1
```

The SDK step (6.4.2, `XCODE_XIP=$HOME/Downloads/Xcode_27.2.xip`):

```
== 6. Darwin SDK registration ==
- iPhoneOS27.2.sdk
- iPhoneSimulator27.2.sdk
- MacOSX27.2.sdk
SDK cache kept at: /home/user/.cache/xtool/darwin-iPhoneOS27.2.xtoolsdk
Xcode version recorded: 27.2 27B52
Installing prebuilt SDK...
darwin
Installed actool, xcstringstool, momc and ibtool (version probe; compiles a small xib subset) into /home/user/.config/swiftpm/swift-sdks/darwin.artifactbundle/...
Building OpenAppleMacrosServer cb003a1763b08947dd37376ed8240cbfb4745c32 (first run: about 5 minutes)
== 7. Apple ID sign-in (interactive, needed before device deploys) ==
Run: /home/user/.local/bin/xtool auth
Done. Next: plug in the iPhone and run ./device-run.sh
```

Run on the host, outside the container: `xtool --version`, `rcodesign
--version` and `ipsw version` print the versions above, the venv imports
`pymobiledevice3` and `cryptography` (50.0.2), and `ldd` on the installed xtool
reports nothing missing.

`swift sdk list` prints `darwin` inside the container. On the host it prints
`No Swift SDKs are currently installed.` until `XDG_CONFIG_HOME=$HOME/.config`
is set, because distrobox sets that variable and the host shell does not.

## The iPhone from inside the container

With an iPhone 15 (`iPhone15,4`, iOS 27.2.1) plugged in, the host's `usbmuxd`
is active and `pymobiledevice3 usbmux list` on the host lists the phone. Inside
the container there is no socket:

```
ls: cannot access '/run/usbmuxd': No such file or directory
$ idevice_id -l
ERROR: Unable to retrieve device list!
```

The host socket is at `/run/host/run/usbmuxd`. After
`sudo ln -sfn /run/host/run/usbmuxd /run/usbmuxd` in the container, `idevice_id
-l` prints the UDID, and `pymobiledevice3 lockdown info` shows
`"ProductType": "iPhone15,4"`, `"ProductVersion": "27.2.1"` and
`"TrustedHostAttached": true`. `pymobiledevice3 amfi developer-mode-status`
prints `true`. After `distrobox stop` and a new `distrobox enter`, the link is
still there and `idevice_id -l` still lists the phone.

## Not run

- `xtool auth`, an app build, a device install and LLDB.
