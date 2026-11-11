# Production diagnostics

Use these exit statuses and diagnostic codes to resolve a reported failure at its owning input. A successful structural check establishes neither artistic success nor permission.

## Exit codes

`production_workflow.py`, the package builder, the verifier, the dispatcher preview, `production_binding.py`, `adoption_workflow.py` and `studio_reference.py` share these exit statuses.
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
| `INPUT_ARGUMENT_INVALID` | The arguments do not match the command. The usage goes to stderr, and the operation log records this code. `logs-cleanup` prints it for an invalid date or selector, and `resume` for `--interval` or `--limit` given without `--watch` or with a value that is not a positive number of seconds. |
| `INPUT_SCHEMA_INVALID` | A JSON input breaks its schema. |
| `INPUT_UNREADABLE` | A declared input or the task cannot be read; adds `file`, `pointer` and `cause`, and `line` for a JSONL line that is not one JSON value. `required_action` gives the repair that fits the cause, as for `EVIDENCE_CAPTURE_FAILED`. An authoring report also gives it, with `field`, for an editable file that the choices select, a declared task source or an authored target file that cannot be read as selected. |
| `INPUT_CONSISTENCY_ERROR` | Inputs contradict each other or a contract they must satisfy. In phase `semantic-edit` it reports a task whose edit plan has no image input, a scene reference whose bytes no applied `accepted-source` of the task holds (`reference`, `reference_sha256` and `accepted_sources`), or review criteria the task does not declare (`criteria`); `required_action` names the task source or the plan field to correct. `draft-inputs` reports it in phase `authoring` for selectors that do not start one draft, such as `--edit-character` without `--edit-slot`, an edit with `--task`, `--from-run`, another route or execution, or an upscale option, an edit slot without a current accepted image, an edit with no open work task and no `--new-task`, and an upscale selector outside `--route upscale`; `required_action` gives the selector to use. |
| `PROMPT_DELIVERY_MISMATCH` | The exact external prompt text differs from its delivery source. Reports both files, the request field, newline counts and whether line endings alone differ. Use `build-inputs` to derive both from the delivery; manual UTF-8 byte writes preserve LF across platforms. |
| `CHECK_NOT_PERFORMED` | A check did not run because a prerequisite did not pass; `blocked_by` names the prerequisites it waits for. When one of them did not run either, `failed_prerequisites` names the failed checks behind it. `required_action` names the failed one to resolve first, by its own diagnostic in the same report; the check runs once that passes. The entry of phase `compilation` names in `blocked_by` the phases of the errors that stop the compilation. |
| `SOURCE_CHANGED` | A source differs from the bytes read or pinned earlier, or a pinned live source can no longer be read. `resume --outcome-file` reports it when the statement's evidence file differs from the digest the statement declares, or changed while it was read. |
| `TASK_CHANGED` | The task names another work task than the open one, or the open work task changed during preparation. In the first case `expected` is the open work task and `actual` the one the task names; `file` and `pointer` locate it when the task is a Studio file. In the second, `expected` is the work task that was open when preparation started and `actual` the one open now; run the same command again. |
| `STUDIO_REFERENCE_CHANGED` | An accepted Studio reference that the run bound is no longer the current accepted artwork of its slot, or can no longer be verified; `cause` gives the difference. Select the current accepted artwork and prepare a new request. `resume` still recovers a run that was sent. |
| `UPLOAD_SOURCE_INVALID` | An `upload_sources` entry of the task is not `{"file", "url"}`, repeats a file, names a file that cannot be read or that matches no prepared carrier, gives a URL that is not https (http only on a loopback address) or that carries credentials, a fragment or whitespace, or gives one carrier two URLs. `pointer` names the entry's `file` or `url`; a carrier mismatch lists `carriers`. |
| `UPLOAD_SOURCE_REQUIRED` | The transport takes uploads by URL, and a prepared media carrier has no `upload_sources` entry; `carriers` lists each one. Select its exact file and URL in `upload_sources`. |
| `PROMPT_SYNTAX_SELECTION_REQUIRED` | The interfaces an authored text can target use different prompt grammars. Select the service or execution mode at `$.authored.target`, then check the text again. |
| `PROMPT_SYNTAX_MISMATCH` | The syntax asserted at `$.authored.target.syntax` differs from the grammar of the selected interface. Select the intended interface controls or correct the assertion. |
| `PROMPT_VOCABULARY_REQUIRED` | A tag target lacks its dictionary search: the vocabulary record does not cover this exact prompt and negative for the selected model, or the enabled packs supply no `prompt-vocabulary` and `prompt-dialects` resources. Search the final wording for the model and settle each authored term, or enable those resources. |
| `TAG_PROMPT_PROBLEM` | The authored or final text breaks the grammar or a declared interface constraint of its target; `prompt_check` holds every finding. Correct the text or the selected weighting grammar. |
| `IMPLEMENTATION_CHANGED` | Pinned files of the installed implementation changed after preparation. A run reports them as one finding: `file`, `expected` and `actual` name the first changed file, and `changed_files` lists every changed file with its pinned and current digest when there are several. A prepared run reports it as a notice in `freshness_notices` and continues; a variant or repeat reports it in `runtime_warnings` and compiles with the current installation. |
| `CONTROL_NOT_AVAILABLE` | A control is undeclared, not applicable or managed by the service; also an upscale scale outside the `supported_scale_factors` its model record lists, or guidance text for an upscaler that accepts none. A record without that list leaves the scale to the offering's execution profile: a factor that the schema of its scale control refuses is reported at `$.scale_factor` of the upscale declaration, and `required_action` names that control of the offering. |
| `MODEL_PROFILE_MISSING` | The selected target has no execution profile, offering, service profile or upscale scale key; or the model selected for an upscale is not an upscaler. |
| `DEPENDENCY_UNAVAILABLE` | Exit 3. A Python dependency a check imports is not installed. |
| `EXECUTION_NOT_APPLICABLE` | The operation needs a prepared model request: `draft-execution` or `execute` of a run without one, or a dispatcher preview with no prepared run behind it. `status --run RUN` gives such a run its next action. |
| `RUN_NOT_REGISTERED` | No formal run has this ID. `status` without `--run` lists the runs of the Studio. |

