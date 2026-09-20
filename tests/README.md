# Smoke-suite pytest bridge

Discovers every `scripts/*smoke_test.py` suite and the reference-runtime CLI
contract suite, runs each as a subprocess from the repository root, and asserts
exit code 0. New suites are included automatically. An inventory test rejects
duplicate registrations and stale invocation or slow-marker overrides.

This directory is intentionally outside the release inventory: never add
it to package-manifest.toml and never move these files under scripts/.

Usage (from the repository root, sequential only; xdist is unsupported
because suites configure global pack runtime state):

    python -m pytest tests/              # everything
    python -m pytest tests/ -m "not slow"  # quick lane

validate.py and package.py remain the integrator's gates and are not run
by this bridge.
