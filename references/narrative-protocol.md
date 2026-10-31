# Narrative Protocol

The contracts for what a series is about, as against what is true in it at a moment.

State artifacts carry what is true at a moment: contracts, snapshots, events, projections.
None of them says what the series is for, so an installation that holds only those has identity,
wardrobe and environment at a story point and nothing above them.

Two artifacts sit here. Both are authored by whoever owns the series, and both are read rather
than written by whatever implements this contract.

## Ownership

- The author owns the narrative and every scene plot. An implementation reads them; it does not
  write them.
- An implementation that plans coverage reads them to place scenes, break them into units, and
  refuse work that contradicts them.
- An implementation that composes model-facing text reads them to say where an image came from: its
  own plot names the scene plot it was written from, by the hash that plot was approved under.
- Neither is state. A narrative says the audience learns something in chapter three; a state
  snapshot says what a character knows at story order 400. They meet through `timeline_id` and the
  story orders each chapter declares. A work with no story clock uses a null `timeline_id` and no chapter story coordinates; chapter presentation order is not converted to time.

## Scope without a prescribed story model

The contract records declared intent; it does not select a protagonist, headcount, genre, theme,
moral position or dramatic structure. Work may be world-led, agent-led, observational, episodic,
associative or organized otherwise. These are not closed genre labels in the data.

The root `themes`, `characters`, `arcs` and `chapters` fields are arrays and may be empty. Required
reference arrays may likewise be empty except where a declared type entails its subject: a
`character` arc needs character references, and a `thematic` arc needs theme references. Missing
arrays, invalid entries, unknown fields and unresolved declared references are still refused.
Empty means not declared here, not necessarily nonexistent, decided, complete or approved. Local
authoring records distinguish deliberate absence from open design choices.

Arc `setup`, `rising`, `climax` and `resolution` sections are optional. If present, text fields
contain nonempty text and `rising` is an array of nonempty development-stage strings; it may be
empty. `want` and `need` are independently optional authored text on any thread. No obligatory escalation, character transformation, climax or closed resolution is implied.

A scene may have no cast, explicit themes, named arcs, exchanges, persistent changes or
relationship delta. It still records its purpose, setting, focalization, presented beats and
supported realization. `turn` and named `structure` are optional. Data consistency and approval
are separate from the artistic adequacy of these choices.

This is a serializer for ordered chapters and scenes in the media listed below, not a universal
interactive graph or a requirement that all creative work be serialized. Local design documents
may hold unsupported structure. Do not add undocumented JSON fields or invent events to force it
through this reader. Linked world and design prose is not semantically validated here.

## `narrative`

```text
artifact_type   "narrative"
series_id       the series this covers
timeline_id     a named timeline when story coordinates are declared; otherwise null
medium          prose, comics, screen or mixed; what a scene of this becomes
themes          id, statement, and an optional note; declared thematic concerns,
                without a required count, message or relevance to every scene
arcs            id, name, type, status, the themes and characters it carries,
                optional setup, rising, climax, resolution, want and need; type is authored text
acts            id, number from 1 without gaps, name, does, and the chapters it
                groups; every chapter belongs to one act or the series declares none
chapters        id, number from 1 without gaps, title, status, the declared arcs,
                depicts as a non-empty array of non-empty strings describing the
                material presented or held here, and the story orders it covers
                as story_order_start and story_order_end
characters      id, name, persona as the document in force, phases as the earlier
                phases of that life, prohibitions as what this person never does,
                and optionally the chapters they first_appears in and are
                written_out_in.
                A phase carries id, persona, and from_chapter; every phase after
                the first also carries changed and held, which are what moved at
                that boundary and what did not, and the first carries neither
                because it has no predecessor to have moved from. The phases run
                in chapter order, and persona is the document of the last of them.
                A prohibition carries kind, an optional note, and one of two
                fields: a surface prohibition carries surface, the phrase itself,
                and a judgement prohibition carries statement, the behaviour. A
                prohibition carrying the field of the other kind is refused
relationships   id, from, to, bond_type, at_start, and the arcs it carries;
                directional, because what one owes the other is not what comes back
promises        id, statement, status, the arcs it carries, optionally the
                characters, and where it was planted and paid as planted and
                payoff, each naming a chapter
questions       id, statement, status, optionally the arcs and characters, and
                where it was raised and answered as introduced and resolved, each
                naming a chapter
knowledge       id, fact, known_by, learned_in, and an optional note; who learned
                which fact, and in which chapter, with audience among the knowers
approved        by, at as an RFC3339 UTC time, content_sha256, and an optional note
```

