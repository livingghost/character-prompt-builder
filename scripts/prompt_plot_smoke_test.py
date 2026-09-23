#!/usr/bin/env python3
"""Check that the plot and retrieval readers reach the verdict each rule is for.

`prompt_artifact_smoke_test.py` drives both of these through
`build_prompt_artifacts.py` and asserts that a bad input is refused. That proves
the packaging stops, and not which rule stopped it: a plot refused for the wrong
reason still leaves the run non-zero, so a rule that quietly stops firing is
invisible there.

Each case here changes one thing in a document that answers the contract and
names the fragment the message has to carry.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from prompt_plot import content_sha256, validate_prompt_plot  # noqa: E402
from prompt_retrieval import validate_prompt_retrieval_record  # noqa: E402


def plot() -> dict[str, Any]:
    """A plot that answers the contract, for a case to change one thing in."""

    return {
        "artifact_type": "prompt-plot",
        "story": [
            {"id": "s1", "beat": "He lights the second lantern without being asked.",
             "visibility": "visible"},
            {"id": "s2", "beat": "The other one has not come down the ladder yet.",
             "visibility": "context"},
        ],
        "derived": [
            {"kind": "shows", "statement": "two lanterns on the bench", "from": ["s1"]},
            {"kind": "placement", "statement": "he stands at the bench, the lanterns in front of him",
             "from": ["s1"]},
            {"kind": "composition", "statement": "from the hatch, waist level, the bench across frame",
             "from": ["s1"]},
            {"kind": "must_preserve", "statement": "the pale blue shirt and the olive apron",
             "from": ["s1"]},
            {"kind": "free", "statement": "what is on the windowsill"},
        ],
    }


def approve(value: dict[str, Any]) -> dict[str, Any]:
    value["approved"] = {"by": "the case author", "at": "2026-09-11T00:00:00Z",
                         "content_sha256": content_sha256(value)}
    return value


def changed(**edits: Any) -> dict[str, Any]:
    value = plot()
    value.update(copy.deepcopy(edits))
    return value


def derived(index: int, **edits: Any) -> dict[str, Any]:
    value = plot()
    value["derived"][index].update(copy.deepcopy(edits))
    return value


def without_kind(kind: str) -> dict[str, Any]:
    value = plot()
    value["derived"] = [entry for entry in value["derived"] if entry["kind"] != kind]
    return value


PLOT_CASES: list[dict[str, Any]] = [
    {"name": "the contract answered", "value": plot(), "error": None},
    {"name": "an unknown key", "value": changed(notes="something"), "error": "unknown keys"},
    {"name": "the plot names a target", "value": changed(target="some-interface"),
     "error": "the interface is chosen after it"},
    {"name": "the plot names a model", "value": changed(model="some-model"),
     "error": "the interface is chosen after it"},
    {"name": "the wrong artifact type", "value": changed(artifact_type="scene-plot"),
     "error": "artifact_type must be 'prompt-plot'"},
    {"name": "no story", "value": changed(story=[]), "error": "story must be a non-empty array"},
    {"name": "two beats with one id",
     "value": changed(story=[plot()["story"][0], {**plot()["story"][1], "id": "s1"}]),
     "error": "repeats 's1'"},
    {"name": "a beat that is neither visible nor context",
     "value": changed(story=[{**plot()["story"][0], "visibility": "implied"},
                             plot()["story"][1]]),
     "error": "visibility must be one of"},
    {"name": "no derived statements", "value": changed(derived=[]),
     "error": "derived must be a non-empty array"},
    {"name": "a statement from a beat that does not exist",
     "value": derived(0, **{"from": ["s9"]}),
     "error": "names a beat that does not exist: 's9'"},
    {"name": "a statement from a context beat",
     "value": derived(0, **{"from": ["s2"]}),
     "error": "cannot put anything in the frame"},
    {"name": "a statement that repeats its source",
     "value": derived(0, **{"from": ["s1", "s1"]}),
     "error": "repeats a beat id"},
    {"name": "a statement with no source at all",
     "value": derived(0, **{"from": []}),
     "error": "must name at least one story beat"},
    {"name": "a free statement that claims a source",
     "value": derived(4, **{"from": ["s1"]}),
     "error": "does not belong to a 'free' statement"},
    {"name": "a statement of no known kind", "value": derived(0, kind="mood"),
     "error": "kind must be one of"},
    {"name": "an empty statement", "value": derived(0, statement="   "),
     "error": "statement must be a non-empty string"},
    {"name": "no composition statement", "value": without_kind("composition"),
     "error": "derived carries no 'composition' statement"},
    {"name": "no must_preserve statement", "value": without_kind("must_preserve"),
     "error": "derived carries no 'must_preserve' statement"},
    {"name": "no free statement", "value": without_kind("free"),
     "error": "derived carries no 'free' statement"},
    {"name": "a visible beat nothing derives from",
     "value": changed(story=[*plot()["story"],
                             {"id": "s3", "beat": "The radio is on.", "visibility": "visible"}]),
     "error": "is marked visible but nothing derives from it"},
    {"name": "a context beat nothing derives from", "value": plot(), "error": None},
    # Where the plot came from, when it came from somewhere.
    {"name": "no source at all, which is a plot written from a brief",
     "value": plot(), "error": None},
    {"name": "a source that names an upstream artifact",
     "value": changed(source={"artifact_type": "scene-plot", "id": "sc01",
                              "content_sha256": "b" * 64, "shot_id": "sc01-m01"}),
     "error": None, "source": {"artifact_type": "scene-plot", "id": "sc01",
                               "content_sha256": "b" * 64, "shot_id": "sc01-m01"}},
    {"name": "a source that is not an object", "value": changed(source="sc01"),
     "error": "source must be an object"},
    {"name": "a source with an unknown key",
     "value": changed(source={"artifact_type": "scene-plot", "id": "sc01",
                              "content_sha256": "b" * 64, "chapter": "ch1"}),
     "error": "source has unknown keys: ['chapter']"},
    {"name": "a source that says what it is but not which one",
     "value": changed(source={"artifact_type": "scene-plot", "id": "  ",
                              "content_sha256": "b" * 64}),
     "error": "source.id must be a non-empty string"},
    {"name": "a source with no hash",
     "value": changed(source={"artifact_type": "scene-plot", "id": "sc01"}),
     "error": "source.content_sha256 must be the hash the upstream artifact was approved under"},
    {"name": "a source whose hash is not a hash",
     "value": changed(source={"artifact_type": "scene-plot", "id": "sc01",
                              "content_sha256": "not-a-hash"}),
     "error": "source.content_sha256 must be the hash the upstream artifact was approved under"},
    {"name": "a source with an empty shot id",
     "value": changed(source={"artifact_type": "scene-plot", "id": "sc01",
                              "content_sha256": "b" * 64, "shot_id": "  "}),
     "error": "source.shot_id must be a non-empty string when present"},
]

# The approval is reported apart from the contract, so a caller can tell an
# invalid plot from an unapproved one.
APPROVAL_CASES: list[dict[str, Any]] = [
    {"name": "an approval that holds", "value": approve(plot()), "approved": True, "error": None},
    {"name": "no approval at all", "value": plot(), "approved": False, "error": None},
    {"name": "an approval with a loose time",
     "value": {**plot(), "approved": {"by": "someone", "at": "yesterday",
                                      "content_sha256": "0" * 64}},
     "approved": False, "error": "must be an RFC3339 UTC timestamp"},
    {"name": "an approval that names nobody",
     "value": {**plot(), "approved": {"by": "  ", "at": "2026-09-11T00:00:00Z",
                                      "content_sha256": "0" * 64}},
     "approved": False, "error": "approved.by must be a non-empty string"},
    {"name": "an approval with no content hash",
     "value": {**plot(), "approved": {"by": "someone", "at": "2026-09-11T00:00:00Z"}},
     "approved": False, "error": "must be the sha256 of the plot without its approval"},
    {"name": "an approval with an unknown key",
     "value": {**plot(), "approved": {"by": "someone", "at": "2026-09-11T00:00:00Z",
                                      "content_sha256": "0" * 64, "scope": "all"}},
     "approved": False, "error": "approved has unknown keys"},
]


def record() -> dict[str, Any]:
    """A retrieval record that answers the contract."""

    return {
        "artifact_type": "prompt-retrieval-record",
        "pack_state": "the resolved pack state this retrieval ran under",
        "elements": [
            {
                "element": "pose",
                "queries": ["standing at a counter", "pouring"],
                "inspected_records": ["pose/standing-at-work-surface"],
                "outcome": "adopted",
                "adopted_records": ["pose/standing-at-work-surface"],
            },
            {
                "element": "light",
                "queries": ["bright window at the far end"],
                "inspected_records": [],
                "outcome": "composed",
                "composed_wording": "the window at the far end is bright and the near end stays dim",
                "reason": "no record carries a near-to-far falloff across one room",
            },
        ],
    }


def element(index: int, **edits: Any) -> dict[str, Any]:
    value = record()
    value["elements"][index].update(copy.deepcopy(edits))
    return value


def drop(index: int, key: str) -> dict[str, Any]:
    value = record()
    value["elements"][index].pop(key, None)
    return value


RECORD_CASES: list[dict[str, Any]] = [
    {"name": "the contract answered", "value": record(), "error": None},
    {"name": "the wrong artifact type",
     "value": {**record(), "artifact_type": "prompt-plot"},
     "error": "artifact_type must be 'prompt-retrieval-record'"},
    {"name": "an empty pack state", "value": {**record(), "pack_state": "  "},
     "error": "pack_state must be a non-empty string when present"},
    {"name": "no elements", "value": {**record(), "elements": []},
     "error": "elements must be a non-empty array"},
    {"name": "an element with an unknown key", "value": element(0, tier="curated"),
     "error": "has unknown keys"},
    {"name": "two elements with one name", "value": element(1, element="pose"),
     "error": "repeats 'pose'"},
    {"name": "an element that searched for nothing", "value": element(0, queries=[]),
     "error": "element 'pose': queries must not be empty"},
    {"name": "an element with no outcome", "value": drop(0, "outcome"),
     "error": "element 'pose' has no outcome; mark it with --adopted ID"},
    {"name": "an adopted element naming no record", "value": drop(0, "adopted_records"),
     "error": "element 'pose': adopted_records is required"},
    {"name": "an adopted element that also composed wording",
     "value": element(0, composed_wording="something"),
     "error": "composed_wording does not belong to an adopted outcome"},
    {"name": "an adopted element that gives a reason",
     "value": element(0, reason="because"),
     "error": "reason does not belong to an adopted outcome"},
    {"name": "a composed element with no wording", "value": drop(1, "composed_wording"),
     "error": "composed_wording is required when outcome is 'composed'"},
    {"name": "a composed element with no reason", "value": drop(1, "reason"),
     "error": "reason is required when outcome is 'composed'"},
    {"name": "a composed element that also adopted a record",
     "value": element(1, adopted_records=["light/bright-far-window"]),
     "error": "adopted_records does not belong to a composed outcome"},
    {"name": "an adopted record that was never inspected",
     "value": element(0, adopted_records=["pose/standing-at-work-surface", "pose/leaning"]),
     "error": "element 'pose': adopted records were not inspected: ['pose/leaning']"},
]


def check(name: str, report: dict[str, Any], expected: str | None,
          failures: list[str]) -> dict[str, Any]:
    joined = "; ".join(report["errors"])
    if expected is None:
        if report["errors"]:
            failures.append(f"{name}: expected no error, got {joined}")
    elif expected not in joined:
        failures.append(f"{name}: expected {expected!r}, got {joined or 'no error'}")
    return {"case": name, "ok": report["ok"], "errors": report["errors"]}


def main() -> int:
    failures: list[str] = []
    results: list[dict[str, Any]] = []

    for case in PLOT_CASES:
        report = validate_prompt_plot(case["value"])
        results.append(check(f"plot: {case['name']}", report, case["error"], failures))
        if "source" in case and report["source"] != case["source"]:
            failures.append(
                f"plot: {case['name']}: the report gives source {report['source']!r} where the "
                f"plot carries {case['source']!r}"
            )

    for case in APPROVAL_CASES:
        report = validate_prompt_plot(case["value"])
        name = f"plot approval: {case['name']}"
        joined = "; ".join(report["approval_errors"])
        expected = case["error"]
        results.append({"case": name, "approved": report["approved"],
                        "approval_errors": report["approval_errors"]})
        if expected is None:
            if report["approval_errors"]:
                failures.append(f"{name}: expected no approval error, got {joined}")
        elif expected not in joined:
            failures.append(f"{name}: expected {expected!r}, got {joined or 'no error'}")
        if report["approved"] != case["approved"]:
            failures.append(
                f"{name}: expected approved={case['approved']}, got {report['approved']}"
            )

    # An approval binds the bytes it was given, and an edit after it breaks it.
    signed = approve(plot())
    edited = copy.deepcopy(signed)
    edited["derived"][0]["statement"] = "three lanterns on the bench"
    report = validate_prompt_plot(edited)
    results.append({"case": "plot approval: an edit after the approval",
                    "approved": report["approved"]})
    if report["approved"]:
        failures.append("plot approval: an edit after the approval still held")
    if not any("changed after it was approved" in item for item in report["approval_errors"]):
        failures.append(
            f"plot approval: an edit after the approval reported {report['approval_errors']}"
        )

    # The source is part of the plot, so the approval covers it: a plot re-pointed
    # at a different upstream artifact after approval is a different plot.
    sourced = approve(changed(source={"artifact_type": "scene-plot", "id": "sc01",
                                      "content_sha256": "b" * 64}))
    report = validate_prompt_plot(sourced)
    results.append({"case": "plot approval: a source under an approval",
                    "approved": report["approved"], "source": report["source"]})
    if not report["approved"]:
        failures.append(f"plot approval: a source under an approval: {report['approval_errors']}")
    # The report is what the package manifest records. A case that reads the
    # value and asserts nothing about it carries the defect in its own output.
    if report["source"] != sourced["source"]:
        failures.append(
            "plot approval: a source under an approval: the report gives "
            f"{report['source']!r} where the plot carries {sourced['source']!r}"
        )
    repointed = copy.deepcopy(sourced)
    repointed["source"]["content_sha256"] = "c" * 64
    report = validate_prompt_plot(repointed)
    results.append({"case": "plot approval: the source repointed after approval",
                    "approved": report["approved"]})
    if report["approved"]:
        failures.append("plot approval: the source repointed after approval still held")

    # The counts a caller reads back are what the plot actually carries.
    report = validate_prompt_plot(plot())
    counted = {"beats": report["beats"], "visible_beats": report["visible_beats"],
               "derived": report["derived"]}
    results.append({"case": "plot: what the report counts", **counted})
    if counted != {"beats": 2, "visible_beats": 1, "derived": 5}:
        failures.append(f"plot: what the report counts: got {counted}")

    for case in RECORD_CASES:
        report = validate_prompt_retrieval_record(case["value"])
        results.append(check(f"retrieval: {case['name']}", report, case["error"], failures))

    report = validate_prompt_retrieval_record(record())
    counted = {"elements": report["elements"], "adopted": report["adopted"],
               "composed": report["composed"]}
    results.append({"case": "retrieval: what the report counts", **counted})
    if counted != {"elements": 2, "adopted": 1, "composed": 1}:
        failures.append(f"retrieval: what the report counts: got {counted}")

    print(json.dumps({
        "ok": not failures,
        "checks": len(results),
        "results": results,
        "errors": failures,
    }, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
