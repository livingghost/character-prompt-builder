# Author the first image input

This complete synthetic example starts a new Studio without a prepared run or
earlier task to copy. It prepares one image request with one supplied reference.
The local model, colored reference, authority and interface evidence exercise
input contracts. They establish no provider behavior or artistic quality.

Run from the Skill's locked environment:

```bash
python examples/input-authoring/build_example.py --out /absolute/path/to/new-example
python examples/input-authoring/build_example.py --check
```

The first command keeps every editable input, captured request and local model
fixture under the new directory. It refuses an existing directory. The second
runs the same no-history preparation in an isolated temporary directory. Neither
command submits the request.

## Inspect the complete files

The checked-in [filled source inventory](filled/source-files.json) contains the
complete editable set from a successful preparation, including
[choices](filled/work/input/choices.json),
[the Production Specification](filled/work/input/production_spec.json),
[authority](filled/authority.json), [the original direction](filled/owner-direction.txt),
[negative provenance](filled/work/input/negative_provenance.json),
[execution policy](filled/synthetic-validation/200927b60fffc782/policy.json) and
[its reference render contract](filled/synthetic-validation/200927b60fffc782/references.json).
These are filled examples for inspection. The generator creates the actual
task IDs, reading record and source context for each new executable Studio.
`--check` also compares the filled sources with a new successful preparation,
apart from the newly issued task, production and reading identifiers.
Maintainers regenerate the example-owned set with `--refresh-filled` after an
authored contract change.

| File under the generated directory | Role |
| --- | --- |
| `studio/work/input/choices.json` | Filled choices, target, source selectors, criteria and reading key |
| `studio/work/input/context.json` | The draft's actual source context; the builder writes it |
| `studio/work/input/prompt.txt` | Exact authored prompt selected by the choices |
| `studio/work/input/production_spec.json` | Complete selected Production Specification |
| `studio/work/input/plot.json` | Authored plot and actual synthetic author's approval |
| `studio/work/input/retrieval_record.json` | Explicitly empty investigation set for this descriptive fixture |
| `studio/work/input/creative_intent.json` | Authored image promise |
| `studio/work/input/negative.txt` | Selected exclusion text |
| `studio/work/input/negative_provenance.json` | Scope and origin of those exclusions |
| `studio/owner-direction.txt` | Original commission, distinct from the rendition |
| `studio/authority.json` and `studio/authority-basis.txt` | Synthetic scope and its basis; no submission grant |
| `studio/reference.png` | The one supplied reference input |
| `studio/synthetic-validation/*/policy.json` | Selected execution policy |
| `studio/synthetic-validation/*/references.json` | Reference render contract and its evidence |
| `input-guide.json` | Actual field and file navigation from `explain-inputs` |
| `report.json` | Prepared run and its exact scoped status command |

The authoring documents have one editable file each. Their choices entries are
`{"file": "work/input/negative_provenance.json"}` and equivalent selectors.
Edit the selected file and run `check --choices` or `prepare --choices`; do not
copy its body into choices or edit the compiled copy. The previous prepared run
keeps its captured bytes.

Generated identifiers, hashes and reading keys describe this particular new
Studio. For another commission, start with its `draft-inputs` result and author
the current choices. Do not copy this fixture's authority or claim that its
reading key delivered knowledge in a new context.

## Discover a field before writing it

```bash
python scripts/production_workflow.py explain-inputs --root STUDIO --choices work/input/choices.json
python scripts/production_workflow.py explain-inputs --root STUDIO --choices work/input/choices.json --field authoring.documents.negative_provenance
python scripts/production_document_contracts.py explain production_spec
python scripts/production_document_contracts.py validate negative_provenance STUDIO/work/input/negative_provenance.json
```

The guide names the exact editable source, schema when one exists, permitted
keys, owning instructions and remaining contextual checks. `artifact_type` is
present only where that document's contract declares it; file extensions do not
decide its fields. The complete state-derived specialist set remains in the
[state-aware pilot](../state-aware-pilot/README.md). Ordinary input authoring does
not need to select those state documents.

## Follow the actual operation

For authored text, use `save --choices`. For an image request, use
`prepare --choices` after recording actual direction, target and evidence.
`check --choices` diagnoses the same authored files without publishing a run.
After preparation, use the returned `status --run RUN` command for that request.
Unqualified `status` inspects the Studio's runs and is a broader operation.

Execution decisions belong to a prepared request and current submission grant.
When submission is authorized, `draft-execution --run RUN --out FILE` generates
the matching decision document. This preparation-only example grants no
submission authority and fabricates no execution decision. The complete
[execution example](../production-execution/README.md) supplies an explicitly
synthetic lifecycle for that separate phase.
