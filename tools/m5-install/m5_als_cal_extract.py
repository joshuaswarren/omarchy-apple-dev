#!/usr/bin/env python3
"""Private per-device M5 ALS calibration extractor (offline, metadata-only).

Validates exactly two agreeing macOS ioreg captures and writes the
AppleSPUVD6286 CalibrationData blob raw as apple/aop-als-cal.bin. The
comb3e v2 driver requests that file and sends EPIC property 0x0b; this is
not the separate 80-byte DT firmware-name setup message.
"""
import argparse
import errno
import hashlib
import os
import re
import secrets
import stat
import sys

EXPECTED_MODEL = "Mac17,11"
EXPECTED_NODE = "AppleSPUVD6286"
EXPECTED_LEN = 193
EXPECTED_SHA256 = "6012df8764786c2c75f91a97f59378fb908cda362362feca44403221bd3e6853"

NODE_RE = re.compile(r"^[| ]*\+-o (\S+)\s+<class ([^,>]+),")
KEY_RE = re.compile(r'^[| ]*"([^"]+)"\s*=\s*(.*)$')
BLOB_RE = re.compile(r"^<[0-9a-fA-F]+>$")
MODEL_VAL_RE = re.compile(r'^<"([^"]+)">$')


class CalError(Exception):
    """Refusal/failure; message is metadata only, never payload bytes."""


class Parsed:
    __slots__ = ("payload", "sha256")

    def __init__(self, payload):
        self.payload = payload
        self.sha256 = hashlib.sha256(payload).hexdigest()


def _prop_block(lines, start):
    """Return properties, key line indexes, and closing line for one node."""
    if start + 1 >= len(lines) or "{" not in lines[start + 1]:
        raise CalError("node has no property block")
    col = lines[start + 1].index("{")
    props, keylines = {}, {}
    for i in range(start + 2, len(lines)):
        line = lines[i]
        match = KEY_RE.match(line)
        if match:
            key = match.group(1)
            if key in props:
                raise CalError("duplicate property %s" % key)
            props[key] = match.group(2).strip()
            keylines[key] = i
            continue
        if col < len(line) and line[col] == "}":
            return props, keylines, i
        if NODE_RE.match(line):
            raise CalError("unexpected nested node inside property block")
    raise CalError("unterminated property block")


def _nodes(lines, name=None, cls=None):
    matches = []
    for i, line in enumerate(lines):
        match = NODE_RE.match(line)
        if match and (name is None or match.group(1) == name) \
                and (cls is None or match.group(2) == cls):
            matches.append(i)
    return matches


def _require(props, key, value=None):
    if key not in props:
        raise CalError("missing property %s" % key)
    if value is not None and props[key] != value:
        raise CalError("property %s mismatch" % key)


def _decode_blob(first_val, lines, idx):
    """Assemble a <hex> value with optional tree-prefixed continuations."""
    value = first_val.strip()
    i = idx
    while ">" not in value:
        i += 1
        if i >= len(lines):
            raise CalError("unterminated hex blob")
        value += lines[i].strip().lstrip("| ").rstrip()
    if not BLOB_RE.match(value):
        raise CalError("malformed hex blob")
    hexstr = value[1:-1]
    if len(hexstr) % 2:
        raise CalError("odd hex length")
    try:
        return bytes.fromhex(hexstr)
    except ValueError:
        raise CalError("invalid hex")


def parse_capture_text(text, expected_digest=None):
    """Validate captured identity and payload; digest injection is internal."""
    if expected_digest is None:
        expected_digest = EXPECTED_SHA256
    lines = text.splitlines()
    platforms = _nodes(lines, cls="IOPlatformExpertDevice")
    if len(platforms) != 1:
        raise CalError("expected exactly one IOPlatformExpertDevice, found %d"
                       % len(platforms))
    props, _, _ = _prop_block(lines, platforms[0])
    _require(props, "model")
    model = MODEL_VAL_RE.match(props["model"])
    if model is None:
        raise CalError("capture model property has invalid shape")
    if model.group(1) != EXPECTED_MODEL:
        raise CalError("capture model is not %s" % EXPECTED_MODEL)

    nodes = _nodes(lines, name=EXPECTED_NODE)
    if len(nodes) != 1:
        raise CalError("expected exactly one %s node, found %d"
                       % (EXPECTED_NODE, len(nodes)))
    if NODE_RE.match(lines[nodes[0]]).group(2) != EXPECTED_NODE:
        raise CalError("node class mismatch")
    props, keylines, _ = _prop_block(lines, nodes[0])
    _require(props, "Calibrated", "Yes")
    _require(props, "EXBrightCalibrationSuccess", "Yes")
    _require(props, "CalibrationData")
    payload = _decode_blob(props["CalibrationData"], lines,
                           keylines["CalibrationData"])
    if len(payload) != EXPECTED_LEN:
        raise CalError("calibration length %d != %d" % (len(payload), EXPECTED_LEN))
    parsed = Parsed(payload)
    if parsed.sha256 != expected_digest:
        raise CalError("calibration digest mismatch")
    return parsed


