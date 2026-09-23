#!/usr/bin/env python3
"""The corpus a second implementation of the narrative contract is checked against.

The contract is two readers and the cases that exercise them. A copy of the
readers cannot be compared with a copy somewhere else, and the cases are Python
that only this installation can run. What another implementation can run is a
list of documents, each with the verdict the contract requires of it: whether
it is accepted, the fragments of the messages that refuse it, the notices it
draws, and whether its approval holds.

That list is written here from the case tables the suites carry, so it says
exactly what those tables assert and nothing they do not. It is published by
hash beside the readers in the contract. `--check` refuses a copy on disk that
is not what the tables here would write, and a verdict in it that the readers
here do not reach.

    python scripts/narrative_corpus.py            write scripts/narrative_corpus.json
    python scripts/narrative_corpus.py --check    refuse a stale or unreached corpus
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORPUS = "scripts/narrative_corpus.json"

# The suite for each reader, by the names an installation may give it.
SUITES = {
    "narrative": ("narrative_smoke_test.py", "narrative_contract_smoke_test.py"),
    "scene-plot": ("scene_plot_smoke_test.py", "scene_plot_contract_smoke_test.py"),
}
# The tables a suite holds, and what a case in each one asserts.
TABLES = {
    "narrative": (
        ("CASES", "errors"),
        ("generated_cases", "errors"),
        ("UNNAMED_CASES", "errors"),
        ("NARRATIVE_APPROVAL_CASES", "approval"),
    ),
    "scene-plot": (
        ("CASES", "errors"),
        ("UNNAMED_CASES", "errors"),
        ("APPROVAL_CASES", "approval"),
    ),
}
VERDICT = {
    "ok": "whether the reader accepts the document",
    "refuses": "fragments that each appear in one of the messages refusing it",
    "notices": "fragments that each appear in one of the notices it draws",
    "approved": "whether the approval block holds",
    "approval_refuses": "fragments that each appear in one of the approval errors; "
                        "empty when there are none",
}


def load_suite(root: Path, artifact: str) -> Any:
    for name in SUITES[artifact]:
        path = root / "scripts" / name
        if path.is_file():
            spec = importlib.util.spec_from_file_location(path.stem, path)
            module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(module)  # type: ignore[union-attr]
            return module
    raise FileNotFoundError(f"no suite for {artifact} under {root / 'scripts'}")


def entries(root: Path, artifact: str) -> list[dict[str, Any]]:
    module = load_suite(root, artifact)
    found: list[dict[str, Any]] = []
    for table, kind in TABLES[artifact]:
        cases = getattr(module, table)
        if callable(cases):
            cases = cases()
        for case in cases:
            expect: dict[str, Any] = {}
            if kind == "approval":
                expect["approved"] = bool(case["approved"])
                expect["approval_refuses"] = [case["error"]] if case["error"] else []
            elif "notice" in case:
                expect["ok"] = True
                expect["notices"] = [case["notice"]]
            else:
                expect["ok"] = case["error"] is None
                expect["refuses"] = [case["error"]] if case["error"] else []
            found.append({
                "artifact": artifact,
                "name": case["name"],
                "document": case["value"],
                "expect": expect,
            })
    return found


def corpus(root: Path) -> dict[str, Any]:
    return {
        "what": "The documents in the case tables of the suites that check the contract's "
                "readers, each with the verdict the contract requires of it. An implementation "
                "is checked by whether it reaches every verdict here.",
        "verdict": VERDICT,
        "entries": entries(root, "narrative") + entries(root, "scene-plot"),
    }


def text(body: dict[str, Any]) -> str:
    return json.dumps(body, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def unreached(body: dict[str, Any]) -> list[str]:
    """The entries whose verdict the readers here do not reach."""
    from narrative import validate_narrative
    from scene_plot import validate_scene_plot
    readers = {"narrative": validate_narrative, "scene-plot": validate_scene_plot}
    missed: list[str] = []
    for entry in body["entries"]:
        report = readers[entry["artifact"]](entry["document"])
        expect = entry["expect"]
        label = f"{entry['artifact']}: {entry['name']}"
        if "ok" in expect and report["ok"] != expect["ok"]:
            missed.append(f"{label}: ok is {report['ok']}, the corpus says {expect['ok']}")
        for key, messages in (("refuses", "errors"), ("notices", "notices"),
                              ("approval_refuses", "approval_errors")):
            joined = "; ".join(report.get(messages, []))
            for fragment in expect.get(key, []):
                if fragment not in joined:
                    missed.append(f"{label}: {messages} do not say {fragment!r}")
        if "approved" in expect:
            if report["approved"] != expect["approved"]:
                missed.append(f"{label}: approved is {report['approved']}, "
                              f"the corpus says {expect['approved']}")
            if not expect["approval_refuses"] and report.get("approval_errors"):
                missed.append(f"{label}: approval errors where the corpus says none")
    return missed


def check(root: Path, errors: list[str]) -> None:
    """For a validator: the corpus on disk is what the tables write, and the readers reach it.

    The verdicts are run from the file and not from the tables, so a document that
    does not survive being written as JSON, or a reader that has moved away from
    what is published, is reported as such.
    """
    path = root / CORPUS
    if not path.is_file():
        errors.append(f"{CORPUS} is missing; scripts/narrative_corpus.py writes it")
        return
    held = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    try:
        body = json.loads(held)
    except json.JSONDecodeError as exc:
        errors.append(f"{CORPUS} is not JSON: {exc}")
        return
    try:
        fresh = text(corpus(root))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{CORPUS} cannot be compared with the tables here: {exc}")
    else:
        if held != fresh:
            errors.append(f"{CORPUS} is not what the tables here write; "
                          "scripts/narrative_corpus.py rewrites it")
    try:
        missed = unreached(body)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{CORPUS} cannot be run through the readers here: {exc}")
        return
    for miss in missed:
        errors.append(f"{CORPUS}: {miss}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true",
                        help="Refuse a corpus that is stale or that the readers here do not reach")
    args = parser.parse_args(argv)
    if args.check:
        errors: list[str] = []
        check(ROOT, errors)
        for error in errors:
            print(error)
        if errors:
            return 1
        print(f"current: {CORPUS}")
        return 0
    body = corpus(ROOT)
    written = text(body)
    (ROOT / CORPUS).write_text(written, encoding="utf-8", newline="\n")
    digest = hashlib.sha256(written.encode("utf-8")).hexdigest()
    print(f"wrote {CORPUS} ({len(body['entries'])} entries, sha256 {digest[:16]})")
    return 0


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
