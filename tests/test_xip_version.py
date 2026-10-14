import lzma
import plistlib
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tools/xip_version.py"
VERSION = {"CFBundleShortVersionString": "27.0", "ProductBuildVersion": "27A266a"}


def odc(name, data=b"", mode=0o100644):
    raw = name.encode() + b"\0"
    head = (b"070707" + b"%06o" % 0 + b"%06o" % 1 + b"%06o" % mode + b"%06o" % 0 + b"%06o" % 0
            + b"%06o" % 1 + b"%06o" % 0 + b"%011o" % 0 + b"%06o" % len(raw) + b"%011o" % len(data))
    return head + raw + data


def cpio(app="Xcode.app", version=None, with_version=True):
    if version is None:
        version = plistlib.dumps(VERSION)
    parts = [odc("./" + app, mode=0o040755),
             odc(f"./{app}/Contents/Info.plist", b"<plist>not the version</plist>")]
    if with_version:
        parts.append(odc(f"./{app}/Contents/version.plist", version))
    parts.append(odc("TRAILER!!!", mode=0))
    return b"".join(parts)


def pbzx(payload):
    # Two chunks: the first xz-compressed, the second stored raw (size equals uncompressed size).
    half = len(payload) // 2
    first = lzma.compress(payload[:half], format=lzma.FORMAT_XZ)
    second = payload[half:]
    out = b"pbzx" + struct.pack(">Q", len(payload))
    out += struct.pack(">QQ", len(payload[:half]), len(first)) + first
    out += struct.pack(">QQ", len(second), len(second)) + second
    return out


def xar(content, magic=b"xar!"):
    metadata = b"<plist/>"
    toc = ("<?xml version=\"1.0\" encoding=\"UTF-8\"?><xar><toc>"
           f"<file id=\"1\"><name>Metadata</name><data><offset>0</offset><length>{len(metadata)}</length></data></file>"
           f"<file id=\"2\"><name>Content</name><data><offset>{len(metadata)}</offset><length>{len(content)}</length></data></file>"
           "</toc></xar>").encode()
    packed = zlib.compress(toc)
    header = struct.pack(">4sHHQQI", magic, 28, 1, len(packed), len(toc), 1)
    return header + packed + metadata + content


class XipVersionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.out = self.dir / "version.plist"

    def run_tool(self, archive):
        xip = self.dir / "Xcode.xip"
        xip.write_bytes(archive)
        return subprocess.run([sys.executable, "-I", str(TOOL), str(xip), str(self.out)],
                              capture_output=True, text=True)

    def assert_found(self, archive):
        done = self.run_tool(archive)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "27.0 27A266a")
        self.assertEqual(plistlib.loads(self.out.read_bytes()), VERSION)

    def assert_refused(self, archive):
        done = self.run_tool(archive)
        self.assertEqual(done.returncode, 3, done.stdout + done.stderr)
        self.assertFalse(self.out.exists())
        self.assertNotIn("Traceback", done.stderr)
        self.assertEqual(len(done.stderr.strip().splitlines()), 1, done.stderr)

    def test_valid_archive(self):
        self.assert_found(xar(pbzx(cpio())))

    def test_beta_app_name(self):
        self.assert_found(xar(pbzx(cpio(app="Xcode-beta.app"))))

    def test_no_version_member(self):
        self.assert_refused(xar(pbzx(cpio(with_version=False))))

    def test_bad_xar_magic(self):
        self.assert_refused(xar(pbzx(cpio()), magic=b"nope"))

    def test_truncated_pbzx(self):
        archive = xar(pbzx(cpio()))
        self.assert_refused(archive[:-40])

    def test_member_is_not_a_plist(self):
        self.assert_refused(xar(pbzx(cpio(version=b"this is not a plist"))))


if __name__ == "__main__":
    unittest.main()
