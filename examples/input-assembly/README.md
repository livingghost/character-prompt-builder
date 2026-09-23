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

Start with an authored production task in a project directory.
The following commands leave preparation, authorization, and sending as separate operations.

```bash
python scripts/production_workflow.py inspect-inputs --root PROJECT --task task.json
python scripts/production_workflow.py draft-inputs --root PROJECT --task task.json --out-dir work/input-draft
python scripts/production_workflow.py build-inputs --root PROJECT --task task.json --choices work/input-draft/choices.json --out-dir work/inputs
```

Edit the `choices` member of the draft before calling `build-inputs`.
Retain the draft envelope; the builder recalculates its `unresolved` entries.
Use a new output directory for each construction.
A failed build preserves existing output directories and the authored task.

## Reading choices

Copy `reading_key`, `applied`, and `resource_applied` from the reading record the route read wrote, after filling its quotations and reasons.
`snapshot_id` can be null when the issued record remains valid without the delivery snapshot.
The builder resolves the document hashes from the issued record.

## Input choices

`visual` and `validation` stay null unless this directory must hold their records.
The Generation Package builder takes continuity as `--continuity SUBJECT=DECISION` and derives request validation from the active pack's observed schema.
An upscale or a bounded-context dispatcher task needs a validation choice, and so does a package with selected references.

Validation choices contain `mode`, `model`, `target`, `service_profiles`, `contract`, `evidence`, and `execution_policy`.
Select a canonical model ID and an exact target with `service`, `model_identifier`, and `operation`.
A null `service_profiles` uses the active service resource; an explicit path selects a local service file.
`contract` and `evidence` select project files. An unused execution policy can be null.
Use the same pack runtime arguments for reading, input construction, and the generation builder.

A visual choice with `purpose`, `basis`, `subjects`, `production_spec`, and `prepared_reference_set` builds a complete continuity record instead.
Each subject declares `continuity`, `character_id`, `studio_character`, and `identity_refs`, and each identity reference names its `slot` and `iteration_id`.
A null field inside a supplied choice is an unanswered question.

## Inspect the result

`inputs` lists the formal files and their computed hashes.
`derived_from` identifies the source records and selected run.
`assessment_required` names judgments still needed for the current work.
`next_actions` supplies operation arguments and their effects.
`execution_ready` remains false: model requests still need rendering, review, and authorization.

The generated task points to the new reading record.
The builder action lists its remaining arguments in `required_args`, `continuity` among them when no visual record was built.
