# Shared State Protocol Schema Index

## Contracts

- `character-identity-contract.schema.json`
- `era-contract.schema.json`
- `form-contract.schema.json`
- `appearance-variant-contract.schema.json`
- `character-state-schema.schema.json`
- `frame-character.schema.json`
- `part-measurement.schema.json`
- `accessory-geometry.schema.json`

## Canonical events and derived state

- `state-event.schema.json`
- `state-process.schema.json`
- `world-state-snapshot.schema.json`
- `state-snapshot.schema.json`
- `relationship-state.schema.json`
- `environment-snapshot.schema.json`
- `wardrobe-state.schema.json`
- `inventory-state.schema.json`
- `scene-context-snapshot.schema.json`

`state-event` uses per-change expiry and clear references, exact scene binding for scene-local mutations, and explicit process lifecycle actions. `state-process` uses authored integer milestones and one required interruption policy. World and character snapshots record the target scene context used for resolution.

The reusable starters preserve both event modes: `templates/state/state-event.template.json` demonstrates a scene-local mutation, and `templates/state/state-event-temporary-until-cleared.template.json` demonstrates preconditions plus per-change clearing and expiry.

## Projection and generation

- `relationship-projection.schema.json`
- `visual-state-projection.schema.json`
- `appearance-adaptation-proposal.schema.json`
- `asset-render-specification.schema.json`
- `state-lineage.schema.json`
- `visual-authority.schema.json`
- `semantic-region-map.schema.json`
- `visual-evidence-bundle.schema.json`
- `reference-use-plan.schema.json`
- `surface-lighting-plan.schema.json`
- `prepared-generation-reference.schema.json`
- `prepared-reference-set.schema.json`
- Production Specification
- Generation Package

The generation reference chain has one authority direction:

```text
explicit canonical record uses
→ Reference Use Plan
+ optional finalized Reference Selection as a state-eligibility gate
→ Prepared Reference Set
→ Generation Package
→ verifier-produced host forwarding
```

State Lineage also has two independent starters. `templates/state/state-lineage.template.json` is stateless; `templates/state/state-lineage-state-aware.template.json` exposes every required state-aware graph hash without replacing the stateless example.

The Reference Selection and Reference Use Plan are not parallel activation lists. The Reference Selection proves story-time eligibility for committed binding sources and intended influences. The Reference Use Plan is the only activation, authority, technical-artifact, precedence, transport-mode, and surface-lighting decision. State-aware execution intersects the plan with the selection; it never unions their authority.

## References, adoption, and observation

The reusable core visual-evidence starters at `templates/state/semantic-region-map.template.json`, `templates/state/visual-authority.template.json`, and `templates/state/visual-evidence-bundle.template.json` are neutral and unbound. Their `canonical_record_refs` arrays are empty, and placeholder source and derivative values carry no authority. Populate source hashes, derivative artifacts, semantic observations, and record bindings only after reviewing real evidence. Run `python scripts/default_only_example_resolution_smoke_test.py` to resolve every non-empty catalog-selection field in the state-aware pilot and core state templates against `packs/commons` alone. Pack-specific evidence remains in its owning pack and is validated through that pack's lock and release gate.

- `reference-bundle-plan.schema.json`
- `candidate-manifest.schema.json`
- `adoption-receipt.schema.json`
- `state-aware-reference-binding.schema.json`
- `reference-selection.schema.json`
- `observed-render-state.schema.json`
- `drift-observation.schema.json`

All protocol artifacts declare `artifact_type`. Hash-sealed derived artifacts exclude their own hash field from canonical JSON before SHA-256 calculation. Structural validity comes from the current schema files and validators in the same product release, not from an independently versioned artifact field.


## Morphology artifacts

