# Production status and recovery

Continue the existing execution from its saved inputs, claim and observed result. Current status and recovery retain the selected execution kind; a fresh context obtains its complete applicable contract.

## Status and resume

```text
python scripts/production_workflow.py status --root STUDIO --run RUN
python scripts/production_workflow.py resume --root STUDIO --run RUN
python scripts/production_workflow.py resume --root STUDIO --run RUN --watch [--interval SECONDS] [--limit SECONDS]
python scripts/production_workflow.py draft-outcome --root STUDIO --run RUN --out outcome.json
python scripts/production_workflow.py resume --root STUDIO --run RUN --outcome-file outcome.json
```

`status` reads frozen inputs and formal events without executing. Its default
navigation view retains every state, blocker, draft location and next action,
while complete source text and authority declarations are available through the
returned `details_action` (`status --view full`) and phase-specific `workspace`.
The navigation view is not evidence for a submission or review decision.
`schemas/authoring/production-status-summary.schema.json` defines this view;
`schemas/authoring/production-status.schema.json` defines full status.
One unreadable run does not hide the others.
`current_task` names the open work task: `task_id`, `goal`, `next` and `production_run`.
Its `authoring` state covers every draft of the work task, its readings and its last check.
`status --run RUN`, and the result of `execute` or `resume`, inspect only the drafts of that run: those reopened from it and the draft or export whose choices or task prepared it. They leave out the last check and give `current_task.authoring_action`, the `status` command that inspects the whole work task.
Each run reports these state axes:

| Axis | Values |
|---|---|
| `preparation` | `staged`, `prepared`, `authored` |
| `readiness` | `ready`, `authorization_required`, `configuration_required`, `blocked`, `not-applicable`, `unchecked`, `saved`, `published` |
| `submission` | `unclaimed`, `claimed`, `send_started`, `pending`, `acknowledged`, `outcome_unknown`, `not_executed`, `not-applicable` |
| `capture` | `none`, `partial`, `complete`, `not-applicable` |
| `cleanup.state` | `not-needed`, `waiting`, `pending`, `failed`, `outcome_unknown`, `complete`, `unsupported` |
| `registration` | `unregistered`, `registered`, `projection-missing`, `work-task` |
| `review` | `unreviewed`, `partial`, `complete` |
| `task_disposition` | `open`, `completed`, `abandoned` |

