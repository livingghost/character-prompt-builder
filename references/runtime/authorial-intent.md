# Authorial Intent, Portrayal Identity and Deliberate Change

## Activation and responsibility

Read this route when establishing or revising how a work, subject or recurring pattern is
portrayed, when diagnosing identity drift, or when selecting among plausible realizations; also
when constancy, a contrast, a rupture or uncertainty about identity is the point of the work.
Read the adopted design and world records, and for an individualized agent the complete persona
and its applicable phase; this route supplements those authorities rather than replacing either.

This is an authoring rule rather than a claim about a person's psychology, and it leaves cast,
protagonist, relationship, genre, theme, anatomy, communication mode, growth arc and emotional
range to the work. An unpeopled landscape, process, institution, object, narrator or visual
pattern can have a portrayal aim while lacking a mind, and a work may deliberately leave its
identity unstable or undecidable.

[World-Coherent Creative Development](narrative-development.md) owns the whole-work method;
[Character Performance](character-performance.md) resolves individualized moments; the
[Project Design Template](../../templates/narrative/design/design-template.md) owns the
**Authorial intent register**, of which persona section 2 holds an interpretation rather than a
copy.

## 1. Distinguish four kinds of claim

| Kind | Meaning and owning record |
|---|---|
| Established conditions | What exists, happens or is possible in the declared continuity. World, narrative, visual identity and state records own these facts at their respective scopes. |
| Subject identity | What makes this subject continuous or recognizable, including scoped values, dispositions, patterns and uncertainty. Persona section 2 owns an individualized subject's profile; non-agent subjects use their world record. |
| Authorial portrayal intent | What the creator chooses to sustain, contrast, reveal, withhold or disrupt in the audience's experience, and why. A scoped design intent owns this, whether or not a subject knows or understands it. |
| Realization | The particular words, timing, acts, viewpoints, shapes or omissions used in this output. Scene and performance records apply the first three without becoming their new source of truth. |

A motive leaves the voice open; a visible signature leaves the motive unproven; plausible
psychology alone leaves the intended portrayal unselected. Production convenience changes no
fact, user anchor, adoption or actual capacity on its own: expose such a proposal and its
dependencies before adopting it.

An author may choose restraint, stylization, exaggeration or ambiguity over naturalism; a
vulnerability, a contrasting trait, a hidden wound or an expressive cue stays optional.
Source-based analysis separates evidenced portrayal from conjecture about the original creator's
intention. For real people, record-based facts and uncertainty constrain portrayal, which rules
out an invented inner core or dramatic framing presented as verified psychology.

## 2. Define an identity by scope and selection criteria

Ask what this work needs to preserve about the subject or pattern rather than what would stay
fixed in every possible story. Specify continuity, phase, place, viewpoint, medium and other
boundaries only where relevant; a work-wide identity and a phase-wide presentation can have
different scopes, and a record can leave a stable center unspecified, since a universal lifelong
essence is optional.

A usable portrayal aim selects between plausible alternatives; 'interesting', 'consistent',
'confident' or 'individual' alone selects nothing. State what should remain perceptible, what
variation belongs to that portrayal and what would materially change it, keeping the actual
language and available channels in view. A signature is not a compulsory catchphrase, pose or shot.

Constancy and switching can each be the organizing identity. A presence that stays steady through
different emotions is a different design from a usual informality that turns into focused
assurance at selected moments, even with an identical decisive line. Continuity with surrounding
moments carries the first; the transition and contrast carry the second.
Neither mode has to be a mask or a more authentic self. This illustrates a distinction rather than an approved
character pair or a taxonomy every project must adopt.

Specify meaningful invariants and the intended pattern of variation together. For example:

- an address form may hold while sentence structure changes;
- a principle may persist while its expression changes;
- a location may keep its spatial logic while the telling changes its mood.

Which channels change stays open: requiring all of them to change, or one particular channel to
stay fixed, is a choice rather than a rule.

## 3. Persist the actual design intent

Use the **Authorial intent register** in a design record. Each entry has a stable lowercase ID, a
heading `### Intent <id>` and the link target `#intent-<id>`. Use the exact fields in the project
design form. They hold:

- the subject and scope, declared status and actual basis;
- the portrayal aim, recognition anchors, variation envelope, contrast and cadence;
- departure policy, relevant world/subject dependencies and unresolved conflicts;
- the information boundary, affected realizations and review basis.

`proposed`, `adopted`, `user-anchor`, `rejected` and `deferred` describe the author's recorded
status, and a tool reports that word as written. Delegation to invent is different from
retrospective adoption, and a sample is not independent evidence for its own rule.
An unexpected draft choice was unplanned; after honest review it can become a new proposal, with
its actual basis recorded.

Use `authorial_intent_refs` in a persona, world record or scoped realization note to link the
relevant entries with ordinary relative Markdown links. Example from a project persona:

```markdown
- **authorial_intent_refs**: [scoped portrayal](../design/project.md#intent-i-pattern)
```

Also name the design entity in the record's front-matter `references` when using the narrative
index. The index tracks entity IDs; the intent audit checks the finer file and intent links;
neither reads applicability from prose.

Keep one owner for a decision:

- the design ledger refers to an intent ID instead of repeating its status and rule;
- persona section 2 interprets the adopted intent for this subject and binds its own response,
  voice and body rules to that interpretation;
- individual factual or internal traits stay in persona;
- world laws stay in world records.

A standalone conversation can use the same structure unsaved; save the scoped record when a
persistent project is requested.

## 4. Resolve a moment under the intended identity

Before a consequential realization, identify:

- the applicable intent IDs and their status;
- the current identity profile;
- relevant world and state constraints;
- the request's change boundary.

Resolve what the moment should sustain, contrast, reveal, withhold or disrupt, then choose the
actual voice, body and form within the permitted range. This is an author-side selection rather
than dialogue for the character's mouth.

For each materially used conditional response or voice mode, record how its held and changed
components realize the identity profile and governing intent; a shorthand reference to section 2
suffices when it unambiguously identifies the relationship. Conditions such as emotion, addressee,
audience and fatigue activate rules; a new identity needs its own scoped decision. A convincing
explanation for a local reaction can still be wrong for the adopted portrayal aim.

If two instructions conflict, compare their explicit scopes, applicability, statuses and sources;
a narrower instruction overrides another only when an actual scoped decision authorizes that
exception. A computed universal author, theme, world and emotion hierarchy, or an average of
contradictions, is outside that resolution. Resolve, propose or retain a reported open issue as
the requested output needs, and leave unrelated anchors unchanged rather than quietly bending
them to make a favored line work.

## 5. Distinguish variation from a deliberate departure

Treat these as review descriptions rather than an exhaustive enum of possible stories:

| Operation | Question to answer |
|---|---|
| In-range variation or designed contrast | Does this perform a mode or boundary already contained in the adopted identity? The contrast itself need not be a break. |
| Disclosure | Does the audience learn something while the underlying identity or world condition remains unchanged? Keep audience knowledge separate from a change in fact. |
| Scoped disruption | What normally held pattern is disrupted here, for what authored purpose, and what remains? A disruption may be unexplained to the audience. |
| Lasting change | Which established traits or conditions change, from when, with what continuation or uncertainty? Use the appropriate phase/state/world owner. |
| Editorial redesign | Which creator decision is revised? This is not automatically an in-world event or a memory the subject gains. |
| Deliberate indeterminacy | Which boundaries of interpretation remain open, and what would prematurely settle them? Do not manufacture an invariant solely to close the record. |

For a consequential departure record its aim, exact scope, affected and retained dimensions,
necessary conditions, audience treatment, and aftermath or explicitly withheld aftermath. Link
the owning decision and affected outputs. A separate intent entry can own that exception instead
of every persona mode copying it. A rule's `departure_policy` states what requires a new scoped
decision and leaves departures possible. An adopted exception does not erase the general rule.

An unexplained break, unreliable narration or abrupt tonal shift can be intentional, and its
author-side record can be precise even when the audience is told nothing. A surprising reaction
proves nothing about a hidden 'real self', and an accidental inconsistency is an inconsistency
rather than another side of a person.

## 6. Review the pattern across the requested span

A local beat can fit while the accumulated portrayal loses its center. Review the actual sequence
or set of outputs at the scope the request needs, including ordinary, consequential and
intervening moments where available. For a one-off artifact, review its framing and intended
reference context instead of manufacturing a series; a gap in evidence stays a gap rather than a
reason to invent scenes.

