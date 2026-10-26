# State-aware Prompt Workflow

## Inputs

1. approved Character Identity Contract
2. optional Era, Form, and Appearance contracts
3. resolved Character State Snapshot
4. Scene Context Snapshot
5. authored Visual State Projection request
6. selected art direction and production knowledge
7. validated State-aware Reference Bindings, each with an explicit semantic role and complete pack-artifact or supplied-file source
8. an explicit record-use decision for every canonical record that may supply visual evidence
9. target model

## Procedure

1. Resolve approved events and processes at the scene's story time.
2. Extract one Character State Snapshot per state-aware subject; stateless scene participants require no history.
3. Build the Scene Context Snapshot with relationships, environment, inventory and prop bindings, disclosure state, and planned transitions.
4. Decide what the camera can actually show. Build a Visual State Projection containing visible identity, visible state deltas, performance cues, wardrobe, props, relationship blocking, environmental responses, occluded state, required references, text anchors, and review dimensions.
5. Create an Asset Render Specification for the exact scene image or reference asset.
6. Build State Lineage and place its hash in Production Specification.
7. Compose the whole current scene from that projection before detailing its subjects. Interpret narrative context into the visible state, performance and relationships it requires. Keep event history, state IDs and review dimensions in their owning records.
8. Run state-aware reference selection against the current identity, era, appearance, state, story order, and required visible features. Its finalized Reference Selection is an eligibility artifact: it says which committed binding sources and intended influences are allowed at this story point. It does not activate a reference, choose its technical artifact, assign precedence, or replace the Reference Use Plan.
9. When using pack references, build one Reference Use Plan from explicit record, intended-influence and subject-use decisions. It owns active pack artifacts, their order, canonical authority and Surface and Lighting Plan. Execute it with the finalized Reference Selection for its state-managed subjects. Each such source, subject and influence must match its eligible binding. Direct state and additional ordinary references keep their own source and adoption authority in the same prepared set. Any unresolved required state, inactive pack source, stale hash, omitted source or authority expansion blocks materialization.
10. Treat the resulting Prepared Reference Set as the sole prepared-reference truth. Package it with `build_state_generation_package.py`, which validates the lineage graph and selection story order against the supplied State Snapshot, copies its portable carriers into `<out-stem>.references/` beside the Generation Package JSON, rebases their paths, and seals the resulting Prepared Reference Set hash into `generation_input_sha256`. The JSON and companion directory are published transactionally. Verify the Generation Package before model handoff and forward only the verifier-produced host payload.

## Cross-scene rendered-reference transfer

When an earlier render supplies character identity for a new scene, build a reference transfer matrix before prompt composition:

1. `permanent_identity`: stable traits authorized by the Character Identity Contract;
2. `approved_scene_specific_state_to_continue`: current traits authorized by the State Snapshot and Visual State Projection;
3. `source_scene_specific_state_to_discard`: every visible or performance-relevant source property that can change while identity remains the same;
4. `source_render_context_to_discard_or_rescope`: source camera, crop, light, environment, finish, text, logos, insignia, watermarks, and other non-identity residue;
5. `target_scene_specific_state_to_render`: affirmative replacements required by the new Scene Context and Visual State Projection;
6. `scene_reference_scope`: geometry, support, contact, props, camera, environment, light, or finish supplied by each non-identity reference.

Audit scene-specific character state through complete domains: attention and performance; facial, gestural, postural, action, contact, and support articulation; physical, physiological, emotional, and surface condition; appearance and presentation; possession, inventory, equipment, and prop bindings; relationship, social stance, and viewer awareness; environmental response; and resolved current era, form, transformation, or appearance state.

Keep this complete transfer matrix in the reference and state records. In the prompt, describe the target scene and use the actual supplied images or board panels to identify each needed reference use. Preserve the full identity specificity the scene requires. Add concrete retention, replacement or exclusion wording where needed to prevent source-state leakage; the internal state taxonomy is not prompt text.

Do not infer the transfer boundary from visual similarity, input order, or the phrase `same character`. Review the complete target rendition with its actual media to confirm each use is understandable. Record source-state leakage separately from identity drift during output inspection.

## State-aware command chain

