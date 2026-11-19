"""Product identity and release-value syntax shared by runtime and maintenance.

These values describe the product contract. Release validation acquires the
package declaration and dependency artifacts in package_metadata.
"""
from __future__ import annotations

from datetime import date
import re


PACKAGE_NAME = "character-prompt-builder"
CALVER_RE = re.compile(
    r"^([0-9]{4})\.(0[1-9]|1[0-2])\.(0[1-9]|[12][0-9]|3[01])\.([1-9][0-9]*)$"
)


def calver_key(value: object, *, field: str = "CalVer") -> tuple[int, int, int, int]:
    """Parse one canonical UTC Gregorian ``YYYY.MM.DD.N`` release value."""

    if not isinstance(value, str):
        raise ValueError(
            f"{field} must use canonical UTC Gregorian CalVer YYYY.MM.DD.N: {value!r}"
        )
    match = CALVER_RE.fullmatch(value)
    if not match:
        raise ValueError(
            f"{field} must use canonical UTC Gregorian CalVer YYYY.MM.DD.N "
            f"with N starting at 1: {value!r}"
        )
    year, month, day, revision = (int(part) for part in match.groups())
    try:
        date(year, month, day)
    except ValueError as exc:
        raise ValueError(f"{field} contains an invalid Gregorian date: {value!r}") from exc
    return year, month, day, revision


def pep440_version_for_calver(value: object, *, field: str = "CalVer") -> str:
    """Return the one normalized PEP 440 spelling of a core CalVer release."""

    return ".".join(str(part) for part in calver_key(value, field=field))
