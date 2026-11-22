# Production workflow

The requested result determines the operation and its completion. Author the
meaning and expression at their owning sources. The runtime reads those
sources, derives exact inputs and records the action that actually occurred.
A saved revision, prepared request, external result, review and canonical
adoption remain distinct facts.

## Open the current work

Use [Authoring work](authoring-work.md) to compose or amend the actual candidate.
Retain the current request as supplied text and select the source applications
needed for this work. The agent develops the character and open construction
choices to the depth the current artifact needs. A conversational delivery uses
that candidate directly.

For saving or execution, initialize or reopen its Studio and work task. Use
`production_workflow.py status --root STUDIO`, `studio.py status --studio STUDIO`
or session entry to locate existing editing sources and an active execution.
Status exposes current authoring sources; session entry reads the saved task
trail without opening the Production database or refreshing Studio displays.
Continue the actual files and recover an uncertain external operation from its
saved run.

Default status begins with the selected run, current blocker locations and its
executable next action. Each historical list shows at most eight entries;
its `<name>_summary` gives `total`, `omitted` and `full_report`, where total minus
the displayed count equals omitted. The report path and JSON Pointer locate
the complete original list. A run-specific view shows its decision drafts with
`relation: selected-run`; unrelated task history remains in the counts and
complete report. This ordering makes no author choice. When several branches
remain, select the intended `inspect-inputs --choices FILE` action, including
alternatives in the full report.

Authoring findings appear once in `current_task.authoring.diagnostics`.
The standalone `inspect-inputs` summary keeps the same indexed findings in its
top-level `diagnostics`.
Inputs and their context name those findings through `diagnostic_ids`, including
findings for branches outside the displayed prefix. `blockers` locates every
current blocking finding. Repeated identical commands use an `action_ref`
JSON Pointer to the executable action already in the summary, with the primary
next action first. Different decision reasons or scopes retain their own actions. Reading changes
show source paths; complete before/after hashes remain in `full_report`.
`full_report_action` reads the exact saved JSON snapshot; `details_action` and
`status --view full` acquire complete current evidence. Presentation changes no
event, ledger, draft, review or permission decision.

When an unchanged editable source exactly matches a prepared run, later reading
requirements alone do not reopen that saved input as pending authoring. Status
retains them under that input's `future_authoring`, with complete diagnostics,
stage and reading actions in the full report. They establish no current
knowledge and do not change runtime or authorization checks. To edit again,
select `inspect-inputs --choices FILE`; its current reading requirements become
active authoring findings. An actual change to the editable files also restores
the current stage, gaps and reading actions.

Session entry and `work_ledger.py show --view summary` show the current goal, unfinished steps, every open question and
blocker, and the latest checkpoint still present in the current task revision.
It excerpts the latest note and reports `note_count` and `omitted`. Its
`work_ledger.py show --studio STUDIO --task-id TASK_ID --view full` action reads
the complete saved task and ledger history, including suspended or closed work;
omit `--task-id` to inspect the complete Studio work trail. Session startup
does not execute these inspection or refresh commands.

## Read the current stage

For saved work, begin with the structural `draft-inputs` command and follow its
reading action before following runtime-document links. It has made no creative
decision; the delivered contracts inform the actual authorship that follows.
This supplies the complete selected originals once, with delivery evidence,
instead of requiring an initial direct read and then a second route read.
Direct file reads made earlier remain ordinary knowledge, not issued receipts.

New character drafts begin at `definition`; enlargement begins at `prepare`.
Reopened unfinished work retains its saved stage. `draft-inputs --stage STAGE`
selects another current scope. `choices.authoring_stage` records the work
currently in progress. Keep the definition, selected depiction and rendition
in their actual editable files as they develop. Select the stage whose choices
need work; the stages are editing scopes, not a requirement to repeat completed
decisions or an automatic verdict that a picture is finished.

