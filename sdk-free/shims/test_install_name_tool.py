import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parent / "install_name_tool.py"
MH64, ARM64 = 0xFEEDFACF, 0x0100000C
LC_ID_DYLIB, LC_LOAD_DYLIB, LC_RPATH, LC_SEGMENT_64 = 0xD, 0xC, 0x8000001C, 0x19


def lc(cmd, body):
    size = 8 + len(body)
    size += -size % 8
    return struct.pack("<II", cmd, size) + body.ljust(size - 8, b"\0")


def dylib_cmd(cmd, name):
    return lc(cmd, struct.pack("<4I", 24, 0, 0, 0) + name.encode() + b"\0")


def rpath_cmd(name):
    return lc(LC_RPATH, struct.pack("<I", 12) + name.encode() + b"\0")


def segment_cmd(fileoff):
    body = b"__TEXT".ljust(16, b"\0") + struct.pack("<QQQ", 0, 0, fileoff) + struct.pack("<4I", fileoff, 0, 0, 0)
    return lc(LC_SEGMENT_64, body)


def macho(cmds, pad=0x400):
    body = b"".join(cmds)
    return struct.pack("<8I", MH64, ARM64, 0, 6, len(cmds), len(body), 0, 0) + body


def names_of(data, cmds):
    out = []
    off = 32
    for _ in range(struct.unpack_from("<I", data, 16)[0]):
        cmd, size = struct.unpack_from("<II", data, off)
        if cmd in cmds:
            offname = struct.unpack_from("<I", data, off + 8)[0]
            out.append(data[off + offname:].split(b"\0", 1)[0].decode())
        off += size
    return out


class Shim(unittest.TestCase):
    def run_tool(self, path, *args):
        return subprocess.run([sys.executable, str(TOOL), *args, str(path)],
                              capture_output=True, text=True)

    def fixture(self, tmp, cmds):
        p = Path(tmp) / "lib.dylib"
        p.write_bytes(macho(cmds).ljust(0x400, b"\0"))
        return p

    def test_id_rewrites_the_install_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self.fixture(tmp, [segment_cmd(0x400),
                                   dylib_cmd(LC_ID_DYLIB, "/old/libx.dylib")])
            r = self.run_tool(p, "-id", "/new/libx.dylib")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(names_of(p.read_bytes(), {LC_ID_DYLIB}), ["/new/libx.dylib"])

    def test_change_rewrites_only_the_matching_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self.fixture(tmp, [segment_cmd(0x400),
                                   dylib_cmd(LC_ID_DYLIB, "/id/lib.dylib"),
                                   dylib_cmd(LC_LOAD_DYLIB, "/a/one.dylib"),
                                   dylib_cmd(LC_LOAD_DYLIB, "/a/two.dylib")])
            r = self.run_tool(p, "-change", "/a/one.dylib", "/b/one.dylib")
            self.assertEqual(r.returncode, 0, r.stderr)
            got = names_of(p.read_bytes(), {LC_ID_DYLIB, LC_LOAD_DYLIB})
            self.assertEqual(got, ["/id/lib.dylib", "/b/one.dylib", "/a/two.dylib"])

    def test_add_rpath_appends_a_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self.fixture(tmp, [segment_cmd(0x400), rpath_cmd("/first")])
            r = self.run_tool(p, "-add_rpath", "/second")
            self.assertEqual(r.returncode, 0, r.stderr)
            data = p.read_bytes()
            self.assertEqual(names_of(data, {LC_RPATH}), ["/first", "/second"])
            self.assertEqual(struct.unpack_from("<I", data, 16)[0], 3)

    def test_rpath_rewrites_the_matching_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self.fixture(tmp, [segment_cmd(0x400), rpath_cmd("/old/path"), rpath_cmd("/keep")])
            r = self.run_tool(p, "-rpath", "/old/path", "/new/path")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(names_of(p.read_bytes(), {LC_RPATH}), ["/new/path", "/keep"])

    def test_refusals_leave_the_file_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self.fixture(tmp, [segment_cmd(0x400), dylib_cmd(LC_ID_DYLIB, "/x")])
            before = p.read_bytes()
            for args in (["-frobnicate"], ["-id", "/toolong/" + "x" * 0x400]):
                r = self.run_tool(p, *args)
                self.assertEqual(r.returncode, 1, args)
                self.assertEqual(p.read_bytes(), before, args)
            bad = Path(tmp) / "junk"
            bad.write_bytes(b"not mach-o")
            r = self.run_tool(bad, "-id", "/x")
            self.assertEqual(r.returncode, 1)
            self.assertIn("only thin 64-bit Mach-O", r.stderr)


if __name__ == "__main__":
    unittest.main()
