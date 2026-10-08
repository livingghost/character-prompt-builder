# Operation diagnostics

Every public CLI call records one local diagnostic operation, starting before argument parsing.
Nested validation and construction stages share the operation ID of their call.
A log never establishes approval, source understanding or image review.

## Where an operation is recorded

- With a selected Studio: `STUDIO/logs/operations/UTC-DATE/OPERATION-ID/`.
- Without a Studio: `logs/operations/UTC-DATE/OPERATION-ID/` in the configuration directory, which `CPB_HOME` names and which is `~/.character-prompt-builder` while `CPB_HOME` is unset.

`--root`, `--production-root` and `--studio-root` name an existing Studio.
`--studio` can also name a directory inside that Studio. A sheet command identifies its Studio through the ancestors of `--sheet` or a locally stored `--spec`.
An unresolved studio and an argument error stay in the configuration directory.
When the configuration directory cannot be written, the operation rebuilds its early record in the Studio and notes `user_log_unavailable`.
Logging alone creates no Studio, task, run, authorization or execution claim.

A child process started during a call records that call as `parent_operation`.
The parent passes its ID in the `CPB_PARENT_OPERATION` environment variable.
An operation lists every candidate and execution claim it touched.
`logs`, `logs-export` and `status` record the run they inspect as `query_run`, so they never join that run's operations.

## What an operation holds

- `operation.json`: the command, its arguments, the linked task, run, candidates and execution claims, the parent operation and the process;
- `events.jsonl`: each stage with its duration, the formal storage events, and a final `completed` event with the exit code;
- `stdout.log` and `stderr.log`: the console output;
- `artifacts.json`: each file the operation wrote, with its SHA-256 when the operation ended.

The `operation.json` of a synthetic `prepare` from `examples/generation/build_example.py`, trimmed:

```json
{"command": "production_workflow.py", "operation_id": "b4fca86d-23a8-473d-8fd9-c3339498b263",
 "parent_operation": null, "pid": 34136, "created_at": "2026-10-03T18:58:41.396315Z",
 "arguments": {"command": "prepare", "root": "C:\\...\\case1\\studio", "task": "task.json", "state_file": "C:\\...\\state.json"},
 "context": {"studio": "C:\\...\\case1\\studio", "run": "01a10321-fceb-77cb-bcd6-ea82826cd107",
             "task": "01a10321-dfe1-7330-84e3-4bd05c8e3073"}}
```

Its `events.jsonl`, three of the first lines and the last of 78:

```text
{"at": "2026-10-03T18:58:41.402501Z", "event": "started"}
{"at": "2026-10-03T18:58:41.476890Z", "event": "arguments_parsed"}
{"at": "2026-10-03T18:58:41.535273Z", "event": "stage_started", "phase": "input-validation"}
{"at": "2026-10-03T18:58:44.242327Z", "complete": true, "duration_seconds": 2.844000000040978, "event": "completed", "exit_code": 0, "log_failures": []}
```

An operation without a `completed` event is incomplete.

## What the records keep

JSON stdout stays machine readable, with no log prefix.
The records omit payload fields such as prompts, terms and renditions, image data and known credentials.
An argument outside the known safe set is recorded as `[VALUE OMITTED]`.
Inputs, the runtime and artifacts are referenced by path and SHA-256.
The complete creative sources stay in the formal production artifacts.
Console output a command prints can still quote work text in `stdout.log` and `stderr.log`.

A credential that `execute` or `resume` reads is redacted from every later write of that operation.
Values shorter than eight characters, booleans and numbers are never treated as credentials.
Unknown secrets embedded in free text cannot be detected with a universal guarantee.

Textual exit diagnostics go to stderr after credential redaction.
An exception keeps its code and phase in the JSON on stdout, with a short safe explanation on stderr.
[Production execution](production-execution.md) lists the exit status of each diagnostic code.
An argument error's final record carries `INPUT_ARGUMENT_INVALID`.

## Logs and formal records

Logs cannot reconstruct the authoritative execution state.
Inspect the committed Production claim and result records before resuming any external operation.
A failed auxiliary log never invalidates results already saved.
An irreversible effect does not start while its required durable records cannot be saved.
Read-only queries such as `status` stay usable while a new operation cannot save its own log.

## Inspect, export and clean up

```sh
python scripts/production_workflow.py logs --root STUDIO --run RUN
python scripts/production_workflow.py logs --root STUDIO --failed
python scripts/production_workflow.py logs --root STUDIO --operation OPERATION_ID
python scripts/production_workflow.py logs-export --root STUDIO --run RUN --out diagnostics --without-streams
python scripts/production_workflow.py logs-cleanup --root STUDIO --before YYYY-MM-DD
python scripts/production_workflow.py logs-cleanup --root STUDIO --operation OPERATION_ID
```

