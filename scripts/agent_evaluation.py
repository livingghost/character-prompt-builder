#!/usr/bin/env python3
"""Run explicitly configured agent commands and retain attributable measurements.

No host, provider, model or external skill is assumed. Every trial gets a fresh
workspace and an optional copy of the selected skill. This is process/workspace
isolation, not an OS security sandbox. There are no automatic retries, installs,
model calls in inspection mode, estimated token counts, or automatic artistic grades.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time
from typing import Any, Sequence

import material_support as m

ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", "dist"}
from io_budget import file_identity, optional_count, optional_seconds


def pointer(value: Any, path: str) -> Any:
    if not isinstance(path, str) or not path.startswith("/"):
        raise ValueError("metric pointer must be an absolute JSON pointer")
    for component in path[1:].split("/"):
        key = component.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict):
            if key not in value:
                return None
            value = value[key]
        elif (
            isinstance(value, list)
            and key.isdecimal()
            and str(int(key)) == key
            and int(key) < len(value)
        ):
            value = value[int(key)]
        else:
            return None
    return value


def files_in(directory: Path) -> list[tuple[str, bytes]]:
    directory = m.root_path(directory)
    rows = []
    for path in sorted(directory.rglob("*")):
        rel = path.relative_to(directory)
        if any(part in SKIP_DIRS for part in rel.parts) or path.suffix in {".pyc", ".pyo"}:
            continue
        if path.is_symlink():
            raise ValueError("evaluation inputs may not contain symlinks")
        if path.is_file():
            rows.append((rel.as_posix(), m.read(path)))
    return rows


def validate_study(value: dict) -> None:
    m.exact(value, {"purpose", "cases", "conditions", "repetitions"}, label="agent study")
    m.text(value["purpose"], "study purpose")
    if type(value["repetitions"]) is not int or value["repetitions"] < 1:
        raise ValueError("repetitions must be a positive integer; the approved study determines the run count")
    cases = m.indexed(value["cases"], "id", "cases")
    conditions = m.indexed(value["conditions"], "id", "conditions")
    if not cases or not conditions:
        raise ValueError("study needs cases and conditions")
    for row in cases.values():
        m.exact(row, {"id", "prompt", "inputs", "expected_outputs", "criteria"}, label="case")
        m.text(row["prompt"], "prompt path")
        m.strings(row["inputs"], "case inputs")
        m.strings(row["expected_outputs"], "expected output paths")
        m.strings(row["criteria"], "review criteria")
    for row in conditions.values():
        m.exact(
            row,
            {"id", "host_label", "model_label", "argv", "skill", "timeout_seconds", "metrics"},
            {"max_log_bytes"},
            label="condition",
        )
        m.text(row["host_label"], "declared host")
        m.text(row["model_label"], "declared model")
        if row["skill"] is not None:
            m.text(row["skill"], "skill directory")
        if not isinstance(row["argv"], list) or not row["argv"]:
            raise ValueError("argv must name an explicit executable and arguments")
        for arg in row["argv"]:
            m.text(arg, "command argument")
        optional_seconds(row["timeout_seconds"], "condition timeout_seconds")
        optional_count(row.get("max_log_bytes"), "condition max_log_bytes")
        metrics = row["metrics"]
        if metrics is not None:
            m.exact(metrics, {"match_pointer", "match_value", "pointers"}, label="metrics selector")
            pointer({}, metrics["match_pointer"])
            m.exact(
                metrics["pointers"],
                set(),
                {"total_tokens", "tool_calls", "triggered", "completed"},
                label="metric pointers",
            )
            for path in metrics["pointers"].values():
                pointer({}, path)
    for identifier in [*cases, *conditions]:
        if not ID.fullmatch(identifier) or identifier in {".", ".."}:
            raise ValueError("case/condition IDs must be portable filename components")


def plan_study(root: Path, study_path: str, output: str) -> tuple[dict, dict]:
    root = m.root_path(root)
    raw = m.read(m.local(root, study_path))
    study = m.decode(raw)
    validate_study(study)
    target = m.local(root, output, exists=False)
    cases = []
    for case in study["cases"]:
        paths = [case["prompt"], *case["inputs"]]
        inputs = [
            {"path": p, "sha256": m.digest(m.read(m.local(root, p)))} for p in dict.fromkeys(paths)
        ]
        # Expected outputs are names in a fresh output directory, never arbitrary source paths.
        for path in case["expected_outputs"]:
            m.local(root, path, exists=False)
        m.read(m.local(root, case["prompt"])).decode("utf-8")
        cases.append({"id": case["id"], "inputs": inputs})
    conditions = []
    for condition in study["conditions"]:
        executable = shutil.which(condition["argv"][0])
        if executable is not None:
            executable = str(Path(executable).resolve())
        skill = condition["skill"]
        manifest = None
        if skill is not None:
            source = m.local(root, skill)
            if source == target or target.is_relative_to(source) or source.is_relative_to(target):
                raise ValueError("evaluation output and skill source must not contain each other")
            members = files_in(source)
            if not any(name == "SKILL.md" for name, _ in members):
                raise ValueError("selected skill directory must contain its own SKILL.md")
            manifest = [{"path": name, "sha256": m.digest(data)} for name, data in members]
        conditions.append(
            {
                "id": condition["id"],
                "executable": executable,
                "executable_sha256": file_identity(Path(executable))["sha256"]
                if executable
                else None,
                "skill_files": manifest,
            }
        )
    plan = m.sealed(
        {
            "artifact_type": "agent-evaluation-plan",
            "study_path": study_path,
            "study_sha256": m.digest(raw),
            "output": output,
            "cases": cases,
            "conditions": conditions,
            "study": study,
            "warning": "Configured commands can use credentials and incur costs. No security sandbox or automatic retry is provided.",
        }
    )
    return study, plan


def extract_metric_lines(lines, selector: dict | None) -> tuple[dict, dict]:
    values = {"total_tokens": None, "tool_calls": None}
    observations = {
        "triggered": None,
        "completed": None,
        "metric_line": None,
        "invalid_metrics": [],
    }
    if selector is None:
        return values, observations
    chosen = None
    for number, line in enumerate(lines, 1):
        try:
            value = m.decode(line)
        except (ValueError, UnicodeError):
            continue
        if pointer(value, selector["match_pointer"]) == selector["match_value"]:
            chosen = (number, value)
    if chosen is None:
        return values, observations
    observations["metric_line"] = chosen[0]
    for name, path in selector["pointers"].items():
        value = pointer(chosen[1], path)
        if value is None:
            continue
        if name in values:
            if type(value) is int and value >= 0:
                values[name] = value
            else:
                observations["invalid_metrics"].append(name)
        elif type(value) is bool:
            observations[name] = value
        else:
            observations["invalid_metrics"].append(name)
    return values, observations


def extract_metrics(raw: bytes, selector: dict | None) -> tuple[dict, dict]:
    return extract_metric_lines(raw.splitlines(), selector)


def terminate(process: subprocess.Popen) -> None:
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif process.poll() is None:
        # On Windows, terminate the explicit process tree without invoking a shell.
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if process.poll() is None:
            process.kill()
    if process.poll() is None:
        process.wait(timeout=10)


def _write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def execute_trial(
    root: Path,
    base: Path,
    case: dict,
    condition: dict,
    condition_plan: dict,
    case_plan: dict,
    repetition: int,
    plan_hash: str,
) -> dict:
    directory = base / "runs" / case["id"] / condition["id"] / f"trial-{repetition:04d}"
    directory.mkdir(parents=True, exist_ok=False)
    workspace = directory / "workspace"
    workspace.mkdir()
    outputs = workspace / "outputs"
    outputs.mkdir()
    input_dir = workspace / "inputs"
    input_dir.mkdir()
    for item in case_plan["inputs"]:
        raw = m.read(m.local(root, item["path"]))
        if m.digest(raw) != item["sha256"]:
            raise ValueError("evaluation case input changed after plan approval")
        _write(m.local(input_dir, item["path"], exists=False), raw)
    # Use the bytes already checked and copied for this trial. Reopening the
    # original would allow a concurrent edit to escape its input commitment.
    prompt = m.read(m.local(input_dir, case["prompt"])).decode("utf-8")
    prompt_path = directory / "prompt.txt"
    _write(prompt_path, prompt.encode("utf-8"))
    skill_dir = directory / "skill"
    if condition["skill"] is not None:
        skill_dir.mkdir()
        source = m.local(root, condition["skill"])
        for item in condition_plan["skill_files"]:
            raw = m.read(m.local(source, item["path"]))
            if m.digest(raw) != item["sha256"]:
                raise ValueError("skill changed after evaluation plan approval")
            _write(m.local(skill_dir, item["path"], exists=False), raw)
    else:
        skill_dir.mkdir()
    substitutions = {
        "prompt": prompt,
        "prompt_file": str(prompt_path),
        "workspace": str(workspace),
        "inputs": str(input_dir),
        "outputs": str(outputs),
        "skill": str(skill_dir),
    }
    argv = []
    for token in condition["argv"]:
        # Only whole-argument placeholders are substituted; arbitrary braces in prompts/JSON stay literal.
        if token.startswith("{") and token.endswith("}") and token[1:-1] in substitutions:
            argv.append(substitutions[token[1:-1]])
        else:
            argv.append(token)
    executable = condition_plan["executable"]
    if executable is not None:
        if (
            file_identity(Path(executable))["sha256"]
            != condition_plan["executable_sha256"]
        ):
            raise ValueError("evaluation executable changed after plan approval")
        argv[0] = executable
    log_budget = optional_count(condition.get("max_log_bytes"), "condition max_log_bytes")
    deadline = optional_seconds(condition["timeout_seconds"], "condition timeout_seconds")
    status = "unavailable"
    returncode = None
    elapsed = None
    stdout_path = directory / "stdout.jsonl"
    stderr_path = directory / "stderr.txt"
    process = None
    start = time.monotonic()
    with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
        if executable is not None:
            try:
                process = subprocess.Popen(
                    argv,
                    cwd=workspace,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    shell=False,
                    start_new_session=(os.name == "posix"),
                )
                status = "executed"
                while process.poll() is None:
                    if deadline is not None and time.monotonic() - start > deadline:
                        status = "timeout"
                        break
                    if log_budget is not None and (
                        stdout_path.stat().st_size > log_budget
                        or stderr_path.stat().st_size > log_budget
                    ):
                        status = "log-limit"
                        break
                    time.sleep(0.02)
                if status in {"timeout", "log-limit"}:
                    terminate(process)
                returncode = process.wait()
                if status == "executed" and returncode != 0:
                    status = "failed"
            except OSError as exc:
                status = "launch-failed"
                stderr.write(("Launch failed: " + type(exc).__name__ + "\n").encode())
            finally:
                if process is not None:
                    terminate(process)
                elapsed = time.monotonic() - start
        stdout.flush()
        stderr.flush()
        os.fsync(stdout.fileno())
        os.fsync(stderr.fileno())
    # A budget stops execution, not evidence retention. Keep every byte already
    # captured, including a final burst that arrives between two polls. Strict
    # disk quotas belong to the execution environment, not a false byte guarantee.
    budget_exceeded = [p.name for p in (stdout_path, stderr_path)
                       if log_budget is not None and p.stat().st_size > log_budget]
    if budget_exceeded and status == "executed":
        status = "log-limit"
    if not budget_exceeded:
        with stdout_path.open("rb") as stream:
            metrics, observed = extract_metric_lines(stream, condition["metrics"])
    else:
        metrics = {"total_tokens": None, "tool_calls": None}
        observed = {"triggered": None, "completed": None, "metric_line": None,
                    "invalid_metrics": ["operator-log-budget-exceeded"]}
    measurements = {"elapsed_seconds": elapsed, **metrics}
    actual = []
    issues = []
    for path in sorted(outputs.rglob("*")):
        if path.is_symlink():
            issues.append("symlink output not read: " + path.relative_to(outputs).as_posix())
            continue
        if path.is_file():
            try:
                identity = file_identity(path)
                actual.append(
                    {
                        "path": path.relative_to(root).as_posix(),
                        "output_name": path.relative_to(outputs).as_posix(),
                        **identity,
                    }
                )
            except (OSError, ValueError) as exc:
                issues.append(str(exc))
    names = {x["output_name"] for x in actual}
    missing = sorted(set(case["expected_outputs"]) - names)
    logs = [
        {
            "path": p.relative_to(root).as_posix(),
            **file_identity(p),
            "truncated": False,
            "operator_budget_exceeded": p.name in budget_exceeded,
        }
        for p in [stdout_path, stderr_path]
    ]
    receipt = m.sealed(
        {
            "artifact_type": "agent-evaluation-run",
            "case": case["id"],
            "condition": condition["id"],
            "repetition": repetition,
            "plan_sha256": plan_hash,
            "resource_policy": {"timeout_seconds": deadline, "max_log_bytes": log_budget},
            "status": status,
            "returncode": returncode,
            "argv": argv,
            "host_label": condition["host_label"],
            "model_label": condition["model_label"],
            "input_commitments": case_plan["inputs"],
            "skill_content_sha256": m.content_hash(condition_plan["skill_files"]),
            "logs": logs,
            "measurements": measurements,
            "host_observations": observed,
            "outputs": actual,
            "missing_outputs": missing,
            "issues": issues,
            "criteria": case["criteria"],
            "quality_verdict": "not-reviewed",
            "limitations": [
                "Elapsed time is runner-measured; token/tool counts and trigger/completion flags are host-reported when present.",
                "Exit status, output existence and skill triggering do not establish semantic or artistic success.",
                "Fresh working directories are not an operating-system security sandbox.",
            ],
        }
    )
    result_path = directory / "result.json"
    _write(result_path, m.encoded(receipt))
    measured = {
        "values": measurements,
        "basis": "agent-evaluation-run: retained process and host-output evidence; no estimates",
        "evidence_path": result_path.relative_to(root).as_posix(),
    }
    _write(directory / "measurements.json", m.encoded(measured))
    evidence_complete = not missing and not issues and not budget_exceeded
    return {
        "case": case["id"],
        "condition": condition["id"],
        "repetition": repetition,
        "status": status,
        "evidence_complete": evidence_complete,
        "missing_outputs": missing,
        "issues": issues,
        "log_budget_exceeded": budget_exceeded,
        "result": result_path.relative_to(root).as_posix(),
        "measurements": (directory / "measurements.json").relative_to(root).as_posix(),
        "content_sha256": receipt["content_sha256"],
    }


def run_study(root: Path, study_path: str, output: str, approved_plan: str) -> dict:
    root = m.root_path(root)
    study, plan = plan_study(root, study_path, output)
    if plan["content_sha256"] != approved_plan:
        raise ValueError("evaluation plan differs from the explicitly approved command/input plan")
    base = m.local(root, output, exists=False)
    base.mkdir(parents=True, exist_ok=False)
    _write(base / "plan.json", m.encoded(plan))
    _write(base / "study.json", m.encoded(study))
    condition_plans = {x["id"]: x for x in plan["conditions"]}
    case_plans = {x["id"]: x for x in plan["cases"]}
    results = []
    for case in study["cases"]:
        for condition in study["conditions"]:
            for repetition in range(1, study["repetitions"] + 1):
                results.append(
                    execute_trial(
                        root,
                        base,
                        case,
                        condition,
                        condition_plans[condition["id"]],
                        case_plans[case["id"]],
                        repetition,
                        plan["content_sha256"],
                    )
                )
    execution_ok = all(run["status"] == "executed" for run in results)
    evidence_complete = all(run["evidence_complete"] for run in results)
    result = {
        "ok": execution_ok and evidence_complete,
        "execution_ok": execution_ok,
        "evidence_complete": evidence_complete,
        "plan_sha256": plan["content_sha256"],
        "runs": results,
        "quality_verdict": "not-reviewed",
    }
    _write(base / "results.json", m.encoded(result))
    return result


def verify_measurements(root: Path, path: str, values: dict) -> dict:
    """Verify retained log/output commitments before the existing evaluator uses counts."""
    receipt = m.load(root, path)
    if receipt.get("artifact_type") != "agent-evaluation-run":
        raise ValueError("measurement evidence is not an agent evaluation run")
    m.check_seal(receipt)
    if receipt["measurements"] != values:
        raise ValueError("measurements differ from the retained run evidence")
    for item in [*receipt["logs"], *receipt["outputs"]]:
        if file_identity(m.local(root, item["path"]))["sha256"] != item["sha256"]:
            raise ValueError("evaluation log or output evidence changed")
    return {
        "status": receipt["status"],
        "host_observations": receipt["host_observations"],
        "quality_verdict": receipt["quality_verdict"],
        "limit": "Runner-recorded process evidence and host-reported counters; no claim of semantic correctness or independent counter authenticity.",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["inspect", "run"])
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--study", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--approve-plan", help="Exact plan content hash; run never executes without it"
    )
    args = parser.parse_args(argv)
    if (args.command == "run") != bool(args.approve_plan):
        parser.error("--approve-plan is required only for run")
    try:
        result = (
            {"ok": True, "plan": plan_study(args.root, args.study, args.out)[1]}
            if args.command == "inspect"
            else run_study(args.root, args.study, args.out, args.approve_plan)
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1
    except (ValueError, OSError, KeyError, TypeError, UnicodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
