#!/usr/bin/env python3
"""Symbolicate an iOS .ips crash report on Linux.

usage: ips-symbolicate.py REPORT.ips [--binary PATH]...

Line 1 of the report is a JSON header; the rest is one JSON body. The tool
prints the app, version, OS, incident id, exception, termination, the faulting
thread, and each frame of the faulting thread and of lastExceptionBacktrace.
A frame the device already symbolicated keeps its name. A frame without a
symbol resolves against a --binary whose LC_UUID matches the frame's image
(thin arm64, or any arm64 slice of a fat file), using the nearest preceding
LC_SYMTAB symbol from a section flagged as holding machine instructions.
Swift names stay mangled unless swift-demangle is on PATH, and each distinct
name is demangled once per run. The tool reads the modern JSON .ips form only; the older plain-text
form is rejected. Frames resolve at imageOffset as given, with no
return-address minus 1 adjustment. Pure Python 3 standard library; writes to
stdout (errors to stderr) and nowhere else.
"""
import argparse
import json
import shutil
import struct
import subprocess
import sys

MH_MAGIC_64, FAT_MAGIC = 0xFEEDFACF, 0xCAFEBABE
CPU_ARM64 = 0x0100000C
LC_SYMTAB, LC_SEGMENT_64, LC_UUID = 0x2, 0x19, 0x1B
N_STAB = 0xE0
# The two section flags the Mach-O headers define for "this section holds
# machine instructions". Data and constant sections carry neither, so their
# symbols cannot shadow the nearest function.
EXE_SECTION_FLAGS = 0x80000000 | 0x400  # S_ATTR_PURE_INSTRUCTIONS | S_ATTR_SOME_INSTRUCTIONS


def parse_thin(data):
    """Return (uuid_hex, sorted [(image_offset, name)]) for a thin arm64
    Mach-O, or None when it is not one. A symbol counts only when it has no
    STAB bits and its section flags say the section holds machine
    instructions; N_SECT alone does not mean the symbol is a function."""
    if len(data) < 32 or struct.unpack_from("<I", data, 0)[0] != MH_MAGIC_64:
        return None
    if struct.unpack_from("<I", data, 4)[0] != CPU_ARM64:
        return None
    ncmds = struct.unpack_from("<I", data, 16)[0]
    uuid = symtab = text_vm = None
    sections = []
    off = 32
    for _ in range(ncmds):
        if off + 8 > len(data) or struct.unpack_from("<I", data, off + 4)[0] < 8:
            break
        cmd, size = struct.unpack_from("<II", data, off)
        if cmd == LC_UUID and off + 24 <= len(data):
            uuid = data[off + 8:off + 24].hex()
        elif cmd == LC_SYMTAB and off + 24 <= len(data):
            symtab = struct.unpack_from("<IIII", data, off + 8)
        elif cmd == LC_SEGMENT_64 and off + 72 <= len(data):
            if data[off + 8:off + 24].rstrip(b"\0") == b"__TEXT":
                text_vm = struct.unpack_from("<Q", data, off + 24)[0]
            # nsects sits at +64. +56 is maxprot, which is smaller than
            # nsects on a real dylib, so reading it there drops the last
            # sections and their symbols.
            for s in range(struct.unpack_from("<I", data, off + 64)[0]):
                so = off + 72 + 80 * s
                if so + 80 > len(data):
                    break
                sections.append(struct.unpack_from("<I", data, so + 64)[0])
        off += size
    syms = []
    if uuid and symtab:
        symoff, nsyms, stroff, _strsize = symtab
        for i in range(nsyms):
            if symoff + 16 * (i + 1) > len(data):
                break
            n_strx, n_type, n_sect, _desc, n_value = struct.unpack_from(
                "<IBBHQ", data, symoff + 16 * i)
            if n_type & 0x0E != 0x0E:
                continue
            if n_type & N_STAB or not 1 <= n_sect <= len(sections) \
                    or not sections[n_sect - 1] & EXE_SECTION_FLAGS:
                continue
            start = stroff + n_strx
            if start >= len(data):
                continue
            end = data.find(b"\0", start)
            name = data[start:end if end >= 0 else len(data)].decode("utf-8", "replace")
            if name.startswith("_"):
                name = name[1:]
            syms.append((n_value - (text_vm or 0), name))
        syms.sort()
    if not uuid:
        return None
    return uuid, syms


def parse_binary(path):
    """Return [(uuid_hex, symbols)] for every arm64 slice of a thin or fat
    Mach-O, else []. A fat file may carry arm64 and arm64e; both have
    cputype CPU_ARM64 and differ only in cpusubtype, so each slice's own
    LC_UUID is returned."""
    with open(path, "rb") as f:
        data = f.read()
    found = []
    if len(data) >= 8 and struct.unpack_from(">I", data, 0)[0] == FAT_MAGIC:
        narch = struct.unpack_from(">I", data, 4)[0]
        for i in range(narch):
            entry = 8 + 20 * i
            if entry + 20 > len(data):
                break
            cpu, _sub, aoff, asize, _align = struct.unpack_from(">IIIII", data, entry)
            if cpu == CPU_ARM64 and aoff + asize <= len(data):
                r = parse_thin(data[aoff:aoff + asize])
                if r is not None:
                    found.append(r)
        return found
    r = parse_thin(data)
    return [r] if r is not None else []