**Evidence and integrity**

| Code | Reports |
|---|---|
| `EVIDENCE_SNAPSHOT_MISSING` | A saved snapshot that a record depends on is not available. Either the stored file of a source or evidence snapshot is missing, or the record names no snapshot for a file that a later step reads from it: evidence that an authorization or a selection cites, or an input that the task of a `variant` or `repeat` source run declares. Restore a missing file to the bytes matching `expected`. A record that names no snapshot is not corrected in place, and `required_action` names the way on: an authorization that saved no reading of evidence it cites is replaced by a new authorization of the same operation, which saves it; a recorded selection whose authorization saved no reading of its owner instruction, or a studio-adoption selection with no snapshot of a file its saved Studio records name, leaves its run unreadable, and a new run is prepared; a source run that pins no snapshot is not a source of a variant or repeat, and a new run is prepared. |
| `EVIDENCE_SNAPSHOT_CORRUPT` | A saved source snapshot differs from its digest. |
| `EVIDENCE_CAPTURE_FAILED` | A file named as evidence, as a decision file or as another input could not be read as one stable file. `cause` states why: no file at the path, a symbolic link, a directory, private Studio authentication state, a path that the root it is read from refuses, such as one that starts at a root or, on Windows, at a drive (`cause` then gives its form below the root when it lies there), a line of a JSONL file that is not one JSON value (`line` names it), or an operating-system error such as a denied read. `required_action` gives the repair that fits that cause. |
| `EVIDENCE_INCOMPLETE` | JSONL evidence ends with an incomplete record. |
| `INPUT_SNAPSHOT_CORRUPT` | The run envelope or consumer differs from its digest. |
| `ARTIFACT_MISSING` | A published file of the run is missing; restore the bytes matching `expected`. |
| `ARTIFACT_CORRUPT` | A published file differs from its committed contents, an upload receipt belongs to another input, or the journal's copy of a reference or of a deletion request differs from the bytes the run sealed. Restore the bytes matching `expected`; a journal file is restored from the run's copy before `resume`. |
| `ARTIFACT_INCOMPLETE` | The publication manifest is not marked complete. Remove a publication without a registration with `staging-cleanup`. A registered run whose registered manifest bytes are not complete is not corrected in place, and nothing is read from it; prepare a new run. |
| `ARTIFACT_MANIFEST_CORRUPT` | The publication manifest differs from its registered digest, is not a file array, or declares a file twice, at an invalid path or with conflicting contents. A registered manifest is restored to the bytes matching `expected`; a run whose registered manifest bytes are themselves not a valid file array is not corrected in place, and a new run is prepared. A publication without a registration whose manifest is damaged, or differs from the one its preparation wrote, cannot be registered: remove it with `staging-cleanup` and prepare again. The same code reports a running operation whose file set refuses a file that the operation declared, requested or staged; no stored record is damaged, registered runs are unaffected and the command is run again. |
| `PREDECESSOR_UNAVAILABLE` | The prior run of the same work task and production series, which protected criteria are compared with, cannot be read; `run` names it and `cause` gives the failure. Repair that run. Its protected criteria are not skipped. |
| `ARTIFACT_SET_MISMATCH` | The stored tree has missing or unexpected members relative to its producers' declared set; the diagnostic lists both. |
| `EVENT_CHAIN_CORRUPT` | Formal events, or an exported copy of them, do not form one chain, or a recorded event is not a valid transition after the events before it. A recorded event that replay refuses is named by its digest in `event`, its `kind` and its `sequence`; `field` names a field that its rules read and did not find, and `cause` retains the refusing rule's diagnostic. Restore the committed events, since the action inside `cause` addresses whoever attempts that transition. |
| `EVENT_CONFLICT` | Another operation committed first; read the run again with `status --run RUN`. |
| `AUTHORITY_STATE_CORRUPT` | The stored authority is not the last committed event or differs from its digest. |
| `EXECUTION_RECORD_CORRUPT` | An execution transition names an invalid identity or authorization. |

