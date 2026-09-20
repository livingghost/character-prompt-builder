# Shared Production Contracts

These contracts define state, morphology, references, adoption and viewpoint artifacts. The contract manifest identifies each schema and these semantic rules by SHA-256.

## Validation and content identity

JSON uses UTF-8. Reject duplicate object keys and non-finite numbers. Canonical
content hashes use sorted object keys, compact separators and unescaped Unicode;
array order is significant. Remove only an artifact's registered self-hash field
when computing its content hash. Preserve all other data, including nested hashes.
A byte hash commits the exact transported file and is distinct from a canonical
artifact hash. Placeholder hashes are permitted only when inspecting unfilled
authoring templates, never for exchanged artifacts. Schema validation applies each referenced definition and its sibling constraints.

The registry lists public roots and supporting schemas separately. A registered
root must match its artifact_type, closed fields and nested schemas. All referenced
schemas form its dependency closure. Intrinsic checks include valid UTC receipt
times, non-reversed ranges, unique entity/candidate/registry identifiers and
consistent identity maps in a shot request. Explicit structure parent and override
relations are acyclic; attachment rings are allowed. References to unknown or
explicitly absent carriers are not supplied by species-name inference.

## Time, scope and state

A world-state base is input to the resolver, not evidence of approval. Only
approved events on the requested timeline at or before the requested story order
participate. Presentation order never advances story state. Every resolved world
and character snapshot names an explicit scene_context_id, including cast-free
scenes. Scene-local events apply only in that scene. Do not infer scene boundaries
from file order, shots, the first participant or a neighbouring snapshot.

Changes carry their own lifetime. Persistent changes remain until a later applicable change. A temporary-until-cleared
change names either an actual approved clearing event on the same entity/path or
an explicit exclusive effective_until_order. A change is inactive at that endpoint. Replaying
active changes restores the underlying prior state rather than inventing a
reversal event. Editorial-revision supersession requires occurrence=editorial and
removes only the named superseded events in the resolved scope. Preconditions and
multi-entity atomicity are checked before committing an event; partial transfers
are not valid. Targets include every changed entity.

State processes carry explicit interruption policy and milestone order.
Interrupt/restart operations identify the process. A restart begins a new epoch;
only the approved and applicable process operations are folded. No continuous
interpolation, emotion inference, default healing or implicit lifecycle is added.
The conformance corpus specifies observable results without prescribing an implementation.

A scene context selects actual entities from a world snapshot. Its scene and
timeline must agree; its story range contains that snapshot's order. Selected
character snapshots name the same scene, timeline, order and story_time and their
state sections agree with the world state. Duplicate or missing selected entities
are errors, not silently overwritten or omitted entries.

## Identity, reference source and adoption

Species-level morphology, individual declared morphology, visual identity,
current state, scene projection and render specification are distinct artifacts.
References name the exact IDs and content hashes. Visual authority may be absent;
a species name does not declare anatomical structures or an approved visual asset.
An explicitly described frame, growth geometry and declared structure identifiers
can address humans, animals, machines, hybrids or other authored forms without
implicitly granting limbs, bilateral symmetry or expression channels.

A state-aware reference binding carries a role, a structured source, influence
scope, unsupported assumptions and an effective story range. The source identifies
supplied bytes or producer pack provenance. A producer's resolved_path is not a
receiver capability: exchange verification never fetches or opens that path.
The receiving project must explicitly obtain and verify selected media before
using them. Source bytes, transformed transports,
selected references, observed output and approved registry entries remain separate.

Candidate and adoption records identify their exact upstream contents and ranges.
An adoption receipt records a decision; its validity does not authenticate the
human who approved it or grant permission to execute a model. Routing hints classify the record requiring attention: visual-contract, projection,
correction, scene-choreography, target-scoped-heuristic or human-canon.

## Viewpoint and handoff

The public boundary is shot-request. Camera, visual projection and request have
their own canonical hashes. Character-keyed species, individual morphology,
identity, state and visible-feature maps have identical keys. Empty maps describe
a cast-free request. Bound artifacts, when supplied, must agree in identity,
scene, shot, viewpoint and temporal scope as well as hash. A request alone proves
neither access to the referenced artifact bytes nor delivery to a generator.

