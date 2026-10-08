# Story Flow, timeline and ledger inspection

Read the development of a story, compare passages and inspect their recorded consequences.
Graph is the opening view and shows branches and revisions as connected cards.
Flow reads the story as ordered passages. Axis retains the event lanes and exact state inspection.
The author judges motivation, continuity, information gaps and the effect of a scene.
A structural check does not decide whether the story is convincing.

Ordinary narrative and scene files own story content. The world-state-base, event ledger
and State Processes own state. [State Event Ledger](../state-event-ledger.md) defines
state semantics. All three views use the same records and shared resolver results.

## Open the story view

```bash
python scripts/story_timeline.py --studio STUDIO
python scripts/studio.py sync --studio STUDIO
```

The default inputs are `state/world-state-base.json` and `state/events.jsonl`.
If present, `state/processes.json` supplies one State Process or an array of them.
The default output is `timeline.html` at the Studio root, with a small
`timeline.status.json` publication receipt beside it. Flow also discovers `narrative/narrative.json` and scene-plot JSON
files under `narrative/scenes/`, including subdirectories. A narrative-only Studio can
display its scenes before a state ledger exists. It creates no imaginary world base,
event, initial condition or resolved viewpoint. An empty scaffold alone does not activate it.

Use [the view template](../../templates/story-timeline-view.json) as
`state/timeline-view.json` to select other Studio-relative inputs, named viewpoints,
explicit scene artwork and evidence sources. Its
[schema](../../schemas/authoring/story-timeline-view.schema.json) validates the complete form.
Paths are literal local paths within this Studio. Symlinks and escaping paths are refused.

A named viewpoint follows this form. This is a synthetic example:

```json
{
  "view_id": "workshop-before",
  "label": "Before entering the workshop",
  "timeline_id": "main",
  "story_order": 20,
  "story_time": "chapter:2",
  "scene_context_id": "SC-workshop"
}
```

A null `scene_context_id` asks for shared state with scene-local changes excluded.
Without named viewpoints, the page shows the last declared event or process-milestone
coordinate per timeline, labelled `order:N`. This generated label is not an authored
story time, an inferred present, or a promise that later events do not exist.

For an additional explicit point, write a separate view:

```bash
python scripts/story_timeline.py --studio STUDIO \
  --timeline main --story-order 20 --story-time chapter:2 \
  --scene-context-id SC-workshop --out views/workshop.html
```

`--out` is Studio-relative and ends in `.html`. It replaces only a timeline-owned page.
An existing unrelated file is preserved. `studio.py sync` rebuilds the default page
from the saved configuration; ad-hoc CLI selections are not silently saved as canon.
Put recurring viewpoints in `state/timeline-view.json`.


## Read the story without authoring a diagram

Flow is generated whenever the normal story projection runs. The agent records
story decisions in the ordinary narrative, scene and event sources, then runs
`studio.py sync` after those writes. The user does not maintain a second synopsis,
node table, edge file or Flow-specific form. Drafts remain visibly unapproved.

The readable cards quote the scene's proposition, participants, setting, beats and
consequences. Open a passage to read its full account, exchanges, preserved conditions
and source. Events without a scene show their recorded notes and changes. A missing
narrative account is marked missing instead of being completed from a model or keywords.
State-event notes can hold the account the agent already records for that event.

For example, a synthetic source may say "Mara distrusts Ivo" before another says
"Mara gives Ivo the only key." Pin the first passage and open the second. Compare
the actual actions, who knows what, and the stated consequences. The page does not
decide whether the missing explanation is a flaw, a deliberate mystery or a later reveal.

Two reading orders remain distinct:

- Declared presentation follows narrative chapter numbers and each scene's order.
  A flashback remains where the author presents it.
- Story order follows exact event positions and the scene's explicitly referenced
  scene-context-snapshot. No coordinate is inferred from chapter order, a filename,
  a similar scene ID or an audience disclosure label.

A scene joins an event only through its `setting.scene_context`, the committed
snapshot's timeline/scene identity, and its declared interval. Unassociated events
remain visible on separate chronological tracks. Unplaced scene sources are shown
without an invented story position. Equal positions are peers, not forced causal
steps. Separate timelines do not acquire inferred branch points or cross-timeline edges.