Without `--root`, these commands read the logs of the configuration directory, and `logs-export --out` must be absolute.
`logs --failed` lists incomplete operations and nonzero exits other than 3, which means waiting for authority or configuration.

`logs-export` builds a new directory, relative to `--root`, in staging and publishes it once.
`--without-streams` leaves `stdout.log` and `stderr.log` out.
Its `export.json` states the included files, exclusions, redaction, work content, incomplete operations and omissions.
Unreadable or linked log files appear as omissions, not as copies.
A synthetic export with `--without-streams`, trimmed:

```json
{"included": ["b4fca86d-23a8-473d-8fd9-c3339498b263/artifacts.json",
              "b4fca86d-23a8-473d-8fd9-c3339498b263/events.jsonl",
              "b4fca86d-23a8-473d-8fd9-c3339498b263/operation.json"],
 "excluded": ["image files and image data", "formal production artifacts: requests, responses, candidates and reviews",
              "stdout.log and stderr.log console output"],
 "work_content": "Console output is excluded. The remaining files hold identifiers, paths, digests and diagnostics.",
 "limitations": "Unknown secrets in free text cannot be guaranteed absent.",
 "incomplete_operations": [], "omissions": []}
```

Logs stay local and are never uploaded automatically.

`logs-cleanup` is a dry run until `--apply` is given.
It assesses only directories that hold the five owned files with matching operation metadata.
`--apply` checks each listed operation again under the studio lock, then removes the eligible ones.
These stay protected, each with its reason:

- the running operation (`active-operation`);
- an operation without a `completed` event whose process may still run, or that `--operation` names (`incomplete-operation`);
- an operation whose own log is incomplete (`diagnostic-incomplete`);
- a directory with unknown files, linked paths or unreadable metadata (`unowned-or-missing-content`, `diagnostic-corrupt-or-unsafe`);
- a run-linked operation whose studio is unknown (`formal-studio-unknown`);
- an operation whose run has an unresolved external outcome or charge (`remote-outcome-unresolved`), including a host handoff with no settled result;
- with `--apply`, an operation that changed between its assessment and the locked recheck (`changed-since-inspection`).

`--before` lists only operations created before that date.
An incomplete operation created before the `--before` date becomes eligible as `abandoned-incomplete` once its process has ended.
A synthetic dry run, trimmed; the protected operation is the cleanup itself:

```json
{"ok": true, "apply": false, "selector": {"before": "2026-10-05", "operation": null},
 "candidates": [{"operation_id": "b4fca86d-23a8-473d-8fd9-c3339498b263", "eligible": true,
                 "run": "01a10321-fceb-77cb-bcd6-ea82826cd107", "reason": "eligible"}],
 "protected": [{"operation_id": "1992fec6-bf3d-4d6e-8107-9da778655a89", "eligible": false, "run": null,
                "reason": "active-operation"}],
 "deleted": [], "formal_artifacts_deleted": false}
```

Cleanup never removes formal requests, responses, candidates, reviews or other Production evidence.
Confirm an external host's actual result with `settle-external`; unknown billing is never treated as zero.


## Automatic operator timeline

Successful work transitions also append immutable redacted records under `STUDIO/work/activity/events/`. Each record carries an event ID, UTC timestamp, subject, revision, operation ID when invoked through a public CLI, and links or identifying fields. Candidate registration, adoption, history reoffer, batch allocation/progress, authored sheet edits, review creation, answers, reopened work and task switches are represented. An explicit revision makes retries idempotent.

`work/activity/timeline.jsonl` and `timeline.md` are automatically generated chronological views; `gallery.html` links to them. They are not a second approval or execution ledger. Actual answers and prior task revisions remain in `work/ledger.jsonl` and `work/tasks/`; exact prompts, requests, responses, approvals and images remain with Production and sheet artifact owners. Redaction in the activity view is not deletion of the formal evidence.

After a committed transition, a failed event write returns `ACTIVITY_RECORD_PENDING`; a small redacted retry receipt is saved when storage allows. A failed display refresh returns `PROJECTION_REFRESH_PENDING`. Both retain committed state and mark `work/activity/projections-pending.json` when writable. `studio.py sync` retries queued events and rebuilds the views. The warning says whether a retry receipt could be saved; total storage failure cannot be represented as a successfully saved log. A repeated generation is never a log-repair operation.

Formal execution claims still have to be durable **before** any external effect. This post-commit projection recovery does not relax that rule. Diagnostic cleanup does not remove activity events, task snapshots, required approval evidence or captured artwork.
