#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

from prompt_plot import load_prompt_plot
from prompt_retrieval import load_prompt_retrieval_record
from validate_prompt_semantics import validate_plan


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_artifact(source: Path, destination: Path) -> dict[str, Any]:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return {"path": destination.name, "bytes": destination.stat().st_size, "sha256": sha256(destination)}


def selected_reference_count(path: Path | None) -> int:
    """Count `reference_items` in a document that answers the reference-use-plan schema."""

    if path is None:
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"reference use plan must be a JSON object: {path}")
    artifact_type = data.get("artifact_type")
    if artifact_type != "reference-use-plan":
        raise ValueError(
            "reference use plan artifact_type must be 'reference-use-plan', "
            f"got {artifact_type!r}: {path}"
        )
    items = data.get("reference_items")
    if not isinstance(items, list):
        raise ValueError(f"reference use plan reference_items must be a list: {path}")
    return len(items)


def resolved_inputs(args: argparse.Namespace) -> dict[str, Path]:
    """Every path the run reads, resolved, with the required ones present."""

    named = {
        "--prompt": args.prompt,
        "--negative": args.negative,
        "--reference-use-plan": args.reference_use_plan,
        "--surface-lighting-plan": args.surface_lighting_plan,
        "--prepared-reference-set": args.prepared_reference_set,
        "--reference-preamble": args.reference_preamble,
        "--semantic-plan": args.semantic_plan,
        "--revision-contract": args.revision_contract,
        "--retrieval-record": args.retrieval_record,
        "--plot": args.plot,
    }
    inputs: dict[str, Path] = {}
    for flag, value in named.items():
        if value is None:
            continue
        path = Path(value).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"{flag} does not exist: {path}")
        inputs[flag] = path
    return inputs


