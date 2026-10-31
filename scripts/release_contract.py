#!/usr/bin/env python3
"""Check product CalVer, dated release notes, and generated distribution identity.

This module concerns the product release only. Scene/state/protocol artifacts
continue to identify their content without independent release counters.
"""
from __future__ import annotations
import operation_context as _operation_context

import argparse
from datetime import date
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib
from typing import Any, Mapping

CALVER = re.compile(r"([0-9]{4})\.(0[1-9]|1[0-2])\.(0[1-9]|[12][0-9]|3[01])\.([1-9][0-9]*)", re.ASCII)
ENVIRONMENT_EXPORT_COMMAND = ("uv", "export", "--locked", "--no-emit-project", "--format", "requirements.txt")


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


def release_heading(version: str, style: str) -> str:
    """The CHANGELOG heading text of one release in the given style."""
    year, month, day, _ = calver_parts(version)
    return version if style == "plain" else f"[{version}] - {date(year, month, day).isoformat()}"


def heading_release(heading: str, style: str) -> str | None:
    """The release a CHANGELOG heading names, or None when it names none in this style."""
    match = re.fullmatch(r"(\S+)" if style == "plain" else r"\[(\S+)\] - \d{4}-\d{2}-\d{2}", heading)
    if match is None:
        return None
    try:
        return match.group(1) if release_heading(match.group(1), style) == heading else None
    except ValueError:
        return None


def validate_changelog(text: str, version: str, *, style: str) -> list[str]:
    """Check one section per release, newest first, the newest being this release, each with notes."""
    try:
        calver_parts(version)
    except ValueError as exc:
        return [str(exc)]
    if style not in {"plain", "dated"}:
        raise ValueError("unsupported product changelog heading style")
    expected = release_heading(version, style)
    sections = list(re.finditer(r"(?m)^##[ \t]+([^\r\n]+)[ \t]*$", text))
    if not sections:
        return [f"CHANGELOG.md has no release; add ## {expected}"]
    errors = []
    if sections[0].group(1).strip() != expected:
        errors.append(f"CHANGELOG.md newest release must be ## {expected}")
    releases = []
    for index, section in enumerate(sections):
        heading = section.group(1).strip()
        release = heading_release(heading, style)
        if release is None:
            errors.append(f"CHANGELOG.md heading ## {heading} names no release; write ## {expected} for this one")
            continue
        end = sections[index + 1].start() if index + 1 < len(sections) else len(text)
        # A heading-only section is not a release record.
        if not any(line.strip() and not line.lstrip().startswith(("#", "<!--"))
                   for line in text[section.end():end].splitlines()):
            errors.append(f"CHANGELOG.md release {release} has no change notes")
        releases.append(release)
    for newer, older in zip(releases, releases[1:]):
        if calver_parts(newer) <= calver_parts(older):
            errors.append(f"CHANGELOG.md releases run newest first, each once: {newer} comes before {older}")
    return errors


def product_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "package-manifest.toml").is_file():
            return parent
    raise ValueError("package-manifest.toml is not present above the installed script")


def check_dependency_artifacts(root: Path) -> dict[str, Any]:
    """Verify the project, lock and exact official requirements export read-only."""
    from package_metadata import DEPENDENCY_DEFINITIONS, validate_environment_artifacts
    report: dict[str, Any] = {"ok": False, "definition": DEPENDENCY_DEFINITIONS["pyproject"],
                             "export_command": list(ENVIRONMENT_EXPORT_COMMAND), "errors": []}
    try:
        with (root / "package-manifest.toml").open("rb") as stream:
            declarations = tomllib.load(stream).get("dependencies", {})
        with (root / DEPENDENCY_DEFINITIONS["pyproject"]).open("rb") as stream:
            project = tomllib.load(stream)
        report["python_requirement"] = validate_environment_artifacts(root, declarations, project)
        if shutil.which("uv") is None:
            raise ValueError("uv is required to verify the locked environment artifacts; install uv and rerun validation")
        completed = subprocess.run(ENVIRONMENT_EXPORT_COMMAND, cwd=root, capture_output=True,
            env={**os.environ, "UV_OFFLINE": "1", "UV_NO_PROGRESS": "1"}, timeout=60, check=False)
        report["export_returncode"] = completed.returncode
        if completed.returncode:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            raise ValueError("uv could not verify the locked environment export: " + detail)
        expected = (root / declarations["requirements"]).read_bytes()
        report["export_matches"] = completed.stdout == expected
        if not report["export_matches"]:
            raise ValueError("requirements.txt differs from the official locked uv export; regenerate it with "
                             + " ".join(ENVIRONMENT_EXPORT_COMMAND))
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        report["errors"].append(str(exc))
    report["ok"] = not report["errors"]
    return report


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
    environment = None
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
        environment = check_dependency_artifacts(root)
        errors.extend(environment["errors"])
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
            "distribution_identities": identities, "dependency_artifacts": environment, "errors": errors}


def main() -> int:
    parser = _operation_context.ArgumentParser(description=__doc__)
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
    raise SystemExit(_operation_context.run_cli(main))
