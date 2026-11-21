# Continue a production result

Use a saved work plan for a requested artifact, a retained candidate, an image
revision or a sheet batch. The author selects the source and intended result
once. The runtime carries preparation, execution, review, selection, adoption,
view refresh and work completion through their existing owners.

## Contents

- [Begin and continue](#begin-and-continue)
- [Select the commissioned result](#select-the-commissioned-result)
- [Author and revise inputs](#author-and-revise-inputs)
- [Authorize an exact request](#authorize-an-exact-request)
- [Observe and review](#observe-and-review)
- [Select and adopt](#select-and-adopt)
- [Continue a sheet batch](#continue-a-sheet-batch)
- [Finish and recover work](#finish-and-recover-work)
- [Public request contract](#public-request-contract)

## Begin and continue

Run these commands in the locked Skill environment. `STUDIO` is an initialized
Studio. Select one source and its result directly; the runtime writes the plan
request and its bindings. For new authored work:

```bash
python scripts/production_workflow.py plan --root STUDIO --request-file request.txt --route prompt-only --scope save
```

For a retained reviewed result whose actual destination is a character sheet:

```bash
python scripts/production_workflow.py plan --root STUDIO --run RUN --scope sheet --influence identity
```

After the applicable plan command, continue the result with:

```bash
python scripts/production_workflow.py advance --root STUDIO
```

`--request-file` contains the actual
UTF-8 commission, not a JSON envelope. `--choices` selects an existing editable
draft and `--batch` selects a saved sheet batch. Each source requires `--scope`;
sheet and catalog also require `--influence`. `--candidate` explicitly selects
a result of `--run` when needed; omission leaves the ordinary candidate choice.
For new or revised requests, `--feature` is repeatable and `--from-run`,
`--operation`, `--execution`, `--model` and `--service` retain their authoring
meanings. `--goal` supplies the actual new task for later use of completed work.
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
`actions.continue` advances that delivery; `actions.next` is offered only when
a selected section ends and other required sections remain. `actions.index`
opens the complete source scope and navigation. Replay and fresh-context
restart remain available, with no change to the required source bytes.
After an explicitly selected section ends, input inspection offers the remaining
complete scope in bounded pages. A section's end does not require visiting every
remaining heading separately.

For several dependent results or an imported artwork owner, use the complete
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

With an existing plan file, `plan` refreshes changed pending judgments without
sending a request or applying a selection. It writes a new answer revision,
links the previous answer and preserves committed effects. Use this returned
`refresh_action` when approval, review or placement changed. Record the current
reason and any newly unanswered conditions, then continue with `advance`.

At a judgment boundary, the report names `current.answer_file`, the evidence
and the reason for that judgment. Complete that file from the actual request
and observations, then run the same `advance` action. The runtime retains the
run, hashes, reviewed candidate, current placement, authority predecessor and
individual operation records separately. Those generated bindings require no
editing. An unchanged answer returns the same normal continuation.

The report describes the whole requested result. `needs-input` names the
current authored judgment, `pending` names a dependency or existing external
operation, and `blocked` names an actual inconsistency with its repair. A
`complete` plan has verified results and a closed owning work task. Existing
free-form work can produce `work-required` until its actual remaining steps
or questions are resolved. `verification-required` identifies inconsistent
saved results or derived views that need their owning repair.

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

## Author and revise inputs

The plan keeps one editable source across definition, depiction, rendition and
preparation. Read the reported stage and complete its actual files. `advance`
moves a structurally ready stage to the next stage after that author action.
The next stage returns its own applicable reading. Readiness is structural;
the author remains responsible for meaning and artistic completion.

When `inspect-inputs` shows ready choices owned by this plan, its continuation
returns to the exact plan's `advance`. Follow that action to publish the result
and update the work milestones together. Standalone inputs still offer their
own save or prepare action; a separately saved run is not silently assigned to
a plan merely because its content matches.

Preparation reserves one run identity before publication. Repeating `advance`
recovers that publication. Once prepared, the run uses its saved revision.
Later edits stay discoverable at their editable owner and belong to an
explicitly reopened revision.

To amend a retained result through the same plan workflow, select the actual
new request and retained input:

```json
{
  "goal": "Revise the selected character illustration for the new commission.",
  "source": {
    "request": "revision-request.txt",
    "from_run": "RUN"
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

## Authorize an exact request

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
events. The supplied evidence must cover both operations. A delivery-only
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

Independent items can be declared in `items`, each with a stable `name`,
`source`, `result` and optional `after` array of item names. A missing
dependency or cycle is rejected before work begins. Each ready item can make
progress while another item awaits a judgment or an external result.

## Finish and recover work

Formal result records satisfy their explicitly bound work steps. After the
commissioned results exist, the plan refreshes derived Studio views, validates
them and records the verified completion of its owning task.

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