```bash
python scripts/state_protocol.py resolve-world --scene-context-id <scene-context-id> ...
python scripts/state_protocol.py extract-character ...
python scripts/build_scene_context.py ...
python scripts/build_visual_state_projection.py ...
python scripts/build_asset_render_spec.py ...
python scripts/state_protocol.py make-lineage --mode state-aware ...
python scripts/select_state_references.py \
  --bindings state-aware-reference-bindings.json \
  --selection-id <selection-id> \
  --identity-contract character-identity-contract.json \
  --state-snapshot character-state-snapshot.json \
  --story-order <story-order> \
  --required-feature <required-visible-feature> \
  --state-file PACK_STATE_JSON \
  --cache-dir CATALOG_CACHE \
  --managed-root MANAGED_PACKS \
  --pack-root ADDITIONAL_PACK_ROOT \
  --out reference-selection.json
python scripts/build_reference_use_plan.py \
  --record-use <canonical-record-id>=identity \
  --transport-mode multi-image \
  --target-model <model-id> \
  --source-lighting-mode replace \
  --light-source-json '<resolved-light-source-object>' \
  --material-response-json '<resolved-material-response-object>' \
  --state-file PACK_STATE_JSON \
  --cache-dir CATALOG_CACHE \
  --managed-root MANAGED_PACKS \
  --pack-root ADDITIONAL_PACK_ROOT \
  --out reference-use-plan.json
python scripts/reference_runtime.py execute \
  --plan reference-use-plan.json \
  --reference-selection reference-selection.json \
  --output-dir prepared-reference-package \
  --prompt-file prompt.txt \
  --negative-file negative.txt \
  --max-side 1536 \
  --state-file PACK_STATE_JSON \
  --cache-dir CATALOG_CACHE \
  --managed-root MANAGED_PACKS \
  --pack-root ADDITIONAL_PACK_ROOT
python scripts/prompt_retrieval.py lookups.json --settle \
  --prompt-file prompt.txt --plot-file approved-plot.json --out retrieval-settled.json
python scripts/build_state_generation_package.py \
  --model <model-id> \
  --plot-file approved-plot.json \
  --retrieval-record-file retrieval-settled.json \
  --production-spec-file production-specification.json \
  --state-graphs-file state-graphs.json \
  --references-file prepared-reference-package/prepared-reference-set.json \
  --request-validation-file request-validation.json \
  --continuity SUBJECT_ID=DECISION \
  --production-root STUDIO \
  --state-file PACK_STATE_JSON \
  --cache-dir CATALOG_CACHE \
  --managed-root MANAGED_PACKS \
  --pack-root ADDITIONAL_PACK_ROOT \
  --out generation-package.json
python scripts/verify_generation_payload.py generation-package.json \
  --studio-root STUDIO \
  --target <model-id> \
  --state-file PACK_STATE_JSON \
  --cache-dir CATALOG_CACHE \
  --managed-root MANAGED_PACKS \
  --pack-root ADDITIONAL_PACK_ROOT
```

Each State-aware Reference Binding owns one caller-authored lowercase `role` and one complete nested `source`. A pack-artifact source preserves pack UUIDv7 and release, asset and artifact IDs, path, media type, and SHA-256. A supplied-file source preserves its stable request-scoped `reference_id`, path, media type, and SHA-256. The declared source kind remains unchanged through state selection.

