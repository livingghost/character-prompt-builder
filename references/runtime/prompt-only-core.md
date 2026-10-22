# Prompt-only core

The shortest ordinary path from a user brief to prompt text. Record maintenance, release operations, full morphology doctrine and model-facing visual transport apply only when a trigger requires them.

## 1. Resolve the request

Identify the requested artifact: plain prompt text, prompt plus negative text, reusable prompt package, or generation-ready package. Prompt-only means no generation API call. It does not automatically require reference transport files.

Extract explicit anchors: subject domain, species or body plan, stable identity, count, role, situation, state, camera, medium, and any user-fixed appearance. Keep unmentioned axes open.

Choose the rendering axes deliberately under [Rendering choices and execution controls](render-contract.md).
Record user selection or the agent's reason. Keep the finish separate from subject identity and presentation.
When a model is named, read its complete model guidance card before final wording.
When no model is named, keep the prompt portable rather than inventing execution settings.

## 2. Retrieve only what is useful

Use catalog recommendation for a sparse brief. Use atomic search for a named axis. Inspect selected records. Shared identity, occupation, mood, and situation requirements apply to every direction. Camera, lighting, environment, and rendering direction may vary only where the user left them open.

Do not let role similarity replace an explicit species. Do not choose a specific subspecies from a broad species request without evidence. Use occupation modules for role and archetypes for identity structure.

## 3. Compose

Select what the image needs before wording it. Preserve explicit requirements,
add relationships needed to communicate the event, and choose art direction
for a stated visual purpose. Keep incidental deductions out of the prompt.

For an inferred detail, consider an image where that detail differs. If the
image still meets the brief and the selected direction, leave that detail open.
Omit it rather than writing permission to omit, hide or change it. Then check
sufficiency: could all remaining instructions describe a different event? Add
the missing action or relationship, not a complete inventory of the imagined scene.
[Prompt Composition](prompt-composition.md#select-the-depiction) owns this judgment.

Write the intended event and its participants as one depiction. Specify roles,
action targets, gaze, placement or contact where they establish its meaning.
Choose framing to communicate the necessary information. Readable interaction
does not by itself require a close-up or complete views of every participant.

Keep any selected camera distance, scale, height, pitch and occupancy consistent.
Assign task-bearing limb actions to their owners. Use garment, body or accessory
geometry at the specificity needed by the brief and the reference evidence.

This is the master prompt. For a named interface, follow its adapter and
[Prompt Writing Guide](prompt-writing-guide.md) after meaning is settled. Use
only evidenced syntax. Portable semantic language is the default rendition.

## 4. References and output

If a selected record has relevant Visual Evidence, inspect and use it without waiting for a reminder. Deliver the evidence artifact when it materially supports a reusable prompt result.

Do not create empty reference artifacts. Include `reference-use-plan.json` only when references are selected. Include `surface-lighting-plan.json` only when lighting or material transfer needs an explicit contract. Include `prepared-reference-set.json` and `reference-preamble.txt` only for a target-specific or generation-ready package.

## 5. Preflight and deliver

Check the prompt for necessary instructions and sufficient scene meaning. Remove unsupported constraints and planning commentary. Run the structured preflight for declared body-count and camera contradictions; it does not judge meaning. After target rendition, verify that ordering or weighting preserves the approved depiction. Deliver the prompt, any requested or supported negative, and the justified artifacts. The `negative-policy` resource owns negative sources and target syntax.
## 6. Deterministic commands

Use `python scripts/build_prompt_artifacts.py --help` to materialize the conditional prompt artifact set. The builder accepts an optional structured semantic plan and refuses invalid limb or camera assignments before publication. `python scripts/validate_prompt_semantics.py plan.json` checks the plan alone; its `--template` prints a plan to start from, and its `--help` names every field.

A text draft may omit `--plot`, or include a valid unapproved plot for review. `--prepare-for-generation` requires an approved `--plot`, never invented from an "autonomous" request. A plot separates story beats (`visible` or `context`) from selected frame statements (`shows`, `placement`, `composition`, `must_preserve`, `free`). Beat linkage records the source of a decision, not proof that every inference needs an instruction. `free` identifies open choices for planning; it is not a permission block to paste into a prompt. Validate it with `python scripts/prompt_plot.py plot.json`. An actual approval records `by`, an RFC3339 UTC `at`, and `content_sha256` of the plot without its approval; print that hash using `--content-sha256`. A changed plot requires renewed approval. Optional upstream `source` remains part of the approved content. Choose a target when useful for the draft; target limitations that change approved meaning require renewed approval.

Draft output has no execution or canonical-update authorization. A saved text file alone does not require Studio initialization. Generation preparation, an explicitly authorized run, and canonical adoption are separate operations.

The builder takes the retrieval record with `--retrieval-record lookups.json`. Catalog and vocabulary searches given `--record lookups.json --element NAME` write that record, and a vocabulary search given `--queries` records each query under its own element. Mark each element with `python scripts/prompt_retrieval.py lookups.json --element NAME --adopted ID`, repeating `--adopted` for each record the wording uses, or with `--composed TEXT --reason TEXT` when no inspected record fits. Where retrieval cannot run at all, pass `--retrieval-unavailable` with the reason; the package records `retrieval.settled: false` and `--prepare-for-generation` is refused. For generation, bind the marked record to the authored prompt and approved plot with `python scripts/prompt_retrieval.py lookups.json --settle --prompt-file prompt.txt --plot-file plot.json --out retrieval-settled.json`. Missing, unavailable, unsettled, or mismatched records block preparation.

Regression checks: `python scripts/prompt_artifact_smoke_test.py` and `python scripts/prompt_plot_smoke_test.py`.

## Retrieved wording checks

Only when retrieval returns no suitable term may the agent compose new wording. Prefer a short proven phrase over a pile of single-word tags, and check the chosen phrase against sibling tags in the same prompt for competition over the same region or attribute (for example a weighted pose tag cancelling a weighted action tag over the same body region). Also re-read each compact tag for a second model-legible sense: a region word can name gear (muzzle as a restraint versus the snout) and a directional body word can name a camera view (back as the rear view versus the body region), and the wrong sense can hijack content or camera.

## Optional structural detail

The plan `validate_prompt_semantics.py --template` prints uses an empty `structure_plan`, not a human limb inventory. Fill it from the actual proposal when topology matters. Read [Declared Structures Runtime](declared-structures.md) for counts, local scope and detailed geometry. A short draft need not acquire irrelevant structural artifacts.


## Artifact evidence and completion

For a saved deliverable, continue through [Production Execution](production-execution.md). A search hit or a newly created image is neither production completion nor canonical adoption.
