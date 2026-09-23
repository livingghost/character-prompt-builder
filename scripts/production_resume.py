"""Report saved production evidence before deciding what a new execution needs."""
from __future__ import annotations
import copy
from pathlib import Path
import execution_contract as c
import reservation_lifecycle as lifecycle


def _action(operation: str, root: Path, run: str, *, args: dict | None = None,
            required: list[str] | None = None, external: str = "none",
            budget: str = "none", preserves: list[str] | None = None,
            invalidates: list[str] | None = None, actor: str | None = None) -> dict:
    return {"operation": operation, "args": {"root": str(root), "run": run, **(args or {})},
            "entrypoint": "scripts/production_workflow.py",
            "required_args": required or [], "external_effect": external,
            "budget_effect": budget, "preserves": preserves or ["saved-evidence"],
            "invalidates": invalidates or [], "actor": actor}


def _freshness(root: Path, prepared: dict, rows: list[dict]) -> dict:
    from production_workflow import current_sha256
    dependencies = list(prepared["dependencies"])
    dependencies += [{**item, "space": "artifact", "receipt": row["sha256"]}
                     for row in rows for item in row["data"].get("files", []) + row["data"].get("evidence", [])]
    changes = []
    for item in dependencies:
        try:
            current = current_sha256(root, item)
            if current == item["sha256"]:
                continue
            reason = "bytes-changed"
        except (OSError, ValueError):
            current = None
            reason = "unavailable"
        changes.append({"space": item["space"], "path": item["path"],
                        "recorded_sha256": item["sha256"], "current_sha256": current,
                        "state": reason, "receipt": item.get("receipt")})
    reading = {"current": False, "reason": "The prepared record has no route reading."}
    if "route_reading" in prepared:
        import route_reading
        try:
            route_reading.require_route_reading(prepared["route_reading"], project=root,
                routes={prepared["task"]["route"]}, features=prepared["task"]["features"])
            reading = {"current": True}
        except (OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
            reading = {"current": False, "reason": str(exc)}
    return {"current": not changes and reading["current"] is not False,
            "changes": changes, "reading": reading}


def _artifacts(rows: list[dict]) -> list[dict]:
    result = []
    for row in rows:
        if row["event"] in {"dispatch-results", "candidate", "review", "selection",
                             "adoption-result", "completion"}:
            result.append({"event": row["event"], "receipt": row["sha256"],
                "files": copy.deepcopy(row["data"].get("files", [])),
                "recorded": True})
    return result


def _execution(rows: list[dict], states: dict) -> dict:
    claims = [row for row in rows if row["event"] == "dispatch-claim"]
    results = [row for row in rows if row["event"] == "dispatch-results"]
    external = [row for row in rows if row["event"] == "external-claim"]
    boundaries = [row for row in rows if row["event"] == "reservation-start"]
    claim = claims[-1] if claims else None
    result = next((row for row in reversed(results)
                   if claim is not None and row["data"].get("claim") == claim["sha256"]), None)
    owned = [state for token, state in states.items()
             if claim is not None and lifecycle.claim_owns(claim, token)]
    candidate_files = {(item["path"], item["sha256"]) for row in rows if row["event"] == "candidate"
                       for item in row["data"].get("files", [])}
    registration = None
    if result is not None:
        registration = all((item["path"], item["sha256"]) in candidate_files for item in result["data"]["files"])
    if result is not None:
        state = "outputs-recorded"
    elif claim is not None and any(item["status"] == "started" and not lifecycle.releasable(item) for item in owned):
        state = "boundary-recorded-outcome-unconfirmed"
    elif claim is not None and owned and all(item["status"] == "released" for item in owned):
        state = "claim-cancelled-before-send"
    elif claim is not None:
        state = "claimed-before-send"
    elif external:
        state = "external-authority-handed-off"
    else:
        state = "no-dispatch-claim"
    return {"state": state, "claim": claim["sha256"] if claim else None,
            "result_receipt": result["sha256"] if result else None,
            "candidate_registration_complete": registration,
            "boundaries": [{"receipt": row["sha256"], **copy.deepcopy(row["data"])} for row in boundaries],
            "journal": claim["data"].get("journal") if claim else None,
            "provider_charge": {"confirmed": False, "basis": None},
            "new_submission_allowed_by_this_report": False}


def report(root: Path, run: str) -> dict:
    """Read frozen records first; freshness gates new work, not evidence visibility."""
    import production_workflow as workflow
    root = root.absolute()
    with c.lock(root):
        try:
            _, prepared, _, rows = workflow.load_run(root, run)
            states = lifecycle.derive(rows, prepared, run)
        except (OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
            return {"ok": False, "run": run, "next": "inspect-integrity",
                    "integrity": {"ok": False, "reason": str(exc)},
                    "freshness": None, "artifacts": [], "reservations": None,
                    "execution": {"state": "unknown", "new_submission_allowed_by_this_report": False},
                    "permissions": {"assessment": "not-assessed"},
                    "blockers": [{"code": "record-integrity", "selector": run, "reason": str(exc)}],
                    "next_actions": []}
        fresh = _freshness(root, prepared, rows)
        execution = _execution(rows, states)
        blockers = []
        if not fresh["current"]:
            blockers.append({"code": "new-execution-inputs-changed", "selector": run,
                             "reason": "Inspect changed inputs before preparing a new execution."})
        actions = []
        for token, state in states.items():
            if lifecycle.releasable(state):
                actions.append(_action("draft-release", root, run, args={"reservation": token},
                    required=["out"], actor=state["actor"], budget="none-until-explicit-release",
                    preserves=["saved-evidence", "spent-reservations", "current-delegation"]))
        events = {row["event"] for row in rows}
        state = execution["state"]
        if state == "boundary-recorded-outcome-unconfirmed":
            next_stage = "recover-recording-or-resolve-remote-status"
            actions.extend(_recover_actions(root, run, execution))
        elif state == "external-authority-handed-off" and "candidate" not in events:
            next_stage = "resolve-external-outcome"
        elif state == "outputs-recorded" and not execution["candidate_registration_complete"]:
            next_stage = "recover-recording"
            actions.append(_action("recover-recording", root, run,
                preserves=["same-output-bytes", "saved-request", "spent-reservations"]))
        elif "completion" in events:
            next_stage = "recorded-complete-inputs-changed"
            if fresh["current"]:
                try:
                    workflow.verify_completion(root, run, prepared["task"]["task_id"])
                    next_stage = "done"
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    next_stage = "inspect-completion"
                    blockers.append({"code": "completion-evidence", "selector": run, "reason": str(exc)})
        elif not fresh["current"]:
            next_stage = "inspect-impact-and-refresh-inputs"
            actions.append(_action("impact", root, run,
                preserves=["saved-evidence", "accepted-history", "spent-reservations"]))
        elif state == "claim-cancelled-before-send":
            next_stage = "prepare-new-run-after-release"
            actions.append(_action("impact", root, run))
        elif state == "claimed-before-send":
            next_stage = "inspect-unsent-claim"
        else:
            next_stage = _normal_next(workflow, root, run, prepared, rows)
        return {"ok": fresh["current"] and not blockers, "run": run, "input_sha256": prepared["input_sha256"],
                "next": next_stage, "integrity": {"ok": True}, "freshness": fresh,
                "artifacts": _artifacts(rows), "reservations": list(states.values()),
                "execution": execution, "permissions": _permissions(prepared, rows),
                "blockers": blockers, "next_actions": actions, "events": len(rows),
                "reads": prepared["route"]["reads"],
                "scope": "Saved evidence and current dependencies. Actions execute only through explicit commands."}


def _permissions(prepared: dict, rows: list[dict]) -> dict:
    authority = prepared["authority"]
    return {"assessment": "not-assessed-for-a-new-request", "issuer": authority["issuer"],
            "grants": copy.deepcopy(authority["grants"]),
            "stop_conditions": copy.deepcopy(authority["stop_conditions"])}


def _recover_actions(root: Path, run: str, execution: dict) -> list[dict]:
    # A claim without result evidence never implies that a provider accepted it.
    actions = [_action("impact", root, run,
        preserves=["saved-request", "start-boundary", "reserved-budget"])]
    # A saved answer is the provider's reply: its images download without a new submission.
    if execution["journal"] and c.local(root, execution["journal"] + "/answer.json", exists=False).is_file():
        actions.append(_action("recover-recording", root, run, external="downloads-saved-results",
            preserves=["saved-answer", "saved-request", "spent-reservations"]))
    return actions


def _normal_next(workflow, root: Path, run: str, prepared: dict, rows: list[dict]) -> str:
    events = {row["event"] for row in rows}
    stage = "authorize-direction-and-handoff"
    if "handoff" in events:
        stage = "capture"
        if prepared["task"]["execution"] == "external" and "external-claim" not in events:
            stage = "authorize-external-submission"
        if prepared["task"]["execution"] == "dispatcher" and "dispatch-claim" not in events:
            stage = "authorize-dispatch"
    if "candidate" in events:
        candidate = workflow.find(rows, "candidate")
        stage = "review"
        try:
            reviewed = workflow.latest_review(rows, candidate["sha256"])
            workflow.eligible(prepared, reviewed)
            stage = "authorize-selection"
        except ValueError:
            if any(row["event"] == "review" and row["data"]["candidate"] == candidate["sha256"] for row in rows):
                stage = "review-or-revise-candidate"
    if "selection" in events:
        selection = workflow.find(rows, "selection")["data"]["selection"]
        try:
            reviewed = workflow.latest_review(rows, selection["candidate"])
            workflow.eligible(prepared, reviewed)
            stage = "complete" if reviewed["sha256"] == selection["review"] else "authorize-selection"
        except ValueError:
            stage = "review-or-revise-candidate"
    return stage
