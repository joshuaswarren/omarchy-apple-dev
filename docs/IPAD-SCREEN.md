# iPad screen and control

This optional tool mirrors and controls a USB-attached iPad using
pymobiledevice3 >=11.55,<12. It does not build apps.

## Install and start

Use a user-owned Python environment containing the supported upstream version.
Selection: IPAD_SCREEN_PYTHON, ~/pymobile3-venv/bin/python, then the user pipx
pymobiledevice3 environment.

```sh
./tools/ipad-screen.sh install
ipad-screen start --udid YOUR_USB_UDID
ipad-screen status
ipad-screen stop
```

Explicit start --upgrade permits a bounded upgrade in that user environment.
Installation creates the command, menu entry, private directories and disabled
user unit. It also prepares upstream state directories before sandboxing.
It is not part of the toolchain installer.

Developer Mode and USB trust must already be enabled. If prompted, stop and
let the person holding the iPad unlock it, tap Trust, or enable Developer Mode
in Settings > Privacy & Security. No automatic reboot is attempted.
DDI auto-mount uses the rootless userspace USB tunnel.

## Publication and authentication

Upstream binds only to 127.0.0.1, using HTTPS and a private password.
A selected port (8080 by default, change with --port) must be unused in
Tailscale Serve configuration. After loopback authentication is verified, the
wrapper runs tailscale serve --bg --yes --https=PORT with an
https+insecure://127.0.0.1:PORT backend. The self-signed backend certificate
stays on loopback; the published endpoint uses Tailscale's trusted certificate.
Ready requires 401 without credentials and 200 with credentials on both
loopback and the published URL. Authentication transport retries are bounded.
Use the published URL from status. HTTPS and browser HEVC decoding support
are required for video.

A destination address bind alone does not enforce an ingress boundary:
routed LAN traffic can reach addresses on another interface. Loopback plus
Serve keeps the upstream listener off LAN and tailnet interfaces and makes
Tailscale enforce the network access boundary.

The shared password is stored in
~/.config/omarchy-apple-dev/ipad-screen/password with mode 0600, inside a
0700 directory. Any username is accepted. Never paste the password into chat,
URLs, commands, logs or automation arguments. It is passed upstream in memory,
never argv or environment. Stop before rotating the file.

Restrict tag:ipad-viewer on the selected HTTPS port to group:ipad-operators
in the tailnet grants/ACL policy; remove broader rules that permit that port.
The password remains defense in depth. Stop the viewer when finished.

Serve requires existing account permission. If denied, an administrator must
grant the account operator access using tailscale set --operator=<ACCOUNT>.
The wrapper never grants permission or changes preferences itself.
It never uses public publication. Existing mappings on the selected port
are refused. Stop removes only its exact, unchanged mapping, preserving all
other mappings. An externally changed mapping requires manual inspection.
Do not concurrently edit the selected port while starting or stopping.
If the process is forcibly killed or the daemon is unavailable during cleanup,
inspect Serve status and remove only the viewer mapping before restarting.

## Optional user service

After installation, start once without enabling:

```sh
systemctl --user daemon-reload
systemctl --user start ipad-screen@YOUR_USB_UDID.service
systemctl --user stop ipad-screen@YOUR_USB_UDID.service
```

Use the service or manual start, not both. It uses the same lock and Serve
lifecycle. It restarts on failure after five seconds, limited to three attempts
per minute. Filesystem protection permits only private viewer and upstream
state directories. Upstream 11.55 keeps pairing records and its personalized
DDI cache under ~/.pymobiledevice3 when present; otherwise it uses
$XDG_DATA_HOME/pymobiledevice3 (default ~/.local/share/pymobiledevice3).
The optional ~/.cache/pymobiledevice3 path is also allowed. Custom XDG roots
require creating the private directory and a matching ReadWritePaths override.
Lifecycle state and logs live under ~/.local/state/omarchy-apple-dev/ipad-screen.
State is atomically replaced; stop never confirms exit while the lock is held.
