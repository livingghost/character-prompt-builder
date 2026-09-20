#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prompt_plot import content_sha256
from prompt_retrieval import settle_retrieval_record

NL = chr(10)

INVALID_SEMANTIC_PLAN = {
    "structure_plan": {
        "expected_counts": {"arm": 2},
        "assigned_structures": [
            {"structure_id": "left-arm", "kind": "arm", "side": "left", "owner_id": "C01"},
            {"structure_id": "left-arm-copy", "kind": "arm", "side": "left", "owner_id": "C01"},
            {"structure_id": "right-arm", "kind": "arm", "side": "right", "owner_id": "C01"},
        ],
        "primary_actions": [],
    },
    "camera": {
        "angle": "worms-eye", "shot_scale": "wide", "distance": "distant",
        "camera_height": "eye", "pitch": "level", "subject_frame_occupancy": 0.2,
    },
}

RETRIEVAL_RECORD = {
    "artifact_type": "prompt-retrieval-record",
    "elements": [
        {
            "element": "pose",
            "queries": ["standing arms at sides"],
            "inspected_records": ["MOD-POSE-EXAMPLE"],
            "outcome": "adopted",
            "adopted_record": "MOD-POSE-EXAMPLE",
        },
        {
            "element": "camera",
            "queries": ["knee up front view"],
            "inspected_records": [],
            "outcome": "composed",
            "composed_wording": "a knee-up view from the front",
            "reason": "no retrieved record covers this framing",
        },
    ],
}

PLOT = {
    "artifact_type": "prompt-plot",
    "story": [
        {"id": "s1", "beat": "The subject stands still for a reference photograph.", "visibility": "visible"},
        {"id": "s2", "beat": "The room beyond the backdrop is a working studio.", "visibility": "context"},
    ],
    "derived": [
        {"kind": "shows", "statement": "the subject and a plain backdrop", "from": ["s1"]},
        {"kind": "placement", "statement": "the subject stands centred, facing the camera", "from": ["s1"]},
        {"kind": "composition", "statement": "a knee-up view at eye height", "from": ["s1"]},
        {"kind": "must_preserve", "statement": "the subject own proportions", "from": ["s1"]},
        {"kind": "free", "statement": "the backdrop exact tone"},
    ],
}

APPROVED_PLOT = {**PLOT, "approved": {
    "by": "the person who owns the brief",
    "at": "2026-09-11T00:00:00Z",
    "content_sha256": content_sha256(PLOT),
}}

PREVIOUS_PACKAGE = "previous package" + NL
UNAVAILABLE = "no pack state is resolvable in this environment"


def run(script: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *arguments], text=True, capture_output=True, check=False
    )


