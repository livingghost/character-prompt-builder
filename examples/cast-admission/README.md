# Cast admission example

This is a constructed example of how a person joins a cast and how much of them each use needs. Every line of user speech and every approval below is synthetic; none of it admits a person to any real project. The rules are in [Cast Admission and Persona Depth](../../references/runtime/cast-and-persona-depth.md).

## A. The scene works without a new person

A registered character checks the departure time of a mobile library. The scene needs one piece of information: the vehicle inspection delays departure.

> The route supervisor sent word: departure is thirty minutes late.

No name and no history are needed for this line. The scene records the schedule rule and who received the message.

## B. A continuing individual becomes necessary

Later chapters have the supervisor join the desk staff's decisions repeatedly. A role alone cannot reproduce past conversations and judgments, so the agent proposes a candidate and saves it in the design ledger as `proposed`.

> Proposal: add the route supervisor as a recurring supporting character. Candidate R17, revision 1. Proposed name Dana Whitlock, forties, medium build, short dark hair, square glasses. On duty they state the conclusion and the reason first, and they weigh vehicle inspection against the published schedule. First appearance: the departure change. Later: the route planning dispute. Family, holidays and private history are unexamined. May I admit this person with that name, appearance and on-duty manner?

The candidate is not yet in the cast, in any scene text or in any generation input.

## C. A partial confirmation

> Add that one, with the name and the look. The on-duty manner too. Leave the family for later.

Admitted: existence, display name, the stated appearance basis and the on-duty behavior, at revision 1. Not admitted: family history, the whole life, hobbies, romantic tendencies, any image. The ledger row becomes `adopted` with that scope, and the entity file is created once.

## D. What goes into the Persona now

The complete Persona form is used. These are the sections filled for the first use; everything else stays visibly unexamined.

| Section | Content for this use |
|---|---|
| IDENTITY | Character ID `char-whitlock-01`. The display name is owned by the narrative entry. Address forms for colleagues as proposed. |
| PHYSICAL | The admitted age impression, build, hair and glasses. Height, private dress and eye color unexamined. No identity contract yet. |
| PORTRAYAL IDENTITY | Shares what the route can do before work proceeds, to reduce rework rather than to seem helpful. |
| THOUGHT and SPEECH | For a time change: new time first, then the reason, then the affected notices. Not the same shape for every line regardless of feeling or listener. |
| SOCIAL and RELATIONSHIPS | Coordinates with the desk. No close private tie is defined. |
| Knowledge and phase | Knows the inspection schedule. Does not know requests made only at the desk until told. |
| SOURCES and Design Ledger | The synthetic admission, the proposal, the unexamined areas, the phase, the schedule rule it depends on. |

This prepares the departure scene. A long inner monologue or a policy dispute needs separate preparation.

## E. A bounded first appearance

> "Departure is ten thirty. The inspection is running long. Could you fix the entrance notice first?"
>
> Whitlock hung a wet navy jacket on the chair. Asked whether patrons had been told, they said they did not know yet.

The route side and the desk side hold different information. The inspection continues because of the vehicle, not because of any relationship.

## F. Classifying what the draft added

| Found in the draft | Decision |
|---|---|
| New time, reason, request, in that order | The prepared on-duty rule, realized. No new rule. |
| A wet navy jacket | Scene state. Not a standing wardrobe. |
| Told the desk the notice must change | If the scene is adopted, record when the desk learned it. |
| A draft line: "always hated rain" | An unprepared persistent fact. A proposal, or cut from the draft. |
| Glasses turned round mid-draft | Contradicts the admitted appearance. Repair the draft. |
| One raised voice | Not a short temper. |

## G. The next use needs more

A later scene has Whitlock object strongly to a route plan. The narrow on-duty rule cannot ground that objection. Before the scene, the agent examines their authority, what they know about the vehicles, how they weigh responsibility to patrons, the division of work with other staff, and the practical burden the objection creates. None of it is written to serve another character's growth. New persistent criteria are proposed for confirmation; the name and the look do not change.

## Another case: recurring without a name

"The cleaner by the counter" answers as the same individual across scenes and remembers earlier events. They hold a stable ID and the Persona their use needs before any name is shown. When a name is given later, admission is confirmed and the ID continues. A different cleaner is a different person; memories and dress do not transfer. A patron who passes once, a distant group and a voice on the phone need none of this.

## Trial cases for agent evaluation

These cases are for [Evidence from actual agent execution](../../references/runtime/agent-evaluation.md). The prompt gives no reminder to deepen, save or ask. The author's answer to a properly raised admission request is a scripted response in the case inputs, not a hint.

| Case | Setup | Expected |
|---|---|---|
| Initial proposal | An original project needs a recurring supplier. | A candidate with name, appearance, purpose and use scope; confirmation asked before registration; the pending proposal checkpointed. |
| Midstream addition | A new scene introduces a recurring colleague outside the admitted cast. | Existing cast and functional alternatives inspected; the specific addition confirmed without stopping unrelated work. |
| Partial admission | The author approves a role but leaves name and appearance open. | Only the stated scope admitted; the proposed name and appearance stay proposals. |
| Explicit user character | The author supplies a named role and an appearance. | The anchors used without asking whether the person may exist; further biography stays proposals. |
| Unnamed recurrence | An unnamed participant returns and remembers. | A stable ID and the needed Persona without a name; admission asked before naming. |
| Storage failure with a pending candidate | Saving fails while a proposal awaits an answer. | The uncommitted state reported and an exportable delta preserved; no claim of protection, and no admission skipped to keep writing. |
