import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import test_tomacco_frontend as lifecycle

TOOL = Path(__file__).resolve().parents[1] / "tools/tomacco-frontend.py"


class FrontendPlatformTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("gio"), "gio is required for real desktop argument round trips")
    def test_real_gio_argument_round_trip(self):
        fixture = lifecycle.TomaccoFrontendTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        module = fixture.module()
        cases = [("recorder.py", argument) for argument in
                 ("plain-control", "ends-with-backslash\\", "two\\\\backslashes",
                  'quote" dollar$ percent%f', "literal\\n-control", "")]
        cases.extend((name, "path-control") for name in
                     ('quote"$%f.py', "two\\\\backslashes.py", "ends-with-backslash\\"))
        for index, (name, argument) in enumerate(cases):
            with self.subTest(recorder=name, argument=argument):
                recorder = fixture.home / name
                recorder.write_text("import json, sys\nprint(json.dumps(sys.argv[1:]), flush=True)\n")
                command = " ".join(module.desktop_argument(p) for p in
                                   (sys.executable, "-I", recorder, argument))
                desktop = fixture.home / f"case-{index}.desktop"
                desktop.write_text("[Desktop Entry]\nType=Application\nName=Argv recorder\n"
                                   f"Exec={command}\nTerminal=false\n")
                done = subprocess.run(["gio", "launch", str(desktop)], env=fixture.env,
                                      capture_output=True, text=True, timeout=10, check=False)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(done.stderr, "")
                self.assertEqual(json.loads(done.stdout), [argument])

    def test_valid_launch_executes_fixture_with_original_home_and_saved_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installation = root / 'separate "fixture" %f\\'
            installation.mkdir()
            capture = root / "observed.json"
            frontend = installation / "tomacco"
            frontend.write_text(f'''#!{sys.executable}
import json, os, sys
from pathlib import Path
Path(os.environ["CAPTURE"]).write_text(json.dumps({{
    "argv": sys.argv, "pid": os.getpid(),
    "env": {{k: os.environ.get(k) for k in ("HOME", "PATH", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME")}}
}}))
raise SystemExit(23)
''')
            frontend.chmod(0o755)
            cli = installation / "tomaccoctl"
            cli.write_bytes(b"fixture control executable; never executed")
            cli.chmod(0o755)
            env = {**os.environ, "HOME": str(root / "normal-home"),
                   "XDG_CONFIG_HOME": str(root / "normal-config"),
                   "XDG_DATA_HOME": str(root / "normal-data"),
                   "XDG_CACHE_HOME": str(root / "normal-cache"), "CAPTURE": str(capture)}
            code = '''
import hashlib, importlib.util, os, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("frontend", sys.argv[1])
assert spec is not None and spec.loader is not None
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
root = Path(sys.argv[2])
m.BINARIES = {n: hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ("tomacco", "tomaccoctl")}
m.enable(root)
os.environ["PATH"] = "/not-the-registered-path"
sys.argv = [str(m.__file__), "launch"]
m.main()
'''
            child = subprocess.Popen([sys.executable, "-I", "-c", code, str(TOOL), str(installation)],
                                     env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = child.communicate(timeout=10)
            self.assertEqual(child.returncode, 23, stdout + stderr)
            observed = json.loads(capture.read_text())
            self.assertEqual(observed["argv"], [str(frontend)])
            self.assertEqual(observed["pid"], child.pid)
            self.assertEqual(observed["env"], {k: env[k] for k in
                             ("HOME", "PATH", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME")})


if __name__ == "__main__":
    unittest.main()
