#!/usr/bin/env python3
"""NIBArchive reader, dump and diff: the test harness for a Linux ibtool.

Decodes the iOS binary nib format (magic "NIBArchive") that Apple's ibtool
emits for CocoaTouch storyboards/xibs. Format reference:
  https://github.com/matsmattsson/nibsqueeze/blob/master/NibArchive.md
  https://github.com/tokenbleed/nibkit (internal/nib/archive.go)
Both verified against the golden corpus produced by Xcode 27.0 ibtool.

Usage:
  nibarchive.py dump FILE            print the decoded object graph
  nibarchive.py diff A B             semantic diff; exit 1 when different
  nibarchive.py --self-test          decode every golden nib, check pinned facts
"""

import argparse
import difflib
import glob
import os
import struct
import sys

MAGIC = b"NIBArchive"

# Coder value types (UINibCoderValueType).
INT8, INT16, INT32, INT64 = 0, 1, 2, 3
TRUE, FALSE, FLOAT, DOUBLE, DATA, NIL, OBJREF = 4, 5, 6, 7, 8, 9, 10

STRING_KEYS = ("NS.bytes", "NS.string")  # NSString objects carry text here


class NibError(Exception):
    pass


class _Reader:
    __slots__ = ("buf", "pos")

    def __init__(self, buf, pos=0):
        self.buf = buf
        self.pos = pos

    def _need(self, n):
        if self.pos + n > len(self.buf):
            raise NibError(f"truncated at offset {self.pos} (need {n} bytes)")

    def take(self, n):
        self._need(n)
        out = self.buf[self.pos:self.pos + n]
        self.pos += n
        return out

    def unpack(self, fmt):
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))[0]

    def u8(self):
        return self.take(1)[0]

    def u32(self):
        return self.unpack("<I")

    def vint(self):
        # 7-bit little-endian chunks; high bit set on the terminal byte.
        result = shift = 0
        while True:
            b = self.u8()
            result |= (b & 0x7F) << shift
            shift += 7
            if b & 0x80:
                return result


class Value:
    __slots__ = ("key_idx", "type", "payload")

    def __init__(self, key_idx, vtype, payload):
        self.key_idx = key_idx
        self.type = vtype
        self.payload = payload


class Object:
    __slots__ = ("class_idx", "value_start", "value_count")

    def __init__(self, class_idx, value_start, value_count):
        self.class_idx = class_idx
        self.value_start = value_start
        self.value_count = value_count


class Archive:
    __slots__ = ("version", "minor", "keys", "classes", "objects", "values")

    def __init__(self):
        self.version = self.minor = 0
        self.keys = []     # [bytes] raw key bytes, in table order
        self.classes = []  # [(bytes raw name incl. any NUL, extras tuple)]
        self.objects = []  # [Object]
        self.values = []   # [Value]

    def key(self, idx):
        return self.keys[idx].decode("utf-8")

    def object_values(self, obj):
        return self.values[obj.value_start:obj.value_start + obj.value_count]

    def object_class(self, idx):
        return self.classes[self.objects[idx].class_idx][0].rstrip(b"\x00").decode("utf-8")

    def object_string(self, idx):
        """Text of an NSString object, or None."""
        if self.object_class(idx) not in ("NSString", "NSMutableString"):
            return None
        for v in self.object_values(self.objects[idx]):
            if v.type == DATA and self.key(v.key_idx) in STRING_KEYS:
                return v.payload.rstrip(b"\x00").decode("utf-8")
        return None

    def dump_text(self):
        out = [f"NIBArchive version={self.version} objects={len(self.objects)}"
               f" values={len(self.values)} keys={len(self.keys)}"
               f" classes={len(self.classes)}"]
        for i, obj in enumerate(self.objects):
            out.append(f"[{i}] {self.object_class(i)}")
            for v in self.object_values(obj):
                out.append(f"    {self.key(v.key_idx)} = {self.render(v)}")
        return "\n".join(out)

    def render(self, v):
        t, p = v.type, v.payload
        if t == INT8 or t == INT16 or t == INT32 or t == INT64:
            return f"int {p}"
        if t == TRUE:
            return "bool true"
        if t == FALSE:
            return "bool false"
        if t == FLOAT:
            return f"float {p!r}"
        if t == DOUBLE:
            return f"double {p!r}"
        if t == DATA:
            return f"data[{len(p)}] {p.hex()}"
        if t == NIL:
            return "nil"
        if t == OBJREF:
            idx = p
            if not 0 <= idx < len(self.objects):
                raise NibError(f"object ref out of range: {idx}")
            text = self.object_string(idx)
            cls = self.object_class(idx)
            if text is not None:
                return f'string {text!r} -> [{idx}] {cls}'
            return f"ref -> [{idx}] {cls}"
        raise NibError(f"unknown value type {t}")


