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
2. Extract one Character State Snapshot per visible subject.
3. Build the Scene Context Snapshot with relationships, environment, inventory and prop bindings, disclosure state, and planned transitions.
4. Decide what the camera can actually show. Build a Visual State Projection containing visible identity, visible state deltas, performance cues, wardrobe, props, relationship blocking, environmental responses, occluded state, required references, text anchors, and review dimensions.
5. Create an Asset Render Specification for the exact scene image or reference asset.
6. Build State Lineage and place its hash in Production Specification.
7. Write the prompt as one coherent art brief. Use current visible results, not the full event history.
8. Run state-aware reference selection against the current identity, era, appearance, state, story order, and required visible features. Its finalized Reference Selection is an eligibility artifact: it says which committed binding sources and intended influences are allowed at this story point. It does not activate a reference, choose its technical artifact, assign precedence, or replace the Reference Use Plan.
9. Build exactly one record-scoped Reference Use Plan from explicit `record_id=intended_influence` decisions. The plan is the only activation and ordering truth. It binds every selected record use to active pack artifacts, assigns contiguous precedence and unique semantic roles, derives canonical `controls` and `must_not_control` authority, embeds the Surface and Lighting Plan, and seals both plan hashes. Execute that plan with the finalized Reference Selection as an eligibility gate. Every activated plan source must exactly match a selected binding source, and the plan item's intended influence must be present in that binding's `intended_influence` array. Any mismatch, unresolved required state, inactive pack source, stale source hash, omitted record use, or authority expansion blocks materialization.
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

The prompt must label each image by role. State that the identity image governs permanent traits only. Define scene-specific character state using the identity-preserving counterfactual test, exclude the complete source state by domain, and give affirmative target values for every load-bearing domain. Do not use a finite list ending in `and so on` as the transfer boundary. Scope source-render context separately, and scope each scene reference to authorized scene construction while rejecting its source-character identity and contamination.

Do not infer the transfer boundary from visual similarity, input order, or the phrase `same character`. A minimal instruction may achieve coarse compositing while still leaking source state. Record source-state leakage separately from identity drift during output inspection.

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
  --prompt-file prompt.txt \
  --plot-file approved-plot.json \
  --retrieval-record-file retrieval-settled.json \
  --production-spec-file production-specification.json \
  --state-lineage-file state-lineage.json \
  --species-profile-file species-morphology-profile.json \
  --individual-morphology-file individual-morphology-contract.json \
  --identity-contract-file character-identity-contract.json \
  --state-snapshot-file character-state-snapshot.json \
  --scene-context-file scene-context-snapshot.json \
  --visual-projection-file visual-state-projection.json \
  --asset-render-spec-file asset-render-specification.json \
  --references-file prepared-reference-package/prepared-reference-set.json \
  --request-validation-file request-validation.json \
  --continuity SUBJECT_ID=DECISION \
  --production-root PROJECT \
  --state-file PACK_STATE_JSON \
  --cache-dir CATALOG_CACHE \
  --managed-root MANAGED_PACKS \
  --pack-root ADDITIONAL_PACK_ROOT \
  --out generation-package.json
python scripts/verify_generation_payload.py generation-package.json \
  --target <model-id> \
  --state-file PACK_STATE_JSON \
  --cache-dir CATALOG_CACHE \
  --managed-root MANAGED_PACKS \
  --pack-root ADDITIONAL_PACK_ROOT