**Pack and runtime drift**

A compilation stops when what it just bound changes before it is published. A prepared run reports the same codes as warnings in `freshness_notices` and continues with its sealed request and fixed runtime. A variant or repeat reports them in `runtime_warnings` and compiles against the current packs.

| Code | Reports |
|---|---|
| `PACK_RUNTIME_REQUIRED` | Exit 3. Pack state is not initialized; run `pack_cli.py ready`. |
| `PACK_NOT_ENABLED` | Exit 3. No active pack satisfies the declared runtime; enable one with `pack_cli.py enable`, or settle the decisions `pack_cli.py ready` prints. |
| `PACK_SELECTION_CHANGED` | The run binds a pack that the current pack state does not select. |
| `PACK_RELEASE_MISMATCH` | The current and pinned pack releases differ. |
| `PACK_CONTENT_MISMATCH` | Captured bytes differ from the pack lock, a pack file changed during capture, or a pack-owned reference artifact differs from the bytes its delivered reference records. |
| `RECORD_NOT_FOUND` | A selected pack root, file or record has vanished, or the acquired packs do not hold a record or file the preparation uses. The diagnostic names the pack, record or resource and its repair. |
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
| `AUTHORIZATION_MISMATCH` | Exit 3. An authorization differs from the prepared operation; names the field and the `intent`. An execution decision file that does not list every prepared operation once, in prepared order, reports it at `$.decisions`. `resume --outcome-file` reports it when the statement's actor is not one of the execution's recorded outcome actors, which `expected` lists. |
| `GRANT_SCOPE_EXCEEDED` | Exit 3. No current grant covers the targets, or the grant names another actor, omits the operation. A target shortfall adds `granted`, `missing` and `coverage`. |
| `GRANT_REVOKED` | Exit 3. The current authority does not contain the grant, or the grant is revoked or expired. |
| `GRANT_NOT_EFFECTIVE` | Exit 3. The grant is not yet effective. |
| `CREDENTIAL_UNAVAILABLE` | Exit 3. The selected credential is missing, unusable or differs from the execution's pinned source. Follow the diagnostic's Studio credential repair action; an explicit binding keeps its own failure instead of choosing another source. |
| `HANDOFF_REQUIRED` | Exit 3. The operation needs a recorded handoff that the run lacks. |
| `HANDOFF_NOT_PERFORMED` | A low-level dispatcher handoff is refused; `execute` records that handoff. |
| `EXECUTION_CLAIM_REQUIRED` | An external step, an effect receipt, a result or an input cleanup names an authorization that owns no execution of the run, or a claim that the run did not commit under that authorization. `execute` commits the execution and its claim before its first step. |
| `TASK_ABANDONED` | The run's work task was abandoned, so its production decisions and new execution remain closed. A separately authorized adoption can use its existing selected candidate. |
| `AUTHORITY_UPDATE_CONFLICT` | An authority import names a stale current event. |
| `AUTHORITY_SOURCE_NOT_IMPORTED` | A warning in the `readiness_diagnostics` of an unsent run: the authority file of the latest import changed after that import, so its edit has no effect yet. Its repair names the exact `authority-import` command; `authority.source_edited` gives the path and both digests. |

