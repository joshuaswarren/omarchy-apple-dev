# m6-install: macOS-side install for Apple-silicon Macs

One image server on an admin host, one driver, one partition writer on the target Mac.

- `m6-macos-install.sh` runs on the admin host: drives the whole flow over ssh, with `--selftest`, `--dry-run` and `--go` (see its header).
- `m6-image-server.py` streams `boot.img`, `root.img`, `esp.tar` (+ `esp.sha`), `boot.bin`, `SHA256SUMS` and the two scripts to the target over HTTP, token and allow-list gated.
- `m6-partition-write.sh` runs on the target Mac: creates the three partitions after the Aura stub, writes the images with stream and readback hash checks, unpacks `esp.tar` only after its sha256 matches `esp.sha`.
- `test-esp-verify.sh` proves a changed `esp.tar` is refused before unpack; run it anywhere, no network, no disk.

Trust boundary: `esp.sha`, like `SHA256SUMS`, is announced by the same image server, so the hash checks catch a damaged or mismatched download and do NOT protect against someone who controls that server or the path to it; the user runs the server on their own network with the token and allow-list.