One description still uses an array. This synthetic excerpt contains only a
chapter's `depicts` field:

```json
{"depicts": ["The empty room remains dark."]}
```

The author chooses the descriptions, their language and length. Multiline and
repeated descriptions are valid; the reader checks the string shape, not what
the chapter should present or whether its condition changes.

`characters[].persona` and `characters[].phases[].persona` are paths relative
to the series directory, the directory containing `narrative/`. In the standard
layout, `<series>/narrative/personas/c01.md` is recorded as
`"narrative/personas/c01.md"`. The base stays the series directory when that
series sits inside a studio. The current pointer still names the last declared
phase; a scene selects the phase applicable to its chapter.

## `scene-plot`

```text
artifact_type   "scene-plot"
scene_id        the scene this plot covers
narrative_sha256  the narrative this was written against, so a change above it
                invalidates this approval rather than passing unnoticed
chapter, order  which chapter, and where in it; a chapter's scenes run from 1
arcs            the declared organizing threads this scene carries; may be empty
characters      who is in this scene
themes          which of the series' themes this scene carries
focalization    kind; through as a character id, required for internal and optional
                for external; zero has no named holder; and an optional note
setting         interior_exterior, location as an id, where inside it, time_of_day,
                optionally season and weather, and optionally scene_context naming
                a derived snapshot by a path relative to the series directory
scene_function  authored text describing this scene's function
delivery_role   what job the scene does for the audience
proposition     why the scene exists, in one sentence
turn            optional value, from and to comparison, including persistence, and an optional note
structure       optionally profile and parts, each part naming a beat this scene holds
beats           id, beat as presented material or a contextual fact, visibility,
                and optionally who it teaches
exchanges       id, between as who speaks, about, achieves as what saying it
                accomplishes, and from
placement       who or what is where; must_preserve, what cannot change; free, what
                is open. Each entry carries a statement, and placement and
                must_preserve carry from. free carries none: it is what the scene
                has not decided, so there is no beat it follows from
state_changes   target, change, and from: what the scene leaves behind for later
                scenes, and the beat it leaves it behind from
relationship_delta  channel, between, change, and from: which channel moved between
                whom, and the beat it moved in
realization     kind, one of shots, pages or passages, and the units it breaks into
approved        by, at as an RFC3339 UTC time, content_sha256, and an optional note
```

Every sourced statement names its supporting beats in `from`: a non-empty list of
ids of beats this scene holds, without repeats. The field determines what that
support establishes.

| Field | Support |
|---|---|
| `placement`, `must_preserve` | Visible or context beats can ground an arrangement or preserved condition. |
| Unit `shows`, `composition`, `covers` | Visible or context beats can ground the selected depiction, framing or treatment. |
| `exchanges`, `state_changes`, `relationship_delta` | Each source is a visible beat in which the speaking, consequence or interaction change is established. |
| Unit `focal_beat` | An existing visible beat that the unit presents as its focus. |
| `free` | No source: this is what the scene leaves open. |

A context reference retains the beat's declared visibility. It can explain a
depiction choice without presenting the contextual fact or establishing a new
event. The author judges whether the choice follows from its sources and what
the audience receives. If the scene discloses that fact, record the disclosure as
presented material; a context beat cannot carry `teaches`. Learning, exchanges
and lasting changes still need their explicit declarations and visible support.
Applying a consequence through the state runtime requires its separately approved
state event.

For example, in a synthetic boathouse scene, visible beat `b1` is a worker lifting
a lantern down and context beat `b5` is another person sleeping up the ladder.
That context can support the shot composition below while the lantern action
remains its visible focus. This excerpt describes only that unit's treatment:

```json
{
  "focal_beat": "b1",
  "shows": [{"statement": "The worker steadies the lantern as it leaves the hook.", "from": ["b1", "b5"]}],
  "composition": [{"statement": "Close on the hands and lantern; keep the sleeper outside the frame.", "from": ["b5"]}]
}
```

The sleeping person need not be shown or learn anything for that choice to have
a source. A wake-up, spoken exchange or lasting relationship change would require
its own presented support. Necessary exclusions, such as keeping the sleeper
outside the frame, remain part of the authored depiction.

## The closed lists

Closed operational values and open authored text are distinguished below. Example vocabulary never becomes a compulsory dramatic or performance taxonomy.

| Field | Values |
|---|---|
| `arcs[].type` | nonempty authored text |
| `arcs[].status` | `planned`, `in-progress`, `resolved` |
| `chapters[].status` | `planned`, `in-progress`, `complete` |
| `promises[].status` | `planned`, `planted`, `paid-off`, `dropped` |
| `questions[].status` | `open`, `answered`, `resolved`, `dropped` |
| `characters[].prohibitions[].kind` | `surface`, `judgement` |
| `medium` | `comics`, `mixed`, `prose`, `screen` |
| `relationships[].bond_type` | nonempty authored text |
| `focalization.kind` | `zero`, `internal`, `external` |
| `setting.interior_exterior` | `interior`, `exterior`, `both` |
| `scene_function` | nonempty authored text |
| `delivery_role` | nonempty authored text |
| `structure.profile` | nonempty authored text |
| `realization.kind` | `pages`, `passages`, `shots` |
| `realization.units[].mode`, for passages | `scene`, `summary` |
| `relationship_delta[].channel` | nonempty authored text |
| `beats[].visibility` | `visible`, `context` |

A status is a claim about what the document must also carry. A promise that is
`planted` or `paid-off` names the chapter it was planted in, one that is `paid-off`
also names the chapter it was paid off in, and one still `planned` names neither,
because an intended payoff is not a payoff. A question that is `answered` or
`resolved` names both the chapter it was introduced in and the chapter it was
answered in, and one still `open` names no resolved chapter. A payoff before its
plant and an answer before its question are refused.

A channel is an interaction-specific change, not a cast limit or a score: `initiates-contact` is who reached
first, `gives-ground` is who yielded, `carries-the-object` is who holds the shared thing, and
`public-distance` against `private-distance` is how close each is allowed in company and
alone.

## Optional comparison and organization

A scene can observe a place, sustain an atmosphere, repeat a process or hold a condition without
changing a relationship or ending differently. Omit `turn` when no comparison is declared. When
supplied it is an object with nonempty `value`, `from` and `to` text, and an optional `note`.
Identical endpoints explicitly describe persistence and are valid; a malformed object is not.
`null` is not an omitted field. `state_changes` remains a required array, with `[]` for no
persistent consequence, not a fabricated statement claiming that something changed.

A named `structure` is optional. Its `profile` is nonempty authored text and `parts` is a
nonempty map from authored part names to existing beat IDs. No tradition, part count, climax,
change, or arrangement is supplied automatically. Omit the entire structure when it has no use.

Coverage checks declared threads and chronology, not a compulsory trigger and payoff in every
complete chapter or a minimum of two scenes per resolved arc. A one-scene completion and a
non-dramatic chapter are not gaps merely because of their form.

## What a scene becomes

`realization` is the scene in the parts its medium actually has, and the narrative's `medium` says
which kind a scene of this series takes.

| Medium | Kind | A unit carries |
|---|---|---|
| `screen` | `shots` | `id`, `focal_beat`, `shows`, `composition` |
| `comics` | `pages` | `id`, `focal_beat`, `shows`, `panels`, and optionally `spread` and `ends_on_turn` |
| `prose` | `passages` | `id`, `focal_beat`, `covers`, `mode` |
| `mixed` | any | |

`focal_beat` names the unit's focal visible beat; it need not depict a
change. It names one beat this unit carries, and `shows`, `composition` and
`covers` are statements, each naming the visible or context beats supporting its
depiction choices. Context support does not cover an otherwise unsupported visible
beat or make a context beat a valid focal beat. In prose, presented material can be
told or summarized; `visible` does not require an invented optical view. `panels` is how many
panels the page holds, from 1; `spread` and `ends_on_turn` say whether the page is a
spread and whether the reader must turn to resolve it.

