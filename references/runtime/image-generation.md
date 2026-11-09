# Image Generation Runtime

Use this document only when the user requests an image-generation call or a model-facing reference transport. Finish art direction, canonical record inspection, visual authority review, and prompt-facing planning before entering this path.

## Contents

- [Activation and dependency preflight](#activation-and-dependency-preflight)
- [Choose execution](#choose-execution)
- [Prompt rendition gate](#prompt-rendition-gate)
- [Model and negative transport](#model-and-negative-transport)
- [Model-facing reference transport](#model-facing-reference-transport)
- [Dispatcher package](#dispatcher-package)

Select exactly one target adapter: [GPT Image](../adapters/gpt-image.md), [Midjourney and Niji](../adapters/midjourney-niji.md), [SDXL and ComfyUI](../adapters/sdxl-comfyui.md), [NovelAI](../adapters/novelai.md), [Grok Imagine](../adapters/grok-imagine.md), [Instruction-Edit](../adapters/instruction-edit.md), or the [Unlisted Image Interface](../adapters/unlisted-interface.md). Do not assume capabilities.

Gemini or Imagen, Firefly, Ideogram, Recraft, Leonardo, and future design-oriented generators use that unlisted-interface rule. Inspect the exact active interface and model record; never infer media or negative transport from a brand family.

## Choose execution

For `execution: dispatcher`, follow [Generation Package](generation-package.md), the prepared-reference contract and the verifier procedures delivered for that execution.
For a host tool, use Production Execution's external branch for the approved generation task. `task.image_input` binds the exact model, supplied media and external request through the [shared image-input plan](../../schemas/authoring/image-input-plan.schema.json). A text-only image request uses `references: []`. An existing-image replacement additionally follows [Semantic instruction editing](semantic-instruction-edit.md) for its source, intended changes and preserved properties. A text-to-image request does not acquire a scene-source or edit plan just because its model is absent from the catalog. The host request must still name the exact requested model, parameters, evidence and available media; a bounded trial requires its declared authority. External binding does not claim a compiled Generation Package or verified model profile.

When accepted characters must share a scene, use [Character Assets and Multi-Character Scenes](character-repose-workflow.md) to decide whether any character asset is missing before preparing the scene request. Assess the exact stage's model against the requested use case and actual reference count through [Render contract](render-contract.md). An explicit model choice remains scoped to the stage the author selected.

## Activation and dependency preflight

Use the same locked environment established at the Skill entry for every operation. Run commands through `uv run --project <skill-root> --locked python <skill-root>/scripts/<script>.py`, preserving the Studio working directory and the command's original arguments. The project supplies the complete Python dependency set from `pyproject.toml` and `uv.lock`.

Choose the reference transport from the selected material and target. It determines the work and verification to perform in that environment:

| Operation | Operation checks |
| --- | --- |
| prompt only, no references | prompt, retrieval and request contracts |
| `prompt-artifacts` with existing SVG or raster sources | source bytes, safety, authority and actual file delivery |
| `svg-bundle` | source bytes, SVG safety and the bundle manifest |
| SVG-to-model PNG transport | bounded rasterization and original-source and transport hashes |
| raster extraction or fidelity recomputation | source decoding, visual derivation and fidelity |
| `single-board` construction | each source assignment, panel region and actual board bytes |
| full product publication | the complete [Release Validation](../release/validation.md) gates |

Check the complete environment at entry. Model-facing preparation rechecks it before SVG rasterization or board composition:

```bash
uv run --project <skill-root> --locked python <skill-root>/scripts/check_dependencies.py
```

The check covers Python packages, native imports, FFmpeg and the sheet fonts. If it fails:

1. Apply the check's installation commands within the existing environment-installation authority and rerun the check. Keep the project environment and interpreter identified by the report. `--install --yes` runs the printed package and FFmpeg commands when that action is authorized; the report identifies any additional system-font requirement.
2. When a required environment change lacks authority, report the exact missing requirement and installation command, then stop.
3. Never omit a selected reference, send raw SVG to a raster-only endpoint, substitute another artifact, downgrade to text-only, or silently change transport.

Do not begin model-facing materialization until the dependency check passes.

## Prompt rendition gate

Use [Production direction](production-direction.md#choose-the-expression) for
the depiction being commissioned and
[Prompt Writing Guide Runtime](prompt-writing-guide.md) for its interface
rendition. Select the exact model record and adapter. When the active pack state
selects a `prompt-writing-guide` provider, resolve and read the complete guide before final rendition.
Apply only the ordering, separators, weights, LoRA or embedding notation,
negative handling, and other rules supported by the exact active interface.

If the parser is unknown, keep portable semantic text instead of guessing Stable Diffusion parentheses, square brackets, LoRA calls, embedding tokens, or platform parameters. Recheck the target rendition against the master prompt so syntax changes emphasis without changing subject identity, count, anatomy, relationships, camera, medium, or state.

When the final rendition is shown to the user for a decision, show it twice: the exact text as it would be sent, which is the only copy that travels, and a literal rendering in the user's language beside it, term by term and field by field, the negative field included. A model-facing text is written in the language the checkpoint was trained on, and a person cannot approve a defect they cannot read; the rendering is a reading aid and is never sent, never a summary, and never shortened where the text repeats. A term with no ordinary equivalent is carried across as it stands, with a line on what it draws.

Generation builders commit the supplied final rendition and the verified media.
Before submission, use
[Production direction's judgment](production-direction.md#observe-and-repair)
to assess the picture those actual inputs request against the commission,
including each subject and reference use. Record that judgment in the existing
`rendition_review` under
[Production permissions](production-permissions.md#authorization-and-execution-records).
Builders preserve the authored language and apply only the selected interface's
declared transport controls.

## Model and negative transport

Enabled `model` records are the dispatcher authority for negative transport and
accepted reference media. Use a canonical model ID, exact label or declared alias.
For ComfyUI, identify the loaded model and its exact workflow contract.

Generation Package dispatch requires an enabled, evidence-backed model offering
and execution profile, including for reference-free requests. Adding that record
updates model resolution, negative transport, reference media and package
construction together. Explicit transport selection operates within this contract.

For a requested model missing from that catalog, distinguish the requested operation before choosing an execution path. For a new image, use the [Unlisted Image Interface](../adapters/unlisted-interface.md) with the normal generation task and exact provider evidence; prepare an authorized external host request, or explicitly register and validate a model offering before dispatcher packaging. For an edit of an existing image, use [Semantic instruction editing](semantic-instruction-edit.md) to pin the source and each reference. Neither path substitutes a nearby model or pretends that a missing offering is executable through the dispatcher. A host-tool result establishes only what was actually sent and returned, not a verified model profile.

The supported negative modes are:

- `separate-field`: send the complete verified negative to an independent field;
- `integrated-critical`: author one coherent rendition carrying the depiction and necessary exclusions, using direct negation or positive construction as meaning requires; supply `--integrated-prompt-file` or certify the reviewed primary prompt with `--critical-avoidance-integrated`;
- `native-subset`: author a concise platform-native subset and package it through `--native-negative-file`;
- `retained-only`: forward the verified integrated rendition while retaining the portable negative for audit when the interface remains uncharacterized.

The builder preserves authored transport text rather than appending a negative list to the positive prompt. `generation_payload.transports` retains three independently hashed records: `separate` holds positive and portable-negative text; `integrated` holds the reviewed single-field rendition; `native_subset` holds positive and platform-native negative text. Unavailable integrated or native renditions have `available: false`, `method: "unavailable"`, empty text and matching hashes. Only the selected transport must be available. A separate or native negative field needs no unused integrated alternative, and a native negative needs no duplicate portable list. The verifier selects the exact committed rendition for the target mode.

Select exclusions for the current image from the applicable policy, explicit requirements and observed or supported risks. A selected style or render profile supplies scoped evidence, not a command to emit all its `negative_terms`. Keep source IDs and activation decisions in negative provenance. Review whether the complete rendition preserves the intended finish and construction; no source-to-sentence mapping establishes that meaning. When medium drift is diagnosed, search the active catalog for a matching correction and inspect the exact resolved record before use. Core runtime logic must not assume that any optional-pack correction ID exists.

## Services and offerings

Three records change at different times, so they are three records.

- A **service record** says how a service is called: the transport module that sends to it, endpoint, authentication shape, request envelope, operations, delivery and polling, error shape, and limits, with one `observed_at` and one `source` for the whole record. It is the `service-profiles` resource of the active pack runtime. `python scripts/service_profile.py <service-id>` prints it; print it beside anything sent, so an ageing record is seen before it fails. Nothing in this repository carries an endpoint of its own.
- A **model record** says how a model behaves: its evidenced `prompt_input` mode, supported forms and vocabulary scope, prompt style, ordering, negative transport, accepted reference media, limits and notes. An unresolved input mode remains unresolved until its target evidence is established. Nothing in it names an endpoint.
- An **offering** inside the model record says how one service exposes that model: `service` (the key it has in the service record), `model_identifier` (its identifier there), `request_keys` (the request key each input occupies: `model` where the request body names the model, `prompt`, `negative prompt` where the target has a negative field, `reference images`, `seed image`, `mask image`, `input image`, on an upscaler that takes one, `guidance prompt`, and for the image size either `width` and `height` or one `size` key), `size_format` with a `size` key (how its text is written, such as `{width}x{height}` or `{ratio_width}:{ratio_height}`), `constraints` (the limits that service enforces, in words), `observed_at`, optionally `schema_snapshot`, `parameter_keys` (the request key each of the record's `recommended_parameters` occupies on this service), and for an upscaler `setting_keys` (the request key each setting the record declares occupies on this service). A record's `recommended_parameters` are the sampling values its author recommends, by service-neutral name (`sampler`, `steps`, `guidance`, `clip_skip`, and the `hires_` values). When a package leaves a *required* control unset, resolution takes the single recommended value the execution profile ties to it. The package then commits exactly what is sent. An *optional* control stays unset, and a two-number range is never filled; [Rendering choices and execution controls](render-contract.md) owns those statuses. Every model record carries `offerings`; an empty array says no service here exposes the model, which is the state of a record used through a first-party interface or a local host.

`schema_snapshot` points at the offering's attributed parameter contract in its selected pack. Its artifact kind identifies an unchanged acquired schema or the pack author's supported scope. The [model evidence workflow](model-evidence.md) defines both kinds, imports acquired schemas, preserves reference sources, and attaches existing trial records. The `schema`, `reference`, and `attach-probe` operations publish a validated new local pack for explicit activation.

Preparation selects the offering the task's `generation.service` names; `scripts/build_generation_payload.py` takes `--service` when the record is exposed on more than one. Each builds the request as the service would see it from the committed prompt, the parameters and the number of selected references. It evaluates that request against the selected parameter schema and refuses the package on any violation, such as:

- a width and height pair the service does not accept;
- a preset given together with explicit dimensions;
- more references than the channel holds;
- a parameter the model does not take.

The package commits the offering as `generation_payload.service`, and the verifier makes the same check from the package. A record with no offering is checked against its own limits only.

The checker evaluates the schema keywords `$ref`, `$defs`, `type`, `const`, `enum`, `required`, `properties`, `additionalProperties`, `propertyNames`, `minProperties`, `maxProperties`, `dependentRequired`, `items`, `contains`, `minItems`, `maxItems`, `uniqueItems`, `minLength`, `maxLength`, `pattern`, `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`, `multipleOf`, `allOf`, `anyOf`, `oneOf`, `not`, and `if`/`then`/`else`.

Supported root-level `x-constraints` also evaluate scalar `area` and `ratio`, plus per-image `fileSize`, `width` and `height` from ordered media metadata. Missing evidence, unsupported operations and nested extensions remain explicitly unmeasured. Other validation keywords appear in the request validation record's `unmeasured` list as `schema-keyword:KEYWORD`, and the service settles them.

Adding a service is one record in `service-profiles`, an offering on every model record it exposes, and the module its `transport` names: `"transport": "runware"` selects `scripts/transport_runware.py`. A transport is written against `scripts/transport_contract.py`, which states what it defines and the network rules it keeps. Adding a model on a service that is already recorded is one offering.

## Model-facing reference transport

Before selecting model carriers, complete the semantic reading and reference-to-prompt synthesis in [Visual Reference Activation and Transport](../visual-reference-activation-and-transport.md). Review each item's intended use and preserve, replace, add, and omit scopes. Express the needed reference directions using the actual delivered image or panel. Transport implements that authority; it does not decide what the SVG means.

Build the canonical plan from record uses. Use `multi-image` when the endpoint accepts several images and preserve every item independently in plan order. Use `single-board` only when the endpoint accepts one image. A board is disposable transport, not a new semantic source; retain each panel's source hash, model-transport hash, semantic role, authority, exclusions, coordinates, and the separate board hash.

Supported raster bytes pass through unchanged when declared by the model record. A selected safe SVG is deterministically rasterized from that same SVG into a supported PNG. Commit renderer ID and release, source hash, dimensions, `max_side`, and output hash. Never substitute a structural, palette, saturation, specular, mask, or faithful artifact for another.

Model-facing execution requires a fully resolved Surface and Lighting Plan. Only a `lighting` plus `faithful-archival-vector` item can resolve `preserve`. `rescope` and `replace` require reviewed target lights and material responses. A nonempty `surface-lighting-plan.unresolved_decisions` list blocks execution.

Build and execute with one pack runtime:

```bash
python scripts/reference_runtime.py plan \
  --record-use <character-record-id>=identity \
  --record-use <scene-record-id>=pose-camera \
  --transport-mode multi-image \
  --target-model MODEL_ID \
  --source-lighting-mode replace \
  --light-source-json '{"light_id":"target-key","direction":"front-left and above","apparent_size":"large","color":"neutral daylight","relative_intensity":"primary","softness":"soft"}' \
  --material-response-json '{"material":"character surfaces","roughness":"target-defined by material","specular_strength":"moderate by material","highlight_shape":"broad on soft surfaces and tight on hard surfaces","wetness":"dry","anisotropy":"none"}' \
  --out reference-use-plan.json \
  --state-file PACK_STATE_JSON \
  --cache-dir CATALOG_CACHE \
  --managed-root MANAGED_PACKS \
  --pack-root ADDITIONAL_PACK_ROOT

python scripts/reference_runtime.py execute \
  --plan reference-use-plan.json \
  --output-dir prepared-reference-package \
  --max-side 1536 \
  --state-file PACK_STATE_JSON \
  --cache-dir CATALOG_CACHE \
  --managed-root MANAGED_PACKS \
  --pack-root ADDITIONAL_PACK_ROOT
```

For state-aware pack evidence, add the finalized `--reference-selection`. Follow [State-Aware Series Runtime](state-aware-series.md); the plan cannot bypass state eligibility. Supplied-file-only selection prepares on the plan-null path; a shared image-input binding also produces a plan-null set scoped by its binding.

The canonical prepared-reference-set commits target and transport mode, optional finalized state selection, non-null plan for activated pack evidence, nested Surface and Lighting hash, structured zero-reference reason, authoritative source identities, exact source and model carriers, derivations, precedence, optional board manifest, and `prepared_reference_set_sha256`. Each character reference retains `subject_uses` with its subject, use and priority. Priority orders references only within that subject and use; it does not expand source authority. Logical uses survive deduplication of the same physical attachment. The set is the only reference object passed into Generation Package construction.

`prompt-artifacts` and `svg-bundle` are prompt-delivery transports, never Generation Package reference transports. A Generation Package may contain only a verified `multi-image` prepared set, a verified `single-board` prepared set, or a reference-free `none` set for the exact target model. Do not embed or carry prompt-delivery files as model inputs, and do not relabel a prompt-facing package as a model-facing transport.

## Dispatcher package

For `execution: dispatcher`, [Generation Package](generation-package.md) owns complete package construction, verification, forwarding and service execution. The operation reader delivers that complete technical contract with the selected dispatcher route. External hosts use [External request inputs](production-external-inputs.md) and [External host execution](production-external-execution.md).

## The model's family

A model record declares its input workflow in `prompt_input`.
`scripts/prompt_dialect.py --model <model-id>` returns that exact declaration,
its evidence and vocabulary-search requirement. Tag-based records name their
owning family in `prompt_dialect`; the report includes its grammar, blocks and
scoped terms. Search the actual tag rendition under
[Vocabulary](prompt-vocabulary.md#select-wording-for-a-tag-based-model), including
models that also accept prose. Compose from the selected input contract and
family evidence without importing another family's controls. Descriptive input
uses its declared forms; unresolved input does not become descriptive merely
because a family field is absent. [Prompt Writing Guide Runtime](prompt-writing-guide.md)
owns the interface rendition.

## Delivery geometry

A checkpoint renders inside the sizes it was trained at. Ask it for a much larger frame and bodies repeat and heads duplicate; ask for a much smaller one and the composition is lost. Reach a larger delivery size with a second pass instead, either the two-stage enlargement the target's adapter describes or an upscale of the accepted image.

`scripts/generation_geometry.py` settles the geometry from the model record rather than from a remembered number:

```bash
python scripts/generation_geometry.py --model <model-id> --list
python scripts/generation_geometry.py --model <model-id> --ratio 2:3
python scripts/generation_geometry.py --model <model-id> --width 832 --height 1216
```

A ratio the record declares in `size_hints` uses the recorded size and label. A hint is not proof of training resolution. An undeclared ratio requires an explicit `--multiple` taken from the applicable model/service contract or an explicitly selected integer-pixel grid. There is no universal eight-pixel assumption. Its pixel budget is the explicit `--pixels` value, or a proposal based on the median declared area; the report distinguishes the two and does not call either a quality guarantee. The size goes on the keys the selected offering records for it and is checked against that offering's parameter contract. An aspect ratio is sent as the ratio requested or declared, not as the sides reduced. An offering that records no size key leaves the size unchecked. Unknown service limits remain unknown.

Output is JSON on stdout: the width, the height, the pixel count, the ratio, where the answer came from, the offering it was checked against with the `size_fields` it put to the schema (null where the offering records no size key), and `refused_by_the_observed_schema`. The exit status is 1 when a size is refused, and the command exits with a message when the model is unknown, the ratio is not written as width and height, or the record declares no size and none was given. `scripts/generation_geometry_smoke_test.py` is its regression test.

An upscale goes the same way, from one image rather than a package. Write its input declaration and prepare the upscale task as [Upscale Adapter](../adapters/upscale.md) shows, then execute the run like a generation. The dispatcher previews the upscale run of the studio's open task and refuses any input that differs from the sealed declaration:

```bash
python scripts/dispatch.py --upscale --model UPSCALER_ID --source SOURCE_IMAGE --scale 2 --settings-file SETTINGS_JSON --render-intent RENDER_INTENT_JSON --request-validation-file VALIDATION_JSON --studio STUDIO --character SUBJECT_ID --slot SLOT_ID
```

Preparation checks the upscale request:

- the factor and the settings against the upscaler record;
- each setting on the request key the offering's `setting_keys` gives it, refusing a declared setting with no key (`CONTROL_NOT_AVAILABLE`);
- a guidance prompt only where the offering records a `guidance prompt` request key, refusing it otherwise;
- the whole request against the selected parameter schema.

After the service answers, `execute` builds an Upscale Package from the source and each returned image in the send's journal. It records the package as an iteration with the request and the answer. A generative or creative upscaler leaves the package's identity audit pending until [Upscale Adapter](../adapters/upscale.md) review passes.

After generation, apply
[Production direction's judgment](production-direction.md#observe-and-repair)
to the image and the commission, using the image intent, Visual State Projection
and reference-scope boundary at their declared authority. A render can follow
the prompt while the prompt's choices fail the commission. Diagnose identity
drift separately from source-state leakage. When continuity matters, save an
Observed Render State. A render is noncanonical until explicitly accepted;
route defects to the correct owner rather than editing stable identity to
compensate for a scene or model failure.

## Prompt recommendation research

See [Model Prompt Recommendation Research](../model-prompt-recommendations.md) for the admission rule and per-record decisions.

## Executable walkthrough

[Workflow Walkthrough](workflow-walkthrough.md) takes one idea to a prepared run and its exact request through a declared synthetic interface. It sends nothing and uses no credential. The state-aware example commands in [Generation Package](generation-package.md#generation-package) name `--plot-file` and `--retrieval-record-file` for a run whose task declares neither; `examples/state-aware-pilot/build_example.py` supplies explicit illustrative lookup data for its generated package.


## Artifact evidence and completion

Complete the operation actually commissioned under [Production workflow](production-workflow.md), preserving this document's interpretation, retrieval, authority and adoption boundaries. An authored plan, prompt or design uses [Authored storage](production-authored-storage.md): save its exact revision and perform delivery or review when requested. Model execution instead prepares its exact input, captures the actual result and binds review and selection to that result. Canonical adoption records its own decision and destination.

`production_workflow.py status`, `impact` and `resume` expose current dependencies, artifact integrity and the next action. Close the owning work task when its requested result is complete. A search hit, saved revision, generated image and adoption each establish their own scope.


## Explicit rendering and controls

Read [Rendering choices and execution controls](render-contract.md) before preparing model-specific input.
The builder requires a resolved intent and an interface execution profile.
The verifier recomputes effective values and rejects changed model guidance.
Preparation rejects wire values that differ from the contract, and the dispatcher preview shows the choice and complete request.
