#!/usr/bin/env python3
"""Summarize recorded repeated failures and retain attributed repair hypotheses.

This reads the existing production evidence. It neither retries nor edits work,
chooses a model, rewrites identity, or grants execution/canonical authority.
"""

from __future__ import annotations
import argparse
from collections import defaultdict
import json
from pathlib import Path
from typing import Sequence

import artifact_review
import material_support as m


def summarize(reports: list[dict], hypotheses: list[dict] | None = None) -> dict:
    seen = set()
    groups = {}
    inputs = []
    for report in reports:
        run = report["run"]
        if run in seen:
            raise ValueError("one production run may be analyzed only once")
        seen.add(run)
        inputs.append(
            {
                "run": run,
                "input_sha256": report["input_sha256"],
                "receipt_head": report["receipt_head"],
                "current": report["current"],
                "changed_dependencies": report["changed_dependencies"],
            }
        )
        criteria = {c["id"]: c for c in report["criteria"]}
        for candidate in report["candidates"]:
            if not candidate["reviews"]:
                continue
            latest = candidate["reviews"][-1]
            review = latest["review"]
            for check in review["checks"]:
                if check["verdict"] != "fail":
                    continue
                criterion = criteria.get(check["criterion"])
                if criterion is None:
                    raise ValueError("review names an unknown criterion")
                # Identical local IDs do not imply identical requirements across tasks.
                requirement = {k: v for k, v in criterion.items() if k != "id"}
                group_id = m.content_hash(requirement)
                group = groups.setdefault(
                    group_id, {"group_id": group_id, "requirement": requirement, "occurrences": []}
                )
                observations = review.get("observations", [])
                selected = []
                for i in check["observation_indices"]:
                    if type(i) is not int or not 0 <= i < len(observations):
                        raise ValueError("review observation index is out of range")
                    selected.append(observations[i])
                group["occurrences"].append(
                    {
                        "run": run,
                        "candidate": candidate["id"],
                        "review_receipt": latest["receipt"],
                        "criterion": check["criterion"],
                        "reason": check["reason"],
                        "observations": selected,
                        "current": report["current"],
                    }
                )
    for group in groups.values():
        group["run_count"] = len({x["run"] for x in group["occurrences"]})
        group["candidate_count"] = len({(x["run"], x["candidate"]) for x in group["occurrences"]})
    proposed = []
    for row in hypotheses or []:
        m.exact(
            row,
            {
                "hypothesis_id",
                "group_ids",
                "explanation",
                "alternatives",
                "proposed_change",
                "protected_requirements",
                "acceptance_check",
                "scope",
            },
            label="repair hypothesis",
        )
        m.text(row["hypothesis_id"], "hypothesis ID")
        m.strings(row["group_ids"], "hypothesis groups", nonempty=True)
        if set(row["group_ids"]) - groups.keys():
            raise ValueError("hypothesis is not linked to observed failed criteria")
        for key in ["explanation", "proposed_change", "acceptance_check", "scope"]:
            m.text(row[key], key)
        m.strings(row["alternatives"], "alternative explanations")
        m.strings(row["protected_requirements"], "protected requirements")
        proposed.append({**row, "status": "hypothesis-not-established"})
    m.indexed(proposed, "hypothesis_id", "hypotheses")
    return m.sealed(
        {
            "artifact_type": "repair-analysis",
            "inputs": inputs,
            "failure_groups": sorted(groups.values(), key=lambda g: g["group_id"]),
            "hypotheses": proposed,
            "execution_authorized": False,
            "canon_changed": False,
            "limits": [
                "The latest review per candidate is analyzed; prior review receipts remain in the original run.",
                "Multiple candidates in one run are not independent trials.",
                "Repeated failure is not proof of its cause or permission to remove a protected requirement.",
                "No count threshold mandates a genre, simplification, model change, or retry.",
            ],
        }
    )


