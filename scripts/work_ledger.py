#!/usr/bin/env python3
"""The open task and the trail of tasks in a studio, so work survives a lost context.

A studio holds one open task at a time in `work/current.json`: the goal, the
steps planned, which are done, what comes next, and what it is blocked on. Every
change to it is also appended to `work/ledger.jsonl`, which is never rewritten.
A session that starts without memory of what it was doing reads the open task
and continues from `next`; a session that finds no open task reads the last
finished ones and asks what to do.

Use the task ledger to plan and continue multi-step Production work, including
the drafts and decisions that lead to its run. Mark each step as it is done.
Finish names the exact run and requires all steps and the evidence for its
explicit completion scope: a production result or a complete prepared input.
Otherwise block or abandon it with the reason. Studio administration records
its results through the commands' operation records. A planned step that is
not written down is a step the next session does again or skips.

    python scripts/work_ledger.py begin --studio DIR --goal "..." --step "..." --step "..."
    python scripts/work_ledger.py step --studio DIR <n> [--note "..."]
    python scripts/work_ledger.py note --studio DIR "..."
    python scripts/work_ledger.py block --studio DIR "the question the user has to answer"
    python scripts/work_ledger.py respond --studio DIR --question-id ID --answer "..." --actor "..."
    python scripts/work_ledger.py reopen --studio DIR --from-step 1 --reason "..." --actor "..."
    python scripts/work_ledger.py suspend --studio DIR --reason "..."
    python scripts/work_ledger.py resume-task --studio DIR --task-id ID
    python scripts/work_ledger.py finish --studio DIR --run RUN
    python scripts/work_ledger.py finish --studio DIR --run RUN --scope prepared-input
    python scripts/work_ledger.py abandon --studio DIR --reason "..." [--actor "..."]
    python scripts/work_ledger.py show --studio DIR
    python scripts/work_ledger.py show --studio DIR --task-id ID --view full
"""
from __future__ import annotations
import operation_context as _operation_context

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from cli_invocation import python_argv, shown
from studio_activity import timestamp as now, mutation

SCRIPT = Path(__file__).resolve()
WORK_DIR = "work"
CURRENT = "current.json"
LEDGER = "ledger.jsonl"
FINISH_SCOPES = ('production-result', 'prepared-input')


def begin_command(root: Path) -> str:
    """The command that opens a task in this studio, with every argument it requires."""
    return shown(python_argv(SCRIPT, "begin", "--studio", str(root.resolve()),
                             "--goal", "<goal>", "--step", "<step>", "--step", "<step>"))


def work_dir(root: Path) -> Path:
    return root / WORK_DIR


def ledger_lock(root: Path):
    """Own task updates through their real append-only journal."""
    from execution_contract import atomic, file_lock, local
    path = local(root, WORK_DIR + '/' + LEDGER, exists=False)
    if not path.exists():
        try:
            atomic(path, b'')
        except FileExistsError:
            pass
    return file_lock(path)


def read_current(root: Path) -> dict[str, Any] | None:
    path = work_dir(root) / CURRENT
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: not an object")
    saved = task_path(root, value['task_id'])
    if saved.is_file():
        latest = json.loads(saved.read_text(encoding='utf-8'))
        if latest.get('work_state') != 'active':
            return None
        return latest
    raise ValueError('active task snapshot is missing: ' + str(saved))


def task_path(root: Path, task_id: str) -> Path:
    from execution_contract import local
    import uuid
    if str(uuid.UUID(task_id)) != task_id:
        raise ValueError('task ID must be a canonical UUID')
    return local(root, 'work/tasks/' + task_id + '/task.json', exists=False)


def save_task(root: Path, task: dict) -> None:
    from execution_contract import atomic_write_json
    atomic_write_json(task_path(root, task['task_id']), task)


def write_current(root: Path, value: dict[str, Any] | None) -> None:
    path = work_dir(root) / CURRENT
    if value is None:
        if path.is_file():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    from execution_contract import atomic, encoded
    save_task(root, value)
    atomic(path, encoded(value), replace=True)


def append(root: Path, entry: dict[str, Any]) -> None:
    path = work_dir(root) / LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    import os
    from pack_manager import generate_uuid7
    entry = {**entry, 'event_id': generate_uuid7()}
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
        stream.flush(); os.fsync(stream.fileno())
    import studio_activity as activity
    activity.changed(path, 'work-' + entry['event'], subject=entry['task_id'], revision=entry['event_id'],
                     details={**entry, 'formal_ledger': 'work/ledger.jsonl'}, views={'activity-timeline'})


