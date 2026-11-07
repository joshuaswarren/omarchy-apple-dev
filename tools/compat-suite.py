#!/usr/bin/env python3
"""Run one app through the compatibility stages and write a markdown receipt.

  tools/compat-suite.py compat/suite/APP.json --app-dir DIR --out DIR

Stages: adapt (optional), compile, package, sign, install, launch, test, archive.
package, sign and archive come from one `ship` command: ship.sh prints "== N. ..." before each
step, so the last marker and the exit code say which of its steps passed.
install and launch need an iPhone. They are never run here: the receipt lists them NEEDS-DEVICE
with the USB state read from sysfs, or DEVICE-PRESENT when an Apple device is attached.
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

APPLE_VENDOR = "05ac"
ERROR_LINE = re.compile(r"error|fatal|failed|no such|not found", re.I)
SHIP_MARKER = re.compile(r"^== (\d+)\. ", re.M)


def read_text(path):
    with open(path) as handle:
        return handle.read().strip()


def usb_state(sysfs="/sys/bus/usb/devices"):
    """Return (vendor:product lines, count of Apple devices, idevice_id output or None)."""
    devices = []
    for vendor_file in sorted(glob.glob(os.path.join(sysfs, "*", "idVendor"))):
        base = os.path.dirname(vendor_file)
        ids = f"{read_text(vendor_file)}:{read_text(os.path.join(base, 'idProduct'))}"
        devices.append(f"{os.path.basename(base)} {ids}")
    apple = sum(1 for d in devices if d.split()[1].startswith(APPLE_VENDOR + ":"))
    tool = shutil.which("idevice_id")
    listing = None
    if tool:
        run = subprocess.run([tool, "-l"], capture_output=True, text=True, check=False)
        listing = f"rc={run.returncode} {(run.stdout + run.stderr).strip()}"
    return devices, apple, listing


def first_error(log):
    lines = [line.strip() for line in log.splitlines() if line.strip()]
    hard = [line for line in lines if re.search(r"error:|Fatal error|Trace/breakpoint", line)]
    for line in hard or lines:
        if ERROR_LINE.search(line):
            return line[:200]
    return lines[-1][:200] if lines else "(no output)"


def run_stage(command, cwd, log_path, timeout):
    start = time.monotonic()
    try:
        done = subprocess.run(["bash", "-c", command], cwd=cwd, capture_output=True, text=True,
                              timeout=timeout, check=False)
        rc, log = done.returncode, done.stdout + done.stderr
    except subprocess.TimeoutExpired as err:
        rc, log = 124, f"timeout after {timeout}s\n{(err.stdout or b'').decode(errors='replace')}"
    log = log.replace(os.path.expanduser("~"), "~")
    with open(log_path, "w") as handle:
        handle.write(log)
    return rc, log, round(time.monotonic() - start)


def ship_results(rc, log):
    """Map ship.sh's exit code and last "== N." marker to package, sign and archive."""
    if rc == 0:
        return {"package": "PASS", "sign": "PASS", "archive": "PASS"}
    marker = max((int(n) for n in SHIP_MARKER.findall(log)), default=0)
    if marker <= 5:
        order = {"package": "FAIL", "sign": "BLOCKED", "archive": "BLOCKED"}
    elif marker == 6:
        order = {"package": "BLOCKED", "sign": "FAIL", "archive": "BLOCKED"}
    elif marker == 7:
        order = {"package": "FAIL", "sign": "PASS", "archive": "BLOCKED"}
    else:
        order = {"package": "PASS", "sign": "PASS", "archive": "FAIL"}
    return order


def run_suite(config, app_dir, out_dir, timeout=3600, sysfs="/sys/bus/usb/devices"):
    os.makedirs(out_dir, exist_ok=True)
    rows = {}

    def record(stage, command, rc, log, seconds, status=None):
        rows[stage] = {"status": status or ("PASS" if rc == 0 else "FAIL"), "command": command, "rc": rc,
                       "seconds": seconds, "error": "" if rc == 0 else first_error(log)}

    def stage(name):
        command = config.get(name)
        if not command:
            return None
        log_path = os.path.join(out_dir, f"{config['name']}-{name}.log")
        rc, log, seconds = run_stage(command, app_dir, log_path, timeout)
        return command, rc, log, seconds

    ok = True
    for name in ("adapt", "compile"):
        result = stage(name)
        if result:
            record(name, *result)
            ok = ok and result[1] == 0
    ship = stage("ship") if ok else None
    if ship:
        command, rc, log, seconds = ship
        for name, status in ship_results(rc, log).items():
            rows[name] = {"status": status, "command": command, "rc": rc, "seconds": seconds,
                          "error": first_error(log) if status == "FAIL" else ""}
    else:
        for name in ("package", "sign", "archive"):
            rows[name] = {"status": "BLOCKED", "command": config.get("ship", ""), "rc": "",
                          "seconds": "", "error": "an earlier stage failed"}
    result = stage("test")
    if result:
        record("test", *result)
    else:
        rows["test"] = {"status": "NEEDS-DEVICE", "command": "", "rc": "", "seconds": "",
                        "error": "no host test command; the XCTest bundle needs an iOS runtime"}
    devices, apple, listing = usb_state(sysfs)
    for name in ("install", "launch"):
        status = "NEEDS-DEVICE" if apple == 0 else "DEVICE-PRESENT"
        rows[name] = {"status": status, "command": "", "rc": "", "seconds": "", "error": ""}
    return rows, devices, apple, listing


def receipt(config, rows, devices, apple, listing):
    order = ["adapt", "compile", "package", "sign", "install", "launch", "test", "archive"]
    out = [f"# {config['name']} compatibility run", "",
           f"Project: {config['repo']} at {config['sha']} ({config['license']}).", "",
           "| stage | result | seconds | exit | first error |", "|---|---|---|---|---|"]
    for name in order:
        if name in rows:
            row = rows[name]
            out.append(f"| {name} | {row['status']} | {row['seconds']} | {row['rc']} | {row['error']} |")
    out += ["", "Commands:", ""]
    out += [f"- {n}: `{rows[n]['command']}`" for n in order if n in rows and rows[n]["command"]]
    out += ["", f"USB state read from sysfs: {len(devices)} device(s), {apple} Apple (vendor {APPLE_VENDOR}).",
            "The sysfs list is the evidence. idevice_id needs usbmuxd and fails without it.", "",
            "```", *(devices or ["(no USB devices)"]),
            f"idevice_id -l: {listing if listing is not None else 'tool absent'}", "```", ""]
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("config")
    parser.add_argument("--app-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--timeout", type=int, default=3600)
    args = parser.parse_args(argv)
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.environ.setdefault("OMARCHY_APPLE_DEV", repo)
    with open(args.config) as handle:
        config = json.load(handle)
    rows, devices, apple, listing = run_suite(config, args.app_dir, args.out, args.timeout)
    text = receipt(config, rows, devices, apple, listing)
    with open(os.path.join(args.out, f"{config['name']}.md"), "w") as handle:
        handle.write(text)
    print(text)
    return 1 if any(r["status"] in ("FAIL", "BLOCKED") for r in rows.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