def _read_capture(path, expected_digest):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        raise CalError("cannot read capture %s: %s"
                       % (os.path.basename(path), e.__class__.__name__))
    return parse_capture_text(text, expected_digest)


def extract_from_files(paths, expected_digest=None):
    """Parse exactly two captures and return their shared payload."""
    if expected_digest is None:
        expected_digest = EXPECTED_SHA256
    paths = tuple(paths)
    if len(paths) != 2:
        raise CalError("expected exactly two capture inputs, got %d" % len(paths))
    first_path, second_path = paths
    first = _read_capture(first_path, expected_digest)
    second = _read_capture(second_path, expected_digest)
    if first.payload != second.payload:
        raise CalError("captures disagree")
    return first


def _sha_fd(fd):
    digest, offset = hashlib.sha256(), 0
    while True:
        chunk = os.pread(fd, 65536, offset)
        if not chunk:
            return digest.hexdigest()
        digest.update(chunk)
        offset += len(chunk)


def _existing_or_refuse(dirfd, name, want):
    """Apply the same nofollow/private/hash decision to initial or raced files."""
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=dirfd)
    except OSError as e:
        if e.errno == errno.ELOOP:
            raise CalError("destination is a symlink")
        if e.errno == errno.ENOENT:
            return None
        raise CalError("destination is not a private regular file")
    try:
        current = os.fstat(fd)
        if not stat.S_ISREG(current.st_mode):
            raise CalError("destination is not a private regular file")
        if current.st_mode & 0o077:
            raise CalError("existing calibration file is not private; refusing")
        if _sha_fd(fd) == want:
            return "idempotent"
        raise CalError("existing calibration differs; refusing overwrite")
    finally:
        os.close(fd)


def _open_parent(parent):
    try:
        return os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        raise CalError("output parent must be an existing directory")


def _open_temp(dirfd):
    """Create an exclusive temp and transfer its name+fd before writing."""
    name = ".m5-als-cal." + secrets.token_hex(8)
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=dirfd)
    except FileExistsError:
        raise CalError("temporary name collision; rerun")
    return name, fd


def _verify_created(dirfd, name, want):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                 dir_fd=dirfd)
    try:
        current = os.fstat(fd)
        if not stat.S_ISREG(current.st_mode) or _sha_fd(fd) != want:
            raise CalError("post-write verification failed; inspect destination")
    finally:
        os.close(fd)


def _link_or_existing(dirfd, owned, name, want):
    """Link without overwrite, or decide the concurrent creator's file."""
    try:
        os.link(owned, name, src_dir_fd=dirfd, dst_dir_fd=dirfd)
    except FileExistsError:
        verdict = _existing_or_refuse(dirfd, name, want)
        if verdict is None:
            raise CalError("destination vanished during install; rerun")
        return verdict
    _verify_created(dirfd, name, want)
    return "created"


def install_payload(payload, dest):
    """Atomically create a private file through a validated parent dirfd."""
    dest = os.path.abspath(dest)
    name = os.path.basename(dest)
    if not name:
        raise CalError("invalid destination path")
    want = hashlib.sha256(payload).hexdigest()
    dirfd = _open_parent(os.path.dirname(dest) or ".")
    owned = None
    try:
        parent = os.fstat(dirfd)
        if not stat.S_ISDIR(parent.st_mode) or parent.st_mode & 0o022:
            raise CalError("output parent is missing or group/world writable")
        verdict = _existing_or_refuse(dirfd, name, want)
        if verdict is None:
            owned, fd = _open_temp(dirfd)
            with os.fdopen(fd, "wb") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            return _link_or_existing(dirfd, owned, name, want)
        return verdict
    finally:
        try:
            if owned is not None:
                try:
                    os.unlink(owned, dir_fd=dirfd)
                except FileNotFoundError:
                    pass
            os.fsync(dirfd)
        finally:
            os.close(dirfd)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="m5_als_cal_extract.py",
        description="Validate two agreeing ioreg captures; write metadata-only.")
    parser.add_argument("capture", nargs=2, metavar="CAPTURE")
    parser.add_argument("-o", dest="output", required=True, metavar="OUTPUT")
    args = parser.parse_args(argv)
    try:
        parsed = extract_from_files(args.capture)
        action = install_payload(parsed.payload, args.output)
    except (CalError, OSError) as e:
        print("m5-als-cal-extract: %s" % e, file=sys.stderr)
        return 2
    print("m5-als-cal-extract: model=%s node=%s bytes=%d sha256=%s "
          "output=%s action=%s" % (EXPECTED_MODEL, EXPECTED_NODE,
                                   len(parsed.payload), parsed.sha256,
                                   args.output, action))
    return 0


if __name__ == "__main__":
    sys.exit(main())