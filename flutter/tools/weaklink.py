#!/usr/bin/env python3
"""Rewrite LC_LOAD_DYLIB into LC_LOAD_WEAK_DYLIB for named system
frameworks, in place, in every arm64 slice of a Mach-O, and mark every
symbol import bound to them as a weak import.

Why: Swift autolinking emits a STRONG load command for every framework a
SwiftPM dependency imports. When the framework was introduced after the
app's deployment target (SwiftUICore, iOS 18, dragged in by Sentry 9.x's
SwiftUI import), dyld then aborts the app at launch on every older iOS.
Xcode emits a weak link in this situation; the cross linker cannot be
asked to — neither autolink nor an explicit -weak_framework survives its
allowed-clients tbd check ("cannot link directly ... not an allowed
client") — so the load command is fixed after the link instead. For dyld a
weak missing library simply resolves to NULL pointers, exactly what an
Xcode-built app gets.

A weak load command alone does not stop the abort: any symbol still bound
STRONGLY against the weak-linked framework aborts dyld at launch on every
system where the framework is missing. So the chained-fixups imports
table is patched too: every strong import bound to a named framework is
downgraded to a weak import, and the app must not rely on that
framework's functionality on systems where it is absent (there a weak
import resolves to NULL instead of killing the process at launch).
--weak-imports F1,F2,... names frameworks whose imports alone are
downgraded, without touching their load commands.

Usage: weaklink.py <mach-o> [--weak-imports F1,F2,...] [<Framework> ...]
At least one of --weak-imports or a positional Framework is required.
Prints one line per rewrite; exit 0 even when nothing matched (the
framework may legitimately be absent), 2 on bad usage, 1 on I/O or
parse errors (a file that is not a Mach-O with an arm64 slice counts as
a parse error).
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
LC_REEXPORT_DYLIB = 0x8000001F
LC_LOAD_UPWARD_DYLIB = 0x80000023
LC_DYLD_INFO = 0x22
LC_DYLD_INFO_ONLY = 0x80000022
LC_DYLD_CHAINED_FIXUPS = 0x80000034
CPU_TYPE_ARM64 = 0x0100000C
# dyld_chained_fixups imports formats -> entry size in bytes. The header
# carries no packed/alignment attributes, so entries are naturally
# aligned: 4 (dyld_chained_import), 8 (dyld_chained_import_addend) and 16
# (dyld_chained_import_addend64). dyld validates exactly these sizes via
# sizeof() (common/MachOAnalyzer.cpp, validChainedFixupsInfo).
IMPORT_FORMAT_SIZES = {1: 4, 2: 8, 3: 16}
# How to read the first word of an entry of each imports_format — the
# word that carries lib_ordinal and weak_import (struct code, mask over
# the lib_ordinal bits, bit index of weak_import). Layouts come from
# Apple's mach-o/fixup-chains.h: DYLD_CHAINED_IMPORT and
# DYLD_CHAINED_IMPORT_ADDEND share the same first uint32
# (lib_ordinal:8, weak_import:1, name_offset:23; the ADDEND format only
# appends an int32 addend), DYLD_CHAINED_IMPORT_ADDEND64 starts with a
# uint64 (lib_ordinal:16, weak_import:1, reserved:15, name_offset:32)
# followed by a uint64 addend.
IMPORT_WORD = {1: ('<I', 0xFF, 8), 2: ('<I', 0xFF, 8), 3: ('<Q', 0xFFFF, 16)}
# Every load command that occupies a dylib ordinal (1-based, file order):
# an import's ordinal indexes THIS list, never LC_ID_DYLIB. This is
# exactly the command set dyld itself counts as dependent dylibs
# (common/MachOFile.cpp, forEachDependentDylib); LC_LAZY_LOAD_DYLIB is
# deliberately absent — dyld does not count it, so it holds no ordinal.
ORDINAL_DYLIB_CMDS = (LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB,
                      LC_REEXPORT_DYLIB, LC_LOAD_UPWARD_DYLIB)


def signed_ordinal(value, bits):
    """lib_ordinal re-read as a signed integer of its field width.

    dyld does the same cast per format when it walks the imports table
    (common/MachOFile.cpp, forEachChainedFixupTarget: int8_t for the
    8-bit field, int16_t for the 16-bit one). Values <= 0 are the
    special ordinals of mach-o/bind.h — BIND_SPECIAL_DYLIB_SELF (0),
    BIND_SPECIAL_DYLIB_MAIN_EXECUTABLE (-1),
    BIND_SPECIAL_DYLIB_FLAT_LOOKUP (-2), BIND_SPECIAL_DYLIB_WEAK_LOOKUP
    (-3) — and never name an entry of the dylib load command list.
    """
    if value & (1 << (bits - 1)):
        return value - (1 << bits)
    return value


def slices(data):
    """File offsets of the arm64 Mach-O slices (thin -> one at 0).

    Raises ValueError on a fat header that promises more arch entries
    than the file actually holds (truncated fat table)."""
    magic = struct.unpack_from('<I', data, 0)[0]
    if magic == MH_MAGIC_64:
        return [0]
    if magic == FAT_MAGIC:
        nfat = struct.unpack_from('>I', data, 4)[0]
        if len(data) < 8 + 20 * nfat:
            raise ValueError(f'fat header declares {nfat} arches, '
                             'file too short for its arch table')
        out = []
        for i in range(nfat):
            off = 8 + i * 20
            if struct.unpack_from('>I', data, off)[0] == CPU_TYPE_ARM64:
                out.append(struct.unpack_from('>I', data, off + 8)[0])
        return out
    return []


def dylib_name(data, addr):
    """The dylib path of the LC_*_DYLIB command at addr."""
    off = struct.unpack_from('<I', data, addr + 8)[0]
    end = data.index(b'\0', addr + off)
    return data[addr + off:end].decode('utf-8', 'replace')


def framework_of(path):
    """The <X>.framework directory the dylib path points into."""
    return path.rsplit('/', 2)[-2] if '/' in path else ''


class SliceImports:
    """What one slice's load commands say about libraries and fixups."""

    def __init__(self):
        self.flips = []      # (cmd-field offset, dylib path) to turn weak
        self.dylibs = []     # framework dirs in ordinal order (dylibs[0] = ordinal 1)
        self.chained = None  # (dataoff, datasize) of LC_DYLD_CHAINED_FIXUPS
        self.classic_binds = False  # dyld_info with a non-zero bind table


