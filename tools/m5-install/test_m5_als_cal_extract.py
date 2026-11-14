#!/usr/bin/env python3
"""Contract tests for tools/m5-install/m5_als_cal_extract.py (tests only).

python3 tools/m5-install/test_m5_als_cal_extract.py
Stdlib only. No root, no hardware, no real captures, no real calibration
bytes. Synthetic 193-byte payloads throughout; any valid Mac17,11 payload
is accepted, so success and refusal paths both run the real parser, CLI,
and install boundary.

CLI contract: m5_als_cal_extract.py CAPTURE CAPTURE -o OUTPUT
Exactly two agreeing captures, required explicit -o, no other options.
"""
import contextlib
import hashlib
import io
import os
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import m5_als_cal_extract as ext  # noqa: E402

TOOL = os.path.join(HERE, "m5_als_cal_extract.py")

SYN = bytes(((i * 7 + 3) & 0xFF) for i in range(193))
assert len(SYN) == ext.EXPECTED_LEN
SYN_HEX = SYN.hex()
assert SYN_HEX[:32] not in open(TOOL, encoding="utf-8").read()  # no literals

ROOT = "+-o Root  <class IORegistryEntry, id 0x100000100, retain 10>\n"
PLAT_HDR = ("  +-o K114cAP  <class IOPlatformExpertDevice, id 0x200000101, "
            "registered, matched, active, busy 0 (0 ms), retain 20>\n")
PLAT_OPEN, PLAT_CLOSE = "    | {\n", "    | }\n"
PLAT_PP = "    |   "
VD_PP = "    | |   |       |           |   "
VD_HDR = ("    | |   |       |         +-o {name}  <class {cls}, id 0x10000102b, "
          "registered, matched, active, busy 0 (0 ms), retain 10>\n")
VD_OPEN, VD_CLOSE = "    | |   |       |           | {\n", "    | |   |       |           | }\n"


def prop(pp, key, value):
    return '%s  "%s" = %s\n' % (pp, key, value)


def fixture(model="Mac17,11", node="AppleSPUVD6286", node_cls=None,
            payload_hex=SYN_HEX,
            calibrated="Yes", exbright="Yes", data_key="CalibrationData",
            ndata=1, nnodes=1, nplat=1, raw_payload=None):
    """Synthetic ioreg text; structural mirror of the real capture shape."""
    text = ROOT
    if model is not None:
        plat = PLAT_HDR + PLAT_OPEN
        plat += prop(PLAT_PP, "compatible", '<"K114cAP","%s","AppleARM">' % model)
        plat += prop(PLAT_PP, "model", '<"%s">' % model)
        text += (plat + PLAT_CLOSE) * nplat
    body = prop(VD_PP, "Calibrated", calibrated)
    body += prop(VD_PP, "EXBrightCalibrationSuccess", exbright)
    if raw_payload is not None:
        body += '%s  "%s" = %s\n' % (VD_PP, data_key, raw_payload)
    else:
        body += '%s  "%s" = <%s>\n' % (VD_PP, data_key, payload_hex) * ndata
    for _ in range(nnodes):
        text += VD_HDR.format(name=node, cls=node_cls or node) + VD_OPEN + body + VD_CLOSE
    return text


FAILURES, TESTS = [], []


def check(name):
    def deco(fn):
        def run():
            try:
                fn()
                print("PASS %s" % name)
            except AssertionError as e:
                FAILURES.append(name)
                print("FAIL %s: %s" % (name, e))
            except Exception as e:  # noqa: BLE001
                FAILURES.append(name)
                print("FAIL %s: %r" % (name, e))
        TESTS.append(run)
        return run
    return deco


def run_cli(args):
    return subprocess.run([sys.executable, TOOL] + args,
                          capture_output=True, text=True)


def run_cli_inproc(args):
    """ext.main() in-process; argparse exits surface as SystemExit."""
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = ext.main(list(args))
    except SystemExit as e:  # argparse errors
        rc = e.code
    return rc, out.getvalue(), err.getvalue()


def tmpdir():
    return tempfile.mkdtemp(prefix="m5alstest-")