```

Each State-aware Reference Binding owns one caller-authored lowercase `role` and one complete nested `source`. A pack-artifact source preserves pack UUIDv7 and release, asset and artifact IDs, path, media type, and SHA-256. A supplied-file source preserves its stable request-scoped `reference_id`, path, media type, and SHA-256. The declared source kind remains unchanged through state selection.

Preparation has two exclusive paths. If the finalized selection contains any `pack-artifact`, build one record-scoped Reference Use Plan and execute it with `reference_runtime.py execute --reference-selection`; the exact selected source and intended influence must match the plan. If the finalized selection contains only `supplied-file` sources, run `prepare_generation_references.py --state-selection-file <reference-selection.json> --output-dir <carrier-dir> --out <prepared-reference-set.json>`; this path keeps the plan and Surface and Lighting fields null and rejects every pack-artifact row. Do not combine pack-backed and plan-null preparation.

`select_state_references.py` validates the bindings against the complete active pack runtime and emits a finalized Reference Selection with an ordered `selected_references` array. Every entry retains `binding_id`, `role`, `source`, `covers`, `intended_influence`, `review_dimensions`, `unsupported_or_occluded_state`, and `unsupported_assumptions`. Its `selection_sha256` seals those fields together with the identity, era, appearance, and State Snapshot hashes, story order, required state features, and unresolved requirements. Selection, plan execution, package build, and verification must use the same complete pack runtime. Repeat `--pack-root` for every configured additional root.

The Reference Use Plan records non-empty `selected_records` rows containing exactly `record_id` and one canonical `intended_influence`: `identity`, `pose-camera`, `outfit`, `surface-finish`, `lighting`, `environment`, `prop-accessory`, or `local-color`. Each `reference_items` row binds that use to one active `pack-artifact` source and records `precedence`, `semantic_role`, `layer`, `canonical_record_id`, `intended_influence`, `asset_id`, `artifact_id`, `technical_role`, canonical `authority`, and canonical `preamble`. Every selected record-use pair must be represented unless the plan carries a structured `zero_reference_reason`; a bare empty selection is not an activation plan.

Authority is the intersection of intended influence and technical evidence role, not the union of everything visible in the source. `controls` lists only the authorized dimensions. `must_not_control` always excludes scene-conditioned presentation outside the declared intended influence, then adds influence-specific and technical-role-specific exclusions. Identity authority includes permanent character identity, stable anatomy and markings, and stable hair, mane, fur-tuft, body-fur distribution, and grooming topology. It excludes gaze, expression, mouth state, perspiration, other transient body state, and wind-, wetness-, motion-, or scene-driven displacement. A state binding may narrow eligibility; it cannot broaden the plan's canonical authority.

Pack-backed plan execution validates every active record, pack release, linked asset and artifact, media type, path, and source SHA-256 again. It embeds the finalized Reference Selection and `selection_sha256`, the Reference Use Plan and `reference_use_plan_sha256`, the nested `surface_lighting_plan_sha256`, the canonical reference preamble, and the exact ordered prepared rows in one `prepared-reference-set`. Supplied-file-only state preparation embeds the same finalized selection and ordered rows while keeping the plan-related fields null. Both paths preserve `binding_id`, `role`, `source`, `transport`, bounded `authority`, `covers`, `intended_influence`, `review_dimensions`, `unsupported_or_occluded_state`, and `unsupported_assumptions`. For `gpt-image-2.5-flare`, PNG, JPEG, and WebP sources use direct transport; a selected safe SVG remains the authoritative source and is deterministically rasterized to a committed PNG transport. Portable model carriers are stored with package-relative paths. The `prepared_reference_set_sha256` seals the complete canonical object.

Unresolved state requirements block state-reconciled preparation. Unresolved Surface and Lighting Plan decisions block `multi-image` and `single-board` materialization because those modes are model-facing. `prompt-artifacts` and `svg-bundle` may preserve unresolved lighting for review, but those prompt-package modes cannot enter a Generation Package or be forwarded to a model. A no-reference state-aware result remains explicit: it carries the finalized Reference Selection, the plan's structured `zero_reference_reason`, and an empty transport payload.

The Generation Package builder revalidates the complete Prepared Reference Set under the active pack runtime, copies every portable carrier into `<out-stem>.references/` beside the output JSON, rewrites only carrier paths relative to the Generation Package, reseals `prepared_reference_set_sha256`, and includes that hash in `generation_input_sha256`. It publishes the JSON and companion directory transactionally. The verifier resolves those paths against the Generation Package directory, rehashes source and carrier bytes, revalidates the active pack links, and emits `host_forwarding`: `model`, `parameters`, `selected_transport`, `reference_preamble`, `effective_prompt`, `effective_prompt_sha256`, `selected_references`, and `generation_input_sha256`. A host sends only `effective_prompt`, the verifier-selected negative transport, parameters, and the ordered `selected_references` array of `role`, absolute verifier-resolved `resolved_path`, `media_type`, and `sha256`. `reference_preamble` remains audit data and is already incorporated into `effective_prompt`; do not prepend it a second time. For `single-board`, the reference array contains only the verified `composite-reference-board`, while panel source and transport hashes remain sealed inside the Prepared Reference Set. Do not forward plan sources, prompt-artifact copies, or independently reconstructed references. If verification or forwarding fails, stop the generation request.

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
