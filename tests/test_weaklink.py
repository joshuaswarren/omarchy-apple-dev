import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "flutter/tools/weaklink.py"


def dylib(name):
    name = f"/System/Library/Frameworks/{name}.framework/{name}".encode() + b"\0"
    size = (24 + len(name) + 7) & ~7
    command = struct.pack("<6I", 0xC, size, 24, 0, 0, 0) + name
    return command + bytes(size - len(command))


def executable(commands, count=None, size=None):
    return struct.pack("<8I", 0xFEEDFACF, 0x0100000C, 0, 2,
                       len(commands) if count is None else count,
                       sum(map(len, commands)) if size is None else size, 0, 0) + b"".join(commands)


class WeaklinkTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.binary = Path(temporary.name) / "Runner"

    def run_cli(self):
        return subprocess.run([sys.executable, str(TOOL), str(self.binary), "SwiftUICore"],
                              capture_output=True, text=True, timeout=5, check=False)

    def test_truncated_later_command_leaves_input_unchanged(self):
        first = dylib("SwiftUICore")
        data = executable([first, b"\0" * 4], count=2, size=len(first) + 8)
        self.binary.write_bytes(data)
        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.binary.read_bytes(), data, "failed parse must not partly rewrite the executable")
        self.assertIn("weaklink:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_valid_rewrite_changes_only_requested_command_and_is_idempotent(self):
        data = executable([dylib("SwiftUICore"), dylib("UIKit")])
        self.binary.write_bytes(data)
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = bytearray(data)
        struct.pack_into("<I", expected, 32, 0x80000018)
        self.assertEqual(self.binary.read_bytes(), bytes(expected))
        self.assertIn("SwiftUICore LOAD -> WEAK", result.stdout)
        again = self.run_cli()
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(self.binary.read_bytes(), bytes(expected))
        self.assertIn("nothing to rewrite", again.stdout)


if __name__ == "__main__":
    unittest.main()
