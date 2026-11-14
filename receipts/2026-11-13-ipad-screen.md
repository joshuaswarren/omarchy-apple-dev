# iPad screen validation

Historical validation used a USB host and a viewing host. Site identifiers have been removed. Current automated validation uses stubs, without a device or network configuration changes. Physical interaction and the alternative publication design require separate maintainer decisions.

Review fixes add fail-closed HTTP authentication verification, bounded
pymobiledevice3 upgrades, explicit optional installation, early process identity
publication, reusable bind probing, and service hardening. Seventeen focused
tests cover authentication acceptance/rejection and termination, version bounds
and upgrade requirements, worker arguments and in-memory password defaults,
startup state, private files, installation, menu, and shell forwarding.
No physical device or alternative publication configuration was exercised.

Round-two validation used upstream 11.55.0 on a USB-attached iPad:
the installed, disabled user service completed the DDI auto-mount under
ProtectSystem=strict without a read-only-path error, reached verified ready,
and returned HTTP 401 without credentials and 200 with credentials.
The service was then stopped; no listener remained on the viewer port.
No unlock, Trust, or mode prompt was needed. No password was printed.
The service remains installed and disabled.

Round-three publication validation was blocked by existing account permissions:
the scoped Serve request was denied. No operator preferences were changed.
The unit was stopped and remains disabled; the viewer port has no listener.
Recorded Serve JSON before and after both equal the empty configuration.
DDI auto-mount reached the viewer stage, but published-URL authentication
could not be tested. No successful Serve/device publication test is claimed.
