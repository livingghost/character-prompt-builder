# Production input variants

Change an existing prepared input through its declared owner. Preserve independent criteria, unchanged evidence and the earlier execution records. Read this contract when selecting a variant, intentional repeat or another target.

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
| `schema` | The JSON Schema of an accepted value, inline or a reference to its owning schema. Model controls carry the execution profile's allowed values. |
| `required` | Whether the compiled request needs a value. |
| `nullable` | Whether `null` is accepted, which removes that input. |
| `value_form` | `inline` for a JSON value, or `studio-file` for `{"path": "studio-relative-file.json"}`. |
| `document_type` | For a studio file, the document it must hold, such as `prepared-reference-set` or `production-spec`; null for an inline value. |
| `checks` | The compiler checks that run again; they match `phase` in the report's `checks`. |
| `rebuild` | The artifacts built again: `package`, `request` or both. |
| `protected_criteria` | `unchanged` for seed and count, `redefine` for direction and criteria, `recheck` otherwise. |

Task-owned fields reference their property in
`schemas/authoring/production-task.schema.json`. Validation resolves that
property within the complete owning schema, including nested references such
as identity bindings in `criteria` and `source-materials`. The variant uses
the current installation's task contract, as its subsequent compilation does.
An earlier run's execution plan remains a record of its preparation; its
exported task-field schemas do not replace that current authoring contract.
Model controls retain the source plan's selected profile constraints.