def parse(buf):
    if len(buf) < 50 or buf[:10] != MAGIC:
        raise NibError(f"not a NIBArchive ({buf[:10]!r})")
    r = _Reader(buf, 10)
    a = Archive()
    a.version = r.u32()
    a.minor = r.u32()  # observed 9 or 10; meaning unknown, kept for the record
    obj_count, obj_off = r.u32(), r.u32()
    key_count, key_off = r.u32(), r.u32()
    val_count, val_off = r.u32(), r.u32()
    cls_count, cls_off = r.u32(), r.u32()
    # Count guard: every table entry consumes >= 1 byte, so a count larger
    # than the buffer cannot be valid (avoids absurd allocations on bad input).
    if obj_count > len(buf) // 3 or key_count > len(buf) // 2 \
            or val_count > len(buf) // 2 or cls_count > len(buf) // 3:
        raise NibError("table count exceeds file size")

    r.pos = key_off
    for _ in range(key_count):
        a.keys.append(r.take(r.vint()))

    r.pos = cls_off
    for _ in range(cls_count):
        name_len = r.vint()
        extras = tuple(r.u32() for _ in range(r.vint()))
        a.classes.append((r.take(name_len), extras))

    r.pos = obj_off
    for _ in range(obj_count):
        a.objects.append(Object(r.vint(), r.vint(), r.vint()))

    signed = {INT8: "<b", INT16: "<h", INT32: "<i", INT64: "<q"}
    floats = {FLOAT: "<f", DOUBLE: "<d"}
    r.pos = val_off
    for _ in range(val_count):
        key_idx = r.vint()
        vtype = r.u8()
        if vtype in signed:
            payload = r.unpack(signed[vtype])
        elif vtype == TRUE:
            payload = True
        elif vtype == FALSE:
            payload = False
        elif vtype in floats:
            payload = r.unpack(floats[vtype])
        elif vtype == DATA:
            payload = r.take(r.vint())
        elif vtype == NIL:
            payload = None
        elif vtype == OBJREF:
            payload = r.u32()
        else:
            raise NibError(f"unknown value type {vtype}")
        if key_idx >= len(a.keys):
            raise NibError(f"key index out of range: {key_idx}")
        a.values.append(Value(key_idx, vtype, payload))

    for i, obj in enumerate(a.objects):
        if obj.class_idx >= len(a.classes):
            raise NibError(f"object {i}: class index out of range")
        if obj.value_start + obj.value_count > len(a.values):
            raise NibError(f"object {i}: value range out of bounds")
    # Render walk also validates every object ref; do it once up front so
    # dump/diff never die halfway through a graph.
    for obj in a.objects:
        for v in a.object_values(obj):
            if v.type == OBJREF:
                if v.payload >= len(a.objects):
                    raise NibError(f"object ref out of range: {v.payload}")
    return a


def load(path):
    with open(path, "rb") as f:
        return parse(f.read())