def read_ledger(root: Path) -> list[dict[str, Any]]:
    path = work_dir(root) / LEDGER
    if not path.is_file():
        return []
    entries = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{number}: not an object")
        entries.append(value)
    return entries


def next_step(task: dict[str, Any]) -> dict[str, Any] | None:
    for step in task.get("steps") or []:
        if not step.get("done_at"):
            return step
    return None


def refreshed(task: dict[str, Any]) -> dict[str, Any]:
    step = next_step(task)
    task["next"] = step["text"] if step else None
    unanswered = [q for q in task.get('questions', []) if q['state'] == 'open']
    task['blocked_on'] = unanswered[0]['question'] if unanswered else None
    return task


def new_task_id(root: Path) -> str:
    from pack_manager import generate_uuid7
    return generate_uuid7()


def require_beginnable(root: Path, goal: str, steps: list[str]) -> None:
    """The shared gate for opening work and for a caller's check before it opens work."""
    if read_current(root) is not None:
        raise ValueError("a task is already open; suspend, finish or abandon it before opening another")
    if not goal.strip():
        raise ValueError("a task needs a goal")
    if not steps or not all(text.strip() for text in steps):
        raise ValueError("a task needs at least one step, each with text")


@mutation
def begin(root: Path, goal: str, steps: list[str], *, task_id: str | None = None) -> dict[str, Any]:
    """Open work. A caller that built inputs for an unopened task supplies that task's ID."""
    with ledger_lock(root):
        return _begin_locked(root, goal, steps, task_id)


def _begin_locked(root: Path, goal: str, steps: list[str], task_id: str | None = None) -> dict[str, Any]:
    require_beginnable(root, goal, steps)
    if task_id is not None and task_path(root, task_id).exists():
        raise ValueError('the task ID already belongs to saved work')
    task = refreshed({
        "task_id": task_id or new_task_id(root),
        "goal": goal.strip(),
        "opened_at": now(),
        "steps": [{"n": index, "text": text.strip(), "done_at": None} for index, text in enumerate(steps, 1)],
        "next": None,
        "notes": [],
        "blocked_on": None,
        "questions": [], "revision": 1, "work_state": "active", "revisions": [],
    })
    write_current(root, task)
    append(root, {"at": task["opened_at"], "task_id": task["task_id"], "event": "opened", "text": task["goal"],
                  "steps": [step["text"] for step in task["steps"]]})
    return task


def require_open(root: Path) -> dict[str, Any]:
    task = read_current(root)
    if task is None:
        raise ValueError(f"no task is open; open one with: {begin_command(root)}")
    return task


@mutation
def record_prepared(root: Path, task_id: str, run: str) -> dict:
    """Attach a published run to its still-current task under the ledger owner.

    Production publication is already durable. A changed task is reported to
    that caller instead of overwriting another task's current pointer.
    """
    with ledger_lock(root):
        task = require_open(root)
        if task['task_id'] != task_id:
            raise ValueError('the open work task changed during Production preparation')
        if task.get('production_run') == run:
            return task
        task['production_run'] = run
        write_current(root, task)
        append(root, {'at': now(), 'task_id': task_id, 'event': 'note',
                      'text': 'Prepared Production run ' + run, 'production_run': run})
        return task


@mutation
def step_done(root: Path, number: int, note: str | None = None) -> dict[str, Any]:
    with ledger_lock(root):
        return _step_done_locked(root, number, note)


def _step_done_locked(root: Path, number: int, note: str | None = None) -> dict[str, Any]:
    task = require_open(root)
    steps = task.get("steps") or []
    found = next((step for step in steps if step.get("n") == number), None)
    if found is None:
        raise ValueError(f"the open task has no step {number}; it has 1 to {len(steps)}")
    if found.get("done_at"):
        raise ValueError(f"step {number} is already done")
    found["done_at"] = now()
    if note:
        found["note"] = note.strip()
    write_current(root, refreshed(task))
    append(root, {"at": found["done_at"], "task_id": task["task_id"], "event": "step", "n": number,
                  "text": found["text"], "note": note.strip() if note else None})
    return task


@mutation
def note(root: Path, text: str) -> dict[str, Any]:
    with ledger_lock(root):
        return _note_locked(root, text)


def _note_locked(root: Path, text: str) -> dict[str, Any]:
    task = require_open(root)
    if not text.strip():
        raise ValueError("a note needs text")
    task.setdefault("notes", []).append(text.strip())
    write_current(root, task)
    append(root, {"at": now(), "task_id": task["task_id"], "event": "note", "text": text.strip()})
    return task


