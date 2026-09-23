# Image Generation Runtime

Use this document only when the user requests an image-generation call or a model-facing reference transport. Finish art direction, canonical record inspection, visual authority review, and prompt-facing planning before entering this path.

## Contents

- [Activation and dependency preflight](#activation-and-dependency-preflight)
- [Prompt rendition gate](#prompt-rendition-gate)
- [Model and negative transport](#model-and-negative-transport)
- [Model-facing reference transport](#model-facing-reference-transport)
- [Generation Package](#generation-package)
- [Verification and host forwarding](#verification-and-host-forwarding)
- [Failure policy](#failure-policy)
- [Concurrent batch dispatch](#concurrent-batch-dispatch)

Select exactly one target adapter: [GPT Image](../adapters/gpt-image.md), [Midjourney and Niji](../adapters/midjourney-niji.md), [FLUX](../adapters/flux.md), [SDXL and ComfyUI](../adapters/sdxl-comfyui.md), [NovelAI](../adapters/novelai.md), [Grok Imagine](../adapters/grok-imagine.md), [Instruction-Edit](../adapters/instruction-edit.md), or the [Unlisted Image Interface](../adapters/unlisted-interface.md). Do not assume capabilities.

Gemini or Imagen, Firefly, Ideogram, Recraft, Leonardo, and future design-oriented generators use that unlisted-interface rule. Inspect the exact active interface and model record; never infer media or negative transport from a brand family.

## Activation and dependency preflight

Choose the reference transport before installing anything:

| Operation | Profile |
| --- | --- |
| prompt only, no references | Core |
| `prompt-artifacts` with existing SVG or raster sources | Core |
| `svg-bundle` | Core |
| SVG-to-model PNG transport | Visual |
| raster extraction or fidelity recomputation | Visual |
| `single-board` construction | Visual |
| full product publication | Tested |

For `multi-image` or `single-board`, determine whether any selected source needs SVG rasterization, then run the check before plan execution:

```bash
python scripts/check_dependencies.py --profile visual
```

If the check fails:

1. When the user's task authorizes environment mutation and dependency installation is within scope, run the `install_command` the check printed, then rerun the Visual check.
2. When environment mutation is not authorized, report the exact missing package and installation command, then stop.
3. Never omit a selected reference, send raw SVG to a raster-only endpoint, substitute another artifact, downgrade to text-only, or silently change transport.

Do not begin model-facing materialization until the required profile passes.

## Prompt rendition gate

Finish and review one master prompt before applying target syntax. Select the exact model record and adapter, then follow [Prompt Writing Guide Runtime](prompt-writing-guide.md). When the active pack state selects a `prompt-writing-guide` provider, resolve and read the complete guide before final rendition. Apply only the ordering, separators, weights, LoRA or embedding notation, negative handling, and other rules supported by the exact active interface.

If the parser is unknown, keep portable semantic text instead of guessing Stable Diffusion parentheses, square brackets, LoRA calls, embedding tokens, or platform parameters. Recheck the target rendition against the master prompt so syntax changes emphasis without changing subject identity, count, anatomy, relationships, camera, medium, or state.

When the final rendition is shown to the user for a decision, show it twice: the exact text as it would be sent, which is the only copy that travels, and a literal rendering in the user's language beside it, term by term and field by field, the negative field included. A model-facing text is written in the language the checkpoint was trained on, and a person cannot approve a defect they cannot read; the rendering is a reading aid and is never sent, never a summary, and never shortened where the text repeats. A term with no ordinary equivalent is carried across as it stands, with a line on what it draws.

Generation builders commit the supplied final rendition. They do not choose vocabulary, add attention weights, translate prose into tags, or repair unsupported syntax.

## Model and negative transport

Enabled `model` records are the authority for automatic negative transport and accepted reference media. Use a canonical model ID, exact label, or declared alias. Unknown interfaces require an evidence-backed model record or explicit `--negative-transport`; there is no undeclared media override. ComfyUI is a workflow host, so use the loaded model's record or an explicit workflow-level decision.

The model-record catalog is the single extensibility boundary. Adding a valid `model` record to an enabled pack must change automatic model resolution, negative-transport selection, accepted reference media, reference preparation, and Generation Package construction immediately; no second hard-coded model-name, alias, capability, media, or transport table may shadow it. A reference-free call may use an explicit `--negative-transport` decision, but an unknown model never receives assumed automatic transport or assumed reference-media support. Preparing or packaging image references for that model requires an enabled, evidence-backed model record.

The supported negative modes are:

- `separate-field`: send the complete verified negative to an independent field;
- `integrated-critical`: author affirmative construction constraints in the positive prompt, retain the full portable negative for traceability, and supply `--integrated-prompt-file` or certify the reviewed primary prompt with `--critical-avoidance-integrated`;
- `native-subset`: author a concise platform-native subset and package it through `--native-negative-file`;
- `retained-only`: forward the verified integrated rendition while retaining the portable negative for audit when the interface remains uncharacterized.

The builder never appends literal negative text to the positive prompt. Every Generation Package commits all three renditions independently under `generation_payload.transports` rather than deriving one during forwarding: `generation_payload.transports.separate` commits its positive and portable-negative text with `prompt_sha256` and `negative_sha256`; `generation_payload.transports.integrated` commits the reviewed affirmative integrated text with `sha256`; and `generation_payload.transports.native_subset` commits its positive and concise native-negative text with `prompt_sha256` and `negative_sha256`. The verifier recomputes those hashes and selects the exact committed rendition for the target mode.

On an `integrated-critical` interface, the selected family's and rendering profile's `negative_terms` form the medium's anti-drift boundary, but the interface never receives those terms as negative text. Restate each activated finish or construction requirement affirmatively inside the positive prompt, adjacent to the surface or structure it governs. In negative provenance, map every activated source record ID to its nonempty positive wording under `affirmative_translations`; verification must prove that every translation survived into the committed integrated rendition. When medium drift is diagnosed, search the active catalog for a matching correction and inspect the exact resolved record before use. Core runtime logic must not assume that any optional-pack correction ID exists. Never paste diagnostic or negative vocabulary into the positive prompt.

## Services and offerings

Three records change at different times, so they are three records.

- A **service record** says how a service is called: endpoint, authentication shape, request envelope, operations, delivery and polling, error shape, and limits, with one `observed_at` and one `source` for the whole record. It is the `service-profiles` resource of the active pack runtime. `python scripts/service_profile.py <service-id>` prints it; print it beside anything sent, so an ageing record is seen before it fails. Nothing in this repository carries an endpoint of its own.
- A **model record** says how a model behaves: prompt style, ordering, negative transport, accepted reference media, limits, notes. Nothing in it names an endpoint.
- An **offering** inside the model record says how one service exposes that model: `service` (the key it has in the service record), `model_identifier` (its identifier there), `request_keys` (the request key each input occupies: `model` where the request body names the model, `prompt`, `negative prompt` where the target has a negative field, `reference images`, `seed image`, `mask image`, `input image`, on an upscaler that takes one, `guidance prompt`, and for the image size either `width` and `height` or one `size` key), `size_format` with a `size` key (how its text is written, such as `{width}x{height}` or `{ratio_width}:{ratio_height}`), `constraints` (the limits that service enforces, in words), `observed_at`, optionally `schema_snapshot`, `parameter_keys` (the request key each of the record's `recommended_parameters` occupies on this service), and for an upscaler `setting_keys` (the request key each setting the record declares occupies on this service). A record's `recommended_parameters` are the sampling values its author recommends, by service-neutral name (`sampler`, `steps`, `guidance`, `clip_skip`, and the `hires_` values); when a package leaves such a value unset, the builder fills it on the key the offering gives it, so the package shows and commits exactly what is sent. A two-number range is a statement for the person choosing and is never filled in, and a recommendation fills a value rather than switching a feature on: a key under an envelope the package never opened, such as the upscaler of a second pass it does not run, stays unwritten until the package asks for that pass. Every model record carries `offerings`; an empty array says no service here exposes the model, which is the state of a record used through a first-party interface or a local host.

`schema_snapshot` points at the model's attributed parameter schema in its selected pack. The [model evidence workflow](model-evidence.md) imports acquired schemas, preserves reference sources, and attaches existing trial records. The `schema`, `reference`, and `attach-probe` operations publish a validated new local pack for explicit activation.

`scripts/build_generation_payload.py` selects the offering the request goes through (`--service` when the record is exposed on more than one), builds the request as the service would see it from the committed prompt, the parameters, and the number of selected references, evaluates it against the observed schema, and refuses the package on any violation: a width and height pair the service does not accept, a preset given together with explicit dimensions, more references than the channel holds, a parameter the model does not take. The offering used is committed as `generation_payload.service` and the verifier makes the same check from the package. A record with no offering is checked against its own limits only.

The checker evaluates the schema keywords `type`, `const`, `enum`, `required`, `properties`, `additionalProperties`, `dependentRequired`, `items`, `contains`, `minItems`, `maxItems`, `minLength`, `maxLength`, `pattern`, `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`, `multipleOf`, `allOf`, `anyOf`, `oneOf`, `not`, and `if`/`then`/`else`. What a stored schema says with anything else is listed in its `unenforced` field and is settled by the service.

Adding a service is one record in `service-profiles`, an offering on every model record it exposes, and one `scripts/transport_<service>.py` written against the transport contract in the `scripts/dispatch.py` docstring. Adding a model on a service that is already recorded is one offering.

## Model-facing reference transport

Before selecting model carriers, complete the semantic reading and reference-to-prompt synthesis in [Visual Reference Activation and Transport](../visual-reference-activation-and-transport.md). Every selected item must have reviewed preserve, replace, add, and omit scopes plus a positive prompt clause. Transport implements that authority; it does not decide what the SVG means.

Build the canonical plan from record uses. Use `multi-image` when the endpoint accepts several images and preserve every item independently in plan order. Use `single-board` only when the endpoint accepts one image. A board is disposable transport, not a new semantic source; retain each panel's source hash, model-transport hash, semantic role, authority, exclusions, coordinates, and the separate board hash.

Supported raster bytes pass through unchanged when declared by the model record. A selected safe SVG is deterministically rasterized from that same SVG into a supported PNG. Commit renderer ID and release, source hash, dimensions, `max_side`, and output hash. Never substitute a structural, palette, saturation, specular, mask, or faithful artifact for another.

Model-facing execution requires a fully resolved Surface and Lighting Plan. Only a `lighting` plus `faithful-archival-vector` item can resolve `preserve`. `rescope` and `replace` require reviewed target lights and material responses. A nonempty `surface-lighting-plan.unresolved_decisions` list blocks execution.

Build and execute with one pack runtime:

```bash
python scripts/reference_runtime.py plan \
  --record-use <character-record-id>=identity \
  --record-use <scene-record-id>=pose-camera \
  --transport-mode multi-image \
  --target-model gpt-image-2.5-flare \
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

For state-aware pack evidence, add the finalized `--reference-selection`. Follow [State-Aware Series Runtime](state-aware-series.md); the plan cannot bypass state eligibility. Supplied-file-only selection uses its exclusive plan-null preparation path.

The canonical prepared-reference-set commits target and transport mode, optional finalized state selection, non-null plan for activated pack evidence, nested Surface and Lighting hash, structured zero-reference reason, canonical preamble, authoritative source identities, exact source and model carriers, derivations, precedence, optional board manifest, and `prepared_reference_set_sha256`. It is the only reference object passed into Generation Package construction.

`prompt-artifacts` and `svg-bundle` are prompt-delivery transports, never Generation Package reference transports. A Generation Package may contain only a verified `multi-image` prepared set, a verified `single-board` prepared set, or a reference-free `none` set for the exact target model. Do not embed or carry prompt-delivery files as model inputs, and do not relabel a prompt-facing package as a model-facing transport.

## Generation Package

The builder reads the prepared production run and derives what the run and the active pack already hold. The author supplies the prompt, the approved plot, the settled retrieval record, the Production Specification and the continuity decisions.

Before packaging:

1. Prepare a production run for the studio's open work task, as [Production execution](production-execution.md) describes. The run pins the task, its route reading, and the prompt as its delivery.
2. Save the final prompt, the approved plot and the current Production Specification as UTF-8 files. Add the portable negative, its provenance and the image intent when they exist. Omit `--state-lineage-file` for one-off work; the builder seals a stateless lineage.
3. Run each catalog and vocabulary search with `--record lookups.json --element NAME`, and mark each element with `python scripts/prompt_retrieval.py lookups.json --element NAME --adopted ID` (or `--composed TEXT --reason TEXT`). Then run `python scripts/prompt_retrieval.py lookups.json --settle --prompt-file prompt.txt --plot-file plot.json --out retrieval.json`. Unavailable or unsettled retrieval blocks packaging. Approval to prepare is not approval to send.
4. Pass the canonical prepared-reference-set through `--references-file` when references are selected. Do not author another source list.

```bash
python scripts/build_generation_payload.py \
  --model grok-imagine-image-2.0 \
  --prompt-file prompt.txt \
  --plot-file plot.json \
  --retrieval-record-file retrieval.json \
  --production-spec-file production-spec.json \
  --continuity C01=one-off \
  --parameters '{"width":832,"height":1248}' \
  --production-root PROJECT \
  --out PROJECT/generation-package.json
```

The builder derives the rest:

- The run is the open work task's current run, or the one `--production-run` names.
- The route reading is the one the run pinned.
- The request check reads the observed parameter schema that the model record's offering names in the active pack. The package records that pack file by path and hash, with the hashes of the service record, offering, transport and model record. References and bounded production context need an execution policy, so such a package takes `--request-validation-file`. So does a model exposed on no service here.
- Visual continuity comes from `--continuity SUBJECT=DECISION`, one `recurring`, `one-off` or `undecided` decision for each production subject. The builder writes the decisions under the project's `work/continuity/` as their basis. `--visual-continuity-file` supplies a complete record instead.

`--character SUBJECT=CHARACTER` records a subject under its studio character, which a recurring subject needs. That character's current accepted identity images must be among the prepared references. `--sheet-panel` marks an image for a character sheet panel.

For state-aware work, use `scripts/build_state_generation_package.py` with the same production arguments. It validates the supplied graph, story order, and selection identity, era, appearance, state hash, and references. A recurring subject that names the identity contract takes its character ID from that contract. `build_generation_payload.py` rejects state-aware lineage. Production Specification is mandatory for both paths.

State-aware example:

```bash
python scripts/build_state_generation_package.py \
  --model gpt-image-2.5-flare \
  --prompt-file final-prompt.txt \
  --plot-file approved-plot.json \
  --retrieval-record-file retrieval-settled.json \
  --negative-file final-negative.txt \
  --integrated-prompt-file integrated-prompt.txt \
  --negative-provenance-file negative-provenance.json \
  --brief-file source-brief.txt \
  --intent-file creative-intent.json \
  --production-spec-file production-specification.json \
  --state-lineage-file state-lineage.json \
  --species-profile-file species-profile.json \
  --individual-morphology-file individual-morphology.json \
  --identity-contract-file identity-contract.json \
  --state-snapshot-file state-snapshot.json \
  --scene-context-file scene-context.json \
  --visual-projection-file visual-projection.json \
  --asset-render-spec-file asset-render-specification.json \
  --references-file prepared-reference-package/prepared-reference-set.json \
  --request-validation-file request-validation.json \
  --continuity C01=recurring --character C01=C01 \
  --parameters '{"size":"1024x1536"}' \
  --production-root PROJECT \
  --state-file PACK_STATE_JSON \
  --cache-dir CATALOG_CACHE \
  --managed-root MANAGED_PACKS \
  --pack-root ADDITIONAL_PACK_ROOT \
  --out generation-package.json
```

The builder revalidates the prepared set, copies every committed model carrier into the named sibling `<generation-package-stem>.references` directory, rewrites only carrier paths to package-relative paths inside that exact companion, rebuilds reference and generation-input hashes, verifies the staged pair, and publishes with rollback protection.

Move the Generation Package JSON and its named companion together. Every carrier, including a composite board, must use a relative path under that exact companion. Absolute paths, outside-companion paths, traversal, and inferred neighboring files are invalid. Source provenance remains tied to the active pack and is revalidated under the same runtime.

## Verification and host forwarding

Verify and export the committed generation input:

```bash
python scripts/verify_generation_payload.py \
  generation-package.json \
  --prompt-out verified-prompt.txt \
  --negative-out verified-negative.txt \
  --native-negative-out verified-native-negative.txt \
  --payload-out verified-generation-input.json \
  --target gpt-image-2.5-flare \
  --state-file PACK_STATE_JSON \
  --cache-dir CATALOG_CACHE \
  --managed-root MANAGED_PACKS \
  --pack-root ADDITIONAL_PACK_ROOT
```

The verifier output retains the complete positive prompt, portable negative, native subset, all three independently hashed transport renditions, the complete `prepared_reference_set` and `prepared_reference_set_sha256`, its embedded canonical Reference Use Plan and plan hash, its nested Surface and Lighting Plan and hash, and the optional finalized reference-selection origin tied to State Lineage. It does not replace those objects with an abbreviated inventory.

For every ordered prepared-reference row, preserve the complete source identity and source hash, bounded authority, intended influence, exact model-facing transport path, media type and transport hash, deterministic derivation, precedence, and, when state-aware, `binding_id`, `covers`, `review_dimensions`, `unsupported_or_occluded_state`, and `unsupported_assumptions`. Verification reopens current active-pack source bytes and every committed package-relative carrier byte; it also validates the optional board and its panel/source/transport hashes separately from the board hash. A pack-backed activated reference still requires its non-null embedded plan, while a supplied-file-only selection remains on the exclusive plan-null path.

The output also retains `negative_transport_mode`, the exact mode-specific `negative_transport_instruction`, negative provenance, Production Specification plus hash, State Lineage plus hash, verified parameters, and `generation_input_sha256`. That generation-input hash commits the prompts and selected rendition, parameters, Production Specification, State Lineage and selection lineage, and the complete prepared-reference-set commitment as one immutable generation input. Mutating authority, selection scope, source bytes, prepared transport, board, parameter, or lineage requires rebuilding and reverifying the package.

Require all assertions to be true:

- `forward_verified_prompt_transport`;
- `forward_verified_negative_transport`;
- `forward_ordered_reference_transports`;
- `do_not_reconstruct_from_chat`.

Those four true assertions together with the verifier's structured `host_forwarding` object are the complete forwarding contract. The adapter must not supplement them from the sparse brief, chat history, source directories, adjacent files, or remembered model behavior.

When the model record carries an offering, send through the dispatcher, which is what makes recording automatic:

```bash
python scripts/dispatch.py generation-package.json --studio <dir> --character <id> --slot <slot> [--service <id>] [--seed N] [--count N]
python scripts/dispatch.py generation-package.json --studio PROJECT --character SUBJECT_ID --slot SLOT_ID --production-authorization RECEIPT_SHA --send

python scripts/dispatch.py generation-package.json --studio <dir> --character <id> --slot <slot> \
  --state-file PACK_STATE_JSON \
  --cache-dir CATALOG_CACHE \
  --managed-root MANAGED_PACKS \
  --pack-root ADDITIONAL_PACK_ROOT
```

The runtime selectors go together, as everywhere else: the model record and the service record it names are read from one runtime, never from two. Without them the dispatcher reads the default runtime, which is what a session that ran `pack_cli.py ready` already has.

The dry run verifies the package, prints a few plain lines, and then prints the exact request the service would receive. The lines name:

- the model and the service with its endpoint;
- the output count;
- whether the negative prompt is sent, said plainly when the target has no negative field;
- the cost from the offering's or the service's price record, or `cost: unknown`;
- the production run, followed by `shown, not sent`.

`--preview-out FILE` saves the transformation trace and the validation report, and `--intent-out FILE` saves the submission intent to authorize. `--send` executes only under the actual direct or delegated authority for that exact request. Every live send requires a package bound to a prepared production run. The package names the run, and the studio is the production root. Reserve the submission intent and pass its receipt with `--production-authorization`. Upload and send occur only after the claim. The uppercase arguments above are operator-supplied paths and an actual authorization receipt, not values created by the dispatch command.

Every returned image is saved and recorded as an iteration with the request, its response, the answer, the package and the actual file, updating the Studio gallery. The answer is kept once, and each image's response names its place in that answer and the answer's SHA-256. That includes images beside a refusal and a count that differs from the authorization; the run journal under `runs/` records the expected and received counts, any refusal and any failed download. The production run receives a result only when the authorized count arrived in full. An image the answer carries inline is decoded from it, one it names by URL is downloaded only over https from a host the transport declares, and either is kept only when its bytes are an image. When one fails, the images that arrived stay recorded, and `python scripts/production_workflow.py recover-recording --root PROJECT --run RUN_ID` saves the rest from the saved answer without sending anything again. Direction, selection and canonical adoption require their separate authority; see [Production permissions](production-permissions.md). The credential is read from the environment variable the service record names, or from an MCP server's `env` block in the host's configuration, and is never written anywhere. The transport sends it only to the endpoint it accepts from the service record. A model exposed on no service here is sent by hand, and its result is recorded with `studio.py iterate` before anything else is done with it.

## The model's family

A model record names the family whose prompt grammar it reads in `prompt_dialect`, and `scripts/prompt_dialect.py --model <model-id>` returns that family's grammar, blocks, and vocabulary together with the rules that apply to it. Compose for the family the record names, and never carry a quality block, a rating term, a period term, or a weight from another family into it. [Prompt Writing Guide Runtime](prompt-writing-guide.md) owns the sequence.

## Delivery geometry

A checkpoint renders inside the sizes it was trained at. Ask it for a much larger frame and bodies repeat and heads duplicate; ask for a much smaller one and the composition is lost. Reach a larger delivery size with a second pass instead, either the two-stage enlargement the target's adapter describes or an upscale of the accepted image.

`scripts/generation_geometry.py` settles the geometry from the model record rather than from a remembered number:

```bash
python scripts/generation_geometry.py --model <model-id> --list
python scripts/generation_geometry.py --model <model-id> --ratio 2:3
python scripts/generation_geometry.py --model <model-id> --width 832 --height 1216
```

A ratio the record declares in `size_hints` uses the recorded size and label. A hint is not proof of training resolution. An undeclared ratio requires an explicit `--multiple` taken from the applicable model/service contract or an explicitly selected integer-pixel grid. There is no universal eight-pixel assumption. Its pixel budget is the explicit `--pixels` value, or a proposal based on the median declared area; the report distinguishes the two and does not call either a quality guarantee. The size goes on the keys the selected offering records for it and is checked against that service's observed schema. An aspect ratio is sent as the ratio requested or declared, not as the sides reduced. An offering that records no size key leaves the size unchecked. Unknown service limits remain unknown.

Output is JSON on stdout: the width, the height, the pixel count, the ratio, where the answer came from, the offering it was checked against with the `size_fields` it put to the schema (null where the offering records no size key), and `refused_by_the_observed_schema`. The exit status is 1 when a size is refused, and the command exits with a message when the model is unknown, the ratio is not written as width and height, or the record declares no size and none was given. `scripts/generation_geometry_smoke_test.py` is its regression test.

An upscale goes the same way, from one image rather than a package. First prepare an upscale production task and authorize the exact source hash, model, factor and settings; use settings actually supported by the selected upscaler. The upscale goes under the run prepared for the studio's open task:

```bash
python scripts/dispatch.py --upscale --model UPSCALER_ID --source SOURCE_IMAGE --scale 2 --settings SETTINGS_JSON --request-validation-file VALIDATION_JSON --studio PROJECT --character SUBJECT_ID --slot SLOT_ID --production-authorization RECEIPT_SHA --send
```

The factor and the settings are checked against the upscaler record, each setting is placed on the request key the offering's `setting_keys` gives it (a declared setting with no key cannot be sent), `--guidance` is sent only where the offering records a `guidance prompt` request key and is refused before anything is uploaded where it does not, the request asks for a lossless PNG result, the request is checked against the observed schema, and after the service answers the Upscale Package is built from the source and the returned image under the studio's `packages/` and recorded as an iteration with the request and the answer. A generative or creative upscaler leaves the package's identity audit pending until [Upscale Adapter](../adapters/upscale.md) review passes.

`negative_transport_instruction` must equal the verifier-confirmed target instruction exactly. `host_forwarding.reference_preamble` remains separately visible for audit, while `host_forwarding.effective_prompt` is the already assembled transport prompt with that canonical preamble attached exactly once. Forward only `host_forwarding.effective_prompt`, the exact verified negative channel, `host_forwarding.parameters`, and `host_forwarding.selected_references`; never concatenate the separately exposed preamble again.

For `multi-image`, selected references are the committed independent transports in plan order. For `single-board`, the array contains only the committed board. Do not reconstruct from chat. Do not append, paraphrase, reorder, substitute, omit, add, rescope, re-rasterize, scan directories, or resolve carrier paths outside the verifier.

After generation, review the image against the image intent, Visual State Projection, and reference-scope boundary. Diagnose identity drift separately from source-state leakage. When continuity matters, save an Observed Render State. A render is noncanonical until explicitly accepted; route defects to the correct owner rather than editing stable identity to compensate for a scene or model failure.

## Failure policy

Stop when Visual dependencies remain unavailable; the target lacks a declared media type or negative mode; selected evidence is missing, unsafe, changed, or ineligible; the Surface and Lighting Plan is unresolved; the reference count exceeds the endpoint; a carrier escapes its companion; a package or hash check fails; or the host cannot receive every committed transport.

Do not continue by dropping references, changing modes, rebuilding prompt text from chat, scanning an output directory, or forwarding an unverified path. Revise the reviewed plan and regenerate the prepared set and Generation Package.

## Prompt recommendation research

See [Model Prompt Recommendation Research](../model-prompt-recommendations.md) for the admission rule and per-record decisions.

## Concurrent batch dispatch

When the user requests several images at once, across different models or as concurrent variants of one model, complete this runtime for every image first, then follow [Batch Generation Runtime](batch-generation.md). A batch only changes dispatch and review; every image keeps its own verified package, adapter, and image intent.


## Executable walkthrough

[Workflow Walkthrough](workflow-walkthrough.md) takes one idea to a dispatch preview for `grok-imagine-image-2.0` on Runware through the builder and dispatcher CLIs. It sends nothing and uses no credential. State-aware example commands above require both `--plot-file` and `--retrieval-record-file`; `examples/state-aware-pilot/build_example.py` supplies explicit illustrative lookup data for its generated package.


## Artifact evidence and completion

For a saved deliverable, continue through [Production Execution](production-execution.md). Preserve this document's own interpretation, retrieval, approval and adoption boundaries. Prepare the exact inputs, capture the real output, bind review and selection to it, then complete and close the work task. `scripts/production_workflow.py status`, `impact` and `resume` recheck dependencies and artifact bytes. A progress checkbox, a search hit or a newly created image is not production completion or canonical adoption.
