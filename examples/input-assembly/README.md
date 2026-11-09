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
| `generation` | Service, count, seed, continuity decisions and other declared generation choices |
| `references` | Ordered reference choices, source authority, uses and transport choice |
| `upscale` | The selected source, model, scale, settings, guidance, rendering and request evidence, or null |

Changing a declared source's body preserves its ID, role and locator while the
builder creates the new file and updates its task reference. The original file
stays intact. Binary source material keeps its existing selector. A source that
is no longer selected is not copied into the new input.

The builder writes repeated file references and measured hashes. It rebuilds
reference attachment positions and board placement from the ordered choice.
The agent still decides intended influence, prohibited transfer, subject scope,
the depiction and its independent criteria. A plot change must carry its actual
approval; unchanged plot content can retain its earlier approval.

`visual` and `validation` stay null when their necessary evidence is already
provided by the selected authored inputs or the ordinary model contract.
An upscale draft retains its existing valid request validation. Choosing new
evidence uses these fields; a new build does not require inventing another
validation record merely because the draft was reopened.

### Validation choices

Each validation choice contains the following seven fields. This synthetic
example selects an observed schema from an active fixture pack:

```json
{"mode": "target-schema", "model": "cpb-synthetic-image",
 "target": {"service": "synthetic", "model_identifier": "synthetic:robot", "operation": "generate"},
 "service_profiles": null,
 "contract": "@pack/019a0290-1234-789a-8123-0123456789ab/resources/model-schemas/example-editor.json",
 "evidence": "@pack/019a0290-1234-789a-8123-0123456789ab/resources/model-schemas/example-editor.json",
 "execution_policy": null}
```

Place this object in `choices.validation`. `contract` and `evidence` are string
selectors; the builder measures their hashes and writes the final `{path, sha256}`
references. A Studio file uses a path relative to `--root`, such as
`"inputs/schema/contract.json"`. An active pack file uses the named selector
`@pack/<pack-id>/<pack-relative-path>`.

Derive the observed-schema selector from the current catalog:

1. Run `python scripts/catalog_cli.py inspect MODEL_ID` with the selected pack runtime.
2. Read the result's `source_pack` and select the exact service offering in `record.offerings`.
3. Join `@pack/`, that `source_pack`, `/`, and the offering's `schema_snapshot`.
4. Use that identical string as both `contract` and `evidence`.

The pack ID is the model record's active owner; its display name or absolute
installation path is not a selector. The runtime resolves only active named
roots and preserves their path boundaries. Keep the same pack runtime arguments
for reading, input construction and generation.

An `observed-parameter-schema` envelope is its own pack evidence. Copying it
into a Studio does not establish pack provenance. For a newly acquired raw
JSON Schema, retain the original response and acquisition record, then select
the resulting `model-schema-contract` and `schema-acquisition` files separately.
The raw schema alone does not provide either evidence contract. Follow
[Model request evidence](../../references/runtime/model-evidence.md#import-a-schema-and-publish-it)
for acquisition and contract construction.

`target` uses the canonical model's exact service, model identifier and wire
operation. A null `service_profiles` selects the active service resource; a
string selects a service-profiles file. `execution_policy` is a string selector
for the authored policy when reference delivery requires one. It may
be null when unused. The policy keeps the same exact target and declares how
reference instructions reach the model.
See [Execution policy for reference delivery](../../references/runtime/model-evidence.md#execution-policy-for-reference-delivery)
for the complete policy and reference render contract shapes and saved public examples.

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
reading, visual and validation choices. The plan follows the ordinary
image-input contract. Drafting an existing external task restores the editable
plan and native request directly:

```json
{"external": {"image_input": {}, "request": {}, "media_slots": [], "reference_delivery": null, "source_files": {}}}
```

This excerpt shows only the container shape, not a complete input. The actual
draft supplies the selected plan, request object or array, and recorded media
slots. Edit independent native controls in `request`; the common delivery
owns prompt text, the model plan owns target identity, and
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
retains the preparation target beside those choices as `target_model`.
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
