# RNProbe: the abort follows the older JS bundle

2026-10-11 evening (CDT). iPhone 15 Pro Max (iPhone16,2), iOS 27.0.1 (24A446). App: RNProbe, React Native 0.87.1. Install and launch ran from a Linux machine over the tailnet, with `pymobiledevice3 apps install` and `pymobiledevice3 developer dvt launch <bundle id> --stream`. Each launch ran 25 seconds.

This receipt answers the open cause question in `receipts/2026-10-12-rnprobe-stale-bundle.md`, with the limits stated below.

## Phone results

| Build | sha256 (first 16) | Launches | Result |
|---|---|---|---|
| Original ipa from 2026-10-09 | `44bea4269a9bd489` | 3 | All 3 aborted: `RCTEventEmitter.receiveEvent()` not registered. App not running after 25 s. |
| Rebuilt from the current `App.tsx`, no shim | `54d64ea3ae5ce982` | 4 | All 4 running after 25 s. No `RCTFatalException` in stderr. |
| Rebuilt, with a no-op `RCTEventEmitter` shim | `35ef56f29213ddb7` | 1 | Running after 25 s. No fatal. |

With the 7 earlier aborts of the original ipa, that build aborted 10 of 10 launches without a debugger. The same build stayed running for 220 s under LLDB (`receipts/2026-10-12-rnprobe-stale-bundle.md`, debugger run), so the abort is not 11 of 11. The rebuilt builds have not aborted in 5 launches.

The earlier receipt records no ipa hash. The hash `44bea4269a9bd489` of the 2026-10-09 ipa ties to the 7 earlier launches by the file path and the dates only.

## What differs between the builds

- The native files differ only inside the code signature. For each file the differing bytes all lie in the `LC_CODE_SIGNATURE` range, and file sizes are identical. Differing bytes, signature range, and bytes outside it: `RNProbe` 4464, [127440, 145872), 0; `React` 1170, [12089360, 12199952), 0; `ReactNativeDependencies` 4340, [1236864, 1262464), 0; `hermesvm` 1166, [5066176, 5122496), 0.
- `main.jsbundle` differs: 1254057 bytes against 1237259 bytes.
- The plain JS of the original bundle contains `RNCSafeAreaProvider` and `RNCSafeAreaView` (2 matches each). The rebuilt bundles contain neither.
- Time stamps: the original JS bundle was built 2026-10-09 18:30. `App.tsx` was changed at 18:39, to use React Native's own `SafeAreaView`. The ipa was signed at 18:42 and kept the 18:30 bundle.

## Reading

The ipa shipped a bundle built from the old template `App.tsx`. That file used `react-native-safe-area-context`, which has native components this app does not have. Without a debugger, the abort happens on that bundle and not on a bundle built from the current `App.tsx`. The exact mechanism is not proven. My inference is that the missing native component sends a legacy event. The shim is not needed: the rebuild runs without it.

## Not checked

Nobody checked the screen. What the app draws is unknown. The runs in the table did not use a debugger. The lock state of the phone was not recorded.

## Fix for the route

Build the bundle after the last edit of the app source. `rn-js.sh` always runs Metro, so a rebuild with `rn-js.sh` fixes it. Check the bundle time stamp against `App.tsx` before you sign.
