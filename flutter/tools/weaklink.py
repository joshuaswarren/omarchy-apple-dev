#!/usr/bin/env python3
"""Rewrite LC_LOAD_DYLIB into LC_LOAD_WEAK_DYLIB for named system
frameworks, in place, in every arm64 slice of a Mach-O.

Why: Swift autolinking emits a STRONG load command for every framework a
SwiftPM dependency imports. When the framework was introduced after the
app's deployment target (SwiftUICore, iOS 18, dragged in by Sentry 9.x's
SwiftUI import), dyld then aborts the app at launch on every older iOS.
Xcode emits a weak link in this situation; the cross linker cannot be
asked to — neither autolink nor an explicit -weak_framework survives its
allowed-clients tbd check ("cannot link directly ... not an allowed
client") — so the load command is fixed after the link instead. For dyld a
weak missing library simply resolves to NULL pointers, exactly what an
Xcode-built app gets. Safe even when symbols are bound against the
framework: the Sentry 9.x link closure binds none (verified against the
chained-fixups imports table of a real Runner), so no strong imports can
dangle from the flipped command.

Usage: weaklink.py <mach-o> <Framework> [<Framework> ...]
Prints one line per rewrite; exit 0 even when nothing matched (the
framework may legitimately be absent), non-zero only on I/O or parse
errors.
"""

import struct
import sys

MH_MAGIC_64 = 0xFEEDFACF
FAT_MAGIC = 0xBEBAFECA  # little-endian view of 0xCAFEBABE
LC_LOAD_DYLIB = 0xC
# LC_REQ_DYLD | 0x18. The bare 0x18 written here before was an invalid
# load command: App Store upload rejected the binary with
# "error 91032: Invalid executable ... contains an invalid load command"
# (ITMS-91032) even though the flip was byte-for-byte the intended shape.
LC_LOAD_WEAK_DYLIB = 0x80000018
CPU_TYPE_ARM64 = 0x0100000C



def slices(data):
    """File offsets of the arm64 Mach-O slices (thin -> one at 0)."""
    magic = struct.unpack_from('<I', data, 0)[0]
    if magic == MH_MAGIC_64:
        return [0]
    if magic == FAT_MAGIC:
        nfat = struct.unpack_from('>I', data, 4)[0]
        out = []
        for i in range(min(nfat, 8)):
            off = 8 + i * 20
            if struct.unpack_from('>I', data, off)[0] == CPU_TYPE_ARM64:
                out.append(struct.unpack_from('>I', data, off + 8)[0])
        return out
    return []


def rewrite(path, frameworks):
    wants = {f'{f}.framework' for f in frameworks}
    with open(path, 'rb+') as fh:
        data = fh.read()
        changed = []
        for base in slices(data):
            ncmds = struct.unpack_from('<I', data, base + 16)[0]
            p = base + 32
            for _ in range(ncmds):
                cmd, cmdsize = struct.unpack_from('<II', data, p)
                if cmd == LC_LOAD_DYLIB:
                    off = struct.unpack_from('<I', data, p + 8)[0]
                    end = data.index(b'\0', p + off)
                    name = data[p + off:end].decode('utf-8', 'replace')
                    parent = name.rsplit('/', 2)[-2] if '/' in name else ''
                    if parent in wants:
                        fh.seek(p)
                        fh.write(struct.pack('<I', LC_LOAD_WEAK_DYLIB))
                        changed.append(name)
                p += cmdsize
    return changed


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    path, frameworks = sys.argv[1], sys.argv[2:]
    try:
        changed = rewrite(path, frameworks)
    except OSError as e:
        print(f'weaklink: {path}: {e}', file=sys.stderr)
        return 1
    for name in changed:
        print(f'weaklink: {path}: {name.rsplit("/", 1)[-1]} LOAD -> WEAK')
    if not changed:
        print(f'weaklink: {path}: nothing to rewrite '
              f'({", ".join(frameworks)} not strongly loaded)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