Inspect what is repeatedly foregrounded, what is conspicuously omitted, how transitions are set
up or intentionally left unset, and what remains after them. A mode intended to be exceptional
can lose its contrast once it becomes every scene's default; a steady presence can be lost
through repeated small reactive flourishes even when each is individually plausible; repetition
can also be exactly the chosen form. Cadence is authored rather than a numerical seriousness
ratio or gesture quota.

Compare actual realization with the aim, beyond dossier wording. Use held-context and
new-situation probes from the performance route, and add a multi-moment review of constancy,
contrast and a deliberate departure when those are in scope. Where a different expression channel
is actually requested, test whether the intended center survives with its most obvious cue
removed. Two subjects, visual generation and a blind-identification pass score are all optional.

Record in a **Portrayal review**:

- sources and hashes inspected;
- the selected span;
- observations;
- counterexamples;
- decisions;
- unchanged material;
- unresolved risks.

A favorable invented example alone fails as evidence that a running narrative maintains the
intended identity.

## 7. Keep author knowledge and downstream access separate

An author-facing record may contain future, alternative or concealed material. Labels such as
'author-only' are labels rather than access control: for a limited-viewpoint or current-phase
consumer, construct a scoped view holding only the applicable adopted instruction and the
information that consumer may receive. Remove concealed answers and future outcomes, including
revealing negative constraints, rather than sending the whole register with a request to ignore
parts of it. An image prompt receives only the selected visible and performance intent, which
excludes a future resolution and a character's unshown knowledge.

A plan for a future rupture leaves the present unchanged; an audience's misreading stays outside
world fact; an intentionally ambiguous outcome may require withholding both interpretations.
Retain the author-side owner separately and record which fields or entries were actually
supplied.

## Inspection and revision

[Narrative Authoring](../narrative-authoring.md#inspect-authorial-intent-links) documents
`scripts/authorial_intent_audit.py`: explicit inputs, bounded local dependencies, intent IDs,
required fields, declared statuses and fingerprints. The report, like every script in this
route, is author-facing and read-only: it establishes declared links and text completeness, and
leaves consent, precedence, adoption, identity scoring, approval, spoiler-safe views and artistic
success to the author. Use `python scripts/authorial_intent_smoke_test.py` for current-contract
structural tests.

On revision, update the owning intent and relevant identity and rule bindings, review the
affected span, and refresh dependent summaries or projections. A linked Markdown edit leaves JSON
approval to that review rather than to automatic invalidation. Record actual reviewed versions
and unresolved impact; a hash is change-detection evidence rather than a semantic guarantee.
Templates and authoring commands define a single current contract, free of alternate layouts,
aliases, version adapters and migration routes.

## State-backed realization and reusable patterns

Use [World Realization](world-realization.md) when an intention is applied across explicit state
boundaries or depends on source provenance. Pin the owning intent and subject and world files,
resolve the appropriate state targets and author the local instructions for each recipient. The
helper exports only selected scalar state fields and explicit instructions; review the actual
body for what those selections reveal and how well they implement the intent.

[Portrayal Principles](../portrayal-principles.md) provides reusable design patterns for constancy,
contrast, contextual expression, gradual change, disclosure, rupture and uncertainty. Record
selected IDs and their local interpretation in the design workspace; the intent owns adoption and
the actual rule, and the dictionary stays guidance rather than an alternate source of truth. A
reference-state key identifies only its chosen facets rather than an inner core or success in
realizing a creator's aim.

On revision, `world_realization.py impact` can identify source-dependent units; recompile and
inspect the affected actual outputs. This bookkeeping is bookkeeping: an editorial redesign stays
an editorial redesign (see the table in section 5), and canon changes stay the author's. Use the
realization review form for explicit observations, retained dimensions, bounded corrections and
candidate selection.

## Prepared scene Persona material

During scene preparation, read the complete applicable Persona definitions, their portrayal model,
authorial intent and current conditions, and save the relevant definition text, cross-definition
dependencies, partner-specific exceptions and scoped applications with
[Scene Persona Material](scene-persona.md); the saved material records a completed reading rather
than a router's guess at which sections matter.

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