def main() -> int:
    script = Path(__file__).with_name("build_prompt_artifacts.py")
    with tempfile.TemporaryDirectory(prefix="cpb-prompt-artifacts-") as temp:
        root = Path(temp)
        prompt = root / "prompt.txt"
        prompt.write_text("A coherent prompt." + NL, encoding="utf-8")
        record = root / "retrieval-record.json"
        record.write_text(json.dumps(settle_retrieval_record(RETRIEVAL_RECORD, prompt=prompt.read_text(encoding="utf-8"), plot=PLOT), ensure_ascii=False, indent=2) + NL, encoding="utf-8")
        plot = root / "plot.json"
        plot.write_text(json.dumps(PLOT, ensure_ascii=False, indent=2) + NL, encoding="utf-8")
        approved_plot = root / "approved-plot.json"
        approved_plot.write_text(json.dumps(APPROVED_PLOT, ensure_ascii=False, indent=2) + NL, encoding="utf-8")
        answered = ("--retrieval-record", str(record), "--plot", str(approved_plot))
        unapproved = ("--retrieval-record", str(record), "--plot", str(plot))

        out = root / "out"
        proc = run(script, "--prompt", str(prompt), "--out-dir", str(out), *answered)
        files = sorted(path.name for path in out.iterdir()) if out.is_dir() else []
        expected = ["final-prompt.txt", "prompt-artifact-manifest.json", "prompt-plot.json", "prompt-retrieval-record.json"]
        minimal_ok = proc.returncode == 0 and files == expected

        invalid = root / "invalid-semantic.json"
        invalid.write_text(json.dumps(INVALID_SEMANTIC_PLAN, ensure_ascii=False, indent=2) + NL, encoding="utf-8")
        blocked = run(
            script, "--prompt", str(prompt), "--out-dir", str(root / "blocked"), *answered,
            "--semantic-plan", str(invalid), "--require-semantic-plan",
        )

        # A prompt begins from a plot, and generation-ready needs it approved.
        no_plot = run(script, "--prompt", str(prompt), "--out-dir", str(root / "no-plot"),
                      "--retrieval-record", str(record))
        unapproved_package = run(
            script, "--prompt", str(prompt), "--out-dir", str(root / "unapproved"), *unapproved,
        )
        approved_generation = run(
            script, "--prompt", str(prompt), "--out-dir", str(root / "approved-gen"), *answered,
            "--prepare-for-generation",
        )
        invented = {
            "artifact_type": "prompt-plot",
            "story": PLOT["story"],
            "derived": PLOT["derived"][:-1] + [
                {"kind": "shows", "statement": "a kettle on the bench", "from": ["s2"]},
                {"kind": "free", "statement": "the backdrop"},
            ],
        }
        invented["approved"] = APPROVED_PLOT["approved"]
        invented_path = root / "invented-approved.json"
        invented_path.write_text(json.dumps(invented, ensure_ascii=False) + NL, encoding="utf-8")
        invented_run = run(script, "--prompt", str(prompt), "--out-dir", str(root / "invented"),
                           "--retrieval-record", str(record), "--plot", str(invented_path))
        targeted = root / "targeted-plot.json"
        targeted.write_text(json.dumps({**APPROVED_PLOT, "target": "some-interface"}, ensure_ascii=False) + NL, encoding="utf-8")
        targeted_run = run(script, "--prompt", str(prompt), "--out-dir", str(root / "targeted"),
                           "--retrieval-record", str(record), "--plot", str(targeted))
        plot_counts = json.loads(proc.stdout)["manifest"]["plot"] if proc.returncode == 0 else None
        duplicate = root / "duplicate-source-plot.json"
        duplicate.write_text(json.dumps({**APPROVED_PLOT, "derived": [
            {**APPROVED_PLOT["derived"][0], "from": ["s1", "s1"]},
        ] + APPROVED_PLOT["derived"][1:]}, ensure_ascii=False) + NL, encoding="utf-8")
        duplicate_run = run(script, "--prompt", str(prompt), "--out-dir", str(root / "duplicate"),
                            "--retrieval-record", str(record), "--plot", str(duplicate))
        loose_time = root / "loose-time-plot.json"
        loose_time.write_text(json.dumps({**PLOT, "approved": {"by": "someone", "at": "yesterday"}},
                                         ensure_ascii=False) + NL, encoding="utf-8")
        loose_time_run = run(script, "--prompt", str(prompt), "--out-dir", str(root / "loose-time"),
                             "--retrieval-record", str(record), "--plot", str(loose_time))
        plot_ok = (
            no_plot.returncode == 0
            and unapproved_package.returncode == 0
            and approved_generation.returncode == 0
            and invented_run.returncode != 0
            and targeted_run.returncode != 0
            and duplicate_run.returncode != 0
            and loose_time_run.returncode != 0
            and plot_counts == {"settled": True, "beats": 2, "visible_beats": 1, "derived": 5,
                            "source": None, "approved": True}
        )

        # The retrieval gate is answered or the run is refused.
        no_answer = run(script, "--prompt", str(prompt), "--out-dir", str(root / "no-answer"), "--plot", str(approved_plot))
        unavailable = run(
            script, "--prompt", str(prompt), "--out-dir", str(root / "unavailable"),
            "--retrieval-unavailable", UNAVAILABLE, "--plot", str(approved_plot),
        )
        unavailable_settled = None
        if unavailable.returncode == 0:
            unavailable_settled = json.loads(unavailable.stdout)["manifest"]["retrieval"]
        unavailable_generation = run(
            script, "--prompt", str(prompt), "--out-dir", str(root / "unavailable-gen"),
            "--retrieval-unavailable", UNAVAILABLE, "--plot", str(approved_plot), "--prepare-for-generation",
        )
        both = run(
            script, "--prompt", str(prompt), "--out-dir", str(root / "both"), *answered,
            "--retrieval-unavailable", UNAVAILABLE,
        )
        malformed = root / "malformed-record.json"
        malformed.write_text(json.dumps({
            "artifact_type": "prompt-retrieval-record",
            "elements": [{"element": "pose", "queries": ["x"], "outcome": "composed"}],
        }) + NL, encoding="utf-8")
        malformed_run = run(
            script, "--prompt", str(prompt), "--out-dir", str(root / "malformed"),
            "--retrieval-record", str(malformed),
        )
        counted_retrieval = json.loads(proc.stdout)["manifest"]["retrieval"] if proc.returncode == 0 else None
        gate_ok = (
            no_answer.returncode != 0
            and unavailable.returncode == 0
            and unavailable_settled == {"settled": False, "reason": UNAVAILABLE}
            and unavailable_generation.returncode != 0
            and both.returncode != 0
            and malformed_run.returncode != 0
            and counted_retrieval == {"settled": True, "elements": 2, "adopted": 1, "composed": 1}
        )

        # A rejected run leaves the previous package and the inputs alone.
        kept = root / "kept"
        kept.mkdir()
        survivor = kept / "keep.txt"
        survivor.write_text(PREVIOUS_PACKAGE, encoding="utf-8")
        missing_input = run(script, "--prompt", str(root / "absent.txt"), "--out-dir", str(kept), *answered)
        survived = survivor.is_file() and survivor.read_text(encoding="utf-8") == PREVIOUS_PACKAGE

        # An input inside the output directory is refused rather than destroyed.
        nested_dir = root / "nested"
        nested_dir.mkdir()
        nested_prompt = nested_dir / "prompt.txt"
        nested_prompt.write_text("A prompt inside the output directory." + NL, encoding="utf-8")
        nested = run(script, "--prompt", str(nested_prompt), "--out-dir", str(nested_dir), *answered)
        nested_ok = nested.returncode != 0 and nested_prompt.is_file()

        # Replacing a package that is already there is an explicit request.
        refused = run(script, "--prompt", str(prompt), "--out-dir", str(kept), *answered)
        allowed = run(script, "--prompt", str(prompt), "--out-dir", str(kept), "--overwrite", *answered)
        overwrite_ok = refused.returncode != 0 and allowed.returncode == 0

        # A plan carrying reference_items keeps its count, and a document that
        # does not answer the schema is an error rather than a plan with none.
        plan = root / "reference-use-plan.json"
        plan.write_text(json.dumps({
            "artifact_type": "reference-use-plan",
            "reference_items": [{"record_id": "R1"}, {"record_id": "R2"}],
        }, ensure_ascii=False) + NL, encoding="utf-8")
        with_refs = run(
            script, "--prompt", str(prompt), "--out-dir", str(root / "with-refs"), *answered,
            "--reference-use-plan", str(plan),
        )
        counted = -1
        carried = False
        if with_refs.returncode == 0:
            manifest = json.loads(with_refs.stdout)["manifest"]
            counted = manifest["selected_reference_count"]
            carried = (root / "with-refs" / "reference-use-plan.json").is_file()

        unknown = root / "unknown-plan.json"
        unknown.write_text(json.dumps({"selected_references": [{"record_id": "R1"}]}) + NL, encoding="utf-8")
        unknown_run = run(
            script, "--prompt", str(prompt), "--out-dir", str(root / "unknown"), *answered,
            "--reference-use-plan", str(unknown),
        )
        references_ok = counted == 2 and carried and unknown_run.returncode != 0

        errors: list[str] = []
        if not minimal_ok:
            errors.append(f"unexpected minimal prompt-only package: return={proc.returncode}, files={files}, stderr={proc.stderr}")
        if blocked.returncode == 0:
            errors.append("an invalid semantic plan was published")
        if not plot_ok:
            errors.append(
                "plot gate wrong: "
                f"no_plot={no_plot.returncode}, unapproved_package={unapproved_package.returncode}, "
                f"approved_generation={approved_generation.returncode}, invented={invented_run.returncode}, "
                f"targeted={targeted_run.returncode}, duplicate={duplicate_run.returncode}, "
                f"loose_time={loose_time_run.returncode}, counts={plot_counts}"
            )
        if not gate_ok:
            errors.append(
                "retrieval gate wrong: "
                f"no_answer={no_answer.returncode}, unavailable={unavailable.returncode}, "
                f"settled={unavailable_settled}, unavailable_generation={unavailable_generation.returncode}, "
                f"both={both.returncode}, malformed={malformed_run.returncode}, counted={counted_retrieval}"
            )
        if not survived:
            errors.append("a rejected run destroyed the existing output directory")
        if not nested_ok:
            errors.append("an input inside the output directory was not refused")
        if not overwrite_ok:
            errors.append(f"overwrite handling wrong: refused={refused.returncode}, allowed={allowed.returncode}")
        if not references_ok:
            errors.append(
                f"reference plan handling wrong: counted={counted}, carried={carried}, "
                f"unknown_refused={unknown_run.returncode != 0}"
            )

        report = {
            "ok": not errors,
            "errors": errors,
            "stats": {
                "files": files,
                "invalid_semantic_plan_blocked": blocked.returncode != 0,
                "plot_required": no_plot.returncode != 0,
                "unapproved_plot_refused": unapproved_package.returncode != 0,
                "approved_plot_allows_generation": approved_generation.returncode == 0,
                "context_beat_as_source_refused": invented_run.returncode != 0,
                "plot_naming_a_target_refused": targeted_run.returncode != 0,
                "repeated_source_refused": duplicate_run.returncode != 0,
                "loose_approval_time_refused": loose_time_run.returncode != 0,
                "plot_counts": plot_counts,
                "retrieval_required": no_answer.returncode != 0,
                "retrieval_unavailable_recorded": unavailable_settled,
                "retrieval_unavailable_blocks_generation": unavailable_generation.returncode != 0,
                "retrieval_flags_exclusive": both.returncode != 0,
                "malformed_record_refused": malformed_run.returncode != 0,
                "retrieval_counts": counted_retrieval,
                "existing_output_survived_rejected_run": survived,
                "input_under_output_refused": nested_ok,
                "overwrite_requires_flag": overwrite_ok,
                "reference_items_counted": counted,
                "reference_plan_carried": carried,
                "unknown_plan_shape_refused": unknown_run.returncode != 0,
            },
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