For a retained amendment, declare `--retain` and `--change` owners with `plan`
or `draft-inputs` under [amendment scope](production-authoring.md#declare-a-retained-amendment).
The declaration lives in `work-basis.json.change_scope`. Its current structural
differences select operation profiles independently of the stage label. The plan
starts with the changed work and reports `remaining_stages` and `next_stage`;
it does not repeat an unchanged definition before a view, parameter or recording
edit. Changed definitions automatically select definition knowledge, and a
conflicting retained owner requires an explicit correction. Final preparation
still checks actual source bytes, identity, current model and the exact request.

| Stage | Work and complete source knowledge |
| --- | --- |
| `definition` | Establish or revise the concrete character, acquired sources, their applications and usable wording. |
| `depiction` | Develop the intended construction and actual candidate with independent assessment criteria. Apply image contributions and retained requirements at their selected scopes. |
| `rendition` | Carry that construction into the actual prompt, supported negative text, references and rendering controls. Apply complete selected model guidance; changed wording or target also requires writing guidance. |
| `prepare` | Bind the saved content, references and evidence into the exact native request, or complete the input for saving authored text. Inspect the whole resulting input without inventing new creative decisions. |

```bash
python scripts/production_workflow.py inspect-inputs --root STUDIO --choices work/draft/choices.json
python scripts/production_workflow.py stage-inputs --root STUDIO --choices work/draft/choices.json --stage depiction
python scripts/execution_routes.py read --root STUDIO --choices work/draft/choices.json
```

`stage-inputs` retains the choices, source files and prior results and returns
the reading and editing actions for the selected stage. Its reading action starts
complete bounded delivery with `--all`; follow `actions.continue` to completion.
Use `actions.index` when inspecting the source scope or choosing an exact section.
Use the returned invocation with its complete runtime selection. Read the required original
sections before making that stage's decisions. Finish its authored work, then
select the next needed stage. Return to an earlier stage when a changed request
reopens its definition, construction or expression; retain all applicable
choices outside that change. A stage's structural readiness establishes neither
artistic completion nor final request readiness.

The choices-based reader derives the actual route, execution, features, target,
composition and source conditions. Adding an image, changing source applications
or introducing accepted variation can change required knowledge even when the
stage name stays the same. Inspect the current choices and follow their current
reading action after such edits. Read newly required or changed bodies before
using them; earlier complete ranges can contribute only while their actual text
remains known in the same context. Never activate an unused specialist merely
to fill a field or obtain a reading record.

After conversation compaction or a new agent, use `inspect-inputs` to recover
the current editable files and stage, then take its fresh reading action with
no `--known-reading` assertion. Read the complete requirements for that stage
and inspect its actual saved content. An older receipt, stage name or successful
check supplies no retained knowledge. Completed work remains available as source
material, so rebuilding context does not repeat earlier authoring or execution.

### Read an operation without editable choices

Index the complete contract for the current operation with
`execution_routes.py read ROUTE --operation OPERATION --execution EXECUTION --root STUDIO`,
adding applicable features and the selected model or writing family. Take
`authored`, `external` or `dispatcher` from the task. The index shows exact source
sizes, required sections and selection owners; it delivers no source bodies and issues no
reading. Whole-source internal headings expand with `--snapshot ID --index-source SELECTOR`.
Each `selection_reason_ids` entry resolves in the shared `selection_reasons` map.
Select a returned source or heading with `--snapshot ID --section SELECTOR`,
follow `actions.next`, or choose `actions.all` for complete paged delivery. The
explicit `--all` option also starts a complete read directly.

Read every returned JSON `body`. Follow `actions.continue` through a selected
section, then choose the next required section or all remaining material.
Completion requires non-null `reading`; a null continuation can mean only that
one section ended. The required operation, route and specialist contracts remain
complete, and the record is issued only after exact complete coverage and current
source checks. [Production authoring](production-authoring.md#select-and-read-the-current-knowledge)
owns the index, section, replay and recovery contract.

An existing record establishes earlier source delivery. A new context still
needs the complete knowledge required for its present judgment. In the same
context, append `context_reuse.arguments` to the actual next draft's reading
action. That action owns its operation and scope; the explicit complete reading
keys allow the reader to deliver only missing or changed bodies.
`context_reuse.operations` offers the current operation's inspection without
enumerating unrelated future operations. This reuses delivered knowledge,
not an earlier successful source or permission check.

Execution reads the permissions, exact-input interpretation, transport, capture
and recovery contract for the saved request. Review reads observation, source
scope, criteria and evidence limits for the actual artifact. Their explicit
section profiles defer authoring templates and new-depiction procedures to
reopened input work. Unmanaged selected specialists retain their complete
delivery. Every required section still receives exact-byte coverage before a
reading record is issued.

The `execute` and `review` reading actions select the saved task's route,
features and execution kind. With no new model-family inspection selected,
they do not reopen every family's prompt-authoring resources. Use the
workspace's `saved_knowledge` paths for the exact prepared model, offering and
guide originals. An explicit model or family inspection still delivers its
selected guidance. Current catalog changes do not redefine a saved request.

| Requested work | Operation and owning result |
| --- | --- |
| Write or revise | `author`: edit the commission, expression, source use and independent criteria |
| Save authored text | `save`: preserve its exact revision and unresolved choices, or validate finished target input |
| Prepare an image | `prepare`: compile current text, controls and actual references into an inspectable request |
| Generate or recover | `execute`: perform the authorized external operation or recover that same operation |
| Assess an artifact | `review`: observe the actual artifact and judge it against the commission and sources |
| Select or adopt | `adopt`: record the actual decision, intended owner and applicable authority |

## Edit and produce the requested artifact

`draft-inputs --operation compose|amend` creates the editing source from the
current request and, when selected, a saved task or run. Supply the actual new
request with `--request-file FILE`. Continuing the same request can use the
saved authoring work. `compose` builds a candidate from the current sources and
retained requirements; `amend` applies scoped changes to the actual baseline.
Both seed meaningful current content from the selected source. An amend retains
the complete identity source set, including its bytes, subjects, scope and
authority; a compose owns a new current selection. Use
`draft-inputs --choices CURRENT_CHOICES --out-dir NEW_DIRECTORY` to carry the
current edits into that compose. The selected choices supply the request and
content, so no separate reuse or edit-replay arguments are needed.
The registered work goal locates the task, while the supplied request establishes
what the user commissioned. Edit the directly accessible text files and selected
structured documents. Keep one meaningful choice at one owner. Preserve
independent criteria and applicable source authority. A detailed specification,
adopted plot or other specialist source remains available when the work uses
it; ordinary work needs no unused placeholder documents.

Select the `prepare` authoring stage for finished input, complete its current
reading and inspect the whole candidate. Use `save --choices FILE` for an authored revision, or `prepare --choices FILE`
for a model request. `save --draft` preserves unfinished content and unresolved
choices. Completed target-specific text applies the target's input contract,
grammar and required real dictionary search even when no image is generated.
`check --choices FILE` is the same compiler without publication when a separate
diagnostic is useful. If authored choices are still incomplete, its next action
returns to their current stage. When only final binding knowledge remains, it
offers `prepare`; the final reading requirement remains part of every completed
check. `build-inputs` is an optional export of derived inputs.
Direct ProductionTask inputs select their acquired common basis with `work_basis`.
Their completed checks use the same request, character and actual-source
relationships as saved choices; [Authoring work](authoring-work.md#save-or-execute-the-same-work)
owns acquisition and current applications.

Failures point to the editable file and field. Resolve independent reported
problems there, preserving unsupported or unresolved meaning as such. The
compiler regenerates paths, reference positions, content hashes and dependent
inputs. Reassess only the choices whose meaning or applicability changed;
keep all other valid choices and history.

`acquire-source` and `edit-choices` check retained identity before publishing
their changes. A mismatch returns an executable compose repair from a captured
candidate and keeps the original draft intact. The returned source path names
that specific candidate; the output directory names only its new destination.
Follow [source changes and structured editing](production-authoring.md#acquire-a-production-source)
for the source descriptor, field edit and complete A-to-B continuation example.

## Change direction without losing prior work

Use [Variation](production-variation.md) to branch from saved inputs, including
completed results. Separate branches can hold different prompts, models,
controls and reference selections. Each branch has an explicit editable
source and its own prepared request; preparing one does not replace another.
Add, remove or reorder references at their authored source selection and
preserve their intended roles and exclusions. The builder derives positions
and hashes for the resulting request.

An enlargement starts from the selected retained image, with its own operation
contract and criteria. `draft-inputs` accepts an explicit source run and
candidate as described in [Variation](production-variation.md); it retains the
image's provenance without imposing its generation prompt on enlargement.
Choose the resulting enlarged candidate through the common acceptance flow.

If the earlier work task is finished, `--new-task` opens the requested revision
while retaining the prior task, result, selection and completion. Applicable
content and criteria remain available. Apply the current commission's actual
authority to the new task; a saved approval is evidence only at its own scope.
An already active task must be selected or suspended explicitly.

## Continue according to the actual result

Saving completes the save operation. If the commission also requests delivery
or independent review, perform and record those actions for the exact saved
revision under [Authored storage](production-authored-storage.md). A later edit
is a new revision, retaining the history of earlier deliveries and reviews
without inheriting their current status.

A prepared model request contains its exact prompt, media, controls and target.
Inspect it before execution. Use its `status.next_action` and the complete
execution contract for the current dispatcher or external host. Apply existing
permission at its real scope; local authentication is separate from authority.
An uncertain send resumes the same execution rather than making another call.

Evaluate actual returned media before selection. The criteria come from the
commission and applicable sources independently of the prompt being assessed.
Chosen angles, wording and controls are means to that result. Keep limitations
and inconclusive evidence visible. Canonical adoption requires its actual
owner decision and authority; it is never a side effect of saving or capture.
## Continue a retained result

Select the actual retained source and destination before a curation decision.
`draft-acceptance` returns the reading action for `delivery-only` or `studio-slot`;
`draft-adoption` returns it for `sheet` or `catalog`. The action carries the
independent `--source-kind production-candidate` selection. Imported iterations
use their Studio and adoption owners with `--source-kind imported-iteration`.
A sheet withdrawal reads `--operation withdraw --scope sheet` for its actual
source owner. These complete scoped contracts include applicable authority,
prerequisites, exceptions and recovery; source excerpts chosen only for
navigation cannot replace them.

Use [Acceptance](production-adoption.md) for a reviewed result: author the
decision once with `draft-acceptance`, then `accept` derives and records its
exact authorization, selection and completion. Its work state identifies
unfinished steps or questions before the owning task can finish. Continue a
saved acceptance after interruption without generating the image again.