@mutation
def block(root: Path, question: str) -> dict[str, Any]:
    with ledger_lock(root):
        return _block_locked(root, question)


def _block_locked(root: Path, question: str) -> dict[str, Any]:
    task = require_open(root)
    if not question.strip():
        raise ValueError("say what the task is blocked on")
    from pack_manager import generate_uuid7
    question_id = generate_uuid7()
    task.setdefault('questions', []).append({'question_id': question_id, 'question': question.strip(),
        'opened_at': now(), 'state': 'open', 'answer': None, 'candidates': []})
    write_current(root, refreshed(task))
    append(root, {"at": now(), "task_id": task["task_id"], "event": "blocked", "text": question.strip(),
                  'question_id': question_id})
    return task


@mutation
def respond(root: Path, question_id: str, answer: str, *, actor: str,
            evidence: str | None = None, candidates: list[str] | None = None) -> dict:
    """Record an actual answer, without inferring approval or changing artwork."""
    import execution_contract as c
    with ledger_lock(root):
        task = require_open(root)
        question = next((q for q in task['questions'] if q['question_id'] == question_id), None)
        if question is None:
            raise ValueError('question is not recorded in the active task')
        c.text(answer, 'answer'); c.text(actor, 'responding actor')
        proof = None
        if evidence is not None:
            proof = {'path': evidence, 'sha256': c.sha256_file(c.local(root, evidence))}
        response = {'text': answer.strip(), 'actor': actor.strip(), 'evidence': proof}
        if question['state'] == 'answered':
            if {k: question['answer'][k] for k in response} == response:
                return task
            raise ValueError('question already has an answer; open a new question for a revised decision')
        question.update(state='answered', answer={**response, 'at': now()}, candidates=candidates or [])
        write_current(root, refreshed(task))
        append(root, {'at': now(), 'task_id': task['task_id'], 'event': 'answered',
                      'question_id': question_id, 'actor': actor, 'text': answer, 'evidence': proof,
                      'candidates': candidates or []})
        return task


@mutation
def reopen(root: Path, from_step: int, *, reason: str, actor: str) -> dict:
    """Reopen this and later steps as a new work revision, retaining the old plan and runs."""
    import execution_contract as c
    with ledger_lock(root):
        task = require_open(root)
        c.text(reason, 'reopen reason'); c.text(actor, 'reopening actor')
        if type(from_step) is not int or from_step not in {s['n'] for s in task['steps']}:
            raise ValueError('reopen must name an existing step')
        old = json.loads(json.dumps(task))
        revision = task['revision']
        archive = task_path(root, task['task_id']).parent / 'revisions' / f'{revision:06d}.json'
        if archive.exists() and c.load(archive) != old:
            raise ValueError('work revision archive conflicts with the current revision')
        if not archive.exists(): c.atomic(archive, c.encoded(old))
        task['revisions'].append({'revision': revision, 'at': now(), 'from_step': from_step,
                                  'reason': reason, 'actor': actor,
                                  'snapshot': archive.relative_to(root).as_posix(),
                                  'production_run': task.get('production_run')})
        task['revision'] += 1
        for step in task['steps']:
            if step['n'] >= from_step:
                step['done_at'] = None
                step.pop('note', None)
        task.pop('production_run', None)
        write_current(root, refreshed(task))
        append(root, {'at': now(), 'task_id': task['task_id'], 'event': 'reopened',
                      'from_step': from_step, 'revision': task['revision'], 'actor': actor, 'text': reason})
        return task


@mutation
def suspend(root: Path, *, reason: str) -> dict:
    import execution_contract as c
    with ledger_lock(root):
        task = require_open(root)
        c.text(reason, 'suspension reason')
        task.update(work_state='suspended', suspended_at=now(), suspension_reason=reason.strip())
        save_task(root, task)
        append(root, {'at': now(), 'task_id': task['task_id'], 'event': 'suspended', 'text': reason})
        write_current(root, None)
        return task


@mutation
def resume_task(root: Path, task_id: str) -> dict:
    import execution_contract as c
    with ledger_lock(root):
        current = read_current(root)
        if current is not None:
            if current['task_id'] == task_id: return current
            raise ValueError('suspend the active task before resuming another task')
        task = c.load(task_path(root, task_id))
        if task.get('work_state') not in {'suspended', 'active'}:
            raise ValueError('only a suspended task can be resumed')
        task.update(work_state='active', resumed_at=now())
        write_current(root, refreshed(task))
        append(root, {'at': now(), 'task_id': task_id, 'event': 'resumed', 'text': task['goal']})
        return task


