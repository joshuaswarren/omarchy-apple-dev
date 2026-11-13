# iPad screen and control over Tailscale

On the Linux host with the USB iPad, this tool runs pymobiledevice3's iOS 27+
web viewer: video, taps/swipes, keyboard, hardware buttons, audio and clipboard.
It only mirrors/controls; it never builds an app. Build elsewhere and use the
existing install/launch tools for a finished IPA.

## Set up and start

The toolchain installer registers `ipad-screen` in `~/.local/bin` and adds
**iPad screen (Tailscale)** to the application menu. On an existing install,
register just this tool (no toolchain installer or builds):

```sh
./tools/ipad-screen.sh install
ipad-screen start --udid YOUR_USB_UDID --upgrade
ipad-screen status
ipad-screen stop
```

`--upgrade` upgrades pymobiledevice3 to >=11.55 only when needed, using the
selected user venv, never system pip. Selection: `IPAD_SCREEN_PYTHON`, then
`~/pymobile3-venv/bin/python`, then the user pipx pymobiledevice3 environment.
An old version otherwise stops with upgrade instructions. Use `--port 8081`
if 8080 is occupied. The application menu prompts for start/stop/status and UDID.

Developer Mode must already be enabled in Settings > Privacy & Security.
The tool checks it, ensures the DDI with `mounter auto-mount`, and uses an
in-process rootless userspace USB tunnel for the viewer. No tunneld, sudo,
network service changes or reboot are needed. If USB trust, an unlock, or
Developer Mode is required, stop and let the person holding the iPad tap it;
then retry manually. DDI download/mount may take several minutes.

## Open from milcmini, r630s, or another tailnet host

Start on Surface via SSH, then open the URL printed by `status` on the viewing
host, for example `https://100.114.95.95:8080/` or
`https://surface.zeedonk-ostrich.ts.net:8080/` (the name must resolve to Surface's
Tailscale IPv4). Accept pymobiledevice3's ephemeral self-signed certificate
warning for this known host. HTTPS is required for remote WebCodecs video;
a browser/OS with HEVC decoding support is also required. A certificate can
change on each start.

The browser requests HTTP Basic authentication: any username, and the password
from `~/.config/omarchy-apple-dev/ipad-screen/password` **on Surface**. Use an
approved secret channel to enter it; agents must never paste it into chat,
commands, URLs, logs, or browser automation arguments. The wrapper generates
this file with mode 0600 if absent and refuses empty/insecure files. It passes
the password to the upstream CLI in memory, never through argv or environment.
It never prints the password. To rotate, stop, remove the file, and start again.

Anyone with the password and tailnet access to that port controls the iPad.
The listener binds exclusively to the IPv4 returned by `tailscale ip -4`;
there is no LAN/wildcard bind override. Tailnet access rules still apply.
Stop the viewer when finished. Stop mirroring before using the iPad camera or
microphone. Viewer accessibility changes can persist on the device; use its
Reset controls when appropriate.

Private lifecycle state and stage log live under
`~/.local/state/omarchy-apple-dev/ipad-screen/` (0700). Upstream viewer output
is suppressed to prevent credentials appearing in tracebacks. A ready status
means the TCP listener is up; it does not assert that the browser decoded video.

## Optional user service (not enabled by installation)

Installation copies `tools/ipad-screen@.service` to `~/.config/systemd/user/`.
After one successful manual start/stop, optionally run:

```sh
systemctl --user daemon-reload
systemctl --user start ipad-screen@YOUR_USB_UDID.service
systemctl --user status ipad-screen@YOUR_USB_UDID.service
systemctl --user stop ipad-screen@YOUR_USB_UDID.service
```

Use either this service or manual `start`, not both. The unit runs in the
foreground with the same lifetime lock and password requirements. It does not
upgrade Python packages or enable itself. A service started manually exits if
the device disconnects; retry after reconnecting. No lingering is configured.

Upstream references: [screen mirroring](https://doronz88.github.io/pymobiledevice3/latest/guides/screen-mirroring/),
[CLI recipes](https://doronz88.github.io/pymobiledevice3/latest/guides/cli-recipes/).
