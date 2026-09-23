# Narrative Authoring

[Narrative Protocol](narrative-protocol.md) defines the shared narrative and scene-plot contracts.
[World-Coherent Creative Development](runtime/narrative-development.md) defines how to develop the
work, test its interfaces and retain decisions. This document owns the local files, commands and
reports; approval and artistic judgment stay with the author, and a hash or a passing check leaves
approval unchanged.

## Before file creation

Start at the request itself: a world, theme, agent, event, form or local revision. Use the complete
[Project Design Template](../templates/narrative/design/design-template.md) as the cross-layer
workspace, and the complete
[Persona Template](../templates/narrative/personas/persona-template.md) when individualized
behavior or dialogue is designed or materially revised; unpeopled work skips it. Read existing
records before proposing changes. A one-off answer stays in the conversation. Once a draft will be
reused or revised, create the series directory and the studio work trail before the next dependent
draft, and save what that draft depends on: the instruction, the draft shown, the decisions with
their scope, and the open questions. Saving needs no image prompt, model, pack activation, sheet or
finished persona. A series directory may sit inside a studio, for example
`<studio>/story/narrative/`, so the files and the trail share one home;
[Studio Runtime](runtime/studio.md) owns the trail and its checkpoints.

An agent may draft for the author; an implementation consumes approved intent rather than
inventing it or its approval. Preserve user anchors, proposals, adopted scope, rejected options
and unresolved choices across authoring and execution roles.

## File responsibilities

A series directory is any directory holding `narrative/`; nothing else is assumed around it.

```text
<series>/narrative/
  design/project.md       scope, intent, form, dependencies, decisions and impact
  design/*.md             additional scoped design records when useful
  narrative.json          declared themes, arcs, chapters, characters, relationships,
                          promises, questions and knowledge
  personas/               individually portrayed agents, one file per relevant phase
  world/locations/        places, access and scoped environmental conditions
  world/factions/         groups, roles, practices and relevant internal differences
  world/systems/          mechanisms, institutions, effects and actual constraints
  world/artifacts/        consequential objects and time-scoped changes
  glossary/               shared meanings rather than private definitions in each persona
  scenes/                 supported serialized scene plots
```

Design records connect responsibilities rather than competing canonical copies. Their front matter
uses `kind: design`, a filename-matching ID and `references` to dependent entity or declared
character IDs. All design records, including proposed and alternate designs, are authoring roots
in the index; reachability and adoption stay separate. The body owns scope and decision
rationale; the index reads declared references only, leaving the ledger unparsed for permissions
and prose unparsed for dependencies.

A persona holds readable embodiment and behavior; world facts and adopted visual identity keep
their own owners, and its PHYSICAL section defers to them for measurements and markings. Scope
current health, wardrobe and knowledge in time; a future plan is a plan rather than an established
event. A handoff includes relevant world and persona content, beyond file paths alone.

## Initialize a workspace

```bash
python scripts/narrative_init.py --out <directory> --series-id <id> --title "<title>" \
    [--medium screen|comics|prose|mixed] [--seed neutral|example]
```

The default `neutral` seed creates only an empty narrative and the full `design/project.md`
workspace; characters, persona instances, themes, arcs, chapters and behavioral prohibitions are
left for the author to declare. An empty table means nothing has been declared in it; record
deliberate absence versus deferred design in the design note. A valid empty narrative is a
starting point rather than a finished or approved work.

`--seed example` uses the [teaching seed](../templates/narrative-seeds/example.json), which adds
one placeholder character and outline; its persona comes from the same full-form creator as later
persona additions. Headcount, theme, genre and structure remain the author's to set. Both seeds
retain the reusable full forms.

`--medium` selects shots, panels or passages; the default `screen` is a default rather than a
recommendation, so choose the medium for the actual output and edit `narrative/narrative.json`
if it changes. `mixed` permits supported realizations; a native game or branching graph format
lies outside it, and unsupported structures can stay in scoped design notes rather than being
forced into scene JSON.

Init refuses an invalid series ID or a nonempty destination, and treats a missing or empty full
template as an error rather than permission to substitute a short form. A failed initialization
may leave a partial new directory; inspect it rather than claiming success. Migrating an existing
project is outside init.

