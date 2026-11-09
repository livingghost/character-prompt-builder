# Production status and recovery

Continue the existing execution from its saved inputs, claim and observed result. Current status and recovery retain the selected execution kind; a fresh context obtains its complete applicable contract.

## Status and resume

```text
python scripts/production_workflow.py status --root STUDIO --run RUN
python scripts/production_workflow.py resume --root STUDIO --run RUN
python scripts/production_workflow.py draft-outcome --root STUDIO --run RUN --out outcome.json
python scripts/production_workflow.py resume --root STUDIO --run RUN --outcome-file outcome.json
```

`status` reads frozen inputs and formal events without executing; `schemas/authoring/production-status.schema.json` defines its output.
One unreadable run does not hide the others.
`current_task` names the open work task: `task_id`, `goal`, `next` and `production_run`.
Each run reports these state axes:

| Axis | Values |
|---|---|
| `preparation` | `staged`, `prepared`, `authored` |
| `readiness` | `ready`, `authorization_required`, `configuration_required`, `blocked`, `saved`, `published` |
| `submission` | `unclaimed`, `claimed`, `send_started`, `pending`, `acknowledged`, `outcome_unknown`, `not_executed`, `not-applicable` |
| `capture` | `none`, `partial`, `complete`, `not-applicable` |
| `cleanup.state` | `not-needed`, `waiting`, `pending`, `failed`, `outcome_unknown`, `complete`, `unsupported` |
| `registration` | `unregistered`, `registered`, `projection-missing`, `work-task` |
| `review` | `unreviewed`, `partial`, `complete` |
| `task_disposition` | `open`, `completed`, `abandoned` |

`submission` comes only from the claim, the send step and `execution-outcome` events.
`pending` means the provider accepted the request and still has unfinished outputs; its next action is `resume`.
`outcome_unknown` means the available evidence does not establish whether the provider carried out the request.
`readiness` reports current authority, credentials, input and recording diagnostics before any send.
The live dispatcher status report's `authentication` field distinguishes the required source selection, local availability and configuration diagnostics. `required` identifies whether the next provider step needs the key; `available` is `null` when no credential lookup is necessary. `remote_validation: "not-performed"` means that this check made no provider authentication request. External run status uses `authentication: null`. These are current runtime observations; `check`, `prepare`, the frozen execution plan and prepared input stay credential-independent. A missing or changed pinned selection reports `configuration_required` and names the repair action. After key entry, inspect the intended run with `status --root STUDIO --run RUN_ID` and check its `authentication.selection`, required availability, `readiness` and `next_action`. The command's top-level `ok` reports inspection success, so it alone does not establish that the run can continue. The Agent follows the returned next action to resume the original production task after its requirements are met.
External tasks with a declared image input require a recorded handoff and a current exact submission authorization before reporting `ready`.
A complete review is not necessarily a passing one.
`registration` is `unregistered` with candidates when the recording destination is gone; the run keeps the captured bytes.
`projection-missing` means the destination exists and only its Studio rows are missing.
Each run also lists its candidates with their states, freshness and selection diagnostics, its execution record, its journal and its logs.

`next_action` is the one command that moves the run forward, as `{command, argv, reason}`.
It is null when nothing is left: a completed or abandoned run with no unresolved provider outcome or supported input cleanup.
Later reference adoption has its own status in [Adoption Workflow](adoption-workflow.md).
It retains the source run's completed or abandoned disposition.
A step that needs an authored file names its draft command, and the reason names the command that consumes the file.
A run whose live sources changed before anything was handed over points to `prepare`.
A synthetic prepared run that waits for authority shows (trimmed, the studio path shortened):

```json
{"readiness": "authorization_required", "submission": "unclaimed",
 "next_action": {"command": "draft-execution",
  "argv": ["python", "scripts/production_workflow.py", "draft-execution", "--root", "STUDIO", "--run", "01a10323-be7f-...", "--grant", "fixture-grant", "--out", "decisions.json"],
  "reason": "Fill decisions.json from the actual approval or delegation, then run: python scripts/production_workflow.py execute --root STUDIO --run 01a10323-be7f-... --decisions-file decisions.json"}}
```

`resume` recovers the same execution from saved evidence and never sends its request again:

- A completed provider answer is registered again without sending. Repeated recovery creates no second candidate, Studio iteration or settlement.
- Capturing a complete saved answer needs no API key. Recovery that asks the provider, continues before the first send, or deletes uploaded inputs resolves the claim's pinned credential selection.
- Every acquired output is kept, including partial or unexpected output counts.
- A processing response keeps the execution open. Its available outputs become candidates while `resume` asks for the same provider task.
- The first response stays in `send-observation.json`; each lookup keeps its own receipt and response. Only a completed response becomes `answer.json`.
- Each output retains its first response, acquisition digest and stable position. A later response can change order without duplicating candidates.
- A response charge remains provisional when that response omits earlier acquired outputs. Unknown total cost never becomes a confirmed smaller bill.
- Resume compares acquired bytes with their first digest. Restore a changed journal image from its Production snapshot before recovering further outputs.
- An execution with no started step continues after current conditions are checked again. A failed check is recorded as a stopped attempt of the same claim.
- A durably completed upload can be reused before the first send; an upload without a saved response stays unknown.
- An unreadable successful HTTP response or an inconclusive JSON response stays `outcome_unknown`. The journal preserves the observation.
- A started send without a completed answer uses the transport's lookup once per `resume` call, including accepted processing tasks.
- When acceptance remains unknown and lookup finds no answer, `draft-outcome` writes the statement form.
  The actor fills it with evidence that the provider's records hold no such task.
- `resume --outcome-file` records that statement as `not_executed`; the actor must be one of the execution's recorded outcome actors.

Cleanup is reported separately from image capture and artistic review. It waits
while generation is pending, its outcome is unknown, or a returned image has
not been saved. A proven generation refusal also permits cleanup of completed
uploads. Only identifiers in this execution's actual upload receipts are targets;
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

An outcome-unknown execution stays unresolved. Inspect provider evidence; a timeout or missing file never authorizes resending.
A pending task keeps `resume` as its next action even when a later lookup has no answer.
Transport adapters normalize their supported output carriers: URL, base64 or data URI.
Direct responses and lookup share the same acquisition contract.
A synthetic partial-response test reports this state while one output remains unfinished (trimmed):

```json
{"submission": "pending", "capture": "partial",
 "execution": {"status": "captured"}, "next_action": {"command": "resume"}}
```

A transport without lookup returns the warning `PROVIDER_LOOKUP_UNSUPPORTED`.
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