Flow arrows show reading order. Its cause and revision buttons navigate to the exact
record. Graph draws those explicit relationships as arrows between cards. In the open `cause` object, `type: "event"` identifies a literal
event-ID reference in the same timeline. Other cause types remain recorded text;
even matching prose is not promoted into an event link. Missing or ambiguous explicit
references get source notices. Cyclic references cannot trap a recursive layout.
A revision replaces the earlier event as a whole according to the existing resolver,
not as an inferred partial inheritance.

Open story threads to inspect the narrative's arcs, wants, needs, promises, questions
and knowledge. Statuses and chapter links are quoted as recorded. An open question
or unchanged relationship is not automatically a defect. More records can be expanded
without opening another data file. No acceptance or new story fact is written by browsing.

Pin any passage and compare another, including a passage outside the active filters.
The comparison says explicitly when a pinned source is outside those filters.
Previous/next move through the filtered sequence, and omitted intermediate positions
are counted. Switching Graph/Flow/Axis preserves filters, comparison pins and the selected resolver viewpoint.

The inspector distinguishes authored consequences from before/after values in a
stored resolver trace. Processes show their declared milestones; interruption and
restart effects come only from that resolver. Click the Axis inspector for the exact
state fields and their source operations. Flow does not replay state in JavaScript.

## See branches and revisions in Graph

The generated page opens on **Graph / branches**. The graph is created from
ordinary story records during the existing projection. It needs no second diagram,
new author form, extra command, graph service or downloaded JavaScript library.
`timeline.html#flow` and `timeline.html#axis` at the Studio root open the other modes.

Cards retain the existing scene, event and process identifiers. Selecting a card
opens the same passage inspector used by Flow. Pin one, open another and read their
accounts side by side. Related events remain visible even when Flow presents their
associated scene as the primary reading card.

Solid arrows run from a resolved `cause.type: "event"` reference to its recorded
result. Dashed revision arrows run from the new revision to the whole old event it
replaces. This direction is intentionally opposite to the old-to-new relation index
used by the Flow inspector. No relation or resolver meaning is changed.
Arrows appear only where a cause reference or a supersedes link is recorded.
Record the cause when an event's origin is known; without references the graph
shows ordered cards without links. Notes carry story facts about the recorded
change; decision history belongs in `evidence` sources, not in notes.

This is a synthetic four-event example:

```text
A (meeting) --cause--> B (reconciliation)
           --cause--> C (misunderstanding)
D (later revision) --revision--> B
```

Both cause arrows leave A visibly. The dashed arrow returns from D to B. An optional
synthetic example has D revise both B and C; both recorded references remain visible.
Create either example with:

```bash
python examples/story-flow/build_example.py --out /tmp/story-graph-demo --graph
python examples/story-flow/build_example.py --out /tmp/story-graph-merge --graph --merge
```

The x direction is increasing declared story order, not chapter presentation order.
Columns have equal spacing, not proportional duration. Parallel records at the same
position stack vertically. Four alternating barycentre sweeps reduce edge crossings
without changing a record's declared position. Separate timelines have separate lanes.
Unplaced scenes, incomplete event coordinates and chapter-only material stay outside
the time axis. No filename, similar name or chapter number supplies a missing position.

Use **Highlight a recorded state path** to find an entity's changes, then **Read path
records** for their exact sources. Sharing a path neither creates a causal edge nor
proves two changes conflict. Axis retains the resolver's before/after values at the
chosen viewpoint. The graph does not introduce another state replay.

Filters collapse connected hidden records into labelled placeholders at their real
positions. Their original cause/revision edges remain attached to those placeholders;
a hidden chain is never replaced by an invented direct relationship. Clicking the
placeholder opens its members, including their outside-filter status. A selected or
pinned record stays readable when later filters hide its card.

A directed loop receives a visible **Cycle cut** on a feedback edge. The exact edge
remains in the relationship list. The iterative walk terminates on long chains and
invalid cycles. This is a layout annotation, not a new contradiction verdict: combining
a legitimate cause with a later revision can itself form a display loop. Existing
ledger diagnostics still appear on their recorded nodes.

