# Changelog

## Unreleased

### Xcode version from a .xip

- `install-toolchain.sh` reads `Xcode.app/Contents/version.plist` from the `.xip` stream with
  `tools/xip_version.py` (Python standard library only) and records it next to the cached SDK, so `ship.sh`
  stamps `DTXcode` and `DTXcodeBuild` without `XCODE_VERSION` and `XCODE_BUILD`. A missing member or a
  malformed archive records nothing and keeps the old `XCODE_VERSION`/`XCODE_BUILD` message. Covered by
  `tests/test_xip_version.py`, which builds a synthetic `.xip` in the test.

### Tests

- `tests/run.sh` now runs every `tests/test_*.py` unittest file. Before, CI ran none of them, so
  `tests/test_associated_domains.py` and `tests/test_xcstrings_symbols.py` never ran there.

### Findings

- FINDINGS.md gains an entry on linking a Rust static library into an xtool app. The archive holds C members that duplicate symbols in `libclang_rt.ios.a`, and `ld64.lld` rejects the duplicates. The entry gives an `llvm-ar` and `llvm-nm` filter that deletes a member only when every symbol it defines is also defined in `libclang_rt.ios.a`. Reported by a user, not reproduced here. The filter was checked on scratch archives only.

### Venv repair

- `install-toolchain.sh` creates the pymobiledevice3 venv from the resolved interpreter path, not from a
  `latest` symlink, and both step 4 and `--repair` rebuild the venv when its packages no longer import. The
  rebuild removes only the venv directory after a path guard. Covered by stub tests in
  `tests/install-venv/run.sh`; see `receipts/2026-10-13-venv-resolve.md`.

### Device console

- `device-run.sh --rsd` and `--over-tailnet` take `--console [SECONDS]`. After the install it streams the
  app's own output, reports `running after N s: yes/no` and `fatal text seen: yes/no`, then stops the app.
  A fatal line is a report, not an error of the script. A stream from a running app through `--console`
  is not yet proven on a phone. Covered by stub tests in `tests/device-run-console/run.sh`; see
  `receipts/2026-10-12-device-run-console.md`.

### Crash symbolication

- `tools/ips-symbolicate.py` reads a pulled `.ips` crash report on Linux. It matches local Mach-O files by `LC_UUID` and resolves stripped frames from the symbol table. It prints the exception, the termination reason, and the backtraces of the faulting thread and the last exception. See `docs/CRASH-SYMBOLICATION.md` and `receipts/2026-10-12-ips-symbolicate.md`.
- Review fixes for the same tool: frames resolve only against symbols in sections flagged as holding machine instructions, so a data or STAB entry can no longer shadow the nearest function. A fat file can carry arm64 and arm64e slices, and the report UUID is matched against every slice. `swift-demangle` runs once per distinct symbol instead of once per frame. The section count is read from `nsects`, not from `maxprot`, so the last sections of a real library are not dropped. See `receipts/2026-10-12-ips-symbolicate-review.md`.
- `device-run.sh --rsd` and `--over-tailnet` take `--symbolicate [DIR]`. After the launch step it pulls the phone's crash reports and prints each pulled `.ips` through `tools/ips-symbolicate.py` with the app binary and its frameworks. No report for the app: a note and exit 0. A failed pull is the only error. The live run is not yet proven on a phone. Covered by stub tests in `tests/device-run-symbolicate/run.sh`; see `receipts/2026-10-12-device-run-symbolicate.md`.

## v0.3.0

### Simulation research and simview

- M5 adds scripted vertical scrolling. A scripted drag changes the `ScrollView` content offset in our own SwiftUI-like module. The offset clamps at the content bounds. A drag past eight points cancels the row tap.
- This is our scroll model. It does not match Apple's scroll implementation.
- `receipts/2026-10-11-simview-m5.md` records the measurements. The viewport is 390 by 844 points. The demo content is 1103 points high. The offset clamps at 259 points. A 200 point drag matched its golden image with 0 differing pixels.
- The M5 suite passed 7 test rows and 5 mutation checks. Fling, pinch, rotate, and keyboard input stay outside this milestone.

### Continuous integration

