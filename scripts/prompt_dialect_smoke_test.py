#!/usr/bin/env python3
"""Exercise dialect resolution: what one family owns, and what is kept from it."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import prompt_dialect as dialects  # noqa: E402
from pack_manager import PackError  # noqa: E402

EXPECTED_CHECKS = 12

SOUND = {
    "format": "character-prompt-builder-prompt-dialects",
    "name": "Fixture dialects",
    "description": "Two fixture families for the regression test.",
    "dialects": [
        {
            "id": "family-one", "name": "Family One", "description": "The first fixture family.",
            "tag_separator": "a comma followed by one space",
            "block_order": ["quality", "subject", "camera"],
            "rating_terms": ["general", "explicit"],
            "inert_terms": ["4k"],
        },
        {
            "id": "family-two", "name": "Family Two", "description": "The second fixture family.",
            "tag_separator": "a comma followed by one space",
            "block_order": ["quality", "subject"],
            "weight_range": [1.2, 1.4],
            "rating_terms": ["safe", "nsfw"],
        },
    ],
}
GUIDE = {
    "format": "character-prompt-builder-prompt-writing-guide",
    "name": "Fixture guide",
    "description": "A fixture guide for the regression test.",
    "sections": [
        {"id": "everywhere", "title": "Everywhere", "rules": ["Holds for every target."]},
        {"id": "one-only", "title": "One only", "dialects": ["family-one"], "rules": ["Holds for the first family."]},
        {"id": "two-only", "title": "Two only", "dialects": ["family-two"], "rules": ["Holds for the second family."]},
    ],
}


def refused(call) -> str | None:
    try:
        call()
    except PackError as exc:
        return str(exc)
    return None


def main() -> int:
    results: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: Any = None) -> None:
        results.append({"name": name, "passed": bool(passed), "detail": detail})

    check("a sound resource is accepted", dialects.validate_dialects(json.loads(json.dumps(SOUND))) is not None)

    unnamed = json.loads(json.dumps(SOUND))
    del unnamed["dialects"][0]["block_order"]
    check("a dialect with no block order is refused", refused(lambda: dialects.validate_dialects(unnamed)) is not None)

    repeated = json.loads(json.dumps(SOUND))
    repeated["dialects"][1]["id"] = "family-one"
    message = refused(lambda: dialects.validate_dialects(repeated))
    check("a repeated dialect id is refused", message is not None and "repeats" in message, message)

    stray = json.loads(json.dumps(SOUND))
    stray["dialects"][0]["unexpected"] = True
    check("an unknown key in a dialect is refused", refused(lambda: dialects.validate_dialects(stray)) is not None)

    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        dialect_path = home / "dialects.json"
        dialect_path.write_text(json.dumps(SOUND), encoding="utf-8")
        guide_path = home / "guide.json"
        guide_path.write_text(json.dumps(GUIDE), encoding="utf-8")

        loaded = dialects.load_dialects(dialect_path)
        check("dialects load by their id", sorted(loaded) == ["family-one", "family-two"], sorted(loaded))
        check("a loaded dialect carries its own vocabulary",
              loaded["family-one"]["rating_terms"] == ["general", "explicit"]
              and loaded["family-two"]["rating_terms"] == ["safe", "nsfw"])

        broken = home / "broken.json"
        broken.write_text(json.dumps({"format": "x"}), encoding="utf-8")
        check("a file that is not the resource is refused", refused(lambda: dialects.load_dialects(broken)) is not None)

        split = dialects.applicable_sections(guide_path, "family-one")
        check("a section naming no family applies to every target",
              [s["id"] for s in split["universal"]] == ["everywhere"], split["universal"])
        check("a section naming this family is returned",
              [s["id"] for s in split["dialect"]] == ["one-only"], split["dialect"])
        check("a section naming another family is withheld rather than returned",
              [s["id"] for s in split["withheld"]] == ["two-only"], split["withheld"])

        none = dialects.applicable_sections(guide_path, None)
        check("a target with no family gets the universal sections and no family section",
              [s["id"] for s in none["universal"]] == ["everywhere"] and none["dialect"] == []
              and [s["id"] for s in none["withheld"]] == ["one-only", "two-only"])

        check("no guide resource yields no rules rather than an error",
              dialects.applicable_sections(None, "family-one") == {"universal": [], "dialect": [], "withheld": []})

    passed = sum(1 for row in results if row["passed"])
    report = {"ok": len(results) == EXPECTED_CHECKS and passed == len(results), "checks": len(results),
              "expected_checks": EXPECTED_CHECKS, "passed": passed,
              "failures": [row for row in results if not row["passed"]]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