def wfile(path, data, mode=0o600):
    with open(path, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(path, mode)
    return path


def wfpair(d, text, name):
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


def assert_no_temps(d, keep=()):
    leftovers = [n for n in os.listdir(d) if n.startswith(".") and n not in keep]
    assert not leftovers, "temp files left behind: %r" % leftovers


# --- success paths (synthetic) ---------------------------------------------

@check("success_two_agreeing_captures_idempotent")
def t1():
    d = tmpdir()
    try:
        c1 = wfpair(d, fixture(), "a.txt")
        c2 = wfpair(d, fixture(), "b.txt")
        out = os.path.join(d, "aop-als-cal.bin")
        rc, stdout, stderr = run_cli_inproc([c1, c2, "-o", out])
        assert rc == 0, "exit %s: %s" % (rc, stderr)
        assert os.path.isfile(out) and not os.path.islink(out)
        st = os.stat(out)
        assert stat.S_IMODE(st.st_mode) == 0o600, oct(st.st_mode)
        assert open(out, "rb").read() == SYN
        blob = stdout + stderr
        assert SYN_HEX[:32] not in blob, "payload hex leaked to output"
        assert ext.EXPECTED_NODE in stdout and "bytes=193" in stdout
        assert ext.EXPECTED_MODEL in stdout and "idempotent" not in stdout
        os.utime(out, (1000000000, 1000000000))
        rc2, stdout2, _ = run_cli_inproc([c1, c2, "-o", out])
        assert rc2 == 0 and "idempotent" in stdout2
        assert os.stat(out).st_mtime == 1000000000, "valid file rewritten"
        assert open(out, "rb").read() == SYN
        assert_no_temps(d)
    finally:
        shutil.rmtree(d)


@check("success_multiline_blob_continuation")
def t2():
    d = tmpdir()
    try:
        raw = "<%s\n%s  %s\n%s  %s>" % (SYN_HEX[0:128], VD_PP.rstrip(),
                                        SYN_HEX[128:256], VD_PP.rstrip(),
                                        SYN_HEX[256:])
        c1 = wfpair(d, fixture(raw_payload=raw), "a.txt")
        c2 = wfpair(d, fixture(raw_payload=raw), "b.txt")
        out = os.path.join(d, "aop-als-cal.bin")
        rc, _, err = run_cli_inproc([c1, c2, "-o", out])
        assert rc == 0, "exit %s: %s" % (rc, err)
        assert open(out, "rb").read() == SYN
        assert_no_temps(d)
    finally:
        shutil.rmtree(d)


# --- fail closed: malformed / identity / duplicates / count ----------------

@check("malformed_hex_fails_no_output")
def t4():
    d = tmpdir()
    try:
        out = os.path.join(d, "aop-als-cal.bin")
        cases = [fixture(payload_hex="xyz"), fixture(payload_hex=SYN_HEX[:-1]),
                 fixture(raw_payload="<%s" % SYN_HEX), fixture(payload_hex=SYN_HEX + "00")]
        for i, text in enumerate(cases):
            c = wfpair(d, text, "bad%d.txt" % i)
            r = run_cli([c, c, "-o", out])
            assert r.returncode != 0, "case %d accepted malformed input" % i
            assert not os.path.exists(out)
            assert SYN_HEX[:32] not in r.stdout + r.stderr
        assert_no_temps(d)
    finally:
        shutil.rmtree(d)


@check("wrong_model_or_missing_model_fails")
def t5():
    d = tmpdir()
    try:
        out = os.path.join(d, "aop-als-cal.bin")
        for name, text in (("wm", fixture(model="Mac17,12")),
                           ("nm", fixture(model=None))):
            c = wfpair(d, text, name + ".txt")
            r = run_cli([c, c, "-o", out])
            assert r.returncode != 0 and not os.path.exists(out), name
    finally:
        shutil.rmtree(d)


@check("wrong_or_missing_node_fails")
def t6():
    d = tmpdir()
    try:
        out = os.path.join(d, "aop-als-cal.bin")
        c = wfpair(d, fixture(node="AppleSPUVD6285"), "wn.txt")
        r = run_cli([c, c, "-o", out])
        assert r.returncode != 0 and not os.path.exists(out)
        c = wfpair(d, ROOT, "nn.txt")
        r = run_cli([c, c, "-o", out])
        assert r.returncode != 0 and not os.path.exists(out)
    finally:
        shutil.rmtree(d)


@check("duplicate_node_or_data_fails")
def t7():
    d = tmpdir()
    try:
        out = os.path.join(d, "aop-als-cal.bin")
        for name, text in (("dn", fixture(nnodes=2)), ("dd", fixture(ndata=2))):
            c = wfpair(d, text, name + ".txt")
            r = run_cli([c, c, "-o", out])
            assert r.returncode != 0 and not os.path.exists(out), name
    finally:
        shutil.rmtree(d)


@check("not_calibrated_flags_fail")
def t8():
    d = tmpdir()
    try:
        out = os.path.join(d, "aop-als-cal.bin")
        for kw in ({"calibrated": "No"}, {"exbright": "No"}, {"calibrated": "Maybe"}):
            c = wfpair(d, fixture(**kw), "nc.txt")
            r = run_cli([c, c, "-o", out])
            assert r.returncode != 0 and not os.path.exists(out), kw
    finally:
        shutil.rmtree(d)


@check("cli_accepts_foreign_valid_193b")
def t9():
    # A foreign but valid 193-byte payload in two agreeing captures must
    # install through the real subprocess CLI with exactly those bytes.
    d = tmpdir()
    try:
        out = os.path.join(d, "aop-als-cal.bin")
        foreign = bytes(((i * 11 + 5) & 0xFF) for i in range(193))
        c = wfpair(d, fixture(payload_hex=foreign.hex()), "fh.txt")
        r = run_cli([c, c, "-o", out])
        assert r.returncode == 0, "exit %s: %s" % (r.returncode, r.stderr)
        assert open(out, "rb").read() == foreign
        assert stat.S_IMODE(os.stat(out).st_mode) == 0o600
        assert ("sha256=%s" % hashlib.sha256(foreign).hexdigest()) in r.stdout
        assert_no_temps(d)
        r = run_cli([c, c, "-o", out, "--expected-digest", "0" * 64])
        assert r.returncode != 0
        r = run_cli([c, c])  # missing -o
        assert r.returncode != 0
    finally:
        shutil.rmtree(d)


@check("disagreeing_captures_fail")
def t10():
    d = tmpdir()
    try:
        out = os.path.join(d, "aop-als-cal.bin")
        other = bytes(((i * 13 + 1) & 0xFF) for i in range(193))
        c1 = wfpair(d, fixture(), "a.txt")
        c2 = wfpair(d, fixture(payload_hex=other.hex()), "b.txt")
        r = run_cli([c1, c2, "-o", out])
        assert r.returncode != 0 and not os.path.exists(out)
    finally:
        shutil.rmtree(d)


@check("missing_calibration_data_is_CalError")
def t18():
    # Regression: absent CalibrationData key must fail closed as CalError,
    # never leak an uncaught KeyError.
    try:
        ext.parse_capture_text(fixture(data_key="SomeOtherKey"))
        raise AssertionError("missing CalibrationData accepted")
    except ext.CalError:
        pass
    d = tmpdir()
    try:
        c = wfpair(d, fixture(data_key="SomeOtherKey"), "mk.txt")
        r = run_cli([c, c, "-o", os.path.join(d, "out.bin")])
        assert r.returncode != 0
        assert "KeyError" not in r.stderr and "Traceback" not in r.stderr
    finally:
        shutil.rmtree(d)


@check("duplicate_platform_node_fails")
def t19():
    # Regression: exactly one IOPlatformExpertDevice is acceptable; a
    # second (ambiguous captured root) must fail closed.
    try:
        ext.parse_capture_text(fixture(nplat=2))
        raise AssertionError("duplicate platform node accepted")
    except ext.CalError:
        pass


@check("wrong_capture_count_fails")
def t20():
    # Regression: exactly two agreeing captures, no more, no fewer.
    d = tmpdir()
    try:
        c1 = wfpair(d, fixture(), "a.txt")
        c2 = wfpair(d, fixture(), "b.txt")
        c3 = wfpair(d, fixture(), "c.txt")
        for paths in ([c1], [c1, c2, c3]):
            try:
                ext.extract_from_files(paths)
                raise AssertionError("capture count %d accepted" % len(paths))
            except ext.CalError:
                pass
        r = run_cli([c1, "-o", os.path.join(d, "x.bin")])
        assert r.returncode != 0
        r = run_cli([c1, c2, c3, "-o", os.path.join(d, "x.bin")])
        assert r.returncode != 0
    finally:
        shutil.rmtree(d)


# --- output boundary --------------------------------------------------------

@check("existing_mismatch_refused_and_preserved")
def t11():
    d = tmpdir()
    try:
        c = wfpair(d, fixture(), "a.txt")
        out = wfile(os.path.join(d, "aop-als-cal.bin"), b"PREEXISTING")
        r = run_cli([c, c, "-o", out])
        assert r.returncode != 0
        assert open(out, "rb").read() == b"PREEXISTING"
        assert_no_temps(d)
    finally:
        shutil.rmtree(d)


@check("symlink_dest_refused_target_untouched")
def t12():
    d = tmpdir()
    try:
        c = wfpair(d, fixture(), "a.txt")
        target = wfile(os.path.join(d, "real-target"), b"KEEP")
        out = os.path.join(d, "aop-als-cal.bin")
        os.symlink(target, out)
        r = run_cli([c, c, "-o", out])
        assert r.returncode != 0
        assert os.path.islink(out) and open(target, "rb").read() == b"KEEP"
        out2 = os.path.join(d, "dangling.bin")
        os.symlink(os.path.join(d, "nope"), out2)
        r = run_cli([c, c, "-o", out2])
        assert r.returncode != 0 and os.path.islink(out2)
    finally:
        shutil.rmtree(d)


@check("too_open_existing_private_file_refused")
def t13():
    # Regression of the private-success rule: an existing file readable by
    # group/other must be refused at the write boundary even if the bytes
    # would match. Direct install_payload call.
    d = tmpdir()
    try:
        out = wfile(os.path.join(d, "aop-als-cal.bin"), SYN, mode=0o644)
        try:
            ext.install_payload(SYN, out)
            raise AssertionError("too-open existing accepted")
        except ext.CalError:
            pass
        assert open(out, "rb").read() == SYN  # preserved
        assert stat.S_IMODE(os.stat(out).st_mode) == 0o644  # untouched
        assert_no_temps(d)
    finally:
        shutil.rmtree(d)


@check("parent_permissions_refused")
def t14():
    d = tmpdir()
    try:
        c = wfpair(d, fixture(), "a.txt")
        sub = os.path.join(d, "loose")
        os.mkdir(sub)
        os.chmod(sub, 0o777)
        r = run_cli([c, c, "-o", os.path.join(sub, "aop-als-cal.bin")])
        assert r.returncode != 0 and not os.path.exists(os.path.join(sub, "aop-als-cal.bin"))
        os.chmod(sub, 0o700)
    finally:
        os.chmod(d, 0o700)
        shutil.rmtree(d)


@check("unwritable_dir_refused_no_temps")
def t15():
    d = tmpdir()
    try:
        c = wfpair(d, fixture(), "a.txt")
        sub = os.path.join(d, "ro")
        os.mkdir(sub)
        os.chmod(sub, 0o500)
        out = os.path.join(sub, "aop-als-cal.bin")
        try:
            r = run_cli([c, c, "-o", out])
            assert r.returncode != 0 and not os.path.exists(out)
            assert os.listdir(sub) == [], "temps left in unwritable dir"
        finally:
            os.chmod(sub, 0o700)
    finally:
        shutil.rmtree(d)


@check("concurrent_writer_wins_tool_preserves")
def t16():
    d = tmpdir()
    try:
        out = os.path.join(d, "aop-als-cal.bin")
        real_link = os.link

        def racing_link(src, dst, *a, **kw):
            wfile(out, b"OTHER-WRITER")
            return real_link(src, dst, *a, **kw)  # EEXIST

        os.link = racing_link
        try:
            try:
                ext.install_payload(SYN, out)
                raise AssertionError("race accepted silently")
            except ext.CalError:
                pass
        finally:
            os.link = real_link
        assert open(out, "rb").read() == b"OTHER-WRITER"
        assert_no_temps(d)
    finally:
        shutil.rmtree(d)


@check("concurrent_symlink_refused_not_idempotent")
def t17():
    # Regression: a concurrent writer that places a SYMLINK (to identical
    # bytes) at the destination must be refused exactly like an initial
    # symlink; the tool must not follow it to reach a "matching" verdict.
    d = tmpdir()
    try:
        out = os.path.join(d, "aop-als-cal.bin")
        target = wfile(os.path.join(d, "target"), SYN)
        real_link = os.link

        def racing_link(src, dst, *a, **kw):
            os.symlink(target, out)
            return real_link(src, dst, *a, **kw)  # EEXIST

        os.link = racing_link
        try:
            try:
                ext.install_payload(SYN, out)
                raise AssertionError("raced symlink accepted as idempotent")
            except ext.CalError:
                pass
        finally:
            os.link = real_link
        assert os.path.islink(out)
        assert open(target, "rb").read() == SYN
        assert_no_temps(d)
    finally:
        shutil.rmtree(d)


@check("install_direct_existing_and_missing_parent")
def t21():
    d = tmpdir()
    try:
        out = wfile(os.path.join(d, "aop-als-cal.bin"), SYN)
        os.utime(out, (1000000000, 1000000000))
        assert ext.install_payload(SYN, out) == "idempotent"
        assert os.stat(out).st_mtime == 1000000000
        try:
            ext.install_payload(b"z" * 193, out)
            raise AssertionError("mismatch accepted")
        except ext.CalError:
            pass
        try:
            ext.install_payload(SYN, os.path.join(d, "missing-dir", "f"))
            raise AssertionError("missing parent accepted")
        except ext.CalError:
            pass
        assert_no_temps(d)
    finally:
        shutil.rmtree(d)


@check("parent_renamed_midflight_stays_on_opened_dir")
def t22():
    # Regression: after install_payload opens the parent directory, a
    # concurrent rename of that directory plus a replacement directory at
    # the old path must not divert the writer. Every child operation is
    # anchored to the opened dirfd: the file must land in the renamed
    # (still-opened) directory; the replacement directory stays untouched.
    d = tmpdir()
    try:
        p1 = os.path.join(d, "out-dir")
        os.mkdir(p1)
        p2 = os.path.join(d, "moved-dir")
        real_link = os.link
        state = {"renamed": False}

        def renaming_link(src, dst, *a, **kw):
            os.rename(p1, p2)      # move the opened directory away
            os.mkdir(p1)           # replacement at the old path
            state["renamed"] = True
            return real_link(src, dst, *a, **kw)

        os.link = renaming_link
        try:
            action = ext.install_payload(SYN, os.path.join(p1, "aop-als-cal.bin"))
        finally:
            os.link = real_link
        assert state["renamed"]
        assert action == "created"
        assert open(os.path.join(p2, "aop-als-cal.bin"), "rb").read() == SYN
        assert os.listdir(p1) == [], "replacement directory was written"
        assert_no_temps(p2)
    finally:
        shutil.rmtree(d)


@check("temp_name_collision_preserves_other_writer_temp")
def t24():
    # Regression: ownership starts only after the O_EXCL open succeeds.
    # A fixed-token temp-name collision must refuse WITHOUT unlinking the
    # other writer's temp (bytes and mtime preserved).
    d = tmpdir()
    try:
        out = os.path.join(d, "aop-als-cal.bin")
        fixed = ".m5-als-cal." + "ab" * 8
        pre = os.path.join(d, fixed)
        wfile(pre, b"OTHER-TEMP", mode=0o600)
        os.utime(pre, (1234567890, 1234567890))
        real_token = ext.secrets.token_hex
        ext.secrets.token_hex = lambda n: "ab" * n
        try:
            try:
                ext.install_payload(SYN, out)
                raise AssertionError("temp collision accepted")
            except ext.CalError:
                pass
        finally:
            ext.secrets.token_hex = real_token
        assert open(pre, "rb").read() == b"OTHER-TEMP", "foreign temp destroyed"
        assert os.stat(pre).st_mtime == 1234567890, "foreign temp rewritten"
        assert not os.path.exists(out)
        assert_no_temps(d, keep=(fixed,))
    finally:
        shutil.rmtree(d)


@check("error_cleanup_unlink_fsync_close_order")
def t23():
    # Regression: the error-path cleanup is durable and ordered — owned
    # temp unlink, then dir fsync, then dirfd close (nested finally).
    # Forced via a failing post-write verification.
    d = tmpdir()
    try:
        out = os.path.join(d, "aop-als-cal.bin")
        real = {"unlink": os.unlink, "fsync": os.fsync, "close": os.close}
        events = []

        def rec_unlink(path, *a, **kw):
            events.append(("unlink", path))
            return real["unlink"](path, *a, **kw)

        def rec_fsync(fd):
            events.append(("fsync", fd))
            return real["fsync"](fd)

        def rec_close(fd):
            events.append(("close", fd))
            return real["close"](fd)

        real_sha = ext._sha_fd

        def bad_sha(fd):
            return "0" * 64  # verification can never match

        os.unlink, os.fsync, os.close = rec_unlink, rec_fsync, rec_close
        ext._sha_fd = bad_sha
        try:
            try:
                ext.install_payload(SYN, out)
                raise AssertionError("verify failure accepted")
            except ext.CalError:
                pass
        finally:
            os.unlink, os.fsync, os.close = (real["unlink"], real["fsync"],
                                             real["close"])
            ext._sha_fd = real_sha
        assert open(out, "rb").read() == SYN  # preserved, not deleted
        kinds = [e[0] for e in events]
        assert "unlink" in kinds and kinds[-1] == "close"
        i_unlink = kinds.index("unlink")
        i_fsync_last = len(kinds) - 1 - kinds[::-1].index("fsync")
        i_close_last = len(kinds) - 1 - kinds[::-1].index("close")
        assert i_unlink < i_fsync_last, "unlink must precede final dir fsync"
        assert i_fsync_last < i_close_last, "dirfd close must follow fsync"
        assert_no_temps(d)
    finally:
        shutil.rmtree(d)


@check("file_fsync_failure_cleans_owned_temp")
def t25():
    # Regression: ownership transfers at O_EXCL open, so a write/flush/
    # fsync failure inside the caller must still clean the owned temp.
    # First fsync (the temp file's) fails; the dir fsync afterwards works.
    d = tmpdir()
    try:
        out = os.path.join(d, "aop-als-cal.bin")
        real_fsync = os.fsync
        state = {"calls": 0}

        def flaky_fsync(fd):
            state["calls"] += 1
            if state["calls"] == 1:
                raise OSError("simulated file fsync failure")
            return real_fsync(fd)

        os.fsync = flaky_fsync
        try:
            try:
                ext.install_payload(SYN, out)
                raise AssertionError("fsync failure accepted")
            except OSError:
                pass
        finally:
            os.fsync = real_fsync
        assert not os.path.exists(out), "output written despite fsync failure"
        assert os.listdir(d) == [], "owned temp leaked after fsync failure"
    finally:
        shutil.rmtree(d)


@check("unlink_error_still_closes_dirfd")
def t26():
    # Regression: a non-ENOENT unlink error on the owned temp must not
    # leak the directory fd — close still happens and failure propagates.
    d = tmpdir()
    try:
        out = os.path.join(d, "aop-als-cal.bin")
        real = {"unlink": os.unlink, "close": os.close}
        events = []

        def bad_unlink(path, *a, **kw):
            if os.path.basename(str(path)).startswith(".m5-als-cal."):
                events.append(("unlink-fail", path))
                raise OSError("simulated unlink failure")
            return real["unlink"](path, *a, **kw)

        def rec_close(fd):
            events.append(("close", fd))
            return real["close"](fd)

        os.unlink, os.close = bad_unlink, rec_close
        try:
            try:
                ext.install_payload(SYN, out)
                raise AssertionError("unlink failure accepted")
            except OSError:
                pass
        finally:
            os.unlink, os.close = real["unlink"], real["close"]
        kinds = [e[0] for e in events]
        assert "unlink-fail" in kinds
        i = kinds.index("unlink-fail")
        assert "close" in kinds[i + 1:], "dirfd leaked after unlink error"
        # The destination was linked and verified before cleanup failed;
        # it remains valid while the failure still propagates.
        assert open(out, "rb").read() == SYN
    finally:
        shutil.rmtree(d)




@check("parser_block_errors_direct")
def t27():
    # In-process calls cover parser branches that subprocess coverage misses.
    plat = (PLAT_HDR + PLAT_OPEN + prop(PLAT_PP, "model", '<"Mac17,11">')
            + PLAT_CLOSE)
    header = VD_HDR.format(name=ext.EXPECTED_NODE, cls=ext.EXPECTED_NODE)
    try:
        ext.parse_capture_text(ROOT + plat + header)
        raise AssertionError("missing block opener accepted")
    except ext.CalError as e:
        assert "no property block" in str(e)

    col = VD_OPEN.index("{")
    for tail in ("", " " * col + "\n", " " * col + "|\n"):
        text = ROOT + plat + header + VD_OPEN + prop(VD_PP, "Calibrated", "Yes") + tail
        try:
            ext.parse_capture_text(text)
            raise AssertionError("unterminated block accepted: %r" % tail)
        except ext.CalError as e:
            assert "unterminated property block" in str(e)

    child = ("    | |   |       |           |     +-o Child  "
             "<class Child, id 0x1, registered, matched, active, busy 0 (0 ms), retain 1>\n")
    text = ROOT + plat + header + VD_OPEN + child + prop(VD_PP, "Calibrated", "Yes") + VD_CLOSE
    try:
        ext.parse_capture_text(text)
        raise AssertionError("nested node accepted")
    except ext.CalError as e:
        assert "nested node" in str(e)


@check("parser_identity_and_blob_direct")
def t28():
    # Direct calls cover exact node class, model value shape, and blob failures.
    cases = (
        (fixture(node_cls="AppleSPUVD6285"), "class mismatch"),
        (fixture(payload_hex=SYN_HEX[:-1]), "odd hex"),
        (fixture(payload_hex=SYN_HEX + "00"), "length 194"),
        (fixture(raw_payload="<" + SYN_HEX), "unterminated hex"),
        (fixture(ndata=2), "duplicate property CalibrationData"),
        (fixture().replace('= <"Mac17,11">', '= Mac17,11'), "invalid shape"),
    )
    for text, phrase in cases:
        try:
            ext.parse_capture_text(text)
            raise AssertionError("malformed input accepted: %s" % phrase)
        except ext.CalError as e:
            assert phrase in str(e), (phrase, str(e))
@check("writable_parent_and_required_output_direct")
def t29():
    # Hit output validation directly with synthetic bytes.
    d = tmpdir()
    try:
        c1 = wfpair(d, fixture(), "a.txt")
        c2 = wfpair(d, fixture(), "b.txt")
        rc, _, err = run_cli_inproc([c1, c2])
        assert rc == 2 and "usage:" in err  # required -o, valid inputs

        sub = os.path.join(d, "open")
        os.mkdir(sub)
        os.chmod(sub, 0o777)
        try:
            try:
                ext.install_payload(SYN, os.path.join(sub, "out.bin"))
                raise AssertionError("writable parent accepted")
            except ext.CalError as e:
                assert "writable" in str(e)
            assert os.listdir(sub) == []
        finally:
            os.chmod(sub, 0o700)
    finally:
        shutil.rmtree(d)

def main():
    for t in TESTS:
        t()
    print("---")
    if FAILURES:
        print("FAILED: %d (%s)" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("ALL %d CONTRACT TESTS PASS" % len(TESTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
