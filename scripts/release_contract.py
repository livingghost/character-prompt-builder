#!/usr/bin/env python3
"""Check product CalVer, dated release notes, and generated distribution identity.

This module concerns the product release only. Scene/state/protocol artifacts
continue to identify their content without independent release counters.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re
import sys
import tomllib
from typing import Any, Mapping

CALVER = re.compile(r"([0-9]{4})\.(0[1-9]|1[0-2])\.(0[1-9]|[12][0-9]|3[01])\.([1-9][0-9]*)", re.ASCII)


def calver_parts(value: object) -> tuple[int, int, int, int]:
    if not isinstance(value, str) or not (match := CALVER.fullmatch(value)):
        raise ValueError("product version must use canonical UTC CalVer YYYY.MM.DD.N with N starting at 1")
    year, month, day, sequence = map(int, match.groups())
    try:
        date(year, month, day)
    except ValueError as exc:
        raise ValueError("product version contains an invalid Gregorian date") from exc
    return year, month, day, sequence


def validate_metadata(manifest: Mapping[str, Any], tag: str | None = None) -> list[str]:
    errors: list[str] = []
    package = manifest.get("package", {})
    release = manifest.get("release", {})
    if not isinstance(package, Mapping) or not isinstance(release, Mapping):
        return ["package and release must be TOML tables"]
    version = package.get("version")
    try:
        calver_parts(version)
    except ValueError as exc:
        errors.append(str(exc))
    if package.get("version_scheme") != "YYYY.MM.DD.N":
        errors.append("package.version_scheme must be YYYY.MM.DD.N")
    if package.get("release_timezone") != "UTC":
        errors.append("package.release_timezone must be UTC")
    name = package.get("name")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        errors.append("package.name must be a canonical product name")
    if release.get("output") != f"dist/{name}-{version}.zip":
        errors.append("release.output must use the canonical product name and CalVer")
    if tag is not None and tag != f"v{version}":
        errors.append("release tag must equal v followed by package.version")
    return errors


def validate_changelog(text: str, version: str, *, style: str) -> list[str]:
    """Check the single current product entry and its substantive release notes."""
    try:
        year, month, day, _ = calver_parts(version)
    except ValueError as exc:
        return [str(exc)]
    if style not in {"plain", "dated"}:
        raise ValueError("unsupported product changelog heading style")
    iso = date(year, month, day).isoformat()
    expected = version if style == "plain" else f"[{version}] - {iso}"
    sections = list(re.finditer(r"(?m)^##[ \t]+([^\r\n]+)[ \t]*$", text))
    if len(sections) != 1:
        return ["CHANGELOG.md must contain one current product release entry"]
    index, heading = 0, sections[0]
    errors = []
    if heading.group(1).strip() != expected:
        errors.append(f"CHANGELOG.md newest release must be ## {expected}")
    end = sections[index + 1].start() if index + 1 < len(sections) else len(text)
    body = text[heading.end():end]
    # A heading-only section is not a release record.
    if not any(line.strip() and not line.lstrip().startswith(("#", "<!--")) for line in body.splitlines()):
        errors.append("CHANGELOG.md current release has no substantive change notes")
    if sum(m.group(1).strip() == expected for m in sections) != 1:
        errors.append("CHANGELOG.md must contain exactly one current release entry")
    return errors


def product_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "package-manifest.toml").is_file():
            return parent
    raise ValueError("package-manifest.toml is not present above the installed script")


def check(root: Path, tag: str | None = None) -> dict[str, Any]:
    root = root.resolve()
    try:
        with (root / "package-manifest.toml").open("rb") as stream:
            manifest = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return {"ok": False, "errors": [f"cannot read package-manifest.toml: {exc}"]}
    errors = validate_metadata(manifest, tag)
    package = manifest.get("package", {})
    if not isinstance(package, dict):
        return {"ok": False, "errors": errors}
    version = package.get("version", "")
    # The package layout selects the declared changelog heading style.
    style = "dated" if isinstance(manifest.get("hosts"), dict) and manifest["hosts"].get("suite_root") else "plain"
    try:
        errors.extend(validate_changelog((root / "CHANGELOG.md").read_text(encoding="utf-8"), version, style=style))
    except (OSError, UnicodeError) as exc:
        errors.append(f"cannot read CHANGELOG.md: {exc}")
    identities = {}
    for rel in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
        try:
            host = json.loads((root / rel).read_text(encoding="utf-8"))
            identities[rel] = host.get("version")
            if host.get("version") != version or host.get("name") != package.get("name"):
                errors.append(f"{rel} release identity differs from package-manifest.toml")
        except (OSError, ValueError, AttributeError) as exc:
            errors.append(f"cannot read {rel}: {exc}")
    dependencies = manifest.get("dependencies", {})
    pyproject_path = dependencies.get("pyproject") if isinstance(dependencies, dict) else None
    if pyproject_path:
        try:
            with (root / pyproject_path).open("rb") as stream:
                project = tomllib.load(stream)["project"]
            expected = ".".join(map(str, calver_parts(version)))
            identities[pyproject_path] = project.get("version")
            if project.get("version") != expected or project.get("name") != package.get("name"):
                errors.append("pyproject.toml must represent this product CalVer in normalized PEP 440 spelling")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"cannot validate Python distribution identity: {exc}")
        try:
            inventory = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))
            identities["MANIFEST.json"] = inventory.get("version")
            if inventory.get("version") != version or inventory.get("package") != package.get("name"):
                errors.append("MANIFEST.json release identity differs from package-manifest.toml")
            for field in ("version_scheme", "release_timezone"):
                if inventory.get(field) != package.get(field):
                    errors.append(f"MANIFEST.json {field} differs from package-manifest.toml")
            expected_date = date(*calver_parts(version)[:3]).isoformat()
            if inventory.get("generated_at") != expected_date:
                errors.append("MANIFEST.json generated_at must retain the deterministic release date")
        except (OSError, ValueError, AttributeError) as exc:
            errors.append(f"cannot validate distribution inventory identity: {exc}")
    return {"ok": not errors, "package": package.get("name"), "version": version,
            "version_scheme": package.get("version_scheme"), "release_timezone": package.get("release_timezone"),
            "distribution_identities": identities, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--tag", help="Publication tag to compare with the declared CalVer")
    args = parser.parse_args()
    try:
        report = check(args.root or product_root(), args.tag)
    except (OSError, ValueError) as exc:
        report = {"ok": False, "errors": [str(exc)]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
