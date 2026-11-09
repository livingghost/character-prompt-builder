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
| `schema` | The JSON Schema of an accepted value, with the execution profile's allowed values. |
| `required` | Whether the compiled request needs a value. |
| `nullable` | Whether `null` is accepted, which removes that input. |
| `value_form` | `inline` for a JSON value, or `studio-file` for `{"path": "studio-relative-file.json"}`. |
| `document_type` | For a studio file, the document it must hold, such as `prepared-reference-set` or `production-spec`; null for an inline value. |
| `checks` | The compiler checks that run again; they match `phase` in the report's `checks`. |
| `rebuild` | The artifacts built again: `package`, `request` or both. |
| `protected_criteria` | `unchanged` for seed and count, `redefine` for direction and criteria, `recheck` otherwise. |

Every field problem is collected before the variant stops, and no formal run is created.
[Diagnostic codes](production-diagnostics.md#diagnostic-codes) lists the variation codes.
`references: null` removes the selected reference set and reruns the required contracts.
Replacing a named document also updates the task source role that points at it.
A removed dependency stops being a freshness requirement, and unchanged dependencies stay checked.
For URL-import transports, `upload-sources` selects the same `[{"file": "studio-relative-carrier.png", "url": "https://assets.example.org/carrier.png"}]` contract as `task.upload_sources`. Select the actual hosted carrier file; the compiler derives its hash and current media position.

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

`variant` keeps its model and service. `retarget` applies another target to an
exact prepared dispatcher or external image request. Reopen the source run and
select the target in the common editable input. Keep its work task ID and
production series ID, and record why the target changes.

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

Retargeting resolves the currently selected runtime, including explicit `--state-file`, `--cache-dir`, `--managed-root` and `--pack-root` options.
The same target is accepted when the current pack runtime differs from the parent's fixed runtime.
The new run then records `{"field": "runtime", "before": ..., "after": ...}` in `parent.changes`.
Retargeting does not reactivate a disabled pack or restore the parent's provider.
The [generation example](../../examples/generation/README.md#retry-a-reference-request-with-another-target)
includes a reference request retried with another synthetic target, a different
supported operation and current schema evidence, retaining its prompt and identity source.
