import importlib.util
import os
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "compat_suite", os.path.join(os.path.dirname(__file__), "..", "tools", "compat-suite.py"))
suite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(suite)

MARKERS = "".join(f"echo '== {n}. step'; " for n in range(1, 9))


def run(config, sysfs):
    config = {"name": "app", "repo": "r", "sha": "s", "license": "MIT", **config}
    with tempfile.TemporaryDirectory() as work:
        rows, devices, apple, _ = suite.run_suite(config, work, os.path.join(work, "out"), 30, sysfs)
    return {k: v["status"] for k, v in rows.items()}, rows, devices, apple


class CompatSuiteTest(unittest.TestCase):
    def setUp(self):
        self.sysfs = tempfile.mkdtemp()

    def add_usb(self, name, vendor, product):
        os.makedirs(os.path.join(self.sysfs, name))
        for file, value in (("idVendor", vendor), ("idProduct", product)):
            with open(os.path.join(self.sysfs, name, file), "w") as handle:
                handle.write(value + "\n")

    def test_all_stages_pass_and_device_stages_need_a_device(self):
        self.add_usb("1-1", "0bda", "8156")
        status, _, devices, apple = run({"compile": "true", "ship": MARKERS + "true", "test": "true"}, self.sysfs)
        self.assertEqual(status, {"compile": "PASS", "package": "PASS", "sign": "PASS", "archive": "PASS",
                                  "test": "PASS", "install": "NEEDS-DEVICE", "launch": "NEEDS-DEVICE"})
        self.assertEqual((devices, apple), (["1-1 0bda:8156"], 0))

    def test_attached_iphone_is_reported_not_hidden(self):
        self.add_usb("1-2", "05ac", "12a8")
        status, _, _, apple = run({"compile": "true", "ship": "true"}, self.sysfs)
        self.assertEqual(apple, 1)
        self.assertEqual((status["install"], status["launch"]), ("DEVICE-PRESENT", "DEVICE-PRESENT"))

    def test_stage_logs_do_not_leak_absolute_home_paths(self):
        config = {"name": "app", "repo": "r", "sha": "s", "license": "MIT",
                  "compile": 'echo "$HOME/leak"; test -n "$HOME"'}
        with tempfile.TemporaryDirectory() as work:
            suite.run_suite(config, work, os.path.join(work, "out"), 30, self.sysfs)
            logs = os.path.join(work, "out")
            written = "".join(open(os.path.join(logs, f)).read() for f in sorted(os.listdir(logs)) if f.endswith(".log"))
        rows, devices, apple, _ = suite.run_suite(config, work, os.path.join(work, "out2"), 30, self.sysfs)
        self.assertNotIn(os.path.expanduser("~"), written)
        self.assertIn("~/leak", written)
        receipt_text = suite.receipt(config, rows, devices, apple, None)
        self.assertNotIn(os.path.expanduser("~"), receipt_text)

    def test_compile_failure_blocks_ship_but_not_test(self):
        status, rows, _, _ = run({"compile": "echo 'x.swift:3: error: no such module'; exit 1",
                                  "ship": "touch ship-ran", "test": "true"}, self.sysfs)
        self.assertEqual(status["compile"], "FAIL")
        self.assertEqual([status[s] for s in ("package", "sign", "archive")], ["BLOCKED"] * 3)
        self.assertEqual(status["test"], "PASS")
        self.assertIn("no such module", rows["compile"]["error"])

    def test_ship_failure_is_attributed_to_the_step_that_failed(self):
        cases = {
            "echo '== 3. icons'; echo 'icon error' >&2; exit 1": ("FAIL", "BLOCKED", "BLOCKED"),
            "echo '== 6. sign'; echo 'rcodesign: failed' >&2; exit 1": ("BLOCKED", "FAIL", "BLOCKED"),
            "echo '== 6. sign'; echo '== 7. package'; echo 'zip: failed' >&2; exit 1": ("FAIL", "PASS", "BLOCKED"),
            MARKERS + "echo 'ITMS-90000 rejected' >&2; exit 1": ("PASS", "PASS", "FAIL"),
            "echo 'note: a warning line' >&2; echo 'Fatal error: icon has no source' >&2; exit 1": ("FAIL", "BLOCKED", "BLOCKED"),
        }
        for ship, expected in cases.items():
            with self.subTest(ship=ship):
                status, rows, _, _ = run({"compile": "true", "ship": ship}, self.sysfs)
                self.assertEqual((status["package"], status["sign"], status["archive"]), expected)
                self.assertTrue(any(r["error"] for r in rows.values() if r["status"] == "FAIL"))


if __name__ == "__main__":
    unittest.main()
