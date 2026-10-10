#!/usr/bin/env bash
# Build the machoload pair: the arm64 Linux loader and the iOS Mach-O hello.
#
#   machoload/build.sh [workdir]
#
# Needs: a clang with the aarch64 and arm64 backends (SDKFREE_CLANG), the
# sdk-free sysroot (NOSDK_SYSROOT), and ld64.lld next to that clang.
# Defaults point at the paths used on the build container.
# Verifies the pair by running `loader Hello` under qemu-aarch64-static.
set -euo pipefail
cd "$(dirname "$0")"

CLANG=${SDKFREE_CLANG:-$HOME/scratch/apple-free/tc2/usr/bin/clang}
LLD=${SDKFREE_LLD:-$(dirname "$CLANG")/ld64.lld}
SR=${NOSDK_SYSROOT:-$HOME/scratch/apple-free/iPhoneOS.sdk}
OUT=${1:-$PWD/.build}
QEMU=${QEMU_AARCH64:-qemu-aarch64-static}

mkdir -p "$OUT"

# --- the iOS arm64 Mach-O hello (sdk-free/cc.sh compile, ld64.lld link) ---
"$CLANG" -target arm64-apple-ios17.0 -isysroot "$SR" -nostdinc \
  -isystem "$SR/usr/include" -isystem "$("$CLANG" -print-resource-dir)/include" \
  -fno-builtin -fno-stack-protector -c hello.c -o "$OUT/hello.o"
"$LLD" -arch arm64 -platform_version ios 17.0 26.0 -syslibroot "$SR" \
  -undefined dynamic_lookup -no_fixup_chains -o "$OUT/Hello" "$OUT/hello.o"

# --- the freestanding arm64 Linux loader (direct syscalls, no libc) ---
"$CLANG" -target aarch64-linux-gnu -ffreestanding -fno-builtin \
  -fno-stack-protector -nostdlib -static -O2 loader.c -o "$OUT/loader"

echo "built: $OUT/loader, $OUT/Hello"

# --- check: run the pair where qemu is available ---
if command -v "$QEMU" >/dev/null 2>&1; then
    "$QEMU" "$OUT/loader" "$OUT/Hello"
else
    echo "qemu-aarch64-static not found; stage $OUT for a native aarch64 run"
fi