def suspended_tasks(root: Path) -> list[dict]:
    rows = []
    for path in sorted((root / 'work/tasks').glob('*/task.json')):
        try:
            task = json.loads(path.read_text(encoding='utf-8'))
            if task.get('work_state') == 'suspended': rows.append(task)
        except (ValueError, OSError):
            continue
    return sorted(rows, key=lambda row: row['suspended_at'], reverse=True)


def finish_argv(root: Path, run: str, *, scope: str = 'production-result') -> list[str]:
    """An explicit completion choice; the command verifies its evidence when run."""
    if scope not in FINISH_SCOPES:
        raise ValueError('completion scope must be production-result or prepared-input')
    return python_argv(SCRIPT, 'finish', '--studio', str(root.resolve()), '--run', run,
                       '--scope', scope)


@mutation
def finish(root: Path, run: str, *, scope: str = 'production-result') -> dict[str, Any]:
    """Close the run's owning task, preserving any unrelated active task.

    The author selects prepared-input only when the completed goal is the
    input itself. That closure records no execution, result or authority and
    leaves the sealed run available for later authorized execution. A suspended
    task can finish on its own evidence; another task's evidence never substitutes.
    """
    with ledger_lock(root):
        return _finish_verified(root, run, scope=scope)


def _clear_finished_pointer(root: Path, task_id: str) -> None:
    pointer = work_dir(root) / CURRENT
    if pointer.is_file():
        held = json.loads(pointer.read_text(encoding='utf-8'))
        if held.get('task_id') == task_id:
            write_current(root, None)


def _require_finished_steps(task: dict[str, Any]) -> None:
    left = [step for step in task.get("steps") or [] if not step.get("done_at")]
    if left:
        raise ValueError(
            f"{len(left)} step(s) are not done: " + "; ".join(f"{s['n']} {s['text']}" for s in left)
            + ". Mark them done, or abandon the task with the reason."
        )


def _require_finishable_work(task: dict[str, Any]) -> None:
    """The shared work gate for status and the eventual owning-task mutation."""
    if task.get('work_state') not in {'active', 'suspended'}:
        raise ValueError('only active or suspended work can finish on its own verified evidence')
    if task.get('blocked_on') or any(question['state'] == 'open' for question in task.get('questions', [])):
        raise ValueError('resolve the open author questions before finishing')
    _require_finished_steps(task)


def _prepared_input_evidence(loaded) -> dict[str, Any]:
    """Identify a complete input from the acquired immutable publication."""
    prepared = loaded.prepared
    if prepared['task']['execution'] == 'authored':
        from production_authored import completion_data
        revision = prepared['authored_revision']
        if revision['state'] != 'finished' or not revision['input_verified']:
            raise ValueError('prepared-input completion requires a finished, verified input; continue the saved draft first')
        completion_data(prepared, loaded.rows)
    plan = loaded.artifacts['execution-plan.json']
    members = {item['path']: item for item in loaded.manifest['files']}
    # An external image plan's request_sha256 names the image-input binding;
    # prepared_request_sha256 names its exact host request. Manual and authored
    # inputs have no transport request and retain their sealed consumer instead.
    request = (plan['prepared_request_sha256'] if plan['execution'] == 'external' and 'request' in plan
               else plan['request_sha256'])
    return {'input_sha256': prepared['input_sha256'],
            'manifest_sha256': loaded.registered['manifest_sha256'],
            'consumer_sha256': members['consumer.json']['sha256'], 'request_sha256': request}


def _finish_identity(run: str, scope: str, completion: dict) -> dict[str, Any]:
    if scope == 'prepared-input':
        return {'production_run': run, 'completion_scope': scope, 'prepared_input': completion}
    return {'production_run': run, 'completion_sha256': completion['sha256']}


def _finish_journal(root: Path, run: str, task: dict[str, Any], completion: dict, *,
                    scope: str = 'production-result') -> list[dict]:
    expected = _finish_identity(run, scope, completion)
    matching = [entry for entry in read_ledger(root) if entry.get('event') == 'finished'
                and entry.get('task_id') == task['task_id']]
    fields = ('production_run', 'completion_scope', 'completion_sha256', 'prepared_input')
    if matching and (len(matching) != 1 or any(matching[0].get(key) != expected.get(key) for key in fields)):
        raise ValueError('task completion journal conflicts with the exact run evidence')
    if task.get('work_state') == 'completed' and (not matching or any(
            task.get(key) != expected.get(key) for key in ('production_run', 'completion_scope', 'prepared_input'))):
        raise ValueError('closed task completion journal conflicts with its saved completion')
    return matching


