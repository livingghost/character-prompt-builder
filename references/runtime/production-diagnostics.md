# Production diagnostics

Use these exit statuses and diagnostic codes to resolve a reported failure at its owning input. A successful structural check establishes neither artistic success nor permission.

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
| `TASK_ABANDONED` | The run's work task was abandoned, so its production decisions and new execution remain closed. A separately authorized adoption can use its existing selected candidate. |
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