`submission` comes only from the claim, the send step and `execution-outcome` events.
`pending` means the provider accepted the request and still has unfinished outputs; its next action is `resume --watch`.
`outcome_unknown` means the available evidence does not establish whether the provider carried out the request.
`readiness` reports current authority, credentials, input and recording diagnostics before any send.
`task_disposition` belongs to the run: `completed` after its completion, `abandoned` after its abandonment and `open` otherwise.
A work task closes on its own record, so a run stays `open` when the work task that prepared it finished with another run.
Status compares the current sources, installation and packs with the prepared ones for every open run of active or suspended work, and for an open run selected with `--run`.
A changed or missing author source, a changed Studio reference, installation,
pack or preparation reading is listed in `freshness_notices` as a warning.
The selected run keeps its saved request, media and fixed runtime, so these
changes leave `execute`, `resume`, review and acceptance available. Preparing
the current choices explicitly selects a new revision. A damaged fixed runtime
is listed in `freshness_diagnostics` and makes the saved run `blocked`; its
repair identifies the saved data to restore, without selecting new creative
input on the operator's behalf. `retarget` prepares against current packs.
A completed or abandoned run reports `readiness: not-applicable` with empty `freshness_diagnostics`: it is shown from its retained records, and a later source edit does not change them.
An open run whose work task is completed or abandoned reports `unchecked` in the view of the whole Studio.
When that run was not sent, its next action is `status --run RUN`, which compares it and gives its continuation; a sent one keeps its recovery, review or selection action.
Each execution effect checks its saved publication and runtime, current
imported authority and execution ownership. It does not reread original
authoring files as an execution prerequisite. Recovery uses the recorded
request and effect evidence and never sends again merely because a source changed.
One status call observes each source run of the open task's drafts once and resolves their targets against one acquisition of the selected packs.
`authorization_requirements` lists every prepared operation and target with its
current candidate grants and missing scope. It is null once the request was sent,
and for a run that status does not compare. `authority` includes its observed
event and exact update command; full status also includes the declaration.
Saved execution, review, selection, acceptance and outcome drafts remain
visible in `current_task.authoring.decision_drafts`, independently of diagnostic
logs. Each records its run, kind, editable location and producer-owned decision
basis. Status continues a custom `--out` path when that basis still applies.
Unfinished JSON does not hide the saved candidate or change its review context.
Several applicable drafts require an explicit choice; none is selected by file
age. A changed review, authority or destination obtains its current decision
draft while the earlier file remains available. Continue the selected file
after resolving current authority; saved choices do not themselves grant
permission.
The live dispatcher status report's `authentication` field distinguishes the required source selection, local availability and configuration diagnostics. `required` identifies whether the next provider step needs the key; `available` is `null` when no credential lookup is necessary. `remote_validation: "not-performed"` means that this check made no provider authentication request. External run status uses `authentication: null`. These are current runtime observations; `check`, `prepare`, the frozen execution plan and prepared input stay credential-independent. A missing or changed pinned selection reports `configuration_required` and names the repair action. After key entry, inspect the intended run with `status --root STUDIO --run RUN_ID` and check its `authentication.selection`, required availability, `readiness` and `next_action`. The command's top-level `ok` reports inspection success, so it alone does not establish that the run can continue. The Agent follows the returned next action to resume the original production task after its requirements are met.
External tasks with a declared image input require a recorded handoff and a current exact submission authorization before reporting `ready`.
A complete review is not necessarily a passing one.
`registration` is `unregistered` with candidates when the recording destination is gone; the run keeps the captured bytes.
`projection-missing` means the destination exists and only its Studio rows are missing.
Each run also lists its candidates with their states, freshness and selection diagnostics, its execution record, its journal and its logs.

`next_action` is the one command that moves the run forward, as `{command, argv, reason}`.
When several drafts or candidates remain, its `alternatives` expose each
applicable continuation. Choose the intended one from the commission and actual
evidence; listing order does not select or prefer a result. A reviewed candidate
uses `draft-acceptance` and `accept` for either delivery or an explicit Studio slot.
An image's recording location alone does not select its final use. Delivery-only
is the ordinary action; an available Studio slot has its own explicit
alternative. A previously recorded selection retains its chosen scope when
recovery needs another authored decision.
It is null when nothing is left: a completed or abandoned run with no unresolved provider outcome or supported input cleanup.
Later reference adoption has its own status in [Adoption Workflow](adoption-workflow.md).
It retains the source run's completed or abandoned disposition.
A step that needs an authored file names its draft command, and the reason names the command that consumes the file.
A run whose original sources changed keeps the continuation for its saved
request. Select the editable choices explicitly to prepare their newer content.
A synthetic prepared run that waits for authority shows (trimmed, the studio path shortened):

```json
{"readiness": "authorization_required", "submission": "unclaimed",
 "next_action": {"command": "draft-execution",
  "argv": ["python", "scripts/production_workflow.py", "draft-execution", "--root", "STUDIO", "--run", "01a10323-be7f-...", "--out", "decisions.json"],
  "reason": "Fill decisions.json from the actual approval or delegation, then run: python scripts/production_workflow.py execute --root STUDIO --run 01a10323-be7f-... --decisions-file decisions.json"}}
```

`resume` recovers the same execution from saved evidence and never sends its request again:

- A completed provider answer is registered again without sending. Repeated recovery creates no second candidate, Studio iteration or settlement.
- Capturing a complete saved answer needs no API key. Recovery that asks the provider, continues before the first send, or deletes uploaded inputs resolves the claim's pinned credential selection.
- Every acquired output is kept, including partial or unexpected output counts.
- A processing response keeps the execution open. Its available outputs become candidates while `resume` asks for the same provider task.
- The first response stays in `send-observation.json`; each lookup that observes something new keeps its own receipt and response. Only a completed response becomes `answer.json`.
- A lookup records nothing when it observes what the run already records for the send: an answer the transport reads with the same outcome, outputs, refusals and charge as the latest recorded one, or no answer again for the same reason.
- Each output retains its first response, acquisition digest and stable position. A later response can change order without duplicating candidates.
- A response charge remains provisional when that response omits earlier acquired outputs. Unknown total cost never becomes a confirmed smaller bill.
- Resume compares acquired bytes with their first digest. Restore a changed journal image from its Production snapshot before recovering further outputs.
- An execution with no started step continues after current conditions are checked again. A failed check is recorded as a stopped attempt of the same claim.
- A durably completed upload can be reused before the first send; an upload without a saved response stays unknown.
- For an upload that started without a saved response, `execute` and `resume` report `REMOTE_OUTCOME_UNKNOWN` and send nothing again. That execution cannot reach its send, so its next action is `repeat --from RUN --prepare`: a new run with its own approval. While the operation that started the upload still runs, the next action is `status`, and `resume` reports `DISPATCH_ALREADY_CLAIMED`.
- What such an upload exchange returned stays in `upload-NNN-indeterminate.json` of the journal: the reason, and the HTTP status and body of an answer that came. A service can answer with an issued media identifier whose stored content could not be verified; that body names it, for a check of the provider's own records. The diagnostic lists the file in `evidence`.
- The stopped attempt records the upload under `unknown_uploads`, with that file as evidence. The execution then starts no further upload or send, and the inputs it uploaded before are deleted in the same call, as after a refused upload. The unknown upload has no recorded identifier and is never deleted. When the operation that started it ended without that record while earlier inputs remain to delete, the next action is `resume`, which records it and deletes them.
- An unreadable successful HTTP response or an inconclusive JSON response stays `outcome_unknown`. The journal preserves the observation.
- A started send without a completed answer uses the transport's lookup once per `resume` call, including accepted processing tasks. Every transport defines lookup; one whose service keeps no task that could be asked for again returns no answer.
- When acceptance remains unknown and lookup finds no answer, `draft-outcome` writes the statement form.
  The actor fills it with evidence that the provider's records hold no such task.
- `resume --outcome-file` records that statement as `not_executed`; the actor must be one of the execution's recorded outcome actors.
  A run without a started send has no provider task to state: `OUTCOME_STATEMENT_NOT_APPLICABLE` names the run's next action instead.

Cleanup is reported separately from image capture and artistic review. It waits
while generation is pending, its outcome is unknown, or a returned image has
not been saved. A proven generation refusal also permits cleanup of completed
uploads, and so do a refused upload and an upload recorded under
`unknown_uploads`: neither is sent again, so the send never starts. Only
identifiers in this execution's actual upload receipts are targets;
the caller's source URL and local originals are not deleted.

For untouched inputs or unresolved cleanup, `next_action` selects `resume`.
Each owned input receives one deletion request. An actual deletion error,
including a missing target, is recorded as `failed` and is never sent again.
Other untouched inputs still receive their own deletion requests. Once all
targets have a settled result, cleanup failures remain explicit warnings and
the saved images can proceed to review. An unanswered deletion is looked up by
its original saved request; recovery never sends another deletion. A saved deletion response can be recorded after
an interruption without another provider call. Cleanup recovery does not require
the live source file and cannot start an upload, regenerate an image or replace
captured result evidence. Its receipts and any reported charge remain separate
external-effect records. `unsupported` identifies a transport without deletion
capability and retains the uploaded IDs explicitly; it does not claim deletion.

A synthetic send whose answer was lost makes `resume` exit 4 after the lookup, with this run state (trimmed):

