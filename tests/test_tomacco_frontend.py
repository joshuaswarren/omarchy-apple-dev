import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TOOL = Path(__file__).resolve().parents[1] / "tools/tomacco-frontend.py"


class TomaccoFrontendTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.env = {**os.environ, "HOME": str(self.home),
                    "XDG_CONFIG_HOME": str(self.home / "config"),
                    "XDG_DATA_HOME": str(self.home / "data")}

    def module(self):
        spec = importlib.util.spec_from_file_location("tomacco_frontend", TOOL)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def release(self, module):
        root = self.home / 'separate release "with spaces" %f'
        root.mkdir()
        pins = {}
        for name in ("tomacco", "tomaccoctl"):
            data = b"\x7fELF" + name.encode()
            (root / name).write_bytes(data)
            (root / name).chmod(0o755)
            pins[name] = hashlib.sha256(data).hexdigest()
        return root, patch.object(module, "BINARIES", pins)

    def test_unselected_status_has_no_side_effects(self):
        done = subprocess.run([sys.executable, "-I", str(TOOL), "status"],
                              env=self.env, capture_output=True, text=True, check=False)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["enabled"], False)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_enable_disable_preserve_toolkit_and_separate_install(self):
        module = self.module()
        root, pins = self.release(module)
        credentials = self.home / "existing-toolkit-auth"
        credentials.write_text("untouched")
        with patch.dict(os.environ, self.env), pins:
            module.enable(root)
            state, desktop = module.locations()
            saved = json.loads(state.read_text())
            self.assertEqual(saved["release"], module.REVISION)
            entry = desktop.read_text()
            self.assertIn("launch", entry)
            self.assertNotIn("toolkit_install", entry)
            module.enable(root)
            module.disable()
            module.disable()
            self.assertFalse(state.exists())
            self.assertFalse(desktop.exists())
        self.assertEqual(credentials.read_text(), "untouched")
        self.assertTrue((root / "tomacco").is_file())
        self.assertTrue((root / "tomaccoctl").is_file())

    def test_bad_binary_cannot_create_registration(self):
        module = self.module()
        root, pins = self.release(module)
        (root / "tomaccoctl").write_bytes(b"changed")
        with patch.dict(os.environ, self.env), pins:
            with self.assertRaisesRegex(ValueError, "evaluated"):
                module.enable(root)
            state, desktop = module.locations()
            self.assertFalse(state.exists())
            self.assertFalse(desktop.exists())

    def test_existing_desktop_is_not_overwritten(self):
        module = self.module()
        root, pins = self.release(module)
        with patch.dict(os.environ, self.env), pins:
            state, desktop = module.locations()
            desktop.parent.mkdir(parents=True)
            desktop.write_text("user desktop")
            with self.assertRaisesRegex(ValueError, "changed|owned"):
                module.enable(root)
            self.assertEqual(desktop.read_text(), "user desktop")
            self.assertFalse(state.exists())

    def test_disable_preserves_user_modified_registration(self):
        module = self.module()
        root, pins = self.release(module)
        with patch.dict(os.environ, self.env), pins:
            module.enable(root)
            state, desktop = module.locations()
            desktop.write_text("user edit")
            with self.assertRaisesRegex(ValueError, "changed"):
                module.disable()
            self.assertEqual(desktop.read_text(), "user edit")
            self.assertTrue(state.exists())

    def test_launch_rejects_changed_binary_before_execution(self):
        module = self.module()
        root, pins = self.release(module)
        with patch.dict(os.environ, self.env), pins:
            module.enable(root)
            (root / "tomacco").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "evaluated"):
                module.launch()

    def test_symlinked_desktop_is_not_removed(self):
        module = self.module()
        root, pins = self.release(module)
        outside = self.home / "user-file"
        outside.write_text("keep")
        with patch.dict(os.environ, self.env), pins:
            module.enable(root)
            _, desktop = module.locations()
            desktop.unlink()
            desktop.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "changed"):
                module.disable()
            self.assertTrue(desktop.is_symlink())
        self.assertEqual(outside.read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