## Create and maintain records

```bash
python scripts/narrative_entity.py --series <directory> add design <id> --name "<name>"
python scripts/narrative_entity.py --series <directory> add persona <id> --character <id> \
    [--phase <name>] [--name "<name>"]
python scripts/narrative_entity.py --series <directory> add system <id> --name "<name>"
python scripts/narrative_entity.py --series <directory> rename <old> <new>
python scripts/narrative_entity.py --series <directory> remove <id> [--force]
```

Kinds are `design`, `persona`, `location`, `faction`, `system`, `artifact` and `term`. Design and
persona creation use the installed current full templates, the identity-led form and the
authorial intent register, as their sole form authority, through one creation path with no
abbreviated form or version adaptation; project copies of the forms are reading material rather
than alternate creation sources. Other kinds receive prompts appropriate to their responsibility.

Adding a persona leaves the narrative character, phase history and adoption to the author: set the
narrative's pointers explicitly. Keep phase-specific knowledge and choices in the correct file; a
current pointer is no permission to use the final persona in an earlier scene.

A person the agent proposes is a candidate in the design ledger until the author admits it; create
the persona entity and set the pointers after that decision, once.
[Cast Admission and Persona Depth](runtime/cast-and-persona-depth.md) owns the candidate, the scope
of a confirmation and the depth a use needs.

`rename` changes the entity filename and ID, declared front-matter references, narrative persona
pointers and supported scene location references; arbitrary prose, ledger entries and Markdown
links stay as written, so review those separately. A changed JSON document loses its approval; a
Markdown-only change leaves another document's approval to the author's review.

`remove` refuses an entity that another record or JSON document still names; an implicit design
root is internal and by itself leaves removal allowed. `--force` deletes anyway and reports the
remaining dangling references; resolve those rather than hiding them behind the flag.

## Inspect links, drafting gaps and declared coverage

```bash
python scripts/narrative_index.py <directory> [--json] [--strict]
python scripts/narrative_coverage.py <directory> [--json] [--strict] [--scenes <directory>]
```

The index checks entity kind, filename, ID, persona pointers and declared references in both
directions. A missing target is dangling; an unreferenced non-root record is an orphan. Design
roots let world records participate before any scene or character exists. Placeholders in full
design and persona forms stay visible as line-numbered findings in JSON `unfilled`: empty labeled
fields, list items, table cells, unchecked audit items and explicit placeholder tokens. Comments
and quoted examples count as unanswered, nested group labels as structure rather than extra empty
leaves, and multiline or code-valued answers as content. `unknown` and `n/a` are examined states
rather than proof of sufficient support, adoption or quality.

Coverage checks declared chapters and scenes, reference and medium agreement, chronology,
character participation, knowledge attribution and phase selection, and reports the applicable
persona with its file hash and gap count when the series is available. Valid shapes include:

- any protagonist count;
- a complete chapter lacking a dramatic trigger and payoff;
- an arc resolved in fewer than two scenes;
- empty cast, theme and arc lists;
- observational scenes;
- deliberate persistence.

Declared references must still resolve.

Errors are contradictions or invalid data; gaps are declared material still awaiting coverage or
review: missing scenes, unused locations, open forms, absent persona files or missing approvals.
A world atlas can legitimately hold locations with zero scenes, and a draft can hold unresolved
decisions. `--strict` exits nonzero for gaps as well as errors; use it as a checkpoint where a
gap-free state applies rather than as a universal completion definition. Both reports are
read-only. The interface review, which judges whether a world's laws, themes, personalities,
associations and causal links convince, belongs to the creative method; perform it there and
state its scope.

## Inspect authorial intent links

Follow [Authorial Intent](runtime/authorial-intent.md) for the creator-facing design and review.
The design register uses `### Intent <id>` headings and the fields of the installed full design
form: status, basis, subject/scope, aim, recognition, variation, cadence, departure policy,
dependencies, conflicts, information boundary, realization links and review basis. Each ID is
lowercase, starts with a letter, contains only letters, digits and hyphens, and runs up to 64
characters; its fragment is `#intent-<id>`. Plain prose remains the source of meaning rather than
a JSON rule engine.

