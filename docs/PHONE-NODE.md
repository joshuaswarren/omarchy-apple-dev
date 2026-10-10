# Phone-node app (parked)

Idea: a small SwiftUI app on the phone that runs probes and posts the results to a receiver on the tailnet,
delivered by TestFlight with no cable and no Mac.

Parked on 2026-10-10. The cable-free route in [OVER-TAILNET.md](OVER-TAILNET.md) reaches the phone from outside, so no
app has to be opened on the phone.

Limits that made the app a weaker answer:

- iOS suspends a backgrounded app. It listens on its own tailnet address only while it is in the foreground, and
  background wake-ups are throttled and not on demand.
- An app cannot screenshot other apps, attach a debugger, or install other builds.
- Someone has to open it on the phone.

What it would still add: probe runs on a phone that is away from every paired host, and on-device GPU timing that
the app itself measures. Build it only if the RemotePairing route fails on the road.