- A GitHub Actions workflow runs `bash tests/run.sh` on ubuntu-latest. It runs on pushes to main and on pull requests. The job gets read-only contents permission and no secrets.
- The runner has a Swift compiler, so the four simview suites run and pass there, about 90 seconds in all. Only `compile-golden.sh` skips, because it needs Apple's ibtool. On a host without a Swift compiler, each simview suite skips with exit 0. See `.github/workflows/tests.yml`.

### Tools and distros

- `device-run.sh` and the Flutter install step look up xtool, pymobiledevice3, and ipsw on `PATH`. The lookup runs only when the pinned path holds no executable file. The pinned path stays first when it is executable.
- The Darwin SDK registration check now matches the exact line `darwin`. A broken SDK bundle makes `swift sdk list` print a warning with the same word. The old substring match could wrongly pass on it. See `install-toolchain.sh`.
- `docs/DISTROS.md` adds a NixOS section. The section reports the flake author's own run. This repository holds no run record for it.

### React Native probe

- The abort listed under v0.2.0 happens with the first ipa's JS bundle (built from an older `App.tsx`) and not with a rebuild from the current `App.tsx`. The mechanism is not proven. The rebuild stayed running for 25 seconds in 5 of 5 phone launches. Nobody checked the screen. See `receipts/2026-10-12-rnprobe-stale-bundle.md`.

## v0.2.0

### Build routes

- The README separates no-Xcode and full-mode needs. No-Xcode needs Linux. It needs an iPhone to run apps and an Apple ID to sign them. Setup needs about 7 GB of temporary disk space.
- A run in an Ubuntu 24.04 container now has setup and build results.

### Device run and over-tailnet

- `device-run.sh --over-tailnet` installs and launches an app over the tailnet without a cable. Screenshot and system log need separate `pymobiledevice3` commands. Pair once over USB first. The phone needs Wi-Fi. Cellular-only access failed.
- One debugger run stopped at the app's `main` breakpoint. It took 220 seconds. Earlier tries did not stop there.

### Simulation research and simview

- M1 ran a small arm64 C program through the Linux loader on an arm64 Linux laptop. This proves the loader and its syscall shims. It does not prove Objective-C or Swift support.
- M2 draws a 390 by 844 frame on Linux. It compares the frame with a saved image. This checks one frame. The saved image is the goal.
- M3 adds scripted touch frames and hit testing. It updates `@State` and draws the frame again. It does not support scrolling, gestures, or windows.
- M4 adds a simulated navigation stack. Scripted actions push and pop screens. The recorded run passed seven test rows and five mutation checks.
- Simview uses our own SwiftUI-like module. It does not match Apple's renderer or navigation behavior. This is not full SwiftUI.
- The four stages add one capability at a time. Each stage has limits. All four run on Linux. None uses a Mac.

### React Native probe

- Seven phone launches with no debugger ended in the same abort. The five crash reports show an abort within one second of launch. The Hermes bundle loaded and ran. See `receipts/2026-10-11-rnprobe-launch.md`.
- React Native reported: "Failed to call into JavaScript module method RCTEventEmitter.receiveEvent(). Module has not been registered as callable." The cause is unknown.
- With a debugger attached from launch, the app was still running after 220 seconds. Nobody checked the screen.

### Documentation

- Added `docs/SIM-INPUT-MODEL.md` for scripted input and `docs/OVER-TAILNET.md` for remote device use. `docs/PHONE-NODE.md` is a parked note.
- Updated `docs/IOS-SIMULATION-LINUX.md` with host needs and M1 through M4 findings. `docs/DISTROS.md` links the Ubuntu run at `receipts/2026-10-09-ubuntu-2404.md`.
- The wider device-side SwiftUI declarations include `Color`, `Font`, `padding`, `List`, `ForEach`, and `NavigationLink`. None ran on a phone. The phone SwiftUI stubs do not export `NavigationStack`.

## v0.1.0

First tagged release of omarchy-apple-dev. It added Linux builds for iOS apps without Xcode. It added a portable toolchain, resource tools, project setup, Flutter support, and macOS builds. The release included app and device-run records. The first tag set a baseline.

Five of five files matched the same Xcode output in each of three metadata tests. Some other parts have device records and no offline test suite.
