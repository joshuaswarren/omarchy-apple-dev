import subprocess
import sys
import tempfile
import unittest
import zlib
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import keyorder  # noqa: E402

SIMVIEW = ROOT / "simview"
sys.path.insert(0, str(SIMVIEW))
import compare as simcompare  # noqa: E402


def png(width, height, rows):
    """rows: list of (filter_type, filtered_row_bytes) already filtered."""
    def chunk(ctype, payload):
        return struct.pack(">I", len(payload)) + ctype + payload + \
            struct.pack(">I", zlib.crc32(ctype + payload) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBB", width, height, 8, 6) + b"\x00\x00\x00"
    raw = b"".join(bytes([f]) + r for f, r in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def encode_row(line, prev, ftype):
    """Forward PNG filter (the decoder's inverse)."""
    out = bytearray(len(line))
    for i in range(len(line)):
        a = line[i - 4] if i >= 4 else 0
        b = prev[i]
        c = prev[i - 4] if i >= 4 else 0
        if ftype == 0:
            out[i] = line[i]
        elif ftype == 1:
            out[i] = (line[i] - a) & 0xFF
        elif ftype == 2:
            out[i] = (line[i] - b) & 0xFF
        elif ftype == 3:
            out[i] = (line[i] - (a + b) // 2) & 0xFF
        elif ftype == 4:
            out[i] = (line[i] - simcompare._paeth(a, b, c)) & 0xFF
    return bytes(out)


class CFStrHash(unittest.TestCase):
    def test_empty_and_determinism(self):
        self.assertEqual(keyorder.cf_str_hash(""), 0)
        for s in ("NS.title", "a", "NS.objects", "x" * 96):
            self.assertEqual(keyorder.cf_str_hash(s), keyorder.cf_str_hash(s))
            self.assertGreaterEqual(keyorder.cf_str_hash(s), 0)
            self.assertLess(keyorder.cf_str_hash(s), 1 << 64)

    def test_long_strings_sample_three_windows(self):
        # Past 96 chars only the first/middle/last 32 bytes are hashed:
        # changes in the unsampled spans cannot move the hash.
        base = list("a" * 200)
        mutated = list("a" * 200)
        mutated[50] = "Z"   # between the first (0-31) and middle (84-115) windows
        mutated[140] = "Q"  # between middle and last (168-199) windows
        self.assertEqual(keyorder.cf_str_hash("".join(base)),
                         keyorder.cf_str_hash("".join(mutated)))
        changed_in_window = list("a" * 200)
        changed_in_window[10] = "Z"
        self.assertNotEqual(keyorder.cf_str_hash("".join(base)),
                            keyorder.cf_str_hash("".join(changed_in_window)))


class KeyOrder(unittest.TestCase):
    def test_duplicates_intern_once_and_result_is_the_same_set(self):
        keys = ["a", "b", "a", "c", "b", "d"]
        got = keyorder.key_order(keys)
        self.assertEqual(sorted(got), ["a", "b", "c", "d"])

    def test_growth_keeps_every_key(self):
        keys = [f"k{i}" for i in range(400)]  # grows through several ladder sizes
        got = keyorder.key_order(keys)
        self.assertEqual(sorted(got), sorted(keys))
        self.assertEqual(len(set(got)), 400)


class GoldenGates(unittest.TestCase):
    def test_nibarchive_self_test(self):
        r = subprocess.run(["python3", str(TOOLS / "nibarchive.py"), "--self-test"],
                           capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout[-500:])
        self.assertIn("self-test passed", r.stdout)

    def test_keyorder_check_over_the_golden_corpus(self):
        r = subprocess.run(["python3", str(TOOLS / "keyorder.py"), "--check",
                            str(ROOT / "tests" / "ibtool" / "golden")],
                           capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout[-500:])
        self.assertIn("68/68", r.stdout)


class ReadPNG(unittest.TestCase):
    def test_all_five_filter_types_round_trip(self):
        rows_pixels = [
            bytes(range(16)),                       # filter 0
            b"\x10\x20\x30\x40" * 4,                # filter 1 (sub)
            b"\xff\x00\xff\x00" * 4,                # filter 2 (up)
            bytes([7, 99, 128, 255] * 4),           # filter 3 (avg)
            bytes([i * 17 % 256 for i in range(16)])  # filter 4 (paeth)
        ]
        raw, prev = [], bytearray(16)
        for f, line in enumerate(rows_pixels):
            raw.append((f, encode_row(bytearray(line), prev, f)))
            prev = bytearray(line)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.png"
            p.write_bytes(png(4, 5, raw))
            (w, h), px = simcompare.read_png(str(p))
            self.assertEqual((w, h), (4, 5))
            self.assertEqual(bytes(px), b"".join(rows_pixels))

    def test_non_png_and_bad_format_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.png"
            bad.write_bytes(b"not a png")
            with self.assertRaises(SystemExit):
                simcompare.read_png(str(bad))


class SimviewCLIs(unittest.TestCase):
    def write(self, path, pix, w, h):
        raw = [(0, bytes(pix))]
        Path(path).write_bytes(png(w, h, [(0, bytes(pix[y * w * 4:(y + 1) * w * 4])) for y in range(h)]))

    def test_compare_ok_and_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "a.png"
            b = Path(tmp) / "b.png"
            white = b"\xff" * 16
            self.write(a, white, 2, 2)
            self.write(b, white, 2, 2)
            r = subprocess.run(["python3", str(SIMVIEW / "compare.py"), str(a), str(b)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            dark = bytearray(white)
            dark[0] = 0
            self.write(b, bytes(dark), 2, 2)
            r = subprocess.run(["python3", str(SIMVIEW / "compare.py"), str(a), str(b)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertIn("differing pixels", r.stdout)

    def test_inkbox_reports_the_ink_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "i.png"
            # 8x8 white, with a 2x2 dark block at (3,4)-(4,5)
            pix = bytearray(b"\xff" * 8 * 8 * 4)
            for y, x in ((4, 3), (4, 4), (5, 3), (5, 4)):
                i = (y * 8 + x) * 4
                pix[i:i + 3] = b"\x00\x00\x00"
            self.write(p, bytes(pix), 8, 8)
            r = subprocess.run(["python3", str(SIMVIEW / "inkbox.py"), str(p), "0", "0", "8", "8"],
                               capture_output=True, text=True)
            self.assertEqual(r.stdout.strip(), "3 4 4 5")
            r = subprocess.run(["python3", str(SIMVIEW / "inkbox.py"), str(p), "0", "0", "3", "3"],
                               capture_output=True, text=True)
            self.assertEqual(r.stdout.strip(), "none")


if __name__ == "__main__":
    unittest.main()