def parse_slice(data, base, wants):
    info = SliceImports()
    ncmds = struct.unpack_from('<I', data, base + 16)[0]
    p = base + 32
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from('<II', data, p)
        if cmd == LC_LOAD_DYLIB:
            name = dylib_name(data, p)
            info.dylibs.append(framework_of(name))
            if framework_of(name) in wants:
                info.flips.append((p, name))
        elif cmd in ORDINAL_DYLIB_CMDS:
            info.dylibs.append(framework_of(dylib_name(data, p)))
        elif cmd == LC_DYLD_CHAINED_FIXUPS:
            info.chained = struct.unpack_from('<II', data, p + 8)
        elif cmd in (LC_DYLD_INFO, LC_DYLD_INFO_ONLY):
            # dyld_info_command: its bind_size, weak_bind_size and
            # lazy_bind_size are the 6th, 8th and 10th uint32. Any
            # non-zero bind table means the slice binds with classic
            # opcodes.
            bind, weak, lazy = (struct.unpack_from('<I', data, p + 20)[0],
                                struct.unpack_from('<I', data, p + 28)[0],
                                struct.unpack_from('<I', data, p + 36)[0])
            if bind or weak or lazy:
                info.classic_binds = True
        p += cmdsize
    return info


def import_writes(data, base, slice_end, info, wants):
    """Weak-import bit writes for one slice, as (address, format, value).

    Returns (writes, {framework dir: imports downgraded}). Raises
    ValueError on anything unsafe to patch: every check runs before any
    write is made, so a raise leaves the file untouched.
    """
    if info.chained is None:
        if info.classic_binds:
            raise ValueError('classic dyld bind opcodes are not supported, '
                             'refusing to leave imports into weak-linked '
                             'frameworks unchecked')
        return [], {}  # neither fixups nor binds: no imports exist here
    blob_start = base + info.chained[0]
    blob_end = blob_start + info.chained[1]
    if blob_start < base or blob_end > slice_end:
        raise ValueError('LC_DYLD_CHAINED_FIXUPS blob lies outside the slice')
    (fixups_version, _starts_offset, imports_offset, _symbols_offset,
     imports_count, imports_format, _symbols_format) = \
        struct.unpack_from('<7I', data, blob_start)
    if fixups_version not in (0, 1):
        raise ValueError(f'unsupported chained fixups version {fixups_version}')
    entry_size = IMPORT_FORMAT_SIZES.get(imports_format)
    if entry_size is None:
        raise ValueError(f'unsupported chained fixups imports format {imports_format}')
    table_start = blob_start + imports_offset
    table_end = table_start + imports_count * entry_size
    if table_end > blob_end:
        raise ValueError('chained fixups imports table lies outside the '
                         'fixups blob')
    writes = []
    counts = {}
    code, ordinal_mask, weak_shift = IMPORT_WORD[imports_format]
    ordinal_bits = 16 if imports_format == 3 else 8
    for i in range(imports_count):
        at = table_start + i * entry_size
        (word,) = struct.unpack_from(code, data, at)
        if word & (1 << weak_shift):
            continue  # already weak
        ordinal = signed_ordinal(word & ordinal_mask, ordinal_bits)
        if ordinal <= 0:
            # Special ordinal (self, main executable, flat lookup, weak
            # lookup): bound to no entry of the dylib list.
            continue
        if ordinal > len(info.dylibs):
            raise ValueError(f'chained fixups import {i}: dylib ordinal '
                             f'{ordinal} is outside the slice\'s dylib list '
                             f'of {len(info.dylibs)}')
        framework = info.dylibs[ordinal - 1]
        if framework in wants:
            writes.append((at, code, word | (1 << weak_shift)))
            counts[framework] = counts.get(framework, 0) + 1
    return writes, counts