def check_no_input_under_output(inputs: dict[str, Path], out: Path) -> None:
    for flag, path in inputs.items():
        if path == out or out in path.parents:
            raise ValueError(
                f"{flag} is inside the output directory and would be destroyed: {path}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a conditional prompt-only or generation-ready artifact package.")
    parser.add_argument("--prompt", required=True, type=Path)
    parser.add_argument("--negative", type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--reference-use-plan", type=Path)
    parser.add_argument("--surface-lighting-plan", type=Path)
    parser.add_argument("--prepared-reference-set", type=Path)
    parser.add_argument("--reference-preamble", type=Path)
    parser.add_argument("--semantic-plan", type=Path, help="Structured anatomy and camera plan to validate before artifact publication")
    parser.add_argument("--revision-contract", type=Path, help="Explicit edit/explore/retarget baseline and candidate semantics")
    parser.add_argument("--require-semantic-plan", action="store_true", help="Fail when no semantic plan is supplied")
    parser.add_argument("--prepare-for-generation", action="store_true")
    parser.add_argument("--retrieval-record", type=Path, help="Record of the catalog and prompt-vocabulary lookups behind this prompt")
    parser.add_argument("--retrieval-unavailable", help="Reason retrieval could not be run; refuses --prepare-for-generation")
    parser.add_argument("--plot", type=Path, help="Optional for drafts; an approved plot is required for generation-ready packaging")
    parser.add_argument("--overwrite", action="store_true", help="Replace a non-empty output directory that already exists")
    args = parser.parse_args()

    out = args.out_dir.resolve()
    inputs = resolved_inputs(args)
    check_no_input_under_output(inputs, out)

    plot_value = json.loads(args.plot.read_text(encoding="utf-8")) if args.plot else None
    plot_report = load_prompt_plot(args.plot) if args.plot else None
    plot = {"settled": plot_report is not None, "approved": bool(plot_report and plot_report["approved"])}
    if plot_report:
        plot.update({key: plot_report[key] for key in ("beats", "visible_beats", "derived", "source")})
        if plot_report["approval_errors"]:
            raise ValueError("invalid supplied approval: " + "; ".join(plot_report["approval_errors"]))
    if args.prepare_for_generation and not plot["approved"]:
        raise ValueError("generation-ready packaging requires an approved plot")

    if args.retrieval_record and args.retrieval_unavailable:
        raise ValueError("--retrieval-record and --retrieval-unavailable are exclusive")
    retrieval: dict[str, Any]
    if args.retrieval_record:
        report = load_prompt_retrieval_record(args.retrieval_record)
        record_value = json.loads(args.retrieval_record.read_text(encoding="utf-8"))
        if args.prepare_for_generation:
            from prompt_retrieval import require_generation_retrieval
            require_generation_retrieval(record_value, prompt=args.prompt.read_text(encoding="utf-8"), plot=plot_value)
        retrieval = {
            "settled": record_value.get("settled") is True,
            "elements": report["elements"],
            "adopted": report["adopted"],
            "composed": report["composed"],
        }
    elif args.retrieval_unavailable:
        reason = args.retrieval_unavailable.strip()
        if not reason:
            raise ValueError("--retrieval-unavailable requires a reason")
        retrieval = {"settled": False, "reason": reason}
        if args.prepare_for_generation:
            raise ValueError(
                "generation-ready packaging requires a retrieval record; "
                f"retrieval was reported unavailable: {reason}"
            )
    else:
        raise ValueError(
            "prompt wording requires a retrieval record: pass --retrieval-record, "
            "or state why retrieval could not be run with --retrieval-unavailable"
        )

    revision_report = None
    if args.revision_contract:
        from revision_contract import validate_revision
        revision_report = validate_revision(json.loads(args.revision_contract.read_text(encoding="utf-8")))
        if not revision_report["ok"]:
            raise ValueError("revision preflight failed: " + "; ".join(revision_report["errors"]))

    semantic_report: dict[str, Any] | None = None
    if args.require_semantic_plan and args.semantic_plan is None:
        raise ValueError("--require-semantic-plan requires --semantic-plan")
    if args.semantic_plan is not None:
        plan = json.loads(args.semantic_plan.read_text(encoding="utf-8"))
        if not isinstance(plan, dict):
            raise ValueError("semantic plan root must be an object")
        semantic_report = validate_plan(plan)
        if not semantic_report.get("ok"):
            raise ValueError(
                "prompt semantic preflight failed: "
                + "; ".join(str(value) for value in semantic_report.get("errors", []))
            )

    ref_count = selected_reference_count(args.reference_use_plan)
    if args.prepare_for_generation and ref_count:
        if not args.prepared_reference_set:
            raise ValueError("generation-ready reference transport requires --prepared-reference-set")
        if not args.reference_preamble:
            raise ValueError("generation-ready reference transport requires --reference-preamble")

    if out.exists():
        if not out.is_dir():
            raise ValueError(f"output path exists and is not a directory: {out}")
        if any(out.iterdir()) and not args.overwrite:
            raise ValueError(f"output directory is not empty; pass --overwrite to replace it: {out}")

    staging = out.parent / f".{out.name}.partial-{os.getpid()}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        included: list[dict[str, Any]] = []
        omitted: list[dict[str, str]] = []
        included.append(copy_artifact(args.prompt, staging / "final-prompt.txt"))
        if args.negative:
            included.append(copy_artifact(args.negative, staging / "final-negative.txt"))
        if semantic_report is not None:
            semantic_path = staging / "semantic-preflight.json"
            semantic_path.write_text(json.dumps(semantic_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            included.append({"path": semantic_path.name, "bytes": semantic_path.stat().st_size, "sha256": sha256(semantic_path)})

        if args.reference_use_plan and ref_count > 0:
            included.append(copy_artifact(args.reference_use_plan, staging / "reference-use-plan.json"))
        else:
            omitted.append({"artifact": "reference-use-plan.json", "reason": "no selected references"})

        if args.revision_contract:
            included.append(copy_artifact(args.revision_contract, staging / "revision-contract.json"))
            (staging / "revision-report.json").write_text(json.dumps(revision_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            included.append({"path": "revision-report.json", "bytes": (staging / "revision-report.json").stat().st_size, "sha256": sha256(staging / "revision-report.json")})
        if args.plot:
            included.append(copy_artifact(args.plot, staging / "prompt-plot.json"))
        else:
            omitted.append({"artifact": "prompt-plot.json", "reason": "unapproved draft; no plot supplied"})
        if args.retrieval_record:
            included.append(copy_artifact(args.retrieval_record, staging / "prompt-retrieval-record.json"))
        else:
            omitted.append({"artifact": "prompt-retrieval-record.json", "reason": retrieval["reason"]})

        if args.surface_lighting_plan:
            included.append(copy_artifact(args.surface_lighting_plan, staging / "surface-lighting-plan.json"))
        else:
            omitted.append({"artifact": "surface-lighting-plan.json", "reason": "no explicit lighting or material transfer contract"})

        if args.prepare_for_generation:
            if args.prepared_reference_set:
                included.append(copy_artifact(args.prepared_reference_set, staging / "prepared-reference-set.json"))
            if args.reference_preamble:
                included.append(copy_artifact(args.reference_preamble, staging / "reference-preamble.txt"))
        else:
            omitted.extend([
                {"artifact": "prepared-reference-set.json", "reason": "not preparing target-specific generation transport"},
                {"artifact": "reference-preamble.txt", "reason": "references are not being sent to a model"},
            ])

        manifest = {
            "artifact_type": "prompt-artifact-package",
            "mode": "generation-ready" if args.prepare_for_generation else "prompt-only",
            "approval_scope": "preparation-only" if args.prepare_for_generation else "draft-unapproved",
            "execution_authorized": False,
            "canonical_update_authorized": False,
            "selected_reference_count": ref_count,
            "plot": plot,
            "retrieval": retrieval,
            "revision": revision_report,
            "included": included,
            "omitted": omitted,
        }
        (staging / "prompt-artifact-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    if out.exists():
        shutil.rmtree(out)
    staging.rename(out)
    print(json.dumps({"ok": True, "manifest": manifest}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
