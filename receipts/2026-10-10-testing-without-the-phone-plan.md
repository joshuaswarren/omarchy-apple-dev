# Plan: testing iPhone apps from Linux when the phone is not on the cable (2026-10-10)

Question: what can we test for a week with no iPhone plugged into the Linux lab host? This plan lists what was checked
today, what each route can prove, and the order to try them.

## Checked today (observed)

| Check | Result |
|---|---|
| Simulator route on a Mac with Xcode 27.0 (iOS 26.5 runtime, iPhone 17 Pro): `tools/simctl-remote.sh apps/HelloOmarchy` | Works end to end in about 90 s. The app builds in the Linux chroot, the Mac boots the simulator, installs and launches it, and a screenshot comes back (`Hello, world!` with the globe symbol). I shut the simulator down and removed its staging dir afterwards. |
| Host side of wireless pairing on Linux: `pymobiledevice3 remote pair-host` (11.23.0) | Starts, prints the setup steps, and advertises `_remotepairing-pairable-host._tcp`. The phone side is untested because no phone was reachable. |
| Discovery on the lab LAN: `pymobiledevice3 remote browse`, `usbmux list`, `idevice_id -n` | All empty. No iPhone advertises on the lab LAN right now. |
| Tailscale | The lab LAN is reachable from anywhere on the tailnet through a subnet router (the lab subnets). mDNS does not cross it. No iPhone is on the tailnet. |
| iPhone on USB | Not attached. The kernel log shows the cable was pulled at 17:06 CDT on 2026-10-09 (the whole USB host controller of that port went away). |

## 1. iPhone over Wi-Fi

What is known, from `FINDINGS.md` item 17 and `device-run.sh`:

- iOS 26.6.2 refused every wireless path for a Linux host. Each host needs its own RemotePairing tunnel, and the phone only
  creates one for a Mac that was paired through Xcode.
- iOS 27 adds a device-side pairing screen: Settings > Developer > Paired Macs. `pymobiledevice3 remote pair-host`
  (11.12 and later) is the Linux side. The pairing record it creates is then used by `remote start-tunnel` for a wireless
  tunnel. Our phone runs iOS 27.0.1, so this route is open. It is untested on the phone.
- Pairing and the first trust prompt need the phone on USB once.
- The phone must be on the same Wi-Fi network as the Linux host for pairing and for discovery (mDNS stays on the local
  network). Tailscale can carry TCP to the lab subnet, but it cannot carry the mDNS that finds the phone, and the phone's
  own services listen on its Wi-Fi interface. So a phone that travels away from the lab Wi-Fi is out of reach. A phone
  that stays on the lab Wi-Fi is reachable from anywhere on the tailnet through the subnet router once the tunnel exists.

What needs the cable and what can use a network tunnel (inference until the first wireless run):

| Task | Cable | Network tunnel |
|---|---|---|
| First trust and pairing | needed | not possible |
| Developer Mode, DDI mount | cable first | after pairing |
| `apps install`, launch, screenshot, syslog, crash pull | works | works through the RSD tunnel (pymobiledevice3) |
| LLDB attach | works | works through the same tunnel (untested) |
| `xtool dev run` | works | needs network discovery in usbmuxd: not set up |
| Phone locked | install works, launch fails | same |

Steps for the person at the phone before leaving (each one is needed):

1. Plug the iPhone into the Linux lab host, unlock it, tap Trust if asked. Keep it unlocked for about 10 minutes: the
   queued runs (SwiftUIWide1, SwiftUIWide2, RNProbe) start by themselves when the phone appears.
2. Check Settings > Privacy & Security > Developer Mode is on.
3. Join the phone to the lab Wi-Fi that bridges to the lab host's subnet (check that the phone gets an address in
   the same subnet as the host).