def finish_state(root: Path, run: str, *, scope: str = 'production-result', loaded=None) -> dict[str, Any]:
    """Expose actual remaining work and the same completion gate that finish enforces.

    Reading this view records no progress, answers no question and closes no task.
    The explicit run identifies its owner even when another task is active.
    """
    from production_operations import read_run, verify_completion
    from execution_contract import load
    from production_diagnostics import from_exception
    argv = finish_argv(root, run, scope=scope)
    loaded = read_run(root, run) if loaded is None else loaded
    if loaded.prepared['run'] != run:
        raise ValueError('the acquired input differs from the selected run')
    task_id = loaded.prepared['task']['task_id']
    task = load(task_path(root, task_id))
    if task.get('task_id') != task_id:
        raise ValueError('the saved task differs from the run owner')
    result = {'task_id': task_id, 'run': run, 'work_state': task.get('work_state'),
        'incomplete_steps': [step for step in task.get('steps', []) if not step.get('done_at')],
        'open_questions': [question for question in task.get('questions', []) if question['state'] == 'open'],
        'blocked_on': task.get('blocked_on'), 'completion': None, 'completion_scope': scope,
        'ready_to_finish': False, 'finished': False, 'diagnostics': [],
        'argv': argv, 'finish_command': shown(argv)}
    try:
        if scope == 'prepared-input':
            completion = _prepared_input_evidence(loaded)
            result['prepared_input'] = completion
            _finish_journal(root, run, task, completion, scope=scope)
            if task.get('work_state') == 'completed':
                result['finished'] = True
                return result
        elif any(row['event'] == 'completion' for row in loaded.rows):
            completion = verify_completion(root, run, task_id)
            result['completion'] = completion['sha256']
            _finish_journal(root, run, task, completion)
            if task.get('work_state') == 'completed':
                result['finished'] = True
                return result
        elif loaded.prepared['task']['execution'] == 'authored':
            from production_authored import completion_data
            completion_data(loaded.prepared, loaded.rows)
        else:
            raise ValueError('the selected production result has no verified completion')
        _require_finishable_work(task)
        result['ready_to_finish'] = True
    except (ValueError, OSError, KeyError, TypeError) as exc:
        result['diagnostics'].append(from_exception(exc, phase='work-finish',
            required_action=('Continue the listed unfinished input or work, resolve its recorded questions, and inspect the exact saved run. '
                'Choose prepared-input only when preparing that input fulfills the actual request; it grants no execution authority.'
                if scope == 'prepared-input' else
                'Complete the actual remaining result or resolve its recorded question, then finish this run. '
                'If the actual request ends at a complete prepared input, choose finish --run RUN --scope prepared-input explicitly.')))
    return result


def _finish_verified(root: Path, run: str, *, scope: str) -> dict[str, Any]:
    from production_operations import complete, read_run, verify_completion
    from execution_contract import load
    finish_argv(root, run, scope=scope)
    loaded = read_run(root, run)
    task_id = loaded.prepared['task']['task_id']
    task = load(task_path(root, task_id))
    if task.get('task_id') != task_id:
        raise ValueError('the saved task differs from the run owner')
    if (scope == 'production-result' and loaded.prepared['task']['execution'] == 'authored'
            and not any(row['event'] == 'completion' for row in loaded.rows)):
        _require_finishable_work(task)
        # The authored owner records the actual outcomes through its ordinary
        # completion event. Finishing work need not repeat that bookkeeping.
        complete(root, run)
    completion = (_prepared_input_evidence(loaded) if scope == 'prepared-input' else
                  verify_completion(root, run, task_id))
    matching = _finish_journal(root, run, task, completion, scope=scope)
    if task.get('work_state') == 'completed':
        _clear_finished_pointer(root, task_id)
        return task
    _require_finishable_work(task)
    if not matching:
        finished = {"at": now(), "task_id": task_id, "event": "finished", "text": task["goal"],
                    **_finish_identity(run, scope, completion)}
        append(root, finished)
    else:
        finished = matching[0]
    task.update(work_state='completed', closed_at=finished['at'], production_run=run)
    if scope == 'prepared-input':
        task.update(completion_scope=scope, prepared_input=completion)
    save_task(root, task)
    _clear_finished_pointer(root, task_id)
    return task


