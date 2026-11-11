# Production preparation

Compile the current authored sources into an exact, inspectable request. Preparation validates only the inputs required by its selected operation and capabilities. It creates no submission, candidate review or canonical adoption.

## Prepare one complete input

Prepare directly from `--choices FILE`, or select a deliberately exported `--task FILE`. The public task contract follows
`schemas/authoring/production-task.schema.json` and uses the open work task's ID.
It declares its route, direction, full source selectors, criteria and execution kind.
Dispatcher generation declares `generation` and its actual output recording scope; a work-task output does not need a placeholder character.
The prompt file named by `delivery.path` is the single authored prompt.
For image work, the agent establishes the selected artifact and present
situation, including the premises the renderer needs to understand its action,
performance and reference use. Compose that complete input from the sources,
then refine details and necessary exclusions under
[Prompt Composition](prompt-composition.md#carry-scene-intent-into-depiction).
Define criteria under [Production direction](production-direction.md#record-the-production-direction)
from the commissioned result and applicable source requirements, including
inherited identity and state. Use the task's artifact scope and declared evidence
medium; keep grading language and wider production or story decisions in their
owning records. A task can use image, text, motion or other supported evidence
as its requirements demand.
The compiler packages the rendition with the selected interface's declared controls.

```text
python scripts/production_workflow.py prepare --root STUDIO --choices work/draft/choices.json
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
`--task` names a file. On `capture` and `receive-external`, `--artifact` also names a file; it does not read standard input. On `draft-inputs`, `--artifact` instead selects the new task's artifact kind, such as `text` or `image`.
Every `--out` names a new file; an existing one gives `OUTPUT_ALREADY_EXISTS`.

`check` returns a compilation report (`schemas/authoring/production-compilation-report.schema.json`) with `run: null`.
Its execution plan also has a null `run`.
It creates no formal run, authorization, execution claim or external request, and never changes pack selection.
`prepare` performs the same compilation, so running `check` first is optional.
It publishes the package, request preview and execution plan (`schemas/authoring/production-execution-plan.schema.json`) as one run.
A complete run that waits for authority is a normal prepared result.
Invalid input remains an unpublished staging attempt.

Each row of `checks` names a `phase`, its `state` (`passed`, `failed` or `not-performed`) and the checks it `requires`.
A check whose prerequisite did not pass gives `CHECK_NOT_PERFORMED`: `blocked_by` names that prerequisite, and `required_action` names the failed check to resolve first by its own diagnostic. None of those states is a pass.
A task schema error blocks only the checks that need the whole task.
Declared document checks such as specification, plot, retrieval, parameters and target still run and report. A missing selected file is an error; an unused optional document is not a missing requirement.
A recording error does not stop model controls, route reading, retrieval or negative-input validation.
Each declared input is read once per compilation. Diagnostics from derived files retain the source map to the editable choice or file. Ordinary descriptive input can use the selected depiction directly; required specialist artifacts, adopted state and tag vocabulary retain their own contracts.
A change after that read is reported at publication as `SOURCE_CHANGED`.
A synthetic `check` of a missing task file exits 2 and reports (trimmed):

```json
{"ok": false, "publishable": false, "run": null, "diagnostics": [
  {"code": "INPUT_UNREADABLE", "phase": "task-read", "file": "missing-task.json", "cause": "missing file: missing-task.json",
   "required_action": "No file exists at this path below the root it is read from. Correct the path where it is given, or put the file there, then run the command again."},
  {"code": "CHECK_NOT_PERFORMED", "phase": "task-read", "blocked_checks": ["task-schema", "task-contract", "sources", "..."],
   "blocked_by": ["task-read"],
   "required_action": "Resolve the error of task-read first, as its own diagnostic in this report directs; every check in blocked_checks runs once it passes. Then run the same command again."}]}
```

Full source and evidence bytes belong to the run.
The run also pins the installed implementation: the files listed in `config/implementation-files.json` (the modules the production commands import, every schema, their data files and the route manifest, written by `scripts/rebuild_metadata.py` from the import closure) and the route reads. The index records the digest of each module it was computed from. Preparation refuses an index whose modules changed since, or whose schema list differs from the schema directory, and names `scripts/rebuild_metadata.py` as the fix.
`package-manifest.toml` is not pinned, so a release bump keeps a prepared run current.
A pinned implementation file or a bound pack file that changes later is reported as a notice, `IMPLEMENTATION_CHANGED` or a pack code: the prepared run keeps its sealed request and fixed runtime and still sends.
The transport module that sends is the exception; `TRANSPORT_IMPLEMENTATION_CHANGED` stops the send.
Live creative sources, persona applicability, accepted Studio references and fixed runtime integrity are checked again before execution, and a change in them stops it.

Publication is an atomic, no-replace directory rename.
Each producer declares the exact files it writes. The manifest persists that complete set with each file's content hash and size.
Before publication, the stage must contain exactly those files and its root lifecycle controls: `manifest.json`, `owner.json`, `failure.json` and the lock file.
Reference companions retain their complete source proof, delivered media, supplementary masks and nested metadata.
For example, a companion's `references/manifest.json` is an immutable input even though the root `manifest.json` describes the whole publication.
An unexpected or missing member gives `ARTIFACT_SET_MISMATCH`; the failed stage keeps its bytes for inspection.

The fixed runtime holds what the compilation used from the selected packs: the bound records, the named resources,
and each pack file it bound or read, with the manifest and release of every pack that supplied one.
A pack-owned reference binds its canonical record, its asset record and the artifact file it delivers.
It also records the pack selection. The rest of those packs is not copied, so an edit to a record or file the run
does not use leaves its fixed runtime, and the run, unchanged.
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
## Unpublished staging and interrupted publication

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
It checks ownership and formal references again in the publication store transaction right before removal. The dry run performs no writer transaction.
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

Image work also follows the complete [Image input](production-image-inputs.md) contract. External requests use [External request inputs](production-external-inputs.md); the operation reader delivers those bodies for the selected execution.
