# Production execution

Every artifact-bearing task uses the existing work ledger and one production lifecycle.
First read [Production direction](production-direction.md) and [Production permissions](production-permissions.md).
Author the purpose, selected expression, evidence criteria and authority rather than inferring them from the existence of files.
Selection is not adoption, preparation is not consent, and hash equality is not artistic success.
A run is one prepared unit of production work and its records.
Execution is the act of executing a run: the `execute` command, its claim and its send.
Discussion without an artifact does not require a run.

## Assemble authored choices

Use [Craft consultation](craft-consultation.md) while deciding what to write or revise.

The route read writes a reading record at the path it prints, with the route, the key and every hash filled.
The author decides which of the read documents apply to this task, and lists only those.
Each entry in `applied` names the document's `path`, a `quote` of twelve or more words from one paragraph of it, and `why` it applies.
Each entry in `resource_applied` names `"resource": "prompt-writing-guide"`, a `pointer` such as `/sections/2/rules/0`, that rule's exact text as `quote`, and `why`.
Name the completed file as the task's `route_reading`.

- `inspect-inputs` shows declared sources, recorded candidates, and required choices.
- `draft-inputs` creates an unanswered choices document in a new directory.
- `build-inputs` resolves those choices through the existing contract builders. It derives image hashes, adoption selectors, and reference positions from recorded evidence.

