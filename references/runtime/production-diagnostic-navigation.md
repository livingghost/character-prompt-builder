# Handle a production diagnostic

Use these exit statuses and diagnostic codes to resolve a reported failure at its owning input. A successful structural check establishes neither artistic success nor permission.

## Exit codes

`production_workflow.py`, the package builder, the verifier, the dispatcher preview, `production_binding.py`, `adoption_workflow.py` and `studio_reference.py` share these exit statuses.
Each diagnostic code selects one; [Diagnostic codes](production-diagnostics.md#diagnostic-codes) lists the codes by family.

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
In particular, `SOURCE_CHANGED` and `STUDIO_REFERENCE_CHANGED` notices about
a prepared run's original sources do not block that saved request. Read the
reported severity and phase; a source changing during new acquisition remains
an input error.
`execute` or `resume` that returns `ok: false` without an error diagnostic exits 4.
A synthetic `execute` without a decision file exits 3 and prints (trimmed):

```json
{"ok": false, "diagnostics": [{"code": "AUTHORIZATION_REQUIRED", "severity": "error", "phase": "authorization",
  "pointer": "$.operations.direction", "message": "No exact authorization covers this prepared operation.",
  "required_action": "Fill the execution decision file from the actual approval or delegation, then execute with --decisions-file.",
  "expected": ["decision:expression", "purpose"], "actual": []}]}
```
## Read the reported failure

Every failure after argument parsing prints a JSON object with `ok: false` and `diagnostics`.
Each diagnostic has `code`, `severity`, `phase`, `file`, `pointer`, `message`, `required_action` and `blocked_checks`. A phase or producing contract with a declared owner also supplies `guidance`; unmapped phases omit it.
When present, `guidance.document_path` identifies that owning document and section. `guidance.schema` names the schema when the check declares one. A document without a published JSON Schema uses `guidance.validator_source` to identify its actual logical validator by script path and function; `production_document_contracts.py explain NAME` exposes its permitted fields and validation command. Specification diagnostics include an optional `guidance.validation` action with executable `argv`, quoted `command` and `reason`. The action runs the same validator on the named specification alone. It is available for a focused correction, and is not an additional prerequisite for `check` or `prepare`.
The compiler reports each structural defect of every declared external specification in one result, including when a separate request binding fails. Only checks that depend on an invalid source wait for its correction. Each specification diagnostic names that source file and its field, rather than the enclosing task file.
Some add `run`, `expected`, `actual` or other details.
The shared diagnostic owner also reports `category` and
`repair_responsibility`. Categories are independent of process exit status:

| Category | Repair responsibility |
| --- | --- |
| `input` | The author corrects the named input or completes its judgment. |
| `authority` | The actual principal or delegated authority resolves the permission scope or stop condition. |
| `state-conflict` | The current work owner inspects changed or competing state and continues its exact result. |
| `environment` | The runtime operator repairs dependencies, credentials, configuration or storage. |
| `provider` | The execution owner inspects the provider outcome and recovers the same submission. |

These categories route a repair; they neither choose another candidate nor
authorize a retry that would send again. The concrete `required_action`,
`file`, `pointer` and any `repair_owner` still identify what must be corrected.
For an existing saved plan, follow its reported `plan_continuation` after
repair instead of creating another plan for the same work.

`edit-choices` preserves the exact received JSON Pointer in a pointer failure.
On Windows Git Bash, shell path conversion can turn `/authoring/...` into a
filesystem path even when the argument is quoted. Disable that conversion for
the command, then pass the actual pointer unchanged:

```sh
MSYS_NO_PATHCONV=1 python scripts/production_workflow.py edit-choices --root STUDIO --choices work/draft/choices.json --pointer /authoring/task/criteria --value-file criteria.json
```

The runtime reports `received_pointer` and the owning choices file. It does
not guess a corrected pointer or change the selected owner automatically.
Successful structured edits return `edit.changes`: the actual JSON Pointer
differences with the previous and resulting values, after normalizing the
effective task choices. These are observations of the edit, not a declaration
of permitted scope. `inspect-inputs` separately compares actual differences
with `work-basis.json.change_scope.retain` and `.change`. The console carries
the values needed to inspect the change; operation logs omit `before` and
`after` payloads and count only the owner and pointer.

For parameter failures, `required_action` states whether to supply, replace or
remove the value, or set the explicit dispatcher choice. `expected` gives the
value schema or the available selections when relevant; `recommendation` holds
a range from which the author must still choose one value. A combined parameter
constraint locates the root (`$`) of a selected parameter file. A
`CHECK_NOT_PERFORMED` entry can name the source of its waiting check; its repair
addresses the failed prerequisite rather than asking for an edit to that source.
Exit 2 applies unless a row says otherwise.

The complete [diagnostic-code catalog](production-diagnostics.md#diagnostic-codes) owns each code and its repair conditions. Open the reported code and its owning `guidance` when resolving that failure. The catalog includes unrelated operations and is not part of every successful preparation or execution.
