# Scene Persona material: prepare once, reuse within scope

Scene-specific material preserves a reading decision already made with the
complete applicable Persona (the character's definition), portrayal intent,
current state and world context. Read the definition to find the required
sections; a request word such as "conversation" is too little to go on, because
a routine activity can depend on values, knowledge, memory, culture,
relationships, attention, body, voice and exceptions anywhere in it.

## 1. Preparation and reuse are different operations

For preparation or a scope change, read the complete applicable originals and
the Persona definition model. While designing the scene, select the exact
definitions, their dependencies and the relevant exceptions, and write the
scene applications in that same pass, leaving out any separate chain of
outline, summary and re-summary steps. Retain definition text itself, beyond
trait labels, headings or links. Keep separate:

- original rules;
- current conditions;
- proposed performance options;
- unresolved choices.

For reuse, check the completed bundle against the plan and the complete source
hashes, then read its `persona.md` for writing, performance direction, local
repairs or session resumption. The `scene-persona` feature (section 4) selects
this mode; it removes the repeated full-template read, while the preparation
itself must still have happened. Ordinary wording changes inside the reviewed
scene scope proceed on the existing reading. The code validates integrity and
declared links; understanding the scene stays the reader's work. The verified
bundle is also the record that the Persona is ready for this use, at this phase
and in this medium; it says nothing about the Persona's completeness elsewhere,
which the Persona Template's completion rule governs for a release.

An intact source digest proves the sources unchanged and nothing about a
creative direction the scene has yet to record. Section 3 traces a changed
source to the scenes it reaches. Reopen preparation for a changed participant,
relationship, topic, knowledge access, portrayal aim, mode or other declared
trigger. A definition left out of the excerpts still exists: for an apparent
gap, or a topic or turn beyond the planned scene, consult the originals rather
than substituting a generic personality.

## 2. Files and commands

The scene record remains the scene owner. The root is the studio when the work
is in a studio, and the series directory otherwise; every path in a plan is
relative to it, and the narrative is `story/narrative/narrative.json` in a
studio. Keep the plan and its bundle beside the scene plot or in another
directory of the root, outside `production/`, `runs/`, `characters/`,
`packages/`, `prompts/` and `work/`, and the Persona originals separate. Stable
names or IDs and content hashes identify material; extra version or revision
counters add nothing.

A plan uses `schemas/authoring/scene-persona-plan.schema.json`. It names:

- the complete scene source and complete applicable sources, their hashes and
  attributed full-reading basis;
- subjects with their applicable Persona, functional or explicitly unresolved
  portrayal basis (no human, speech or cast-size requirement);
- each definition by its anchor in a Markdown source, its declared definition
  dependencies and why it applies;
- the medium: `text`, or `image` for any depiction, a picture or a video;
- scene applications, directional interactions, constraints, unknowns and conditions
  that reopen preparation;
- a preparation review with its author, basis, readiness, remaining limitations
  and the source changes it reviewed;
- the material it supersedes, or null.

An anchor is a heading path and, for a field, the field name, joined by ` > `:
`7. SPEECH > Speech Patterns` or `13. RELATIONSHIPS > Important People`. A
shorter anchor names the one heading or field whose path ends with it, and a
heading covers everything below it. A document with one level-1 heading treats
it as the title. `scripts/persona_units.py PERSONA` lists every anchor and
whether it carries an answer; template comments are not content.

The material records the content hash of every heading and field of each
Markdown source it read, quoted or not. Section 3 compares a later Persona
against that record.

A Persona written in the installed form carries a core in every scene: the
`anchors` of `config/persona-core.json`, which are the portrayal identity, what
the person knows at this point, the speech baseline and the prohibitions. An
image material also carries its `depiction_anchors`, the appearance, for each
character whose identity image the studio has not adopted. The build refuses a
material that leaves part of the core or the appearance out, and one with no
answer in it. Fill the core before a scene relies on it, and fill the rest of
the form as scenes need it. A Persona in a custom format names no core.

An adopted identity image holds the appearance, as
[Time and ownership](cast-and-persona-depth.md#time-and-ownership) says, and the
material records its studio character, slot, iteration and hash. `verify` and
production refuse the material unless that image is accepted and bound.

When the scene source is a scene plot and the narrative declares persona
phases, each Persona subject reads the file of the phase its chapter falls in,
and the build refuses another.

`draft` writes a plan from a scene plot: each character's Persona for that
chapter, its core, the appearance an image needs, the Important People table,
and the relationship block for each other character in the scene. Every value
the author writes is a `<fill: ...>` placeholder that the build refuses. After
reading the Persona in full, add the definitions the scene's topics, knowledge
and voice modes need, and write the applications.

```bash
python scripts/scene_persona.py draft --root STUDIO --scene-plot story/narrative/scenes/SC01-plot.json --medium image --out story/narrative/scenes/SC01.plan.json
python scripts/scene_persona.py inspect --root STUDIO --plan story/narrative/scenes/SC01.plan.json
python scripts/scene_persona.py build --root STUDIO --plan story/narrative/scenes/SC01.plan.json --out story/narrative/scenes/SC01-persona
python scripts/scene_persona.py verify --root STUDIO --plan story/narrative/scenes/SC01.plan.json --bundle story/narrative/scenes/SC01-persona --require-ready
python scripts/scene_persona.py impact --root STUDIO --persona story/narrative/personas/c01.md
```

The build writes `material.json` and a deterministic `persona.md` into one
directory. An identical repeat changes nothing; differing content is refused
rather than silently overwritten. Replace an obsolete *derived* bundle under a
different stable task or output name, naming it in `supersedes`, or discard it
explicitly. Update a scene's application in that bundle; the original Persona
stays untouched. A size budget is optional, and a selected budget fails rather
than cutting definition text.

A preparation review is a review record rather than another canon ledger, and
`ready` is an attributed review decision only: neither a machine proof nor
permission to generate, adopt or train. It may retain explicit intentional
unknowns; unresolved applications require stated limits. The complete source
set is hashed, including passages outside the excerpts, so changing any part of
an original invalidates reuse until applicability is reviewed again.

## 3. When a Persona changes after a scene has read it

A Persona edit is one of three things, and each reaches scenes differently:

- A change in the story, after an event, is not an edit. Record a state event
  for a temporary change, or write the next phase for a lasting one; earlier
  scenes stay true to the phase they read.
- A correction changes what the Persona always was. It reaches every scene that
  quoted the changed heading or field.
- An addition answers a field that was blank. No scene quoted it, but a scene
  that read the section may already contradict it. An added past fact follows
  [Time and ownership](cast-and-persona-depth.md#time-and-ownership).

`impact` compares each material with the current sources and lists the scenes
in story order, each with its status:

| Status | Meaning |
|---|---|
| `stale` | A heading or field the material quoted changed, or a field appeared under a quoted heading. |
| `review` | Only headings or fields it did not quote changed, were added, answered or removed. |
| `current` | Nothing it read changed. |
| `superseded` | A later material names it in `supersedes`. |
| `missing` | A source it read is gone. |

Each change is `changed`, `added`, `filled` (a blank field answered),
`removed` or `renamed`. A heading or field whose text stayed and whose name
changed, or that moved under a renamed heading, is `renamed` with the anchor it
had. A quoted rename changes no meaning, but the plan names the old anchor:
point it at the new one and rebuild.

Each scene also lists the production runs that used its material and the studio
images whose Generation Package used it. The report ends with the approved scene
plots that read the Persona with no material recording what they relied on. In
a studio, `studio.py status` prints one line when a change reaches a material.
A report and that line, trimmed (synthetic fixture):

```json
{
  "ok": false,
  "persona": "story/narrative/personas/c01.md",
  "scenes": [{"scene_id": "sc01", "chapter": "ch1", "medium": "image", "status": "stale",
              "material": "story/narrative/scenes/sc01-persona/material.json",
              "sources": [{"source": "story/narrative/personas/c01.md", "status": "stale", "changes": [
                {"anchor": "7. SPEECH > Speech Patterns > first_person", "change": "changed", "quoted": true},
                {"anchor": "9. KNOWLEDGE > Expertise > hobby", "change": "filled", "quoted": false}]}],
              "runs": [{"run": "01a0ce41-0390-7907-b7b6-47bb4933a82b", "selection_recorded": false}],
              "iterations": [{"character": "C01", "slot": "base.front", "iteration_id": "it-0001",
                              "status": "accepted", "accepted": true}]}],
  "unrecorded": []
}
```

```text
persona changes reach 1 scene material (1 stale): python '<skill>/scripts/scene_persona.py' impact --root '<studio>'
```

The author decides which of the three a change is. For a correction, rebuild each
stale material from its plan. Record the change under `review.revisions` with
its kind, anchors and decision, and name the replaced material in `supersedes`.
Whether a run or an accepted image made from the old material is redone is a
separate decision. For an addition, check the scenes marked `review`, and
rebuild those that contradict it.

## 4. Existing production task integration

Add `scene-persona` to `features` and name the material explicitly:

```json
"scene_materials": [
  {"plan": "scene-plan.json", "bundle": "scene-material"}
]
```

Preparation validates the complete sources and exact derived files, pins them
into the production dependencies, and places the text in `consumer.json` under
`authoring_materials`. A task whose artifact is an image or video refuses a
material prepared for text; rebuild it with medium `image`. The production
direction, reviews, authorization and canonical owners still apply. The prepared
authoring material is **not** a generation prompt. Form the actual rendition
under the existing viewpoint and delivery rules instead of attaching the
material wholesale to a media tool, and keep author-only information out of
what a depicted subject knows.

## 5. Public protocol intake

`scene-persona-material` is a producer-independent public artifact. Export or
verify it with `protocol_exchange.py`. The producer's identity, directory layout
and installed tools are irrelevant to a recipient, and producer paths inside the
artifact are source labels rather than files the recipient may open.

For explicitly accepted public material, use this selector instead of a local plan:

```json
"scene_materials": [
  {
    "artifact": "incoming/material.json",
    "accepted_content_sha256": "<the actual public artifact content hash>",
    "accepted_by": "<reviewer>",
    "acceptance_basis": "<scope reviewed, source-availability limits understood>"
  }
]
```

This checks the public contract, the exact accepted content and readiness, and
claims nothing about access to the producer's originals. Its use is a snapshot
acceptance rather than a freshness certificate, canon adoption or
external execution authorization. When the originals are locally available,
prepare a local plan that binds those files.

## 6. Executable examples and checks

`python scripts/create_authoring_example.py --root <empty-workspace>` creates a synthetic, genre-neutral worked example. `python scripts/scene_material_smoke_test.py` checks material, source, freshness and public-artifact behavior without generation services. Both checks are structural, as section 1 says of the code.
