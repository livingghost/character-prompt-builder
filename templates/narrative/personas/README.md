# Personas

One file per character, per phase. A persona says what this person wants, what they know, how they
speak, and what they do when nobody is watching. PHYSICAL supplies readable embodiment and
performance context, but an adopted identity contract owns stable visual geometry and appearance.
Keep that section consistent with the authoritative contract instead of creating competing canon.
A temporary wardrobe or health change remains scene state unless a declared phase requires it.

For original-character development, read the complete form when designing individualized behavior
or dialogue. Read the applicable world and design records as well; persona is one authority within
the work, not a compulsory starting point for every narrative or a substitute for its setting. Preserve
user anchors, assistant proposals, adoption and unresolved choices separately. A new scene should
follow from these people's decisions, not serve as an excuse to invent interchangeable traits.

A persona is phase-fixed. When a character has changed enough that the file no longer describes
them, write the next phase as a new file rather than editing this one, and say in each what changed
and what held. The old file is what the earlier chapters are consistent with, and overwriting it
makes those chapters unverifiable.

## The front matter every persona carries

The first block carries the machine-readable links. The index also scans the body for unfinished
form syntax; it does not judge the meaning, creative quality or adoption of the prose.

```
---
kind: persona
id: c01
name: The first
character: C01
phase: school
references: [kanda-station]
---
```

`id` has to match the file name and `character` has to be the id the narrative gives this person.
`phase` names which of that character's declared phases this file is, and the narrative's pointer
for that phase has to be this file: where the two disagree the check refuses, rather than leaving a
session to read whichever it opened first.

```
python <skill>/scripts/narrative_entity.py --series <series> add persona c01 --character C01
python <skill>/scripts/narrative_index.py <series>
```

The first uses the installed current full persona form and writes the entity front matter.
Series initialization uses the same full-form creator for any explicitly requested teaching seed.
Project copies of the template are reading material; creation reads the installed source.

## The form

`persona-template.md` beside this file is the blank form, and every project gets a copy.
It is one phase of one life in twenty sections, and its own instructions are written into
it as comments beside each field: what belongs in the field, what does not, and what to
write when the answer is not settled. Two of its rules are worth knowing before starting.

The first is that a trait is recorded in three layers, because they routinely disagree:
what the character believes about themselves, what they observably do, and how they are
seen from outside. The second is that anything not directly attested is marked as an
inference with its reasoning, so a later session can tell what the source said from what
somebody worked out. In original-design mode, deliberate invention is a proposal with a design
basis, not an inference pretending to have a source. Record adoption separately in META and SOURCES.

Create the current file with the command above, then fill it. A field nobody has settled says so;
an empty field and a settled blank are not the same answer.

## What a persona file carries

The current full form carries readable prose and explicit bindings. These are the decisions a
later session needs, with unexamined gaps retained rather than silently inferred:

- where this phase sits in the character's life, and what they know at this point that they did not
  know before;
- the scoped identity core, the governing authorial aim and the intended pattern of constancy or change;
- how they think, decide, and react under pressure, with the reaction stated before the reasoning;
- how they speak: register, vocabulary, sentence shape, what they will not say out loud;
- what they know and can do, and the edge of it;
- how they behave toward each important person, which is not the same as how they feel;
- how they are seen from outside, which is not the same as either;
- meaningful limits in the actual scope, without assuming lifelong prohibitions.

Of these behavioral rules, the gate only checks the explicitly declared prohibitions mechanically. A prohibition is declared in
`narrative.json` under the character, in one of two kinds, because the two are not settled the same
way. A `surface` prohibition names a phrase and is refused when the text a model receives carries
it. A `judgement` prohibition names a behaviour, which no string search settles, so it is reported
with the text for a person to answer. Explain the rule here; declare it there.

## Contextual voice and performance

The full form connects PHYSICAL baselines, THOUGHT conditional responses, SPEECH contextual voice
modes and RELATIONSHIPS exceptions. Record exact forms, changed and held components, relevant
simultaneous conditions, switch points, release and residue. A temporary emotional or audience
shift is not a new persona phase. Mode IDs are local prose references, not shared JSON fields.

Use EXAMPLES for matched-context, changed-condition and new-situation probes; similarity can be
intentional and an unchanged response can be correct. Do not confuse completed fields, literal
text hygiene, or a long form with successful individualized portrayal. The skill's Character
Performance route owns the full authoring/review procedure. Its read-only expression audit can
surface drafting gaps and repeated descriptions without changing any file or approving content.

## Authorial identity

Section 2 PORTRAYAL IDENTITY distinguishes the subject's inner core from the creator's portrayal
aim. Bind it to the applicable authorial intent entries in a design record, and bind response,
voice and bodily rules to that profile. Signature dynamics may be constant, contrasting or
intentionally indeterminate. A register switch is not automatically a break in identity.

Review the actual span of outputs as well as isolated examples. Record deliberate departures,
retained dimensions and aftermath under their owning design decision. A plan is not current
knowledge, and a label is not access control: remove concealed/future information from a
limited-consumer view. Creator intent stays distinct from both factual claims and local acting cues.

## Naming

`c01.md` for the character whose id is `C01` in `narrative.json`, and `c01-phase-2.md` or a named
phase for a later one. Each character entry in `narrative.json` points at the file for the phase the
series is currently in, and `narrative_index.py` reports a pointer with no file behind it.
