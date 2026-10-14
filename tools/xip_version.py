#!/usr/bin/env python3
"""Stream Xcode.app/Contents/version.plist out of an Xcode .xip without unpacking it.

A .xip is a xar archive. Its "Content" member is a pbzx stream (xz chunks) of an odc cpio archive.
The tool walks the cpio headers and keeps at most one decompressed chunk plus the member it reads.

Usage: python3 -I xip_version.py <Xcode.xip> <out.plist>

Exit 0: <out.plist> holds the member bytes; "<CFBundleShortVersionString> <ProductBuildVersion>" is
        printed on stdout.
Exit 3: nothing is written; one line on stderr says why (not a xar, no Content member, not pbzx,
        not odc cpio, truncated stream, no version.plist member, member is not a plist).
Exit 2: wrong arguments.
"""
import lzma
import plistlib
import re
import struct
import sys
import xml.etree.ElementTree as ET
from xml.parsers.expat import ExpatError
import zlib

MEMBER = re.compile(r"^[^/]+\.app/Contents/version\.plist$")
MAX_MEMBER = 1 << 20  # cap on a member read into memory
MAX_NAME = 4096  # cap on a cpio member name
XZ_MAGIC = b"\xfd7zXZ\x00"
ODC_HEADER = 76


def content_range(f):
    """Return (start, length) of the top-level "Content" member in the xar heap."""
    head = f.read(28)
    if len(head) < 28:
        raise ValueError("not a xar archive (file too short)")
    magic, hsize, _version, toc_c, _toc_u, _alg = struct.unpack(">4sHHQQI", head)
    if magic != b"xar!":
        raise ValueError("not a xar archive (bad magic)")
    f.seek(hsize)
    packed = f.read(toc_c)
    if len(packed) < toc_c:
        raise ValueError("truncated xar table of contents")
    try:
        root = ET.fromstring(zlib.decompress(packed))
    except ET.ParseError as e:
        raise ValueError(f"xar table of contents is not XML ({e})") from e
    toc = root.find("toc")
    if toc is not None:
        for entry in toc.findall("file"):
            if entry.findtext("name") == "Content":
                try:
                    offset = int(entry.findtext("data/offset"))
                    length = int(entry.findtext("data/length"))
                except (TypeError, ValueError) as e:
                    raise ValueError("Content member has no usable offset and length") from e
                return hsize + toc_c + offset, length
    raise ValueError("no Content member in the xar archive")


def pbzx_chunks(f, start, length):
    """Yield the decompressed chunks of the pbzx stream at start."""
    f.seek(start)
    if f.read(4) != b"pbzx":
        raise ValueError("Content member is not a pbzx stream")
    if len(f.read(8)) < 8:
        raise ValueError("truncated pbzx header")
    consumed = 12
    while consumed < length:
        head = f.read(16)
        if len(head) < 16:
            raise ValueError("truncated pbzx stream")
        _flags, size = struct.unpack(">QQ", head)
        data = f.read(size)
        if len(data) < size:
            raise ValueError("truncated pbzx stream")
        consumed += 16 + size
        yield lzma.decompress(data) if data[:6] == XZ_MAGIC else data


class Stream:
    """Sequential reader over the chunks. Holds one chunk at a time."""

    def __init__(self, chunks):
        self.chunks = chunks
        self.chunk = b""
        self.pos = 0

    def _fill(self):
        while self.pos >= len(self.chunk):
            try:
                self.chunk = next(self.chunks)
            except StopIteration:
                raise EOFError("truncated cpio stream") from None
            self.pos = 0

    def read(self, n):
        out = []
        while n > 0:
            self._fill()
            piece = self.chunk[self.pos:self.pos + n]
            self.pos += len(piece)
            n -= len(piece)
            out.append(piece)
        return b"".join(out)

    def skip(self, n):
        while n > 0:
            self._fill()
            step = min(n, len(self.chunk) - self.pos)
            self.pos += step
            n -= step


def find_member(stream):
    """Walk the odc cpio entries and return the bytes of the first version.plist member."""
    while True:
        head = stream.read(ODC_HEADER)
        if head[:6] != b"070707":
            raise ValueError("cpio archive is not odc (bad header magic)")
        try:
            namesize = int(head[59:65], 8)
            filesize = int(head[65:76], 8)
        except ValueError as e:
            raise ValueError("cpio header has a bad size field") from e
        if not 0 < namesize <= MAX_NAME:
            raise ValueError("cpio header has a bad name size")
        name = stream.read(namesize)[:-1].decode("utf-8", "replace")
        if name == "TRAILER!!!":
            raise ValueError("no Xcode.app/Contents/version.plist member in the archive")
        if name.startswith("./"):
            name = name[2:]
        if MEMBER.match(name):
            if filesize > MAX_MEMBER:
                raise ValueError("version.plist member is too large")
            return stream.read(filesize)
        stream.skip(filesize)


def read_version(path):
    """Return (plist bytes, version, build) or raise ValueError and friends."""
    with open(path, "rb") as f:
        start, length = content_range(f)
        data = find_member(Stream(pbzx_chunks(f, start, length)))
    try:
        info = plistlib.loads(data)
        version = info["CFBundleShortVersionString"]
        build = info["ProductBuildVersion"]
    except (plistlib.InvalidFileException, ExpatError, ValueError, KeyError, TypeError) as e:
        raise ValueError("version.plist member is not a plist with the Xcode version") from e
    if not isinstance(version, str) or not isinstance(build, str):
        raise ValueError("version.plist member has no usable Xcode version")
    return data, version, build


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: xip_version.py <Xcode.xip> <out.plist>\n")
        return 2
    try:
        data, version, build = read_version(argv[1])
        with open(argv[2], "wb") as out:
            out.write(data)
    except (struct.error, lzma.LZMAError, zlib.error, EOFError, ValueError, OSError) as e:
        sys.stderr.write(f"xip_version.py: {e}\n")
        return 3
    sys.stdout.write(f"{version} {build}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
