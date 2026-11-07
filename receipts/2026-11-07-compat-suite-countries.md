# clean-architecture-swiftui compatibility run

Project: https://github.com/nalexn/clean-architecture-swiftui at 9eca97b8cfff96a14084b564b1fefd949c93d232 (MIT).

| stage | result | seconds | exit | first error |
|---|---|---|---|---|
| adapt | PASS | 0 | 0 |  |
| compile | PASS | 10 | 0 |  |
| package | FAIL | 10 | 133 | Swift/ErrorType.swift:254: Fatal error: Error raised at top level: AppIcon 'AppIcon' declares size 1024x1024 but no source file matched |
| sign | BLOCKED | 10 | 133 |  |
| install | NEEDS-DEVICE |  |  |  |
| launch | NEEDS-DEVICE |  |  |  |
| test | NEEDS-DEVICE |  |  | no host test command; the XCTest bundle needs an iOS runtime |
| archive | BLOCKED | 10 | 133 |  |

Commands:

- adapt: `python3 "$OMARCHY_APPLE_DEV/tools/xcodeproj2xtool.py" CountriesSwiftUI.xcodeproj`
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
