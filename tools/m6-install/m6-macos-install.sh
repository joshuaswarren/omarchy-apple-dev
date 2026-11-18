#!/bin/bash
# One-command driver for the macOS-side install steps (partition, image, verify) for Apple-silicon Macs. Run on any admin host with ssh to the target and the boot server. Holds the boot server flock for the whole run.
#
#   SERVER=http://<image-server-host>:<port>/<token> bash m6-macos-install.sh --selftest   # lock + server check, NO M6 contact
#   SERVER=... bash m6-macos-install.sh --dry-run                                    # read-only on the M6, partition dry run
#   SERVER=... POWER_GUARD='<arm command>' bash m6-macos-install.sh --go            # partitions, images, verify, power guard
#
# Needs: the M6 booted into Macintosh HD with ssh and passwordless sudo (sudo -n), the Aura stub volume present.
# Never shuts the M6 down. It never changes the boot policy, the boot object or the default startup volume.
set -euo pipefail

mode="${1:---dry-run}"
case "$mode" in --selftest | --dry-run | --go) ;; *) echo "usage: $0 --selftest | --dry-run | --go" >&2; exit 64 ;; esac
: "${SERVER:?SERVER=http://<image server>:<port>/<token>}"
M6="${M6:?M6=ssh alias of the target Mac booted into macOS}"
STUDIO="${STUDIO:?STUDIO=user@boot-server-host (holds the flock + serial client)}"
LOCK="${LOCK:-/tmp/m6.lock}"
here="$(cd "$(dirname "$0")" && pwd)"
fifo="/tmp/m6-install-lock.$$"

mkfifo "$fifo"
(ssh -o BatchMode=yes "$STUDIO" "flock -n $LOCK cat > /dev/null" < "$fifo"; echo "lock holder ended: $?" >&2) &
holder=$!
exec 9> "$fifo"
rm -f "$fifo"
sleep 3
kill -0 "$holder" 2> /dev/null || { echo "ABORT: $LOCK is held by someone else (or the Studio is unreachable)" >&2; exit 1; }
echo "holding $LOCK on the Studio"

curl -fsS -m 10 "$SERVER/sizes" | tee /tmp/m6-install-sizes.txt
awk '$1=="boot.img"{b=$2} $1=="root.img"{r=$2} END{exit !(b==2147483648 && r>=1073741824 && r%4096==0)}' /tmp/m6-install-sizes.txt || { echo "ABORT: unexpected image sizes from the server (boot 2 GiB, root a multiple of 4 KiB)" >&2; exit 1; }
curl -fsS -m 10 "$SERVER/SHA256SUMS"
if [ "$mode" = "--selftest" ]; then
    echo "SELFTEST OK: lock held, server answers. The M6 was not contacted."
    exit 0
fi

m6() { ssh -o BatchMode=yes -o ConnectTimeout=10 "$M6" "$@"; }

echo "--- M6 state (read-only)"
m6 'sw_vers -productVersion; sw_vers -buildVersion; uname -m; bless --getBoot; sudo -n true && echo sudo-ok'
vol="$(m6 "diskutil info -plist / | plutil -extract VolumeName raw -o - -")"
[ "$vol" = "Macintosh HD" ] || { echo "ABORT: booted volume is '$vol', not Macintosh HD" >&2; exit 1; }

after=""
for name in "Aura - Data" "Aura"; do
    after="$(m6 "diskutil info -plist '$name' 2> /dev/null | plutil -extract APFSPhysicalStores.0.APFSPhysicalStore raw -o - - 2> /dev/null" || true)"
    [ -n "$after" ] && break
done
[ -n "$after" ] || { echo "ABORT: no Aura volume found on the M6" >&2; exit 1; }
echo "Aura stub container: $after"
m6 "diskutil list /dev/disk0"

scp -q "$here/m6-partition-write.sh" "$M6:/tmp/m6-partition-write.sh"
run() { m6 "sudo -n env SERVER='$SERVER' AFTER='$after' $1 bash /tmp/m6-partition-write.sh $2"; }

echo "--- partition dry run"
run "" --dry-run
if [ "$mode" = "--dry-run" ]; then
    echo "DRY RUN OK. Nothing changed on the M6."
    exit 0
fi

echo "--- partition, write and verify"
run "REVIEWED='$after'" --go

if [ -n "${POWER_GUARD:-}" ]; then
    echo "--- power guard"
    m6 "$POWER_GUARD"
    m6 'pmset -g | grep -E "autorestart"; pmset -g sched'
fi
echo "DONE. The M6 is still in macOS. Reboot (never shut down) when told to."
