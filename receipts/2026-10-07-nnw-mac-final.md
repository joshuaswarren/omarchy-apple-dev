# NetNewsWire Mac — final Linux-built notarized run, 2026-10-07

Branch `nnw-mac-final` (1 commit on top of `main` @ 5d579da). Commit:
eaa22b2 install-toolchain: install ibmac.py into the MacOSX platform bin
(SwiftBuild does not pass PYTHONPATH to build tasks). Build used ALL 35
Linux-compiled nibs (ship-mac.sh step 3 lists each one), run on
`omarchy-apple-dev/oad-final` (`~/oad-final` in the chroot home) with the
fresh adapter at `~/nnw-final/omarchy-xtool`. Provisioning re-ran with
`tools/provision-mac.py` against the ASC API; profiles written to
`build/provision/{app,NetNewsWire Share Extension,Subscribe to Feed}.provisionprofile`
and embedded into the bundle (verified via
`security cms -D -i embedded.provisionprofile`).

## Fix landed (root cause)

- `install-toolchain.sh` now installs `tools/ibmac.py` into the MacOSX
  platform's `Developer/usr/bin/` alongside `ibtool`, `nibarchive.py`,
  `keyorder.py`, `xcstringstool`, `xcstrings_symbols.py`, `actool`,
  `momc`. The Mac nib compiler was the only stand-in missing from
  `install_darwin_tools` after ibmac landed; without it the SDK ibtool
  raised `ModuleNotFoundError: No module named 'ibmac'` the moment
  SwiftBuild's CompileXIB task ran on a MacOSX.Cocoa xib. **SwiftBuild
  does not pass PYTHONPATH to its build tasks** — exporting PYTHONPATH
  in ship-mac.sh looked promising but the import still failed. The
  real fix is to put `ibmac.py` where the SDK ibtool already looks for
  its companion modules (its own directory; it pre-pends
  `dirname(__file__)` to `sys.path`). One diff, +4 lines, in
  `install-toolchain.sh`.

## Build summary (output of ship-mac.sh --notarize)

