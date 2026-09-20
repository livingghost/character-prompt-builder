# World records

These records own the places, groups, mechanisms and consequential objects of the work. The world
is not merely a backdrop for relationships; its material, social and expressive implications
must agree with its scoped rules. A character's beliefs about a place or system do not override
that record, and an author-facing theme or genre convention is not itself an in-world law.

## Record what the current work depends on

Use one subject per file, with enough context to apply it and references to related records.
Avoid both duplicated canonical facts and an encyclopedia that blocks a small requested output.

| Directory and kind | Useful content, when applicable |
|---|---|
| `locations/`, `location` | Situation, access, spatial relations, contents, environmental conditions, uses and local meanings |
| `factions/`, `faction` | Composition, roles, practices, internal differences, external relations and changes; no assumed single will |
| `systems/`, `system` | Conditions, operation, scope, effects, persistence, limits, exceptions and unknowns; costs only when actually part of the design |
| `artifacts/`, `artifact` | Properties, provenance when known, access, uses and constraints; changing possession is time-scoped, not an unqualified permanent fact |

A rule may be ordinary, fantastic, symbolic or intentionally only partly explained. Record the
kind of claim: established condition, proposed design, cultural account, individual belief or
narrative presentation. Do not convert uncertainty into a new fact, impose realistic costs on a
free mechanism, or invent origins for an object whose origin is irrelevant or unknowable.

Trace important interfaces. A mechanism can affect everyday routines, infrastructure, institutions,
objects and language as well as the exceptional scene that introduced it. Record actual scoped
consequences, not every plausible inference as canon. Differences between regions or times may be
intentional; say where each condition applies and what changes. Distinguish immutable properties,
current state and an author's planned future.

## File and link contract

```text
---
kind: system
id: light-cycle
name: The local light cycle
references: [observatory]
---
```

The `kind` matches the directory, `id` matches the filename, and `references` lists other entity
or declared character IDs. This front matter supplies machine links; prose below it is the
record, with adoption, basis, scope and remaining uncertainty stated where relevant.

```bash
python <skill>/scripts/narrative_entity.py --series <series> add system <id> --name "<name>"
python <skill>/scripts/narrative_entity.py --series <series> rename <old-id> <new-id>
python <skill>/scripts/narrative_index.py <series>
```

Use the commands for creation and ID changes. Rename updates declared ID references, supported
JSON fields and persona pointers; it does not rewrite arbitrary prose. Report dangling and orphan
records without treating them as judgments of the fictional design. A design note can reference
world records before any scene uses them. Coverage may still report unused locations as drafting
gaps; a worldbuilding deliverable does not need invented scenes to erase those gaps.

Cross-layer intent and revision rationale belong in `design/`; behavior belongs in persona;
shared vocabulary belongs in `glossary/`; executed temporal state belongs in state artifacts.
A handoff includes the relevant versions of these records, not merely their titles or hashes.

## Grounding and realization

Retain a source locator or actual creator decision for consequential conditions and changes. Do not
turn a plausible completion of sparse material into a recovered fact. Distinguish a condition from
a report about it, its disclosure, and an observation of a generated output. Relevant non-agent
subjects need no invented psychology.

When state is serialized, the installed `references/runtime/world-realization.md` describes a
source-pinned plan over the existing event ledger. Story targets are resolved independently of
presentation order. World files remain the factual owners; the plan coordinates dependencies and
recipient views. Source or intent edits require an impact review rather than silent reuse of stale
outputs. These installed paths are instructions, not relative links inside the created project.
