# M1: an arm64 Mach-O hello runs on Linux through our loader

2026-10-10. `machoload/` on branch `machoload-m1`: a freestanding arm64
Linux loader for iOS Mach-O executables built by the no-xcode toolchain.

## What ran

On the build container (Linux x64), under `qemu-aarch64-static`:

```sh
qemu-aarch64-static machoload/.build/loader machoload/.build/Hello
Hello from an iOS Mach-O on Linux
exit 0
```

The pair: `machoload/.build/loader` (ELF 64-bit ARM aarch64, statically
linked) and `machoload/.build/Hello` (Mach-O 64-bit arm64, MH_EXECUTE,
platform iOS 17.0, linked with `ld64.lld -undefined dynamic_lookup
-no_fixup_chains`). The hello calls `puts`, `getpid`, `clock_gettime`,
`memcpy`, `memset`; all five are undefined in the binary and the loader
binds each by name before the entry runs (an unresolved name stops the
load with the name on stderr, and the hello self-checks the resolved
results before printing).

## How the loader works

- Maps each `LC_SEGMENT_64` at its link-time vmaddr, copies the file
  bytes, and restores initprot after binding. No slide, so no rebases.
- Interprets the classic dyld bind and lazy-bind opcode streams
  (`llvm/BinaryFormat/MachO.h` opcode table) and writes resolved Linux
  addresses into `__got` and `__la_symbol_ptr` slots; stubs then work
  untouched.
- Entry from `LC_MAIN` (`__TEXT` vmaddr + entryoff), called with
  argc/argv/envp from the Linux initial stack.

## Native aarch64 run

The same two files are staged at
`~/scratch/apple-dev/machoload-m1/run/` (loader, Hello, RUN.md) for a
native aarch64 Linux run on a GUARD ticket. No Mac or device needed.

## Not in this step

Objective-C and Swift: they need an objc4 / Swift core port before any
loader work pays off, so the loader proves C first (machoload/README.md
lists the limits: no rebases needed, no chained fixups, no TLS).
