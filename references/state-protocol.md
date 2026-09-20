# Shared State Protocol

## Purpose

This protocol represents enduring identity, approved events and time-varying state. Use the applicable design and event records to derive snapshots and shot-visible projections. Keep exact submissions, observations and adoption decisions linked to the artifacts they concern.

Species and individual morphology define the declared construction. Events may change only approved mutable paths; permanent structural changes need the appropriate form or identity lineage. A `shot-request` binds the applicable contracts and visible obligations without rewriting them.

The protocol preserves four different truths:

1. **Identity**: who the character is across time.
2. **Canonical state**: what is true at one story time.
3. **Visual state projection**: what the current shot should visibly express.
4. **Observed render state**: what an actual returned image or video contains.

A render never becomes canon automatically.

## Canonical flow

```text
Character Identity Contract
+ optional Era / Form / Appearance contracts
+ approved State Event Ledger
→ World State Snapshot
→ Character State Snapshot
+ Scene Context Snapshot
→ Visual State Projection
→ Asset Render Specification
+ State Lineage

State-aware Reference Bindings
+ identity / era / appearance / state / story-time inputs
→ finalized Reference Selection eligibility

explicit canonical record uses
+ active pack-linked visual evidence
→ Reference Use Plan
+ finalized Reference Selection eligibility when state-aware
→ Prepared Reference Set

Asset Render Specification
+ State Lineage
+ Production Specification
+ Prepared Reference Set
→ Generation Package
→ Observed Render State / Drift Observation
```

Reference Selection and Reference Use Plan have different, one-way responsibilities. Reference Selection proves whether a committed binding source and intended influence are eligible at the resolved story point. Reference Use Plan is the sole activation, authority, artifact, precedence, transport-mode, and surface-lighting plan. Prepared Reference Set is the sole prepared-reference truth after the plan has been intersected with any required state eligibility.

## Record responsibilities

| Decision or evidence | Record |
|---|---|
| Enduring identity and approved variations | Identity, Era, Form, Appearance and Character State Schema contracts |
| What an inspected reference supports | Visual authority, semantic regions and visual-evidence bundles, with approval and effective range |
| Approved changes and story time | Append-only State Event Ledger and State Processes |
| Current resolved state | Derived world and character snapshots |
| Scene-visible obligations | Visual State Projection and Asset Render Specification |
| Render plan and exact generation input | Production Specification and Generation Package |
| Reference eligibility at a story point | Reference Selection |
| Activated evidence, precedence and lighting intent | Reference Use Plan and Surface and Lighting Plan |
| Prepared files and forwarding scope | Prepared Reference Set and verified generation input |
| Selected media and its lineage | Asset Registry and Adoption Receipt |
| Observed result and discrepancy | Observed Render State and Drift Observation |
| Reusable drawing repairs | Correction presets |

Create or revise these records under the relevant authoring, approval and observation procedures. Validation checks the declared content; it does not supply a missing author decision or media inspection.

## Time and event semantics

Events distinguish:

- `effective_from`: when the change is true in the story world;
- `recorded_at`: when production records it;
- `disclosed_at`: when the viewer or another subject learns it;
- per-change `effective_until_order`: the exclusive story order at which that individual change stops applying;
- per-change `clear_event_id`: a strictly later approved same-timeline, same-entity, same-path event that clears that individual change.

Events may occur on screen, off screen, or as editorial revisions. Approved events are applied in story order. Supersession is future-filtered, so a later editorial event cannot alter a snapshot resolved before its own effective order. Multiple-entity transfers use `atomic: true`, so a prop cannot remain with both characters after a transfer.

## Persistence

State changes declare one of:

- `scene-local`
- `temporary-until-cleared`
- `decaying`
- `progressive`
- `persistent-until-superseded`
- `era-level`
- `form-level`

`scene-local` changes bind an explicit event `scene_context_id` and apply only to an exact resolver target-scene match. `decaying` and `progressive` changes bind a State Process with the same timeline, entity, path, and start order.

State Process milestones use exact non-negative integer offsets beginning at zero. The resolver emits only authored milestone states, performs no interpolation or rounding, and preserves the latest applicable milestone. `supersedable-by-event` cancels future milestones at the first strictly later approved same-path mutation. `fixed` rejects lifecycle actions. `restartable` stops only on explicit interruption, never auto-resumes, and starts a fresh epoch only on explicit restart. At one story order, lifecycle effects precede milestones, and state mutations follow milestones.

## Prompt regeneration

A prompt is regenerated when a scene-visible semantic input changes: identity/era/form, approved appearance variant, visible physical state, wardrobe layers, held props, expressed emotion, relationship blocking, environmental body response, camera, crop, light, target, the Reference Selection eligibility result, any selected record use or intended influence, visual authority or precedence, Surface and Lighting Plan, transport mode, or the render specification.