Use a top-level `- **authorial_intent_refs**:` field with ordinary relative Markdown links in the
persona profile, world record or scoped realization note; indented continuation is supported. Use
`n/a: reason` or `none: reason` only for an examined non-applicability. Add the owning entity ID to
front-matter references for lifecycle tracking. Entity rename updates the active links in this field; links inside fenced examples, quotations
and ordinary prose stay as they are, so inspect them after such an edit.

```bash
python scripts/authorial_intent_audit.py --root <project-directory> narrative/personas/<id>.md
python scripts/authorial_intent_audit.py --root <project-directory> narrative/design/project.md --fail-on-gaps
python scripts/authorial_intent_audit.py --help
python scripts/authorial_intent_smoke_test.py
```

Input paths may be absolute or relative to `--root`. The reader visits only explicit Markdown
inputs and the dependencies declared in `authorial_intent_refs`; file size and dependency count
are unlimited by default, and optional operator budgets report an incomplete audit rather than
omit sources. Local `.md#intent-<id>` targets within that root are permitted, including same-file
fragments; URL queries, remote links, root escapes and symbolic links are errors. Instructions,
metadata, quoted examples and fenced examples stay outside the authored intent entries.

The JSON output reports file hashes, intent IDs with field locations and declared statuses,
resolved links, structural gaps and errors, and omits the substantive aim and hidden-plan text; it
remains author-facing metadata rather than an automatically filtered runtime view. Status is
reported as declared, unverified; a link to a proposed, rejected or deferred entry receives a
review note rather than inferred adoption. Scope, precedence, truth and artistic coherence stay
outside the audit, which writes and migrates nothing.

Exit 0 means error-free structure, reads and links, and nothing about readiness; exit 1 reports
errors; exit 2 reports unresolved fields under `--fail-on-gaps` or invalid CLI arguments through
argparse. An unreadable input is reported alongside the inspectable ones, and a missing reference
is reported rather than repaired by guessing. See the hypothetical worked record under
[Authorial Intent Example](../examples/authorial-intent/README.md). The review itself, across
the requested span, follows the route linked at the top of this section.

## Inspect expression drafting hygiene

For individualized voice and body-language work, follow
[Character Performance](runtime/character-performance.md) and the full persona form. The optional
read-only audit takes explicit Markdown paths, including a single persona or unrelated candidate
files; a series, pack, Studio or model is unnecessary:

```bash
python scripts/persona_expression_audit.py <persona.md> [<other.md> ...] [--min-chars 24] [--fail-on-unfilled]
python scripts/persona_expression_audit.py --help
python scripts/character_performance_smoke_test.py
```

It prints JSON with input file hashes, existing line-numbered drafting gaps and `duplicate_groups`
for exact repeated authored descriptions in recognized identity-binding, speech, response and body
fields. Whitespace is normalized; language, case, punctuation and tokens are compared literally
rather than translated or judged for meaning. The length threshold counts Unicode characters and
limits duplicate triage only. Comments, quoted examples, fenced examples, containers and short
examined-state tokens are excluded; tables and custom field names are excluded from the repetition
comparison, while gap detection still checks supported form syntax. Duplicate input paths are
inspected once. Unclosed comments or fences produce advisory `parse_notes` because they can
conceal text; inspect those before relying on an empty report.

`ok` means the inputs were readable, which says nothing about a persona being complete or
distinctive. Exit 0 permits advisories; exit 1 reports input errors, including missing, non-UTF-8
or oversized files; exit 2 is an invalid CLI or, with `--fail-on-unfilled`, a detected drafting
gap. Markdown byte size is unlimited by default; `--max-input-bytes` supplies an optional operator
budget. Repeated text is advisory even in that mode, because shared rules and voices can be
intentional. Similarity scores, emotion inference, overlap resolution, adoption and quality
verdicts are outside the report, and zero duplicates falls short of proof that six voices differ.

The installed full current form owns scoped identity, bodily baselines, conditional responses,
contextual voice modes and performance probes. Resolve portrayal intent and identity bindings
before evaluating a realization; update only the owning record at the authorized creative scope.
Authoring Markdown and shared JSON fields keep their separate responsibilities.