Pack sources use `reference_runtime.py execute --reference-selection` with the reviewed Reference Use Plan. A selection containing only direct sources uses `prepare_generation_references.py --state-selection-file <reference-selection.json> --model MODEL_ID --output-dir <carrier-dir> --out <prepared-reference-set.json>`. Either executor accepts `--studio-selection-file` with `--studio`, or `--supplied-selection-file`, to append ordinary references for stateless subjects and the scene. [State-aware series](runtime/state-aware-series.md#reference-selection-and-materialization) defines their shared ordering and eligibility checks.

`select_state_references.py` validates the bindings against the complete active pack runtime and emits a finalized Reference Selection with an ordered `selected_references` array. Every entry retains `subject_id`, optional `subject_uses`, `binding_id`, `role`, `source`, `covers`, `intended_influence`, `review_dimensions`, `unsupported_or_occluded_state`, and `unsupported_assumptions`. Its `selection_sha256` seals those fields together with each `subjects[]` context: identity, era, appearance and snapshot hashes, story order, required features, and subject-keyed unresolved requirements. Selection, plan execution, package build, and verification must use the same complete pack runtime. Repeat `--pack-root` for every configured additional root.

The Reference Use Plan records non-empty `selected_records` rows containing `record_id`, optional `subject_uses`, and one canonical `intended_influence`: `identity`, `pose-camera`, `outfit`, `surface-finish`, `lighting`, `environment`, `prop-accessory`, or `local-color`. Each `reference_items` row binds that use to one active `pack-artifact` source and records `precedence`, `semantic_role`, `layer`, `canonical_record_id`, `intended_influence`, `asset_id`, `artifact_id`, `technical_role`, canonical `authority`, and internal authority guidance in `preamble`. Every selected record-use pair must be represented unless the plan carries a structured `zero_reference_reason`; a bare empty selection is not an activation plan.

Authority is the intersection of intended influence and technical evidence role, not the union of everything visible in the source. `controls` lists only the authorized dimensions. `must_not_control` always excludes scene-conditioned presentation outside the declared intended influence, then adds influence-specific and technical-role-specific exclusions. Identity authority includes permanent character identity, stable anatomy and markings, and stable hair, mane, fur-tuft, body-fur distribution, and grooming topology. It excludes gaze, expression, mouth state, perspiration, other transient body state, and wind-, wetness-, motion-, or scene-driven displacement. A state binding may narrow eligibility; it cannot broaden the plan's canonical authority.

Pack-backed plan execution validates every active record, pack release, linked asset and artifact, media type, path, and source SHA-256 again. It embeds the finalized Reference Selection and `selection_sha256`, the Reference Use Plan and `reference_use_plan_sha256`, the nested `surface_lighting_plan_sha256`, and the exact ordered prepared rows in one `prepared-reference-set`. Direct-source state preparation embeds the same finalized selection and ordered rows while keeping the plan-related fields null. Both paths preserve `binding_id`, `role`, `source`, `transport`, bounded `authority`, `covers`, `intended_influence`, `review_dimensions`, `unsupported_or_occluded_state`, and `unsupported_assumptions`. A supported raster source uses direct transport. A selected safe SVG retains source authority and becomes a committed PNG only when the target accepts PNG; [Derived Visual Evidence](derived-visual-evidence.md#layer-c-runtime-attachment-build) defines that preparation. Portable model carriers are stored with package-relative paths. The `prepared_reference_set_sha256` seals the complete canonical object.

Unresolved state requirements block state-reconciled preparation. Unresolved Surface and Lighting Plan decisions block `multi-image` and `single-board` materialization because those modes are model-facing. `prompt-artifacts` and `svg-bundle` may preserve unresolved lighting for review, but those prompt-package modes cannot enter a Generation Package or be forwarded to a model. A no-reference state-aware result remains explicit: it carries the finalized Reference Selection, the plan's structured `zero_reference_reason`, and an empty transport payload.

The Generation Package builder revalidates the complete Prepared Reference Set under the active pack runtime, copies every portable carrier into `<out-stem>.references/` beside the output JSON, rewrites only carrier paths relative to the Generation Package, reseals `prepared_reference_set_sha256`, and includes that hash in `generation_input_sha256`. It publishes the JSON and companion directory transactionally. The verifier resolves those paths against the Generation Package directory, rehashes source and carrier bytes, revalidates the active pack links, and emits `host_forwarding`: `model`, `parameters`, `selected_transport`, `effective_prompt`, `effective_prompt_sha256`, `selected_references`, and `generation_input_sha256`. A host sends only `effective_prompt`, the verifier-selected negative transport, parameters, and the ordered `selected_references` array of `role`, absolute verifier-resolved `resolved_path`, `media_type`, and `sha256`. The authored prompt expresses each reference use through the delivered images; internal bindings retain its source and subject assignment. For `single-board`, the reference array contains only the verified `composite-reference-board`, while panel source and transport hashes remain sealed inside the Prepared Reference Set. Do not forward plan sources, prompt-artifact copies, or independently reconstructed references. If verification or forwarding fails, stop the generation request.

The state builder reads one `state_graphs` array for one or several characters.
Each entry contains the complete concrete nodes consumed by the existing graph
validator. [State-aware series](runtime/state-aware-series.md#reference-selection-and-materialization)
defines their keys, mixed state-aware and stateless cast, and independent coverage.
The Generation Package commits the graphs and their array hash; verification
rechecks every subject's full graph, common scene context and render decisions.

## Within-clip change

Represent a visible transition with:

```text
start state snapshot
planned transition event
end state snapshot proposal
```

A start frame may carry opening state, the motion prompt may carry the causal path, and an end frame may carry landing state. A planned transition becomes approved canon only after user approval or acceptance of the visible event.


## Morphology resolution step

Before prompt composition:

1. Load and validate the subject's species morphology profile.
2. Load and validate the individual morphology contract.
3. Verify that the identity contract references both hashes.
4. Resolve the approved current form and morphology-related state paths.
5. Select the visible feature instances required by the shot.
6. Preserve hidden features as out-of-frame or occluded declarations.
7. Build count, attachment, surface, expression, crop, and uncertainty proof into `resolved-morphology`.
8. Regenerate the prompt when the resolved morphology, state snapshot, or scene context changes.

Do not reconstruct anatomy from chat memory or from the species noun alone.