Purely internal knowledge that has no visible or performance consequence updates story state but does not force a new image prompt.

## Hash model

Shared state artifacts use canonical JSON and SHA-256. The State Lineage binds:

```text
identity contract
optional era/form/appearance contract
state snapshot
scene context
visual state projection
asset render specification
```

The Reference Selection seals its identity, era, appearance, and State Snapshot hashes, story order, required state features, ordered eligible binding rows, unresolved requirements, and `selection_sha256`. It is an eligibility hash, not an activation hash.

The Reference Use Plan seals the non-empty ordered `selected_records` decisions, exact active pack-linked `reference_items`, canonical per-item authority and preamble, the embedded Surface and Lighting Plan, `surface_lighting_plan_sha256`, any structured `zero_reference_reason`, and `reference_use_plan_sha256`. Each selected record row contains exactly `record_id` and one intended influence from `identity`, `pose-camera`, `outfit`, `surface-finish`, `lighting`, `environment`, `prop-accessory`, or `local-color`.

State-aware execution requires exact source equality between each activated plan item and one eligible Reference Selection row, and it requires the plan item's intended influence to occur in that row's `intended_influence` array. The selection may narrow eligibility; it cannot broaden the plan's canonical authority. Each plan item's `controls` are the intersection of intended influence and technical evidence role. Its `must_not_control` excludes scene-conditioned presentation outside the declared intended influence and all influence- and technical-role-specific prohibited dimensions. Stable hair, mane, fur-tuft, body-fur distribution, and grooming topology can be identity; gaze, expression, mouth state, perspiration, outfit, transient state, and wind-, wetness-, motion-, or scene-driven displacement are not identity authority.

The Prepared Reference Set embeds the finalized selection and hash when state-aware, the Reference Use Plan and both plan hashes when record evidence is active, canonical reference preamble, exact prompt-artifact copies, ordered model-facing reference rows, optional single-board metadata, an explicit zero-reference reason when applicable, and `prepared_reference_set_sha256`. State-scoped rows preserve binding scope and unsupported-state declarations as well as source, exact transport, derivation, and plan-derived authority. Its portable carrier paths are relative to the package containing it. Active-pack source paths remain committed provenance and must still resolve to the same active pack, release, asset, artifact, media type, and bytes.

The Generation Package hashes the Prepared Reference Set together with the State Lineage, reviewed prompt transports, negative text, Production Specification, model parameters, and target model. Its `prepared_reference_set_sha256` appears at package and generation-contract level and is incorporated into `generation_input_sha256`. The package builder copies portable carriers into `<out-stem>.references/` beside the output JSON, rebases only their paths, reseals the Prepared Reference Set, seals the generation input, and publishes the JSON and companion directory transactionally. `generation_input_sha256` changes when text, parameters, lineage, selection, plan, authority, reference order, scope, source or transport metadata, derivation, carrier path, hash, or bytes change. Any later mutation fails verification.

### Approval hashes, and the three conventions

Three hash conventions run through this protocol, and a reader who assumes one applies everywhere
will compute the wrong digest.

| Convention | What is hashed | Where it applies |
|---|---|---|
| `content_sha256` | the document with its `approved` block removed, canonical JSON | prompt plot, scene plot and narrative |
| `artifact_hash` | the document with its own self-hash field removed | shared-state artifacts, whose self-hash field is named per type |
| `viewpoint_hash` | the document with its own self-hash field removed, per the viewpoint table | shot camera specification, shot visual projection, shot-request |

The second and third differ only in which field each artifact type calls its own; the first differs in
kind, because an approval is a claim about the content that was approved and not about the document
that carries the claim.

An approval that names only a time is a claim about a document that can change after the claim.
`content_sha256` binds it to the bytes, so a plot edited after approval is refused rather than
silently re-approved. The prompt plot travels whole inside the Generation Package, its `approved`
block and the `source` block below included, and `plot_sha256` is the digest of that whole document,
so `generation_input_sha256` covers both and any later mutation fails verification. The settled retrieval
record travels in the Generation Package, bound to the authored `composition_prompt` and approved
plot content. Its `retrieval_record_sha256` is committed in the generation contract and input hash;
all builders and verification reject missing, unsettled, or mismatched records. Prompt-artifact
packages also retain the record with a manifest hash.

### Where a prompt plot came from

A prompt plot may carry `source`: the upstream artifact's `artifact_type`, its `id`, the
`content_sha256` it was approved under, and optionally the `shot_id` of the shot it covers.