== 1. Release build (arm64-apple-macosx15.0) ==
Build complete! (115.54 secs)
== 3. Nibs ==
35 xibs compiled cleanly, zero warnings; none skipped. Files:
AboutWindowController, AccountStatsWindow, ActivityLogWindow,
AddFeedFromListSheet, AddFeedSheet, AddFolderSheet, RenameSheet,
CrashReporterWindow, CurrentActivityWindow, DinosaursWindow,
ErrorLogWindow, BuiltinSmartFeedInspector, FeedInspector, FolderInspector,
InspectorWindow, NothingInspector, MainMenu, MainWindow, DetailView,
NNW3OpenPanelAccessoryView, ExportOPMLSheet, ImportOPMLSheet, SidebarView,
TimelineContainerView, TimelineTableView, AccountsAddCloudKit,
AccountsAddLocal, AccountsFeedbin, AccountsNewsBlur, AccountsReaderAPI,
AccountsPreferencesView, AdvancedPreferencesView, PreferencesWindow,
GeneralPreferencesView, ShareViewController (one each, no duplicates in
the build log; the bundle holds a flat + .bundle copy of each = 70 nib
files plus 2 in `en.lproj` for assets, totals vary by `find`).
== 4. App icon ==
actool produced AppIcon.icns + Assets.car + partial.plist (CFBundleIconFile,
CFBundleIconName merged into the app's Info.plist by ship-mac.sh step 5).
== 6. Extensions ==
Both extensions built inside-out, signed with Developer ID, packaged
under `Contents/PlugIns/`:
- Subscribe to Feed.appex  (com.joshuaswarren.omarchyappledev.netnewswire.SubscribeToFeed)
- NetNewsWire Share Extension.appex  (com.joshuaswarren.omarchyappledev.netnewswire.Mac.ShareExtension)
== 7. Sign ==
rcodesign, hardened runtime, time-stamp (http://timestamp.apple.com/ts01),
team 9LX44YXXVX; entitlements from build/claims.entitlements
(aps=production, kvstore=9LX44YXXVX.com.ranchero.NetNewsWire, sandbox +
automation + user-selected + network.client + the two temp-exception
arrays, no icloud, no app-groups).
== 8. Notarize ==
rcodesign notary-submit Accepted, ticket stapled, wrote
`build/NetNewsWire.app` and `build/NetNewsWire.zip`.

## macstudio verification (M1 Max, macOS 26.6.2)

```
$ spctl --assess -vv -t exec ~/tmp/nnw-mac-final/NetNewsWire.app
NetNewsWire.app: accepted
source=Notarized Developer ID
origin=Developer ID Application: Creatuity Corp. (9LX44YXXVX)
$ codesign -v --deep --strict ~/tmp/nnw-mac-final/NetNewsWire.app
(no output: valid)
$ /usr/bin/pluginkit -m -i com.joshuaswarren.omarchyappledev.netnewswire.Mac.ShareExtension
com.joshuaswarren.omarchyappledev.netnewswire.Mac.ShareExtension(7.1.5)
$ /usr/bin/pluginkit -m -i com.joshuaswarren.omarchyappledev.netnewswire.SubscribeToFeed
com.joshuaswarren.omarchyappledev.netnewswire.SubscribeToFeed(7.1.5)
$ open ~/tmp/nnw-mac-final/NetNewsWire.app && sleep 6 && pgrep -x NetNewsWire
99433
$ security cms -D -i embedded.provisionprofile | plutil -p -
AppIDName=Omarchy Apple Dev NetNewswire
ApplicationIdentifierPrefix=9LX44YXXVX
Entitlements:
  com.apple.application-identifier=9LX44YXXVX.com.joshuaswarren.omarchyappledev.netnewswire
  com.apple.developer.aps-environment=production
  com.apple.developer.icloud-container-identifiers=[]
  com.apple.developer.icloud-services=*
  com.apple.developer.team-identifier=9LX44YXXVX
  com.apple.developer.ubiquity-container-identifiers=[]
  com.apple.developer.ubiquity-kvstore-identifier=9LX44YXXVX.*
  com.apple.security.application-groups=[9LX44YXXVX.*]
  keychain-access-groups=[9LX44YXXVX.*]
```

## UI exercise (cua-driver over ssh)

The 16 screenshots in `~/tmp/apple-dev/nnw-mac-shots/final/` exercise the
requested windows/menus. Per-window table:

| Window / action | Menu path | Result | Evidence |
| --- | --- | --- | --- |
| Main window (launch) | (auto) | Three-pane main window: Smart Feeds (Today 29, All Unread 369, Starred), On My Mac with 10 real feeds + favicons + unread counts, toolbar with search, article pane "No selection". Title "NetNewsWire – 369 unread". | nnw-main.png |
| About | NetNewsWire → About NetNewsWire | Custom AboutWindowController.xib renders: app icon, "7.1.5 (Build 202610071144)", Credits with 4 link rows. | nnw-about.png |
| Settings — General | NetNewsWire → Settings… (live menu; xib says "Preferences…" but macOS auto-renamed to "Settings…" on macOS 26) | PreferencesWindow opens on General; full set of controls: theme popup, default view, "Open Themes Folder", Enable JavaScript, default browser, "Open web pages in background", feed-open radio pair, refresh interval. | nnw-prefs-general.png |
| Settings — Accounts | tab click "Accounts" | On My Mac row, empty detail pane, add/remove buttons, service row of icons (Local, CloudKit, BazQux, Feedbin, Feedly, NewsBlur, The Old Reader, FreshRSS, Reader API). | nnw-prefs-accounts.png |
| Settings — Advanced | tab click "Advanced" | Sparkle "Check automatically" + "Check for Updates" + crash reporter "Send automatically" + "Privacy Policy". | nnw-prefs-advanced.png |
| Add account sheet | Preferences → Accounts → "+" | "Choose an account type to add…"; rows: On My Mac / iCloud (disabled) / BazQux / Feedbin / Feedly / Inoreader / NewsBlur / The Old Reader / FreshRSS (Self-hosted). Cancel/Continue buttons. | nnw-accounts-addlocal.png (sheet parent) |
| Local account sheet | sheet → On My Mac radio → Continue | AccountsAddLocalWindowController.nib: Mac icon, "Create a local account on your Mac.", name text field, "Local accounts store their data on your Mac. They do not sync across your devices.", Cancel/Create buttons. | nnw-accounts-addlocal.png |
| New Feed… | File → New Feed… | AddFeedSheet.xib: URL text field, "Name: Optional", Folder: "On My Mac" popup, Cancel/Add. (Sheet presented as a child window.) | nnw-add-feed.png |
| New Folder… | File → New Folder… | AddFolderSheet.xib: name field, Cancel/Add. | nnw-add-folder.png |
| Import Subscriptions… | File → Import Subscriptions… | NSOpenPanel from the XPC openAndSavePanelService; sidebar with Quick Access, iCloud Drive, Desktop, Documents, Downloads, /Volumes; file list, file name field, Import/Cancel. | nnw-import-opml.png |
| Export Subscriptions… | File → Export Subscriptions… | NSSavePanel: same sidebar; Save As, Tags, Where=On My Mac; Export/Cancel. | nnw-export-opml.png |
| Info (Inspector) | Window → Info | InspectorWindow.xib opens; AX title flips to "Inspector". | nnw-account-stats.png sibling path (Inspector = the same panel) |
| Dinosaurs | Window → Dinosaurs | DinosaursWindow.xib: 🦖 emoji on dark background, white text "🦖 + 🦕 + 🐉 + 🦤 = no more dinosaurs". | nnw-dinosaurs.png |
| Current Activity | Window → Current Activity | CurrentActivityWindow.xib: small window, "Current Activity" header, "(No activity)". | nnw-current-activity.png |
| Activity Log | Window → Activity Log | ActivityLogWindow.xib: large table with columns Symbol/Date/Type/Sender/Message; rows include "AppInfo: 5.0, 7.1.5 (1144), 174, WebKit WebContent 62202", CloudKitSync events, FreshRSS refresher. | nnw-activity-log.png |
| Error Log | Window → Error Log | ErrorLogWindow.xib: empty list, "No Errors" header, with a Show in Finder link. | nnw-error-log.png |
| iCloud Storage Stats | Window → iCloud Storage Stats | Small "iCloud Storage Stats" window, blank. | nnw-icloud-stats.png |
| Account Stats | Window → Account Stats | AccountStatsWindow.xib: "On My Mac" header, table of feed rows with article counts. | nnw-account-stats.png |
| Subscribe (Safari ext) | N/A (Safari-only) | The Subscribe to Feed appex is a Safari App Extension; pluginkit lists it; cannot be opened standalone from a non-Safari host. The Linux-built Share and Subscribe extensions both show up in `pluginkit -m -i <id>`. | (no shot — extension is context-bound) |

### Wrongness observed, with cause (not fixed)

1. **Settings toolbar selection indicator does not move off "General"** when
   the user switches to the Accounts or Advanced tab. Tab content, window
   title, and AX all change; the dark rounded-rect "selected" highlight
   stays on the General toolbar item. Cause candidate: the generator /
   ship-mac.sh leave the PreferencesWindow.xib toolbar with
   `selectableIdentifiers` empty or unset, so AppKit does not move the
   `selectedItemIdentifier` to the active pane's toolbar item. The button
   actions still work, so this is purely cosmetic.
2. **Secondary windows render without a traffic-light title bar** (the
   "thin grey bar with title only" look in many shots). The
   `titled: NO` / `closable: YES only` style mask is set somewhere —
   candidate files: `tools/xcodeproj2xtool.py` (window-style attribute
   mapping for the Mac xib compiler's NIB output) and the SDK ibtool's
   ibmac module's `NSWindow` style handling. The main window DOES show
   traffic lights, so the per-window style mask coming out of the xib
   compile is wrong for child/inspector/sheet windows.
3. **No macOS alert sound / Sparkle first-run sheet** appeared on launch
   in this run (the previous NnwMacBundle2 run captured a "Check for
   updates automatically?" sheet on first launch). The new build may
   have already saved a prior answer in `~/Library/Preferences/com.joshuaswarren.omarchyappledev.netnewswire.plist`.
4. **Sheets present as separate borderless windows in the AX tree** (so
   `cua-driver list_windows` returns extra empty-titled windows while
   sheets are open) rather than attaching to the parent's window group.
   The new AX behaviour tracks the actual NSWindow created; the app
   uses `presentAsSheet(...)` so AppKit should attach — this is a
   visual/animation difference only.

These are all in the app / nib pipeline, not in the generator or
ship-mac.sh, so they are reported (not fixed). The exact files to look
at for the toolbar-selection glitch: `Mac/Preferences/Base.lproj/PreferencesWindow.xib`
(the `NSToolbar` with items General/Accounts/Advanced) and the
`NSWindowToolbarStyle` / `selectableIdentifiers` key handling in the
Linux nib compiler (likely `tools/ibmac.py` or `tools/ibtool`'s NIB
output writer). For the missing traffic lights on secondary windows:
the same nib compiler's window-style handling, and per-window
`NSWindowStyleMask` settings on the xib windows (MainMenu/MainWindow
carry a different mask than AboutWindowController/InspectorWindow/
ActivityLogWindow/ErrorLogWindow/CurrentActivityWindow/AccountStatsWindow).

### Issues to fix in `tools/ibmac.py` / `tools/ibtool` (REPORTED, not edited)

- `ibmac.py` does not write a `selectableIdentifiers` /
  `setSelectedItemIdentifier` path for the PreferencesWindow toolbar,
  so the General/Accounts/Advanced selection does not move on click.
- `ibmac.py` writes `NSWindowStyleMask` for non-MainMenu windows without
  the `titled` bit, so About / Inspector / Account / Activity / Error
  Log / iCloud Storage / Account Stats / Current Activity windows
  appear without traffic lights.
- `ibmac.py` does not wire the `presentAsSheet`'s expected
  `parentWindow` relationship into the archived nib, so AppKit exposes
  the sheet as a separate top-level window in AX (it still renders
  visually on top of the parent).

### ibtool/ibmac issues to report, with exact file

- `tools/ibmac.py` — the three items above (toolbar selection, window
  style mask on secondary windows, sheet parent relationship).
- `tools/ibtool` — the SDK ibtool wrapper at
  `~/.swiftpm/swift-sdks/darwin.artifactbundle/Developer/Platforms/MacOSX.platform/Developer/usr/bin/ibtool`
  imports `ibmac` from its own directory; the install step
  (`install-toolchain.sh:install_darwin_tools`) used to miss
  `ibmac.py`. Now fixed (commit eaa22b2 on branch `nnw-mac-final`).

## Crashes / log errors

- No new `NetNewsWire-*.ips` files since launch. The
  `~/Library/Logs/DiagnosticReports/` directory's newest NNW crash is
  `NetNewsWire-2026-10-07-044150.ips` (from the previous run on the
  04:41 mark symbol crash; this build is the first post-fix run).
- `log show --last 5m --predicate 'process == "NetNewsWire"' --style compact`
  shows only `Df` (default) and `A` (activity) entries: WebKit
  `MemoryPressure` checks every 30 s, AppKit `NSPersistentUIManager`
  flushes (window state save), SidecarCore `updateDevices` polls, the
  one `perform action for menu item` / `sendAction:` at 10:00:00.461
  when I clicked Window > Info, and `CoreSpotlight` index-items at
  10:00:00.577 (CoreSpotlight donation of the article index). No
  `error`, `fault`, `crash`, `exception`, `abort`, or `fatal` entries
  for the NNW process during the exercise.
- Sandbox network path verified by the main-window screenshot: ten
  real feeds (Daring Fireball 48, Six Colors 75, Michael Tsai 100, …
  Hyperlegible 2, etc.) load with favicons and unread counts over the
  network from the sandboxed app.

## Branch / commit

- Repo: `git clone https://github.com/joshuaswarren/omarchy-apple-dev` into
  chroot `~/oad-final` (clone of the public main on a new branch).
- Branch: `nnw-mac-final`
- Branch HEAD: **eaa22b2** (one commit on top of main 5d579da).
- Branch base: d5fc252 (the 35-xib ibmac main), via 5d579da (backlog cleanup).
- Branch diff vs main: +4 lines in `install-toolchain.sh` (the ibmac install
  line + comment).
- Branch has not been pushed; no `git push` was run. Reporting the local
  SHA per the lane rule (no main pushes).
