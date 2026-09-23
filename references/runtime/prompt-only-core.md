# Prompt-only core

The shortest ordinary path from a user brief to prompt text. Preset maintenance, release operations, full morphology doctrine and model-facing visual transport apply only when a trigger requires them.

## 1. Resolve the request

Identify the requested artifact: plain prompt text, prompt plus negative text, reusable prompt package, or generation-ready package. Prompt-only means no generation API call. It does not automatically require reference transport files.

Extract explicit anchors: subject domain, species or body plan, stable identity, count, role, situation, state, camera, medium, and any user-fixed appearance. Keep unmentioned axes open.

## 2. Retrieve only what is useful

Use catalog recommendation for a sparse brief. Use atomic search for a named axis. Inspect selected records. Shared identity, occupation, mood, and situation requirements apply to every direction. Camera, lighting, environment, and rendering direction may vary only where the user left them open.

Do not let role similarity replace an explicit species. Do not choose a specific subspecies from a broad species request without evidence. Use occupation modules for role and archetypes for identity structure.

## 3. Compose

Write one coherent image intent followed by subject identity and state, pose and body language, camera and framing, environment, representation grammar, material response, light and shadow, and detail hierarchy. Use exact garment and accessory geometry when it affects identity or reproduction.

Keep camera distance, shot scale, frame occupancy, camera height, and pitch mutually consistent. A worms-eye view normally needs a low camera, upward pitch, a near subject, and substantial frame occupancy. A wide establishing shot is a different intent unless explicitly requested.

Assign each limb and hand action once. If a pose contains several actions, identify which hand or limb performs each action. Do not ask one hand to hold two unrelated objects unless the grip is explicitly possible.

Treat this as the master prompt. For a named model or interface, read its adapter in `references/adapters/` and follow [Prompt Writing Guide Runtime](prompt-writing-guide.md) before delivering the final rendition. Resolve the selected `prompt-writing-guide` provider when one exists, and apply only syntax supported by the active interface. When no parser is named or evidenced, keep portable semantic language.

## 4. References and output

If a selected preset has relevant Visual Evidence, inspect and use it without waiting for a reminder. Deliver the evidence artifact when it materially supports a reusable prompt result.

Do not create empty reference artifacts. Include `reference-use-plan.json` only when references are selected. Include `surface-lighting-plan.json` only when lighting or material transfer needs an explicit contract. Include `prepared-reference-set.json` and `reference-preamble.txt` only for a target-specific or generation-ready package.

## 5. Preflight and deliver

Run the structured semantic preflight for body-count and camera contradictions. After target rendition, verify that ordering or weighting did not alter the approved meaning. Then deliver the requested prompt, an optional negative prompt, and only the conditional artifacts justified by the request. A negative carries only the sources the `negative-policy` resource activates, written in the form that resource gives for the target.
## 6. Deterministic commands

Use `python scripts/build_prompt_artifacts.py --help` to materialize the conditional prompt artifact set. The builder accepts an optional structured semantic plan and refuses invalid limb or camera assignments before publication. `python scripts/validate_prompt_semantics.py plan.json` checks the plan alone; its `--template` prints a plan to start from, and its `--help` names every field.

A text draft may omit `--plot`, or include a valid unapproved plot for review. `--prepare-for-generation` requires an approved `--plot`, never invented from an "autonomous" request. A plot separates story beats (`visible` or `context`) from frame statements (`shows`, `placement`, `composition`, `must_preserve`, `free`). Validate it with `python scripts/prompt_plot.py plot.json`. An actual approval records `by`, an RFC3339 UTC `at`, and `content_sha256` of the plot without its approval; print that hash using `--content-sha256`. A changed plot requires renewed approval. Optional upstream `source` remains part of the approved content. Choose a target when useful for the draft; target limitations that change approved meaning require renewed approval.

Draft output has no execution or canonical-update authorization. A saved text file alone does not require Studio initialization. Generation preparation, an explicitly authorized run, and canonical adoption are separate operations.

The builder takes the retrieval record with `--retrieval-record lookups.json`. Catalog and vocabulary searches given `--record lookups.json --element NAME` write that record, and a vocabulary search given `--queries` records each query under its own element. Mark each element with `python scripts/prompt_retrieval.py lookups.json --element NAME --adopted ID`, repeating `--adopted` for each record the wording uses, or with `--composed TEXT --reason TEXT` when no inspected record fits. Where retrieval cannot run at all, pass `--retrieval-unavailable` with the reason; the package records `retrieval.settled: false` and `--prepare-for-generation` is refused. For generation, bind the marked record to the authored prompt and approved plot with `python scripts/prompt_retrieval.py lookups.json --settle --prompt-file prompt.txt --plot-file plot.json --out retrieval-settled.json`. Missing, unavailable, unsettled, or mismatched records block preparation.

Regression checks: `python scripts/prompt_artifact_smoke_test.py` and `python scripts/prompt_plot_smoke_test.py`.

## Retrieved wording checks

Only when retrieval returns no suitable term may the agent compose new wording. Prefer a short proven phrase over a pile of single-word tags, and check the chosen phrase against sibling tags in the same prompt for competition over the same region or attribute (for example a weighted pose tag cancelling a weighted action tag over the same body region). Also re-read each compact tag for a second model-legible sense: a region word can name gear (muzzle as a restraint versus the snout) and a directional body word can name a camera view (back as the rear view versus the body region), and the wrong sense can hijack content or camera.

## Optional structural detail

The plan `validate_prompt_semantics.py --template` prints uses an empty `structure_plan`, not a human limb inventory. Fill it from the actual proposal when topology matters. Read [Declared Structures Runtime](declared-structures.md) for counts, local scope and detailed geometry. A short draft need not acquire irrelevant structural artifacts.


## Artifact evidence and completion

For a saved deliverable, continue through [Production Execution](production-execution.md). A search hit or a newly created image is neither production completion nor canonical adoption.
