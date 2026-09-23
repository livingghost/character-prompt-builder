# Craft consultation

Use the `craft-consultation` route feature to include these rules in the selected route reading.

## Explore within the current task

Use `production_workflow.py consult-presets --help` when a craft question arises during direction, composition, comparison, or repair.
The agent chooses the question, fitting knowledge, scope, and application.
Existing approvals establish the status of those assets; execution and identity adoption use their own authority.

`inspect-inputs` exposes `craft_lookup` and the concrete consultation operation for the task.
Its image and video paths also show the active catalog scope.
`catalog_cli.py consult` provides the same layered search without a production task.

The consultation reports discovered packs, enabled packs, searchable counts, selected providers, and resolution diagnostics.
Confirm the intended library is active before interpreting results.
Use the pack manager to change activation explicitly.
File presence and an empty result describe different conditions.

Select a focus for each question:

| Focus | Knowledge layers |
|---|---|
| scene | Scenes and recipes in separate groups |
| detail | Modules for a local craft question |
| finish | Style families, profiles, aesthetic cores, and domain realizations |
| repair | Corrections for an observed problem |
| identity | Archetypes within the declared subject requirements |
| all | All of these layers, kept separate |

Use `--questions` for several explicit questions in one catalog request.
Each item carries `request_id`, `canonical_query`, and `focus`.
Existing search options include `domain`, `anchors`, `categories`, `limit`, and `tier`.
Translate questions semantically while preserving their anchors and modifier relationships.
Refine an empty query or inspect another layer while keeping those relationships.
Search rank supplies candidates, not a quality or acceptance verdict.

## Read and choose

Use `--inspect` with explicit record IDs to open their complete records and linked asset information.
Recipes also open their declared scene and rendering profile.
Style families open their declared rendering profile.
Opened dependencies remain distinct from selected applications.

`--previous` carries the earlier questions and inspected choices into another consultation on the same catalog snapshot.
Both queries and inspections use the selected pack runtime.
Pass the same state, cache, managed root, and additional pack roots to subsequent operations.
A changed catalog requires a current consultation; the earlier evidence remains a record of its own scope.

The workflow writes `consultation.json` and an unanswered `decisions.json` into a new project directory.
Returned actions name the report, decision file, runtime, and remaining arguments.
The public [consultation example](../../examples/craft-consultation/README.md) runs these commands and shows their actual output summary.

## Apply the chosen relationships

Write the intended production fields before calling `apply-presets`.
Supply the consultation, authored decisions, current production specification, task, and a new output directory.
The decision has `source_id`, `reason`, `uses`, and `not_used`.
Each use names:

- the inspected `record_id` and the craft relationship `borrowed`;
- what is `preserved`, what is `changed`, and the existing specification `targets` as JSON Pointers;
- existing `review_criteria` IDs and an authored `review_question`.

An unused inspected record carries its ID and reason.
Use no preset when none fits; application records are useful evidence, not a new mandatory gate.
For an unchanged technique, describe its retained scope rather than inventing a modification.

The tool resolves record hashes, target values, and selected IDs from these choices.
It snapshots the full consulted knowledge and appends a `preset-application` source to a copied task.
The copied specification retains all authored fields and existing selected IDs, then adds the newly used IDs.
Existing task sources retain earlier applications and judgments.
Nonuse of a previously selected ID requires an explicit revision of that earlier choice.

`apply-presets` publishes the copied task, copied specification, application source, and input snapshots together.
An existing output directory, stale source, missing selection, or unknown target/criterion returns an error before publication.
Change the authored decisions or sources and rebuild in a new directory.

The returned task continues through the existing input builders, preparation, preview, and scoped authorization.
The command keeps the original task, authority, and specification unchanged.
Its output is authoring evidence, not a generated candidate or an adopted identity.

The existing retrieval record identifies prompt-wording provenance.
The application source identifies craft adaptation, including combinations of several records.
Use the existing retrieval gate for final wording and inspect actual assets before transferring their visual authority.

## Review and return to the library

Preparation captures the application as an ordinary production source.
`draft-review` copies its authored questions into the matching criterion reasons with `not-assessed` verdicts and empty observations.
Replace those prompts with judgments supported by the actual candidate and cited observations.

Review the borrowed relationship, preserved constraints, deliberate changes, and any unrelated subject or setting carried into the output.
Distinguish successful lookup, intended application, and observed effect.
An approved pattern in one scope is a useful starting point, not proof of success in every new context.

`repair-analysis` offers the repair-focused consultation operation after grouping recorded failures.
`draft-variation` offers consultation alongside the next input work.
The agent translates the observation into a craft question before choosing a correction.

When a technique works, attach the actual result and scope through the existing review and owning-pack maintenance workflow.
Refine an existing record where it represents the same knowledge.
Evaluate useful application and avoided repetition, rather than search counts, adoption counts, or a new preset for every image.

## Verification

`scripts/craft_consultation_smoke_test.py` exercises scope, full records, dependency inspection, source binding, nonuse, publication failures, and review transfer.
The public example executes the actual CLI with synthetic local inputs.
These checks measure the operation; candidate quality and author acceptance require their own evidence.