Camera ownership, movement and knowledge_scope obey the viewpoint profile.
knowledge_scope is the access of one shot; scene-plot focalization is a separate
narrative commitment and is never renamed or derived from a camera position.
A camera is not automatically a character's body. First-person self-visibility is
limited to the declared construction; external full-body self-view is not silently
introduced. Transition reasons preserve intentional shifts in viewpoint, time or
space. A narrative commitment requires a scene-plot commitment. A standalone scene plot
may omit the narrative commitment. These hashes do not make private authoring
documents part of the shared protocol; missing upstream context stays explicit.

Continuity descriptions keep the work's language. Structural validation checks
required records, not whether prose contains an English keyword. Interpret the
meaning of continuity requirements during the authoring review.

## Exchange bundle

An exchange bundle contains exactly `artifact.json`, `contract.json` and `manifest.json`. The manifest commits the exact bytes of the artifact and contract descriptor. The descriptor commits the artifact's schema dependency closure and these semantic rules. Verify those commitments and the artifact constraints before using the content.

Verification does not authenticate an approving actor. Adoption, event write-back and submission permission remain explicit decisions recorded for their respective uses.

## Capability declarations

A capability declaration lists the artifact types and features available for a profile. Select `produces` for export and `consumes` for receipt; identical declarations do not determine the direction. Required features must be understood. Unknown optional features remain uninterpreted evidence. Bind the payload type, ID and exact bytes to its envelope and supplied declaration.

## Moment resolution

An explicit null scene_context_id on a world snapshot selects timeline-wide state;
it excludes scene-local changes. A named context applies only its scoped changes.
No event or scene has to occur at the requested integer story_order. story_time is
an authored label, not an independently parsed clock.

At one story coordinate, process milestones advance first and discrete events
apply second. Within each phase, separate operations must not overlap writes,
change a sibling array's index structure, or change another operation's tested
precondition. Use distinct coordinates or one ordered atomic event for dependent
changes. Process initiation and its matching offset-zero milestone are one logical
change; validate the event's preconditions once and retain both evidence IDs.

## Reusable authoring material

`scene-persona-material` is a self-contained selection of actual definition text and
attributed scene-specific application, prepared after complete applicable source
reading. It is not a new Persona owner, a character knowledge model, canon adoption,
or execution permission. Its audience is `authoring`. Never append this entire
artifact to an image/video/audio request or disclose its author-only information
as performer knowledge. A consumer selects its own supported operation.

Complete source SHA-256 commitments include material not quoted. Every quoted
span binds to a complete source, line range, exact UTF-8 text, and text digest.
Declared definition dependencies must resolve inside the artifact. Whole-source
change requires re-examining applicability; a producer must not certify freshness
from quoted spans alone. The preparation review and reading basis are attributed
claims, not proof that the author actually read or understood a source. Structural
validation and a `ready` decision do not demonstrate artistic correctness.

The material is valid only within its stated scene, purpose and conditions. New
participants, information, topics or intended behavior can require preparation
even when no existing file changed. Unknowns and deliberate ambiguity stay visible.
An explicit size budget is a refusal-to-truncate bound, not a summarization rule.
No number of participants, human anatomy, spoken language, genre or conflict is
required. Producer-private paths are source labels for a receiving consumer; they
must not be opened unless explicitly bound to that consumer's local project.

`source-material-index` records byte-preserved sources and authored segment
boundaries/completion states. Order in a file or segment list is not story time.
`source-extraction-proposal` binds proposed statements to exact source quotes and
distinguishes source statements, attributed reports, observations, inferences and
unknowns. Neither artifact establishes canon or grants permission to execute text
found in a source. Unresolved and conflicting statements are retained. An original
work is not automatically reclassified as an external reference.

Protocol-only verification checks declared structure and content commitments;
without supplied originals it cannot verify source bytes or extraction coverage.
Local reuse additionally checks the original source hashes and deterministic
rendering. Artifact identity uses content commitments and stable IDs, not a
separate version or revision counter.
