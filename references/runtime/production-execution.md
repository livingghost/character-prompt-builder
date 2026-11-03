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
Open the work task before reading or drafting its inputs, using
`work_ledger.py begin --studio STUDIO --goal TEXT --step TEXT`. Reuse its task ID
through input authoring and preparation. The input builders and route reader
save their progress under that task automatically.

### Read the route to completion

Begin with the route, applicable features and the target's model or prompt family. A paged read uses a source-byte budget:

```bash
python scripts/execution_routes.py read reference-artifacts --root STUDIO --feature sparse-retrieval --page-bytes 16384
```

Each page prints its source text and a `reading-actions: ` line containing JSON. While source bytes remain, its `continue` action reads the next page. Its `replay` action reads the delivered page again. Each action contains an `argv` argument array, the same invocation quoted as `command`, and its purpose in `reason`. Execute the complete returned `argv`, or the complete `command` string. Continue until the command prints `reading-key` and the final `reading-record` path.

The action retains the selected environment's Python, the installed script, the absolute reading ledger, the Studio when present, the page budget and the snapshot's exact pack runtime, including its additional discovery roots. The cursor supplies the saved route, features and prompt family. `--reading-ledger` locates that existing reading for continuation or replay. The initial read gives an explicit `CPB_READS_LEDGER` location priority; otherwise it uses the specified or current Studio's ledger, then the configured home ledger.

The reader preserves all source bytes across pages and issues the reading key after their complete delivery. The final source check still verifies the snapshot's document and resource hashes. If the source edition changed during reading, begin a new route reading from that edition.

### Apply the completed reading

The route read writes a reading record at the path it prints, with the route, the key and every hash filled.
The author decides which of the read documents apply to this task, and lists only those.
When using `draft-inputs` and `build-inputs`, author the applications once in `choices.reading`, with the issued `reading_key`. The builder resolves the issued document hashes and writes the completed reading record into the generated task. A draft from a saved Run already supplies its previous key and applications for current assessment.
When authoring a task directly, fill the applications in the emitted reading record instead and name that file as the task's `route_reading`.
In either editing location, each entry in `applied` names the document's `path`, a `quote` of twelve or more words from one paragraph of it, and `why` it applies.
Copy the raw Markdown spelling, including link destinations such as `[reference delivery](reference-delivery.md)`, backticks and emphasis markers. The match normalizes whitespace and line wrapping only; rendered link text or rewritten prose is a different quotation.
Each entry in `resource_applied` names `"resource": "prompt-writing-guide"`, a `pointer` such as `/sections/2/rules/0`, that rule's exact text as `quote`, and `why`.
The reading key binds the declared route and features. If either selection changes, issue a reading for the new selection and reassess the applications that still apply.

- `inspect-inputs` shows declared sources, recorded candidates, and required choices.
- `draft-inputs` creates a compact `choices.json` to edit and a separate `context.json` to read. Choices contain reading applications, selected visual and validation evidence, explicit task changes, and an optional external image-input plan.
- `build-inputs` resolves those choices through the owning contract builders. It derives image hashes, adoption selectors and reference positions, and binds generated continuity and validation paths directly into the resulting task.

