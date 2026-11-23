# Continue a production result

Use a saved work plan for a requested artifact, a retained candidate, an image
revision or a sheet batch. The author selects the source and intended result
once. The runtime carries preparation, execution, review, selection, adoption,
view refresh and work completion through their existing owners.

## Contents

- [Begin and continue](#begin-and-continue)
- [Select the commissioned result](#select-the-commissioned-result)
- [Create several distinct images](#create-several-distinct-images)
- [Revise the result or items](#revise-the-result-or-items)
- [Author and revise inputs](#author-and-revise-inputs)
- [Authorize an exact request](#authorize-an-exact-request)
- [Observe and review](#observe-and-review)
- [Select and adopt](#select-and-adopt)
- [Continue a sheet batch](#continue-a-sheet-batch)
- [Finish and recover work](#finish-and-recover-work)
- [Inspect effort and repeated attempts](#inspect-effort-and-repeated-attempts)
- [Public request contract](#public-request-contract)

## Begin and continue

Run these commands in the locked Skill environment. `STUDIO` is an initialized
Studio. Select one source and its result directly; the runtime writes the plan
request and its bindings. For new authored work:

```bash
python scripts/production_workflow.py plan --root STUDIO --request-file request.txt --route prompt-only --scope save --fresh-context
```

For actual image creation through an available host tool whose target is not
in the model catalog:

```bash
python scripts/production_workflow.py plan --root STUDIO --request-file request.txt --route generation --execution external --feature unlisted-interface --scope delivery-only --fresh-context
```

The returned draft owns the exact external target and request. Complete its
`target.kind: "external"` evidence using the host's exposed contract. The
`--model` option selects a catalog record; omit it for an unlisted interface
and never fill it with an invented backend name. `prepared-input` stops before
image execution; `delivery-only` continues through the actual result and review.

Route names belong in `--route` or `source.route`; knowledge feature names belong
in `--feature` or `source.features`. The plan checks every requested item's
explicit names before opening work or saving a plan. A misplaced or unknown name
returns the affected source pointer and its repair; correct that request and retry.
For several separately editable images, use [named items](#create-several-distinct-images).

For a retained reviewed result whose actual destination is a character sheet:

```bash
python scripts/production_workflow.py plan --root STUDIO --run RUN --scope sheet --influence identity
```

After the applicable plan command, continue the result with:

```bash
python scripts/production_workflow.py advance --root STUDIO
```

If preparation is blocked after the stage becomes structurally ready, the plan
shows the actual compilation findings and their input owners before its detailed
items. Follow the returned `check --choices` action, repair those named fields,
and use `plan_continuation` to try the same plan again. Structural readiness is
not final publishability. A reserved run is retained for that retry; it is not a
published result or a reason to create another plan. Status can show these input
blockers even while `runs` is empty. It compares the saved failure's exact choices
and authored-file references with the inputs it just acquired; after an edit it
offers a fresh check instead of asserting that the old findings still apply.
The retained findings describe the last failed preparation. Displaying them
does not revalidate the current packs, external state or execution authority;
checking and the actual effect owners still perform their current validations.

`--request-file` contains the actual
UTF-8 commission, not a JSON envelope. `--choices` selects an existing editable
draft and `--batch` selects a saved sheet batch. Each source requires `--scope`;
sheet and catalog also require `--influence`. `--candidate` explicitly selects
a result of `--run` when needed; omission leaves the ordinary candidate choice.
For new or revised requests, `--feature` is repeatable and `--from-run`,
`--operation`, `--execution`, `--model` and `--service` retain their authoring
meanings. A retained amendment can also declare repeatable `--retain` and
`--change` owners under [retained amendment scope](production-authoring.md#declare-a-retained-amendment).
`--goal` supplies the actual new task for later use of completed work.
Catalog use also names `--registration-file` and `--pack-dir`; requested local
authored delivery can name `--delivery-path`.

Begin at this plan before directly reading all linked runtime documents. Its
current route delivers the complete sections needed for the actual stage.
Execute the returned `argv` with the host's command runner. Read the `body`
pages and use their continuation; custom document-slicing programs are not
part of this workflow. Keep the Studio as the working directory. Editable
files are relative to `--root`; guidance and schema paths belong to the Skill
directory, and absolute paths are used as printed.

The current authoring and curation reading actions start complete paged delivery directly.
`actions.continue` advances that delivery. From an index or after a selected
section ends, `actions.next` reads the complete remaining scope in bounded
pages; individual heading selection is optional. `actions.index`
opens the complete source scope and navigation. Replay and fresh-context
restart remain available, with no change to the required source bytes.
Execute these complete actions without appending the original route, feature,
model or choices flags: their cursor already owns that selection. A
`READING_INVOCATION_CONFLICT` returns the saved owner and a corrected `resume`
action when the invocation's context matches. Run it unchanged in that same
context. A fresh or unselected context receives `restart`, which reads the
required bodies again and retains the authored work. The refusal delivers no
body and issues no reading; repair the invocation rather than rebuilding its
plan or re-entering its source selections.
After an explicitly selected section ends, input inspection offers the remaining
complete scope in bounded pages. A section's end does not require visiting every
remaining heading separately.

`--fresh-context` starts an explicit reading context. Follow returned actions;
they carry its `--reading-context` ID across this uninterrupted context and
automatically select complete applicable readings. The reader delivers missing
or changed ranges and reports required, reused, delivered and remaining bytes
with the selection reasons. Start again with `--fresh-context` after compaction
or a new context. A saved plan never treats its stored receipts as inherited
knowledge, and earlier completed production decisions remain retained.

Generated choices-based reading actions include `--bind-choices`. Complete
delivery writes the issued key to that exact unchanged draft automatically.
The binding checks its task, stage, selected source and target scope; a changed
editor is reported at its owner rather than overwritten. For host capacity
declared in source-text bytes, use `--page-bytes auto --host-page-bytes N` and
reserve separate output room for JSON metadata. A larger page budget does not
permit truncated or unread material to count as complete delivery.

For several independent or dependent results or an imported artwork owner, use the complete
declaration below in a UTF-8 JSON file inside the Studio:

```bash
python scripts/production_workflow.py plan --root STUDIO --file work-request.json
```

`plan` returns the saved `plan` path. With no `--file`, `advance` selects only
the active task's bound plan. Retain the returned path to resume a suspended
task or inspect a completed plan:

```bash
python scripts/production_workflow.py plan --root STUDIO --file work/plans/PLAN/plan.json
python scripts/production_workflow.py advance --root STUDIO --file work/plans/PLAN/plan.json
```

`plan --root STUDIO` locates the active plan. When none exists, it writes a
small unanswered `work/plan-request.json` and returns its concrete `plan`
action. Select its source and actual result before following that action.

With an existing plan file, `plan` reads the current editable input again and
refreshes its authoring stage, selected scope, diagnostics and actions. The
original request and plan definition remain unchanged; current choices own
later input edits. This refresh leaves the authoring stage in place and
prepares no new run. A registered, verified run reserved by this plan takes
precedence over rereading its editor, with its source and work task checked.
An incomplete publication retains its reservation and returns the same
`advance` action for recovery.
Each item's input inspection acquires that exact selected editor. Other
registered drafts remain reachable as comparison actions, without repeating
their content or diagnostics inside every image's current inspection.

`plan` also refreshes changed pending judgments without sending a request or
applying a selection. It writes a new answer revision, links the previous
answer and preserves committed effects. Use this returned `refresh_action`
when approval, review or placement changed. Record the current reason and
any newly unanswered conditions, then continue with `advance`.

At a judgment boundary, the report names `current.answer_file`, the evidence
and the reason for that judgment. Complete that file from the actual request
and observations, then run the same `advance` action. The runtime retains the
run, hashes, reviewed candidate, current placement, authority predecessor and
individual operation records separately. Those generated bindings require no
editing. An unchanged answer returns the same normal continuation.

Each item also reports its exact `source`. While a judgment remains open,
`current.choices` and `current.run` name that same selected input and its saved
run. `previous_sources` retains earlier input branches for explicit inspection;
they never become the next operation merely because their files are newer.

The report describes the whole requested result. `needs-input` names the
current authored judgment, `pending` names a dependency or existing external
operation, and `blocked` names an actual inconsistency with its repair. A
`complete` plan has verified results and a closed owning work task. Existing
free-form work can produce `work-required` until its actual remaining steps
or questions are resolved. `verification-required` identifies inconsistent
saved results or derived views that need their owning repair.

Explain progress through actual deliverables: distinguish saved prompts,
prepared requests and returned images. State how many requested images have
actually returned and the next pending operation in the user's language. For
example, when only text exists: "The three prompts are saved. No images have
returned yet. I am preparing their separate image requests." Preparation or a
completed reading does not mean an image has been produced.

Session startup offers this plan for open work that has no plan yet. Direct
ledger completion applies only when the commissioned scope is already
fulfilled. Continue a plan while review, selection or canonical adoption
remains part of that scope.

## Select the commissioned result

For one item, the request contains only `source` and `result`, with optional
`goal` when opening new work. These are complete synthetic examples; replace
the selected paths and IDs with actual sources.

A reviewed retained candidate for a character sheet:

```json
{
  "source": {"run": "RUN"},
  "result": {"scope": "sheet", "influence": "identity"}
}
```

An editable draft whose requested result is the complete prepared input:

```json
{
  "source": {"choices": "work/draft/choices.json"},
  "result": {"scope": "prepared-input"}
}
```

New authored work starts from the actual commission in `request.txt`:

```json
{
  "source": {
    "request": "request.txt",
    "route": "prompt-only",
    "execution": "authored"
  },
  "result": {"scope": "save"}
}
```

When no work task is open, its goal comes from that actual request. The plan
opens meaningful preparation, result and verification steps and binds them to
their formal evidence. The author still develops the character, depiction and
prompt in the ordinary editable files.

| Result scope | Completion owned by the plan |
| --- | --- |
| `save` | The authored revision and every delivery/review obligation declared by its task |
| `prepared-input` | Complete verified saved input, ready for separately authorized later execution |
| `delivery-only` | Reviewed selection and its production completion |
| `studio-slot` | Reviewed selection, the exact Studio slot receipt and production completion |
| `sheet` | Reviewed selection, Studio receipt and a separately recorded sheet adoption |
| `catalog` | Reviewed selection and the separately authorized catalog registration |
| `withdraw` | The exact canonical withdrawal, retaining the image and its history |

Sheet and catalog use also selects the intended `influence`. Catalog use
supplies its actual `registration_file` and destination `pack_dir`. An authored
task requiring local delivery can name the destination in `result.path`.
An actual external presentation keeps its observed receipt instead.

Imported Studio artwork uses
`{"kind":"imported","character":"CHARACTER","iteration":"ITERATION"}`
as its source. A local sheet candidate uses
`{"kind":"sheet","sheet":"sheet.html","slot":"SLOT","artifact":"ARTIFACT_ID"}`.
A withdrawal names that exact source owner and `result.scope: "withdraw"`.
Production-owned candidates retain their Production run and candidate source.

## Create several distinct images

For separate commissioned images, give each image a named item with its own
editable source, exact request, output and review. Choose the declaration that
matches the actual work:

| Declaration | What it controls |
| --- | --- |
| `route: "batch"` | Batch knowledge for authoring. It does not split a request, create items or set an output count. |
| The native request's supported output count | Several outputs of that exact request, within its execution authorization. They are candidates of one run; an ordinary item selects one reviewed candidate. |
| Named `items` | Separately authored prompts or scenes with their own sources, requests, results and reviews. |
| `--batch FILE` or `source.batch` | Continuation of an existing saved sheet batch and its panels. |

Keep the output count at the selected interface's request and authorization
owners. A count of three does not authorize three different prompts or three
host invocations. Each host invocation needs its own prepared run and recorded
claim; recovering a claim continues that call. Choose the item scopes from the
commission: `prepared-input` ends at preparation, while `delivery-only` includes
the actual image result and review. Neither a route nor a count chooses those
scopes for the author.

This synthetic example uses one shared commission and two explicitly scoped
items. Replace the focus statements with the actual requested image scopes.
Keep shared character requirements in their source definition and apply that
source to each relevant item; an item-specific scene change stays at that
item's owner.
When splitting a retained multi-scene draft, inspect each item's prompt,
native request and review criteria as well as its name. Give it only the
commissioned scene and its actual output count. Apply the shared definition to
the same subject ID in each item's selected Production Specification and
independent whole-subject review criterion. Retain applicable shared identity
and treatment criteria, and scope scene criteria to that item's depiction.
Keep the complete-set requirement in the shared commission and named item
declaration. Review each image against its own conditions and the complete set
against the commission; copying every scene's hard criteria into every item
would ask each single image to satisfy the other images' scenes as well.
Naming separate items does not rewrite those authored inputs.

```json
{
  "goal": "Create the two separate illustrations requested in request.txt",
  "items": [
    {
      "name": "opening",
      "source": {
        "request": "request.txt", "focus": "The opening illustration requested in the commission",
        "route": "batch", "execution": "external", "features": ["unlisted-interface"]
      },
      "result": {"scope": "delivery-only"}
    },
    {
      "name": "closing",
      "source": {
        "request": "request.txt", "focus": "The closing illustration requested in the commission",
        "route": "batch", "execution": "external", "features": ["unlisted-interface"]
      },
      "result": {"scope": "delivery-only"}
    }
  ]
}
```

Save the declaration as `work-request.json` and run `plan --root STUDIO --file
work-request.json --fresh-context`. Each ready item progresses independently
through `advance`. Once the exact host requests have their own recorded claims,
independent host calls may run concurrently when the tool supports it. Retain
the result-to-item mapping when calls complete out of order. The authorized
number and the actual interface contract determine calls and output counts.

An optional `after` array contains item names whose completed results are
actual dependencies. Missing dependencies and cycles are rejected. A shared
character does not by itself require serial execution; a selected reference
that must first be generated does. When the user reconsiders one result, open
that exact item's retained run or choices under the revision procedure below.
Do not replace other images or infer approval for an unrequested regeneration.

## Revise the result or items

When the same open commission needs a different `result.scope` or set of
`items`, open a work revision and bind a new plan. This covers correcting an
input-only plan when image delivery was commissioned, or separating distinct
images that were declared as one item. The saved plan definition remains the
record of its earlier selection. A content edit within an existing item follows
[Author and revise inputs](#author-and-revise-inputs) instead.

Inspect the saved plan and its exact owning task. `reopen` operates on the
active task, so first select that owner: if it is suspended, suspend any other
active task with its actual reason, then use `work_ledger.py resume-task
--studio STUDIO --task-id TASK_ID`. Inspecting a task with `show --task-id`
does not make it active.

```bash
python scripts/work_ledger.py show --studio STUDIO --task-id TASK_ID --view full
python scripts/work_ledger.py reopen --studio STUDIO --from-step FIRST_AFFECTED_STEP --reason "Actual instruction and reason for the changed result or items" --actor "Actual author"
python scripts/production_workflow.py plan --root STUDIO --file revised-work-request.json --fresh-context
```

Replace `FIRST_AFFECTED_STEP` with the first affected existing step number;
earlier completed steps remain complete. Supply the actual instruction's
reason and the author making this revision. Reopening does not approve an
execution or adoption. The old task revision retains its plan and run
references, and the old plan, runs and editable drafts remain available.
The new plan gets its own identity; the earlier unfinished plan is historical.

Write `revised-work-request.json` with the required scopes and named items.
Select each source explicitly: its exact `choices` file for unfinished input,
its `run` and applicable `candidate` for retained results, or its actual request
and `from_run` when revising a prepared input. Give distinct new scenes their
own editable inputs. Retaining an old draft does not automatically distribute
its decisions to new items. Reuse its applicable character and source decisions
at each selected owner, and reassess the changed prompt, request and review
basis. Keep the plan within its actual work task and bind `work_steps` only to
that task's matching milestones; other steps remain separately owned work.

For a closed task, select the retained source in a new plan with the actual
goal of the later work. For an independent commission, suspend the current
work and open that separate task. Neither operation rewrites completed results
or permits another call under an existing claim.

## Author and revise inputs

The plan keeps one editable source across definition, depiction, rendition and
preparation. Read the reported stage and complete its actual files. `advance`
moves a structurally ready stage to its `next_stage` after that author action.
For a declared retained amendment, `change_scope` and `remaining_stages` show
the actual owners that still need work. Unchanged stages are not reopened merely
because they precede the selected change.
The next stage returns its own applicable reading. Readiness is structural;
the author remains responsible for meaning and artistic completion.

When `inspect-inputs` shows ready choices owned by this plan, its continuation
returns to the exact plan's `advance`. Follow that action to publish the result
and update the work milestones together. Standalone inputs still offer their
own save or prepare action. A run prepared directly from the plan's exact
current choices and owning task continues in that plan. Equal content from a
different editor or work task does not establish that relationship.

When an amendment changes retained identity or reference evidence, follow its
`repair_action`. The action composes the explicitly selected candidate in a
new directory. Publication binds that successor as the plan's current input
and returns `plan_continuation.next_action` for the same saved plan. For example:

```bash
python scripts/production_workflow.py draft-inputs --root STUDIO --choices work/amend/choices.json --out-dir work/compose
python scripts/production_workflow.py advance --root STUDIO --file work/plans/PLAN/plan.json
```

This example requires that `work/amend/choices.json` is the unfinished input
already selected by `PLAN`; an unrelated draft retains its separate ownership.
The prior amendment and any other branches remain available for comparison.
An alternative draft within the same open commission retains that work task;
`draft-inputs --new-task` opens a separate task and is unnecessary for that
revision. If a different commission is intended while work remains open,
inspect and suspend the current task through its returned work action before
opening the other one. Retain each plan's path for later continuation.
Ordinary authoring inspection exposes them under `comparison_inputs` with
explicit inspection actions, without adding their unfinished judgments to
the current plan. If interruption occurs after the new directory is published,
the registered source relationship recovers that same continuation.

Preparation reserves one run identity before publication. Repeating `advance`
recovers that publication. Once prepared, the run uses its saved revision.
Its retained owner is checked before editable files, so an interrupted
publication or later edit cannot send continuation back to an older draft.
Later edits stay discoverable at their editable owner and belong to an
explicitly reopened revision.

To amend a retained result through the same plan workflow, select the actual
new request and retained input:

```json
{
  "goal": "Revise the selected character illustration for the new commission.",
  "source": {
    "request": "revision-request.txt",
    "from_run": "RUN",
    "change_scope": {
      "retain": ["identity", "source-authority", "finish", "target"],
      "change": ["depiction.view", "references", "recording.slot"]
    }
  },
  "result": {"scope": "studio-slot"}
}
```

The route, execution kind, artifact and selected model are inherited. Supply
`operation`, `route`, `execution`, `model` or `service` only to choose an actual
change. The ordinary input owner preserves unchanged content, reference uses and
selected source bytes. Edit prompt wording, reference membership/order,
model selection and controls at their documented owners. Use `compose` when
the commission reopens the whole realization. Exact reference meaning,
authority and exclusions remain authored choices. Follow
[Variation](production-variation.md) for those contracts.

The declaration initializes `work-basis.json.change_scope`; that basis is its
editable owner. The runtime unions declared changes with actual owner differences.
A retained value that changed has an explicit repair at the basis, and unreadable
or unclassified comparisons keep broad knowledge with their diagnostic reason.
Parameter-only changes begin at `rendition`; recording-only changes begin at
`prepare`. New composition keeps the complete applicable stage knowledge.
Scope selection changes no approval, source authority, review or final input check.

## Authorize an exact request

When this work task has no registered authority, `advance` first exposes one
shared `initial-authority` answer for all plan items. Record the actual existing
instruction, its issuer and evidence, the permitted actors/modes and scope, and
its stop conditions. Unanswered fields and empty evidence cannot be imported;
the draft itself grants nothing. This is the ordinary authority declaration,
not a new consent request. After that declaration is recorded once, each item
uses its current scope and opens the execution answer below. A concurrent
authority registration is never replaced by the old first-declaration answer.

Execution presents the saved request and one answer for its rendition,
authorization reason and applicable stop judgments. Existing scoped grants
remain usable. When grants are missing, the same answer names the actual
instruction evidence and actor/mode for the selected prepared operations.
The runtime materializes distinct direction and submission grants and their
exact authorizations. Request scope and rendition judgments retain the
[execution contract](production-request-execution.md).

Only missing operations receive additional grants. When several current grants
cover an operation, that answer has a `grant_choices` entry and numbered
`grant_options` identifying their actor, mode and scope. Select the applicable
number. An unrelated authority update preserves an already selected unchanged
grant. Actual revocation, expired permission or changed conditions requires
current assessment. For direct approval, the selected instruction also supplies
the exact-request principal evidence when it covers that request; the runtime
derives its binding without a second copied instruction.

A dispatcher sends through its selected service once. Later `advance` calls
recover its existing claim. Pending, unknown and partially received results
keep that execution identity. An external host receives the exact claimed
request; the agent makes the authorized host call and fills the returned
result form with the actual response and media paths. Recovery reads that
same call's result.

## Observe and review

The first `observe` answer names only the actual saved artifact. Inspect it and
write named observations with
their source, locator, observed content, interpretation and limitations.
`advance` preserves that first observation and opens the `review` answer with
the assessment workspace, source evidence and criteria. Give only the first
workspace and observation form to an independent first observer when that
independence is required. Each check's `supports` names observations in the
review. The recorder derives canonical observation indices and exact hashes.

The initial observation name is `view` and its source is `candidate`. Replace
the empty text with actual observations. Add named region or comparison
observations where the assessment needs them. Each retained criterion has its
own verdict and reason. `indeterminate` records an observed property that the
reviewer cannot decide. The full review contract keeps additional evidence,
repairs and unresolved findings under [Production review](production-review.md).

Several returned candidates remain explicit alternatives. Review them
individually and choose the intended result by its displayed number. The
runtime's ordering supplies navigation, not a choice of the best image.

## Select and adopt

One answer records the reason, actual approval evidence, actor/mode and stop
judgments for the selected destination. Record additional continuity or owner
allowance only when that use requires it. The runtime derives timestamps,
hashes, existing target bindings and separate official records.

`current.answer_contract` explains only the fields in the current answer and
names their absolute Studio and guide owners. Use the host's file editor to
fill that generated answer file. The lower-level selection and adoption
schemas describe the runtime's derived records, not additional forms to fill.

`current.authority_requirements` lists each actual operation, target and
selected current grant. When a grant is absent, its `required_action` names
the missing scope and the same `approval.evidence` answer that must explicitly
authorize it; several eligible grants continue through `grant_choices`.

Choose `approval.evidence` from the instruction for this actual use. A fresh
answer leaves that source unanswered. Prior authority instructions appear as
read-only context with their exact path, locator, hash and a bounded text
preview; `preview_complete` states whether the whole text is displayed. Read
the complete source before choosing it. Existing permission and a requested
destination do not select the current instruction on the author's behalf.
Reassessment also locates the previous use's captured instruction in this
read-only context, so its source remains available without another search.

When `continuity_decision` is present, select the actual `character_id`,
`continuity` (`recurring` or `one-off`) and the instruction establishing them.
The answer initially omits `basis`, declaring the same instruction selected
for approval. Add `basis: {path, locator}` when a distinct instruction
establishes identity or continuity. Selection/adoption permission and a continuity
decision can have different evidence. The runtime captures a shared instruction
once and distinct sources independently, derives their hashes and verifies the retained
continuity basis against the final adoption. It never substitutes approval
evidence for a separately selected continuity source.

For sheet use, that one answer carries selection, Studio acceptance and
canonical adoption. A grant that is missing appears as an unanswered authority
choice before effect; it is derived from the same actual instruction when
completed. Selection and adoption remain distinct grants, authorizations and
events. When both operations are still needed, the supplied evidence must cover
both; a retained selection leaves only the required adoption operation.
A delivery-only
instruction does not imply canonical use.

Recovery retains each committed stage. If selection succeeded and adoption
was interrupted, the same answer continues adoption. A later replacement or
withdrawal remains in force when an older completed operation is inspected or
retried. `current_use` distinguishes current, superseded, withdrawn and
delivery-only historical results. See [Production adoption](production-adoption.md).

## Continue a sheet batch

```json
{
  "source": {"batch": "work/sheet-batch/state.json"},
  "result": {"scope": "sheet", "influence": "identity"}
}
```

The sheet batch retains its task dependencies and execution recovery. The work
plan extends it through each received candidate's review and authored use.
An adopted anchor becomes available to subsequent panels through the existing
reference owner. Each panel keeps its own review and selected result; the
plan carries their completion records and work milestones together.
Every independently ready panel advances even while another awaits an answer.
The current panel is displayed in full; `other_panels` locates the other answer
files. Unprepared panels retain their original preparation diagnostics and
their reserved identities.

For independently authored images, use [named items](#create-several-distinct-images).
Each ready item can progress while another awaits a judgment or external result.

## Finish and recover work

Formal result records satisfy their explicitly bound work steps. After the
commissioned results exist, the plan refreshes derived Studio views, validates
them and records the verified completion of its owning task.
Completion checks the selected draft, actual run and recorded destination
before applying those milestones. A suspended plan can complete its own work
without closing another active task. Open questions and failed view validation
keep its ledger open while preserving the already committed result.

For a task previously planned in free text, `work_steps` can map its numbered
steps to `prepared`, `results` or `verified` once. For example,
`{"1":"prepared","2":"results","3":"verified"}` is appropriate only
when those milestones fulfill those actual step meanings. Otherwise the plan
shows the remaining steps and an answer for that correspondence. Independent
work and open questions remain with their owners.

On a fresh context, locate the saved plan and read only the actual remaining
operation's required sources and evidence. Retained receipts locate completed
work; they provide no inherited knowledge. The current authoring stage and
saved answer file remain available without reauthoring completed content.

Interrupted publication retains its reserved run. Interrupted execution
recovers its existing claim. Interrupted selection/adoption recovers the
separate formal records. An incomplete display refresh returns a repair while
retaining committed results. The complete plan itself is inspectable after
its task closes.

## Inspect effort and repeated attempts

`continuation_observation` compares the selected choices, context, work basis,
batch state and every panel's current answer bytes with the preceding `advance`,
together with each selected source, run, candidate, phase, state and recorded
evidence, the current work-step answer, remaining work and verification findings.
`unchanged_since_previous` is unknown
when that comparison lacks readable inputs. `observed_now` distinguishes a new
observation from one retained in a later inspection. An unchanged comparison
directs attention to the current answer or repair; it supplies no permission
and never skips a production check. Media, external sources and provider state
remain with their independent operation owners.

For the actual operation records in this Studio, run:

```bash
python scripts/production_workflow.py logs --root STUDIO --summary
```

The summary separates recorded calls and stages, reading delivery and reuse,
structured edits, failed or waiting attempts and recovery. It includes selected
plan/input identities so a repeated attempt can be traced to its real owner.
Intervals from a generated judgment form to an observed answer include downtime;
they do not measure active author effort or establish successful application.
Stage durations can overlap and unknown timings remain unmeasured. Compare
the same declared workflow outcome when assessing improvement; these records
do not score creative quality or replace review.

## Public request contract

The request schema is
[`production-work-request.schema.json`](../../schemas/authoring/production-work-request.schema.json).
`plan --help` and `advance --help` describe the same entry surface. The
runtime owners are `scripts/production_work_plan.py`,
`scripts/production_work_execution.py`, `scripts/production_work_review.py`
and `scripts/production_curation.py`. Their local fixtures exercise partial
effects, changed authority, retained results and condition-specific failures.

The existing phase commands remain available for inspecting or repairing the
specific owner. Ordinary continuation follows the plan's returned action.