```json
{"submission": "outcome_unknown", "send_started": true, "capture": "none",
 "effects": [{"step": "send", "operation": "send", "result": "unanswered"}],
 "next_action": {"command": "draft-outcome", "argv": ["python", "scripts/production_workflow.py", "draft-outcome", "--root", "STUDIO", "--run", "01a10322-adb4-...", "--out", "outcome.json"]}}
```

A synthetic upload whose answer never arrived leaves this run state, and `resume` exits 4 with `REMOTE_OUTCOME_UNKNOWN` (trimmed, the studio path shortened):

```json
{"submission": "claimed", "send_started": false,
 "effects": [{"step": "upload:0", "operation": "upload", "result": "unanswered"}],
 "next_action": {"command": "repeat", "argv": ["python", "scripts/production_workflow.py", "repeat", "--root", "STUDIO", "--from", "01a1c5a2-921d-...", "--prepare"]}}
```

Its journal keeps `upload-001-indeterminate.json` for that exchange, which ended in a timeout (synthetic, from `scripts/test_production_execution.py`):

```json
{"body":null,"http_status":null,"outcome":"indeterminate","reason":"the upload ended without a provider answer (TimeoutError)"}
```

When the second of two uploads ends that way, the same call deletes the first one; status then reports (synthetic, from `scripts/test_uploaded_input_lifecycle.py`, trimmed):

```json
{"effects": [{"step": "upload:0", "operation": "upload", "result": "executed"},
             {"step": "upload:1", "operation": "upload", "result": "unanswered"},
             {"step": "delete:0", "operation": "delete", "result": "executed"}],
 "cleanup": {"state": "complete", "uploaded": 1, "deleted": 1, "retained": 0},
 "next_action": {"command": "repeat"}}
```

An outcome-unknown execution stays unresolved. Inspect provider evidence; a timeout or missing file never authorizes resending.
A pending task keeps `resume --watch` as its next action even when a later lookup has no answer.
Transport adapters normalize their supported output carriers: URL, base64 or data URI.
Direct responses and lookup share the same acquisition contract.
A synthetic partial-response test reports this state while one output remains unfinished (trimmed):

```json
{"submission": "pending", "capture": "partial",
 "execution": {"status": "captured"}, "next_action": {"command": "resume"}}
```

A transport whose service keeps no task that could be asked for again returns no answer from its lookup.
After such a send ended without an answer, the first `resume` records that the service gave no answer, and the next action becomes `draft-outcome`, as in the lost-answer state above.
A further `resume` records nothing while the service still gives none.

`resume --watch` waits for a pending provider task, so the agent does not repeat `resume` until its outputs finish.
Its first pass is one `resume`. While the run stays `pending`, it waits `--interval` seconds and asks the provider once through the transport's lookup, without reading or checking the run.
A lookup that reports what the run already records is dropped. A lookup that reports something new goes to a `resume`, which reads and checks the run, records that answer and registers each output that finished, so every pass makes exactly one lookup and only a new answer costs a reading of the run.
It returns once the run is no longer pending, because every output is final or the provider reported a failure, or when the next lookup would start more than `--limit` seconds (120 when left out) after the watch began.
The run is then exactly as a plain `resume` leaves it, and the result is what that `resume` returns, with its next action: a task still processing stays `pending`, with `resume --watch` as its next action again.

Without `--interval`, the watch follows the schedule that the run's sealed service record declares in the `delivery` entry of the task's `artifact`, from the service's own polling guidance. Any service record can declare these fields, and `python scripts/service_profile.py SERVICE` prints the schedule of each entry:

| Field | Meaning |
|---|---|
| `poll_first_delay_seconds` | Least time between the provider's acceptance of the task, the first `pending` record of the run, and the first lookup. The watch waits out the rest of it before its first pass. Left out: ask at once. |
| `poll_interval_seconds` | The first wait between lookups. An entry without it declares no schedule. |
| `poll_backoff_factor` | Each later wait is the wait before it times this factor. Left out or 1: every wait is `poll_interval_seconds`. |
| `poll_max_interval_seconds` | The longest wait, at least `poll_interval_seconds`; required with `poll_backoff_factor`. |