The overview draws at most 200 node symbols. Larger views group records only at the
same timeline/order; each group retains every member ID. If distinct positions still
exceed 200, use position windows. Click a group to read its members, 40 at a time.
**Focus selected passage** navigates to its window without resetting filters.

At most 800 edge groups are drawn in a window. Parallel references with identical
endpoints and kind share a counted line. Internal group links and links to other
windows or unplaced records are reported. The paged **Recorded relationships** list
retains every original edge, including cuts and lines beyond the drawing bound.
These limits bound the SVG, not the ledger. The HTML still contains the full projection.

Use zoom, **Fit width**, or keyboard scrolling to inspect the canvas. Browsing remains
read-only. With no explicit references the cards have no arrows; ordered position is
not presented as a causal chain. A missing explanation remains available for human
story review rather than being completed by the renderer.

The graph geometry is checked by `story_graph_smoke_test.py`. Python checks the
projection and inline assets; Node.js checks the graph algorithms without launching
a browser. Node.js is optional for these algorithm checks and is not a runtime HTML
dependency. A missing Node.js executable is reported as a skipped algorithm check.

## Inspect events and resolved state in Axis

The event lanes use actual `entity_type` values, with cards ordered by integer
`effective_order` inside each timeline. Filter by timeline, entity type, explicit
scene, recorded text, revisions or diagnostic presence. Cards are created a page
at a time; linked images load lazily. Multiple-entity events can appear in more
than one lane, retaining the same source event identity and line number.

Each card retains changes, preconditions, cause, evidence, persistence, occurrence,
canonical status, scene ID and supersession links. `effective_from`, `recorded_at`
and `disclosed_at` appear as distinct values. A late recording does not move an
old event to the end of story order. A scene-local card says which scene it applies
to; the display invents no start/end time or band width for that scene.

The selected-state pane displays a result from `temporal_state.resolve_world`.
Choose a stored resolver viewpoint rather than asking JavaScript to replay events.
Its fields link to actual before/after operation records and the base state.
A trace names the event or process milestone, its entity-relative change and its
absolute JSON Pointer. Container operations may affect several fields; inspect
the recorded before/after values rather than treating proximity as causation.

A record can be applied in the replay even if a later normal transition changes
its value. This is different from being replaced by an editorial revision.
Other labels distinguish future records, proposed/rejected records, expired or
cleared changes, partial application and another scene's local changes.

The page does not approve an interpretation or reconstruct missing evidence.
A failed resolver view has no snapshot and explicitly asserts no state.
Other independently resolved viewpoints remain labelled with their own coordinates.

## Inspect the ledger mechanically

```bash
python scripts/state_protocol.py validate-ledger \
  --base-state STUDIO/state/world-state-base.json \
  --events STUDIO/state/events.jsonl \
  --processes STUDIO/state/processes.json
python scripts/story_timeline.py --studio STUDIO --inspect
```

Omit `--processes` when no process file is authored. `validate` still validates an
individual artifact; `validate-ledger` adds complete-ledger and replay checks.
`--inspect` prints the projection JSON without publishing HTML.
Both return exit 1 when their inspection finds structural or state-resolution errors.
A successfully written HTML can contain ledger errors; its summary then says
`"status":"current","ledger_ok":false`. "Current" describes the projection's
inputs, not a successful resolution of every scene.

The existing schema and temporal validator own scene-local scope, target coverage,
process references, duplicate IDs, missing links and supersession order. The same
validator now reports locations and detects revision cycles iteratively.
The same resolver checks simultaneous writes, array structure changes and
interference with another event's preconditions. It also applies the existing
process-before-event phase precedence.

Normal evolution is not a contradiction. Different story orders can change the
same path without a supersedes link. Gaps in order numbers are allowed. Independent
simultaneous changes are allowed. The protocol rejects unordered interfering changes,
including competing writes that happen to declare equal values.
No rule compares free-form disclosure/effective labels as dates.