@mutation
def abandon(root: Path, reason: str, *, actor: str | None = None) -> dict[str, Any]:
    with ledger_lock(root):
        return _abandon_locked(root, reason, actor)


def _abandon_locked(root: Path, reason: str, actor: str | None) -> dict[str, Any]:
    """Close the open task. A task with production runs is first abandoned in the Production record.

    The Production record keeps every execution as it is; only an evidenced result or a
    settlement closes one. This ledger entry is the trail, not that record.
    """
    task = require_open(root)
    if not reason.strip():
        raise ValueError("abandoning a task needs the reason")
    from production_store import runs
    production_runs = [row["run_id"] for row in runs(root, task_id=task["task_id"])]
    if production_runs:
        if not (actor or "").strip():
            raise ValueError("this task has prepared production runs; name who abandons it with --actor")
        from production_operations import abandon_task
        abandon_task(root, task["task_id"], actor=actor.strip(), reason=reason.strip())
    append(root, {"at": now(), "task_id": task["task_id"], "event": "abandoned", "text": reason.strip(),
                  "left": [s["text"] for s in task.get("steps") or [] if not s.get("done_at")],
                  "production_runs": production_runs})
    task.update(work_state='abandoned', closed_at=now())
    save_task(root, task)
    write_current(root, None)
    return task


def history(root: Path, task_id: str | None = None) -> dict:
    """Read complete saved task and ledger values without refreshing a Studio."""
    task = (json.loads(task_path(root, task_id).read_text(encoding='utf-8'))
            if task_id is not None else read_current(root))
    entries = read_ledger(root)
    return {'task': task, 'entries': [row for row in entries if task_id is None or row.get('task_id') == task_id],
            'suspended_tasks': suspended_tasks(root) if task_id is None else [],
            'scope': 'studio-history' if task_id is None else 'selected-task',
            'external_effect': False}


def latest_checkpoint(task: dict, entries: list[dict]) -> dict | None:
    """Find a retained note or a step still completed in the current revision.

    Ledger order owns recency. Reopened steps cease to be current checkpoints;
    retained notes remain authored history without a new semantic judgment.
    """
    steps = {row['n']: row for row in task.get('steps', [])}
    notes = set(task.get('notes') or [])
    for entry in reversed(entries):
        if entry.get('task_id') != task['task_id']:
            continue
        if entry.get('event') == 'note' and entry.get('text') in notes:
            return entry
        step = steps.get(entry.get('n')) if entry.get('event') == 'step' else None
        if step is not None and step.get('done_at') is not None and (
                step['done_at'] == entry.get('at') and step['text'] == entry.get('text') and
                step.get('note') == entry.get('note')):
            return entry
    return None