The field is optional, and a prompt plot does not have to come from an upstream artifact at all. A
plot written from a brief has no source, and the brief is its root: that is the truth for a single
image and nothing about it changes. A plot written from an approved scene plot names it, and then one
frame carries one approval chain instead of two that do not mention each other. `source` sits inside
the plot, so the plot's own approval covers it: a plot re-pointed at a different upstream artifact
after approval is refused.

## The arriving shot-request

A `shot-request` may arrive under the sender's current viewpoint protocol. The request binds the scene and shot IDs, viewpoint profile, visible identity and state obligations, selected reference candidates, output framing, and hashes for the scene context, shot camera specification, and shot visual projection. It may also carry `scene_plot_sha256`, the approved scene plot the shot was planned in, and beside it `narrative_sha256`, the narrative whose chapter and arcs that scene belongs to. Both are optional, because a request may come from a project that has no scene plot; where `scene_plot_sha256` is present, the prompt plot written from it names the same artifact and hash as its `source`. Where it is absent, `scripts/shot_request.py` reports that as unmeasured rather than passing in silence, because a link nobody supplied is an unanswered question and not an answered one.

The request and any supplied bound artifacts are validated with:

```bash
python scripts/shot_request.py shot-request.json \
  --identity C01=character-identity-contract.json \
  --state C01=state-snapshot-C01.json \
  --scene-context scene-context-snapshot.json \
  --camera-spec shot-camera-spec.json \
  --shot-projection shot-visual-projection.json
```

The request is a production boundary, not an art direction. Its selected reference candidates are candidates, not activated inputs. After validation, the agent still forms the coherent visual direction, resolves the requested visible obligations, selects compatible production knowledge, declares explicit canonical record uses and intended influences, builds the one Reference Use Plan, reconciles it with state eligibility, and writes the final prompt or boundary-frame package. Camera ownership and narrative focalization remain the request's evidence; stable character identity remains contract data.

## Runtime policy

Runtime artifacts are accepted by current structural schemas, semantic identifiers, content hashes, active-pack checks, and lineage checks. Internal protocol artifacts carry no independent version field, and only the documented boundary is owned here.

Reference materialization revalidates every selected record, active pack and release, linked asset and artifact, source path, media type, and source SHA-256. A state-aware plan is also checked against its finalized Reference Selection and rejects unresolved required state. Unresolved Surface and Lighting Plan decisions may remain in `prompt-artifacts` or `svg-bundle` review packages, but they block `multi-image` and `single-board` materialization. Prompt-package modes cannot enter a Generation Package or be forwarded to a model.

The Generation Package verifier resolves package-relative reference carriers against the Generation Package directory, rehashes them, revalidates active-pack provenance, confirms the Prepared Reference Set and generation hashes, and emits the only host-authorized forwarding object. The host sends the verifier's effective prompt, selected negative transport, parameters, and ordered reference rows containing only `role`, verifier-resolved `resolved_path`, `media_type`, and `sha256`. The returned `reference_preamble` is an audit field already incorporated into the effective prompt and must not be prepended again. `multi-image` forwards each verified role transport. `single-board` forwards one `composite-reference-board`; its individual panel source and transport hashes stay sealed inside the Prepared Reference Set. A host must not reconstruct references from chat, forward source files or prompt-artifact copies, rerasterize, reorder, add, omit, or substitute inputs.


## Optional public data exchange

A project may author visual contracts, chronology, scene plans and adoption
records locally. Exchange is a separate, optional path for explicit public data.
It neither divides authoring responsibilities between applications nor discovers
software. Private catalogs, persona stores and execution records stay local.

The capability declaration is `config/integration-capabilities.json`. For receiving
an envelope, supply its actual public declaration and payload bytes. For a
schema-bound bundle, validate the installed schema closure and semantic commitment.
Unknown required features stop interpretation; optional evidence is preserved only
under the declared policy. See [Protocol Exchange](protocol-exchange.md).

## Visual authority and derived evidence handoff

A source-derived guide is evidence, not canon. Extraction, safe static SVG validation, semantic region maps, provenance and disposable runtime attachment compilation are settled here. The local adoption owner records the selected bundle ID and hashes, its story or appearance scope, and whether it is `valid`, `partially-valid`, `stale`, or `invalid`. Receipt of evidence is not adoption. An exported record refers to exact source bytes; it does not authorize silently editing or adopting them.

A bundle declares one scope: identity, appearance state, shot geometry, or identity and shot. It also declares locked and free dimensions. Approved changes to form, aging, wounds, grooming, wardrobe, inventory, accessory transfer, or shot geometry can invalidate some or all of a bundle. The old guide is never silently reused beyond its approved scope.

The State Lineage, Asset Render Specification, and Reference Bundle Plan may carry `visual_authority_sha256` and `visual_evidence_bundle_sha256`. Null values are valid when the character is text-only or the current request does not use a visual bundle.
