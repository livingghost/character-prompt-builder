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
The example uses fixed synthetic reading applications through the fixture helper.
Real operators read the selected sources and write their own quotations and reasons.

## Run the input helpers

Start with an authored production task in a studio.
The following commands leave preparation, authorization, and sending as separate operations.

```bash
python scripts/production_workflow.py inspect-inputs --root STUDIO --task task.json
python scripts/production_workflow.py draft-inputs --root STUDIO --task task.json --out-dir work/input-draft
python scripts/production_workflow.py build-inputs --root STUDIO --task task.json --choices work/input-draft/choices.json --out-dir work/inputs
```

Edit the `choices` member of the draft before calling `build-inputs`.
Retain the draft envelope; the builder recalculates its `unresolved` entries.
Use a new output directory for each construction.
A failed build preserves existing output directories and the authored task.

## Reading choices

Copy `reading_key`, `applied`, and `resource_applied` from the reading record the route read wrote, after listing the documents and guide rules the task applies.
`snapshot_id` can be null when the issued record remains valid without the delivery snapshot.
The builder resolves the document hashes from the issued record.

## Input choices

`visual` and `validation` stay null unless this directory must hold their records.
The Generation Package builder takes continuity as `--continuity SUBJECT=DECISION` and derives request validation from the active pack's observed schema.
An upscale or a package with selected references needs a validation choice.

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

The generated task points to the new reading record.
The builder action lists its remaining arguments in `required_args`, `continuity` among them when no visual record was built.
