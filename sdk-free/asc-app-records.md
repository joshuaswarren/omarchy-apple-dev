# App Store Connect app records for the no-xcode TestFlight loop

`sdk-free/ship.sh --upload` needs an App Store Connect app record for the bundle id
before its first upload (`tools/asc.py upload` exits with "no App Store Connect app"
otherwise). The API cannot create app records (the App Manager key gets only
GET/UPDATE on `/v1/apps`), so the record is created once per bundle id in the App
Store Connect web UI. Bundle IDs themselves are API work: `tools/asc.py identity`
registers the bundle id (`POST /v1/bundleIds`) when it creates the App Store profile,
and a registered id then appears in the web UI's bundle dropdown (within about 80 s).

## Records this loop uses

| App | Bundle id | Record name | SKU | Portal bundle id |
|---|---|---|---|---|
| RNProbe (React Native probe) | `com.joshuawarren.omarchyappledev.rnprobe` | Omarchy RNProbe | `RNPROBE01` | `979927FPFA` (registered 2026-10-09) |
| SwiftUI demo (HelloSwiftUI) | `dev.omarchy.nosdk.swiftui` | Omarchy NoSDK SwiftUI | `NOSDKSUI01` | `QXAR6DC673` (registered 2026-10-09) |

Both bundle ids are already registered, so no bundle-id step is needed. The
`dev.omarchy.nosdk.swiftui` form is fine: the dropdown lists any registered App ID,
whatever its domain style. Only if the New App dialog refuses it, register
`com.joshuawarren.omarchyappledev.nosdksui` instead and build the demo with
`BUNDLE_ID=com.joshuawarren.omarchyappledev.nosdksui` — the bundle id in the built
app must match the record.

## Click-by-click (once per bundle id)

Driven from the signed-in Mac browser session the same way as
receipts/2026-10-09-no-xcode-testflight.md. App Store Connect forms ignore synthetic
DOM events; use real input clicks.

1. Load `https://appstoreconnect.apple.com/apps`. Deep URLs render an empty shell;
   always load the root and click in-app links.
2. Click the "New App" button. It is the small icon button with
   `aria-label="New App"`, not the "New App Bundle" menu entry (a dead route).
3. In the menu, click "New App". A dialog opens.
4. Fill the dialog (the Create button stays disabled until every field is set):
   - Name: the record name from the table above.
   - Primary Language: English (U.S.)
   - Bundle ID: pick the bundle id from the dropdown.
   - SKU: the SKU from the table.
   - Platform: check iOS.
   - User Access: select the "Full Access" radio.
5. Click Create. The app page opens with the record id in the URL
   (`/apps/<record id>/...`); copy the record id into the receipt.
6. TestFlight, internal only: open the new app's TestFlight tab, create one internal
   group named `Omarchy Internal`, and add the team's own accounts as internal
   testers. Internal builds need no review. Never use "Add for Review" and never
   enable external testing.

## Verify without the browser

Read-only API check (same account variables as ship.sh; the `.p8` at
`~/.appstoreconnect/private_keys/AuthKey_<ASC_KEY_ID>.p8`):

```sh
python3 - <<'PY'
import sys
sys.path.insert(0, "tools")
import asc
for b in ("com.joshuawarren.omarchyappledev.rnprobe", "dev.omarchy.nosdk.swiftui"):
    apps = asc.call("GET", f"/v1/apps?filter[bundleId]={b}")["data"]
    print(b, "->", [(a["id"], a["attributes"]["name"]) for a in apps] or "MISSING")
PY
```

`ship.sh --upload` refuses to run when the record is missing, so this check is
optional.

## Where the execution receipt goes

receipts/2026-10-10-testflight-week-records.md
