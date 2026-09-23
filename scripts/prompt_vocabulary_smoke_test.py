#!/usr/bin/env python3
"""Self-contained regression checks for prompt-vocabulary validation and search."""
from __future__ import annotations

import contextlib
import copy
import io
import json
import tempfile
from pathlib import Path
from typing import Any, Callable

from prompt_retrieval import mark_outcome, validate_prompt_retrieval_record
from search_prompt_vocabulary import (
    VocabularyError,
    list_categories,
    load_vocabulary,
    main as search_main,
    read_prompt,
    search_vocabularies,
    validate_vocabulary,
)


def fixture() -> dict[str, Any]:
    return {
        "format": "character-prompt-builder-prompt-vocabulary",
        "name": "Synthetic Prompt Vocabulary",
        "description": "Fictional data used only by the regression test.",
        "categories": [
            {
                "id": "camera",
                "name": "Camera",
                "description": "Camera and viewpoint vocabulary.",
                "entries": [
                    {"term": "low angle", "aliases": ["worm's-eye view"], "description": "A camera view from below the subject."},
                    {"term": "close-up"},
                    {"term": ";D", "description": "A distinct punctuation-bearing expression cue used by the fixture."},
                    {"term": ":D"},
                ],
            },
            {
                "id": "lighting",
                "name": "Lighting",
                "description": "Lighting vocabulary.",
                "entries": [
                    {"term": "soft light", "description": "Diffuse illumination with gentle shadow transitions."}
                ],
            },
            {
                "id": "eye-colors",
                "name": "Eye Colors",
                "description": "Iris colour vocabulary; one figure carries one of these.",
                "single_valued": True,
                "entries": [
                    {"term": "blue eyes", "description": "A blue iris."},
                    {"term": "green eyes", "description": "A green iris."},
                ],
            },
            {
                "id": "eye-states",
                "name": "Eye States",
                "description": "Whether the eyes are open, and how.",
                "entries": [
                    {
                        "term": "closed eyes",
                        "description": "The eyelids are shut, so no iris colour is drawn.",
                        "opposes": ["blue eyes", "green eyes"],
                    },
                ],
            },
            {
                "id": "subject-count",
                "name": "Subject Count",
                "description": "How many figures stand in the picture.",
                "multiple_figures_terms": ["2girls"],
                "entries": [
                    {"term": "solo", "description": "One figure alone."},
                    {"term": "2girls", "description": "Two figures."},
                ],
            },
        ],
    }


def expect_error(fn: Callable[[], Any]) -> bool:
    try:
        fn()
    except VocabularyError:
        return True
    return False