_demangle_cache = {}


def demangle(name):
    if "$s" not in name or demangler is None:
        return name
    hit = _demangle_cache.get(name)
    if hit is None:
        r = subprocess.run([demangler], input=name, capture_output=True,
                           text=True, check=False)
        hit = r.stdout.strip() or name
        _demangle_cache[name] = hit
    return hit


def resolve(frame, images, bins):
    """Render one frame as '<image>  <symbol+offset>[ [markers]]'."""
    if not isinstance(frame, dict):
        return "[unreadable frame]"
    idx = frame.get("imageIndex")
    img = images[idx] if isinstance(idx, int) and 0 <= idx < len(images) and \
        isinstance(images[idx], dict) else None
    name = img.get("name", "?") if img else "?"
    sym = frame.get("symbol")
    if sym is not None:
        loc = frame.get("symbolLocation")
        return f"{name}  {sym}+{loc if loc is not None else '?'}"
    if img is None:
        return f"{name}  ?"
    off = frame.get("imageOffset")
    if not isinstance(off, int):
        return f"{name}  [unreadable imageOffset]"
    want = norm_uuid(img.get("uuid", ""))
    b = bins.get(want)
    if b is None:
        return f"{name}  [no local binary for {name} {img.get('uuid', '?')}]"
    best = None
    for val, sym_name in b:
        if val <= off:
            best = (val, sym_name)
        else:
            break
    if best is None:
        return f"{name}  {off:#x} [no local symbol]"
    return f"{name}  {demangle(best[1])}+{off - best[0]:#x} [resolved locally]"


def norm_uuid(u):
    return str(u).replace("-", "").lower()


def main():
    global demangler
    ap = argparse.ArgumentParser(
        description="Symbolicate an iOS .ips crash report against local Mach-O files.",
        epilog="Reads the modern JSON .ips form only; the older plain-text form "
               "is rejected. Frames resolve at imageOffset as given, with no "
               "return-address minus 1 adjustment.")
    ap.add_argument("report", help="path to the .ips report")
    ap.add_argument("--binary", action="append", default=[], metavar="PATH",
                    help="local Mach-O to resolve frames against; repeatable")
    args = ap.parse_args()
    try:
        with open(args.report, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        sys.exit(f"error: cannot read {args.report}: {e.strerror or e}")
    first, _sep, rest = text.partition("\n")
    try:
        hdr = json.loads(first)
    except (ValueError, RecursionError):
        sys.exit(f"error: {args.report}: line 1 is not JSON; not a valid .ips report")
    try:
        body = json.loads(rest)
    except (ValueError, RecursionError):
        sys.exit(f"error: {args.report}: the report body after line 1 is not "
                 "valid JSON (report truncated or corrupt)")

    print(f"App: {hdr.get('app_name', '?')} {hdr.get('app_version', '?')}"
          f" ({hdr.get('bundleID', '?')})")
    print(f"OS: {hdr.get('os_version', '?')}")
    if hdr.get("incident_id"):
        print(f"Incident: {hdr['incident_id']}")
    exc = body.get("exception") or {}
    if exc:
        parts = [str(exc.get("type", "?"))]
        if exc.get("signal"):
            parts.append(f"({exc['signal']})")
        if exc.get("subtype"):
            parts.append(str(exc["subtype"]))
        print("Exception: " + " ".join(parts))
    term = body.get("termination") or {}
    if term:
        line = " ".join(str(term[k]) for k in ("namespace", "code") if term.get(k))
        if term.get("indicator"):
            line += f" ({term['indicator']})"
        print("Termination: " + (line or "?"))

    demangler = shutil.which("swift-demangle")
    bins = {}
    for path in args.binary:
        try:
            results = parse_binary(path)
        except OSError as e:
            sys.exit(f"error: cannot read {path}: {e.strerror or e}")
        if not results:
            print(f"warning: {path}: no arm64 Mach-O slice with LC_UUID, ignored",
                  file=sys.stderr)
            continue
        for uuid, syms in results:
            if uuid in bins:
                print(f"warning: {path}: LC_UUID {uuid} already covered by an "
                      "earlier --binary, keeping that one", file=sys.stderr)
                continue
            bins[uuid] = syms

    images = [im for im in body.get("usedImages") or [] if isinstance(im, dict)]
    threads = body.get("threads") or []
    ct = body.get("faultingThread")
    if not isinstance(ct, int):
        ct = next((i for i, t in enumerate(threads)
                   if isinstance(t, dict) and t.get("triggered")), None)
    if ct is None:
        print(f"Faulting thread: none of {len(threads)}")
    else:
        print(f"Faulting thread: {ct} of {len(threads)}")
        thread = threads[ct] if isinstance(threads[ct], dict) else {}
        for i, fr in enumerate(thread.get("frames") or []):
            print(f"  {i}  {resolve(fr, images, bins)}")
    last = body.get("lastExceptionBacktrace")
    if last:
        print("Last exception backtrace:")
        for i, fr in enumerate(last):
            print(f"  {i}  {resolve(fr, images, bins)}")


demangler = None
if __name__ == "__main__":
    main()