Entity renames also update active `authorial_intent_refs` links throughout regular, non-hidden
project Markdown, retaining their exact intent IDs and declared status; fenced examples, comments,
quoted material and ordinary prose links are ordinary text rather than active bindings and stay as
written, and unregistered prose references remain an editorial concern. Run the intent audit on
affected source records after a rename; a path update is a path update rather than a renewed
portrayal review.

## Read and hand off supported JSON

```bash
python scripts/narrative.py <directory>/narrative/narrative.json
python scripts/narrative.py <directory>/narrative/narrative.json --content-sha256
python scripts/scene_plot.py <directory>/narrative/scenes/<scene>.json
python scripts/scene_plot.py <directory>/narrative/scenes/<scene>.json --content-sha256
```

The shared contract requires typed arrays even when empty. An explicit character arc needs its
character references and its `want` and `need`; an explicit thematic arc needs theme references;
other work may leave those arc types undeclared. Escalation stays optional in the optional arc
development sections. Optional scene `turn` may be omitted or describe a held condition;
`state_changes: []` declares the absence of a persistent consequence. Scene purpose, observed
beats, setting, viewpoint and supported realization are still checked, and satisfying those links
needs only declared material rather than an invented person or event.

`--content-sha256` hashes the JSON with `approved` removed. Scene and downstream prompt source
hashes must match the actual approved inputs. JSON hashes exclude linked Markdown: record and
compare the reviewed versions of relevant design, world and persona files separately, and
re-review affected outputs when they change; after a Markdown change, a JSON approval is
invalidated through that re-review rather than automatically.

## Regressions

Run:

- `python scripts/world_coherence_smoke_test.py` for neutral design/world and non-dramatic
  integration;
- `python scripts/persona_workflow_smoke_test.py` for full-form persona and phase handling;
- `python scripts/narrative_authoring_smoke_test.py` for existing entity lifecycle and coverage.

Shared-reader changes also require the narrative and scene-plot contract suites,
`narrative_corpus.py --check` and `seal_contract.py --check`. Image generation lies outside the
tests.

## Grounded realization plans and bounded recipient views

For persistent source, state and intent coordination, read
[World Realization](runtime/world-realization.md). The local plan references existing event and
process files and hash-pinned world, persona, intent and evidence sources; it is a plan rather
than another narrative or state ledger, created only when useful, and a cast or plot enters it
only when authored.

```bash
python scripts/world_realization.py inspect --root <project> --plan <relative-plan.json>
python scripts/world_realization.py build --root <project> --plan <relative-plan.json> --out <new-output-directory>
python scripts/world_realization.py verify --root <project> --plan <relative-plan.json> --bundle <output-directory>
python scripts/world_realization.py impact --root <project> --plan <relative-plan.json>
```

Ordinary narrative entity rename leaves the plan's pinned file inventory unchanged. After moving or
changing an owning file, review its declared dependency, update the path and hash as an editorial
operation, and rebuild affected views; a stale dependency is repaired that way rather than guessed
or resealed by a consumer. The helper's impact result is conservative. The author-facing bundle
and the individually selected consumer files have different information boundaries. See the
routed contract for fields, limits, exits, examples and tests.

For reusable identity design patterns use [Portrayal Principles](portrayal-principles.md) under
an authorial intent rather than as a personality label or a second persona.

## Prepared scene Persona material

During scene preparation, read the complete applicable Persona definitions, their portrayal model,
authorial intent and current conditions, and save the relevant definition text, cross-definition
dependencies, partner-specific exceptions and scoped applications with
[Scene Persona Material](runtime/scene-persona.md); the saved material records a completed reading
rather than a router's guess at which sections matter.

When a reviewed material bundle is explicitly selected for this task, verify it and use its
`persona.md` for execution, local repair and resumption; rendering the same scene again is by
itself no reason to repeat the full preparation read. Reopen the preparation when sources change,
material is unready, or the work introduces a participant, topic, knowledge, relationship
condition, aim or other condition outside the prepared application. Genre, cast count, speech and
a human model are all optional; missing material is silent on whether the original had a
definition.

The material is authoring input rather than canon or a performer's knowledge; required text is
kept whole rather than silently truncated, a size measure says nothing about semantic
completeness, and full reading and its scope review remain attributed judgments.