[Model request evidence](model-evidence.md#the-request-validation-record) states when a task needs an authored request validation record.
An incomplete selection returns named unresolved fields and publishes nothing; the task and its sources stay unchanged.
For drafting or building, select either `--task FILE` or `--from-run RUN`. A saved run supplies its captured task and exact delivery, so the operator does not copy a task into another editing document. Copied reading applications still need assessment for the current work. Explicit `task_changes` select changed source, depiction, route or review fields; authority and task identity retain their owners.

For external image work, select `external: {"image_input": "inputs/selected-plan.json"}`. The builder materializes the prompt from the single delivery source and the target, count and media values from that plan's acquired field mappings. Other native controls retain their declared values. It writes the exact request and image-input plan, measures evidence hashes, validates the resulting input and shows its substantive changes. A supplied hash remains a commitment to the selected evidence. This creates inputs, never grants or satisfied judgments.
The [synthetic input assembly example](../../examples/input-assembly/README.md) contains complete commands, choice fields, and actual output.

### Resume input authoring

Interruption can occur before a run exists. Inspect the open work task with:

```bash
python scripts/production_workflow.py inspect-inputs --root STUDIO
python scripts/production_workflow.py status --root STUDIO
```

`inspect-inputs` without a source selector reads the task's saved authoring
state. `status.current_task.authoring` exposes the same information, and session
entry shows its paths and continuation commands. The report names existing
`choices.json`, its context, published input tasks and reports, partial route
reading, completed reading applications, and the last recorded check when one
exists. Continue those files and actions after compaction. A source selector
still performs the ordinary inspection of that task or saved run.

The builders register each output location before publication. Recovery can
therefore find a directory that was published before its caller returned.
The reader records committed page ranges and the saved cursor. Recovery offers
the existing continuation or replay action and reuses completed application
records. It does not issue another key or mark an authored application complete.
Unanswered choices remain unanswered, and a saved check is diagnostic history;
preparation and execution still evaluate their actual current inputs and authority.

`scripts/production_authoring_state.py` owns these discovery pointers under
`work/tasks/TASK/authoring/`. They identify work owned by that ledger task and
do not replace its inputs, reading receipts, run records or author decisions.
Inspection reads the existing files without regenerating them or loading a
catalog merely to discover a saved path.

## Prepare one complete input

Use the open work task's ID in a task that follows `schemas/authoring/production-task.schema.json`.
The task declares its route, direction, full source selectors, criteria and execution kind.
For dispatcher generation it also declares `generation` and `recording`.
The prompt file named by `delivery.path` is the single authored prompt.
For image work, the agent establishes the selected artifact and present
situation, including the premises the renderer needs to understand its action,
performance and reference use. Compose that complete input from the sources,
then refine details and necessary exclusions under
[Prompt Composition](prompt-composition.md#carry-scene-intent-into-depiction).
Define criteria at the task's artifact scope and declared evidence medium;
keep grading language and wider production or story decisions in their owning
records. A task can use image, text, motion or other supported evidence as its
requirements demand.
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
- `--file` of `authorize`, `review`, `disposition`, `selection-intent`, `select`, `accept` and `authority-import`;
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
Each producer declares the exact files it writes. The manifest persists that complete set with each file's content hash and size.
Before publication, the stage must contain exactly those files and its root lifecycle controls: `manifest.json`, `owner.json`, `failure.json` and the lock file.
Reference companions retain their complete source proof, delivered media, supplementary masks and nested metadata.
For example, a companion's `references/manifest.json` is an immutable input even though the root `manifest.json` describes the whole publication.
An unexpected or missing member gives `ARTIFACT_SET_MISMATCH`; the failed stage keeps its bytes for inspection.

The fixed runtime has its own complete membership in `snapshot.json`.
Reading, publication and reuse check that membership and the declared file contents.
Reuse verifies both the staged capture and the existing snapshot before disposing of the duplicate capture.
An integrity check can be reused within one public operation; the forced check before an external effect reads the contents and membership again.
After the runtime is published, it belongs to the Studio's runtime snapshot store, independently of the compiled run.

Published inputs stay bound to their manifest through load, recovery and execution.
Recovery of a published but unregistered run checks complete membership against the same producer declarations and root lifecycle controls before registration.
An unexpected or missing member makes that publication unrecoverable with `ARTIFACT_SET_MISMATCH`, preserving its files for inspection.
Execution copies the complete declared reference companion into its journal and verifies the exact copied bytes.
Later candidates, reviews and execution evidence add content-addressed objects under the existing formal event records.
Those events own the additional objects; the immutable input manifest remains unchanged.
Explicit draft output paths can also place separate documents beside the published inputs.
These later files retain their own purpose and enter the run's evidence only through the corresponding capture or review operation.
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
It contains the generated run and input identities, with one compact entry in `decisions` for each required operation. Each entry selects its grant and contains only its reason, stop-condition assessments and applicable request judgments. Direction and submission remain separate entries and formal events. The full request, exact targets, payloads, actor identities and output counts are derived from the prepared run when execution records those decisions.

Use the `workspace --phase input` view to read the complete model-facing input without the assessment basis, then `workspace --phase decision` to compare that reading with the commission, source roles, current authority and request-review requirements. These views gather material already needed for the decision; they add no approval or read-completion event. Read only context that is missing from the active session. Complete the reasons, stop-condition assessments and final-request assessment from actual evidence.
[Production permissions](production-permissions.md#authorization-and-execution-records) describes each authorization and its `request_decision`.
For the `rendition_review`, first reconstruct the artifact and depicted
situation from the sealed prompt fields, supported controls and actual supplied
images. State which premises and relationships the delivered input establishes.
Then compare that reading with the brief and selected production scope, using
[Prompt assembly and review](prompt-composition.md#prompt-assembly-and-review).
Resolve missing premises and instructions outside the requested depiction in
their owning authored inputs. Record the correspondence and remaining limits
in the existing assessment reasons. The request validator checks the identity,
coverage and author of those assessments; the agent judges their meaning.
A draft has unanswered judgments and grants no permission.
A supplied decision file must cover the complete operation set; altering targets does not narrow the prepared requirement.
With valid exact receipts already recorded, `execute --root STUDIO --run RUN` needs no decision file.

The run owns one complete model input and execution plan, including its handoff recipient and method. Dispatcher work also owns its sealed Generation Package.
A different parameter, count, model, service, media binding or recipient requires a newly prepared input.
A receipt for another request cannot replace that contract, and a mismatch names the field before an execution claim is committed.

For a dispatcher, `execute` performs these steps in order:

1. It loads the sealed package and exact request.
2. It rechecks the recording destination: the Studio character, the slot, the sheet-panel condition and the subject mapping.
3. It resolves the Studio's credential selection and checks current grants and exact request approval.
4. In one transaction, it records the dispatcher handoff, records execution ownership with the nonsecret credential selection and claims the run.
5. The transaction commits before network I/O; each upload and the send then gets its own durable start boundary.
6. It saves the provider answer, downloads every returned image and registers each one as a candidate.
7. Once the provider result is terminal and all returned images are saved, it deletes the inputs uploaded by this execution through the selected transport's deletion capability. Source files, generated images and response records remain saved.

Missing scope or approval rolls back step 4 before any upload or send.
Each upload or send boundary checks the current grant and the live packs again, whatever an earlier check cached.
Revocation after a start boundary cannot undo the started request.
The send boundary records the management identifiers sent with the request.
The prepared submit scope includes deletion of its own uploaded inputs where the transport supports it. Deletion uses the immutable upload receipts and a separately saved request, so cleanup needs no new submission decision. A new generation always uploads again; only recovery within the same execution reuses its completed uploads.
For an external image task, the same `draft-execution` and `execute` commands validate the two decisions, record their separate authorizations, hand the input to its declared service and claim one host call. `execute` returns an `external-execution-instruction` with `host_request` with the exact request, target and supplied-media bindings. The host invokes its named tool once with that input, then receives the actual result as described below. The local command itself does not invoke an external host tool. A claimed external run cannot be executed again; recover that call after interruption.

Low-level `authorize` and both execution branches share the same permission and execution-claim implementation.
A request has one claim even when it returns several images.
Use `resume` for recovery, `variant` for changed input, and `repeat` for an intentional additional request.

### Authentication at execution

[Studio authentication](studio-authentication.md) owns credential configuration and its CLI. The selected offering's service ID identifies one entry in the Studio's private `credentials.json`. That entry contains a saved `api_key` or an `api_key_env` variable name. Follow the existing configuration and the owner's chosen method. Missing configuration or an unusable source gives a diagnostic and a concrete setup or repair action.

For an environment source, the Agent uses `studio.py credentials prepare SERVICE --environment NAME`. Execution reads that variable from its own process. Check the service and run once the variable is available. When the service has no entry, the general diagnostic proposes saved-entry preparation; follow an existing environment choice by preparing that named source. `set --from-env` instead copies the current variable value into `api_key`.

For saved input, the Agent runs the returned `credentials-prepare` action and finishes the required service entries before handing the owner `input.path` and `input.json_pointer`. The owner fills `api_key` under the selected service name and saves, while the Agent pauses its own edits. The Agent then checks that service and this run's authentication selection and readiness. The handoff requires access to the same file in the execution environment. An empty string is a supported waiting state, with a `credentials-status` action requiring the owner's input. Saved input becomes available to the next authentication resolution; submission remains governed by execution authority.

The claim records the nonsecret service and source, including the variable name for `api_key_env`. Pre-send continuation and provider lookup require that recorded source. A change between saved and environment sources, or a change to the recorded variable name, requires explicit restoration before authenticated continuation. Replacing the value at the same saved field or environment variable supports rotation and preserves the prepared request. For recovery, supply a value belonging to the provider account that owns the pending task; the local source identity does not establish that remote account relationship.

A source-difference diagnostic returns an explicit restoration action with `requires_author_input: true`. Apply the user's existing direction when it settles the intended source, or obtain the owner's decision when that choice remains open. A setup action with `requires_author_input: false` prepares the saved field within the authorized task. The Agent presents any remaining value-entry handoff after setup. Credential JSON stays outside ordinary production inputs and evidence, preserving the run's credential-independent input identity.

A complete saved answer can be downloaded and registered without resolving the API credential. A transport declared credential-free also needs no key. External host tools keep their own authentication; exact handoff and submission authorization still govern their use.

Local availability checks establish readability and format. They make no provider request and grant no submission authority. The value is supplied separately to the transport, outside request and input content hashes.

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
| `cleanup.state` | `not-needed`, `waiting`, `pending`, `failed`, `outcome_unknown`, `complete`, `unsupported` |
| `registration` | `unregistered`, `registered`, `projection-missing` |
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
Each diagnostic has `code`, `severity`, `phase`, `file`, `pointer`, `message`, `required_action` and `blocked_checks`. A phase or producing contract with a declared owner also supplies `guidance`; unmapped phases omit it.
When present, `guidance.document_path` identifies that owning document and section. `guidance.schema` names the schema when the check declares one; specification diagnostics include an optional `guidance.validation` action with executable `argv`, quoted `command` and `reason`. The action runs the same validator on the named specification alone. It is available for a focused correction, and is not an additional prerequisite for `check` or `prepare`.
The compiler reports each structural defect of every declared external specification in one result, including when a separate request binding fails. Only checks that depend on an invalid source wait for its correction. Each specification diagnostic names that source file and its field, rather than the enclosing task file.
Some add `run`, `expected`, `actual` or other details.
Exit 2 applies unless a row says otherwise.

**Input and stored records**

| Code | Reports |
|---|---|
| `INPUT_ARGUMENT_INVALID` | The arguments do not match the command. The usage goes to stderr, and the operation log records this code. `logs-cleanup` prints it for an invalid date or selector. |
| `INPUT_SCHEMA_INVALID` | A JSON input breaks its schema. |
| `INPUT_UNREADABLE` | A declared input or the task cannot be read; adds `file`, `pointer` and `cause`. |
| `INPUT_CONSISTENCY_ERROR` | Inputs contradict each other or a contract they must satisfy. |
| `PROMPT_DELIVERY_MISMATCH` | The exact external prompt text differs from its delivery source. Reports both files, the request field, newline counts and whether line endings alone differ. Use `build-inputs` to derive both from the delivery; manual UTF-8 byte writes preserve LF across platforms. |
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
| `ARTIFACT_SET_MISMATCH` | The stored tree has missing or unexpected members relative to its producers' declared set; the diagnostic lists both. |
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
| `RUNTIME_SNAPSHOT_CORRUPT` | The fixed runtime snapshot differs from its digest or complete declared membership; a membership failure retains its cause. |
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
| `CREDENTIAL_UNAVAILABLE` | Exit 3. The selected credential is missing, unusable or differs from the execution's pinned source. Follow the diagnostic's Studio credential repair action; an explicit binding keeps its own failure instead of choosing another source. |
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
| `REVIEW_INCOMPLETE` | A hard criterion is missing or unassessed, so review is needed before selection. |
| `OWNER_ACCEPTANCE_REQUIRED` | A nonpass hard criterion or unresolved matter lacks the owner's explicit acceptance. |
| `REVIEW_MISMATCH` | A disposition cites a review that is not the candidate's latest. |
| `SELECTION_CONFLICT` | Another candidate holds the run's current selection. |
| `SELECTION_REQUIRED` | The candidate is not the current selection of its run. |
| `SELECTION_REVIEW_CHANGED` | A newer review of the selected candidate ended its selection. |
| `SELECTION_REPLACED` | A later selection of another candidate replaced this one. |
| `SELECTED_CANDIDATE` | The Studio holds the selected candidate as its accepted image. |
| `SLOT_ACCEPTANCE_NOT_APPLICABLE` | The run is not an image with a Studio recording destination; use its ordinary selection scope. |
| `STUDIO_CANDIDATE_REQUIRED` | The exact Production candidate lacks its one recorded iteration; recover that run's recording. |
| `SLOT_SELECTION_REQUIRED` | Acceptance needs a current `studio-slot` selection; complete the actual acceptance decision. |
| `SLOT_ACCEPTANCE_REQUIRED` | The selected slot lacks its matching acceptance receipt or result; resume the same acceptance. |
| `SLOT_ACCEPTANCE_MISMATCH` | The recorded image or destination differs from the exact selected candidate. |
| `SLOT_ACCEPTANCE_CONFLICT` | The slot changed after the inspected or committed decision; inspect the newer acceptance before deciding again. |
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
External preparation saves each actual prepared delivery carrier in the run's
ordinary content-addressed object store after checking its recorded hash.
It also archives accepted Studio proofs and every transitive
artwork, provenance and approval file through the existing Studio reference
owner. The run stores these under `image-input.references/studio/` and in its
ordinary snapshot object store. Recorded proof verification needs no live
adoption after a call; a new send still checks the current accepted source.
Historical review uses the saved source and carrier bytes even after their
live files move. Preparation establishes the chosen input; the submission
records establish the actual call and its transmitted media.

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
`model.prompt_input` states the evidenced input mode and forms. A tag-based
target also names its `prompt_dialect`. A known service/model offering retains
its catalog input contract even when an authored plan labels it missing;
an external declaration cannot reclassify that offering to skip vocabulary
search. Resolve an unknown checkpoint's input contract before finalizing text.

Save one exact request JSON. `external_request` names its relative file and
field paths as arrays of keys and array indices. It declares `prompt_field`,
`model_field`, optional `operation_field`, optional `count_field`, expected
`count` and ordered `reference_fields`. Each reference field includes the
reference ID, exact uploaded value and pinned upload evidence. Every selected
reference is covered. Each declared media field shape is checked across all
array positions. For example, `images[*].uri` covers every such URI, including
inside nested arrays. A mixed content array may retain text-only entries.
References with identical prepared carrier hashes and media types can bind
the same media field when its value also matches. This includes different
sources assigned to regions of one prepared board. Their distinct logical
scopes, attachment number and board regions remain recorded. For direct
inputs without a prepared set, shared fields require identical source bytes.

For tag-based input, also declare `negative_field` (null when absent), the
interface's `prompt_syntax`, and `vocabulary_record` with `path`, `sha256` and
`locator` selecting the ordinary prompt retrieval record. Search that exact
prompt and negative text with `prompt_retrieval.py --search-vocabulary` using
the catalog `--model`, or an acquired `--model-file` for an external target.
`prompt_syntax` declares a default grammar and either `control: null` for a
fixed grammar or a control's exact field path and native-value mapping. For
example, a synthetic interface can map `controls.text_mode: "weighted"` to
`compel`; the request field name itself has no grammar meaning. Use the grammar
selected by the actual request when searching its vocabulary.
When the catalog offering has an execution profile, the applied render intent's
mode determines its grammar. Preparation checks the external request's grammar
against that mode; a native operation name does not select a rendering mode.
Preparation repeats the dictionary search and checks the selected terms against
the actual request fields. Existing wording is preferred when it preserves the
intended meaning; a needed authored expression retains its comparison reason.
No plot is required solely to use the external vocabulary record. A descriptive
target does not acquire a tag-search obligation from this binding.
The saved binding retains the inspection and the model constraints it used.
Reading that binding inspects its exact text again with the pinned grammar and
limits, rejects recorded problems, and requires the saved inspection to match.
It does not read a mutable model catalog to reinterpret a saved request.

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
against that entire input, bound to `image_input.binding_sha256`. Apply the
[prepared-request readback](#execute-the-prepared-request) to its scoped
depiction, supplied context, actual reference use and production ownership,
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
per-image byte size and dimensions from the actual prepared carrier bytes,
or from the original image bytes for direct inputs. A shared board is measured
as the one image bound to its request field. Unsupported
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

Supply the actual call record directly when receiving its result. This synthetic example selects the recorded arguments and tool identity without authoring a receipt:

```sh
python scripts/production_workflow.py receive-external --root STUDIO --run RUN --response evidence/response.json --artifact result.png --call evidence/host-call.json --request-pointer '["arguments"]' --model-identity-pointer '["tool"]' --reason "The host returned its final response and image."
```

`request_pointer` selects the actual recorded argument object. For endpoint or
tool identity, `model_identity_pointer` selects its exact recorded value; use
null when identity lives in the request's model field. The saved call must
match the prepared request and declared endpoint/tool. Using the prepared JSON
itself, another file with the same bytes, or the runtime's generated execution instruction fails as call evidence.

Settlement returns `request_evidence.status: matched-recorded-call` when the
actor's recorded call matches. Without `--call`, it returns `not-provided`;
result capture and accounting still work. The receipt and supplied call record
remain immutable evidence. A mismatch fails comparison without deleting already
captured results. A matching actor-attested record does not establish provider
execution, visual reference influence, artistic success or acceptance. Those
claims need their own response and image review evidence.

## Authored and manually executed work

Authored text uses the same immutable sources and formal event store, without a model package. `handoff-intent`, `draft-authorization`, `authorize` and `handoff` describe an actual conversation or manual handoff. External non-image work uses these operations and its separately authorized `external-intent` and `claim-external` boundary.

External image work uses the shared `draft-execution` and `execute` flow above. Set the task's `image_input`; existing-scene edits also activate `semantic-instruction-edit` and declare `semantic_edit`. Preparation exposes the complete exact request. The submit grant must allow the binding's validation mode and have `request_scope: null`; dispatcher scope cases use their own request contract. Existing explicit authority may supply that grant without another confirmation. The claim commits execution ownership and the external-send boundary before returning the request to the host. Reading a claim again does not permit a second call.

Receive the actual host response and returned files in one operation:

```sh
python scripts/production_workflow.py receive-external --root STUDIO --run RUN --response evidence/response.json --artifact result.png --reason "The host returned its final response and image."
```

Repeat `--artifact` for several local files. For an image encoded inside the actual response, use `--image-pointer '["result", "image"]'`; repeat it for several fields. The selected value must be a base64 string or an image data URL. Downloaded remote files use `--artifact`. The command decodes and measures each image, stores its bytes and captures it before recording settlement. It performs no provider call, image review, selection or adoption.

The runtime derives the claim, authorized executor, output count, hashes and content-addressed receipt path from the run and actual files. The generated receipt follows `schemas/production-external-receipt.schema.json`. The executor supplies the observed outcome reason and `--pending` when the host has not finished. An optional `--cost-pointer` selects an actual response object containing `currency` and a decimal-string `amount`; without such evidence, usage stays unknown. Native provider responses remain saved in full. No estimate or absent charge becomes zero.

Optional `--call`, `--request-pointer` and `--model-identity-pointer` select real host-call evidence for comparison with the prepared request. A mismatch retains already captured images and prevents a false matching receipt. Every capture commits before settlement, so an interrupted operation can be repeated with the same actual response and files to finish acquisition and recording. It reuses identical image bytes and never sends again. Recovery uses saved production evidence even when original creative sources or grant evidence have moved. Final accounting does not complete artistic review.

For a further external trial, use `draft-inputs --from-run RUN`, edit only changed choices and `build-inputs --from-run RUN`, then prepare the emitted task. The source run and its earlier candidates remain intact. A changed target requires its explicit model/interface evidence and applicable route reading; a changed depiction still requires its own input review. Dispatcher `variant`, `repeat` and `retarget` use their existing compiler. `production_direction_smoke_test.py` exercises external decisions and reception with synthetic local files and no provider call.

## Capture the actual result

```text
python scripts/production_workflow.py capture --root STUDIO --run RUN --artifact result.png --note "Origin and limits"
```

Capture preserves exact bytes and inspects the declared medium.
Images must decode, JSON and text must parse, and video or audio needs measured streams from ffprobe.
SVG image evidence uses the same self-contained, inactive content checks and
renderer as reference preparation. Its original bytes remain available as an
image for region observations and the review export.
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
Additional evidence entries record path, kind, relation and limitations; their bytes are measured and pinned, not trusted from filenames.

### Observe before interpreting

First inspect the actual candidate and record what it visibly or measurably
establishes, with locators and limits. When a separate reviewer context is
available, give it the candidate and only the technical information needed to
access the relevant file, page, region or stream. Withhold the brief, prompt,
expected portrayal, earlier failures and production history until that first
observation is recorded. `workspace --phase observe --candidate CANDIDATE` supplies only the saved candidate bytes, their access paths and measured media information. Give that view alone to the first observer. The later `workspace --phase review --candidate CANDIDATE` supplies the assessment basis. Even the compact editing draft contains criterion identifiers, so keep it out of the first observer's input.

Then compare the observed depiction with the commissioned result and applicable
source or reference evidence. Use the prepared criteria and allowed variation
within that authority. Additional inspection may answer a
criterion-specific question; keep those later observations distinguishable from
the first reading in their `limitations`. Preserve the direct observation in
`observation`, its meaning against the criterion in `interpretation`, and the
unsupported or uninspected scope in `limitations`. Record the actual reviewer
input boundary and reading order in the review's `conclusion` and relevant
observation limitations. These existing fields require no new record format.

Inspect at the scale the judgment requires. A whole-image view can establish
composition while leaving a small connection, boundary or count unresolved.
When that detail decides a criterion, inspect the available original pixels or
an appropriate region while retaining enough surrounding context to understand
the relationship. A crop or enlargement helps only when it reveals relevant
evidence; it cannot establish detail absent from the source. Record a supported
verdict when the evidence resolves the claim, and retain `indeterminate` when it
does not.

If the same context produced and reviewed the work, state that this is author
self-review and not independent. Describe the artifact before applying the
expected reading, while retaining the limitation that the intent is already
known. An instruction to forget that intent does not erase it. Input-limited
review also remains an interpretation, not a controlled blind comparison; the
[Blind Image Evaluation Protocol](../blind-image-evaluation-protocol.md) owns
study design and release claims.

A face oriented toward someone does not alone show eye contact; cropped eyes
can leave it undecided. A still stance does not establish a path of motion, and
a smile alone need not distinguish the requested emotional state. Assess the
artifact against what its evidence can establish. Use `indeterminate` for an
inspected criterion with inconclusive evidence and `not-assessed` for one not
inspected. Do not infer a pass from the prompt, the intended story or a valid
request. A valid prompt and a rejected candidate can coexist. A different
composition may pass when it preserves the same anchors and allowed variation.

### Apply the prepared review basis

For image inputs, the review workspace includes the original source images and each prepared delivery carrier available in the run. Carrier evidence retains
the source assignment, transformation, attachment position and board region;
external inputs also retain the exact request field. Several logical
references may share one saved carrier while keeping their individual
authority scopes. Compare the candidate against the image and region that
carry each requested attribute, and use the original source to assess what
the preparation preserved. Missing or changed saved bytes fail integrity
validation. The submission evidence separately establishes whether those
prepared inputs were sent.

The review workspace presents the prepared purpose and intended effect once, followed by each criterion's evidence kind, applicable selected realization, craft questions and accepted variations. The editing draft contains unanswered observations and verdicts, with empty reasons. Write the actual judgment there. Its `evidence` list is for additional authored sources; the runtime resolves prepared source and carrier evidence automatically, using the stable IDs shown in the workspace. The formal review retains all effective evidence and its saved bytes. Source records establish what was commissioned; observations
establish what the candidate supplies. The chosen realization is itself open
to judgment against that commission. A renderer can obey a prompt whose
choices miss the request. Do not infer success solely from agreement with
self-authored means, or silently treat those means as user requirements.
Review the basis of a mistaken criterion in the same assessment and revise
the responsible task through its existing authority before formal selection.
Keep uncertainty about an unsupported judgment in the review's limitations.
An intentionally ambiguous portrayal is itself assessable when the artifact
requests it. Changes to a live task leave this prepared review basis unchanged.

Locators are `whole`; `description` with text; one-based inclusive `lines` or `bytes`; `image-region` with normalized x, y, width and height; or `time`.
A `time` locator names an integer stream index and decimal-string `start_seconds` and `end_seconds` within that measured stream.
A motion check needs a nonzero video interval, and audio needs an audio stream.
Neither whole-file labels nor two still images prove the motion between them.
Text or binary evidence cannot pass an image check.

Each criterion gets one verdict:

- `pass` cites observations that support the criterion's declared evidence kind;
- `fail` records a decisive failure, which may come before other criteria are assessed;
- `indeterminate` means the reviewer observed the criterion and could not decide; it cites observations like `pass` and `fail`;
- `not-assessed` leaves the criterion unassessed and permits an empty reason; every judged verdict needs a reason. `not-applicable` excludes the criterion with its explanation.

The candidate's latest review sets its evaluation, by the first row that applies:

| Latest review | Evaluation |
|---|---|
| none, or every criterion `not-assessed` | `unreviewed` (the review reference is kept) |
| any `fail` | `nonconforming` |
| any `indeterminate`, or an unresolved issue listed | `indeterminate` |
| some criteria not assessed | `partially_reviewed` |
| every criterion `pass` or `not-applicable` | `conforming` |

These labels summarize all recorded criteria, including advisory ones. They
do not decide selection eligibility. An advisory failure or an inconclusive
advisory observation can coexist with supported passes on every hard criterion.
Keep the limitation and any optional repair visible rather than changing its
verdict to obtain a preferred aggregate label. The owner's explicit acceptance
can permit selection of assessed departures or uncertainties under the rules
below; the candidate keeps its actual evaluation.

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
`selection_basis` distinguishes `review-pass` from `owner-allowance`, and
`owner_acceptance` exposes the recorded allowance. `selection_requirements`
retains the latest review's `unassessed_hard_criteria`,
`nonpassing_hard_criteria` and `unresolved_indices`; acceptance does not erase
those findings.

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
Every hard criterion needs an assessed verdict. A supported `pass` satisfies it;
`fail`, `indeterminate` or `not-applicable` requires the owner's explicit
acceptance of that criterion. A missing or `not-assessed` hard criterion still
needs review and cannot be accepted in place of inspection. Advisory criteria
may remain unassessed, indeterminate or failed with their actual reasons.
Every entry in the selected review's `unresolved` list needs resolution through
a new review or explicit owner acceptance. Retain a nonblocking improvement as
a proposed repair without making its execution a condition of selection.

The required `owner_acceptance` field is null when there are no explicitly
accepted review findings. A nonnull value contains:

| Field | Decision it records |
|---|---|
| `principal` | The current authority issuer whose instruction accepts the candidate. |
| `evidence` | The instruction's exact `path`, `sha256` and `locator`. |
| `criteria` | Unique IDs of assessed nonpass criteria the owner accepts. |
| `unresolved_indices` | Unique zero-based indices into this exact review's `unresolved` list. |
| `reason` | Why the instruction covers those findings for this candidate. |

The acceptance names at least one criterion or unresolved entry. Its coverage
must include every nonpass hard criterion and every unresolved entry; it may
also identify assessed nonpass advisory criteria. Read the actual instruction
and preserve its scope. Recording acceptance leaves the criteria, observations,
verdicts and evaluation unchanged. It authorizes use of this candidate under
this review, without changing a requirement for future work or claiming a
successful repair. The exact `select` authorization binds this decision and its
evidence. [Production permissions](production-permissions.md#current-authority-and-adoption)
owns its current-authority checks. The
[synthetic review cases](../../examples/production-execution/evidence-review-cases.md)
show acceptance beside an unchanged failed review.

Choose the selection scope for the result being recorded:

| `scope` | Required destination evidence |
|---|---|
| `delivery-only` | `slot` and `adoption` are null; the artifact is selected for delivery. |
| `studio-slot` | `slot` names the exact `character`, `iteration_id` and `slot`; `adoption` is null. Completion also requires the matching Studio acceptance receipt. |
| `studio-adoption` | `adoption` names the completed sheet or catalog adoption; `slot` is null. |

A new selection of a captured candidate checks current authority against the
retained preparation, review and artifact evidence. Completion verifies that
saved selection, its authorization and required destination evidence. Live
creative sources can move or change without making the retained result
unavailable for this decision. Corrupt or missing retained bytes still block it.
A new preparation or execution keeps its live-source requirements.

#### Accept an existing candidate for its Studio slot

Use the original Production run and candidate when the owner chooses an existing
reviewed image for its slot:

```sh
python scripts/production_workflow.py draft-acceptance --root STUDIO --run RUN --candidate CANDIDATE --grant GRANT --out acceptance.json
python scripts/production_workflow.py accept --root STUDIO --run RUN --file acceptance.json
python scripts/work_ledger.py finish --studio STUDIO --run RUN
```

The compact draft follows the
[acceptance decision schema](../../schemas/authoring/production-acceptance.schema.json)
and pins the run, input, candidate, review and current slot state.
Fill its reason, stop-condition assessments and any `owner_acceptance` from the
actual instruction. In this editing document, the acceptance selects its evidence
path and locator, criterion IDs, unresolved indices and reason. The runtime
derives the principal, evidence hash, selector and exact Studio destination from
the current authority and existing records. It checks the decision before
recording an exact select authorization, selection, Studio acceptance receipt
and run completion. The original candidate bytes, iteration, review and work
task remain the owners; acceptance needs no new generation, import, capture or
criteria definition.

The result identifies the selection, slot-acceptance and completion receipts,
the exact slot and owning task, and a `finish_command` for that run. A separate
`studio-slot` selection made through the granular selection commands uses the
same acceptance and completion path.

After selection commits, resume an interrupted acceptance with:

```sh
python scripts/production_workflow.py accept --root STUDIO --run RUN
```

Recovery uses that saved decision and its evidence. Before a selection has been
recorded, supply the completed decision file. Repeating `accept --run RUN` does
not create another iteration or supersede a different slot decision made since
it was authorized. Inspect a reported conflict before continuing.

Acceptance completes the run, then `finish --run RUN` closes its exact owning
work task after the ordinary checks on actual steps, answered questions and
completion evidence. It can close a suspended owning task while leaving another
active task unchanged. It does not mark steps done or answer questions. Use the
owning task's normal workflow when such work remains.

#### Adopt the selected image as a reusable reference

Choose this procedure while the run is still open when the requested result
includes sheet or catalog reuse. It has its own approval and authorization. The
compact `accept` operation completes slot acceptance; a completed run cannot
append a later canonical adoption.

1. Select the candidate with `scope: delivery-only`.
2. Run `adoption-intent`, then `adopt` under its own `adopt` authorization; the Studio accepts the iteration in this step. `adopt` refuses a candidate that is not the run's current selection (`SELECTION_REQUIRED`).
3. Optionally, select the same candidate with `scope: studio-adoption`, citing the adoption record and retaining any applicable owner acceptance. It needs the run's own adoption result (`ADOPTION_RESULT_MISSING` otherwise).
4. Complete the selected scope.

`adoption-intent` and `adopt` take `--candidate`, `--character`, `--iteration` and `--approval`.
`adopt` also takes `--authorization`, the event digest of its adopt authorization.
A catalog adoption adds `--registration-record`, `--pack-dir` and the same explicit pack runtime arguments as the owner.
An imported iteration belongs to `studio.py accept` for slot acceptance and
`adoption_workflow.py adopt` for sheet or catalog adoption. Production
`adoption-intent` identifies that ownership before creating an adoption claim.

A run has at most one current selection:

- `select` refuses another candidate while one holds it (`SELECTION_CONFLICT`).
- A disposition (`not_selected` or `pending`) of the selected candidate withdraws its selection explicitly; `studio.py reject` records the same disposition.
- Both refuse the withdrawal while the Studio holds that candidate as the slot's accepted image (`SELECTED_CANDIDATE`). Accepting another image for the slot first lifts the refusal.
- A newer review of the selected candidate also ends its selection, without a disposition.

`complete` verifies the current selection and its required destination evidence.
`work_ledger.py finish --studio STUDIO --run RUN` checks the named run's
completion and its owning task's actual steps and questions.
Preparations, generated images, draft reviews or a task with no selected artifact are not finished production.

`review`, `disposition`, `select`, `accept`, `complete` and `adopt` update the Studio gallery; [Studio Runtime](studio.md#every-image-with-what-produced-it) covers a failed rewrite.

## Review, repair and a new run

The same review carries repairs (`id`, decision IDs, observation indices, operation, changed targets, reason).
Identify the responsible layer from the observations before choosing the
operation. [Production direction](production-direction.md#observe-and-repair)
connects the criterion, construction, presentation and rendition. A wrong
temporal phase or spatial relationship can require rebuilding the scene; an
incidental facial or garment edit cannot establish an event the view cannot
show. Use a local correction when the mismatch is local, and retain uncertainty
when the evidence does not isolate a cause.
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
The agent interprets the material into the selected depiction's present
circumstances, visible state, performance and relationships. Supply the
contextual premises that make those instructions intelligible in the actual
model input. Complete authoring material remains available to the author;
its presence in the consumer does not establish what the renderer receives.
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

When a decision needs context, `next_action.read_context` names complete
`workspace` commands in reading order. `input` precedes `decision`; candidate-only
`observe` precedes `review`. Acceptance uses the existing review's context and
findings. These are read views, not additional gates or evidence of understanding.
The views retain full actual inputs and relevant source material while keeping
generated facts out of editing fields. They show applicable Skill paths for a
reader whose active context lacks those instructions. A prior reading record
does not establish that a new reader knows them. Execute returned `argv` as given,
and reuse an existing draft instead of creating parallel copies.

The Production run registry resolves the prior run in the **same task and production series at the saved registration boundary**. It does not open every unrelated historical run merely to find that owner. The selected required predecessor is fully verified; a damaged required series run stops protected-criteria use with `PREDECESSOR_UNAVAILABLE`, rather than silently skipping the comparison.

Sheet batching uses the same commands and statuses. [Sheet fills](sheet-fill-workflow.md) adds dated result ownership, frozen batch inputs and discovery. [Studio Runtime](studio.md) documents gallery and timeline recovery; [Operation diagnostics](operation-logs.md) distinguishes auxiliary views from the formal records required before a send.