[Model request evidence](model-evidence.md#the-request-validation-record) states when a task needs an authored request validation record.
An incomplete selection returns named unresolved fields and publishes nothing; the task and its sources stay unchanged.
Use `--from-run` to name a saved run from the same work task; copied reading applications need assessment for the current work.
The [synthetic input assembly example](../../examples/input-assembly/README.md) contains complete commands, choice fields, and actual output.

## Prepare one complete input

Begin the work task with `work_ledger.py --studio STUDIO begin --goal TEXT --step TEXT`.
Use its task ID in a task that follows `schemas/authoring/production-task.schema.json`.
The task declares its route, direction, full source selectors, criteria and execution kind.
For dispatcher generation it also declares `generation` and `recording`.
The prompt file named by `delivery.path` is the single authored prompt.
The agent composes the complete wanted image from the sources, then refines its
details and necessary exclusions. Interpret criteria as requirements on that
depiction; keep their grading language in the task's review records.
The compiler packages the rendition with the selected interface's declared controls.

```text
python scripts/production_workflow.py check --root STUDIO --task task.json
python scripts/production_workflow.py prepare --root STUDIO --task task.json
python scripts/production_workflow.py status --root STUDIO
```

File arguments are studio-relative paths with `/` separators, or absolute paths inside the studio.
Each call may name `-` for one of these JSON options, which then reads standard input:

- `--decisions-file` of `execute` and `--outcome-file` of `resume`;
- `--changes-file` of `variant` and `--intent` of `draft-authorization`;
- `--file` of `authorize`, `review`, `disposition`, `selection-intent`, `select`, `settle-external` and `authority-import`;
- `--approval` and `--registration-record` of `adoption-intent` and `adopt`.

Except for `--changes-file`, the bytes read are kept as `production/runs/RUN/objects/SHA256`, and that path is the recorded evidence.
`authority-import` keeps them as `production/objects/SHA256`.
`--task` and `--artifact` name files only.
Every `--out` names a new file; an existing one gives `OUTPUT_ALREADY_EXISTS`.

`check` returns a compilation report (`schemas/authoring/production-compilation-report.schema.json`) with `run: null`.
Its execution plan also has a null `run`.
It creates no formal run, authorization, execution claim or external request, and never changes pack selection.
`prepare` performs the same compilation, so running `check` first is optional.
It publishes the package, request preview and execution plan (`schemas/authoring/production-execution-plan.schema.json`) as one run.
A complete run that waits for authority is a normal prepared result.
Invalid input remains an unpublished staging attempt.

Each row of `checks` names a `phase`, its `state` (`passed`, `failed` or `not-performed`) and the checks it `requires`.
A failed prerequisite gives `CHECK_NOT_PERFORMED`, whose `blocked_by` names it; none of those states is a pass.
A task schema error blocks only the checks that need the whole task.
Document checks such as specification, plot, retrieval, parameters and target still run and report.
A recording error does not stop model controls, route reading, retrieval or negative-input validation.
Each declared input is read once per compilation.
A change after that read is reported at publication as `SOURCE_CHANGED`.
A synthetic `check` of a missing task file exits 2 and reports (trimmed):

```json
{"ok": false, "publishable": false, "run": null, "diagnostics": [
  {"code": "INPUT_UNREADABLE", "phase": "task-read", "file": "missing-task.json", "cause": "missing file: missing-task.json",
   "required_action": "Name an existing regular file by its path relative to the studio root, with / separators."},
  {"code": "CHECK_NOT_PERFORMED", "phase": "task-read", "blocked_checks": ["task-schema", "task-contract", "sources", "..."]}]}
```

Full source and evidence bytes belong to the run.
The run also pins the installed implementation: the files listed in `config/implementation-files.json` (the modules the production commands import, every schema, their data files and the route manifest, written by `scripts/rebuild_metadata.py` from the import closure) and the route reads. The index records the digest of each module it was computed from. Preparation refuses an index whose modules changed since, or whose schema list differs from the schema directory, and names `scripts/rebuild_metadata.py` as the fix.
`package-manifest.toml` is not pinned, so a release bump keeps a prepared run current.
A pinned implementation file that changes later gives `IMPLEMENTATION_CHANGED`; prepare the task again.
Live creative sources, persona applicability, pack selection and fixed runtime integrity are checked again before execution.

Publication is an atomic, no-replace directory rename.
Its manifest lists every file by content hash, except the root `manifest.json`, `owner.json` and `failure.json`.
An occupied destination stays untouched and is reported as `OUTPUT_ALREADY_EXISTS`.
`ARTIFACT_PUBLISH_FAILED` names the staging directory, the destination and the underlying error, and keeps the complete staging.
Windows handle refusals are retried within a bounded time; no retry replaces an existing destination.
Preparation, publication and recovery refuse a staging or run directory reached through a redirected ancestor or symbolic link.
A studio root given on the command line may be an alias; it is resolved once, and every later lookup rechecks its ancestry.

`production_binding.py`, the upscale declaration command, resolves `--source`, `--settings-file`, `--render-intent`, `--request-validation-file` and `--out` against `--root`.
Authored upscale guidance keeps its exact whitespace and line endings in the request and the result package.
An absent guidance channel is null, never emulated by whitespace.

## Digests

Every digest is the SHA-256 of canonical JSON or of exact file bytes.
Canonical JSON sorts object keys, uses `,` and `:` without spaces, writes non-ASCII characters as UTF-8 rather than `\u` escapes, refuses NaN, and ends with one newline.
Array order and string bytes, including prompt whitespace, are kept.
A run ID is generated, never computed from a digest, so a derived input that names its run directory forms no cycle.
The chain therefore runs one way: authored content, input digest, request digest, run envelope, then authorizations and events.

| Digest | Field and where it is recorded | What it covers |
|---|---|---|
| Input | `input_sha256`: `prepared.json`, the execution plan, the run registry and every formal event | The task without authority, decisions and costs; the consumer; each pinned file's path and SHA-256; the runtime digest. Approval evidence, grant files, logs, the work ledger tail, operation IDs, dates and credentials stay out. |
| Request | `request_sha256`: `prepared.compiled`, the execution plan, `request-contract.json`, the submit authorization, `external-step` events | The sealed request: target, execution mode, request fields without transport management fields, output count, media digests in order, reference bindings and semantic context. Local media paths and credentials stay out. |
| Artifact | `sha256` of a file record: `manifest.json`, `objects/SHA256`, a candidate's `files`, `candidate_sha256` | The exact bytes of one stored file. |
| Event | `sha256` of a formal event, chained through `previous` | Sequence, previous digest, input digest, event kind, data and creation time. Candidate, review, decision and authorization IDs are event digests. |

The other recorded digests each cover one document:

- `consumer_sha256` (`prepared.json`, the plan's `handoff`, the `handoff` event): `consumer.json`, the prepared authoring context and exact authored delivery.
- `generation_input_sha256` (`package.json` and its `generation_contract`): the Generation Package projection that the builder and the verifier both hash. It spans prompt texts, transports, parameters, references and the production binding.
- `package_sha256` (`prepared.compiled`, the submit authorization payload): `package.json`.
- `plan_sha256` (`prepared.compiled`): `execution-plan.json`.
- `envelope_sha256` (`prepared.json`, the run registry): `prepared.json` without that field, which holds the input digest, the compiled digests and the dependency list.

A trimmed `prepared.json` of a synthetic run:

```json
{
  "input_sha256": "7a8ef918ac9a...",
  "consumer_sha256": "2f17ce6a0469...",
  "compiled": {"package_sha256": "ce3a7c8b2743...", "request_sha256": "71bece6826a2...", "plan_sha256": "ae80eb602ada..."},
  "envelope_sha256": "dc091c4966fd..."
}
```

## Execute the prepared request

```text
python scripts/production_workflow.py draft-execution --root STUDIO --run RUN --grant GRANT --out decisions.json
python scripts/production_workflow.py execute --root STUDIO --run RUN --decisions-file decisions.json
```

The draft follows `schemas/authoring/production-execution-decisions.schema.json`.
It contains the run, input digest, request digest and every required authorization.
Complete its reasons, stop-condition assessments and final-request assessment from actual evidence.
[Production permissions](production-permissions.md#authorization-and-execution-records) describes each authorization and its `request_decision`.
Read the sealed prompt fields and actual supplied images together for the
`rendition_review`; source records alone cannot establish what the model receives.
A draft has unanswered judgments and grants no permission.
A supplied decision file must cover the complete operation set; altering targets does not narrow the prepared requirement.
With valid exact receipts already recorded, `execute --root STUDIO --run RUN` needs no decision file.

The run owns one sealed package, request and execution plan, with its handoff recipient and method.
A different parameter, count, model, service, media binding or recipient requires a newly prepared input.
A receipt for another request cannot replace that contract, and a mismatch names the field before an execution claim is committed.

`execute` performs these steps in order:

1. It loads the sealed package and exact request.
2. It rechecks the recording destination: the Studio character, the slot, the sheet-panel condition and the subject mapping.
3. It checks current grants, the credential and exact request approval.
4. In one transaction, it records the dispatcher handoff, records execution ownership and claims the run.
5. The transaction commits before network I/O; each upload and the send then gets its own durable start boundary.
6. It saves the provider answer, downloads every returned image and registers each one as a candidate.

Missing scope or approval rolls back step 4 before any upload or send.
Each start boundary checks the current grant and the live packs again, whatever an earlier check cached.
Revocation after a start boundary cannot undo the started request.
The send boundary records the management identifiers sent with the request.
Low-level `authorize` and the dispatcher share the same permission and execution-claim implementation.
A request has one claim even when it returns several images.
Use `resume` for recovery, `variant` for changed input, and `repeat` for an intentional additional request.

## Exit codes

`production_workflow.py`, the package builder, the verifier, the dispatcher preview and `production_binding.py` share these exit statuses.
Each diagnostic code selects one; [Diagnostic codes](#diagnostic-codes) lists the codes by family.

| Exit | Meaning | Examples |
|---|---|---|
| 0 | Success. | none |
| 2 | Input defect: a declared input, a stored record or an argument needs correcting. Every code not listed for 3 or 4 exits 2. | `INPUT_UNREADABLE`, `SOURCE_CHANGED`, `IMPLEMENTATION_CHANGED` |
| 3 | Waiting for permission or configuration. | `AUTHORIZATION_REQUIRED`, `GRANT_SCOPE_EXCEEDED`, `CREDENTIAL_UNAVAILABLE` |
| 4 | Execution failure, or an outcome that is not known yet. | `REMOTE_OUTCOME_UNKNOWN`, `PROVIDER_REJECTION`, `ARTIFACT_PUBLISH_FAILED` |
| 1 | Unexpected internal error. | none |
| 130 | Interrupted. | none |

A failed result with several error diagnostics exits with the first of 2, 4 and 3 that applies.
Warnings and `CHECK_NOT_PERFORMED` do not choose the status.
`execute` or `resume` that returns `ok: false` without an error diagnostic exits 4.
A synthetic `execute` without a decision file exits 3 and prints (trimmed):

```json
{"ok": false, "diagnostics": [{"code": "AUTHORIZATION_REQUIRED", "severity": "error", "phase": "authorization",
  "pointer": "$.operations.direction", "message": "No exact authorization covers this prepared operation.",
  "required_action": "Fill the execution decision file from the actual approval or delegation, then execute with --decisions-file.",
  "expected": ["decision:expression", "purpose"], "actual": []}]}
```

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
| `preparation` | `staged`, `prepared` |
| `readiness` | `ready`, `authorization_required`, `configuration_required`, `blocked` |
| `submission` | `unclaimed`, `claimed`, `send_started`, `pending`, `acknowledged`, `outcome_unknown`, `not_executed` |
| `capture` | `none`, `partial`, `complete` |
| `registration` | `unregistered`, `registered`, `projection-missing` |
| `review` | `unreviewed`, `partial`, `complete` |
| `task_disposition` | `open`, `completed`, `abandoned` |

`submission` comes only from the claim, the send step and `execution-outcome` events.
`pending` means the provider accepted the request and still has unfinished outputs; its next action is `resume`.
`outcome_unknown` means the available evidence does not establish whether the provider carried out the request.
`readiness` reports current authority, credentials, input and recording diagnostics before any send.
External tasks with a declared image input require a recorded handoff and a current exact submission authorization before reporting `ready`.
A complete review is not necessarily a passing one.
`registration` is `unregistered` with candidates when the recording destination is gone; the run keeps the captured bytes.
`projection-missing` means the destination exists and only its Studio rows are missing.
Each run also lists its candidates with their states, freshness and selection diagnostics, its execution record, its journal and its logs.

`next_action` is the one command that moves the run forward, as `{command, argv, reason}`.
It is null when nothing is left: a completed run, or an abandoned run with no unknown outcome.
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

### Unpublished staging and interrupted publication

```text
python scripts/production_workflow.py staging-cleanup --root STUDIO
python scripts/production_workflow.py staging-cleanup --root STUDIO --operation OPERATION_ID --apply
python scripts/production_workflow.py recover-publication --root STUDIO --run RUN
```

A failed or interrupted compile is never a formal run; `status` lists its staging separately.
The dry run lists three kinds of leftovers, each with eligibility and reasons:

- `items`: compile staging directories;
- `journals`: dispatch journals that no claim names;
- `publications`: run directories published without a registration.

`--apply --operation ID` removes only the eligible items whose owner operation is `ID` and has ended.
It lists everything again under the studio lock right before removal.
A recoverable publication is never removed; its reason names `recover-publication`.
A synthetic studio with nothing to clean prints:

```json
{"ok": true, "apply": false, "items": [], "journals": [], "publications": [], "deleted": 0, "external_effect": false}
```

`recover-publication` registers an intact publication left between file storage and database registration, without compiling or sending.
It verifies the envelope, source snapshots, consumer and fixed runtime first.
It keeps the current authority and imports no grant from the recovered input.
Run `status` afterward to see the execution requirements.
Diagnostic log cleanup is a separate operation, described in [Operation diagnostics](operation-logs.md).
Neither cleanup deletes a formal request, result, review or authorization.

## Diagnostic codes

Every failure after argument parsing prints a JSON object with `ok: false` and `diagnostics`.
Each diagnostic has `code`, `severity`, `phase`, `file`, `pointer`, `message`, `required_action` and `blocked_checks`.
Some add `run`, `expected`, `actual` or other details.
Exit 2 applies unless a row says otherwise.

**Input and stored records**

| Code | Reports |
|---|---|
| `INPUT_ARGUMENT_INVALID` | The arguments do not match the command. The usage goes to stderr, and the operation log records this code. `logs-cleanup` prints it for an invalid date or selector. |
| `INPUT_SCHEMA_INVALID` | A JSON input breaks its schema. |
| `INPUT_UNREADABLE` | A declared input or the task cannot be read; adds `file`, `pointer` and `cause`. |
| `INPUT_CONSISTENCY_ERROR` | Inputs contradict each other or a contract they must satisfy. |
| `CHECK_NOT_PERFORMED` | A check did not run because a prerequisite failed; `blocked_by` names it. |
| `SOURCE_CHANGED` | A source differs from the bytes read or pinned earlier. |
| `TASK_CHANGED` | The open work task changed during preparation. |
| `IMPLEMENTATION_CHANGED` | A pinned file of the installed implementation changed after preparation. |
| `CONTROL_NOT_AVAILABLE` | A control is undeclared, not applicable or managed by the service; also an undeclared upscale scale or guidance. |
| `MODEL_PROFILE_MISSING` | The selected target has no execution profile, offering, service profile or upscale scale key. |
| `DEPENDENCY_UNAVAILABLE` | Exit 3. A Python dependency a check imports is not installed. |
| `EXECUTION_NOT_APPLICABLE` | The operation needs a prepared model request: `draft-execution` or `execute` of a run without one, or a dispatcher preview with no prepared run behind it. |
| `RUN_NOT_REGISTERED` | No formal run has this ID. |

**Evidence and integrity**

| Code | Reports |
|---|---|
| `EVIDENCE_SNAPSHOT_MISSING` | A saved source snapshot of the run is missing; restore it. |
| `EVIDENCE_SNAPSHOT_CORRUPT` | A saved source snapshot differs from its digest. |
| `EVIDENCE_CAPTURE_FAILED` | Evidence could not be read as one stable file. |
| `EVIDENCE_INCOMPLETE` | JSONL evidence ends with an incomplete record. |
| `INPUT_SNAPSHOT_CORRUPT` | The run envelope or consumer differs from its digest. |
| `ARTIFACT_MISSING` | A published file of the run is missing. |
| `ARTIFACT_CORRUPT` | A published file differs from its committed contents, or an upload receipt belongs to another input. |
| `ARTIFACT_INCOMPLETE` | The publication manifest is not marked complete. |
| `ARTIFACT_MANIFEST_CORRUPT` | The publication manifest differs from its registered digest or lists a file twice. |
| `EVENT_CHAIN_CORRUPT` | Formal events do not form one chain. |
| `EVENT_CONFLICT` | Another operation committed first; reload the current state. |
| `AUTHORITY_STATE_CORRUPT` | The stored authority is not the last committed event or differs from its digest. |
| `EXECUTION_RECORD_CORRUPT` | An execution transition names an invalid identity or authorization. |

**Pack and runtime drift**

| Code | Reports |
|---|---|
| `PACK_RUNTIME_REQUIRED` | Exit 3. Pack state is not initialized; run `pack_cli.py ready`. |
| `PACK_NOT_ENABLED` | Exit 3. No active pack satisfies the declared runtime. |
| `PACK_SELECTION_CHANGED` | The run binds a pack that the current pack state does not select. |
| `PACK_RELEASE_MISMATCH` | The current and pinned pack releases differ. |
| `PACK_CONTENT_MISMATCH` | Captured bytes differ from the pack lock, or a pack file changed during capture. |
| `RECORD_NOT_FOUND` | A selected pack root, file or record has vanished. |
| `PINNED_RESOURCE_MISSING` | A file of the run's fixed runtime snapshot is missing. |
| `RUNTIME_SNAPSHOT_CORRUPT` | The fixed runtime snapshot differs from its digest. |
| `PACK_NOT_FOUND` | `pack_cli.py` found no pack with that ID or unique name. |
| `PACK_NAME_AMBIGUOUS` | A `pack_cli.py --pack` name matches several packs; `candidates` lists them. |
| `PACK_DIRECTORY_NOT_ABSOLUTE` | A `pack_cli.py --directory` path is not absolute. |
| `PACK_OPERATION_FAILED` | A pack command failed for the reason its message names. |

A drift diagnostic adds `affected_runs` and `actions`.

**Authorization and execution ownership**

| Code | Reports |
|---|---|
| `AUTHORIZATION_REQUIRED` | Exit 3. No exact authorization covers a prepared operation. |
| `AUTHORIZATION_MISMATCH` | Exit 3. An authorization differs from the prepared operation; names the field and the `intent`. |
| `GRANT_SCOPE_EXCEEDED` | Exit 3. No current grant covers the targets, or the grant names another actor, omits the operation. A target shortfall adds `granted`, `missing` and `coverage`. |
| `GRANT_REVOKED` | Exit 3. The current authority does not contain the grant, or the grant is revoked or expired. |
| `GRANT_NOT_EFFECTIVE` | Exit 3. The grant is not yet effective. |
| `EXTERNAL_COST_LIMIT_EXCEEDED` | Exit 3. A reported charge exceeds its effect ceiling; no further effect starts. |
| `CREDENTIAL_UNAVAILABLE` | Exit 3. The credential variable the service record names is not set. |
| `HANDOFF_REQUIRED` | Exit 3. The operation needs a recorded handoff that the run lacks. |
| `HANDOFF_NOT_PERFORMED` | A low-level dispatcher handoff is refused; `execute` records that handoff. |
| `TASK_ABANDONED` | The run's work task was abandoned, so no new operation starts. |
| `AUTHORITY_UPDATE_CONFLICT` | An authority import names a stale current event. |

**Execution**

| Code | Reports |
|---|---|
| `DISPATCH_ALREADY_CLAIMED` | Exit 4. The run already owns an execution, or this exact step already started. |
| `REMOTE_OUTCOME_UNKNOWN` | Exit 4. An upload or send started without a saved response; nothing is sent again. |
| `PROVIDER_REJECTION` | Exit 4. The provider refused an upload or the request. |
| `TRANSPORT_RESULT_INVALID` | Exit 4. A transport response does not have the declared shape. |
| `RESPONSE_CORRUPT` | Exit 4. A saved provider response differs from its durable receipt. |
| `SETTLEMENT_CONFLICT` | Exit 4. An external step already has a different recorded result. |
| `SETTLEMENT_EVIDENCE_REQUIRED` | Exit 4. No exact external boundary supports the stated outcome. |
| `EXECUTION_STOPPED` | Exit 4. Execution stopped without a more specific diagnostic. |
| `OUTCOME_STATEMENT_NOT_APPLICABLE` | `resume --outcome-file` names a run with no started send. |
| `OUTCOME_STATEMENT_CONFLICT` | The provider answer for the send is saved; resume without the statement. |
| `PROVIDER_LOOKUP_UNSUPPORTED` | Warning. The transport cannot ask the provider for a lost answer. |

**Recording and projection**

| Code | Reports |
|---|---|
| `RECORDING_CONTRACT_INVALID` | The recording target names no existing Studio character or slot, or breaks a slot condition. |
| `SHEET_SUBJECT_MAPPING_MISSING` | A sheet slot needs an explicit subject mapping. |
| `OUTPUT_COUNT_MISMATCH` | Exit 4, or a capture warning. The returned output count differs from the authorized request. |
| `UPSCALE_OUTPUT_CONTRACT_MISMATCH` | Exit 4, or a capture warning. An upscale output breaks its declared output contract. |
| `STUDIO_PROJECTION_FAILED` | Exit 4, or a warning. Candidates are registered; only their Studio rows are missing. |
| `WORK_PROJECTION_FAILED` | Exit 4, or a warning. The formal run is kept; the work-ledger projection failed. |

**Output and publication**

| Code | Reports |
|---|---|
| `OUTPUT_ALREADY_EXISTS` | The destination exists; choose a new `--out`. |
| `ARTIFACT_PUBLISH_FAILED` | Exit 4. A complete staging tree could not be published. |
| `STAGING_CLEANUP_REFUSED` | Staging is outside the owned studio tree or holds a symbolic link. |

**Review, selection and adoption**

| Code | Reports |
|---|---|
| `REVIEW_INCOMPLETE` | A hard criterion has no supported `pass`, so the candidate cannot be selected. |
| `REVIEW_MISMATCH` | A disposition cites a review that is not the candidate's latest. |
| `SELECTION_CONFLICT` | Another candidate holds the run's current selection. |
| `SELECTION_REQUIRED` | The candidate is not the current selection of its run. |
| `SELECTION_REVIEW_CHANGED` | A newer review of the selected candidate ended its selection. |
| `SELECTION_REPLACED` | A later selection of another candidate replaced this one. |
| `SELECTED_CANDIDATE` | The Studio holds the selected candidate as its accepted image. |
| `ADOPTION_RESULT_MISSING` | The run records no completed adoption of the cited Studio iteration. |
| `ADOPTION_RECORD_CORRUPT` | The canonical adoption record is malformed or differs from its artifact. |

**Variation**

| Code | Reports |
|---|---|
| `CHANGES_UNKNOWN_FIELD` | A changed field is not declared mutable. |
| `CHANGES_TYPE_INVALID` | A changed value breaks the field's schema. |
| `CHANGES_NO_OP` | A changed value equals the current one; use `repeat` for another run. |
| `CHANGES_CONFLICT` | The changes set both a complete specification and its execution-mode field. |
| `CHANGES_PATH_INVALID` | A `{"path": ...}` value names a missing or unreadable document. |
| `TARGET_CHANGE_REQUIRED` | A change names a model, service or target, or a specification with another `target_model`; the action names `retarget`. |
| `CANDIDATE_NOT_FOUND` | A `--candidate` names no candidate of the source run. |
| `VARIANT_NOT_APPLICABLE` | The source run has no compiled model request. |
| `REPEAT_INPUT_MISMATCH` | A repeated preparation did not keep the fixed input identity. |
| `RETARGET_NOT_APPLICABLE` | The source run or the new task has no compiled model request. |
| `RETARGET_NO_OP` | Neither the target nor the pack runtime changed. |
| `RETARGET_SCOPE_MISMATCH` | The new task changes the work task or the production series. |

**Operation logs**

| Code | Reports |
|---|---|
| `LOG_WRITE_FAILED` | Exit 4. The operation record cannot be saved before an irreversible effect. |
| `LOG_PATH_UNSAFE` | The diagnostic tree is not an owned regular directory. |
| `LOG_EXPORT_PATH_INVALID` | The export directory is not new, or overlaps the diagnostic tree. |

## Image input and exact external requests

The common `image_input` task property names a Studio-relative
`image-input-plan`, using `templates/image-input-plan.template.json` and
`schemas/authoring/image-input-plan.schema.json`. It serves both ordinary
reference generation and existing-image editing. A new scene may use several
identity, outfit or environment references without declaring a scene source.
Only an actual edit adds `semantic_edit`, whose owner is source, change,
preserve and review meaning.

The image input declares one model target, ordered references and an
`external_request`. Dispatcher work supplies at least one reference, sets
`external_request: null`, and uses its ordinary prepared set and compiled request.
Every external image task pins one exact saved request through this plan.
External non-image work does not need an image-input plan.

An exact text-only image request uses `references: []` and a complete, non-null
`external_request` with `reference_fields: []`. Preparation pins the model
evidence, saved request and any acquired schema through the same binding.
The recorded host call is compared with that exact request during settlement.
A reference-free plan without an external request is invalid. Semantic editing
still requires its selected source image.

Each reference names `id`, `role`, `file`, optional `sha256`, `use_for` and
`do_not_transfer`. Optional `subject_uses` names Production Specification
subjects and intended uses, with priority `0` highest within the same subject
and use. Empty assignments are valid for environment or other inputs without
a named subject. Role names do not grant additional authority, and assignments
cannot enlarge the source's allowed influence.

For existing canonical references, `prepared_references` names their canonical
prepared-reference-set file. Preparation validates its live source provenance,
adoption and selection, pins that file and keeps the complete set. Logical
rows must match its original bytes, role, authority and subject assignments
exactly. The binding consumes the existing set; it cannot reclassify canon as
supplied pixels to replace a state selection or pack Reference Use Plan. Input
files remain the original images used for the exact external media mapping.
A dispatcher additionally checks its declared set against `generation.references`.
External preparation also archives accepted Studio proofs and every transitive
artwork, provenance and approval file through the existing Studio reference
owner. The run stores these under `image-input.references/studio/` and in its
ordinary snapshot object store. Recorded proof verification needs no live
adoption after a call; a new send still checks the current accepted source.

For original supplied files, the common input directly states task-specific
scope. `prepare_generation_references.py --image-input-plan-file` projects it
into the existing prepared set. Matching source bytes or delivery media can
share one attachment while retaining every logical role, original source and
subject use. A verified board retains its panel lineage. External mappings do
not replace several originals with an untracked board.

### Exact target and provider schema

`model` records the requested name, catalog status, canonical record when
present, selected target and saved lookup evidence. A missing catalog record
is recorded explicitly and can proceed as an external trial. It is not a
catalog capability or a proven rendering result. `target.operation` comes
from the selected interface's wire contract, not the render execution mode.

Save one exact request JSON. `external_request` names its relative file and
field paths as arrays of keys and array indices. It declares `prompt_field`,
`model_field`, optional `operation_field`, optional `count_field`, expected
`count` and ordered `reference_fields`. Each reference field includes the
reference ID, exact uploaded value and pinned upload evidence. Every selected
reference is covered. Each declared media field shape is checked across all
array positions. For example, `images[*].uri` covers every such URI, including
inside nested arrays. A mixed content array may retain text-only entries.
Identical source bytes can bind the same media field when its value also
matches; their distinct logical scopes remain recorded.

Inspect the reference mapping before saving the final request:

```sh
python scripts/reference_delivery.py --image-input-plan STUDIO/inputs/image-input.json --studio STUDIO
```

This reads the authored plan and returns `bindings`. `--studio` resolves a
declared canonical prepared set and its source subject assignment. Original
supplied inputs need only the plan's structure at this step. Interpret the
source scopes, subject assignments and precedence into the final prompt using
the images the target receives. Keep request field paths and internal keys in
the binding record.

`check` and `prepare` verify the saved request's exact prompt, ordered media
mapping and source bytes. The agent completes the existing `rendition_review`
against that entire input, bound to `image_input.binding_sha256`. Review the
wanted image, actual reference use and ownership of production information,
including a text-only request's empty image set. A changed prompt, scope,
subject assignment, priority or image position requires that meaning review
again. Dispatcher review uses its compiled request and actual image order or
board regions, bound to the request hash.

For model identity carried in a parameter, `model_field` selects that exact
parameter. If the interface selects a model through an endpoint or tool, use
`model_field: null` with `model_identity` containing `kind` (`endpoint` or
`tool`), exact `value` and saved `evidence` (`path`, `sha256`, `locator`). Do not
add a model parameter the provider does not support. Evidence ties the selected
endpoint/tool to `model.target`; the later host-call record separately shows
which endpoint/tool was used. `operation_field` and `count_field` are null when
those parameters are absent. Record the expected output count explicitly.

An optional `schema: {"path": "inputs/schema.json", "sha256": "...", "pointer": []}`
selects an acquired request schema. An empty pointer selects the whole document;
a nested pointer may select an encoded schema string inside a tool response.
Validation checks supported structural and numeric constraints, including
per-image byte size and dimensions from original image bytes. Unsupported
keywords remain in `schema_validation.unmeasured`. An unavailable schema yields
`bounded-probe` with `schema-unavailable`; an acquired schema yields
`target-schema`. Neither state establishes effective reference use or image
quality. Authority must cover the actual mode and exact-operation request.

Prompt text equals production delivery exactly, including whitespace. A task
with applied `production-spec` or `render-intent` sources runs the common
Production Specification and render validators. The render expression must
appear in delivery, the declared model must agree, and subject assignments
must resolve against the specification's cast. Subject-assigned references
require that specification. State-aware specifications also require their
canonical prepared selection and existing state artifact graphs. External tasks
may name shared files as `generation: {"production_spec": "inputs/spec.json",
"state_graphs": "inputs/graphs.json"}` without dispatcher parameters, plot or
recording fields. `state_graphs` is a JSON array of the existing subject artifact
graphs; each is validated by the existing graph owner. Stateless scenes do not
require it. External preparation does not require a catalog
rendering capability that has not been acquired; such limits remain explicit.

### Prepared JSON and recorded host-call evidence

`request-preview.json` and `execution-plan.prepared_request_sha256` identify
exact prepared arguments. They do not prove that a host invoked its tool.
The external claim pins those arguments and grants one call under the ordinary
handoff and authorization lifecycle. Keep the actual response and saved call
record when the host exposes it.

An external receipt can include this synthetic selector:

```json
{"submission": {"path": "evidence/host-call.json", "sha256": "...",
 "locator": "recorded call arguments and tool name",
 "request_pointer": ["arguments"], "model_identity_pointer": ["tool"]}}
```

`request_pointer` selects the actual recorded argument object. For endpoint or
tool identity, `model_identity_pointer` selects its exact recorded value; use
null when identity lives in the request's model field. The saved call must
match the prepared request and declared endpoint/tool. Using the prepared JSON
itself, or another file with the same bytes, fails as call evidence.

Settlement returns `request_evidence.status: matched-recorded-call` when the
actor's recorded call matches. Without `submission`, it returns `not-provided`;
result capture and accounting still work. The receipt and supplied call record
remain immutable evidence. A mismatch fails comparison without deleting already
captured results. A matching actor-attested record does not establish provider
execution, visual reference influence, artistic success or acceptance. Those
claims need their own response and image review evidence.

## Authored and manually executed work

Authored text uses the same immutable sources and formal event store, without a model package.
`handoff-intent`, `draft-authorization`, `authorize` and `handoff` describe an actual conversation or manual handoff.
For an external tool, authorize its `external-intent`, then `claim-external` before the host runs it.
For image input and exact request binding, set the task's `image_input` as described below. Existing-scene edits also activate `semantic-instruction-edit` and declare `semantic_edit`. Preparation exposes `request-preview.json`; the external claim rechecks pinned inputs before submission. Use that request unchanged in the named host tool.
The submit grant must allow the binding's validation mode and have `request_scope: null`.
These external requests use exact-operation authorization; dispatcher scope cases require a different request contract.
Existing explicit authority may supply that grant without a repeated confirmation.
The claim commits execution ownership and the external-send boundary together before control returns to the host.
A repeated lookup of that claim is not permission to call the host tool twice.
Capture returned files with `capture`; identical bytes are idempotent, and a reused filename cannot exceed the approved count.
Receiving an already delegated result uses saved evidence, even when the original creative files or grant evidence were removed.

Record the actual host response and billing with:

```sh
python scripts/production_workflow.py settle-external --root STUDIO --run RUN --file external-receipt.json
```

The receipt follows `schemas/authoring/production-external-receipt.schema.json`:

- `claim` identifies the external claim, and `actor` is the authorized executor.
- `outputs` equals the saved candidate count.
- `response` holds the real response's studio-relative `path`, exact `sha256` and `locator`.
- Optional `submission` selects the actual recorded host call for comparison with a prepared exact request. It is separate from the response and from the prepared JSON file.
- `cost` is the actual `{"currency": "USD", "amount": "0.01"}`, or `null` when unknown; an estimate is never copied as an actual.
- `final` states whether the host response is final, and `reason` records the executor's conclusion from evidence.

This command records evidence and never invokes the host.
Reported provider usage is retained exactly. Unknown billing remains unknown without blocking result capture or completion.
Final billing closes accounting, not artistic review, and an identical receipt does not settle twice.
`production_direction_smoke_test.py` exercises this workflow with synthetic local files and no provider call.

An additional external trial starts from a separately authored task and exact request, followed by `check` and `prepare`.
Keep relevant earlier runs and reviews as ordinary comparison sources.
The dispatcher's `draft-execution`, `execute`, `variant`, `repeat` and `retarget` commands do not apply to external tasks.

## Capture the actual result

```text
python scripts/production_workflow.py capture --root STUDIO --run RUN --artifact result.png --note "Origin and limits"
```

Capture preserves exact bytes and inspects the declared medium.
Images must decode, JSON and text must parse, and video or audio needs measured streams from ffprobe.
A dispatcher capture must match its already recorded downloaded results.
An external capture cannot exceed the claimed count, and an identical capture creates no second result.
A media header or probe is a processing check, not evidence of an observed expression or a heard sound.

## Review, disposition and selection

Production owns the evaluation and disposition of its candidates.
The Studio reads the same records; its iteration ledger keeps the candidate identity, media references and adoption history, not another verdict.

```sh
python scripts/production_workflow.py draft-review --root STUDIO --run RUN --candidate CANDIDATE --out review.json
python scripts/production_workflow.py review --root STUDIO --run RUN --file review.json
python scripts/production_workflow.py draft-disposition --root STUDIO --run RUN --candidate CANDIDATE --out disposition.json
python scripts/production_workflow.py disposition --root STUDIO --run RUN --file disposition.json
python scripts/production_workflow.py candidate-status --root STUDIO --run RUN --candidate CANDIDATE
```

A review names the actual reviewer, observations, the criteria assessed so far, optional supplemental `evidence`, repairs, unresolved matters and a conclusion.
Each observation names its `evidence` (`candidate` or a supplemental evidence ID), a locator, the observed fact, its interpretation and limitations.
Supplemental entries record path, kind, relation and limitations; their bytes are measured and pinned, not trusted from filenames.

Locators are `whole`; `description` with text; one-based inclusive `lines` or `bytes`; `image-region` with normalized x, y, width and height; or `time`.
A `time` locator names an integer stream index and decimal-string `start_seconds` and `end_seconds` within that measured stream.
A motion check needs a nonzero video interval, and audio needs an audio stream.
Neither whole-file labels nor two still images prove the motion between them.
Text or binary evidence cannot pass an image check.

Each criterion gets one verdict:

- `pass` cites observations that support the criterion's declared evidence kind;
- `fail` records a decisive failure, which may come before other criteria are assessed;
- `indeterminate` means the reviewer observed the criterion and could not decide; it cites observations like `pass` and `fail`;
- `not-assessed` leaves the criterion unassessed, and `not-applicable` excludes it.

The candidate's latest review sets its evaluation, by the first row that applies:

| Latest review | Evaluation |
|---|---|
| none, or every criterion `not-assessed` | `unreviewed` (the review reference is kept) |
| any `fail` | `nonconforming` |
| any `indeterminate`, or an unresolved issue listed | `indeterminate` |
| some criteria not assessed | `partially_reviewed` |
| every criterion `pass` or `not-applicable` | `conforming` |

Disposition is a separate axis: `pending`, `not_selected`, or `selected`, from the candidate's latest decision event.
A disposition file allows `pending` and `not_selected`; only `select` establishes `selected`.
Not selecting a candidate says nothing about its quality.
Each review event names the review it follows in `previous_review`, and submitting the latest review again records nothing.
A synthetic candidate rejected on one failed criterion, with the other left unassessed (trimmed):

```json
{
  "candidate": "43c4d65069b4...", "candidate_sha256": "d035bda74f89...",
  "evaluation": "nonconforming", "disposition": "not_selected", "unassessed_criteria": ["output"],
  "review": "7a64a5f4e4dd...", "decision": "4f422dc3f32d...",
  "reviewed_at": "2026-10-03T19:02:37Z", "decided_at": "2026-10-03T19:02:44Z",
  "selection_current": null, "selection_diagnostics": []
}
```

`selection_current` is true or false for a selected candidate and null otherwise.
`selection_diagnostics` names `SELECTION_REVIEW_CHANGED` or `SELECTION_REPLACED` when a selection is not current.
`status` reports the same states for every candidate.

### Select, optionally adopt, and finish

```text
python scripts/production_workflow.py draft-selection --root STUDIO --run RUN --candidate CANDIDATE --out selection.json
python scripts/production_workflow.py selection-intent --root STUDIO --run RUN --file selection.json
python scripts/production_workflow.py select --root STUDIO --run RUN --file selection.json
python scripts/production_workflow.py complete --root STUDIO --run RUN
```

Fill the selector and reason, then authorize the printed `select` intent as [Production permissions](production-permissions.md) describes.
Put the authorization event digest in `selection.authorization` before `select`.
A selection binds the candidate, its latest review and every selection field.
Every hard criterion needs a supported `pass` first; advisory criteria may stay unassessed with reasons.
A `delivery-only` selection does not change canon.

Adoption follows this order:

1. `select` the candidate with `scope: delivery-only`.
2. Run `adoption-intent`, then `adopt` under its own `adopt` authorization; the Studio accepts the iteration in this step. `adopt` refuses a candidate that is not the run's current selection (`SELECTION_REQUIRED`).
3. Optionally, `select` the same candidate again with `scope: studio-adoption`, citing the adoption record. It needs the run's own adoption result (`ADOPTION_RESULT_MISSING` otherwise).
4. `complete`.

`adoption-intent` and `adopt` take `--candidate`, `--character`, `--iteration` and `--approval`.
`adopt` also takes `--authorization`, the event digest of its adopt authorization.
A catalog adoption adds `--registration-record`, `--pack-dir` and the same explicit pack runtime arguments as the owner.

A run has at most one current selection:

- `select` refuses another candidate while one holds it (`SELECTION_CONFLICT`).
- A disposition (`not_selected` or `pending`) of the selected candidate withdraws its selection explicitly; `studio.py reject` records the same disposition.
- Both refuse the withdrawal while the Studio holds that candidate as the slot's accepted image (`SELECTED_CANDIDATE`). Accepting another image for the slot first lifts the refusal.
- A newer review of the selected candidate also ends its selection, without a disposition.

`complete` verifies the current selection.
Work-ledger finish checks the current production completion.
Preparations, generated images, draft reviews or a task with no selected artifact are not finished production.

`review`, `disposition`, `select`, `complete` and `adopt` rewrite the Studio gallery; [Studio Runtime](studio.md#every-image-with-what-produced-it) covers a failed rewrite.

## Review, repair and a new run

The same review carries repairs (`id`, decision IDs, observation indices, operation, changed targets, reason).
Author a revised task or input files.
`revision-intent` compares the whole prepared input, checks the reviewed scope, and returns an exact `edit` payload:

```text
python scripts/production_workflow.py revision-intent --root STUDIO --run RUN --task revised-task.json --candidate CANDIDATE --repair REPAIR_ID
python scripts/production_workflow.py revise --root STUDIO --run RUN --task revised-task.json --candidate CANDIDATE --repair REPAIR_ID --authorization EDIT_AUTHORIZATION
```

Authorize the returned edit intent, then `revise` creates a new run linked to the parent candidate, latest review, repair and exact changed input.
The new run needs its own direction and submit authorization and real evidence.
Its preparation transfers none of the parent's passing checks or permission to send.
Changed approval evidence requires new authority, not a repair that grants itself more power.

## Deterministic pixel realization

Read [Image Editing](image-editing.md) for the `image-edit` feature.
Its exact intent binds the plan, pinned input pixels, latest reviewed repair and new PNG path to an existing edit authorization.
This creates a candidate in the current run, not a new selected direction or an inherited review.
Contract changes still use `revision-intent` and `revise`.
Retained image outputs can be republished without rerendering.

## Inspectable production evidence

After capture or review, a requested inspection export uses the same prepared sources, consumer, receipts and bytes through [Evidence Review](evidence-review.md).
Exporting a report or study is read-only with respect to production and canon.
Exported observations never authorize a new action; continue decisions through the authority-bearing workflow.

## Scene preparation and reusable authoring input

Use [Scene Persona Material](scene-persona.md) to preserve a full-reading result for one scoped scene.
Add `scene-persona` to the task features and name local selectors as `scene_materials: [{"plan": "scene-plan.json", "bundle": "scene-material"}]`.
Preparation checks the complete source files and deterministic documents, stores their dependencies, and includes the document in `consumer.authoring_materials`.
The agent interprets the material into the visible state, performance and
relationships needed for the authored depiction.
Source definitions, internal keys and review evidence remain in the authoring context.
Viewpoint limits and exact submitted inputs keep their own boundaries.
Public material requires an explicit content hash and accepted-by or basis instead of a search for its producer.

For intake of existing source text, use [Source Material](source-material.md).
For observed host trials, use [Agent Evaluation](agent-evaluation.md); process success is not proof of task completion or expressive quality.
For recurring failures, use [Repair Analysis](repair-analysis.md) over actual reviews, then the repair and authorization process.
None of these commands adopts or sends.

## Input variants and intentional repeats

```text
python scripts/production_workflow.py variant --root STUDIO --from RUN --changes-file changes.json --prepare
python scripts/production_workflow.py variant --root STUDIO --from RUN --changes-file - --candidate CANDIDATE --prepare
python scripts/production_workflow.py repeat --root STUDIO --from RUN --prepare
```

`variant` starts from a prepared input; it needs no captured candidate or completed trial.
`--changes-file -` reads the changes from standard input.
A change made after looking at an image names each candidate it answers with `--candidate`.
The new run records those candidates and their latest reviews as `parent.basis`.
Without `--prepare`, the result is a check with `run: null`, and it leaves no file behind.

The changes file follows `schemas/authoring/production-changes.schema.json`:

```json
{"changes": {"parameter:steps": 22}, "reason": "Compare one declared parameter under the same fixed inputs."}
```

Each key of `changes` is a field the execution plan's `mutable_fields` declares; none is an internal JSON pointer.
A nested parameter such as `parameter:settings.guidance` takes nested JSON, not a literal dotted key.
Each declaration has these keys:

| Key | Value |
|---|---|
| `description` | What the field changes. |
| `schema` | The JSON Schema of an accepted value, with the execution profile's allowed values. |
| `required` | Whether the compiled request needs a value. |
| `nullable` | Whether `null` is accepted, which removes that input. |
| `value_form` | `inline` for a JSON value, or `studio-file` for `{"path": "studio-relative-file.json"}`. |
| `document_type` | For a studio file, the document it must hold, such as `prepared-reference-set` or `production-spec`; null for an inline value. |
| `checks` | The compiler checks that run again; they match `phase` in the report's `checks`. |
| `rebuild` | The artifacts built again: `package`, `request` or both. |
| `protected_criteria` | `unchanged` for seed and count, `redefine` for direction and criteria, `recheck` otherwise. |

Every field problem is collected before the variant stops, and no formal run is created.
[Diagnostic codes](#diagnostic-codes) lists the variation codes.
`references: null` removes the selected reference set and reruns the required contracts.
Replacing a named document also updates the task source role that points at it.
A removed dependency stops being a freshness requirement, and unchanged dependencies stay checked.

A prompt edit is checked again against retrieval and render intent.
Supply an explicitly reassessed `retrieval-record` when the original record does not apply to the new wording.
The runtime invents no lookup or approval evidence.
Unchanged evidence and the fixed runtime stay reusable; current source applicability and pack choices still apply.

The derived task and replaced inputs are published with the new run under `production/runs/RUN/inputs/`.
They are recorded as `task-source` dependencies, and nothing is written under `production/inputs/`.
A failed `--prepare` keeps its staging, with `failure.json` and `inputs/`, for `staging-cleanup`.
A synthetic parameter variant from standard input reports this derivation (trimmed):

```json
{"derivation": {"run": "01a10323-be7f-...", "kind": "variant", "reason": "Compare one declared parameter.",
  "changes": [{"field": "parameter:steps", "before": 20, "after": 22}], "basis": []}}
```

Its new run holds `inputs/parameters.json`, `inputs/requested-changes.json` and `inputs/task.json`.

`repeat` creates another run for the same input and semantic request, with its own future execution claim.
It compares the repeated input before registration and publishes nothing on a mismatch.
It never borrows its parent's exact execution decisions; `resume` instead recovers the parent's execution.
Neither variants nor repeats change a candidate's disposition, select a result or adopt identity.
The [complete synthetic example](../../examples/generation/README.md) shows preparation, variants and repeats.

## Change the target explicitly

`variant` keeps its model and service.
To select a different target, supply a complete task with the reassessed specification, parameters, retrieval, route reading and request-validation evidence for that target.
Keep its work task ID and production series ID, and record why the target changes.

```text
python scripts/production_workflow.py retarget --root STUDIO --from RUN --task retarget/task.json --reason "Use the selected target for this expression." --prepare
```

Without `--prepare`, the shared compiler checks the task and returns a preview without a formal run.
With it, the new run records its parent input and request.
Unchanged authored source files can be referenced directly, without copying or editing them again.
Target-specific guidance, execution profiles, retrieval applicability and reference transport are validated again.
Exact authorizations, claims and image reviews are not inherited.

Retargeting resolves the currently selected runtime, including explicit `--state-file`, `--cache-dir`, `--managed-root` and `--pack-root` options.
The same target is accepted when the current pack runtime differs from the parent's fixed runtime.
The new run then records `{"field": "runtime", "before": ..., "after": ...}` in `parent.changes`.
Retargeting does not reactivate a disabled pack or restore the parent's provider.
The [generation example](../../examples/generation/README.md) includes a second synthetic model with its own execution profile.

## Regression coverage

The synthetic generation example is the executable entry path.
These developer checks exercise the same public contracts; an ordinary production call reads none of them.

| Contract | Executable checks |
|---|---|
| Evidence, transactions and operation diagnostics | [test_production_foundation.py](../../scripts/test_production_foundation.py), [test_production_operations.py](../../scripts/test_production_operations.py) |
| Fixed runtime snapshot reuse and irreversible-boundary checks | [test_runtime_snapshot.py](../../scripts/test_runtime_snapshot.py) |
| Exact execution and handoff boundaries | [test_production_execution.py](../../scripts/test_production_execution.py), [test_production_boundaries.py](../../scripts/test_production_boundaries.py) |
| Current grants, execution ownership and result records | [execution_lifecycle_smoke_test.py](../../scripts/execution_lifecycle_smoke_test.py) |
| Input variants and explicit target changes | [test_production_variation.py](../../scripts/test_production_variation.py), [test_production_retarget.py](../../scripts/test_production_retarget.py) |
| Public commands, JSON files and standard input | [test_production_cli.py](../../scripts/test_production_cli.py), [test_production_file_input.py](../../scripts/test_production_file_input.py) |
| Candidate evaluation and canonical adoption | [test_production_review.py](../../scripts/test_production_review.py), [test_production_adoption.py](../../scripts/test_production_adoption.py) |
| Model trials and observed schemas | [test_model_observation.py](../../scripts/test_model_observation.py) |

Run them all from the installed source root with `python -m unittest discover -s scripts -p 'test_*.py' -v`.
Tests use labeled synthetic approvals and local transports, never real credentials.
A passing test is evidence of its checked contract, not a visual quality judgment or a release certification.


## Managed next-action drafts during repeated work

`status` names a draft under `production/decisions/RUN/KIND/BASIS_DIGEST.json`, scoped to the exact run, candidate and decision basis. When that draft exists, the next action points to inspection/completion and the appropriate apply command instead of repeating a failing `--out` write. A completed draft is not evidence of approval until the usual validator accepts its actual author evidence. A new review basis gets a different draft; no existing decision file is overwritten.

The Production run registry resolves the prior run in the **same task and production series at the saved registration boundary**. It does not open every unrelated historical run merely to find that owner. The selected required predecessor is fully verified; a damaged required series run stops protected-criteria use with `PREDECESSOR_UNAVAILABLE`, rather than silently skipping the comparison.

Sheet batching uses the same commands and statuses. [Sheet fills](sheet-fill-workflow.md) adds dated result ownership, frozen batch inputs and discovery. [Studio Runtime](studio.md) documents gallery and timeline recovery; [Operation diagnostics](operation-logs.md) distinguishes auxiliary views from the formal records required before a send.
