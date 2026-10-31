import os
import subprocess
import sys
import unittest
from pathlib import Path

import test_tomacco_frontend as lifecycle

TOOL = Path(__file__).resolve().parents[1] / "tools/tomacco-frontend.py"


class AtomicRegistrationTest(unittest.TestCase):
    def test_kernel_write_limit_preserves_existing_registration(self):
        fixture = lifecycle.TomaccoFrontendTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        module = fixture.module()
        root, pins = fixture.release(module)
        from unittest.mock import patch
        with patch.dict(os.environ, fixture.env), pins:
            module.enable(root)
            state, desktop = module.locations()
            before = (state.read_bytes(), desktop.read_bytes())
        code = '''
import hashlib, importlib.util, os, resource, signal, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("frontend", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
root = Path(sys.argv[2])
m.BINARIES = {n: hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ("tomacco", "tomaccoctl")}
signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
resource.setrlimit(resource.RLIMIT_FSIZE, (128, 128))
m.enable(root)
'''
        done = subprocess.run([sys.executable, "-I", "-c", code, str(TOOL), str(root)],
                              env=fixture.env, capture_output=True, text=True, check=False)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("File too large", done.stderr)
        self.assertEqual(state.read_bytes(), before[0], "partial write destroyed the prior registration")
        self.assertEqual(desktop.read_bytes(), before[1])
        with patch.dict(os.environ, fixture.env), pins:
            module.enable(root)
            module.disable()
            self.assertFalse(state.exists())
            self.assertFalse(desktop.exists())

    def test_desktop_publication_failure_is_retryable(self):
        import errno
        from unittest.mock import patch
        fixture = lifecycle.TomaccoFrontendTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        module = fixture.module()
        root, pins = fixture.release(module)
        moved = fixture.home / "moved-checkout/tomacco-frontend.py"
        moved.parent.mkdir()
        moved.write_bytes(TOOL.read_bytes())
        with patch.dict(os.environ, fixture.env), pins:
            module.enable(root)
            state, desktop = module.locations()
            before = desktop.read_bytes()
            replace = os.replace
            published_modes = []

            def disk_full(source, target):
                published_modes.append((Path(target), Path(source).stat().st_mode & 0o777))
                if Path(target) == desktop:
                    raise OSError(errno.ENOSPC, "No space left on device")
                return replace(source, target)

            with patch.object(module, "__file__", str(moved)):
                with patch.object(os, "replace", side_effect=disk_full), self.assertRaises(OSError):
                    module.enable(root)
                self.assertEqual(desktop.read_bytes(), before)
                self.assertEqual(published_modes, [(state, 0o600), (desktop, 0o644)])
                module.enable(root)
                module.disable()
            self.assertFalse(state.exists())
            self.assertFalse(desktop.exists())

    def test_completed_update_does_not_own_an_old_entry_restored_by_user(self):
        from unittest.mock import patch
        fixture = lifecycle.TomaccoFrontendTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        module = fixture.module()
        root, pins = fixture.release(module)
        with patch.dict(os.environ, fixture.env), pins:
            module.enable(root)
            state, desktop = module.locations()
            old_entry = desktop.read_bytes()
            moved = fixture.home / "moved-tool.py"
            moved.write_bytes(TOOL.read_bytes())
            with patch.object(module, "__file__", str(moved)):
                module.enable(root)
            desktop.write_bytes(old_entry)
            with self.assertRaisesRegex(ValueError, "changed"):
                module.disable()
            self.assertEqual(desktop.read_bytes(), old_entry)
            self.assertTrue(state.exists())


if __name__ == "__main__":
    unittest.main()