def session_summary(root: Path, task: dict | None, entries: list[dict], paused: list[dict]) -> list[str]:
    """Project acquired work for startup and task navigation; keep every open issue."""
    lines = []
    limit = 640

    def excerpt(text):
        text = ' '.join(str(text).split())
        return text if len(text) <= limit else text[:limit] + f' [omitted {len(text) - limit} characters]'

    if task is not None:
        steps = task.get('steps') or []
        pending = [step for step in steps if not step.get('done_at')]
        label = 'open' if task.get('work_state') == 'active' else task.get('work_state', 'saved')
        lines.append(f"{label} task {task['task_id']}: {task['goal']} "
                     f"({len(steps) - len(pending)} of {len(steps)} steps done)")
        for step in pending:
            lines.append(f"  unfinished: {step['n']}. {step['text']}")
        questions = [row for row in task.get('questions', []) if row['state'] == 'open']
        for question in questions:
            lines.append(f"  blocked on: {question['question']} (question {question['question_id']})")
        if task.get('blocked_on') and task['blocked_on'] not in {row['question'] for row in questions}:
            lines.append('  blocked on: ' + task['blocked_on'])
        if task.get('next'):
            lines.append('  next: ' + task['next'])
        if task.get('production_run') and task.get('work_state') in {'active', 'suspended'}:
            lines.append('  If the requested goal ends at complete input preparation: ' + shown(finish_argv(
                root, task['production_run'], scope='prepared-input')))
            lines.append('  If the requested goal includes the production result: ' + shown(finish_argv(
                root, task['production_run'])))
        if task.get('completion_scope') == 'prepared-input':
            lines.append('  completed scope: prepared-input; execution and production-result completion remain separate.')
        checkpoint = latest_checkpoint(task, entries)
        notes = task.get('notes') or []
        if checkpoint is not None:
            label = checkpoint['event'] + (f" {checkpoint['n']}" if checkpoint['event'] == 'step' else '')
            lines.append(f"  latest retained checkpoint ({label}, {checkpoint.get('at')}): " +
                         excerpt(checkpoint.get('note') or checkpoint['text']))
        if notes and not (checkpoint and checkpoint['event'] == 'note' and checkpoint['text'] == notes[-1]):
            lines.append('  latest note: ' + excerpt(notes[-1]))
        lines.append(f'  notes: note_count={len(notes)}, omitted={max(0, len(notes) - 1)}; '
                     'complete text is in the full task history.')
        lines.append('Read full task history: ' + shown(python_argv(
            SCRIPT, 'show', '--studio', str(root), '--task-id', task['task_id'], '--view', 'full')))
    else:
        finished = [row for row in entries if row.get('event') in {'finished', 'abandoned'}]
        if finished:
            latest = finished[-1]
            lines.append(f"no task is open; latest {latest['event']} task {latest.get('task_id')}: " +
                         excerpt(latest.get('text', '')))
            if latest.get('completion_scope') == 'prepared-input':
                lines.append('  completed scope: prepared-input; the sealed run remains available for authorized execution.')
            lines.append(f'  closed task history: total={len(finished)}, omitted={len(finished) - 1}')
        else:
            lines.append('no task is open; resume a suspended task or begin a new task' if paused else
                         'no task is open, and none has been recorded')
        lines.append('plan the steps of a Production task with: ' + begin_command(root))
        lines.append('Read full Studio work history: ' + shown(python_argv(
            SCRIPT, 'show', '--studio', str(root), '--view', 'full')))
    if paused:
        lines.append(f'{len(paused)} suspended task(s): total={len(paused)}, omitted={max(0, len(paused) - 8)}')
        for row in paused[:8]:
            lines.append('Resume suspended task ' + row['task_id'] + ': ' + shown(python_argv(
                SCRIPT, 'resume-task', '--studio', str(root), '--task-id', row['task_id'])))
        if task is not None:
            lines.append('Read all suspended tasks: ' + shown(python_argv(
                SCRIPT, 'show', '--studio', str(root), '--view', 'full')))
    return lines


def show(root: Path, *, task_id: str | None = None, view: str = 'summary') -> str:
    """Print task navigation or the complete selected task and its saved history."""
    saved = history(root, task_id)
    if view == 'full':
        return json.dumps(saved, ensure_ascii=False, indent=2)
    return "\n".join(session_summary(root, saved['task'], saved['entries'], saved['suspended_tasks']))


