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
repairs or session resumption. The `scene-persona` feature (section 3) selects
this mode; it removes the repeated full-template read, while the preparation
itself must still have happened. Ordinary wording changes inside the reviewed
scene scope proceed on the existing reading. The code validates integrity and
declared links; understanding the scene stays the reader's work.

An intact source digest proves the sources unchanged and nothing about a
creative direction the scene has yet to record. Reopen preparation for a
changed participant, relationship, topic, knowledge access, portrayal aim, mode
or other declared trigger. A definition left out of the excerpts still exists:
for an apparent gap, or a topic or turn beyond the planned scene, consult the
originals rather than substituting a generic personality.

## 2. Files and commands

The scene record remains the scene owner. Keep its prepared material beside it
or in any declared project-relative location, and the Persona originals
separate. Stable names or IDs and content hashes identify material; extra
version or revision counters add nothing.

A plan uses `schemas/authoring/scene-persona-plan.schema.json`. It names:

- the complete scene source and complete applicable sources, their hashes and
  attributed full-reading basis;
- subjects with their applicable Persona, functional or explicitly unresolved
  portrayal basis (no human, speech or cast-size requirement);
- exact inclusive line ranges for definition text, declared definition dependencies
  and why each excerpt applies;
- scene applications, directional interactions, constraints, unknowns and conditions
  that reopen preparation;
- a preparation review with its author, basis, readiness and remaining limitations.

`inspect` returns whole-file digests and line counts from a plan with at least a
`sources` list of `{source_id, path}` objects; the reading and the excerpt choice
stay the agent's own. Finish the plan after reading the actual documents.

```bash
python scripts/scene_persona.py inspect --root PROJECT --plan scene-plan.json
python scripts/scene_persona.py build --root PROJECT --plan scene-plan.json --out scene-material
python scripts/scene_persona.py verify --root PROJECT --plan scene-plan.json --bundle scene-material --require-ready
```

The build writes `material.json` and a deterministic `persona.md` into one
directory. An identical repeat changes nothing; differing content is refused
rather than silently overwritten. Replace an obsolete *derived* bundle under a
different stable task or output name, or discard it explicitly. Update a scene's
application in that bundle; the original Persona stays untouched. A size budget
is optional, and a selected budget fails rather than cutting definition text.

A preparation review is a review record rather than another canon ledger, and
`ready` is an attributed review decision only: neither a machine proof nor
permission to generate, adopt or train. It may retain explicit intentional
unknowns; unresolved applications require stated limits. The complete source
set is hashed, including passages outside the excerpts, so changing an unquoted
original invalidates reuse until applicability is reviewed again.

## 3. Existing production task integration

Add `scene-persona` to `features` and name the material explicitly:

```json
"scene_materials": [
  {"plan": "scene-plan.json", "bundle": "scene-material"}
]
```

Preparation validates the complete sources and exact derived files, pins them
into the production dependencies, and places the text in `consumer.json` under
`authoring_materials`. The production direction, reviews, authorization and
canonical owners still apply. The prepared authoring material is **not** a
generation prompt. Form the actual rendition under the existing viewpoint and
delivery rules instead of attaching the material wholesale to a media tool, and
keep author-only information out of what a depicted subject knows.

## 4. Public protocol intake

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

## 5. Executable examples and checks

`python scripts/create_authoring_example.py --root <empty-workspace>` creates a synthetic, genre-neutral worked example. `python scripts/scene_material_smoke_test.py` checks material, source, freshness and public-artifact behavior without generation services. Both checks are structural, as section 1 says of the code.
