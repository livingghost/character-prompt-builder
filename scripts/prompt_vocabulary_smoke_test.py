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

from prompt_retrieval import main as retrieval_main, mark_outcome, validate_prompt_retrieval_record
from search_prompt_vocabulary import (
    VocabularyError,
    list_categories,
    load_vocabulary,
    main as search_main,
    read_prompt,
    search_vocabularies,
    tokens,
    validate_vocabulary,
)

COMMONS_DICTIONARY = Path(__file__).resolve().parents[1] / "packs/commons/resources/prompt-vocabulary/dictionary.json"


def ranking_fixture() -> dict[str, Any]:
    """Synthetic entries where a word match competes with a longer, weaker one."""
    return {
        "format": "character-prompt-builder-prompt-vocabulary",
        "name": "Synthetic Ranking Vocabulary",
        "description": "Fictional data used only by the regression test.",
        "categories": [
            {"id": "knitwear", "name": "Knitwear", "description": "Knitted garments.", "entries": [
                {"term": "aran sweater", "description": "A wool sweater covered in raised cable and braid knit panels."},
            ]},
            {"id": "devices", "name": "Devices", "description": "Electronics.", "entries": [
                {"term": "charger cable", "aliases": ["charger_cable"], "description": "A cable for charging a device."},
                {"term": "oil can", "description": "A can with a long spout."},
            ]},
            {"id": "faces", "name": "Faces", "description": "Expressions.", "entries": [
                {"term": "pouting lips"},
                {"term": "pout"},
            ]},
        ],
    }


def words_of(row: Any, *, description: bool = True) -> set[str]:
    return set(tokens(" ".join([row.term, *row.aliases, row.description if description and row.description else ""])))


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

        single, many = Path(temp) / "single.json", Path(temp) / "many.json"
        queries = {"camera": ["low angle", "close-up"], "lighting": "soft light"}
        with contextlib.redirect_stdout(io.StringIO()):
            for element, query in (("camera", "low angle"), ("camera", "close-up"), ("lighting", "soft light")):
                search_main([query, "--dictionary", str(path), "--record", str(single), "--element", element])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = search_main(["--dictionary", str(path), "--queries", json.dumps(queries), "--record", str(many)])
        report = json.loads(output.getvalue())
        add("one run answers several queries and records each under its element exactly as single searches do",
            code == 0 and many.read_text(encoding="utf-8") == single.read_text(encoding="utf-8")
            and [(row["element"], row["query"]) for row in report["searches"]]
            == [("camera", "low angle"), ("camera", "close-up"), ("lighting", "soft light")],
            report)
        repeated = Path(temp) / "repeated.json"
        with contextlib.redirect_stdout(io.StringIO()):
            code = search_main(["--dictionary", str(path), "--record", str(repeated),
                                "--queries", '{"camera": ["low angle"], "camera": ["close-up"]}'])
        add("a queries object that names one element twice is refused before anything is recorded",
            code == 2 and not repeated.exists())

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = retrieval_main([str(many), "--element", "camera", "--adopted", "low angle", "--adopted", "close-up"])
        report = json.loads(output.getvalue())
        kept = json.loads(many.read_text(encoding="utf-8"))["elements"][0].get("adopted_records")
        add("several --adopted records for one element are all kept",
            code == 0 and kept == ["low angle", "close-up"]
            and report["marked"]["adopted_records"] == ["low angle", "close-up"], report)
        add("remaining work names the element rather than its position",
            report["remaining"] == ["element 'lighting' has no outcome; mark it with --adopted ID (repeat for each"
                                    " record the wording uses), or with --composed TEXT and --reason TEXT"],
            report["remaining"])

    ranking = ranking_fixture()
    knit = search_vocabularies([ranking], "cable knit")
    add("an entry holding every query word ranks above entries holding one of them",
        [row.term for row in knit] == ["aran sweater", "charger cable"], [r.as_json() for r in knit])
    pout = search_vocabularies([ranking], "pout")
    add("a query matches whole words, so 'pout' finds 'pouting' and not the 'spout' of a description",
        [row.term for row in pout] == ["pout", "pouting lips"], [r.as_json() for r in pout])

    commons = [load_vocabulary(COMMONS_DICTIONARY)]
    solo = search_vocabularies(commons, "solo", limit=40)
    named = ["solo" in words_of(row, description=False) for row in solo]
    add("commons 'solo': the exact term first, and every term naming solo above entries that only mention it",
        bool(solo) and solo[0].term == "solo" and named == sorted(named, reverse=True),
        [r.as_json() for r in solo[:8]])
    cable = search_vocabularies(commons, "cable knit", limit=40)
    both = [{"cable", "knit"} <= words_of(row) for row in cable]
    add("commons 'cable knit': entries holding both words rank above entries holding one",
        bool(cable) and both[0] and both == sorted(both, reverse=True), [r.as_json() for r in cable[:8]])
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
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