def check(root: Path) -> list[str]:
    """What a validator reports: an unreadable ledger, or an open task the ledger does not know."""
    errors: list[str] = []
    try:
        entries = read_ledger(root)
    except (ValueError, json.JSONDecodeError) as exc:
        return [f"{WORK_DIR}/{LEDGER}: {exc}"]
    opened = [entry.get("task_id") for entry in entries if entry.get("event") == "opened"]
    if len(opened) != len(set(opened)):
        errors.append(f"{WORK_DIR}/{LEDGER}: a task id is opened twice")
    for number, entry in enumerate(entries, 1):
        for name in ("at", "task_id", "event"):
            if not isinstance(entry.get(name), str) or not entry[name]:
                errors.append(f"{WORK_DIR}/{LEDGER}:{number}: {name} is missing")
        if entry.get("event") not in ("opened", "step", "note", "blocked", "answered", "reopened", "suspended", "resumed", "finished", "abandoned"):
            errors.append(f"{WORK_DIR}/{LEDGER}:{number}: unknown event {entry.get('event')!r}")
    try:
        task = read_current(root)
    except (ValueError, json.JSONDecodeError) as exc:
        return errors + [f"{WORK_DIR}/{CURRENT}: {exc}"]
    if task is not None:
        if task.get("task_id") not in opened:
            errors.append(f"{WORK_DIR}/{CURRENT}: task {task.get('task_id')!r} was never opened in the ledger")
        closed = {entry.get("task_id") for entry in entries if entry.get("event") in ("finished", "abandoned")}
        if task.get("task_id") in closed:
            errors.append(f"{WORK_DIR}/{CURRENT}: task {task.get('task_id')!r} is open and the ledger says it is closed")
        steps = task.get("steps")
        if not isinstance(steps, list) or not steps:
            errors.append(f"{WORK_DIR}/{CURRENT}: the open task has no steps")
        elif task.get("next") != (next_step(task) or {}).get("text"):
            errors.append(f"{WORK_DIR}/{CURRENT}: next does not name the first step not done")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = _operation_context.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--studio", type=Path, default=Path.cwd(), help="The studio directory (default: the working directory)")
    # The studio may also be named after the command, as Studio Runtime writes it.
    after = _operation_context.ArgumentParser(add_help=False)
    after.add_argument("--studio", type=Path, default=argparse.SUPPRESS, help="The studio directory (default: the working directory)")
    commands = parser.add_subparsers(dest="command", required=True)
    begin_parser = commands.add_parser("begin", help="open a task", parents=[after])
    begin_parser.add_argument("--goal", required=True)
    begin_parser.add_argument("--step", action="append", default=[], help="one step, in order; repeat")
    step_parser = commands.add_parser("step", help="mark a step done", parents=[after])
    step_parser.add_argument("n", type=int)
    step_parser.add_argument("--note")
    note_parser = commands.add_parser("note", help="add a note to the open task", parents=[after])
    note_parser.add_argument("text")
    block_parser = commands.add_parser("block", help="record what the open task waits on", parents=[after])
    block_parser.add_argument("question")
    respond_parser = commands.add_parser('respond', help='record the answer to an exact question; does not approve any execution', parents=[after])
    respond_parser.add_argument('--question-id', required=True)
    respond_parser.add_argument('--answer', required=True)
    respond_parser.add_argument('--actor', required=True)
    respond_parser.add_argument('--evidence')
    respond_parser.add_argument('--candidate', action='append', default=[])
    reopen_parser = commands.add_parser('reopen', help='reopen a step and its downstream steps as a new revision', parents=[after])
    reopen_parser.add_argument('--from-step', type=int, required=True)
    reopen_parser.add_argument('--reason', required=True)
    reopen_parser.add_argument('--actor', required=True)
    suspend_parser = commands.add_parser('suspend', help='pause without completing or abandoning work', parents=[after])
    suspend_parser.add_argument('--reason', required=True)
    resume_parser = commands.add_parser('resume-task', help='restore a suspended task with its questions and exact next step', parents=[after])
    resume_parser.add_argument('--task-id', required=True)
    finish_parser = commands.add_parser("finish", help="close the exact run's owning task at the explicitly selected completion scope", parents=[after])
    finish_parser.add_argument('--run', required=True, help='The exact run whose own work task is being finished')
    finish_parser.add_argument('--scope', choices=FINISH_SCOPES, default='production-result',
        help='production-result (default) requires actual result completion; prepared-input verifies a complete saved input and closes only its work task, without executing, authorizing or completing the production run')
    abandon_parser = commands.add_parser("abandon", help="close the open task without finishing it", parents=[after])
    abandon_parser.add_argument("--reason", required=True)
    abandon_parser.add_argument("--actor", help="Who abandons the task; required once it has a prepared production run")
    show_parser = commands.add_parser('show', help='print task navigation or complete saved task history', parents=[after])
    show_parser.add_argument('--task-id', help='Select an active, suspended or closed saved task by its exact ID.')
    show_parser.add_argument('--view', choices=['summary', 'full'], default='summary',
        help='summary prints task navigation; full returns complete task and ledger entries as JSON without refreshing Studio views.')
    args = parser.parse_args(argv)
    root = args.studio.resolve()
    try:
        if args.command == "begin":
            begin(root, args.goal, args.step)
        elif args.command == "step":
            step_done(root, args.n, args.note)
        elif args.command == "note":
            note(root, args.text)
        elif args.command == "block":
            block(root, args.question)
        elif args.command == 'respond':
            respond(root, args.question_id, args.answer, actor=args.actor, evidence=args.evidence, candidates=args.candidate)
        elif args.command == 'reopen':
            reopen(root, args.from_step, reason=args.reason, actor=args.actor)
        elif args.command == 'suspend':
            suspend(root, reason=args.reason)
        elif args.command == 'resume-task':
            resume_task(root, args.task_id)
        elif args.command == "finish":
            finish(root, args.run, scope=args.scope)
        elif args.command == "abandon":
            abandon(root, args.reason, actor=args.actor)
        elif args.command == 'show':
            print(show(root, task_id=args.task_id, view=args.view))
            return 0
    except (ValueError, OSError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1
    print(show(root))
    return 0


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
