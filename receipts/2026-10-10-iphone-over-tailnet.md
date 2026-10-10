# iPhone over Tailscale, no cable, no Mac (iOS 27.0.1)

2026-10-10. iPhone 15 Pro Max (iPhone16,2), iOS 27.0.1 (24A446), pymobiledevice3 11.23.0. Two Linux hosts on the
same tailnet as the phone: an M1 Max laptop (Python 3.14) and a build container (Python 3.14 venv). Neither host is on the
phone's subnet. A third Linux laptop on the phone's subnet served only as the control sender in the raw probe.

## Finding

lockdownd (port 62078) resets every connection from an address outside the phone's own subnet, before any reply. The
RemotePairing service the phone advertises (`_remotepairing._tcp`, port 49152 in every run) accepts a paired host from any
routed address, including its Tailscale address. So the route is: pair once over USB, then pair-verify against that port,
open the CoreDevice tunnel, and use the tunnel's RSD address with every `--rsd` command.

| Probe (raw `QueryType` to 62078, no pymobiledevice3) | Result |
|---|---|
| sender on the phone's subnet, to the phone's LAN address | reply |
| sender on another subnet, to the LAN address | connection reset |
| any sender, to the phone's Tailscale address | connection reset |

## One-time pairing

`tools/tailnet-tunnel.py pair` runs `pymobiledevice3 lockdown remotepairing --pair` over USB (no prompt on the phone) and
pins `host_identifier` into the record. Without the pin, pymobiledevice3 derives the host identifier from the machine's
hostname, so a copied record fails on another host with `ConnectionTerminatedError` after the handshake.

## Results

Each run: pair-verify, tunnel, `lockdown info`, `apps list`, launch, screenshot, `syslog live`.

| Phone state | Result |
|---|---|
| USB cable in, Wi-Fi on | pass (tunnel RSD `fd5a:fb60:6ed9::1` port 65002; 948 apps; 799 KB screenshot; 17 s) |
| cable out, Wi-Fi off, cellular + Tailscale | **fail**: ports 49152-49167 refused from both hosts; `tailscale ping` still answers (direct path, 100 ms); scan of ports 1-1024 and 49152-65535 finds one unrelated open port that does not speak RemotePairing |
| cable out, Wi-Fi back on | pass from both hosts, same port 49152, 11 s, 676 KB screenshot |
| cable out, Wi-Fi on, screen locked | pass from both hosts; screenshot shows the passcode screen; launch returned a pid |
| `device-run.sh --over-tailnet` with a signed ipa | pass: installed and launched the app (pid 92541), tunnel closed on exit |

## LLDB over the tailnet tunnel

Cable out, Wi-Fi on, from the M1 Max laptop (Swift 6.4 lldb, no on-disk device sysroot):

- `dvt launch --suspended` returned a pid, `developer debugserver start-server` forwarded to a local port.
- `process connect` and `process attach` worked; the process stopped at `_dyld_start` in dyld.
- `breakpoint set -n main` resolved to `main` in SwiftUIWide1 when the local binary matched the installed build.
- Not reached: the stop at the breakpoint. After `continue`, lldb read system libraries from process memory
  (`libobjc.A.dylib is being read from process memory ... could not find the on-disk shared cache`) and the 150 s
  limit passed first. The repo's USB flow downloads the device's dyld shared cache once per iOS build
  (`developer fetch-symbols download`) to avoid this.
- After every run the app was killed, the forwarder and tunnel were stopped, and `proclist` showed no app or debugserver
  left on the phone.

## Gotchas

- `RemotePairingTunnelService.connect(autopair=False)` must run before `start_tunnel_over_remotepairing`, or
  `create_tcp_listener` asserts `encryption_key is not None`.
- The TCP tunnel needs TLS-PSK ciphers and Python 3.13 or newer. `uv` standalone Python builds fail with
  `NO_CIPHERS_AVAILABLE`; older Pythons fall back to QUIC, which iOS 18.2+ removed.
