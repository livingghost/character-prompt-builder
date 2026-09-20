# State Event Ledger and Deterministic Snapshot Resolution

## Canonical State Event Ledger

The canonical ledger is an append-only `state/events.jsonl`. The resolver applies approved events from the selected ledger. World and character snapshots are derived, rebuildable artifacts. A manually maintained current-state copy is not canonical.

Every resolution names an explicit timeline, integer story order, story time, and target `scene_context_id`. The target scene ID is recorded in both world and character snapshots.

## Event changes

An event change has exactly one of two shapes:

- a state mutation using `set`, `replace`, `merge`, `remove`, `append`, or `increment`;
- a process lifecycle action using `interrupt-process` or `restart-process` and an exact `process_id`.

Lifecycle actions do not carry state-mutation persistence or a value. Every change names an entity type, entity ID, and JSON Pointer path. The event `targets` list must include every changed entity. Evaluate every precondition against the unchanged input state before applying any change; a failed precondition rejects the event without partial mutation. A multi-entity event must set `atomic: true`, and every approved event requires evidence.

A temporary state requires an expiry order, a clear event, or a process.

Use `templates/state/state-event.template.json` for a simple scene-local mutation. Use `templates/state/state-event-temporary-until-cleared.template.json` for the complete temporary-state relationship: preconditions, per-change `effective_until_order`, `clear_event_id`, and the required later clearing mutation on the same timeline, entity, and path.

Use entity-relative paths such as:

```text
/physical_state/left_ear_tip
/wardrobe_state/layers
/emotional_state/expressed_state
/inventory_state/items
```

World snapshots contain character, relationship, environment, prop, and world buckets.

## Story order, expiry, clearing, and supersession

`effective_order` belongs to the event. `effective_until_order` belongs to an individual state-mutation change and is exclusive: the change no longer applies at that order. This permits different changes in one atomic event to have different lifetimes.

A `clear_event_id` is also per change. It must identify an approved event on the same timeline, at a strictly later story order, containing a state mutation for the same entity and path. At and after that clearing event, the original change is inactive.

An approved event may supersede earlier events with `supersedes_event_ids`. Supersession is future-filtered. A snapshot before the superseding event still contains the earlier event; a snapshot at or after the superseding event does not. References to unknown events, another timeline, the same event, or an event at the same or a later order are invalid.

## Persistence semantics

- `scene-local` requires the event to declare `scene_context_id`. It applies only when that ID exactly matches the resolver target. It never relies on story-time text or scene inference.
- `temporary-until-cleared` requires a per-change `clear_event_id`, `effective_until_order`, or both.
- `decaying` and `progressive` require a linked State Process for the same timeline, entity, path, and event order.
- `persistent-until-superseded`, `era-level`, and `form-level` remain active until an authored superseding event or contract transition replaces them. They do not carry an expiry or clear reference.

## State processes

A process contains authored milestones at unique, ascending, non-negative integer offsets and begins at offset zero. A linked `decaying` or `progressive` mutation uses `set` or `replace`; the process starts at that event order, and its offset-zero state equals the initiating value.

The resolver applies milestones only at their exact integer story orders. It does not interpolate, round, estimate, or derive intermediate states. The most recent applicable milestone persists until an explicit same-path event, clear, expiry of the linked change, or a lifecycle rule changes the result. `effective_until_order` on a process prevents later milestones from firing; it does not erase the last milestone already reached.

Interruption policies are deterministic:

- `supersedable-by-event`: the first strictly later approved state mutation on the same entity and path cancels milestones at that order and all later milestones.
- `fixed`: same-path events do not stop future milestones. Lifecycle actions targeting a fixed process are rejected.
- `restartable`: only an explicit `interrupt-process` action stops the current epoch. It never resumes automatically. An explicit `restart-process` is valid only after interruption and starts a fresh epoch at the restart event order, replaying authored offsets from zero.

Restarted milestone IDs are epoch-qualified, so an initial milestone and the same offset after restart remain distinguishable in snapshot lineage.

## Same-order precedence

At one story order, lifecycle effects are resolved first, process milestones second, and state mutations last. IDs and authored change indexes break remaining ties. Consequently, an interrupt suppresses a milestone at the same order, a restart may emit its offset-zero milestone at that order, and an authored state mutation wins over a milestone at that same order.

## Validation boundary

Resolution rejects duplicate event IDs, duplicate process IDs, missing cross-references, timeline mismatches, entity/path mismatches, invalid order relationships, multiple initiating changes for one process, lifecycle actions against a non-restartable process, restart without an inactive epoch, and approved changes linked to non-approved records.

The command-line resolver requires the target scene explicitly:

```bash
python scripts/state_protocol.py resolve-world \
  --base-state world-state-base.json \
  --events events.jsonl \
  --processes processes.json \
  --timeline main \
  --scene-context-id SC-EP03-01 \
  --story-order 25 \
  --story-time story:EP03-SC01 \
  --snapshot-id WORLD-main-25 \
  --out world-state-snapshot.json
```

## Domain notes

### Emotional state

Keep felt, expressed, masked, and physiological state separate. A character may feel fear, display professional calm, and reveal tension only through shallow breath and one hand.

### Relationship state

Use directional relationship records for trust, affinity, intimacy, conflict, authority, obligation, contact boundaries, public mask, private behavior, and shared knowledge. Relationship state becomes scene blocking, gaze, distance, contact initiation, and prop-transfer direction only through a scene projection.

### Environment

Season, temperature, humidity, wind, precipitation, water exposure, light, approved locale or culture contracts, dress norms, and surface conditions may produce an **appearance adaptation proposal**. The proposal remains unapproved until a human accepts it; environment data never invents cultural dress automatically.

### Time jumps

A past scene is resolved by applying only the events effective at that story order. A future time jump does not automatically invent gray hair, wrinkles, or body changes. Approved long-term changes belong in an Era Contract.

### Background processes

Healing, drying, fatigue recovery, hair growth, curse progression, or another continuous process uses named milestones. New events may supersede or interrupt the process according to its policy.

## Source-grounded coordination without another ledger

[World Realization](runtime/world-realization.md) adds local source pinning and independent target
resolution around this ledger. Every consequential base assignment needs a scoped basis as well as
every approved mutation/process. The local plan's base provenance covers explicit state pointers;
event/process evidence stays inside the authoritative records. In that workflow each evidence
object names `source_id`, `locator` and `basis`, resolving to a pinned local source.

A locator can point to original material or an actual creator decision. It is not proof that an
inference is true or adopted. Record uncertainty and interpretation separately; never treat a
renderer's accidental state as an approved mutation. Planned chronology and disclosure order are
different, and editorial revisions need not be events experienced by anyone.

The helper compares only named boundary fields and exports only selected recipient fields. Its
snapshots use this resolver's persistence, process and scene semantics, including the aggregate
`world` bucket. It does not infer continuous values, auto-approve a source or silently mutate a
canonical base. Source edits require rebuilding and reviewing dependent outputs.
