# Smoke-suite pytest bridge

Discovers every `scripts/*smoke_test.py` suite and the reference-runtime CLI
contract suite, runs each as a subprocess from the repository root, and asserts
exit code 0. Each suite gets a scratch home whose pack state enables a missing
pack, and a suite whose output names that pack fails. New suites are included
automatically. An inventory test rejects
duplicate registrations and stale invocation or slow-marker overrides.

This development-only bridge is included in source archives, not release archives.
The release keeps the validation suites under scripts/ for its installed checks.
Install pytest separately when using the bridge; individual suites can also
be executed directly.

Usage (from the repository root, sequential only; xdist is unsupported
because suites configure global pack runtime state):

    python -m pytest tests/              # everything
    python -m pytest tests/ -m "not slow"  # quick lane

validate.py and package.py remain the integrator's gates and are not run
by this bridge.