def rewrite(path, frameworks, weak_imports):
    """Returns (flipped dylib paths, {framework name: imports downgraded})."""
    wants_load = {f'{f}.framework' for f in frameworks}
    wants_imports = wants_load | {f'{f}.framework' for f in weak_imports}
    with open(path, 'rb+') as fh:
        data = fh.read()
        flips = []
        writes = []
        tallies = {}
        offsets = slices(data)
        if not offsets:
            raise ValueError('no arm64 Mach-O slice found')
        for i, base in enumerate(offsets):
            # A slice ends where the next one starts (or at end of file).
            slice_end = offsets[i + 1] if i + 1 < len(offsets) else len(data)
            info = parse_slice(data, base, wants_load)
            flips += info.flips
            slice_writes, counts = import_writes(data, base, slice_end,
                                                 info, wants_imports)
            writes += slice_writes
            for framework, n in counts.items():
                tallies[framework] = tallies.get(framework, 0) + n
        # Every slice parsed cleanly — only now touch the file.
        for offset, _ in flips:
            fh.seek(offset)
            fh.write(struct.pack('<I', LC_LOAD_WEAK_DYLIB))
        for addr, code, value in writes:
            fh.seek(addr)
            fh.write(struct.pack(code, value))
    names = [name for _, name in flips]
    report = {framework[:-len('.framework')]: n for framework, n in tallies.items()}
    return names, report


def split_frameworks(value):
    return [f.strip() for f in value.split(',') if f.strip()]


def main():
    args = sys.argv[1:]
    weak_imports = []
    rest = []
    while args:
        arg = args.pop(0)
        if arg == '--weak-imports':
            if not args:
                print(__doc__)
                return 2
            weak_imports += split_frameworks(args.pop(0))
        elif arg.startswith('--weak-imports='):
            weak_imports += split_frameworks(arg.split('=', 1)[1])
        else:
            rest.append(arg)
    if not rest or (len(rest) == 1 and not weak_imports):
        print(__doc__)
        return 2
    path, frameworks = rest[0], rest[1:]
    try:
        changed, counts = rewrite(path, frameworks, weak_imports)
    except (OSError, ValueError, struct.error) as e:
        print(f'weaklink: {path}: {e}', file=sys.stderr)
        return 1
    for name in changed:
        print(f'weaklink: {path}: {name.rsplit("/", 1)[-1]} LOAD -> WEAK')
    for framework in dict.fromkeys(list(frameworks) + weak_imports):
        n = counts.get(framework, 0)
        if n:
            plural = 's' if n != 1 else ''
            print(f'weaklink: {path}: {framework}: {n} strong '
                  f'import{plural} -> weak')
    if not changed and not counts:
        named = ', '.join(dict.fromkeys(frameworks + weak_imports))
        print(f'weaklink: {path}: nothing to rewrite ({named})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
