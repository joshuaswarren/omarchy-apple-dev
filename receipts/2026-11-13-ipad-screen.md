# iPad screen over Tailscale — 2026-11-13

Tested from a Mac via SSH to Surface (Arch/Omarchy, user `developer`) with a
USB iPad12,1 running iPadOS 27.0.1. No app builds ran on Surface. No sudo,
pacman, reboots, Tailscale changes or network-service changes were used.
The pre-existing untracked `tools/ipad-install-only.sh` was preserved.

- Upgraded existing user pipx pymobiledevice3 11.33.1 to 11.55.0, then the
  installer venv `~/pymobile3-venv` 11.33.0 to 11.55.0 via `start --upgrade`.
  The wrapper selects the installer venv first; both upgrades stayed in user
  Python environments.
- Developer Mode check returned true. `mounter auto-mount` confirmed the DDI
  was already present. The viewer used the rootless userspace tunnel.
- `start`, `status`, duplicate-start rejection, `stop`, and restart passed.
  `ss` confirmed a listener only on Surface's Tailscale IPv4, port 8080.
- An HTTPS request from the Mac to `https://100.114.95.95:8080/` without a
  password returned 401. On Surface, missing/wrong credentials returned 401
  for `/`, `/codec`, `/stream.bin`, `/touch`, `/button`, and `/key`.
- With the generated password loaded directly from the private file in memory,
  `/`, `/codec`, and `/stream.bin` returned 200 and nonempty data. Live video
  bytes were received. No password was printed or placed in argv/environment.
- Checked that the password was absent from the viewer's `/proc` argv,
  environment, and captured log. Password and log modes were 0600.
- Installed command symlink, application menu entry, and user unit template
  using the mirror-only `install` command. `systemd-analyze --user verify`
  passed; `systemctl --user is-enabled` reported disabled. No unit was started
  or enabled. Interactive menu selection was not exercised.
- Final state: viewer stopped, port 8080 no longer listening. The generated
  password remains only in Surface's private config file for subsequent use.

Local validation: eight security unit tests passed; shell syntax, Python
compilation, and diff whitespace checks passed. `tests/install-mode.sh` passed.
`tests/install-venv/run.sh` fails on this Mac's `/var` versus `/private/var`
temporary-path handling on both upstream/main and this branch. All its checks
passed on Surface against the changed installer using stub interpreters and
pip (no actual install/build).

Independent read-only review found one small deadline mismatch; increased the
outer startup timeout to cover both device-check deadlines plus overhead.

Not tested: interactive browser HEVC decoding, authenticated taps/swipes,
keyboard/buttons, audio/clipboard, camera-in-use handling, an actual missing
DDI download/mount, and user-service startup. No physical trust/Developer Mode
prompt was needed. Future browser use requires accepting the known host's
self-signed certificate and entering the password through a private channel.
