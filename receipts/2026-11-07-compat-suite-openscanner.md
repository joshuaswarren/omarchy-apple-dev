# openscanner compatibility run

Project: https://github.com/pencilresearch/OpenScanner at 6336c2cba1cac759f3f14bc306b4569ac6bfe494 (MIT).

| stage | result | seconds | exit | first error |
|---|---|---|---|---|
| adapt | PASS | 0 | 0 |  |
| compile | FAIL | 0 | 1 | error: 'omarchy-xtool': multiple resources named 'Assets.xcassets' in target 'ScannerWidgetExtension' |
| package | BLOCKED |  |  | an earlier stage failed |
| sign | BLOCKED |  |  | an earlier stage failed |
| install | NEEDS-DEVICE |  |  |  |
| launch | NEEDS-DEVICE |  |  |  |
| test | NEEDS-DEVICE |  |  | no host test command; the XCTest bundle needs an iOS runtime |
| archive | BLOCKED |  |  | an earlier stage failed |

Commands:

- adapt: `python3 "$OMARCHY_APPLE_DEV/tools/xcodeproj2xtool.py" openscanner.xcodeproj`
- compile: `cd omarchy-xtool && ulimit -n 65536 && xtool dev build`
- package: `cd omarchy-xtool && "$OMARCHY_APPLE_DEV/ship.sh"`
- sign: `cd omarchy-xtool && "$OMARCHY_APPLE_DEV/ship.sh"`
- archive: `cd omarchy-xtool && "$OMARCHY_APPLE_DEV/ship.sh"`

USB state read from sysfs: 8 device(s), 0 Apple (vendor 05ac).
The sysfs list is the evidence. idevice_id needs usbmuxd and fails without it.

```
1-1 0d8c:0022
2-4 0bda:8156
usb1 1d6b:0002
usb2 1d6b:0003
usb3 1d6b:0002
usb4 1d6b:0003
usb5 1d6b:0002
usb6 1d6b:0003
idevice_id -l: rc=255 ERROR: Unable to retrieve device list!
```
