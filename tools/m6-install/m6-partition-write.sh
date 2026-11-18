#!/bin/bash
# Create the three Omarchy partitions after the Aura stub and write the image into them.
# Runs on the M6 in macOS or recoveryOS Terminal (bash 3.2, diskutil, plutil, curl, dd, newfs_msdos, tar, awk; shasum or sha256sum).
# Nothing here changes the boot object, the boot policy or the stub. It only adds partitions after AFTER.
#
#   SERVER=http://<image-server-host>:<port>/<token> AFTER=disk0s3 sh m6-partition-write.sh --dry-run
#   SERVER=... AFTER=disk0s3 REVIEWED=disk0s3 sh m6-partition-write.sh --go
#
# Layout (from the image's installer metadata): ESP FAT32 500 MiB (volume id 0x4f4d5801), Boot 2 GiB (ext4, label OMARCHY_BOOT),
# Root btrfs (label OMARCHY_ROOT; the shipped UUID is 4f4d5801-524f-4f54-8000-000000000001, but serve the overlay r7 root image,
# which has its own random UUID: a fixed one collides with any install stick). Root is ROOT_BYTES; the image is 13.6 GB and grows after first boot.
set -euo pipefail
if command -v shasum > /dev/null 2>&1; then
    sha() { shasum -a 256 | awk '{print $1}'; }
elif command -v sha256sum > /dev/null 2>&1; then
    sha() { sha256sum | awk '{print $1}'; }
else
    echo "ABORT: neither shasum nor sha256sum (nothing changed)" >&2
    exit 1
fi

# Fetch the ESP tar with the same expected-hash discipline as the images: the server
# announces esp.sha, the fetched bytes must match before anything is unpacked.
esp_install() {
    local mnt="$1" want got tmp="/tmp/m6-esp.tar"
    want="$(curl -fsS "$SERVER/esp.sha")" || return 1
    curl -fsS "$SERVER/esp.tar" -o "$tmp" || return 1
    got="$(sha < "$tmp")"
    [ "$got" = "$want" ] || { echo "ABORT: esp.tar sha256 $got, want $want" >&2; return 1; }
    tar -x -f "$tmp" -C "$mnt"
    rm -f "$tmp"
}

# Source-safe exit for test-esp-verify.sh; only takes effect when the file is sourced.
case "${M6_TEST_ONLY:-}" in 1) return 0 2>/dev/null || exit 0 ;; esac

for t in diskutil plutil curl dd newfs_msdos tar awk head; do
    command -v "$t" > /dev/null 2>&1 || { echo "ABORT: $t is missing in this environment (nothing changed)" >&2; exit 1; }
done

mode="${1:-}"
[ "$mode" = "--dry-run" ] || [ "$mode" = "--go" ] || { echo "usage: $0 --dry-run | --go" >&2; exit 64; }
: "${SERVER:?SERVER=http://host:port/token}"
: "${AFTER:?AFTER=disk0s3 (the Aura stub container, the partition the new ones follow)}"
DISK="${DISK:-disk0}"
ESP_BYTES="${ESP_BYTES:-524288000}"
BOOT_BYTES="${BOOT_BYTES:-2147483648}"
ROOT_BYTES="${ROOT_BYTES:-206158430208}"
MIB=1048576
SLACK=$((8 * MIB))

case "$AFTER" in "$DISK"s[0-9]*) ;; *) echo "ABORT: AFTER must look like ${DISK}sN" >&2; exit 1 ;; esac
[ $((ROOT_BYTES % MIB)) -eq 0 ] || { echo "ABORT: ROOT_BYTES must be a multiple of 1 MiB" >&2; exit 1; }

order() {
    diskutil list -plist "$DISK" | plutil -convert json -o - - \
        | sed 's/.*"AllDisksAndPartitions"//' | grep -o "\"${DISK}s[0-9]*\"" | tr -d '"' | awk '!seen[$0]++'
}
after_id() { order | awk -v a="$1" 'f{print; exit} $0==a{f=1}'; }
pinfo() { diskutil info -plist "$1" | plutil -extract "$2" raw -o - -; }

ids="$(order)"
echo "partition order on $DISK: $(echo "$ids" | tr '\n' ' ')"
echo "$ids" | grep -qx "$AFTER" || { echo "ABORT: $AFTER is not on $DISK" >&2; exit 1; }
content="$(pinfo "$AFTER" Content)"
[ "$content" = "Apple_APFS" ] || { echo "ABORT: $AFTER is $content, not an APFS container" >&2; exit 1; }
start=$(( $(pinfo "$AFTER" PartitionMapPartitionOffset) + $(pinfo "$AFTER" Size) ))
next="$(after_id "$AFTER" || true)"
if [ -n "$next" ]; then
    limit="$(pinfo "$next" PartitionMapPartitionOffset)"
    echo "next partition after $AFTER: $next at $limit"
else
    limit="$(pinfo "$DISK" TotalSize)"
    echo "$AFTER is the last partition; disk size $limit"