def _vint(v):
    if v < 0:
        raise NibError(f"negative varint: {v}")
    out = bytearray()
    while True:
        b = v & 0x7F
        v >>= 7
        if v:
            out.append(b)          # low chunks first, high bit clear
        else:
            out.append(b | 0x80)   # terminal chunk carries the stop bit
            return bytes(out)


def encode(a, trailer=b"LNE\x00"):
    """Serialize an Archive exactly the way Apple's ibtool lays the file out:
    50-byte header, then the objects, keys, values and class-name tables
    packed back to back. Round-trips every corpus nib byte-identically.
    iOS output ends in b'LNE\\x00'; macOS output has no trailer (oracle)."""
    objs = b"".join(_vint(o.class_idx) + _vint(o.value_start) + _vint(o.value_count)
                    for o in a.objects)
    keys = b"".join(_vint(len(k)) + k for k in a.keys)
    signed = {INT8: "<b", INT16: "<h", INT32: "<i", INT64: "<q"}
    floats = {FLOAT: "<f", DOUBLE: "<d"}
    vals = bytearray()
    for v in a.values:
        vals += _vint(v.key_idx)
        vals.append(v.type)
        if v.type in signed:
            vals += struct.pack(signed[v.type], v.payload)
        elif v.type in floats:
            vals += struct.pack(floats[v.type], v.payload)
        elif v.type == DATA:
            vals += _vint(len(v.payload)) + v.payload
        elif v.type == OBJREF:
            vals += struct.pack("<I", v.payload)
        elif v.type not in (TRUE, FALSE, NIL):
            raise NibError(f"unknown value type {v.type}")
    clss = b"".join(
        _vint(len(name)) + _vint(len(extras))
        + b"".join(struct.pack("<I", e) for e in extras) + name
        for name, extras in a.classes)

    off = 50
    obj_off = off; off += len(objs)
    key_off = off; off += len(keys)
    val_off = off; off += len(vals)
    cls_off = off
    header = (MAGIC + struct.pack("<II", a.version, a.minor)
              + struct.pack("<II", len(a.objects), obj_off)
              + struct.pack("<II", len(a.keys), key_off)
              + struct.pack("<II", len(a.values), val_off)
              + struct.pack("<II", len(a.classes), cls_off))
    return header + objs + keys + bytes(vals) + clss + trailer


# ---------------------------------------------------------------- self-test

# Apple ibtool 27.0 output, byte-identical to Xcode 27.0's NetNewsWire.app (tests/ibtool/compile-golden.sh).
GOLDEN_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests", "ibtool", "golden")

# (relative path, pinned facts) — values observed in the Xcode 27.0 corpus.
PINNED = [
    ("Base.lproj/LaunchScreenPhone.storyboardc/2hg-qO-omg-view-wsU-Ys-fCl.nib",
     {"objects": 16, "class0": "NSObject"}),
    ("SettingsTableViewCell.nib", {"objects": 27, "class0": "NSObject"}),
]