**Execution**

| Code | Reports |
|---|---|
| `DISPATCH_ALREADY_CLAIMED` | Exit 4. The run already owns an execution, or this exact step already started. `resume` reports it while the operation that started an upload still runs. `status --run RUN` gives the continuation; a new request needs a newly prepared run. |
| `REMOTE_OUTCOME_UNKNOWN` | Exit 4. An upload or send started without a saved response; nothing is sent again. For an upload, `execute` and `resume` report it with `steps`, the `cause` that ended the exchange when one is known, and a `next_action` that prepares a new run with `repeat`. `evidence` lists the journal files `upload-NNN-indeterminate.json` that keep what each exchange returned, and `cleanup` the deletion of the inputs the execution uploaded before; while that deletion remains, `next_action` is `resume`. |
| `PROVIDER_REJECTION` | Exit 4. The provider refused an upload or the request. |
| `TRANSPORT_RESULT_INVALID` | Exit 4. A transport response does not have the declared shape. |
| `RESPONSE_CORRUPT` | Exit 4. A saved provider response, or journal evidence an earlier result record holds, differs from its recorded bytes. Restore the recorded bytes; nothing is sent again. An answer file that differs from the digest its output's `response-N.json` records adds `file`, `expected`, `actual` and `output_response`; when an event of the run holds those bytes, the repair names their copy under `production/runs/RUN/objects/`. Before any output is indexed again, an output response file that is unreadable, names an answer the journal lacks, disagrees with the digest of that answer, or names another output than the answer holds at its position reports `file` (the response file) and `answer`. Its repair copies back the run's recorded copy of whichever of the two differs from it, or states that no event of the run holds one. |
| `PROVIDER_OUTPUT_CHANGED` | Exit 4. An acquired result file, or its acquisition receipt, differs from the bytes first recorded for that output, or a later capture omits an output that was already captured. Restore the result file from `production/runs/RUN/objects/` under the SHA-256 given as `expected` or listed by the run's `dispatch-results` record; nothing is sent again. A changed acquisition receipt `acquisition-N.json` adds `output_response`, the response file whose digest it keeps; its repair copies back the run's recorded copy of whichever of the two differs from it. |
| `TRANSPORT_IMPLEMENTATION_CHANGED` | Exit 4. The installed transport module differs from the one sealed for the run; `expected` and `actual` give both digests. Continue the run with the installation that prepared it; a request that was sent is not sent again. |
| `SETTLEMENT_CONFLICT` | Exit 4. An external step, or the execution's result, already has a different recorded receipt, or an output arrives after the external result was finalized. The first record is kept. |
| `SETTLEMENT_EVIDENCE_REQUIRED` | Exit 4. No exact external boundary supports the stated outcome. |
| `EXECUTION_STOPPED` | Exit 4. Execution stopped without a more specific diagnostic. |
| `OUTCOME_STATEMENT_NOT_APPLICABLE` | `resume --outcome-file` names a run without a started dispatcher send: an external or authored run, a run with no claimed execution, or an execution that stopped before its send. The statement is refused before it is read. `next_action` and `required_action` give the run's next action from `status`, which is `resume` only where that execution can still continue. |
| `OUTCOME_STATEMENT_CONFLICT` | The provider answer for the send is saved; resume without the statement. |
| `CLEANUP_NOT_READY` | A deletion of an uploaded input was requested before the execution captured its final outputs, recorded that nothing was generated, or recorded a refused upload or an upload of unknown outcome before its send, or without the claim that owns it. `resume` deletes uploaded inputs once the execution reaches that state. |
| `CLEANUP_OWNERSHIP_REQUIRED` | An uploaded input has no single successful upload receipt of this run, or the receipt names another input or another provider identifier than the deletion targets. Only an upload this execution recorded is deleted. When `request-contract.json` of the execution's journal names another media input than its upload receipt, `pointer`, `expected` and `actual` give that media entry, and the repair restores the file from the run's sealed request. |
| `INPUT_CLEANUP_FAILED` | Warning. The deletion of `count` uploaded inputs failed at the provider. A deletion is not sent again, and the saved images stay available for review. |
| `INPUT_CLEANUP_PENDING` | Warning. Uploaded inputs still wait for their deletion or for its lost answer. `resume` continues the cleanup without uploading or generating again. |
| `INPUT_CLEANUP_UNSUPPORTED` | Warning. The transport cannot delete uploaded inputs. Their provider identifiers stay recorded as retained. |

