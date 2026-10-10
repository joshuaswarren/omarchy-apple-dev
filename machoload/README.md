# Mach-O loader for Linux (machoload)

Runs an iOS arm64 executable built by this repo's no-xcode toolchain on Linux
aarch64. `loader Hello` maps the Mach-O at its link-time addresses and calls
its entry point, binding every external symbol by name against Linux
implementations: direct syscalls (`write`, `exit`, `getpid`,
`clock_gettime`) and small `memcpy`/`memmove`/`memset`/`puts` helpers. The
loader is freestanding C (no libc) and the same binary runs natively on
aarch64 Linux and under `qemu-aarch64-static` anywhere.

## What works

- C executables compiled with `sdk-free/cc.sh` and linked with `ld64.lld`
  (`-undefined dynamic_lookup -no_fixup_chains`).
- Lazy stub binding by symbol name: the loader walks the `LC_DYLD_INFO_ONLY`
  bind and lazy-bind opcode streams and fills the `__got` and
  `__la_symbol_ptr` slots before the entry point runs.
- Provided symbols: `puts`, `write`, `exit`, `getpid`, `clock_gettime`,
  `memcpy`, `memmove`, `memset`, `abort`, `__stack_chk_guard`,
  `__stack_chk_fail`; `dyld_stub_binder` is bound to a trap that never fires
  when lazy binds are processed at load time. An unresolved symbol stops the
  load with its name on stderr.
- A C hello (`hello.c`) that exercises five of the bound symbols and prints
  `Hello from an iOS Mach-O on Linux`.

## What it gives up (for now)

- No rebase processing: segments are mapped at their preferred vmaddr, so
  there is no slide and file pointers already hold their final values.
- No chained fixups: link with `-no_fixup_chains`; chained-fixup binaries
  are rejected with a message. Fat binaries are rejected too.
- No Objective-C or Swift runtime: an objc4 or Swift core port is the
  prerequisite for anything beyond C.
- No TLS, no unwinding, no debugger support.

## Files

| Path | What it is |
|---|---|
| `loader.c` | the loader: freestanding arm64 Linux C, direct syscalls |
| `hello.c` | the C hello; every call stays an undefined symbol in the binary |
| `build.sh` | builds the pair and checks it under `qemu-aarch64-static` |

## Build and run

```sh
machoload/build.sh              # SDKFREE_CLANG, NOSDK_SYSROOT, SDKFREE_LLD env override the default paths
qemu-aarch64-static machoload/.build/loader machoload/.build/Hello
Hello from an iOS Mach-O on Linux
```

Status: proven under `qemu-aarch64-static`; the same pair is staged for a
native aarch64 run (receipts/2026-10-10-machoload-m1.md).