`--interval SECONDS` replaces the whole schedule: the watch asks at once and waits that many seconds every time.
The included service record declares, for images, a first wait of 2 seconds that grows by half each time up to 10 seconds, and for video a fixed 3 seconds.
A record that declares no schedule leaves the choice to the caller: the next action of a pending run is then a plain `resume`, and `resume --watch` without `--interval` stops after its first pass with `INPUT_ARGUMENT_INVALID`, whose repair names `--interval` and the record's field.
When the first delay outlasts `--limit`, the watch waits until the limit, asks nothing and returns the run as it is, with `resume --watch` as its next action again.
The limit keeps one watch within about two minutes, a common time limit of an agent's command; a task that takes longer stays `pending` and is watched again from its next action.
The command prints its result only when it returns, so allow it `--limit` seconds and one more lookup, or pass a shorter `--limit`.

The watch never sends or uploads again. Ctrl+C ends it with exit 130; what its earlier passes registered stays registered, and `status --run RUN` gives the next action.
`--interval` or `--limit` without `--watch`, or a value that is not a positive number of seconds, reports `INPUT_ARGUMENT_INVALID`, and `--watch` excludes `--outcome-file`.

A synthetic run of two outputs, whose first output is final at the first lookup and whose second never finishes, watched with `--interval 10 --limit 25`, looks up at 0, 10 and 20 seconds and returns `ok: false` (exit 4). Its journal keeps `lookup-001.json` and `lookup-001-answer.json` alone, because the two later lookups found nothing new and never reached a `resume`. The run reports (the scenario of `test_watch_limit_leaves_the_run_as_a_plain_resume_leaves_it` in `scripts/dispatch_recovery_smoke_test.py`, whose synthetic service record declares 10 seconds; trimmed, the run ID and studio path shortened):

```json
{"submission": "pending", "capture": "partial", "execution": {"status": "captured"},
 "next_action": {"command": "resume",
  "argv": ["python", "scripts/production_workflow.py", "resume", "--root", "STUDIO", "--run", "01a1c6d5-9fad-...", "--watch"],
  "reason": "The provider accepted this task and is still processing it. resume --watch asks for the same task every 10 seconds, as its service record declares, registers each output as it finishes and returns when none is pending, or after 120 seconds; --interval fixes every wait and --limit changes that time. It never sends again."}}
```

Recovery uses the exact transport implementation sealed at preparation.
Keep that installation until its sent runs finish; the pack snapshot contains catalog data, not executable transport code.
`TRANSPORT_IMPLEMENTATION_CHANGED` directs recovery through that installation without changing the task identifier or sending again.
The [synthetic resume example](../../examples/resume-recording/README.md) shows a real report before and after an input change.

Abandon a work task with `work_ledger.py --studio STUDIO abandon --reason TEXT --actor NAME`.
It records `abandoned` on each open run of the task and releases nothing.
An abandoned run's `next_action` points to recovery while its outcome is unknown. Abandonment does not erase or reset a started send.

`impact --root STUDIO --run RUN` compares current sources and recorded outputs with their pinned bytes.
It reports declared dependency effects, including transitive decisions and criterion IDs.
Implementation changes appear under a separate `implementation` key and reach no creative decision.
`ok` is false while either `changes` or `implementation` is non-empty, and the command then exits 2.
A synthetic run whose `brief.md` changed after preparation reports (trimmed):

```json
{"ok": false, "changes": [{"path": "brief.md", "space": "studio", "status": "changed",
  "sha256": "55c53ee097e2...", "actual_sha256": "17edf92ddf15..."}],
 "implementation": [], "affected": {"decisions": ["expression"], "criteria": ["output"], "purpose": false, "receipts": []}}
```

Neither `impact` nor `status` infers meaning from a hash.
