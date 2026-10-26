# Prompt-only core

Write prompt text or reusable prompt artifacts without calling a generation service. Read specialized construction or transport instructions when the requested deliverable needs them.

## 1. Resolve the request

Identify the requested artifact: plain prompt text, prompt plus negative text, reusable prompt package, or generation-ready package. Prompt-only means no generation API call. It does not automatically require reference transport files.

Extract explicit anchors: subject domain, species or body plan, stable identity, count, role, situation, state, camera, medium, and any user-fixed appearance. Keep unmentioned axes open.

Follow [Production direction](production-direction.md#choose-the-expression) for
the presentation and open expressive choices, then resolve the rendering axes
under [Rendering choices and execution controls](render-contract.md).
Record user selection or the agent's reason. Keep finish, presentation and
subject identity distinct.
When a model is named, read its complete model guidance card before final wording.
When no model is named, keep the prompt portable rather than inventing execution settings.

## 2. Retrieve only what is useful

Use [Discovery](sparse-discovery.md) for an open expressive question, even when
the subject is fully specified. Use focused search for a known construction
need. Inspect selected records. Shared identity, occupation, mood and situation
requirements apply to every direction. Camera, lighting, environment and
rendering may vary only where the user left them open.

Do not let role similarity replace an explicit species. Do not choose a specific subspecies from a broad species request without evidence. Use occupation modules for role and archetypes for identity structure.

## 3. Compose

Write the selected construction as a complete depiction from the brief and
knowledge. Include whole-artifact hierarchy and local views only where needed.
A reference-free
prompt must identify its subjects and their necessary relationships in text.
With references, identify each supplied image and the properties it should carry.
For an edit, describe the requested change and the properties to preserve.

Use the `composition` route when interacting requirements need a detailed scene
specification. An ordinary text draft needs no invented scene-state artifacts.

This is the master prompt. For a named interface, follow its adapter and
[Prompt Writing Guide](prompt-writing-guide.md) after meaning is settled. Use
only evidenced syntax. Portable semantic language is the default rendition.

## 4. References and output

If a selected record has relevant Visual Evidence, inspect and use it without waiting for a reminder. Deliver the evidence artifact when it materially supports a reusable prompt result.

Do not create empty reference artifacts. Include `reference-use-plan.json` only when references are selected. Include `surface-lighting-plan.json` only when lighting or material transfer needs an explicit contract. Include `prepared-reference-set.json` only for a target-specific or generation-ready package.

## 5. Preflight and deliver

Apply the Skill's common readback to the completed rendition before delivery.
When a structured plan is present, run its preflight for declared structure
assignments and numeric camera bounds. Compare those declarations with the
actual prompt; plan validation cannot establish that their meanings agree.
Deliver the prompt, applicable negative, separate execution settings and selected
reference artifacts. The `negative-policy` resource owns negative sources and
target syntax.

## 6. Deterministic commands

Use `python scripts/build_prompt_artifacts.py --help` to materialize the conditional prompt artifact set. The builder accepts an optional structured semantic plan and refuses violations of its explicit counts, connections, action assignments and numeric camera bounds before publication. `python scripts/validate_prompt_semantics.py plan.json` checks the plan alone; its `--template` prints a plan to start from, and its `--help` names every field.

A text draft may omit `--plot`, or include a valid unapproved plot for review. `--prepare-for-generation` requires an approved `--plot`, never invented from an "autonomous" request. A plot separates story beats (`visible` or `context`) from selected frame statements (`shows`, `placement`, `composition`, `must_preserve`, `free`). Beat linkage records the source of a decision, not proof that every inference needs an instruction. `free` identifies open choices for planning; it is not a permission block to paste into a prompt. Validate it with `python scripts/prompt_plot.py plot.json`. An actual approval records `by`, an RFC3339 UTC `at`, and `content_sha256` of the plot without its approval; print that hash using `--content-sha256`. A changed plot requires renewed approval. Optional upstream `source` remains part of the approved content. Choose a target when useful for the draft; target limitations that change approved meaning require renewed approval.

Saved text uses the `prompt-only` production route; a prompt with selected
references uses `reference-artifacts`. Draft delivery grants no generation or
canonical-update authority. A conversation-only answer needs no Studio.

The builder takes the retrieval record with `--retrieval-record lookups.json`. Catalog and vocabulary searches given `--record lookups.json --element NAME` write that record, and a vocabulary search given `--queries` records each query under its own element. Mark each element with `python scripts/prompt_retrieval.py lookups.json --element NAME --adopted ID`, repeating `--adopted` for each record the wording uses, or with `--composed TEXT --reason TEXT` when no inspected record fits. Where retrieval cannot run at all, pass `--retrieval-unavailable` with the reason; the package records `retrieval.settled: false` and `--prepare-for-generation` is refused. For generation, bind the marked record to the authored prompt and approved plot with `python scripts/prompt_retrieval.py lookups.json --settle --prompt-file prompt.txt --plot-file plot.json --out retrieval-settled.json`. Missing, unavailable, unsettled, or mismatched records block preparation.

Regression checks: `python scripts/prompt_artifact_smoke_test.py` and `python scripts/prompt_plot_smoke_test.py`.

## Retrieved wording checks

Check the intended sense of compact terms before adapting them to a tag interface.
For example, `muzzle` may name restraint gear or a snout, and `back` may name a
body region or a camera view. Read them with their subjects and modifiers.
Vocabulary membership supplies wording evidence; it does not choose the meaning.

## Optional structural detail

The plan `validate_prompt_semantics.py --template` prints uses an empty `structure_plan`, not a human limb inventory. Fill it from the actual proposal when topology matters. Read [Declared Structures Runtime](declared-structures.md) for counts, local scope and detailed geometry. A short draft need not acquire irrelevant structural artifacts.


## Artifact evidence and completion

For a saved deliverable, continue through [Production Execution](production-execution.md). A search hit or a newly created image is neither production completion nor canonical adoption.
