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

Use the supplied key from the full route read.
`snapshot_id` can be null when the issued record remains valid without the delivery snapshot.
Choose each required document quotation and write its `why` for this task.
The builder resolves the document hashes from the issued record.
`resource_applied` also supplies guide rule pointers, exact rule text, and task-specific reasons.

## Input choices

Visual choices contain `purpose`, `basis`, `subjects`, `production_spec`, and `prepared_reference_set`.
The last two fields select project-relative JSON files.
`basis` contains a source `path` and an authored `locator`.
Each subject declares `continuity`, `character_id`, `studio_character`, and `identity_refs`.
Choose each identity reference by its `slot` and `iteration_id`.
The selected studio character, adoption record, and prepared set determine hashes and reference numbers.

Validation choices contain `mode`, `model`, `target`, `service_profiles`, `contract`, `evidence`, and `execution_policy`.
Select a canonical model ID and an exact target with `service`, `model_identifier`, and `operation`.
A null `service_profiles` uses the active service resource; an explicit path selects a local service file.
`contract` and `evidence` select project files. An unused execution policy can be null.
Use the same pack runtime arguments for reading, input construction, and the generation builder.
Use the runtime model lookup to select a canonical model ID before construction.

The author supplies continuity and acceptance decisions.
`undecided` denotes a deliberately undecided, single-subject exploration.
An unanswered null field remains an unanswered question.
For a non-model text task, explicitly select the following applicability choices:

```json
{
  "visual": {
    "applicability": "not-applicable",
    "reason": "This synthetic task produces only local text."
  },
  "validation": {
    "applicability": "not-applicable",
    "reason": "This synthetic task sends no model request."
  }
}
```

## Inspect the result

`inputs` lists the formal files and their computed hashes.
`derived_from` identifies the source records and selected run.
`assessment_required` names judgments still needed for the current work.
`next_actions` supplies operation arguments and their effects.
`execution_ready` remains false: model requests still need rendering, review, and authorization.

The generated task points to the new reading record.
Pass the visual and validation files to the Generation Package builder.
The helper retains that builder as the owner of final package construction.