def self_test():
    root = GOLDEN_ROOT
    nibs = sorted(glob.glob(os.path.join(root, "**", "*.nib"), recursive=True))
    nibs = [p for p in nibs if os.path.isfile(p)]
    if not nibs:
        raise SystemExit(f"no .nib files under {root}")
    dumps = {}
    failed = []
    for path in nibs:
        try:
            dumps[os.path.relpath(path, root)] = load(path).dump_text()
        except NibError as e:
            failed.append(f"{os.path.relpath(path, root)}: {e}")
    if failed:
        raise SystemExit(f"decode FAILED for {len(failed)}/{len(nibs)}: "
                         + "; ".join(failed))

    checks = [f"decoded {len(nibs)} golden nibs"]
    for rel, facts in PINNED:
        if rel not in dumps:
            failed.append(f"{rel}: missing from corpus")
            continue
        arch = load(os.path.join(root, rel))
        got = {"objects": len(arch.objects), "class0": arch.object_class(0)}
        for kind, want in facts.items():
            if got[kind] != want:
                failed.append(f"{rel}: {kind}={got[kind]!r} want {want!r}")
        checks.append(f"{rel}: objects={got['objects']} class0={got['class0']}")

    # M1: parse -> encode is byte-identical for every golden nib
    rt = 0
    for path in nibs:
        raw = open(path, "rb").read()
        if encode(load(path)) == raw:
            rt += 1
        else:
            failed.append(f"round-trip {os.path.relpath(path, root)}")
    checks.append(f"round-trip {rt}/{len(nibs)}")

    # M1: our xib compiler reproduces Apple's bytes for the tiny targets
    ibtool = _load_ibtool()
    for name in ibtool.SELF_TEST_NIBS:
        src = os.path.join(ibtool.SRC, f"{name}.xib")
        if not os.path.isfile(src):
            src = os.path.join(ibtool.SRC, "NetNewsWire", f"{name}.xib")
        out = ibtool.compile_xib(src)
        if out == open(os.path.join(root, f"{name}.nib"), "rb").read():
            checks.append(f"{name} byte-identical")
        else:
            failed.append(f"{name}.nib: compiled output differs from golden")

    # M2: storyboard compile + link reproduce the golden trees
    import tempfile
    for label, src_rel, golden_rel in ibtool.SB_SELF_TEST:
        tmp = tempfile.mkdtemp(prefix="/tmp/nibarchive-sbtest-")
        dirpart = os.path.dirname(golden_rel)
        top = dirpart.split("/")[0]  # as ibtool's self-test: HelloWorld -> HelloWorld
        module = top if top and not top.endswith(".lproj") else ""
        sbc = ibtool.compile_storyboard(
            os.path.join(ibtool.SRC, src_rel),
            os.path.join(tmp, "stage", dirpart))
        out_root = os.path.join(tmp, "out", module)
        ibtool.link_storyboards(out_root, [sbc])
        mine = ibtool._tree_bytes(out_root)
        cut = len(module) + 1 if module else 0
        stripped = golden_rel[cut:]
        prefix = stripped + "/"
        want = {k[cut:]: v for k, v in ibtool._tree_bytes(root).items()
                if k.startswith((module + "/" if module else "") + prefix)}
        if mine == want:
            checks.append(f"{label} byte-identical")
        else:
            failed.append(f"{label}: tree differs from golden")
    if failed:
        raise SystemExit("self-test FAILED: " + "; ".join(failed))

    # diff behaviour: self-diff empty, cross-diff non-empty
    a = dumps["SettingsTableViewCell.nib"]
    b = next(d for k, d in dumps.items() if k != "SettingsTableViewCell.nib")
    if a == b:
        raise SystemExit("self-test FAILED: distinct nibs dumped identical")
    print("self-test passed (" + "; ".join(checks) + ")")


def _load_ibtool():
    import importlib.machinery
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ibtool")
    loader = importlib.machinery.SourceFileLoader("ibtool_tool", path)
    spec = importlib.util.spec_from_loader("ibtool_tool", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--self-test", action="store_true",
                    help="decode the golden corpus and check pinned facts")
    sub = ap.add_subparsers(dest="cmd")
    p_dump = sub.add_parser("dump", help="print the decoded object graph")
    p_dump.add_argument("file")
    p_diff = sub.add_parser("diff", help="semantic diff of two nibs")
    p_diff.add_argument("a")
    p_diff.add_argument("b")
    args = ap.parse_args(argv)

    if args.self_test:
        self_test()
        return 0
    if args.cmd == "dump":
        print(load(args.file).dump_text())
        return 0
    if args.cmd == "diff":
        ta = load(args.a).dump_text()
        tb = load(args.b).dump_text()
        if ta == tb:
            return 0
        sys.stdout.writelines(difflib.unified_diff(
            ta.splitlines(True), tb.splitlines(True),
            fromfile=args.a, tofile=args.b))
        return 1
    ap.error("command required (or --self-test)")


if __name__ == "__main__":
    sys.exit(main())
