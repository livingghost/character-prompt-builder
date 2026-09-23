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
    expect(bool(validate_changelog("# Log\n## [2026.09.19.1] - 2026-09-18\nChanges.\n", "2026.09.19.1", style="dated")), "explicit date must match CalVer date")
    # Check actual distributed product files via the CLI, not only parser units.
    cli = subprocess.run([sys.executable, str(Path(__file__).with_name("release_contract.py")), "--root", str(root), "--tag", "v" + version], capture_output=True, text=True)
    expect(cli.returncode == 0, f"installed release CLI: {cli.stdout} {cli.stderr}")
    # CI controls are not required inside a runtime-only release archive.
    for name in ("ci.yml", "release.yml"):
        path = root / ".github/workflows" / name
        if path.exists():
            text = path.read_text(encoding="utf-8")
            expect("release_contract.py" in text, f"{name}: product contract must execute")
            expect("release_management_smoke_test.py" in text, f"{name}: CalVer regressions must execute")
            if name == "release.yml":
                expect('--tag "$GITHUB_REF_NAME"' in text, "publication must bind the tag to the product")
    # Mutate only a small isolated fixture: no edits to the installed product.
    with tempfile.TemporaryDirectory(prefix="product-release-check-") as td:
        fixture=Path(td)
        (fixture/"package-manifest.toml").write_text((root/"package-manifest.toml").read_text(), encoding="utf-8")
        (fixture/"CHANGELOG.md").write_text((root/"CHANGELOG.md").read_text(), encoding="utf-8")
        for rel in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json", "pyproject.toml", "MANIFEST.json"):
            p=root/rel
            if p.exists():
                target=fixture/rel; target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes())
        expect(check(fixture)["ok"], "isolated product identity must validate")
        for rel in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
            target=fixture/rel; saved=target.read_bytes(); data=json.loads(saved);data["version"]="2000.01.01.1";target.write_text(json.dumps(data))
            expect(not check(fixture)["ok"], f"stale generated host metadata: {rel}");target.write_bytes(saved)
        target=fixture/"CHANGELOG.md";saved=target.read_bytes();target.write_text("# Change notes\n\n## Features\nFeature descriptions.\n")
        expect(not check(fixture)["ok"], "the current entry requires a release date");target.write_bytes(saved)
        inventory_path = fixture / "MANIFEST.json"
        if inventory_path.exists():
            saved = inventory_path.read_bytes()
            for field in ("version", "version_scheme", "release_timezone", "generated_at"):
                data = json.loads(saved); data[field] = "incorrect"
                inventory_path.write_text(json.dumps(data))
                expect(not check(fixture)["ok"], f"distribution inventory {field} must remain bound to product CalVer")
            inventory_path.write_bytes(saved)
    print(json.dumps({"ok":not errors, "checks":checks, "errors":errors}, indent=2))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