- `morphology-feature.schema.json`: reusable feature definition for limbs, organs, appendages, surfaces, mechanical systems, and expression carriers.
- `morphology-feature-instance.schema.json`: exact individual realization of one species feature.
- `species-morphology-profile.schema.json`: species or lineage topology, feature inventory, surfaces, expression grammar, capabilities, population variation, meaningful absences, and differentials.
- `individual-morphology-contract.schema.json`: exact recurring subject morphology, measurements, instances, markings, asymmetries, tools, personal expression, state boundaries, and uncertainties.
- `resolved-morphology.schema.json`: shot-visible anatomy after state, form, crop, pose, clothing, and occlusion.
- `frame-character.schema.json`: face-body frame mass, surface character, padding, structural projections, coherence, and diagnostic misreadings.
- `part-measurement.schema.json`: local landmark-anchored dimensions and tolerances for reconstruction-critical parts.
- `accessory-geometry.schema.json`: accessory count, attachment, construction, dimensions, repeated elements, materials, layer order, contact response, and continuity.
- `visual-authority.schema.json`: content-derived source reference, source SHA-256, native dimensions, the Layer A perceptual-vector hash, canonical record references, and portability notes.
- `semantic-region-map.schema.json`: optional authored regions tied to SVG element IDs in native source coordinates. Automated extraction alone does not imply review or approval.
- `visual-evidence-bundle.schema.json`: native-dimension source-derived perceptual vector projection, fidelity and semantic metadata, content hashes, and canonical record references.
- `reference-use-plan.schema.json`: a non-empty `selected_records` array of exact `record_id` and canonical `intended_influence` pairs; active pack-linked `reference_items` with contiguous `precedence`, unique `semantic_role`, layer, record, asset, artifact, technical role, committed source, canonical `authority`, and canonical `preamble`; the embedded Surface and Lighting Plan and its hash; a structured zero-reference reason when no item is usable; and `reference_use_plan_sha256`.
- `surface-lighting-plan.schema.json`: explicit `preserve`, `rescope`, or `replace` source-lighting mode; technical source-evidence roles; target light sources; shadow topology; highlight response; material response; protected highlight islands; unresolved decisions; and `surface_lighting_plan_sha256`. Unresolved decisions may remain in a prompt package but block model-facing reference materialization.
- `prepared-generation-reference.schema.json`: one exact ordered transport row. A generic row contains `role`, committed `source`, exact `transport`, and explicit `authority`; when it is prepared from a Reference Use Plan, that authority must exactly match the corresponding plan item. A state-scoped row additionally retains `binding_id`, `covers`, the binding's canonical `intended_influence` array, `review_dimensions`, `unsupported_or_occluded_state`, and `unsupported_assumptions`.
- `prepared-reference-set.schema.json`: the sole canonical prepared-reference object. It binds `reference_selection` and `reference_selection_sha256` when state eligibility is used; `reference_use_plan`, `reference_use_plan_sha256`, and `surface_lighting_plan_sha256` when a Reference Use Plan is used; a structured `zero_reference_reason`; canonical `reference_preamble`; exact prompt-artifact copies; ordered model-facing references; single-board metadata; and `prepared_reference_set_sha256`.

The canonical intended-influence values are `identity`, `pose-camera`, `outfit`, `surface-finish`, `lighting`, `environment`, `prop-accessory`, and `local-color`. Each plan item receives only the authority supported by both its intended influence and its technical role. `authority.controls` names those dimensions. `authority.must_not_control` includes scene-conditioned presentation outside the declared intended influence together with influence-specific and technical-role-specific exclusions. In particular, stable hair, mane, fur-tuft, body-fur distribution, and grooming topology may belong to identity, while gaze, expression, mouth state, perspiration, outfit, transient body state, and scene-driven wind, wetness, motion, or grooming displacement do not.

State-aware reconciliation requires exact source equality between each activated plan item and one eligible `selected_references` binding row, plus membership of the plan item's intended influence in that row's `intended_influence` array. Unresolved required state, inactive records or packs, stale releases, changed source paths, media types, or bytes, and authority expansion are validation failures. A state-aware zero-reference set still embeds its finalized Reference Selection and the plan's structured reason.

Portable carriers use paths relative to the prepared-reference package and, after Generation Package construction, relative to the Generation Package directory. The builder copies them into `<out-stem>.references/` beside the output JSON and publishes the JSON and companion directory transactionally. Active-pack source paths remain committed provenance and are revalidated against the configured pack runtime. The Prepared Reference Set hash seals every nested selection, plan, authority, scope, carrier path, derivation, and hash. The Generation Package repeats that hash at package and generation-contract level and incorporates it into `generation_input_sha256`.

Only the verifier may turn a Generation Package into a host request. It resolves and rehashes package-relative carriers and emits an effective prompt plus ordered forwarding rows containing only `role`, resolved `resolved_path`, `media_type`, and `sha256`. The returned `reference_preamble` is an audit field already incorporated into the effective prompt. `multi-image` forwards each verified role transport. `single-board` forwards one `composite-reference-board`; its panel source and transport hashes remain sealed in the Prepared Reference Set. Prompt-package `prompt-artifacts` and `svg-bundle` modes are not model-forwarding contracts.

These schemas and templates are CPB-owned. Optional consumers receive content-addressed interchange envelopes and declared features rather than byte-identical copies of the CPB source tree.

- [`prompt-semantic-preflight.schema.json`](../schemas/prompt-semantic-preflight.schema.json): structured anatomy and camera contradiction preflight for prompt construction.