Every field problem is collected before the variant stops, and no formal run is created.
`CHANGES_TYPE_INVALID` reports the applicable schema in `expected`, with
references relative to `schemas/`, and the nested location of the invalid value.
[Diagnostic codes](production-diagnostics.md#diagnostic-codes) lists the variation codes.
`references: null` removes the selected reference set and reruns the required contracts.
Replacing a named document also updates the task source role that points at it.
A removed dependency has no remaining use in the child. Unchanged inputs come
from the parent's captured revision, including nested source material and
prepared reference bytes. A changed file, deleted original or moved original
does not require restoration before a variant or repeat. An explicit
replacement selects current inputs through that field's owner; it does not
silently draw other retained inputs from edited originals.
For URL-import transports, `upload-sources` selects the same `[{"file": "studio-relative-carrier.png", "url": "https://assets.example.org/carrier.png"}]` contract as `task.upload_sources`. Select the actual hosted carrier file; the compiler derives its hash and current media position.

A prompt edit is checked again against retrieval and render intent.
Supply an explicitly reassessed `retrieval-record` when the original record does not apply to the new wording.
The runtime invents no lookup or approval evidence.
Unchanged evidence stays reusable. New reference selection still checks current
source eligibility, and current pack choices apply to the new compilation.
A variant or repeat compiles against the current installation and packs and fixes its own runtime from what it used.
It keeps the model and service of its parent; `retarget` selects another.
Where the installation or the packs differ from what the parent pinned, the result lists each difference in `runtime_warnings` as a warning.
Compare the new request with the parent's before approving it.
A pack that no longer holds the model or the service stops the compilation, as it stops any preparation.

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
It compares the authored input, the task with its sources and references, before registration and publishes nothing on a mismatch.
The installation and the packs are not part of that comparison; each run pins its own.
It never borrows its parent's exact execution decisions; `resume` instead recovers the parent's execution.
Neither variants nor repeats change a candidate's disposition, select a result or adopt identity.
The [complete synthetic example](../../examples/generation/README.md) shows preparation, variants and repeats.
## Change the target explicitly

After reopening choices, `next_actions` selects `retarget` when the target differs
from the source run's exact request in the same production series, including an
explicitly reopened work task.
Fill its reason with the actual reason for the change. The status view reads the
current editable target again, so reverting that selection restores the ordinary
prepare action. It never invents a change reason or discards unchanged criteria.

`variant` keeps its model and service. `retarget` applies another target to an
exact prepared dispatcher or external image request. Reopen the source run and
select the target in the common editable input. Keep its production series ID,
use its work task or an explicitly reopened task, and record why the target changes.

```text
python scripts/production_workflow.py draft-inputs --root STUDIO --from-run RUN --model MODEL_ID --service SERVICE_ID --out-dir work/retarget
python scripts/production_workflow.py retarget --root STUDIO --from RUN --choices work/retarget/choices.json --reason "Use the selected target for this expression." --prepare
```

Between the calls, read the applicable complete guidance and settle the reported
conditions in their authored owners. `choices.target` owns the actual selection;
the compiler derives target declarations in specifications, references and
requests. The same `retarget` command can select `--task TASK_FILE` for an explicit
complete task instead of `--choices`. It uses the same compiler and contracts.

`choices.validation` selects the validation mode, contract, evidence and
execution policy. For `target-schema`, leave `contract` and `evidence` as `null`
to use the selected offering's attributed schema. The compiler derives the
target, content hashes and `unmeasured` limits from those current inputs.
Select a different explicit policy or acquired evidence only when its actual
scope applies to the new target. An inherited selector keeps its original scope;
there is no need to hand-author or patch a generated request-validation record.

For a reference request, preserve the reference's original source and intended
influence while choosing an operation that the selected target actually
supports. Edit `execution_mode` at its existing `render_intent` owner if that
operation changes, and reassess the selected policy and controls. The compiler
does not rename a mode or invent reference semantics from similar model names.
Rendering can remain with the model through an operation-only render intent;
an explicit authored rendering declaration remains selected when applicable.

Without `--prepare`, compilation returns a preview without a formal run. With
it, the new run records its parent input and request. External target identity
includes the evidenced wire operation as well as model and service.
Unchanged authored source files remain usable without another copy. The prompt,
source scopes, criteria, decisions and applicable reading or evidence stay
selected. Target guidance, execution controls, retrieval applicability, grammar
and reference transport are checked against the current input; the builder does
not rewrite an artistic choice or a source's declared applicability to make it
pass. An execution policy remains tied to the target and dialect it actually
covers. Current schema and request-validation results are derived again and may
match the earlier result when their inputs still match.

The new run receives no prior submission claim or exact-request authorization.
Existing grants retain their scope and can authorize the normal new execution
boundary when applicable. Prior image reviews remain observations of the images
they assessed, and remain available as source evidence for later judgment.

## Revise the editable source across production steps

The common choices file supports broader revisions than the bounded field map.
Reopen the exact source run with `draft-inputs --from-run RUN`, edit the selected
content, and follow `inspect-inputs` for that draft. Same-target `prepare`
records the source run as its parent. A target change supplies the explicit
`retarget` action and authored reason. A saved image is not required to compare
several prompts or models. Keep each intended branch in a separate directory;
`inspect-inputs --choices PATH` selects one when several are pending. Preparing
these branches creates independent immutable inputs without a paid fan-out.

Add or remove reference images at `authoring.references`, keeping each retained
image's intended use, exclusions and subject scope. The owner derives the
current attachment order, boards, transport files and hashes. Removing all
reference selection with `authoring.references: null` also removes its derived
image-input binding. Choose a supported operation at the rendering-intent owner
when moving between requests with and without images. Existing source-based
identity obligations and continuity choices still need their actual carriers;
removing an image does not erase a criterion or approve another identity source.
The compiler reports these unresolved meanings at their owning choices. An
unused carrier or URL ceases to be a live requirement when its reference is
removed. Original prepared requests and their media remain available for review.

An accepted or completed result can be the source of later authorized work.
Use `draft-inputs --from-run RUN --new-task GOAL --out-dir DIRECTORY` after the
earlier work task has closed, or `--task-id ACTIVE_TASK_ID` to bind it explicitly
to current work. The new task reuses content and records its source without
altering the earlier completion. An existing open task must be continued,
suspended or finished before opening another; the command does not replace it.
Current task authority and request-specific judgments are evaluated for the
new work. A registered reopened draft can retarget across that explicit task
binding while retaining its production series.

For a selected generated image, the ordinary upscale entry takes
`--route upscale --source-run RUN --source-candidate CANDIDATE --scale N
--purpose TEXT`, with its selected upscale model and service. It verifies the
retained result and records that candidate as its source. The new upscale
request has its own criteria and review; generation wording is not copied into
a promptless upscaler. After capture, review and accept the enlarged candidate
through the same result operations as other images. Reworking that enlarged
result follows these same reopening rules. See [Production authoring](production-authoring.md#keep-branches-and-reopen-completed-work)
for the complete input and continuation contract.

Retargeting resolves the currently selected runtime, including explicit `--state-file`, `--cache-dir`, `--managed-root` and `--pack-root` options.
The same target is accepted when the current pack runtime differs from the parent's fixed runtime.
The new run then records `{"field": "runtime", "before": ..., "after": ...}` in `parent.changes`.
Retargeting does not reactivate a disabled pack or restore the parent's provider.
The [generation example](../../examples/generation/README.md#retry-a-reference-request-with-another-target)
includes a reference request retried with another synthetic target, a different
supported operation and current schema evidence, retaining its prompt and identity source.
