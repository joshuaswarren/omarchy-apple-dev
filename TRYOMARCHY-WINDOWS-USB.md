# iPhone USB for Try Omarchy on Windows

> [!IMPORTANT]
> This guide applies only when Omarchy is running inside the Windows virtual
> machine distributed by [tryomarchy.com](https://tryomarchy.com). It is not
> needed for a bare-metal Omarchy installation.

Complete the main repository setup before following this guide. The steps below
solve the two VM-specific USB problems that otherwise prevent reliable iPhone
deployment.

## Why the VM needs extra setup

There are two separate issues:

1. **USB passthrough:** Direct QEMU USB passthrough may make the iPhone appear in
   `lsusb`, but it does not provide a connection that `usbmuxd` can reliably use.
   The working transport is `usbipd-win` on the Windows host plus `usbip` in the
   Omarchy guest.
2. **Large app transfers:** Small apps can install over USB/IP while larger
   installs stop after connecting. In the observed failure, `usbmuxd` received a
   device-side error reporting a 65,536-byte message against a 65,535-byte
   maximum. The same behavior has been reported to both
   [usbmuxd](https://github.com/libimobiledevice/usbmuxd/issues/247) and
   [usbipd-win](https://github.com/dorssel/usbipd-win/issues/959). Its exact
   origin remains unresolved; the workaround used here aligns `usbmuxd`'s mux
   and connection-buffer limits at 65,535 bytes.

Both parts are required for a complete setup.

## 1. Share the iPhone from Windows

Open **PowerShell as Administrator** and install
[usbipd-win](https://github.com/dorssel/usbipd-win):

```powershell
winget install --id dorssel.usbipd-win
```

Connect and unlock the iPhone, then find its `BUSID`:

```powershell
usbipd list
```

Share it, replacing `<BUSID>` with the value shown for the iPhone:

```powershell
usbipd bind --busid <BUSID> --force
```

The `--force` option is required on Try Omarchy hosts that have the incompatible
UsbDk filter installed. Sharing normally persists across restarts. Start Try
Omarchy normally; do not also attach the iPhone through a QEMU USB option.

## 2. Install USB/IP in Omarchy

In the Omarchy VM, install the guest tools and load the virtual USB controller:

```bash
sudo pacman -S --needed usbip
sudo modprobe vhci-hcd
```

List the devices exported by Windows:

```bash
usbip list -r 10.0.2.2
```

Attach the iPhone using the `BUSID` shown in that output:

```bash
sudo usbip attach -r 10.0.2.2 -b <BUSID>
```

Keep the iPhone unlocked. Tap **Trust** and enter the passcode if iOS asks
whether to trust the computer.

## 3. Install the USB/IP-safe usbmuxd

This repository includes two patches for `usbmuxd` 1.1.1:

- [Arch Linux's `libplist` compatibility patch](https://gitlab.archlinux.org/archlinux/packaging/packages/usbmuxd/-/blob/main/libplist-2.3.0.diff),
  required to compile 1.1.1 against the current `libplist` API
- the USB/IP transfer workaround described above

The transfer patch reduces the 65,536-byte `DEV_MRU` and `CONN_OUTBUF_SIZE`
limits by one byte and sets `USB_MTU` to the same ceiling. Upstream 1.1.1's
default `USB_MTU` is 49,152 bytes, so this is not simply an MTU reduction; it is
the configuration used to avoid the observed 65,536-byte failure.

From the root of this repository, install the build dependencies, apply both
patches, build the daemon, and place it alongside the distro-owned binary:

```bash
sudo pacman -S --needed base-devel git libimobiledevice libplist libusb

omarchy_apple_dev_dir="$PWD"
usbmuxd_build_dir="$(mktemp -d)"

git clone --branch 1.1.1 --depth 1 \
  https://github.com/libimobiledevice/usbmuxd.git \
  "$usbmuxd_build_dir/usbmuxd"

cd "$usbmuxd_build_dir/usbmuxd"
patch -p1 < "$omarchy_apple_dev_dir/patches/usbmuxd-libplist-2.3.0.patch"
patch -p1 < "$omarchy_apple_dev_dir/patches/usbmuxd-usbipd-safe.patch"

NOCONFIGURE=1 ./autogen.sh
./configure --prefix=/usr --sysconfdir=/etc --localstatedir=/var --sbindir=/usr/bin
make
make check
sudo install -Dm755 src/usbmuxd /usr/local/sbin/usbmuxd-usbipd-safe
```

Configure systemd to use the patched binary without replacing the package-owned
`/usr/bin/usbmuxd`:

```bash
sudo mkdir -p /etc/systemd/system/usbmuxd.service.d
sudo tee /etc/systemd/system/usbmuxd.service.d/10-usbipd-safe.conf >/dev/null <<'EOF'
[Service]
ExecStart=
ExecStart=/usr/local/sbin/usbmuxd-usbipd-safe --user usbmux --systemd
EOF

sudo systemctl daemon-reload
sudo systemctl restart usbmuxd.service
```

This installation is persistent and only needs to be completed once.

## 4. Pair and verify

Use the `pymobiledevice3` environment created by `install-toolchain.sh`:

```bash
~/pymobile3-venv/bin/pymobiledevice3 usbmux list
~/pymobile3-venv/bin/pymobiledevice3 lockdown pair
~/pymobile3-venv/bin/pymobiledevice3 lockdown info >/dev/null && echo paired
```

`usbmux list` should show the iPhone with `"ConnectionType": "USB"`, and the
last command should print `paired`. Pairing is normally required only once.

You can now deploy from an xtool project with this repository's normal device
workflow:

```bash
/path/to/omarchy-apple-dev/device-run.sh
```

## After restarting Windows or the VM

The Windows share and patched `usbmuxd` installation persist. After starting
Try Omarchy, reconnect the iPhone to the running VM with:

```bash
sudo modprobe vhci-hcd
usbip list -r 10.0.2.2
sudo usbip attach -r 10.0.2.2 -b <BUSID>
sudo systemctl restart usbmuxd.service
```

Use the current iPhone `BUSID` printed by `usbip list`; it can change after a
reboot or when the phone is connected to a different USB port.

## Remove the patched daemon

To return to Omarchy's packaged `usbmuxd`:

```bash
sudo rm /etc/systemd/system/usbmuxd.service.d/10-usbipd-safe.conf
sudo systemctl daemon-reload
sudo systemctl restart usbmuxd.service
```
