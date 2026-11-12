"""tools/asc.py frameworks(): a static framework copied into Frameworks/ is removed before signing.
The functions under test are taken from asc.py with ast and run offline on synthetic binaries.

Rows (expected results written before the code):
  1  Frameworks/A.framework/A is a thin ar archive: removed
  2  Frameworks/B.framework/B is a fat file of two ar slices: removed
  3  Frameworks/C.framework/C is a thin 64-bit Mach-O: kept
  4  Frameworks/D.framework/D is a fat file of one ar slice and one Mach-O slice: kept
  5  a 64-bit fat header (cafebabf) of two ar slices: removed
  6  a fat header truncated to 6 bytes: refused with a message naming the file
Mutants (each must fail its row; checked by hand when the test was written):
  M1  is_static_archive returns True for every file -> rows 3, 4
  M2  any() instead of all() over the slices -> row 4
  M3  drop the truncation check -> row 6 (bare struct.error)
"""
import ast
import io
import os
import plistlib
import re
import shutil
import struct
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

NAMES = {"frameworks", "is_static_archive", "rename_dylibs"}

AR = b"!<arch>\n" + b"\0" * 56
MACHO = b"\xcf\xfa\xed\xfe" + b"\0" * 60


def namespace():
    source = (Path(__file__).resolve().parents[1] / "tools/asc.py").read_text()
    tree = ast.parse(source)
    keep = [n for n in tree.body
            if (isinstance(n, ast.FunctionDef) and n.name in NAMES)
            or (isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "FRAMEWORK_INFO_KEYS" for t in n.targets))]
    tree.body = keep
    if {n.name for n in keep if isinstance(n, ast.FunctionDef)} != NAMES:
        raise AssertionError("asc.py must contain the functions under test")
    ns = dict(os=os, re=re, Path=Path, plistlib=plistlib, shutil=shutil, struct=struct)

    def die(message):
        raise SystemExit(message)
    ns["die"] = die
    exec(compile(tree, "asc-static-frameworks.py", "exec"), ns)
    return ns


def fat(slices, fat64=False):
    """A fat file whose slices start on 64-byte boundaries after the header."""
    entry = 32 if fat64 else 20
    header = (b"\xca\xfe\xba\xbf" if fat64 else b"\xca\xfe\xba\xbe") + struct.pack(">I", len(slices))
    offset = (len(header) + entry * len(slices) + 63) // 64 * 64
    entries, body = b"", b""
    for i, data in enumerate(slices):
        start = offset + len(body)
        if fat64:
            entries += struct.pack(">iiQQII", 0, 0, start, len(data), 6, 0)
        else:
            entries += struct.pack(">iiIII", 0, 0, start, len(data), 6)
        body += data.ljust(64, b"\0")
    return (header + entries).ljust(offset, b"\0") + body


class StaticFrameworks(unittest.TestCase):
    def setUp(self):
        self.ns = namespace()
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.app = self.tmp / "App.app"
        (self.app / "Frameworks").mkdir(parents=True)
        with (self.app / "Info.plist").open("wb") as f:
            plistlib.dump({"CFBundleIdentifier": "com.example.app"}, f)

    def framework(self, name, binary):
        directory = self.app / "Frameworks" / f"{name}.framework"
        (directory / "Resources").mkdir(parents=True)
        (directory / name).write_bytes(binary)
        return directory

    def run_frameworks(self):
        with redirect_stdout(io.StringIO()):
            self.ns["frameworks"](self.app)

    def test_rows_1_to_5_only_all_ar_binaries_are_removed(self):
        removed = [self.framework("A", AR), self.framework("B", fat([AR, AR])),
                   self.framework("E", fat([AR, AR], fat64=True))]
        kept = [self.framework("C", MACHO), self.framework("D", fat([AR, MACHO]))]
        self.run_frameworks()
        for directory in removed:
            self.assertFalse(directory.exists(), directory.name)
        for directory in kept:
            self.assertTrue((directory / directory.stem).is_file(), directory.name)

    def test_row_6_truncated_fat_header_names_the_file(self):
        self.framework("T", b"\xca\xfe\xba\xbe\0\0")
        with self.assertRaises(SystemExit) as raised:
            self.run_frameworks()
        self.assertIn("T.framework/T", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