def render(result: dict) -> str:
    """Present the recorded evidence and hypotheses without hiding their basis.

    This is a deterministic view of the analysis, not a new interpretation of
    the observations. Structured locators remain visible even when they name a
    media interval or region instead of a prose passage.
    """

    def data_block(value: object) -> list[str]:
        # Pick a fence longer than any run in supplied evidence text. Evidence
        # must stay data, including text that itself contains Markdown fences.
        payload = json.dumps(value, ensure_ascii=False, indent=2)
        import re

        longest = max((len(match) for match in re.findall(r"`+", payload)), default=0)
        fence = "`" * max(3, longest + 1)
        return [fence + "json", payload, fence, ""]

    lines = [
        "# Recorded failure analysis",
        "",
        "This is a derived report, not execution permission or a canonical change.",
        "Observations, reviewer interpretations and proposed causes remain separate.",
        "",
        "## Source runs and freshness",
        "",
    ]
    for source in result["inputs"]:
        lines.extend(
            [
                "### Run " + source["run"],
                "",
                "Input SHA-256: " + source["input_sha256"],
                "",
                "Review receipt head: " + source["receipt_head"],
                "",
                "Current source commitments: " + ("yes" if source["current"] else "no"),
                "",
                "#### Changed dependencies",
                "",
            ]
        )
        if source["changed_dependencies"]:
            lines.extend(data_block(source["changed_dependencies"]))
        else:
            lines.extend(["No changed dependencies were reported.", ""])

    lines.extend(["## Recorded failure groups", ""])
    if not result["failure_groups"]:
        lines.extend(["No failed criterion was present in the selected latest reviews.", ""])
    for number, group in enumerate(result["failure_groups"], 1):
        lines.extend(
            [
                f"### Failure group {number}",
                "",
                "Group ID: " + group["group_id"],
                "",
                f"Distinct runs: {group['run_count']}",
                "",
                f"Distinct candidates: {group['candidate_count']}",
                "",
                "#### Complete criterion",
                "",
            ]
        )
        lines.extend(data_block(group["requirement"]))
        for occurrence_number, occurrence in enumerate(group["occurrences"], 1):
            lines.extend(
                [
                    f"#### Occurrence {occurrence_number}",
                    "",
                    "Run: " + occurrence["run"],
                    "",
                    "Candidate: " + occurrence["candidate"],
                    "",
                    "Review receipt: " + occurrence["review_receipt"],
                    "",
                    "Criterion ID in that run: " + occurrence["criterion"],
                    "",
                    "Current source commitments: " + ("yes" if occurrence["current"] else "no"),
                    "",
                    "**Recorded reviewer reason**",
                    "",
                    m.quote(occurrence["reason"]),
                    "",
                    "**Cited observations and their locators**",
                    "",
                ]
            )
            if not occurrence["observations"]:
                lines.extend(["No observation was cited; none has been inferred here.", ""])
            for index, observation in enumerate(occurrence["observations"], 1):
                lines.extend([f"Observation {index}:", ""])
                lines.extend(data_block(observation))

    lines.extend(["## Attributed hypotheses", ""])
    if not result["hypotheses"]:
        lines.extend(
            [
                "No cause hypothesis has been supplied. Repetition alone does not establish a cause.",
                "",
            ]
        )
    for hypothesis in result["hypotheses"]:
        lines.extend(
            [
                "### " + hypothesis["hypothesis_id"],
                "",
                "Status: " + hypothesis["status"],
                "",
                "#### Evidence groups",
                "",
                *["- " + group_id for group_id in hypothesis["group_ids"]],
                "",
                "#### Proposed explanation",
                "",
                m.quote(hypothesis["explanation"]),
                "",
                "#### Alternative explanations",
                "",
            ]
        )
        if hypothesis["alternatives"]:
            for alternative in hypothesis["alternatives"]:
                lines.extend([m.quote(alternative), ""])
        else:
            lines.extend(
                ["No alternative explanation was supplied. This does not exclude alternatives.", ""]
            )
        lines.extend(
            [
                "#### Proposed change",
                "",
                m.quote(hypothesis["proposed_change"]),
                "",
                "#### Protected requirements",
                "",
            ]
        )
        if hypothesis["protected_requirements"]:
            for requirement in hypothesis["protected_requirements"]:
                lines.extend([m.quote(requirement), ""])
        else:
            lines.extend(
                [
                    "No protected requirements were listed in this hypothesis; source requirements still apply.",
                    "",
                ]
            )
        lines.extend(
            [
                "#### Acceptance check",
                "",
                m.quote(hypothesis["acceptance_check"]),
                "",
                "#### Scope",
                "",
                m.quote(hypothesis["scope"]),
                "",
            ]
        )
    lines.extend(["## Limits", "", *["- " + limit for limit in result["limits"]], ""])
    return "\n".join(lines)


def analyze(root: Path, runs: list[str], output: str, hypotheses_path: str | None = None,
            *, runtime_arguments: dict | None = None) -> dict:
    reports = []
    for run in runs:
        report, _ = artifact_review.build(root, run)
        reports.append(report)
    hypotheses = None
    if hypotheses_path:
        value = m.load(root, hypotheses_path)
        m.exact(value, {"hypotheses"}, label="hypotheses input")
        hypotheses = value["hypotheses"]
    result = summarize(reports, hypotheses)
    lookup_actions = []
    for report in reports:
        lookup_actions.append({'operation': 'consult-presets', 'script': 'scripts/production_workflow.py',
            'args': {'root': str(root), 'task': report['task_path'], 'focus': 'repair', **(runtime_arguments or {})},
            'required_args': ['query', 'out-dir'], 'external_effect': False, 'budget_effect': 'none',
            'question_owner': 'Translate the observed issue into a craft question and inspect fitting prior knowledge.'})

    files = {
        "analysis.json": m.encoded(result),
        "analysis.md": render(result).encode("utf-8"),
    }
    return {
        "ok": True,
        "content_sha256": result["content_sha256"],
        "next_actions": lookup_actions,
        **m.publish(root, output, files),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--run", action="append", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--hypotheses")
    from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime
    add_pack_runtime_arguments(parser)
    args = parser.parse_args(argv)
    context = resolve_pack_runtime(parser, args)
    runtime_arguments = {"state-file": str(context.settings.state_file),
        "cache-dir": str(context.settings.cache_dir), "managed-root": str(context.settings.managed_root),
        "pack-root": [str(path) for path in context.pack_roots]}
    try:
        print(
            json.dumps(
                analyze(args.root, args.run, args.out, args.hypotheses, runtime_arguments=runtime_arguments),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except (ValueError, OSError, KeyError, TypeError, UnicodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