**Recording and projection**

| Code | Reports |
|---|---|
| `RECORDING_CONTRACT_INVALID` | The recording target names no existing Studio character or slot, or breaks a slot condition. |
| `SHEET_SUBJECT_MAPPING_MISSING` | A sheet slot needs an explicit subject mapping. |
| `OUTPUT_COUNT_MISMATCH` | Exit 4, or a capture warning. The returned output count differs from the authorized request. |
| `UPSCALE_OUTPUT_CONTRACT_MISMATCH` | Exit 4, or a capture warning. An upscale output breaks its declared output contract. |
| `STUDIO_PROJECTION_FAILED` | Exit 4, or a warning. Candidates are registered; only their Studio rows are missing. |
| `WORK_PROJECTION_FAILED` | Exit 4, or a warning. The formal run is kept; the work-ledger projection failed. |
| `ACTIVITY_RECORD_PENDING` | Warning, in `projection_warning` and on stderr. The Studio activity event of a committed transition, or a queued event being retried, could not be written. The committed state is kept, and the warning says whether a retry receipt was saved. Run `studio.py sync`, as [Operation diagnostics](operation-logs.md#automatic-operator-timeline) describes. |
| `PROJECTION_REFRESH_PENDING` | Warning, in `projection_warning` and on stderr. A display that a committed transition changes, such as the gallery, the active references or the activity or story timeline, could not be refreshed; `diagnostics` names each one. The committed state is kept. Run `studio.py sync`. |

**Output and publication**

| Code | Reports |
|---|---|
| `OUTPUT_ALREADY_EXISTS` | The destination exists; choose a new `--out`. A publication whose run directory already exists reports the same code; continue with that run, or register it with `recover-publication`. |
| `ARTIFACT_PUBLISH_FAILED` | Exit 4. A complete staging tree could not be published, or `staging-cleanup --apply` could not remove an owned directory. `published: true` means the directory is complete at its destination and only the flush of the directory that holds it failed: use the published directory, and register a run published this way with `recover-publication`. `logs-export` also reports `published: false` when nothing is at `--out`: the directory that holds `--out`, or the export's staging beside it, could not be created or written, or the rename into place was refused. |
| `STAGING_CLEANUP_REFUSED` | Staging is outside the owned studio tree or holds a symbolic link. |

**Review, selection and adoption**

| Code | Reports |
|---|---|
| `REVIEW_INCOMPLETE` | A hard criterion is missing or unassessed, so review is needed before selection. |
| `OWNER_ACCEPTANCE_REQUIRED` | A nonpass hard criterion or unresolved matter lacks the owner's explicit acceptance. |
| `REVIEW_MISMATCH` | A disposition cites a review that is not the candidate's latest; cite the latest review that `candidate-status` reports, or leave `review` null. |
| `SELECTION_CONFLICT` | Another candidate holds the run's current selection. |
| `SELECTION_REQUIRED` | The candidate is not the current selection of its run. |
| `SELECTION_REVIEW_CHANGED` | A newer review of the selected candidate ended its selection. `accept --file` also reports it for a decision whose `review` is no longer the candidate's latest: `expected` is the latest review and `actual` the decision's, and `required_action` gives the `draft-acceptance` command that drafts a decision against the latest review. |
| `SELECTION_WITHDRAWN` | A later disposition of the selected candidate withdrew its selection. Record a new selection decision before accepting or completing the result; a completed or abandoned run stays closed, and a new selection needs a new run. |
| `SELECTION_REPLACED` | A later selection replaced this one. `status` and `candidate-status` report it for a candidate whose selection a later selection of another candidate replaced. `select` refuses a selection file whose `replaces` no longer names the run's latest selection, because another selection was recorded after the file was drafted; draft, authorize and select it again. `accept` reports it when another operation recorded a newer selection while it applied a decision: `accept --run RUN` resumes that selection, and `accept --file` with the same decision file records the decision again as a new selection that replaces it. |
| `SELECTED_CANDIDATE` | The Studio holds the selected candidate as its accepted image. |
| `SLOT_ACCEPTANCE_NOT_APPLICABLE` | The run is not an image with a Studio recording destination; use its ordinary selection scope. |
| `STUDIO_CANDIDATE_REQUIRED` | The exact Production candidate lacks its one recorded iteration; recover that run's recording. |
| `SLOT_ACCEPTANCE_REQUIRED` | The selected slot lacks its matching acceptance receipt or result; resume the same acceptance. |
| `SLOT_ACCEPTANCE_MISMATCH` | The recorded image or destination differs from the exact selected candidate, or the acceptance applies a selection that is no longer the candidate's current one. A changed Studio image file is restored from the candidate bytes the run recorded. When another selection of the candidate was recorded while `accept` applied a decision, `accept --run RUN` resumes that selection, and `accept --run RUN --file FILE` with the same decision file records it again as a new selection that replaces it. An iteration whose line in `iterations.jsonl` no longer names its Production candidate is restored from a copy of the Studio. |
| `SLOT_ACCEPTANCE_CONFLICT` | The slot changed after the inspected or committed decision; inspect the newer acceptance before deciding again. |
| `ACCEPTANCE_AUTHORITY_CHANGED` | The grant, its source authority or its stop conditions changed after the acceptance decision was drafted. `expected` is the basis the decision file records at `$.authority_sha256` and `actual` the current one. Read the changed authority and draft a new decision with `draft-acceptance`. |
| `ADOPTION_OWNER_MISMATCH` | `adoption-intent` or `adopt` names another run and candidate than the Studio iteration records; `expected` and `actual` give both. An imported iteration is accepted with `studio.py accept` or adopted with `adoption_workflow.py adopt`; a Production candidate is adopted under its own run and candidate. |
| `ADOPTION_PACKAGE_REQUIRED` | The iteration records no generation package, which sheet adoption needs. Attach the original package of an imported iteration with `studio.py attach-package`. A Production candidate recovers its package from the evidence its run keeps. |
| `ADOPTION_RESULT_MISSING` | The Studio adoption record names an adoption claim of the iteration whose result the run does not record: that adoption stopped before the run recorded its result, whether or not the Studio finished its own part. `claim` names it, and `required_action` gives its `production_workflow.py adopt` command; repeating it finishes that adoption and records the result, without starting another adoption. Status reports `record-adoption-result` when the Studio part is complete. Completion reports it for the record that a `studio-adoption` selection saved. A selection keeps what it saved, so there `required_action` gives the commands that record a new selection. |
| `ADOPTION_RECORD_CORRUPT` | The Studio adoption record `characters/CHARACTER/adoptions/ITERATION.json` is missing, is not JSON or not a complete adoption record, or disagrees with the run of its Production iteration: it names no adoption claim of the iteration there, differs from the result the run recorded for its claim, or holds an earlier result than the latest one. A record of a claim whose result is not recorded yet belongs to an adoption in progress and agrees. `studio_reference.py`, status, `adoption-intent`, a new or resumed `adopt` and a `studio-adoption` selection report it. `required_action` gives the `production_workflow.py adopt` command of the iteration's latest completed adoption; repeating it writes the record again from that result. Once the run records an adoption result, `adoption-intent` and a new or resumed `adopt` also report a missing record, because a later adoption continues from it. An imported iteration, or one whose run records no completed adoption, has no recorded result and no command that writes the record again. Completion reports it for the record that a `studio-adoption` selection saved, with the commands that record a new selection. The same code reports a record and run result that agree while the iteration's line in `iterations.jsonl` names another slot or image: `expected` gives the approved slot and image and `actual` the recorded ones, and no command rewrites that line. |

**Editable source and target**

| Code | Reports |
|---|---|
| `AUTHORED_CHOICE_REQUIRED` | A choice of the editable choices file is unanswered, or an edit there conflicts with the record that owns it. `draft-inputs`, `inspect-inputs`, `status`, `build-inputs`, `save` and `check` or `prepare` with `--choices` report it. `field` names the choice, `reason` its kind, `message` what is unanswered and `required_action` the value to give and where it comes from; `guidance` names the section that explains it. The reasons are `reading-required`: no completed route reading is selected at `reading.reading_key`, and the entry carries the read command; `target-selection-required`: `target` lacks a model, service, operation, model file or piece of external evidence that the execution needs, or names a kind the task cannot use; `target-evidence-required`: the selected target does not resolve in the active catalog or in its acquired evidence; `selection-required`: a required selection is null, such as the `validation` of a dispatcher upscale, a `visual` field, or the plan, request or upload of an `external` choice; `source-selection-required`: a source selector is missing, such as a `validation` contract or evidence, or `visual.basis`; `selection-evidence-required`: the image-input plan selected at `external.image_input` cannot be opened; `continuity-choice-required`: a production subject has no continuity decision in `visual.subjects`, or a subject of the selected Production Specification has none at `authoring.generation.continuity.SUBJECT`; `authored-choice-required`: the task direction, its criteria, the delivery text, an upscale source, factor or render intent, or the render intent of a generation is empty, a field of `authoring.task.recording` (`slot`, `sheet_panel` or `role`) or a `prompt_expression` of the selected Production Specification's rendering declaration is null, or the edit plan that `task_changes.semantic_edit` selects leaves `edit.target`, `edit.change`, `edit.preserve` or `review_criteria` unanswered or names a criterion the task does not declare; these plan entries name the plan in `file`; `plot-approval-required`: the selected plot has no approval; `current-judgment-required`: an edit conflicts with its owner, such as changed plot content under an earlier approval, an upload URL whose file is no prepared carrier, a changed or edited identity source, or an edited identity owner of a state graph; `provider-upload-required`: an external reference has no recorded upload that matches its current carrier. The last two are found while the inputs are built, so `inspect-inputs` and `status` do not show them. |
| `AUTHORING_DRAFT_UNREGISTERED` | The directory has no registered work-task owner. Inspect saved inputs to locate the actual draft. |
| `AUTHORING_TASK_SELECTION_REQUIRED` | The source run belongs to another or closed task. The returned draft action explicitly selects the open task or supplies `--new-task` with the actual revision goal. |
| `INPUT_PUBLICATION_CHANGED` | An exported task, report or generated input differs from its registered bytes. Edit the owning choices and build a new export directory. |
| `AUTHORING_DRAFT_REGISTRATION_INVALID` | The registration itself cannot establish the source context. Inspect the named registration. |
| `AUTHORING_CONTEXT_MISSING` | A registered draft lacks its source context. The returned action uses trusted registration to reopen it. |
| `AUTHORING_CONTEXT_MISMATCH` | Source context bytes differ from the registered publication. Reopen the registered source in the offered unused directory. |
| `AUTHORING_STATE_UNREADABLE` | `inspect-inputs`, `status` and session entry could not read one part of the open work task's saved authoring state: a saved draft or reading pointer, the decision drafts, the last check, a run of the task or the current authoring context. `file` names that part and `message` the cause. The rest of the state is still reported and the command succeeds. Inspect or restore the named part, then run `inspect-inputs` again. |
| `IDENTITY_SOURCE_CHANGED` | A selected identity source differs from the original draft witness. Inspect the owning source and reassess its current application. |
| `IDENTITY_SOURCE_UNAVAILABLE` | A selected identity source cannot be read. The action names the source inspection needed before reconstruction. |
| `TARGET_GUIDANCE_REQUIRED` | The selected reading does not cover the current target or source editions. Complete the returned reading action and select its issued key. |
| `READING_SOURCES_CHANGED` | The documents, resources or model guidance that a route reading delivered differ from the current ones, or the reading does not cover the operation, execution or features in use; `changes` lists each difference. Read the current complete material and select its issued reading key. A prepared run reports it as a warning in `freshness_notices` and continues. |
| `EXECUTION_PROFILE_REQUIRED` | The selected interface has no parameter execution profile. Acquire its exact controls and author the profile before a dispatcher preparation. |
| `SERVICE_OPERATION_REQUIRED` | The selected service and transport do not expose this model operation. Select a service with an acquired transport for the requested operation. |
| `VALIDATION_EVIDENCE_REQUIRED` | The offering supplies no default schema and current request evidence has not been selected. |
| `VALIDATION_POLICY_REQUIRED` | Reference delivery has no authored execution policy: no request validation is selected, the selected one names no policy, or its policy declares no `reference_instruction_transport`. Also a retained policy that does not cover the selected target, dialect or reference contract. Author or select the policy at the named field. |

Source-context errors retain `code`, `file`, `pointer`, hashes when measured and
`next_action` / `next_actions`. Execute the supplied `argv` to inspect or reopen
the actual registered source. Recovery keeps existing editor files and does not
select a new source, grant permission or certify artistic judgment.

**Identity coverage**

The compiler reports these in the `identity-coverage` phase; [Character identity contract](../character-identity-contract.md#source-to-input-and-review-coverage) owns the declarations. The repair names the field to correct: an applied source's `sources[].identity` (`subject_ids` and `selectors`), or a criterion's `identity_bindings` or `identity_review`, under `authoring.task` of `choices.json` in a draft. Then run `check` or `prepare` again.

**Visual continuity**

The compiler reports problems of the continuity record in the `visual-continuity` phase as `INPUT_CONSISTENCY_ERROR`, with the problems of every subject in one diagnostic and listed in `problems`. [Generation Package](generation-package.md#generation-package) explains the decisions. The repair names the field: `generation.continuity` holds one `recurring`, `one-off` or `undecided` decision per production subject, `recording.subject_map` maps a recurring subject to its Studio character, and that character's current accepted identity image belongs among the prepared references with the identity use; `generation.visual_continuity` can instead name a complete record. Editable choices hold them at `authoring.generation.continuity`, `authoring.task.recording.subject_map` and `visual`, `build-inputs` returns the problem as an `unresolved` entry of the draft and `prepare --choices` as a diagnostic of its report, with the same repair.

| Code | Reports |
|---|---|
| `IDENTITY_CONTRACT_INVALID` | An identity source, binding, selector or carrier declaration of the task is malformed or contradicts another one; the message names the rule. |
| `IDENTITY_SOURCE_MISSING` | An identity binding of a criterion names a source that the task does not declare. |
| `IDENTITY_SELECTOR_MISSING` | A selector of an identity source or of a criterion binding resolves no value in its source. |
| `IDENTITY_TREATMENT_CONFLICT` | Equally specific identity bindings give one source value conflicting scene treatments for one subject. |
| `IDENTITY_COVERAGE_INCOMPLETE` | Identity source coverage or its independent review basis is incomplete; `gaps` lists the uncovered values, missing carriers, subjects without a source and missing whole-subject reviews. `draft-inputs`, `build-inputs` and `check` or `prepare` with `--choices` give one entry for each kind of gap, with the `field` of the choices file that settles it and its repair. |
| `IDENTITY_CARRIER_MISSING` | A claimed carrier is absent from the actual model input: the text surface, the quoted text or its selected occurrence, the reference, or the request field of the reference. |
| `IDENTITY_CARRIER_CHANGED` | The actual text surface differs from the hash supplied for it. |
| `IDENTITY_REFERENCE_SCOPE` | A reference is used for an influence that its declared scope does not permit or explicitly excludes. |
| `IDENTITY_REFERENCE_SUBJECT` | The influence of a reference is assigned to no subject of its binding, or the actual carriers do not cover every subject of an active binding. |
| `IDENTITY_SUBJECT_REQUIRED` | An identity reference has no subject assignment. Select the Production Specification subjects and assign the identity influence of the reference to the intended one. |

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
| `REPEAT_INPUT_MISMATCH` | A repeated preparation did not keep the authored input: the task, a source or a reference differs from what the run pinned. Restore that content, or declare the difference with `variant`. |
| `RETARGET_NOT_APPLICABLE` | The source run or the new input has no exact prepared dispatcher or external image request. |
| `RETARGET_NO_OP` | Neither the target nor the pack runtime changed. |
| `RETARGET_SCOPE_MISMATCH` | The new task changes the work task or the production series. |

**Operation logs**

| Code | Reports |
|---|---|
| `LOG_WRITE_FAILED` | Exit 4. The operation record cannot be saved before an irreversible effect. `logs-cleanup --apply` also reports it when an eligible operation log could not be removed; `file` names what remains, `deleted` lists the operations that the call removed before the failure, and the same command removes the rest once the path is released. |
| `LOG_PATH_UNSAFE` | The diagnostic tree is not an owned regular directory; replace the link or redirected entry with a regular directory. |
| `LOG_EXPORT_PATH_INVALID` | The export directory is outside the Studio or on a linked path, or it overlaps the diagnostic tree; choose a new `--out`. |
