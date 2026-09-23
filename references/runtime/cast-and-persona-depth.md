# Cast Admission and Persona Depth

Activate this document when a work gains or loses a person:

- an agent proposes a new named character;
- an unnamed participant starts to recur;
- a scene needs more of a person than the Persona holds;
- a finished scene contains something about a person that no record holds yet.

[World-Coherent Creative Development](narrative-development.md) owns the creative method. [Narrative Authoring](../narrative-authoring.md) owns the files and commands. The complete [Persona Template](../../templates/narrative/personas/persona-template.md) owns individual portrayal. This document owns who joins the cast, on whose decision, and how much of a person each use needs.

## Contents

- [Four separate questions](#four-separate-questions)
- [Before adding a person](#before-adding-a-person)
- [Admission: the author decides who joins the cast](#admission-the-author-decides-who-joins-the-cast)
- [One Persona structure, depth by use](#one-persona-structure-depth-by-use)
- [Before an appearance](#before-an-appearance)
- [After an appearance](#after-an-appearance)
- [Time and ownership](#time-and-ownership)
- [Checks and limits](#checks-and-limits)

## Four separate questions

Narrative importance, having a name, continuity and required depth are independent. Answer each on its own:

| Question | What settles it |
|---|---|
| Does this person matter to the work? | The design frame and the scene at hand. |
| Do they have a name? | The author. A name the agent proposes stays a proposal. |
| Do they persist as one individual? | Whether the same person acts, remembers and is recognized across scenes. A recurring person with no revealed name still needs a stable ID. |
| How much must be authored now? | The use at hand: a mention, one bounded scene, recurring appearances, or a consequential choice. |

A crowd, a one-line functional participant and a background process stay impersonal. A stable character ID belongs to every continuing individual, and identity lives in that ID. A name, a title, an alias or a change of prominence leaves it as it is.

## Before adding a person

When a scene exposes a missing role, inspect the existing cast and world records first, and choose the smallest thing that meets the need:

1. an existing person, compared on their actual role, phase, access and availability;
2. an unnamed functional participant, when nothing about them will recur;
3. an impersonal condition such as a timetable, a room or a procedure;
4. a new continuing individual.

A reused person keeps their occupation and knowledge; anything new about them is a proposal. A new person who acts as a person has a present purpose of their own. A job title is a position, and the purpose is what they want there today. A person invented only to explain the focal relationship points to a gap in the world.

## Admission: the author decides who joins the cast

The agent may draft a candidate and save it. An agent-created named person joins the active cast only after the author confirms that candidate, at initial planning and during later expansion alike. A request to deepen the world permits proposals; admission is a separate answer to each listed candidate. Praise of a draft adopts the facts it names. A permission covers the candidates it names, at the revisions it names.

A person the author names directly is a user anchor within the stated content. Ask only for the missing material the task needs.

Record a candidate as a decision in the project design ledger of the [Project Design Template](../../templates/narrative/design/design-template.md) with status `proposed`, before any entity file exists. The candidate carries:

- a candidate ID and the revision of the proposal;
- the role, the person's own purpose, the expected use and continuity;
- why an existing person or an unnamed function does not meet the need;
- the proposed name, a recognizable appearance and the relevant voice or behavior;
- the unresolved fields and the exact scope the agent asks the author to admit;
- the dependencies the candidate introduces.

Present the candidate as a worked proposal the author can accept, change or refuse. Several candidates can be decided in one batch when each is listed. A clearly labeled hypothetical sample may show the candidate; it stays a sample.

### Scope of a confirmation

Record the author's decision against the proposal revision and the exact scope. Admission, the name, the appearance, the history, an accepted image and publication are separate decisions:

| The author says | What is admitted |
|---|---|
| "Add this one, with that name and look." | The person, the name and the stated appearance, at this revision. |
| "The role is needed; the name can wait." | Existence and role. The name stays open. |
| "Different look, please." | Admission stands. The appearance goes back to a proposal. |
| "Think about supporting people too." | Permission to propose. Nothing is admitted. |
| "One and three." | Those candidates at their listed revisions only. |
| No answer, or an answer whose target is unclear. | Nothing. Save the candidate as pending and ask once, narrowly. |

A candidate that changes materially before the decision is a new revision; the earlier approval covers the earlier revision only. An admitted person who is later revised keeps their admission and receives a separately scoped fact or redesign decision. Detail the author explicitly delegated is recorded as delegated; unspecified facts remain proposals.

### While a decision is pending

Save the candidate, the request that produced it, the decision asked for and the next safe operation in the work trail. Keep the candidate out of ordinary story text, current world state, another character's knowledge and generation input. Continue the work that is independent of the decision. A rejected person stays rejected under any name, and so does their biography.

A recurring unnamed individual receives a stable ID and the Persona their use needs, without a revealed name. Ask before an incidental role grows into a consequential continuing individual, since that materially expands the cast; ordinary incidental action needs no per-person approval. When such a person is later named, keep the ID and carry the history forward. Two people with one job title or one name stay two people. Retirement keeps provenance; deletion, replacement, merge, split and retcon each need an explicit impact review.

### Registration after admission

After admission, create the entity once with `narrative_entity.py add persona` and set the narrative's character pointers, as [Narrative Authoring](../narrative-authoring.md) describes. The design ledger row moves to `adopted` with the admitted scope and names the character ID, so a candidate and a registered person correspond one to one and a repeated request creates no second person.

## One Persona structure, depth by use

Every portrayed person, lead or supporting, uses the same complete Persona form and the same identity rules. Depth follows use rather than billing: a supporting person making a consequential choice may need deeper preparation than a lead exchanging a greeting. Unused sections stay visibly unexamined. The form's field states keep their exact meanings, and a field holds examined content or stays visibly open.

| Use | Prepare before it | May stay unexamined |
|---|---|---|
| A mention by name | Stable identity, the mentioned facts, the time they hold | Appearance, inner life, dialogue samples |
| One bounded scene | The judgment, appearance, voice and knowledge that scene needs | Unused family history, the long past |
| Recurring appearances | Prior outcomes, daily life, their own purposes, changed relations and conditions | The whole life in detail |
| A consequential choice, inner view or long dialogue | The values, motives, competing duties and boundary cases behind that choice | Exhaustive material unrelated to the main line |

A depicted named person needs a coherent, recognizable appearance basis: species or kind, age impression, build and the outline of dress, as the use requires, rather than a checklist of eyes, hair, scars and measurements. Prose may leave an appearance unshown; an image that claims canonical identity needs a specified face. A withheld name or appearance is separated into the author's definition and what the audience is shown.

### Ready for a use is not complete

A Persona may be ready for one declared use while incomplete overall. The prepared [Scene Persona material](scene-persona.md) is that readiness record: it binds the character and phase, the complete source hashes, the medium, the scene and the definitions read. The Persona Template's completion rule applies to a released persona. Each label is declared on its own, and a readiness verified for one scope is re-examined when the scope widens, for instance when a person first appears in an image.

Full reading means the full applicable source. A small supporting Persona is read in full, and so is a large one, whatever the person's prominence.

## Before an appearance

Resolve the character ID first; a remembered name is a lookup key. Read the applicable Persona, world records and established consequences. Check for duplicate candidates, stale preparations, a changed phase, hidden information and unresolved admission.

When the scene needs a new load-bearing motive, memory, appearance fact, ability or relationship, propose it and settle its scope before an adopted rendition relies on it. A decisive act written first and justified afterward is a design made backwards. A provisional scene may explore unresolved content when it is labeled and kept apart; its branch-specific choices stay stable until changed and stay branch choices however often they recur.

## After an appearance

Compare the actual draft with the definitions it was written from, and classify every difference before anything is written back:

| Difference | Handling |
|---|---|
| An existing rule realized | Reference the rule. Add no duplicate. |
| A temporary outfit, fatigue, place or prop | Scene or current state. Not stable identity. |
| Information the person acquired | Link to the established event, the knowledge access and the effective time. |
| A new habit, preference, history or tie | A proposal for a persistent fact, applied only under actual adoption or explicitly delegated authority. |
| A contradiction with the current definition | Repair the draft within scope, or obtain a separately scoped redesign. |
| An inferred inner state | An inference. An observed cue establishes no hidden truth. |

An accepted scene adopts the scene; its incidental permanent traits stay proposals. One line proves no habitual voice, one action proves no value, and a rendered detail adopts no visual canon. Store pending additions before the next appearance: reviewed stable additions in the owning Persona or identity decision, scene events in the scene and state owners, and a work trail entry that references those decisions without becoming a second ledger. Provisional additions stay readable as the branch's held choices until they are adopted or dropped.

## Time and ownership

Separate recording time from story-effective time. A past fact authored late is an editorial addition with its own effective time; earlier chapters keep the knowledge they had. A sustained change opens a phase with the unchanged dimensions retained, and a temporary mood stays state.

Each fact has one owner, as the creative method's record homes state:

- the narrative character entry owns the stable ID, the display name and the Persona pointers, and the Persona heading mirrors the name;
- the Persona owns language-bound self and address forms and behavior;
- the declared appearance lives in the Persona's PHYSICAL section until an adopted identity contract or sheet takes authority over stable geometry and markings, and that transfer is recorded with a source-bound summary left behind;
- world, scene and state owners keep their facts;
- the work trail links decisions without duplicating them.

A rename keeps the ID. Renaming an entity updates the references [Narrative Authoring](../narrative-authoring.md) lists; prose and ledger text are reviewed by hand.

## Checks and limits

The index and coverage reports verify IDs, references, decisions and input versions. Consent and adequate portrayal are read by the reviewer from the actual decision and the actual draft. Report pending admission, insufficient preparation for a use, stale sources and failed persistence separately, each by its own name. A worked, synthetic example is under [examples/cast-admission](../../examples/cast-admission/README.md).