fi
free=$((limit - start))
need=$((ESP_BYTES + BOOT_BYTES + ROOT_BYTES + SLACK))
echo "free after $AFTER: $free bytes; need $need (ESP $ESP_BYTES + Boot $BOOT_BYTES + Root $ROOT_BYTES + slack $SLACK)"
[ "$free" -ge "$need" ] || { echo "ABORT: not enough free space after $AFTER" >&2; exit 1; }

curl -fsS "$SERVER/SHA256SUMS" > /tmp/m6-sums.txt
root_sha="$(awk '$2=="root.img"{print $1}' /tmp/m6-sums.txt)"
boot_sha="$(awk '$2=="boot.img"{print $1}' /tmp/m6-sums.txt)"
if [ ${#root_sha} -ne 64 ] || [ ${#boot_sha} -ne 64 ]; then echo "ABORT: no hashes from the server" >&2; exit 1; fi

if [ "$mode" = "--dry-run" ]; then
    cat <<EOF
DRY RUN. Would run:
  diskutil addPartition $AFTER %EFI% %noformat% $ESP_BYTES
  diskutil addPartition <new ESP> %Linux% %noformat% $BOOT_BYTES
  diskutil addPartition <new Boot> %Linux% %noformat% $ROOT_BYTES
  newfs_msdos -F 32 -v OMARCHY-EFI -I 0x4f4d5801 /dev/r<ESP>
  curl $SERVER/boot.img | dd of=/dev/r<Boot> bs=4m   (sha256 must be $boot_sha)
  curl $SERVER/root.img | dd of=/dev/r<Root> bs=4m   (sha256 must be $root_sha)
  curl $SERVER/esp.tar | tar -x -C <ESP mount>   (esp.tar hash-checked against $SERVER/esp.sha before unpacking); remove aurora/stage1-j700.bin and m1n1/boot-j700.bin
Nothing changed.
EOF
    exit 0
fi

[ "${REVIEWED:-}" = "$AFTER" ] || { echo "ABORT: set REVIEWED=$AFTER after reading the dry run" >&2; exit 1; }

add() {
    local after="$1" type="$2" size="$3" new
    diskutil addPartition "$after" "$type" %noformat% "$size"
    new="$(after_id "$after")"
    [ -n "$new" ] || { echo "ABORT: cannot find the partition after $after" >&2; exit 1; }
    echo "$new"
}
esp="$(add "$AFTER" %EFI% "$ESP_BYTES" | tail -1)"
boot="$(add "$esp" %Linux% "$BOOT_BYTES" | tail -1)"
root="$(add "$boot" %Linux% "$ROOT_BYTES" | tail -1)"
echo "created ESP=$esp Boot=$boot Root=$root"

newfs_msdos -F 32 -v OMARCHY-EFI -I 0x4f4d5801 "/dev/r$esp"

stream() {
    local name="$1" dev="$2" want="$3" got
    rm -f "/tmp/m6-$name.sha"
    curl -fsS "$SERVER/$name" | tee >(sha > "/tmp/m6-$name.sha") | dd of="/dev/r$dev" bs=4m
    tries=0
    while [ ! -s "/tmp/m6-$name.sha" ] && [ "$tries" -lt 120 ]; do tries=$((tries + 1)); sleep 1; done
    got="$(cat "/tmp/m6-$name.sha")"
    [ "$got" = "$want" ] || { echo "ABORT: $name sha256 $got, want $want" >&2; exit 1; }
    echo "$name written to $dev, stream sha256 ok"
    if [ "${VERIFY:-1}" = "1" ]; then
        local size back
        size="$(curl -fsS "$SERVER/sizes" | awk -v n="$name" '$1==n{print $2}')"
        set +o pipefail
        back="$(dd if="/dev/r$dev" bs=1m 2>/dev/null | head -c "$size" | sha)"
        set -o pipefail
        [ "$back" = "$want" ] || { echo "ABORT: $name readback sha256 $back, want $want" >&2; exit 1; }
        echo "$name readback from $dev ok ($size bytes)"
    fi
}
stream boot.img "$boot" "$boot_sha"
stream root.img "$root" "$root_sha"

diskutil mount "$esp"
mnt="$(diskutil info -plist "$esp" | plutil -extract MountPoint raw -o - -)"
esp_install "$mnt"
rm -f "$mnt/aurora/stage1-j700.bin" "$mnt/m1n1/boot-j700.bin"
# Without this file the image's initramfs encrypts the root in place on first boot (omarchy-mac-encrypt: absent or encrypt=1).
mkdir -p "$mnt/omarchy"
printf 'format=1\nencrypt=0\nlane=edge\n' > "$mnt/omarchy/install.conf"
[ "$(cat "$mnt/omarchy/install.conf")" = "$(printf 'format=1\nencrypt=0\nlane=edge')" ] || { echo "ABORT: install.conf not written" >&2; exit 1; }
diskutil unmount "$esp"

for p in "$esp" "$boot" "$root"; do
    echo "$p PARTUUID $(pinfo "$p" DiskUUID) size $(pinfo "$p" Size)"
done
echo "DONE: partitions written. Boot object not changed."
