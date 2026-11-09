# Assemble authored input choices

This synthetic example runs the public inspection, drafting, and input-building commands.
It preserves the original task and checks every generated file hash.
The local text task requires neither an image identity nor a model-service contract.
A complete input directory is still distinct from a prepared or authorized production.

Run from the skill directory:

```bash
python examples/input-assembly/build_example.py
python examples/input-assembly/build_example.py --check
```

[The recorded summary](report.json) contains fields from actual command output.
The fixture helper delivers complete sources for this synthetic export.
A real operator reads the applicable complete contract and applies it to the work.

## Run the input helpers

Open a work task in the Studio and read its selected route. New work can start
without a handwritten production task. The following commands leave
preparation, authorization and sending as separate operations:

```bash
python scripts/production_workflow.py draft-inputs --root STUDIO --route prompt-only --artifact text --execution authored --out-dir work/first-draft
python scripts/production_workflow.py save --root STUDIO --choices work/first-draft/choices.json
```

Edit the direct text files and choices between those calls. `save --draft` preserves unfinished work. Use `prepare --choices` for image input. `build-inputs` exports derived files when that separate output is wanted. The open work task supplies the task ID.
Select the route, artifact and execution appropriate to the requested work;
the example above creates authored text. To reopen an existing task instead:

```bash
python scripts/production_workflow.py inspect-inputs --root STUDIO --task task.json
python scripts/production_workflow.py draft-inputs --root STUDIO --task task.json --out-dir work/input-draft
python scripts/production_workflow.py build-inputs --root STUDIO --task task.json --choices work/input-draft/choices.json --out-dir work/inputs
```

Edit `choices.json` before calling `build-inputs`. It contains only authored
choices and their source-selection context. `context.json` supplies the source
task, provenance and unanswered fields for reading; the builder derives its
own current diagnostics. Keep that context beside its choices. A build with
only `--choices` recovers the same starting point from it, including a source
run; it does not reinterpret an existing draft as new unbound work.
Use a new output directory for each construction.
A failed build preserves existing output directories and the authored task.

## Source delivery