Inspection checks the full input structure, then named replay boundaries: last
declared coordinates, scene endpoints, simultaneous entity operations, preconditions,
revisions and temporary changes. Coverage and unresolved query counts are recorded.
An earlier failed operation blocks that query; the inspector does not skip it and
assert a later state. Authorial meaning, unstated time ranges and narrative causality
remain outside these mechanical checks.

## Bind scene artwork and evidence explicitly

`scene_artwork` maps a timeline and scene to the current accepted image in a named
Studio character's slot. It does not infer links from filenames, prompts, creation
times or the most recent generated image. A synthetic mapping is:

```json
{
  "timeline_id": "main",
  "scene_context_id": "SC-workshop",
  "character": "worker",
  "slot": "scene.workshop",
  "label": "Adopted workshop scene"
}
```

The owning sheet supplies the exact artifact, image hash, provenance and approval.
Candidates are not displayed as adopted. Replacing the accepted artifact updates
this link on the next normal projection refresh without changing story order.
A missing or damaged image produces a link diagnostic, not a different world state.
Shared artwork is verified once per owning sheet during a projection.

`evidence_sources` maps explicit `source_id` values to local paths and optional
SHA-256 commitments. Event evidence can also name an explicit local `path` or
HTTP(S) `url`. Unbound references remain visible as unbound. Missing files, hash
mismatches and unsafe URLs are diagnosed; external URLs are not fetched.
HTML uses text nodes and escaped JSON, so a note cannot become executable markup.

## Synchronization, failure and growth

Ordinary Studio transitions already refresh the gallery and activity display.
They also refresh the automatic Flow and Axis page, including after image adoption.
State artifact writers notify this projection when they write a known source or
referenced scene context. A changed scene, new scene file, deleted file, narrative
revision or changed accepted image changes the projection identity.
Files edited in an external editor are not watched by a service:
run `studio.py sync` after saving. This rechecks the base, events, processes,
configuration, narrative/scene files, collection membership and explicit artwork/evidence dependencies. Already open pages show
their printed input revision until reloaded; reloading the page refreshes
the view, not the source files or the story itself.

The output contains its input hashes, renderer identity and generated time.
Inputs are rechecked before an atomic HTML publication. Repeating an unchanged sync
keeps the same page and does not duplicate its activity event.
Projection actions enter the operator activity journal, never `state/events.jsonl`.

If inputs cannot be loaded or rendering fails, the current page becomes an explicit
unavailable view. The prior successful view is retained as `timeline.last-good.html`
with a visible STALE banner. An inaccessible output path may prevent even that
warning from being written; the operation diagnostic and pending-projection marker
then require `studio.py sync`. A story-view failure does not undo an image adoption
or prevent an independent gallery/activity refresh.

One compiled ledger validates artifact structure once and indexes IDs, timelines
and revisions. Flow reads each scene source once and does not request a new replay per
card. Scene IDs, participants, associations and relation directions are indexed.
A corrupt draft remains visible as a source notice; it supplies no guessed scene link.
Duplicate scene IDs are shown without choosing the newest file as canonical.

The browser filters recorded data and creates a bounded page: 24 Flow records,
40 Axis records and 40 state fields. Full source data remains embedded in the HTML;
paging limits DOM work, not total file size or parsing memory. A single very large
scene can still be expensive to inspect. No unbounded scalability is claimed.
Image verification follows explicit bindings, not a recursive scan of all outputs.
Replay work grows with selected/checkpoint queries and their applicable history;
large diagnostic histories can still take time. No history is truncated or silently
removed to make a view appear successful.

## Synthetic example and tests

```bash
python examples/story-timeline/build_example.py --out NEW_STATE_EXAMPLE_DIR
python examples/story-flow/build_example.py --out NEW_STORY_EXAMPLE_DIR
python scripts/state_ledger_smoke_test.py
python scripts/story_timeline_smoke_test.py
python scripts/story_flow_smoke_test.py
```

The state example authors a small test ledger. The Flow example authors a three-scene
synthetic story with a deliberately unexplained change in trust. It proves that human
reading remains useful even when all state checks pass. Neither example is user material.
Tests use synthetic records and independent Studio files, with no personal pack.
