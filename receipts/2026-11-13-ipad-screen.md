# iPad screen validation

Historical validation used a USB host and a viewing host. Site identifiers have been removed. Current automated validation uses stubs, without a device or network configuration changes. Physical interaction and the alternative publication design require separate maintainer decisions.

Review fixes add fail-closed HTTP authentication verification, bounded
pymobiledevice3 upgrades, explicit optional installation, early process identity
publication, reusable bind probing, and service hardening. Seventeen focused
tests cover authentication acceptance/rejection and termination, version bounds
and upgrade requirements, worker arguments and in-memory password defaults,
startup state, private files, installation, menu, and shell forwarding.
No physical device or alternative publication configuration was exercised.