4. Settings > Display & Brightness > Auto-Lock: Never, while the phone stays on its charger. A locked phone cannot launch apps.
5. On the host, run `pymobiledevice3 lockdown wifi-connections on`, then `pymobiledevice3 remote pair-host`. On the phone open
   Settings > Developer > Paired Macs, tap the host under Other Devices, and type the 6-digit code that the host prints.
6. Leave the phone on the charger and the cable on the desk. USB stays the first choice; the Wi-Fi tunnel is the backup.

If the phone leaves with its owner, none of this works. An older iPad or iPhone left plugged in on the desk is the cheapest
fix (any device with iOS 17 or later and Developer Mode).

## 2. Simulator

- There is no iOS Simulator on Linux. It needs macOS frameworks.
- Works today: build on Linux, run in the Simulator on a Mac with Xcode over ssh (`tools/simctl-remote.sh`). That Mac has the
  iOS 26.5 runtime. The iOS 27 runtime is not installed (installing it needs an authorized `xcodebuild -downloadPlatform`).
- A Mac partition on a lab laptop is a second host, but it needs a reboot and Xcode was not checked there.
- QEMU projects (xnu-qemu-arm64, QEMUAppleSilicon) boot old research kernels (iOS 12 era, one iPhone 11 target). They do
  not run app UIs. Not useful for app tests.
- A commercial virtual iPhone service exists. It is a paid service; its fit and price were not checked.
- Next experiment: relink one of our no-Xcode apps (the SwiftUI demo) for the simulator slice (platform `ios-simulator`,
  stub targets `arm64-ios-simulator`) and run it in that Simulator. If it works, the hand-written SwiftUI module can be
  checked against a real SwiftUI without the phone.

## 3. Fallback ladder, cheapest first

| Rung | Cost | Can prove | Cannot prove |
|---|---|---|---|
| 1. Compile, link, symbol check against the device stubs, `macho-lint` | free, seconds | the app references only symbols that exist on the device; the binary is well formed | that it runs |
| 2. App Store Connect validation and TestFlight processing (`sdk-free/ship.sh --upload`) | free, about 2 minutes | Apple accepts the binary and signing | runtime behavior |
| 3. Simulator on a Mac with Xcode over ssh | free, 1 to 2 minutes per run | UI logic, layout, app launch, many crashes, Metal API use on the Mac's GPU | real iPhone GPU or ANE numbers, camera, push, iOS 27 behavior |
| 4. TestFlight install on the phone from anywhere | free, owner taps Install | real device run of a release build; crash and feedback reports come back through App Store Connect | debugger, screenshots by us, debug builds |
| 5. Wi-Fi tunnel to a phone left on the lab Wi-Fi | free, needs the one-time setup above | install, launch, screenshot, logs, LLDB on a real device | anything while the phone is away |
| 6. Phone or spare device on the USB cable | free | everything | needs a person once |
| 7. Paid virtual iPhone service | paid | iOS firmware in a VM | real GPU or ANE numbers |

No rung except a real device proves real GPU, Metal performance, or ANE results.

## 4. Work for the week that needs no phone

1. Relink the SwiftUI demo for the simulator and run it on the Mac (rung 3); extend to the wider SwiftUI demos and the
   Flutter and React Native apps. Merge the wider SwiftUI declarations only for what the simulator draws.
2. Add `sdk-free/ship.sh` apps for RNProbe and the SwiftUI demo, create the App Store Connect records, and test the
   TestFlight install loop (rung 4).
3. Write a wireless helper (`phone-net.sh`) that picks the cable or the network tunnel, so the phone runs do not change.
4. Raise the pymobiledevice3 version on the Linux test host to 11.26 or later for the rootless debugger flow.
5. React Native: build the Fabric pod `react-native-safe-area-context`; add the Observation module and `@Observable`
   to the SwiftUI subset; look for a replacement for `NavigationStack` (the iOS 27.0.1 SwiftUI does not export it).
6. Ubuntu container: run the overlays and the Flutter build there.
7. Watch the open xtool pull requests and answer review comments.
