# Reference Bundle Workflow

## Planning

`scripts/build_reference_bundle.py` creates a Reference Bundle Plan and one Asset Render Specification per planned view. All assets share the same Identity Contract hash and style family, while every view has its own Render Specification hash.

The identity supplies `reference_views` with explicit view names, coverage tokens and camera contracts. It also declares the coverage requirements those candidates can satisfy. The planner selects only from those views until the declared requirements are covered; when no requirements are given it uses the declared views. An unresolved requirement is reported, not replaced by a conventional anatomical view.

`core-coverage`, `series-coverage` and `motion-evaluation` label the intended review scope. The caller authors the corresponding identity, recurring-state or motion coverage requirements. A policy label never supplies a fixed part inventory, camera or image count.

## Generation and inspection

The plan is not canon. Generate candidates, then inspect actual files. `scripts/build_candidate_manifest.py` records file hashes and dimensions while preserving human-authored declarations of visible support, occlusion, contradiction, and recommendation.

A Reference Bundle Plan is a coverage plan for candidate creation, not the activation list for an unrelated generation request. For a current request, inspect active canonical records and their linked assets, then make one explicit `record_id=intended_influence` decision for every record that should contribute. Build one record-scoped Reference Use Plan with `scripts/build_reference_use_plan.py`; do not create a second ordered source list. The plan resolves active linked artifacts, assigns contiguous precedence and unique semantic roles, derives technical roles and canonical authority, embeds the Surface and Lighting Plan, and seals the complete decision. Plan execution, Generation Package construction, and verification use the same complete pack runtime.

The canonical intended-influence vocabulary is `identity`, `pose-camera`, `outfit`, `surface-finish`, `lighting`, `environment`, `prop-accessory`, and `local-color`. A reference artifact may be selected only when its technical role supports the declared influence. Its `controls` are the exact intersection of that influence and technical role. Its `must_not_control` begins with scene-conditioned presentation outside the declared influence and adds all influence-specific and technical-role-specific exclusions. Input order, visible similarity, or an unlabeled image must never expand that authority or invite averaging.

Before plan execution, separate permanent-identity authority from scene-conditioned authority. Identity authority may govern permanent character identity, stable anatomy and marking layout, and stable hair, mane, fur-tuft, body-fur distribution, and grooming topology. It must not govern gaze, facial expression, mouth state, perspiration, other transient body state, outfit, props, pose, camera, environment, lighting, or wind-, wetness-, motion-, and scene-driven grooming displacement unless a separate declared influence independently authorizes that dimension. Record the complete source scene-specific character state and source-render context that must not transfer from an identity-only image. If a selected source cannot produce its declared verified transport, stop the request.

Execute a reviewed plan with `scripts/reference_runtime.py execute`. The executor revalidates the selected canonical records, active pack releases, linked asset and artifact identities, media types, resolved source paths, and source SHA-256 values before copying or rasterizing anything. It writes the Reference Use Plan, Surface and Lighting Plan, canonical reference preamble, exact prompt-artifact copies when requested, model-facing transports when requested, and the sole canonical `prepared-reference-set` into one transactionally published package. Carrier paths are relative to that package; active-pack source provenance remains committed and is revalidated. A safe SVG remains the source artifact and may be deterministically rasterized to PNG only for a target model that accepts the resulting media type.

`prompt-artifacts` and `svg-bundle` are prompt-package modes. They may preserve unresolved Surface and Lighting Plan decisions for review, but they cannot enter a Generation Package or be forwarded to a model. `multi-image` and `single-board` are model-facing modes and require all surface-lighting decisions to be resolved. `multi-image` preserves one verified transport per ordered role. `single-board` preserves each panel's source and transport hashes in the Prepared Reference Set while exposing only the verified composite board at host handoff. A structured `zero_reference_reason` is required when an explicit Reference Use Plan produces no reference item.

## Adoption

For local Studio results, [Adoption Workflow](runtime/adoption-workflow.md) provides an executable sheet-binding and pack-registration path, including a `studio-adoption-receipt`. This receipt bounds visual influence and is not the separate story-state `adoption-receipt`. A story-state Adoption Receipt is still an explicit registry operation using the state protocol; local image adoption does not silently update identity, eras, contracts, or story ranges. It does not edit the Candidate Manifest. The receipt maps accepted candidates to Asset Registry IDs, versions, effective story ranges, and supersession, and preserves the corresponding registry-update payloads in `asset_registry_updates`. The adopting registry must record the resulting registry version and any supersession relationship.

## State-aware bindings

Each adopted asset should receive a State-aware Reference Binding:

- identity/era/appearance/state hashes
- effective story range
- one caller-authored lowercase semantic `role`
- one complete `source`: either an active-catalog `pack-artifact` source or a measured `supplied-file` source
- visibly supported state
- unsupported or occluded state
- intended influence
- unsupported assumptions
- review dimensions

Reference selection checks story time and identity, era, appearance, and State Snapshot hashes before ranking bindings. It emits a finalized eligibility artifact whose ordered `selected_references` array retains `binding_id`, `role`, complete nested `source`, covered state features, intended influence, review dimensions, unsupported or occluded state, and unsupported assumptions. Superseded bindings may remain eligible at story times covered by their approved range. Reference Selection does not activate references, pick linked technical artifacts, assign precedence, or supersede the Reference Use Plan.

Each binding supplies state eligibility, a semantic role, scope limits, and the exact authoritative committed source. Use exactly one of two preparation paths. A selection containing any `pack-artifact` source goes through `scripts/reference_runtime.py execute --reference-selection` with one reviewed Reference Use Plan; every activated plan source and intended influence must match an eligible binding exactly. A selection containing only `supplied-file` sources goes through `scripts/prepare_generation_references.py --state-selection-file`; that path emits a plan-null Prepared Reference Set and rejects every pack-artifact row. Do not mix the two paths or fabricate pack ownership for a supplied file. State eligibility may narrow activation but cannot broaden plan-derived or state-derived authority. Unresolved required state blocks both paths.

The resulting Prepared Reference Set always embeds `reference_selection`, `reference_selection_sha256`, the ordered prepared rows, carrier metadata, a structured zero-reference reason when applicable, and `prepared_reference_set_sha256`. The pack-backed path also embeds the Reference Use Plan, Surface and Lighting Plan hash, and canonical preamble. The supplied-file-only path keeps those plan fields null and derives conservative authority from the finalized selection. Every state-scoped prepared row preserves `binding_id`, `role`, complete `source`, exact `transport`, bounded `authority`, `covers`, `intended_influence`, `review_dimensions`, `unsupported_or_occluded_state`, and `unsupported_assumptions`.

The Generation Package builder validates the Prepared Reference Set, copies its portable carriers into `<out-stem>.references/` beside the output JSON, rewrites only those carrier paths relative to the Generation Package, reseals `prepared_reference_set_sha256`, includes it in `generation_input_sha256`, and publishes the JSON and companion directory transactionally. The verifier resolves and rehashes the carriers, rechecks active-pack sources, and emits the only host-authorized forwarding object. The host sends the verifier's effective prompt, selected negative transport, parameters, and ordered `selected_references` rows of `role`, verifier-resolved `resolved_path`, `media_type`, and `sha256`. The verifier also returns `reference_preamble` for audit, but it is already incorporated into the effective prompt and must not be prepended again. The host must not forward a source path, prompt-artifact copy, unverified transport, or reconstructed reference. Missing files, unresolved required state or model-facing lighting, omitted or reordered scope, authority expansion, source drift, role drift, pack-state drift, carrier drift, or catalog mismatch blocks generation.