def main() -> int:
    value = fixture()
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: Any = None) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    add("valid synthetic vocabulary passes validation", validate_vocabulary(value) is value)
    exact = search_vocabularies([value], "low angle", limit=1)
    add("exact term search ranks the exact term first", bool(exact and exact[0].term == "low angle"), [r.as_json() for r in exact])
    alias = search_vocabularies([value], "worm's-eye view", limit=1)
    add("alias search resolves the canonical term", bool(alias and alias[0].term == "low angle"), [r.as_json() for r in alias])
    close = search_vocabularies([value], "close-up", limit=1)
    add("entry descriptions are optional and omitted when absent", bool(close and close[0].description is None), [r.as_json() for r in close])
    desc = search_vocabularies([value], "diffuse illumination", limit=1)
    add("description text participates in retrieval", bool(desc and desc[0].term == "soft light"), [r.as_json() for r in desc])
    filtered = search_vocabularies([value], "angle", category_filters=["Camera"])
    add("category filters return matching rows and exclude unrelated categories", bool(filtered and all(r.category == "Camera" for r in filtered)), [r.as_json() for r in filtered])
    punctuation = search_vocabularies([value], ";D", limit=5)
    add("punctuation-bearing terms remain distinct and searchable", bool(punctuation and punctuation[0].term == ";D" and all(r.term != ":D" for r in punctuation)), [r.as_json() for r in punctuation])
    categories = list_categories([value])
    add("category listing is deterministic", [r["name"] for r in categories] == ["Camera", "Eye Colors", "Eye States", "Lighting", "Subject Count"], categories)
    add("distinct punctuation-bearing terms pass uniqueness validation", validate_vocabulary(copy.deepcopy(value)) is not None)
    dup = copy.deepcopy(value); dup["categories"][0]["entries"].append({"term": "LOW ANGLE"})
    add("duplicate terms in one category are rejected", expect_error(lambda: validate_vocabulary(dup)))
    bad_alias = copy.deepcopy(value); bad_alias["categories"][0]["entries"][0]["aliases"] = ["Low Angle"]
    add("an alias cannot repeat its canonical term", expect_error(lambda: validate_vocabulary(bad_alias)))
    with tempfile.TemporaryDirectory(prefix="cpb-prompt-vocabulary-") as temp:
        path = Path(temp) / "dictionary.json"
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        add("a UTF-8 dictionary round-trips through the file loader", load_vocabulary(path) == value)
        record = Path(temp) / "lookups.json"
        with contextlib.redirect_stdout(io.StringIO()):
            code = search_main(["low angle", "--dictionary", str(path), "--limit", "1",
                                "--record", str(record), "--element", "camera"])
        recorded = json.loads(record.read_text(encoding="utf-8")) if record.is_file() else None
        add("a recorded search appends its query and returned terms in the catalog lookup shape",
            code == 0 and recorded == {"artifact_type": "prompt-retrieval-record", "elements": [
                {"element": "camera", "queries": ["low angle"], "inspected_records": ["low angle"]}]}, recorded)
        marked = recorded and mark_outcome(recorded, "camera", adopted="low angle")
        add("a returned term can be marked adopted",
            bool(marked) and validate_prompt_retrieval_record(marked)["ok"], marked)
    alternation = read_prompt([value], "[blue eyes|green eyes], (closed eyes:1.3)")
    add(
        "a read returns bracketed alternatives in reading order",
        [row["term"] for row in alternation["text"]] == ["blue eyes", "green eyes", "closed eyes"],
        alternation["text"],
    )
    add(
        "opposed pairs inside an alternation group are reported",
        any("cannot both hold" in notice for notice in alternation["notices"]),
        alternation["notices"],
    )
    add(
        "one alternation group is one value of a single-valued property",
        not any("one property named twice" in notice for notice in alternation["notices"]),
        alternation["notices"],
    )
    repeated = read_prompt([value], "blue eyes, green eyes")
    add(
        "the same property named twice outside brackets is still reported",
        any("one property named twice" in notice for notice in repeated["notices"]),
        repeated["notices"],
    )
    scheduled = read_prompt([value], "[blue eyes:green eyes:0.4]")
    add(
        "a scheduling step count is not read as a term",
        [row["term"] for row in scheduled["text"]] == ["blue eyes", "green eyes"],
        scheduled["text"],
    )
    crowded = read_prompt([value], "2girls, blue eyes, green eyes")
    add(
        "a declared multiple-figures term excuses a property named twice",
        not any("one property named twice" in notice for notice in crowded["notices"]),
        crowded["notices"],
    )
    alone = read_prompt([value], "solo, blue eyes, green eyes")
    add(
        "without a multiple-figures term the same pair is still reported",
        any("one property named twice" in notice for notice in alone["notices"]),
        alone["notices"],
    )

    forbidden = {"source", "source_id", "source_section", "disposition", "blocked_from_search", "requires_review"}
    fields = {key for category in value["categories"] for entry in category["entries"] for key in entry}
    add("the fixture contains no per-entry provenance or policy-control fields", not bool(fields & forbidden), sorted(fields & forbidden))

    output = {"ok": all(row["passed"] for row in checks), "checks": len(checks), "results": checks}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
