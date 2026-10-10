# TestFlight week: ASC records for RNProbe and the SwiftUI demo (draft)

Draft for the lead to execute; not executed yet. Written 2026-10-10 from read-only
App Store Connect API checks on the Linux build host. No browser work was done from
here. Mechanics: `sdk-free/asc-app-records.md` (click-by-click) and
`sdk-free/ship.sh` (stamp, sign, validate, upload).

## Observed ASC state on 2026-10-10 (read-only API)

- App records exist for 8 apps; none for `com.joshuawarren.omarchyappledev.rnprobe`
  or `dev.omarchy.nosdk.swiftui` (`GET /v1/apps?filter[bundleId]=...` is empty for
  both). Both records must be created.
- Both bundle ids are already registered, so the New App bundle dropdown will list
  them right away: `com.joshuawarren.omarchyappledev.rnprobe` (portal bundle id
  `979927FPFA`) and `dev.omarchy.nosdk.swiftui` (portal bundle id `QXAR6DC673`).
- No beta groups exist anywhere (`GET /v1/betaGroups` is empty, and empty per app on
  the counter record `6821068345`), so the internal group is created fresh.

## Who does what

- Lead, records: create the two app records and the internal group in the App Store
  Connect web UI from the signed-in Mac browser session, following
  `sdk-free/asc-app-records.md`.
- Lead, uploads: stage each app into the ship.sh layout
  (`<app dir>/build/ios-sdkfree/release/` holding the app bundle), then run
  `sdk-free/ship.sh --upload <app dir>` (week-plan item 2,
  receipts/2026-10-10-testing-without-the-phone-plan.md).
- Values:
  - RNProbe: record name "Omarchy RNProbe", SKU `RNPROBE01`, bundle
    `com.joshuawarren.omarchyappledev.rnprobe`, version 1.0.0, build number = the
    ship.sh default (UTC `yyyymmddHHMM`; `BUILD_NUMBER` overrides, must strictly
    increase per upload).
  - SwiftUI demo: record name "Omarchy NoSDK SwiftUI", SKU `NOSDKSUI01`, bundle
    `dev.omarchy.nosdk.swiftui`, version 1.0.0, build number = the ship.sh default.
  - Internal group: `Omarchy Internal`, created once per app, testers are the team's
    own App Store Connect accounts.
- Expected screens: Apps list, New App icon button, "New App" menu item, dialog with
  name / English (U.S.) / bundle dropdown / SKU / iOS checkbox / "Full Access" radio
  (Create stays disabled until every field is set), then the app's TestFlight tab
  with the group creation and tester add. The dialog controls need real input clicks,
  not synthetic DOM events (see receipts/2026-10-09-no-xcode-testflight.md).

## Scope guard

Internal TestFlight only: no App Store submission, no "Add for Review", no external
testers, no pricing or agreement steps. Stop when each build reaches TestFlight with
`processingState VALID` and shows up for the internal tester.

## Results (lead fills in)

- [ ] RNProbe record created — record id ______
- [ ] SwiftUI demo record created — record id ______
- [ ] `Omarchy Internal` group created on both apps, tester added
- [ ] RNProbe upload: buildUpload ______, state ______, TestFlight ______
- [ ] SwiftUI demo upload: buildUpload ______, state ______, TestFlight ______
