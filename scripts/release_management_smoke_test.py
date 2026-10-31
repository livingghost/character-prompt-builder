#!/usr/bin/env python3
"""Product CalVer regressions; no runtime artifact counters or provider calls."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib

from release_contract import calver_parts, check, product_root, validate_changelog, validate_metadata
from run_checks import commands as runner_commands


def main() -> int:
    errors = []
    checks = 0

    def expect(condition: bool, label: str) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            errors.append(label)

    root = product_root()
    with (root / "package-manifest.toml").open("rb") as stream:
        manifest = tomllib.load(stream)
    version = manifest["package"]["version"]
    report = check(root)
    expect(report["ok"], f"installed product identity: {report['errors']}")
    expect(not validate_metadata(manifest, "v" + version), "publication tag and CalVer must agree")
    for token in ("2026.09.19.1", "2000.02.29.2", "0001.01.01.1", "2026.12.31.10"):
        try:
            expect(len(calver_parts(token)) == 4, "canonical Gregorian CalVer accepted")
        except ValueError as exc:
            expect(False, f"valid CalVer rejected: {token}: {exc}")
    for token in ("2026.02.29.1", "1900.02.29.1", "0000.01.01.1", "2026.13.01.1",
                  "2026.04.31.1", "2026.9.19.1", "2026.09.19.0", "2026.09.19.01",
                  "2026.09.19.1\n", " 2026.09.19.1", None, 2026):
        try:
            calver_parts(token)
            expect(False, f"malformed release accepted: {token!r}")
        except ValueError:
            expect(True, "invalid Gregorian/date formatting rejected")
    for field, value in (("version_scheme", "arbitrary"), ("release_timezone", "Asia/Tokyo")):
        mutant = copy.deepcopy(manifest); mutant["package"][field] = value
        expect(bool(validate_metadata(mutant)), f"{field} must preserve release policy")
    for field in ("version_scheme", "release_timezone"):
        mutant = copy.deepcopy(manifest); del mutant["package"][field]
        expect(bool(validate_metadata(mutant)), f"missing {field} must fail")
    mutant = copy.deepcopy(manifest); mutant["release"]["output"] = "dist/unidentified.zip"
    expect(bool(validate_metadata(mutant)), "archive filename must identify its product release")
    expect(bool(validate_metadata(manifest, "v2000.01.01.1")), "mismatched publication tag must fail")
    for style, heading in (("plain", "2026.09.19.1"), ("dated", "[2026.09.19.1] - 2026-09-19")):
        text = f"# Changelog\n\n## {heading}\n\nInitial release.\n\n- Product changes.\n"
        expect(not validate_changelog(text, "2026.09.19.1", style=style), f"{style}: current release entry")
        expect(bool(validate_changelog(text.replace("Initial release.", "").replace("Product changes.", "" ).replace("- \n", "\n"), "2026.09.19.1", style=style)), f"{style}: heading-only current section rejected")
        expect(bool(validate_changelog(text.replace(heading, "Current capabilities"), "2026.09.19.1", style=style)), f"{style}: dated release required")
        expect(bool(validate_changelog(text + f"\n## {heading}\nDuplicate.\n", "2026.09.19.1", style=style)), f"{style}: duplicate current entry rejected")
        older = "2026.09.18.2" if style == "plain" else "[2026.09.18.2] - 2026-09-18"
        history = text + f"\n## {older}\n\n- Earlier changes.\n"
        expect(not validate_changelog(history, "2026.09.19.1", style=style), f"{style}: earlier releases follow the current one")
        expect(bool(validate_changelog(history, "2026.09.18.2", style=style)), f"{style}: the newest section is the current release")
        expect(bool(validate_changelog(f"# Changelog\n\n## {older}\n\n- Earlier.\n\n## {heading}\n\n- Later.\n", "2026.09.19.1", style=style)), f"{style}: releases run newest first")
        expect(bool(validate_changelog(history.replace("- Earlier changes.", ""), "2026.09.19.1", style=style)), f"{style}: every release has notes")
        expect(bool(validate_changelog(history + "\n## Notes\n\n- Loose text.\n", "2026.09.19.1", style=style)), f"{style}: every section is a release")
    expect(bool(validate_changelog("# Log\n## [2026.09.19.1] - 2026-09-18\nChanges.\n", "2026.09.19.1", style="dated")), "explicit date must match CalVer date")
    # Check actual distributed product files via the CLI, not only parser units.
    cli = subprocess.run([sys.executable, str(Path(__file__).with_name("release_contract.py")), "--root", str(root), "--tag", "v" + version], capture_output=True, text=True, encoding="utf-8")
    expect(cli.returncode == 0, f"installed release CLI: {cli.stdout} {cli.stderr}")
    # The runner starts every test module once, so a new suite cannot sit unrun.
    labels = {label for label, _ in runner_commands()}
    suites = {
        f"scripts/{path.name}"
        for path in (root / "scripts").glob("*.py")
        if path.name.endswith("_test.py") or path.name.startswith("test_")
    }
    unrun = sorted(suites - labels)
    expect(not unrun, f"scripts/run_checks.py starts no command for {unrun}")
    # CI controls are not required inside a runtime-only release archive.
    ci = root / ".github/workflows/ci.yml"
    if ci.exists():
        expect("python scripts/run_checks.py" in ci.read_text(encoding="utf-8"), "ci.yml: the runner must run every suite")
    release = root / ".github/workflows/release.yml"
    if release.exists():
        text = release.read_text(encoding="utf-8")
        expect("release_contract.py" in text, "release.yml: product contract must execute")
        expect('--tag "$GITHUB_REF_NAME"' in text, "publication must bind the tag to the product")
    # Mutate only a small isolated fixture: no edits to the installed product.
    with tempfile.TemporaryDirectory(prefix="product-release-check-") as td:
        fixture=Path(td)
        (fixture/"package-manifest.toml").write_text((root/"package-manifest.toml").read_text(encoding="utf-8"), encoding="utf-8")
        (fixture/"CHANGELOG.md").write_text((root/"CHANGELOG.md").read_text(encoding="utf-8"), encoding="utf-8")
        for rel in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json", "pyproject.toml", "uv.lock",
                    "requirements.txt", ".python-version", "MANIFEST.json"):
            p=root/rel
            if p.exists():
                target=fixture/rel; target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes())
        expect(check(fixture)["ok"], "isolated product identity must validate")
        requirements = fixture / "requirements.txt"
        saved_requirements = requirements.read_bytes()
        requirements.write_bytes(saved_requirements + b"\n# Changed after the official export.\n")
        changed_export = check(fixture)
        expect(any("requirements.txt differs" in error for error in changed_export["errors"]),
               "release validation binds the complete official requirements export")
        requirements.write_bytes(saved_requirements)
        project = tomllib.loads((fixture / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        lock = fixture / "uv.lock"
        saved_lock = lock.read_text(encoding="utf-8")
        lock_mutations = (
            (f'requires-python = "{project["requires-python"]}"', 'requires-python = ">=3.0"', "requires-python differs"),
            (f'name = "{project["name"]}"\nversion = "{project["version"]}"',
             f'name = "{project["name"]}"\nversion = "2000.1.1.1"', "project identity differs"),
        )
        for original, changed, diagnosis in lock_mutations:
            expect(original in saved_lock, "lock fixture contains the declaration under review")
            lock.write_text(saved_lock.replace(original, changed, 1), encoding="utf-8")
            expect(any(diagnosis in error for error in check(fixture)["errors"]),
                   "lock follows its owning project: " + diagnosis)
        lock.write_text(saved_lock, encoding="utf-8")
        python_version = fixture / ".python-version"
        saved_python = python_version.read_bytes()
        python_version.write_text("3.0\n", encoding="utf-8")
        expect(any("below pyproject.toml" in error for error in check(fixture)["errors"]),
               "the selected interpreter satisfies the project's supported Python minimum")
        python_version.write_bytes(saved_python)
        for rel in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
            target=fixture/rel; saved=target.read_bytes(); data=json.loads(saved);data["version"]="2000.01.01.1";target.write_text(json.dumps(data), encoding="utf-8")
            expect(not check(fixture)["ok"], f"stale generated host metadata: {rel}");target.write_bytes(saved)
        target=fixture/"CHANGELOG.md";saved=target.read_bytes();target.write_text("# Change notes\n\n## Features\nFeature descriptions.\n", encoding="utf-8")
        expect(not check(fixture)["ok"], "the current entry requires a release date");target.write_bytes(saved)
        inventory_path = fixture / "MANIFEST.json"
        if inventory_path.exists():
            saved = inventory_path.read_bytes()
            for field in ("version", "version_scheme", "release_timezone", "generated_at"):
                data = json.loads(saved); data[field] = "incorrect"
                inventory_path.write_text(json.dumps(data), encoding="utf-8")
                expect(not check(fixture)["ok"], f"distribution inventory {field} must remain bound to product CalVer")
            inventory_path.write_bytes(saved)
    print(json.dumps({"ok":not errors, "checks":checks, "errors":errors}, indent=2))
    return int(bool(errors))


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
