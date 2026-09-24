"""Configuration for the smoke-suite pytest bridge.

The source distribution includes this bridge alongside the suites under
scripts/. Pytest is an optional development runner, not a runtime dependency.

Execution model: every suite is run as a subprocess from the repository
root (python scripts/<name>.py), exactly as validate.py, package.py, and
CI invoke it.  Suites are never imported into the pytest process: they
depend on sys.path[0] == scripts/ and they configure module-global pack
runtime state.  For the same reason the bridge is sequential only;
running it under pytest-xdist or any other parallel runner is
unsupported.
"""

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        'slow: long-running smoke suite; use -m "not slow" for the quick lane',
    )


@pytest.fixture(scope="session")
def repo_root():
    return REPO
