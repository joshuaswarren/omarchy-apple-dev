# iPad Pro over Tailscale, built and installed from Linux, no Mac in the path (iPadOS 27.0.1)

2026-10-25. iPad Pro 12.9-inch, 5th generation (iPad13,11), iPadOS 27.0.1. The app is a SwiftUI app built on a Linux
container, signed on Linux, installed over the tailnet by a second Linux laptop. The iPad was on Wi-Fi with the Tailscale
app on; neither Linux host was on its subnet. Same route as `docs/OVER-TAILNET.md` (iPhone, 2026-10-10); this is the
first iPad run.

## Result (read from the tool output)

- `Installation succeed.` from `installation_proxy` at 100 % over the RemotePairing tunnel, to the iPad's Tailscale address.
- Install only: the app was not launched by the script, and no screenshot of the device was taken. Whether the app
  runs correctly on the iPad is not shown by this receipt.
- No Mac was used for the build, the signing, the profile, or the install. A Mac was used elsewhere in the same project (simulator
  renders, a Watch target), not in this path.

## Commands

Build and sign on the Linux container (Swift 6.4, xtool Darwin SDK from Xcode 27.1, `rcodesign` 0.29.0):

```sh
python3 tools/provision-dev.py --bundle-id com.example.App --udid <iPhone-udid> <iPad-udid>   # App Store Connect API key
bash ship.sh                        # SwiftPM build and offline checks
bash tools/sign-dev.sh App.app App.ipa ~/.config/omarchy-apple-dev/development   # rcodesign signing with that profile
```

`tools/provision-dev.py` registers each UDID (platform IOS) and writes one development profile that lists all the devices.
The `--udid` option takes more than one UDID (this change is in the same commit).

One-time pairing, iPad on USB to a Linux laptop (Python 3.14 venv, pymobiledevice3 11.23.0, usbmuxd 1.1.1, idevicepair 1.4.0):

```sh
sudo systemctl start usbmuxd
idevicepair -u <udid> pair                         # tap Trust, enter the passcode on the iPad
pymobiledevice3 lockdown wifi-connections on --udid <udid>
python tools/tailnet-tunnel.py pair                # writes ~/.local/share/pymobiledevice3/remote_<udid>.plist
```

Install over the tailnet (cable out, any network):

```sh
sudo -v
python tools/tailnet-tunnel.py 100.x.y.z --udid <udid> --hold 300     # prints: RSD fd..::1 PORT
pymobiledevice3 apps install App.ipa --rsd fd..::1 PORT
```

`tailnet-tunnel.py` needs `--udid` when the host holds more than one RemotePairing record (here: one iPhone, one iPad).

## What we saw that the iPhone run did not show

- The iPad attached as `05ac:12ab` with the `ipheth` driver bound. `usbmuxd` did not list it until we restarted the
  service; on restart it logged `Changing configuration of device: 1 -> 4` and connected. Start or restart `usbmuxd`
  after the iPad is plugged in.
- `lockdown remotepairing --pair` printed `Waiting user pairing consent` and wrote the record within about two seconds, after the
  `idevicepair` Trust step had been done.
- Developer Mode was already on (`pymobiledevice3 amfi developer-mode-status` printed `true`).
- A tunnel to the iPad's Tailscale address answered `lockdown info` (model, iPadOS version, UDID) while the cable was still in.
  We did not repeat it after unplugging; the iPhone receipt covers the cable-out case.
- Not measured: whether `lockdown wifi-connections on` is needed for the tunnel. We turned it on and did not test without it.
