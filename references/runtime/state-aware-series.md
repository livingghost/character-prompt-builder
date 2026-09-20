# State-Aware Series Runtime

Use this document for recurring characters, temporal continuity, visible consequences of off-screen events, rendered identity references from other scenes, or an arriving shot-request. For a one-off image with no continuity state, use a stateless Production Specification and skip this document.

## Contents

- [Authority graph](#authority-graph)
- [State domains and visibility](#state-domains-and-visibility)
- [Morphology and grooming continuity](#morphology-and-grooming-continuity)
- [Scene Production Specification](#scene-production-specification)
- [Rendered-reference identity transfer](#rendered-reference-identity-transfer)
- [Reference Selection and materialization](#reference-selection-and-materialization)
- [Conditional state authorities](#conditional-state-authorities)
- [Optional consumer boundary](#optional-consumer-boundary)

## Authority graph

When world rules, themes, portrayal or narrative intent are being designed, use
[World-Coherent Creative Development](narrative-development.md). Relevant world records and
phase-specific personas supply their scoped baselines; this runtime governs approved scene state.
A proposed world change, relationship turn or future persona is not an executed state event.
A theme, genre convention or author-only plan cannot override current state.

Do not reconstruct current state from chat memory. Resolve the current image from approved artifacts:

```text
Identity, Era, Form, and Appearance contracts
+ approved State Event Ledger and State Processes
-> World State Snapshot
-> Character State Snapshot
+ Scene Context Snapshot
-> Visual State Projection
-> Asset Render Specification
-> scene-specific Production Specification
```

The Identity Contract owns stable anatomy, proportions, markings, distinctive details, asymmetry, identity-level accessories, stable performance vocabulary, and stable grooming construction. The State Event Ledger owns approved change over story time. Scene Context owns current relationships, environment, wardrobe, inventory, props, disclosure, and planned transitions. Visual State Projection decides what the current camera may show, what remains hidden, what performance consequences are visible, and which text or references carry each critical fact.

The authority order remains user intent and approved canon, approved identity and event history, resolved snapshots and context, Visual State Projection and Production Specification, then selected catalog knowledge and project defaults. A scene record cannot overwrite identity or history. Do not paste the whole history into the prompt; project only current visible or performance-relevant truth while preserving hashes and source references.

## State domains and visibility

Track state as open domains:

- physical condition, injury, healing, wetness, dirt, fatigue, aging, and form;
- felt, expressed, masked, and physiological emotion;
- directional relationship state, authority, trust, conflict, contact boundaries, public mask, and private behavior;
- season, temperature, humidity, weather, physical light, approved locale or culture, and environmental body response;
- wardrobe layers and condition;
- owned, possessed, carried, equipped, stored, transferred, consumed, lost, damaged, or repaired objects;
- character-specific processes such as transformation, curse progression, overheat, seasonal coat, or recovery.

Off-screen events remain real when approved. If the underlying feature is hidden, show only approved visible consequences through posture, behavior, condition, or performance. Do not expose an undisclosed fact because the state model knows it. Resolve time jumps from events and approved Era Contracts; do not invent aging merely because years passed. Multi-entity transfers are atomic.

Regenerate a prompt package when a scene-visible semantic input changes: identity, era, form, appearance variant, visible state, wardrobe, prop or inventory binding, expressed emotion, relationship blocking, environmental response, camera, lighting, target, or reference selection. A knowledge-only update with no visible or performance consequence updates state without forcing a new image prompt.

## Morphology and grooming continuity

Resolve frame character before body-build prose can fill it by implication. Carry one face-body frame declaration, load-bearing landmark-relative measurements, and exact accessory geometry into resolved morphology and the Production Specification.

For recurring or structurally unfamiliar subjects:

1. Author or load one `species-morphology-profile`.
2. Inventory meaningful present and absent features, counts, laterality, attachment topology, dimensions, surfaces, articulation, function, expression role, development, and near-species differences.
3. Author or load one `individual-morphology-contract` containing the face-body frame, exact measurements, feature instances, markings, asymmetry, damage, grooming, nails or claws, accessory geometry, personal performance behavior, tools, state boundaries, and unresolved fields.
4. Resolve the active form and current state into `resolved-morphology` for the shot.
5. Carry visible and hidden feature references, count and attachment proof, expression-channel state, crop rules, and uncertainty into review.
6. Never infer an undeclared part or capability from a broad creature label. Never erase a declared part because it lies outside the crop.
7. For a fictional species, direct topology and feature records are authoritative; a real-species noun is optional.
8. When a shot-request supplies the shot, validate species, individual, identity, state, and visible-feature hashes before composing.

For anthropomorphic or creature subjects, distinguish human-like head hair from base covering, mane, ruff, facial hair, and localized fur or hair systems. Record presence or absence, boundaries, section map, landmark-relative length, density, direction, texture, color relationship, silhouette role, clearance, and continuity. Stable construction belongs to identity; wetness, wind, disorder, compression, raised fur, and temporary styling belong to current state.

For every localized identity detail, use the subject's own left and right, anchor it to stable landmarks, separate physical depth from color, state count and distribution, and preserve visibility or occlusion rules. Leave hidden continuation unspecified. Ask one focused question when a signature detail is materially ambiguous.

## Scene Production Specification

Use `templates/production-spec-template.json`, `templates/performance-language-template.json`, [Production Specification](../production-specification.md), and [Performance Language Specification](../performance-language-specification.md). `templates/state/state-lineage.template.json` is the sealed stateless starter. For a continuity graph, start from `templates/state/state-lineage-state-aware.template.json`, replace every example node hash with the hash of the reviewed artifact it names, then recompute `lineage_sha256`. A state-aware subject references its Identity Contract, State Snapshot, and Visual State Projection; the specification references the sealed State Lineage and Scene Context.

Use only consequential modules. Fine controls may cover identity projection, proportions, head and facial construction, hair and regional covering maps, current physical state, wardrobe layers and condition, inventory, torso and support geometry, separate left/right hand and leg chains, coordinated performance channels, gaze target and head rotation, relationship distance and contact, environmental response, depth, camera, crop, lighting, and selected rendering knowledge.

Validate saved artifacts:

```bash
python scripts/state_protocol.py validate <artifact.json> [...]
python scripts/production_spec.py validate production-specification.json --require-content
python scripts/validate_state_protocol.py .
```

The first two commands validate authored artifacts; `validate_state_protocol.py` validates the repository-wide protocol set.

Author only the complete field structure defined by the current Production Specification template. Artifact identity comes from structure, semantic IDs, hashes, and lineage rather than independent internal version fields.

## Rendered-reference identity transfer

A rendered character reference mixes four evidence classes: permanent identity, scene-specific character state, source-render context, and contamination. A request such as `use the same character` does not tell the target model which visible properties are identity. Scene-specific character state is every visible or performance-relevant property that can change while the subject remains the same character unless an approved Identity, Era, Form, or Appearance Contract owns it.

Audit the source into five groups before prompt writing:

1. permanent identity to transfer;
2. approved scene-specific state to continue because the user or resolved state requires it;
3. source-only scene-specific state to discard;
4. source-render context or contamination to discard or rescope, including camera, crop, lighting, environment, finish, readable text, logos, insignia, and watermarks;
5. affirmative target scene state and render context replacing every discarded load-bearing domain. Do not stop at `do not copy the grin`; specify the intended performance, articulation, physical and surface condition, presentation, bindings, relationships, awareness, environmental response, and current form or appearance.

Source scene state is unlocked by default. A rendered pixel does not promote a feature into the Identity Contract. Stable hair, mane, ruff, facial hair, and regional covering construction already owned by identity remain stable and must not be discarded as temporary grooming.

Audit scene state through attention and awareness; facial, vocal, gestural, postural, action, contact, and support articulation; physical, physiological, emotional, and surface condition; current appearance and presentation; possession, inventory, equipment, and prop bindings; relationship state, social stance, and viewer awareness; environmental response; and current era, form, transformation, or appearance state.

Use this model-facing boundary, replacing placeholders with reviewed target values:

```text
Image 1 supplies permanent character identity only. Do not transfer its scene-specific character state or source-render context. Scene-specific character state means every visible or performance-relevant property that can change while the subject remains the same character, across attention and performance; articulation, pose, action, contact, and support; physical, physiological, emotional, and surface condition; appearance and presentation; possessions and equipment; relationships and viewer awareness; environmental response; and resolved current form or appearance. Reconstruct all of those domains from the target scene and the following target-state requirements: <affirmative target state>. Preserve only these permanent identity traits from Image 1: <identity traits>.
```

Scope every source through the canonical Reference Use Plan. Identity evidence supplies only named permanent identity. Scene and structural evidence supplies only its declared composition, support, contact, prop, camera, environment, light, or other influence. Reject source character identity and source-specific text or insignia from nonidentity references. Review identity drift and source-state leakage as separate failure classes.

A short `use this character in this scene` instruction may produce a plausible composite; it is not a continuity-safe substitute for the complete boundary.

## Reference Selection and materialization

A finalized Reference Selection is the state-eligibility boundary; the Reference Use Plan is semantic and technical authority. A planned item is eligible only when the selection contains the same committed source and includes its intended influence. The plan cannot bypass story range, graph hashes, required-visible-feature rules, unsupported or occluded state, unsupported assumptions, or state eligibility.

State-aware preparation has two exclusive paths:

- If the finalized selection contains any `pack-artifact`, build and review one Reference Use Plan, then execute it with `reference_runtime.py execute --reference-selection`.
- If the selection contains only request-supplied files, use `prepare_generation_references.py --state-selection-file`. That path emits a plan-null prepared set and rejects every `pack-artifact` row.

Do not combine pack-backed and plan-null preparation or fabricate pack coordinates for a supplied file. Preserve each binding's `binding_id`, `covers`, `intended_influence`, `review_dimensions`, `unsupported_or_occluded_state`, and `unsupported_assumptions` in the prepared row.

Build a finalized selection only after reviewing the plan and confirming that every exact planned source and influence exists in the bindings:

```bash
python scripts/select_state_references.py \
  --bindings state-aware-reference-bindings.json \
  --selection-id <selection-id> \
  --identity-contract identity-contract.json \
  --state-snapshot state-snapshot.json \
  --story-order <story-order> \
  --required-feature <required-visible-feature> \
  --out reference-selection.json \
  --state-file PACK_STATE_JSON \
  --cache-dir CATALOG_CACHE \
  --managed-root MANAGED_PACKS \
  --pack-root ADDITIONAL_PACK_ROOT
```

Pass the same state selection and pack runtime into reference materialization and the state-aware Generation Package builder. A change to authority, source, influence, state graph, or visible requirement requires a newly reviewed plan and selection.

## Conditional state authorities

Read only the authority activated by the work:

- stable identity coverage: [Character Identity Contract](../character-identity-contract.md); detailed species/individual layering: [Morphology and Species Contracts](../morphology-and-species-contracts.md);
- temporal events and snapshot semantics: [State Event Ledger](../state-event-ledger.md); snapshot-to-prompt execution: [State-Aware Prompt Workflow](../state-aware-prompt-workflow.md); artifact discovery: [State Protocol Schema Index](../state-protocol-schema-index.md);
- state and adoption records: [Shared State Protocol](../state-protocol.md). Before compilation, validate every incoming `shot-request` with `python scripts/shot_request.py <request.json>` and its required binding arguments;
- view coverage, candidate generation, or adoption: [Reference Bundle Workflow](../reference-bundle-workflow.md);
- observed-render drift ownership and repair: [State Write-back Routing](../state-writeback-routing.md);
- identity testing on a documented video target: [Video-model Identity Evaluation Battery](../video-model-identity-evaluation-battery.md).

## Optional consumer boundary

Local state-aware authoring is complete without exchange. A supplied artifact is an optional input validated under the public contract; no external authoring process or application is presumed.

At the optional boundary, exchange explicit public records. The same workspace
may author every record itself; no external authoring role is required. Receiving
a record never adopts a design, updates state, obtains media or sends a model job.

For a declared profile, publish the exact payload with its public declaration:

```bash
python scripts/build_interchange_envelope.py \
  --profile shot-request --payload-type shot-request --payload PROJECT/request.json \
  --payload-id REQUEST_ID --out PROJECT/exchange/request
python scripts/validate_integration.py \
  --envelope PROJECT/received/request/envelope.json \
  --declaration PROJECT/received/request/declaration.json \
  --payload-root PROJECT/received/request --direction consumes
```

`REQUEST_ID` must equal the actual request's `request_id`. The output directory
is new and contains `artifact.json`, `declaration.json` and `envelope.json`.
Required feature support, declared identity, exact bytes and the public payload
schema are checked before use. The author separately selects the received record
and resolves local state, reference media and production requirements.

For the full set of public types, use [Protocol Exchange](../protocol-exchange.md).

## Grounded multi-unit coordination

Use [World Realization](world-realization.md) to coordinate source-pinned units across presentation
order, independent story targets and explicit state-dependent reference queries. It calls the
existing `state_protocol.resolve_world`; snapshots remain rebuildable and events remain the owner
of mutations. Its author-facing bundle is not a new Generation Package. Select and review the
recipient view, then execute the normal projection, reference, prompt and generation contracts.

Keep entity identity, a resolved state, an asset's exact bytes, a role-specific lookup key and a
portrayal identity distinct. Query equality neither adopts a reference nor proves model-level
identity. A generated first appearance remains a candidate. Review expected versus observed
output with the [write-back route](../state-writeback-routing.md), preserving intentional omissions,
contrasts and departures under actual creator decisions.


## Artifact evidence and completion

For a saved deliverable, continue through [Production Execution](production-execution.md). Preserve this document's own interpretation, retrieval, approval and adoption boundaries. Prepare the exact inputs, capture the real output, bind review and selection to it, then complete and close the work task. `scripts/production_workflow.py status`, `impact` and `resume` recheck dependencies and artifact bytes. A progress checkbox, a search hit or a newly created image is not production completion or canonical adoption.