Use the `reading_key` issued after the complete route, operation and specialist read. The compiler derives the source-delivery record and binds it into the task; the author supplies no quotations or hashes as proof of understanding. A draft from `--from-run` retains the earlier issued source scope. Its record can serve current work only when the required documents, model, offering and family are covered at the exact editions. A fresh context reads the full applicable knowledge even when that earlier record remains valid. See [Production authoring](../../references/runtime/production-authoring.md#use-the-delivered-knowledge).

## Input choices

`authoring` is the common editable content for initial work and later changes:

| Field | Authored content |
| --- | --- |
| `task` | Direction, criteria, source roles and other applicable task choices |
| `delivery` | Exact text through `{file, field?}` or inline `content`; `translation_notes` only for a translation |
| `documents` | Only selected specialist bodies; editable text can use `{file, field?}` selectors |
| `sources` | Text or JSON source bodies keyed by their declared source ID, with `content` and `format` |
| `generation` | Count, seed, continuity, rendering and other declared generation choices |
| `references` | Ordered reference choices, source authority, uses and transport choice |
| `upscale` | The selected source, scale, settings, guidance and rendering, or null |

Changing a declared source's body preserves its ID, role and locator while the
builder creates the new file and updates its task reference. The original file
stays intact. Binary source material keeps its existing selector. A source that
is no longer selected is not copied into the new input.

The builder writes repeated file references and measured hashes. It rebuilds
reference attachment positions and board placement from the ordered choice.
The agent still decides intended influence, prohibited transfer, subject scope,
the depiction and its independent criteria. A plot change must carry its actual
approval; unchanged plot content can retain its earlier approval.

### Target selection

`choices.target` owns the actual model selection for both new and reopened work.
A catalog selection uses the canonical model ID and selected offering service:

```json
{"kind": "catalog", "model": "cpb-synthetic-image", "service": "synthetic"}
```

An acquired authored model uses `kind: "acquired"`, `model_file` and `service`.
An unregistered external interface uses `kind: "external"` and its exact model
identity, source evidence and prompt-input contract in `model`. Select null for
portable authored text. Compilers derive specification targets, reference model
bindings and provider identifiers from this selection. Keep the prompt, controls,
source scope, criteria and artistic decisions in their existing authored owners.

`target_knowledge` in the draft or build report shows the complete selected model
record, model cards, offering and parameter schema. It supplies no reading key or
artistic approval. Optional `target.assessment` holds explicit `use_cases`, `mode`
and `reference_count` conditions for an assessment of the declared guidance.

### Validation choices

`visual` and `validation` can stay null when the ordinary preparation contract
provides the necessary evidence. When explicit validation is selected, its four
fields contain authored policy and evidence selectors. An upscale draft retains
those selections from its saved request. The result is rebuilt for the selected
target; applicable evidence remains usable and can produce the same result.

For the current offering's observed parameter schema, select:

```json
{"mode": "target-schema", "contract": null, "evidence": null,
 "execution_policy": null}
```

The builder resolves the exact schema from the selected model's active owner
and offering. No repeated model, service, operation or hand-entered hash belongs
in `choices.validation`. An explicitly chosen schema remains expressible:

```json
{"mode": "target-schema",
 "contract": "@pack/019a0290-1234-789a-8123-0123456789ab/resources/model-schemas/example-editor.json",
 "evidence": "@pack/019a0290-1234-789a-8123-0123456789ab/resources/model-schemas/example-editor.json",
 "execution_policy": null}
```

`contract` and `evidence` are string selectors; the builder measures their hashes
and writes the final `{path, sha256}` references. A Studio file is relative to
`--root`, such as `"inputs/schema/contract.json"`. An active pack file uses
`@pack/<pack-id>/<pack-relative-path>`. Its exact owner and offering are visible
through `catalog_cli.py inspect MODEL_ID`: `source_pack` supplies the pack UUID
and `record.offerings` supplies the selected offering's `schema_snapshot`.
The pack's display name and absolute installation path are not selectors. Use
the same selected pack runtime for reading, input construction and generation.

An `observed-parameter-schema` envelope is its own pack evidence. Copying it
into a Studio does not establish pack provenance. For a newly acquired raw
JSON Schema, retain the original response and acquisition record, then select
the resulting `model-schema-contract` and `schema-acquisition` files separately.
The raw schema alone does not provide either evidence contract. Follow
[Model request evidence](../../references/runtime/model-evidence.md#import-a-schema-and-publish-it)
for acquisition and contract construction.

`execution_policy` selects the authored policy when reference delivery requires
one. It may be null when unused. The policy retains its exact service, model
identifier, wire operation, dialect and reference instruction contract. A target
change keeps that policy selection and verifies its applicability; the compiler
reports a mismatch with the source and required action, without relabeling the
old evidence. See [Execution policy for reference delivery](../../references/runtime/model-evidence.md#execution-policy-for-reference-delivery)
for the complete policy and reference render contract shapes and saved examples.

### Visual choices

A visual choice with `purpose`, `basis`, `subjects`, `production_spec`, and `prepared_reference_set` builds a complete continuity record instead.
Each subject declares `continuity`, `character_id`, `studio_character`, and `identity_refs`, and each identity reference names its `slot` and `iteration_id`.
A null required field inside a supplied choice is an unanswered question.

## Inspect the result

`inputs` lists the formal files and their computed hashes.
`derived_from` identifies the source records and selected run.
`assessment_required` names judgments still needed for the current work.
`next_actions` supplies operation arguments and their effects.
`execution_ready` remains false: model requests still need rendering, review, and authorization.

The generated task points to the new reading record and any generated
continuity and request-validation records. There is no path transfer to perform.
The next action prepares this derived task.

## Continue from a saved Run

A saved Run supplies its own task and captured prompt. Select it instead of a
task file; the original task and prompt files need not be copied or reopened:

```bash
python scripts/production_workflow.py draft-inputs --root STUDIO --from-run RUN --out-dir work/send-draft
python scripts/production_workflow.py build-inputs --root STUDIO --choices work/send-draft/choices.json --out-dir work/send-inputs
```

To select another model while retaining the saved authored work:

```bash
python scripts/production_workflow.py draft-inputs --root STUDIO --from-run RUN --model MODEL_ID --service SERVICE_ID --out-dir work/target-draft
python scripts/production_workflow.py retarget --root STUDIO --from RUN --choices work/target-draft/choices.json --reason "The selected target suits the current work." --prepare
```

Between the two calls, apply the selected guidance and settle any reported input
conditions. The changed target is the single selection; the compiler derives its
repeated identifiers and exact request. Reusable prompt content, source scopes,
criteria, decisions and applicable reading or evidence are retained. New target
conditions do not certify that existing controls, grammar or references apply.
`retarget` records the source request as lineage for dispatcher or external image
work. It leaves existing grants at their declared scope and requires the exact
new request to pass its normal execution boundary.

A fresh operator reads the complete applicable instructions. The saved key supplies source-delivery evidence. Change `reading` when the current operation, feature or target needs another completed reading. Use `--task-id` to reopen the source run under another active work task.

Ordinary edits use the restored `authoring` content. `task_changes` is an
explicit overlay for fields intentionally changed for this deliverable,
such as `route`, `features`, `sources`, `criteria`, `direction` or `delivery`.
Unmentioned task fields retain their saved values. The task identity and
existing authority selector remain owned by the source. A changed source still
selected by the task must be resolved explicitly. No grant or authorization is
created by input assembly.

To turn an authored prompt into an external image input, select acquired
model/interface and reference evidence once. A direct existing-plan selector
is also accepted:

```json
{
  "external": {"image_input": "inputs/selected-interface.json"},
  "task_changes": {"route": "generation", "features": ["unlisted-interface"]}
}
```

This is the external/task portion of `choices.json`; retain its authoring,
target, reading, visual and validation choices. The plan follows the ordinary
image-input contract. Drafting an existing external task restores the editable
plan and native request directly:

```json
{"external": {"image_input": {}, "request": {}, "media_slots": [], "reference_delivery": null, "source_files": {}, "source_uploads": []}}
```

This excerpt shows only the container shape, not a complete input. The actual
draft supplies the selected plan, request object or array, and recorded media
slots. Edit independent native controls in `request`; the common delivery
owns prompt text, `choices.target` owns target identity, and
`image_input.external_request.count` owns the expected count. Their repeated
request fields are generated values.

Each reference keeps its file, role, `use_for`, `do_not_transfer`, subject use
and actual `transport.value` with its evidence. Add, remove or reorder rows in
`image_input.references`. For one declared homogeneous media array, a new row
can omit `transport.field`: the builder assigns its position. More than one
possible mapping needs an explicit selection. The draft's `media_slots` records
the original mapping and is not a second reference list to edit. Building
recreates the mapped media fields while preserving independent controls and
text entries in mixed content arrays. No provider field names, upload values
or permission are invented.

For a plan bound to canonical prepared references, the draft instead puts
source selection and authority in `external.reference_delivery.choices` and
derives its preparation target from the catalog selection. An unregistered
external target can select its independent canonical preparation model through
`target.reference_model`; that profile does not replace the actual external identity.
Its `image_input.references` rows contain the matching IDs and actual transport
evidence. Edit the canonical selection once; the builder derives the full
image-input references, attachments and boards from it.

When that changes the carrier bytes, the build publishes the new carrier and
an input report with `request_state: "reference-upload-required"`. It publishes
no executable task or provider request. Use the actual service upload, retain
its response and select the returned value and evidence in `transport`. Set
`transport.uploaded_file` to the file actually uploaded. Build again into a
new output directory; the builder checks that file against its current
carrier. Older upload evidence cannot establish that new bytes were uploaded.

The draft's `source_files` holds the original file pins as derived context.
Select a new evidence path when the evidence changes; the builder measures
its hash. An original pinned path must still match its captured bytes.
Evidence hashes may also be omitted in a directly selected authoring plan.
A supplied hash remains a commitment and must match; it is never silently
refreshed. The resulting ordinary image-input plan
contains the derived hashes, exact request and preserved reference scope.
Tag-based input still needs its actual dictionary-search record and grammar
contract, and its exact materialized text is checked before publication.

The read-only input report shows the full materialized request, selected model,
references, field changes and grammar/schema results. The derived task keeps
its criteria and authority unless a permitted authored task field was explicitly
changed. Inspect that complete input and prepare it. Input construction performs
no handoff, authorization, submission, image review or canonical adoption.