The declared realization determines the unit type. Prose does not need an invented camera and
pages do not need to masquerade as shots. A submission surface requiring shot IDs must select
an actual shot realization rather than silently converting another medium.

## How a scene is told

`focalization` is Genette's, because that is the vocabulary narratology settled on. Zero focalization
knows more than anyone in the scene. Internal focalization is restricted to one character, who
filters everything the audience receives, and names them. External focalization sees from outside and
reaches nobody's interior; it may still name the character the telling stays with, because staying
with somebody is not reaching inside them.

This is not the camera. A shot's viewpoint profile says where the lens is; focalization says whose
knowledge the telling is limited to, which is why it sits beside the narrative's knowledge entries
and not beside the camera.

The character is named in `through`, and must appear in the scene's `characters`
array. These synthetic examples use `C01` for a character included in the scene:

| Access to the scene | Focalization object |
|---|---|
| Restricted to C01's knowledge | `{"kind": "internal", "through": "C01"}` |
| Exterior observation staying with C01 | `{"kind": "external", "through": "C01"}` |
| Exterior observation without a named holder | `{"kind": "external"}` |
| Unrestricted narrator | `{"kind": "zero"}` |

Each object may also carry `note`. External and zero focalization can omit
`through` or set it to `null` when no holder is named. Internal focalization
requires a nonempty character ID; zero focalization cannot name a holder.

## The hash an approval carries

`content_sha256` is the sha256 of the document with its `approved` block removed, over canonical
JSON: keys sorted, no ASCII escaping, no spaces after the separators. An approval that names only a
time is a claim about a document that can change after the claim, so a document edited after
approval is refused rather than passing on the presence of a block.

This differs from the Shared State Protocol's `artifact_hash`, which removes the artifact's own
self-hash field instead. The difference is not a style: an approval is a claim about the content
that was approved, and a self-hash is a claim about the document that carries it.

## The implementation that answers this contract

Most of what these contracts refuse cannot be written as a schema. Chapter numbers running from 1
without gaps, a payoff that arrives before its plant, an answer before its question, an exchange
sourced from a context beat, phases out of chapter order, a character in a scene
after they were written out: each of those is a relation between two parts of the document or
between two documents. A schema that expressed the third of this contract it can express would be a
schema a document could pass and still be wrong, which is worse than none.

So the contract is the field lists above, the closed lists, and a reader that implements them.
`scripts/narrative.py` and `scripts/scene_plot.py` are that reader here.

A copy of a reader cannot be compared with a copy somewhere else, because an installation reads only
itself. What it can do is compare its own against the hash published here, of the file with its line
endings normalised:

```text
scripts/narrative.py           b345ffdddc822dd9a5ad790b4a7386c8ef8627d249ec6e30d3dceff179a7e889
scripts/scene_plot.py          5ca1e875c100b72e2bc0496df8e0699907d5efa16929c1805d2c0d3ee38509d0
scripts/narrative_corpus.json  eec0a5a58c7a67131be3df3cd752d51a35d388bddcd2410ae486a65316c510db
```

An edit to a reader that does not travel with this document fails against it. That is the most a
contract can do about an implementation it cannot reach, and it is why the hash is published beside
the rules rather than kept beside the code.

The third file is the corpus: the documents in the case tables the readers here are checked
against, each with the verdict this contract requires of it, so that an implementation written
elsewhere is checked by whether it reaches every verdict there and not by whether it resembles the
readers.

## Reading one

```bash
python scripts/narrative.py <narrative>
python scripts/narrative.py <narrative> --content-sha256
python scripts/scene_plot.py <plot>
python scripts/scene_plot.py <plot> --content-sha256
```

A document written from one of these names it as its `source`: the artifact type, its
id, the `content_sha256` it was approved under, and the unit it covers. That field is
optional, because work made from a brief has no source and the brief is its root.
The downstream prompt plot can likewise retain context as support for its chosen
depiction. Its source commitment identifies the approved scene and unit; contextual
support in either plot does not grant knowledge, establish an event or adopt state.
