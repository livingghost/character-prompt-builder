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
Exit 2 applies unless a row says otherwise.

The complete [diagnostic-code catalog](production-diagnostics.md#diagnostic-codes) owns each code and its repair conditions. Open the reported code and its owning `guidance` when resolving that failure. The catalog includes unrelated operations and is not part of every successful preparation or execution.
