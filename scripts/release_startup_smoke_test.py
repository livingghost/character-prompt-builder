#!/usr/bin/env python3
"""A declared release file is one a release archive can actually carry.

`git archive` drops whatever `.gitattributes` marks `export-ignore`, so a path
that is both an export-ignore and a release include cannot exist in any archive
the repository produces. Presence was also checked while the metadata module was
imported, which made every command a completeness check: the first command a
reader ran, `--help`, died on the absent file. The check now belongs to the
callers that are about a release.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from package_metadata import load_package_metadata, verify_release_includes_present  # noqa: E402


def export_ignored(root: Path) -> set[str]:
    attributes = root / ".gitattributes"
    found: set[str] = set()
    if attributes.is_file():
        for line in attributes.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 2 and "export-ignore" in parts[1:]:
                found.add(parts[0].rstrip("/"))
    return found


def main() -> int:
    errors: list[str] = []
    metadata = load_package_metadata(ROOT)

    ignored = export_ignored(ROOT)
    collide = sorted(set(metadata.release_include) & ignored)
    if collide:
        errors.append(
            "release includes are marked export-ignore and cannot appear in an archive: "
            f"{collide}"
        )

    # The command a reader runs first starts, whatever the release tree holds.
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "catalog_cli.py"), "--help"],
        text=True, capture_output=True, check=False,
    )
    help_ok = proc.returncode == 0 and "usage:" in proc.stdout
    if not help_ok:
        errors.append(f"catalog_cli.py --help failed: {proc.returncode} {proc.stderr[:200]}")

    # The release check itself still refuses an absent file.
    gate_refuses = False
    try:
        verify_release_includes_present(ROOT, (PurePosixPath("release-include-that-does-not-exist"),))
    except ValueError as error:
        gate_refuses = "release include is missing" in str(error)
    if not gate_refuses:
        errors.append("the release presence check accepted a file that does not exist")

    report = {
        "ok": not errors,
        "errors": errors,
        "stats": {
            "release_includes": len(metadata.release_include),
            "export_ignored_paths": sorted(ignored),
            "help_starts": help_ok,
            "release_check_still_refuses": gate_refuses,
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
