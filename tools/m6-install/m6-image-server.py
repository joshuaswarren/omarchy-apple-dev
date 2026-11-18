#!/usr/bin/env python3
"""Stream M6 install artifacts to the M6 over HTTP. Read-only; touches no M6 and writes no disk.

  boot.img, root.img   streamed out of the image zip on the build host (nothing is extracted to disk)
  esp.tar              tar of the zip's esp/ tree, built on the fly
  boot.bin             local file (the composed boot object)
  SHA256SUMS           expected hashes (from the image's IMAGE file)

Every path needs the one-time token as first component: /<token>/root.img. Only --allow addresses or networks connect.
Stdlib only (Python 3.9+).
"""
import argparse
import http.server
import ipaddress
import secrets
import shlex
import socketserver
import subprocess
import sys
from pathlib import Path

REMOTE_STREAM = r"""
import sys, zipfile, shutil, tarfile
z = zipfile.ZipFile(sys.argv[1])
what = sys.argv[2]
out = sys.stdout.buffer
if what == "esp.tar":
    with tarfile.open(fileobj=out, mode="w|") as t:
        for i in z.infolist():
            if i.filename.startswith("esp/") and not i.is_dir():
                ti = tarfile.TarInfo(i.filename[4:])
                ti.size = i.file_size
                ti.mode = 0o644
                with z.open(i) as f:
                    t.addfile(ti, f)
elif what == "size":
    print(z.getinfo(sys.argv[3]).file_size)
else:
    with z.open(what) as f:
        shutil.copyfileobj(f, out, 1 << 20)
"""


def argv(host, command):
    if host == "local":
        return ["bash", "-c", command]
    return ["ssh", "-o", "BatchMode=yes", host, command]


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    server_version = "m6-image-server"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def do_GET(self):
        cfg = self.server.cfg
        parts = self.path.lstrip("/").split("/", 1)
        if len(parts) != 2 or not secrets.compare_digest(parts[0], cfg.token):
            self.send_error(404)
            return
        name = parts[1]
        if not any(ipaddress.ip_address(self.client_address[0]) in net for net in cfg.allow):
            self.send_error(403)
            return
        if name == "boot.bin":
            data = cfg.boot_bin.read_bytes()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if name in ("m6-partition-write.sh", "m6-enrol-boot.sh", "m6-recovery-all.sh"):
            data = (Path(__file__).resolve().parent / name).read_bytes()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if name == "sizes":
            data = "".join(f"{k} {v}\n" for k, v in cfg.sizes.items()).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if name == "SHA256SUMS":
            data = cfg.sums.read_bytes()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if name not in ("boot.img", "root.img", "esp.tar"):
            self.send_error(404)
            return
        if name == "root.img" and cfg.root_file:
            self.send_response(200)
            self.send_header("Content-Length", str(cfg.sizes["root.img"]))
            self.end_headers()
            sent = 0
            with open(cfg.root_file, "rb") as f:
                while True:
                    chunk = f.read(1 << 20)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    sent += len(chunk)
            sys.stderr.write(f"served root.img from file: {sent} bytes\n")
            return
        size = cfg.sizes.get(name)
        self.send_response(200)
        if size is not None:
            self.send_header("Content-Length", str(size))
        self.end_headers()
        remote = f"ionice -c3 nice -n 19 python3 -c {shlex.quote(REMOTE_STREAM)} {shlex.quote(cfg.zip)} {shlex.quote(name)}"
        proc = subprocess.Popen(argv(cfg.host, remote), stdout=subprocess.PIPE)
        sent = 0
        try:
            while True:
                chunk = proc.stdout.read(1 << 20)
                if not chunk:
                    break
                self.wfile.write(chunk)
                sent += len(chunk)
        finally:
            proc.stdout.close()
            proc.wait()
        sys.stderr.write(f"served {name}: {sent} bytes, exit {proc.returncode}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True, help="ssh host that holds the image zip, or 'local' when the zip is on this host")
    ap.add_argument("--zip", required=True, help="path of the image zip on that host")
    ap.add_argument("--boot-bin", type=Path, required=True)
    ap.add_argument("--sums", type=Path, required=True)
    ap.add_argument("--allow", action="append", required=True, help="client IP or network, e.g. 10.0.0.0/24 (repeatable)")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--root-file", type=Path, default=None, help="serve root.img from this local file instead of the zip member")
    ap.add_argument("--token", default=None)
    cfg = ap.parse_args()
    cfg.allow = [ipaddress.ip_network(a, strict=False) for a in cfg.allow]
    cfg.token = cfg.token or secrets.token_urlsafe(12)
    cfg.sizes = {}
    for member in ("boot.img", "root.img"):
        if member == "root.img" and cfg.root_file:
            cfg.sizes[member] = cfg.root_file.stat().st_size
            continue
        out = subprocess.run(
            argv(cfg.host, f"python3 -c {shlex.quote(REMOTE_STREAM)} {shlex.quote(cfg.zip)} size {member}"),
            check=True, capture_output=True, text=True).stdout.strip()
        cfg.sizes[member] = int(out)
    print("sizes", cfg.sizes, flush=True)
    print(f"token {cfg.token}", flush=True)

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    srv = Server(("0.0.0.0", cfg.port), Handler)
    srv.cfg = cfg
    print(f"listening on :{cfg.port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
