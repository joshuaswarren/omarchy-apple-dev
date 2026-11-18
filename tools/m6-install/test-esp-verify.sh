#!/bin/bash
# Exercises the esp_install path in m6-partition-write.sh: a changed esp.tar must be
# refused before anything is unpacked; a matching tar unpacks. Runs on any host with
# bash, tar and shasum/sha256sum; curl is stubbed, no network, no disk touched.
#
# Trust boundary: esp.sha, like SHA256SUMS, is announced by the same image server, so
# the check catches a damaged or mismatched download and does NOT protect against
# someone who controls that server or the path to it; the user runs the server on
# their own network with the token and allow-list.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
if command -v shasum > /dev/null 2>&1; then
    sha() { shasum -a 256 | awk '{print $1}'; }
elif command -v sha256sum > /dev/null 2>&1; then
    sha() { sha256sum | awk '{print $1}'; }
else
    echo "ABORT: neither shasum nor sha256sum (nothing changed)" >&2
    exit 1
fi
td="$(mktemp -d)"
trap 'rm -rf "$td"' EXIT

mkdir -p "$td/esp-tree/aurora" "$td/mnt-good" "$td/mnt-tampered"
printf 'stage1-payload\n' > "$td/esp-tree/aurora/stage1.bin"
tar -cf "$td/good.tar" -C "$td/esp-tree" .
cp "$td/good.tar" "$td/tampered.tar"
printf 'TAMPERED-BYTES\n' >> "$td/tampered.tar"
printf '%s\n' "$(sha < "$td/good.tar")" > "$td/esp.sha"

SERVER="http://stub.invalid/0000"
TAMPER=0
# Stub curl: answers /esp.sha with the good hash; writes good.tar or tampered.tar to
# the path the script passed to -o (it is always /tmp/m6-esp.tar).
curl() {
    local url="" a
    for a in "$@"; do case "$a" in http*) url="$a" ;; esac; done
    case "$url" in
        *esp.sha) cat "$td/esp.sha" ;;
        *esp.tar)
            if [ "$TAMPER" = 1 ]; then cat "$td/tampered.tar" > /tmp/m6-esp.tar
            else cat "$td/good.tar" > /tmp/m6-esp.tar; fi ;;
        *) echo "stub curl: unexpected $url" >&2; return 22 ;;
    esac
}

M6_TEST_ONLY=1 . "$here/m6-partition-write.sh"

# 1: a changed tar is refused and nothing is unpacked
TAMPER=1
if esp_install "$td/mnt-tampered"; then
    echo "FAIL: tampered esp.tar was accepted" >&2; exit 1
fi
[ -z "$(ls -A "$td/mnt-tampered")" ] || { echo "FAIL: tampered esp.tar was unpacked" >&2; exit 1; }
rm -f /tmp/m6-esp.tar

# 2: a matching tar unpacks
TAMPER=0
esp_install "$td/mnt-good"
[ -f "$td/mnt-good/aurora/stage1.bin" ] || { echo "FAIL: good esp.tar did not unpack" >&2; exit 1; }
grep -q 'stage1-payload' "$td/mnt-good/aurora/stage1.bin" || { echo "FAIL: unpacked content wrong" >&2; exit 1; }

echo "ok: changed esp.tar refused before unpack, matching esp.tar unpacked"
