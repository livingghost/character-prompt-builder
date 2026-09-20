# Narrative workspace

This directory holds the authored work and its world. It can begin with a setting, mechanism,
theme, character, event, image or formal idea; a protagonist, a pair, an ensemble, a particular
genre, an explicit moral, a dramatic arc and a change in every scene are all optional.

- `design/`: scope, form, thematic exploration, cross-layer rationale, decisions and impact.
- `narrative.json`: declared themes, arcs, chapters, characters, relationships, questions and knowledge.
- `personas/`: detailed behavior and embodiment, one file per portrayed agent and relevant phase.
- `world/`: locations, factions, systems and artifacts, whether or not people are present.
- `glossary/`: terms the work uses in a particular way.
- `scenes/`: serialized scene plots and their realization in the supported medium.

The design note connects these responsibilities; each record stays authoritative. Shared JSON
validates links and supported shapes; meaning is unchecked. Declared concerns and arcs can be
traced to scenes, yet a creative decision may originate outside any theme, and parts of the work
may stay unconnected.

The neutral initializer creates `design/project.md` from the full design form and a narrative
with empty tables; adding any persona, arc, theme, prohibition or chapter is the author's work.
An empty table is unspecified unless the design record establishes intentional absence. The
explicit example seed adds one placeholder character and a teaching outline as an example rather
than a creative default. Persona creation always uses the full twenty-section form unless
`--blank` is explicitly requested for a custom workflow.

Story order and presentation order differ. The JSON form serializes ordered chapters and scenes;
unsupported structures, including native interactive branches, stay in scoped design notes unless
explicitly projected to supported sequences. Never imply that the serializer accepts unknown
fields, and keep the intended form rather than silently substituting a screen production.

Use:

- `narrative.py` for the JSON contract;
- `narrative_index.py` for links and unfinished fields;
- `narrative_coverage.py` for declared scene coverage.

Only some drafting gaps are errors, and a structurally valid empty workspace is still uncompleted
and unapproved. Read the full design and persona forms when using them; the whole questionnaire
stays out of the reply to the user.
