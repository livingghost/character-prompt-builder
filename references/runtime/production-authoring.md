# Production authoring

Compose or amend the actual candidate through [Authoring work](authoring-work.md).
Edit its commission, selected depiction and source use at their owning locations.
Save authored text or prepare an image request from those same choices. The author
judges meaning; the input owners derive paths, hashes and repeated bindings.

## Assemble authored choices

### Discover input structures

`draft-inputs` returns `authoring_guide` and retains its creation-time copy in
`context.json`. `inspect-inputs` exposes the selected input's current
`context.input.authoring_guide_action`; follow it, or run `explain-inputs --field
authoring`, to obtain the guide for the current Studio and Skill locations.
After moving the Studio or changing the Skill installation, reacquire this
guide before executing its actions; saved context actions may still name their
original locations. Keep that context unchanged as the draft's source record.
Use the current guide's field-specific explain actions to locate the editable
files and complete contracts of unresolved fields before writing them. An unqualified
`explain-inputs` returns the entire field catalogue and may exceed a host's
display capacity; use the supplied `explain_action` or a listed input field
with `--field` for a focused response. A document member's repair pointer is
distinct from its document selector; inspect that member through the selected
document's contract action. This does not replace the current route's required
source reading:

```bash
python scripts/production_workflow.py explain-inputs --root STUDIO --choices work/input/choices.json --field authoring.documents.negative_provenance
python scripts/production_workflow.py explain-inputs --root STUDIO --choices work/input/choices.json --field target.model
python scripts/production_workflow.py explain-inputs --root STUDIO --choices work/input/choices.json --field external
python scripts/production_workflow.py explain-inputs --root STUDIO --choices work/input/choices.json --field external.image_input.external_request
python scripts/production_workflow.py explain-inputs --root STUDIO --choices work/input/choices.json --field authoring.task.recording
python scripts/production_workflow.py explain-inputs --root STUDIO --choices work/input/choices.json --field authoring.task.criteria
python scripts/production_document_contracts.py explain production_spec
python scripts/production_document_contracts.py explain production_spec --pointer /properties/subjects/items
python scripts/production_document_contracts.py validate negative_provenance STUDIO/work/input/negative_provenance.json
```

The complete catalogue remains available by omitting `--field` when the host
can receive it. If a response is truncated, retrieve the affected field again
before using its contents.

`--field` selects a display; its container pointer is not permission to replace
that parent. For example, `--field task_changes` exposes the
`task_changes.semantic_edit` child and its exact edit owner
`/task_changes/semantic_edit`. Use that pointer to select the plan path, then
edit the plan's content in the selected file. Other authored task choices use
their individual `authoring.task` owners. Follow the returned child actions
instead of constructing an `authoring.task_changes` selector.

`explain-inputs` reads the chosen draft without compiling a request or loading
past runs. It distinguishes a field required in the draft schema from a choice
that still needs an actual value before preparation. Select `--field` for one
field or `authoring.documents.NAME` for its current source and complete contract.
The document registry supplies required and permitted keys, the canonical
schema when one exists, the logical validator otherwise, examples and remaining
contextual checks. A document-level success does not establish request readiness.

#### Select a Production Specification

When a Production Specification is selected, its contract's `scaffold` links to
`production_spec.py draft --help`, the existing template and the actual
`subjects` item schema. The draft command starts one subject from the selected
model and explicit subject, domain, brief, render intent and continuity choices;
extend the subject array for the commissioned scene. The template also supports
an explicitly subject-free scene. Select the resulting file at
`authoring.documents.production_spec`; `choices.target` owns its published
`target_model`. The scaffold leaves the character definition to its author.

#### Identify the recorded subjects

`explain-inputs --field authoring.task.recording` exposes the recording schema
and `subject_map`: each key declares an image subject ID and its value names
the Studio character that records it. Preserve the other required recording
fields. Use those subject IDs consistently in their source applications,
reference uses and review criteria.

#### Inspect target and external fields

Target and external fields expose their child contracts through executable
explain actions. `target.model` follows the selected `target.kind`; an unselected
kind remains an explicit choice. `external` shows the runtime-owned editable
envelope and the existing-plan selector. Its child views distinguish authored
fields from the model, request paths, media mappings and hashes derived during
compilation. Follow each `schema_action` for the exact published schema
fragment, then check the complete current draft after editing its owning fields.

#### Select reference inputs

Reference choices expose the same child navigation. Select
`--field authoring.references.additional_references` for the ordered direct
source rows, their exact schema and the public Studio source commands.
`source` pins current adopted artwork; `accepted-source` pins the current slot
without granting canonical identity authority. Put that returned source object
in the selected row and author its role and subject uses. Keep supplied files
under their actual source authority. The builder derives missing use IDs and
file hashes; retain existing IDs referenced by other authored choices. Follow
the returned `image_input_action` to choose the existing mirrored-input or
explicit-plan behavior. Merely capturing an output does not select it as input.

#### Establish the editable definition

The draft is an empty scaffold, not a character definition. For character work,
[establish the subject for this use](production-direction.md#establish-the-character-for-this-use)
before writing its rendition. Acquire the applicable original or task-local
definition through [Authoring work](authoring-work.md). The saved
`work-basis.json` owns the acquired sources, current applications and their
subject assignments; the compiler derives `authoring.task.sources` from them.
Use `authoring_guide.source_acquisition` to acquire or update a Production
source through its complete source row, as described below. It derives hashes
from actual bytes and retains Production role and identity metadata together.
The [saved-basis context command](authoring-work.md#save-or-execute-the-same-work)
owns core requests and application choices; its generic file acquisition does
not declare a Production role or identity selection.
The compiler selects this acquired basis in the public task's `work_basis`.
For a directly authored ProductionTask, acquire the basis with those same core
commands and select its actual path. Completed checking, saving and preparation
capture the current task, delivery and selected documents, require the applicable
character definition, and verify their source applications and subject bindings
against the basis. Draft structure inspection allows this work to remain open.
Preserve the concrete meanings and their
[researched wording](prompt-vocabulary.md#define-a-character-with-usable-wording)
together at that owner. An existing definition remains authoritative; do not
replace it with a summary of the prompt being authored. The builder captures
source bytes in `authored_basis` for independent review.
For a selected Production Specification, project the relevant identity, current
state and performance into its subjects. Carry the meanings needed for this
depiction into the actual delivery, retaining authored phrases when tags alone
lose detail. A saved definition or an internal source path is not model input.
Explicit supporting setting work follows its declared scope.

A task-local definition derived from the current Production Specification
carries the compiler-derived `definition_owner` with `document: "production_spec"`
and its `subject_id`. Reacquiring a public task restores that actual document
as the editable owner. Its subject identity edits update the applied definition;
removing a subject updates the corresponding applications. A definition retained
as independent source material during composition keeps its source owner.
Canonical and external definitions retain their own authority and ownership.

Declare the subjects actually depicted in an image at their input owner. For
new task-local work, select a Production Specification and declare its
`/subjects`; an existing actual `recording.subject_map` also supplies its mapped
subject IDs. Acquired source assignments alone do not declare the image's
subjects. Use those same IDs in the source assignments and review criteria.
Each identity-bearing subject needs a `hard` criterion in
`authoring.task.criteria` whose `identity_review` names it and compares the whole
subject with its complete applicable definition at that source's original
authority. These declarations apply to task-local definitions as well as
canonical ones; complete them while establishing the definition for this use.

The [complete first-input example](../../examples/input-authoring/README.md)
creates all selected inputs and prepares one reference-guided image in a fresh
Studio with no previous run. Use it to understand the relationships; start the
actual work from its own draft and actual authority. The [state-aware
pilot](../../examples/state-aware-pilot/README.md) owns the additional complete
state-derived artifacts when those features apply.

#### Keep specialist documents at their owner

Each `authoring.documents` entry selects one editable file with `{file, field?}`.
`file` is relative to the Studio; `field`, when needed, is an array of JSON
object keys or array indices selecting the value inside that file. Keep the body
in that file. The builder reads its current bytes and captures hashes in the
compiled revision. Editable selectors do not carry hashes to maintain by hand.
For example, correcting `work/input/negative_provenance.json` changes the next
`check --choices` and `prepare --choices` without a second edit to choices.
Diagnostics name that source file and its owning contract. Earlier prepared
revisions retain their captured content; `draft-inputs --from-run` restores it
into the new draft's editable files.

#### Select execution-specific inputs

The `authoring.documents` guide derives `execution_inputs` from the current
ProductionTask schema and selected execution branch. Its
`permitted_generation_documents` and `not_permitted_generation_documents` name
that branch's allowed and excluded document keys. A document's guide reports
`execution_input.permitted_as_generation_document`. Use that scope for external
execution as well: a known document key alone does not make it an execution
input. Applicable research and source evidence keep their existing source
owners; the selected route and content still require their own checks.

The `authoring.generation` guide uses the same execution-specific schema for
inline fields. For external execution, compiled `production_spec` and
`state_graphs` belong to their `authoring.documents` selectors; an inline
`generation.brief` is not permitted. Dispatcher inputs keep their declared
inline fields. Inspect reports an excluded field at its actual editable owner
before compilation, without deleting it or moving the author's meaning.

`artifact_type` belongs only to contracts that declare that discriminator.
Inspect the selected document's permitted keys rather than copying fields from
another kind. `owner-direction.json` is not a reserved artifact type: an original
commission may be prose or structured data, with its source role and locator in
the task. The task's production direction has its own declared schema.

#### Continue from the prepared request

After preparation, inspect the returned `status --run RUN` action for that
request. Unqualified `status` inspects all registered runs and has broader cost.
Both forms report source changes separately from the saved request's execution
requirements; neither requires restoration of edited original files.

#### Bind input work to the open task

Use [Craft consultation](craft-consultation.md) while deciding what to write or revise.
Open the work task before reading or drafting its inputs, using
`work_ledger.py begin --studio STUDIO --goal TEXT --step TEXT`. Reuse its task ID
through input authoring and preparation. The input builders and route reader
save their progress under that task automatically.

### Acquire a Production source

Write one public ProductionTask source row in the Studio, then run the action
returned by `authoring_guide.source_acquisition`. For example, this synthetic
`work/input/design-source.json` selects the actual definition of subject A:

```json
{
  "id": "design",
  "path": "inputs/design.json",
  "role": "identity-contract",
  "disposition": "applied",
  "locator": "The adopted identity and selected body design",
  "reason": "These properties define subject A for this image.",
  "identity": {"subject_ids": ["A"], "selectors": ["/identity", "/parts"]}
}
```

```bash
python scripts/production_workflow.py acquire-source --root STUDIO --choices work/input/choices.json --source-row work/input/design-source.json --view summary
```

The source file and descriptor are Studio-relative. The operation acquires
the original bytes, validates the role, pointers and subject selection, retains
the complete description in the acquired origin and derives applications,
subject assignments and selected source files. Its `source-acquired` result
names `choices_file`, `basis_file`, `projected_source`, unresolved matters and
the next inspection command. `changed: false` means the same selected input
already produced the current acquisition. Reacquisition updates that source's
owned selection without silently dropping unrelated applications or subjects.
A refused acquisition leaves the prior draft usable. Saved runs and their
evidence remain unchanged.

For an `amend` draft, acquisition compares the complete proposed identity
selection with the retained evidence before publishing. Adding or removing an
identity source, replacing its bytes, or changing its subjects, selectors or
authority requires a new `compose` draft. The diagnostic preserves the proposed
candidate, including the newly acquired bytes, outside the original draft. Its
`repair_action.argv` starts a compose from that exact candidate through
`draft-inputs --choices`; execute that action once to continue the change.
The original draft stays available for its existing source selection. An
excluded acquired source uses its retained bytes and needs no live original.

A source without identity coverage uses the same row without `identity`.
Select its actual role, locator, disposition and reason. Use
`source_requirements` in the draft or input guide to see required, applied and
missing roles. Each missing role has a complete row example and acquisition
action. A `considered-not-used` row does not satisfy an applied-role requirement.

Edit the descriptor and reacquire when its Production metadata changes.
`task.sources` and the selected source files are derived views. A projection
diagnostic distinguishes missing origin metadata, undeclared identity and
inconsistent applications from an invalid criterion binding. It names the
acquired origin, applications, subjects, projected identity, dropped fields
and `repair_owner`; follow its `repair_action` instead of editing a field the
next projection replaces.

The complete current ProductionTask path remains available through
`draft-inputs --task FILE`. Initial `draft-inputs --route ROUTE --operation compose`
creates the current editable scaffold without requiring an earlier run.

### Edit an authored choices field

Use `edit-choices` for one structural JSON edit. Save the intended JSON value
in a file, then name the authored field with a JSON Pointer:

```bash
python scripts/production_workflow.py edit-choices --root STUDIO \
  --choices work/input/choices.json --pointer /authoring/task/direction/purpose \
  --operation replace --value-file work/input/purpose.json
```

For example, `purpose.json` can contain the JSON string
`"Show the connection between the two synthetic shell segments."`.
Use `add` for a new member or array entry, `replace` for an existing value and
`remove` without `--value-file` to remove the selected member. A JSON Pointer
escapes a literal slash as `~1` and a tilde as `~0`.

This operation checks the draft's structure while allowing unfinished authored
values. It owns the same choices/basis locks and source boundary as
`acquire-source`. Direction, criteria, recording choices, references, reading,
validation selections and generation choices remain at their authored owners.
Edit the selected text or document file for its contents. Source catalogs,
projected task sources, captured hashes and immutable draft context belong to
their producers; the diagnostic gives the owning operation for those fields.
The compiler derives request fields and bindings when the candidate is checked
or prepared. Structural editing supplies no artistic or source-authority judgment.

An identity-changing edit in an `amend` draft returns the same captured-candidate
compose repair as acquisition. The snapshot contains the result of the requested
edit, so the repair does not ask the agent to repeat a pointer, digest or edit.
Before extracting a selected task or saved run, the input reader reports
missing structure with a public JSON Pointer, schema, expected shape, input
file/run and repair owner. Its rebuild action creates a new scaffold; carry
over applicable request, sources, direction, delivery and criteria, selecting
current evidence and authorization. Never rewrite a historical run to make
it match the current input contract. A scaffold does not copy prior execution
claims, result reviews or exact-request approvals.

#### Read an input summary

`draft-inputs`, `stage-inputs`, `inspect-inputs`, `build-inputs`, `check`, `save` and `prepare`
accept `--view summary`. The summary retains unresolved choices, owning files
and actions, and gives `full_report` for the complete JSON snapshot. The
complete view remains available with `--view full`. Summarizing changes
neither the checks performed nor the command's exit status.
`inspect-inputs` applies the [current-work navigation contract](production-workflow.md#open-the-current-work):
bounded input, reading and decision lists retain `total`, `omitted` and the
complete report location in their `<name>_summary`. Its `diagnostics` owns each
unresolved finding once; input rows and `context.input` use `diagnostic_ids`.
Repeated reading commands use `action_ref` to their executable summary location.
Every distinct unresolved finding in the selected work scope remains visible
even when its branch is outside the displayed list. Retained comparison inputs
have explicit inspection actions; their unresolved choices do not become
current-work findings. Complete source changes, hashes and historical
notes remain available in the saved report.
With `--choices PATH`, inspection acquires that exact registered editable
branch. Other retained paths remain available as `comparison_inputs` without
their content or diagnoses becoming current blockers.

### Select and read the current knowledge

For editable choices, begin with the draft's reading action or
`execution_routes.py read --root STUDIO --choices work/input/choices.json`.
The reader derives the route, execution, selected features and target from
that work. `choices.authoring_stage` selects `definition`, `depiction`,
`rendition` or `prepare` under the
[current-stage contract](production-workflow.md#read-the-current-stage).
`stage-inputs` changes that stage while retaining the actual editable files.
Inspect the current choices after a source, reference or condition changes;
the required section set follows their current explicit selections.

For an operation without editable choices, begin with the route, current operation, actual execution kind, applicable
features and selected model or prompt family. `author` and `save` select the
applicable authoring contract; `prepare`, `execute`, `review`, `adopt` and `withdraw` select
their complete operation contracts. Take `authored`, `external` or `dispatcher`
from the task. An omitted operation uses the route's declared default, shown by
`execution_routes.py inspect ROUTE --execution EXECUTION`.

`config/execution-routes.json` owns the complete required section sets and each
selection reason for the actual operation, execution and selected features.
The complete original documents remain available. Selecting a heading for
delivery does not alter the required set or authorize an omitted operation.

The editable work's stage selects complete original sections for the judgment
now being made. Definition establishes the actual character and source
applications; depiction develops the construction and independent criteria;
rendition writes its supported text and controls; preparation binds those
saved choices to exact inputs. Image-source use, accepted variation and other
declared conditions retain their applicable contracts. A changed choice can
therefore add required sections within the same stage. Unresolved source
content never establishes that an image or protected requirement is absent.
Preparation also receives its authority, source-binding, verification, preview
and interrupted-publication contracts. Execution, result repair and curation
procedures stay with their operation owners. New composition uses the complete
applicable stage knowledge. A declared retained amendment uses the changed-owner
profiles below. Sparse discovery keeps its general construction basis when the
picture is reopened; a changed finishing decision receives the complete selected
specialist. Specialists without an explicit scoped profile remain complete.
A profile refines only selected documents and never activates an unrelated
specialist. Required model cards and writing resources are delivered completely;
unchanged wording need not select a writing resource for a controls-only or
recording-only amendment. The prompt-knowledge boundary remains required.

#### Declare a retained amendment

For a retained input, declare the meaningful owners to retain and the changes
to make before the first read. `plan` and `draft-inputs` accept repeatable
`--retain` and `--change`. For example:

```bash
python scripts/production_workflow.py plan --root STUDIO \
  --request-file revision-request.txt --from-run RUN --operation amend \
  --retain identity --retain source-authority --retain finish --retain target \
  --change depiction.view --change references --change recording.slot \
  --scope prepared-input
```

The plan's `source.change_scope` initializes one editable declaration in the
draft's `work-basis.json`. The input guide names that file and its
`/change_scope` pointer. Edit this owner when the intended scope changes;
the plan request records how the work began and is not a second live copy.
The equivalent basis value is:

```json
{
  "retain": ["identity", "source-authority", "finish", "target"],
  "change": ["depiction.view", "references", "recording.slot"]
}
```

`retain` accepts `identity`, `source-authority`, `depiction`, `rendition`,
`finish`, `target`, `controls`, `references` and `recording`. Retaining `finish`
preserves the rendering declaration while permitting numeric parameter edits.
Retaining `controls` also preserves that declaration. The changed owners select
the following knowledge; combined edits receive the union of complete sections.

| Change | Reading profile and responsibility |
| --- | --- |
| `definition`, `source-authority` | `amend-definition`: current definition, source applications and their complete applicable design contracts. |
| `depiction`, `depiction.view` | `amend-depiction`: the retained definition in the changed construction or view, declared geometry and independent review obligations. |
| `references` | `amend-references`: original media acquisition, selected use, subject coverage and exact transport. |
| `rendition` | `amend-rendition`: actual prompt and negative text, weighting, dictionary evidence and writing guidance. |
| `controls`, `controls.parameters`, `controls.render-intent` | `amend-controls`: supported controls and the authored rendering declaration. A numeric-only edit does not reopen finishing design. |
| `target` | `retarget`: the new model edition, offering, grammar, reference transport and request evidence. |
| `recording`, `recording.slot` | `amend-recording`: the existing Studio or sheet destination, subject mapping and retained provenance. |

The runtime compares the selected editable values and acquired source bytes
with the actual baseline. It adds profiles for observed changes; the declaration
cannot conceal a changed definition or target. The comparison uses structural
owners and exact content, never keywords in prompt prose. A view declaration
does not prove the meaning of an edited sentence. The author remains responsible
for that meaning, source application and the whole-subject review.

The current route and features select their applicable contracts independently
of those content profiles. A route or feature selection is reported as an
observed `route` change; it does not establish changes to every content owner.
The target owner compares the actual target, execution kind and artifact kind.
Moving between workflow routes with the same model, service, wire operation
and execution kind does not by itself select `retarget`.

For a changed definition or depiction, `sparse-retrieval` selects the same
complete general construction sections as ordinary depiction authoring.
Selecting `finishing` explicitly obtains every original specialist section,
example and limitation for that work or a changed rendering intent. Retaining
the finish does not turn sparse discovery into a full finishing commission.

Changed values that contradict `retain` produce `AUTHORING_WORK_INCOMPLETE`
at the basis declaration. Restore those values or revise the declaration to
state the intended change, then inspect the same draft. Unavailable or
unclassified comparison inputs select all amendment profiles and report
`comparison_notices` with the reason and owning repair. Ordinary source and
input diagnostics remain in force. An undeclared amendment keeps the ordinary
complete stage requirements; a new `compose` does not use retained-edit scopes.

Scope selection grants no new source authority. The existing amendment identity
boundary still protects adopted source selections and their bytes. A change
requiring a new identity uses the returned compose repair and the captured
proposed candidate, as described under source acquisition. Selecting
`definition` ensures its knowledge is present; it does not override that boundary.

The plan starts at the first needed stage and exposes `remaining_stages` and
`next_stage`. Definition changes begin at `definition`; depiction or reference
changes begin at `depiction`; wording, controls and retargeting begin at
`rendition`; recording-only changes begin at `prepare`. The selected profiles
persist across stages, so moving to `depiction` alone adds no unrelated design
template or species architecture. Actual new edits can enlarge the profiles.

Preparation independently rederives the scope from the actual saved task,
basis and sources. It retains exact request, source, identity, authority and
review-structure validation. Controls-only and recording-only edits retain
current model-card checks at preparation, while unchanged prompt wording does
not require rereading the writing resources. A changed target or wording
requires those resources again. Changing the recording destination grants no
slot acceptance, canonical adoption or execution permission.

#### Choose a curation scope

For `adopt`, select the destination with `--scope delivery-only|studio-slot|sheet|catalog`
and the independent source owner with
`--source-kind production-candidate|imported-iteration`. A `delivery-only`
selection belongs to Production; imported iterations use a Studio slot or
canonical scope. `withdraw` names the public sheet withdrawal operation and
requires `--scope sheet` plus the actual source kind. It does not revoke a
separate catalog pack. `draft-acceptance` and `draft-adoption` return these exact
reading actions from their acquired decisions, including in a fresh context;
no identifier, destination or hash must be copied into the command manually.

```bash
python scripts/execution_routes.py read adoption --operation adopt --execution dispatcher --scope studio-slot --source-kind production-candidate --root STUDIO
python scripts/execution_routes.py read adoption --operation adopt --execution dispatcher --scope sheet --source-kind production-candidate --root STUDIO
```

A slot selection includes review allowances, select authority,
Studio acceptance, completion and recovery. A Production sheet adoption includes
its current selection, separate canonical authority, approved influence,
reference readiness and retained-claim recovery. Catalog registration, imported
adoption procedures and withdrawal are required only by their selected scope,
source owner or operation.

#### Read the required source bodies

```bash
python scripts/execution_routes.py read reference-artifacts --operation author --execution authored --root STUDIO --feature sparse-retrieval
```

This explicit command starts with a required-source index, with `mode: "index"`, an empty
`body`, and `reading: null`. It reports the selected operation, execution, destination, source kind,
features and model; each source's exact content hash, full byte size, required
ranges and selection owners. A whole-source requirement is shown once;
its `section_count` reports internal navigation headings without expanding them.
Explicit required sections remain visible in `sections`, with original source
offsets and `selection_reason_ids` referring to the complete explanations in
the top-level `selection_reasons` map. Source rows use those same reason IDs.
`sections_expanded` distinguishes an expanded section list from a whole-source
overview. Shared reasons are printed once, so the applicable
contract can be inspected before delivery. `progress.required_bytes` measures the complete
selected material, while `remaining_bytes` excludes source ranges already
delivered in this snapshot and explicitly known complete bodies. Navigation
establishes no source delivery and issues no reading key, even when an earlier
same-context reading supplies every required body. `selection_scope` distinguishes
`complete-source` from `selected-sections`. `selection_summary` reports the
stage, declared change scope, selected profiles and bytes attributed to each
route, feature and operation. Shared bytes can have several selection owners;
those attributed totals are not additive. `progress.fresh_context_bytes` is
the complete current reading size. `progress.same_context_new_bytes` removes
only explicit complete same-context reuse, independently of page progress.

Source states have explicit meanings: `pending` has no delivered bytes;
`partial` has some delivered ranges and still needs the rest; `delivered` has
complete source coverage in this snapshot; and `known` comes from an explicitly
selected complete reading whose required source content is unchanged. An
unrelated edit elsewhere in the document can leave that content reusable.
`same_context_required`
identifies snapshot coverage or known readings already retained when this response
began. A fresh index or first delivery page has neither; its new source text arrives
in that response. A later page, index or status view over delivered ranges relies
on retaining their earlier text. The index reports these state meanings, and
`read --help` lists them.

Generated authoring and recovery actions select `--all` for the current stage.
Their first response delivers a bounded body page; follow `actions.continue`
until `reading` is non-null. `actions.index` exposes this same complete source
index when its scope or individual sections need inspection. Input inspection
continues an unfinished page first, then offers all remaining required material
in bounded pages after a selected section ends.

Inspect the selected scope as needed. Choose the operation actually in progress
and the specialists the task uses. For example, `studio-placement` selects the
complete contract for correcting an existing iteration's current scene or slot;
ordinary image creation does not select that correction. Preparation and execution
receive the complete [diagnostic-handling contract](production-diagnostic-navigation.md).
Consult the linked global code catalog when resolving the reported failure.
The declared section sets retain the prerequisites, authority, constraints,
exceptions and recovery required for that operation and destination. Headings
then guide navigation within those required bytes; selecting a heading in the
index never removes other required sections.

##### Choose a source range

The index supplies an exact `selector` for each source range available to read
and each expanded heading. To inspect a whole source's headings, append
`--index-source SELECTOR` to `actions.index.argv`, as `source_navigation` describes.
This returns `mode: "index"` with the chosen `index_source`, no source body and no
reading. It leaves the complete required scope unchanged. An explicitly `known`
source has a null selector; if its text is no longer
available, start a fresh index without that known-reading assertion. Use its
`section_selection.argv` plus `--section SELECTOR` to read that choice, or execute
`actions.next` to begin the complete remaining scope in bounded pages. A source selector
reads that complete indexed source range; a heading selector reads its exact
byte segment up to the next heading within that range. Markdown headings inside fenced examples are not sections.
Writing-guide sections, dialect records and model offering cards have their own
exact JSON segments, including the source opening and closing bytes.

```bash
python scripts/execution_routes.py read --snapshot SNAPSHOT --section SELECTOR --root STUDIO
```

`--snapshot SNAPSHOT --index-source SELECTOR` is navigation; `--section SELECTOR`
delivers its exact source text. Neither an index nor a direct file read can be
converted into a completed reading by assertion.

##### Deliver every required byte

Use the complete returned invocation when a custom ledger or pack runtime is
selected. `actions.index` reopens the saved index and its current coverage.
The index's `actions.all` explicitly delivers every remaining required byte in
bounded pages. Body pages keep the continuation and recovery actions, and their
`selection_summary` points to `actions.index` for complete selection reasons.
Each executable action provides an `argv` argument array, operation name
`command: read`, and a `reason`. Execute the full `argv`. Continuations restore
the exact pack runtime from their snapshot; those arguments need no repeated
entry on every page.
It is also available when starting a new reading:

```bash
python scripts/execution_routes.py read reference-artifacts --operation author --execution authored --root STUDIO --feature sparse-retrieval --all
```

The default `--view json` response is one JSON object. Read its `body` entries in order. Each
entry contains exact source text in `text` and its kind, path, hash and byte range
in `metadata`. A document body binds the complete original source with
`source_sha256` and `source_size`, and its delivered interval with `source_start`,
`source_end`, `sha256` and `size`. Page `start` and `end` are offsets within that
body; adding `source_start` gives the original document offsets. Top-level `metadata` identifies the selected scope. `progress`
reports required, reused, delivered and remaining source bytes; section and replay
progress also report the bytes left in that selected delivery. Source text and
control fields are separate, so text inside a document cannot become an action.

For an agent-facing display, add `--view text` to the same public read action.
It displays every original `body[].text` character with its actual line breaks,
source path and original byte range. It retains the complete JSON response in
the returned `response_file`, including full source metadata, selection reasons
and every alternate action. The default directory is `reading-responses` beside
the ledger; `--response-dir DIRECTORY` selects another directory. Each call,
including an index or replay, creates a new file without replacing earlier
responses. Source text is flushed to the host before successful delivery can
be recorded, and the complete response is saved before its final controls are
displayed. An interrupted response remains evidence of that interruption.

The text view's final `READING CONTROL` supplies one `next_action`, the current
`reading_context`, `same_context_required`, required/reused/delivered/remaining
byte counts, the issued `reading` and `choices_binding`. Read the whole body
before executing that next action. It preserves the display and response
directory without repeating every alternate command. The index displays all
selected source ranges and their complete selection reasons. Warnings and
diagnostics remain visible; an error or failed binding displays every repair
control. Ordinary command errors and non-JSON stderr remain visible as well.
Use the structured actions in the retained JSON when exact machine parsing is
needed; a literal command in source text is not an executable reader action.

Text view changes presentation alone. It selects no smaller scope, issues no
extra reading and advances no page automatically. An earlier response file or
reading key supplies no knowledge after compaction. When a host wraps command
results, display stdout as text instead of JSON-encoding it a second time.

`--page-bytes N` sets the source-byte budget, which defaults to 16,384 bytes.
It applies to section and full deliveries alike and preserves UTF-8 boundaries.
`--page-bytes auto --host-page-bytes N` uses the host's explicitly declared
safe source-text capacity, bounded at 262,144 bytes. Reserve separate space for
JSON metadata when declaring that capacity. Without a declared capacity, auto
keeps the 16,384-byte default. A fixed budget is also capped by a supplied host
capacity. `page_sizing` reports the selected budget and its meaning; successful
output does not prove that the host displayed every byte.

Follow `actions.continue` while the selected section or full delivery has another
page. When a section ends, `actions.continue` becomes `null`; if required material
remains, `actions.next` or the index's `actions.all` reads the complete remaining scope in
bounded pages. Choosing another individual heading through the index is optional;
ordinary continuation need not step through small headings one at a time.
A null continuation alone does not establish completion. Completion is a non-null
`reading`, containing the issued `reading.key`, `reading.record` path and
`reading.record_absolute` location.
An incomplete result has `reading: null` and `context_reuse: null`. Section reads
may occur in any order, and overlapping reads count their bytes only once. Reading
the final section first cannot issue a complete receipt. A complete paged read
skips ranges this same snapshot has already delivered.

##### Recover an interrupted source delivery

`actions.replay` rereads an actual delivered page; indexes have no source page to
replay. If a host truncates text, replay with a smaller `--page-bytes` budget and
follow its continuation through the rest of that page before proceeding. Replay
retains the full required scope and its earlier delivery evidence. A successful
command does not establish that truncated text was read. Studio status exposes
the saved index, exact partial coverage and next reading action when no complete
JSON response reached the agent.
The reader records the selected continuation explicitly. Reading a later section
first does not replace a subsequently selected earlier section or its byte budget
with a guess based on source order. If no continuation was selected, status opens
the retained index so the next source choice remains explicit.

##### Preserve reading scope and evidence

The actions retain the selected environment's Python, installed script, absolute
reading ledger, Studio when present, byte budget and exact pack runtime, including
additional discovery roots. A snapshot fixes the route, operation, execution, destination, source kind,
features, model, prompt family and explicit same-context sources. A page cursor
also fixes its delivery selection. `--reading-ledger` selects the ledger.
Otherwise an explicit `CPB_READS_LEDGER` takes priority, followed by the specified
or current Studio's ledger, then the configured home ledger.

The reader preserves every required byte and issues a reading only after complete
coverage and a fresh check of actual documents, resources and selected-model
contents. Its record and ledger retain whole-source hashes and the original issuance
witness of every reused interval, together with exact required ranges and
operation scope. A source change during reading names the changed owners and
provides `actions.restart`, which opens a new current index. A new reading checks
its ledger before publishing an index or source body. Following a document link,
viewing a heading index or retaining a file path alone does not deliver that
source's contents.

##### Reuse complete knowledge in this context

Start the current uninterrupted model context with `--fresh-context` on the
saved plan or a reading command. Its returned `reading_context` identifies only
that live context. Follow the returned plan and reading actions: they carry
`--reading-context ID` and automatically select complete readings delivered in
that context through this Studio's ledger. The plan does not retain this ID as
knowledge. An ordinary invocation without either option infers no context from
saved work. After compaction, a new agent or loss of source context, start with
`--fresh-context` again rather than copying the earlier ID.

The automatic selection derives from successful complete deliveries, never an
index or incomplete page sequence. `reuse_selection` reports its selected and
automatic reading counts. The index's complete `selection_summary` names the actual operation,
execution, destination, stage and the selection owners with required and reused
bytes; owner counts overlap when the same source has several reasons. `progress`
separately reports required, reused, delivered and remaining bytes. Execution,
review and curation keep their current operation and destination selectors when
using the same context, so shared knowledge is reused while every additional
requirement still arrives as text.

For another operation in the same active context, use the actual next draft's
reading action and append `context_reuse.arguments` from a completed result.
`context_reuse.operations` offers inspection of the current operation; it does
not choose the next operation, destination or candidate. The arguments carry
the selected context ID, or repeatable `--known-reading KEY` selections when no
context was declared. Explicit keys remain available for individual repair and
inspection. The reader compares exact source kind,
path, content and resource/model scope, together with the original delivery
witness, then delivers every missing or changed required range. Document
deliveries retain each completely covered section's anchor, original byte range
and content hash. When another part of that document changes or moves the
section, matching path, anchor and complete content identify the same known
section at its current range. A matching heading or a hash without complete
delivery evidence supplies no knowledge. For reuse of a subsection from a changed
document edition, the reader also verifies the retained bytes of the complete
earlier body. If that evidence is missing or damaged, a new current read delivers
any ranges it can no longer prove. If the evidence disappears during an open
read, start the current reading again; the incomplete snapshot cannot issue its
record. A complete earlier full source can cover a later
required section, and several complete earlier ranges can cover parts of a
broader requirement. Their union never certifies an unread gap. A scope change
indexes those missing intervals explicitly before any current reading is issued.
Choose sections or the index's `actions.all` to complete the current reading.
When no new bytes are needed, that action checks the current sources and issues
the current record without repeating unchanged bodies. Its response has no
body page to replay, so `actions.replay` is `null`.

For curation, the actual draft supplies its destination and source owner.
Moving from slot acceptance to sheet adoption uses that draft's `reading_action`
and the same explicitly selected context or retained keys. Shared sections remain
known only through their complete deliveries in that context, and additional
canonical-use sections are delivered before completion.

When changing model, service, features, route, destination or source kind, begin an index with the actual
selections and the `context_reuse.arguments` of complete readings still known in
this context. Model and resource scope are independent of shared documents: a
changed model preserves unchanged workflow knowledge and requires its own card.
A changed required section delivers that section again; unchanged sections
remain available through their exact prior witnesses. A changed resource
delivers its complete selected body. Whole-source hashes still identify the
current document edition, and a new record checks the current complete selection
before issuance. A required section with no matching evidence remains unread.
An unneeded specialist
or pack release/lock change does not discard unchanged required knowledge. These
reads preserve prepared inputs and authored decisions; delivery evidence does not
rewrite creative work.

##### Rebuild knowledge in a fresh context

A new agent, compacted conversation or lost source context opens the index for the
operation now needed with `--fresh-context`, without the previous
`--reading-context` or any `--known-reading` selections. Use
`actions.restart` (also referenced by `context_reuse.fresh_context`) or the fresh-context action in
Studio status. Restart retains the selected task scope and existing authoring
files while making no assertion of retained knowledge. Continue the work's saved
choices and current phase; a fresh context need not repeat completed production
operations. A ledger, partial pages or historical key alone never supply knowledge.
An incomplete reading cannot contribute known bodies. A saved page continuation
requires its explicit original context. When a plan is inspected in a different
declared context, its reading action restarts the current source selection;
previously delivered pages are not skipped on that new context's behalf.

##### Read an acquired model

An acquired model outside the catalog uses `--model-file FILE` in place of
`--model`. A relative path is resolved within the Studio. The reader selects the
same complete model and writing guidance, binds its exact edition, and retains
its source for continuation and fresh-context reading. This source matches
`choices.target.model_file` when saving target-specific text; the input owner
derives the compiled task target from that selection.

## Use the delivered knowledge

Read interface guidance; resolve the optional `prompt-writing-guide` and read the complete selected guide before final rendition. Preserve authored meaning while applying its syntax and target evidence. Inspect complete selected knowledge records for actual construction questions. A selected specification records the depiction; its fields do not prescribe sentence order or independent criteria of success. For character reuse, resolve actual reference coverage and stage targets.

Selected-model reads and `target_knowledge` provide `prompt_authoring`, derived
by the script from the selected record. Follow its composition guidance and
vocabulary action without first classifying the model as prose-only, tags-only
or mixed. An unlisted target may omit form metadata; the script retains that
uncertainty and still checks the real request's fields and controls. See
[Prompt input](render-contract.md#prompt-input) for each returned value.

### Keep the reading at its current scope

The final `reading.record` is complete when issued. Generated draft reading
actions include `--bind-choices`: after complete delivery, the input owner binds
the issued key to that exact choices file. It compares the captured authored
content under the file's write lock and rechecks the current stage and knowledge
scope before changing only `reading.reading_key`. A replay may refresh that
derived key without changing authored content or another draft.

`choices_binding.bound` reports the result. `choices-changed` means authored
input changed while the body pages were being read; `reading-scope-changed`
means its current required scope differs from the completed reading. Both leave
the changed choices intact and retain the completed reading, with an inspection
action for the exact owner. Follow that owner's current reading action; the
current context can reuse unchanged complete material while reading any new
requirements. A restart of a binding read derives the current stage and target
from that choices file again.

Direct low-level reads remain available without `--bind-choices`. For that
explicit path, select the issued key in `choices.reading.reading_key`; no
document hashes need copying. The input owner resolves exact document editions,
resource scope and delivered model guidance from the issuance. When authoring
a task directly, name the emitted file as `task.route_reading`.

To use a narrower amendment scope, obtain its current record through the draft's
reading action. Supply prior keys with `--known-reading` only while their complete
contents remain known in this context. The parent record keeps its original
document editions and resource scope. A declared reading context selects its
complete current deliveries automatically. Complete the current scoped read;
the binding action applies its newly issued key even when no new body text is needed.

### Select the delivered target knowledge

Choose the model with `--model MODEL_ID` and its offering with `--service SERVICE_ID`
when already selected. Without a service, the read delivers that model's complete
offering guidance for selection. With `prompt-dialect`, `--dialect ID` instead
selects a known writing family without claiming a selected model. Unknown targets
use the neutral guidance. Each selected card and writing scope arrives through
the same complete, paged snapshot. A current operation may use an already delivered
superset only when the required current source editions and model scope match.

Keep reasons for expression and source use at those actual choices. The delivery
receipt records which source bytes reached this context; it is not an exercise
in quoting instructions and does not certify comprehension or artistic quality.
For a new agent or lost context, read the complete contract for the current work
again using the status action. A prior delivery record alone supplies no knowledge.

### Create or reopen editable work

- `inspect-inputs` gathers the current task, authored content, source roles, recorded candidates and unresolved choices.
- `compare-inputs` reads selected editable candidates together through the common authoring comparison owner, including their current delivery, selected documents and source applications.
- `draft-inputs` creates `choices.json` for the actual candidate and `work-basis.json` for the acquired request, sources and current applications. `context.json` registers those owners and the starting point. `choices.target` owns the model and service; `choices.authoring` holds current task decisions, selectors for editable delivery and selected documents, and reference-use choices. Each selected file owns its content.
- `save --choices FILE` saves an authored revision; `prepare --choices FILE` compiles the current editable sources and prepares a model request. Both use the same input owners. `build-inputs` exports the derived files when a separate input package is wanted; it is not a required step before saving or preparation.

Start a new authored text task without first constructing a production-task file:

```bash
python scripts/production_workflow.py draft-inputs --root STUDIO --operation compose --request-file request.txt --route prompt-only --artifact text --execution authored --out-dir work/first-draft
python scripts/production_workflow.py save --root STUDIO --choices work/first-draft/choices.json
```

Between those calls, author the commission's selected depiction, delivery,
source roles, independent criteria and current knowledge selections. The open
work task supplies its identity. Select the actual execution kind and route;
new image work additionally needs its target, rendering and input evidence.
Unresolved choices stay explicit. `save --draft` preserves them with unfinished text. A completed target-specific prompt and an executable request apply their required input and vocabulary contracts; a saved draft does not certify either.

To edit existing work, select `--task FILE` or `--from-run RUN` and the current
`--operation compose|amend`. Supply a changed request with `--request-file FILE`;
continuation under the same request can use its saved authoring work.
Add `--model MODEL_ID` and `--service SERVICE_ID` when
selecting another target for that draft. Edit the same source files, then save
or prepare that draft.
Reopening a run restores editable source copies and reference media from its
captured inputs. Original working files may have changed or been removed.
Validation sources use automatic `@run/RUN/STUDIO_PATH` selectors; nested source
locators stay within that captured revision. Each new package retains the
qualified evidence it used for the next continuation. Select a current Studio
file explicitly when replacing a source, policy or evidence document. That
choice acquires its current contents and preserves the earlier run separately.
### Prepare an enlargement

For a plain enlargement, select `--route upscale --source-image IMAGE --scale N
--purpose TEXT`. Upscale defaults to image output and dispatcher execution.
An external absolute source is imported into the draft; a Studio source retains
its path. An explicit purpose opens a work task only when none is open and fills
unanswered purpose and criteria. The task opens when the draft is produced; a
refused command, such as one naming an unreadable image, opens no work and can
be corrected and run again. Current authority and existing judgments remain
selected. Follow [Upscale Adapter](../adapters/upscale.md) for the complete flow.

To enlarge an image already captured by Production, select its run and exact
candidate directly. `status` and the review workspace identify all candidates;
choose the intended result even when several came from one request:

```bash
python scripts/production_workflow.py draft-inputs --root STUDIO --operation compose --request-file request.txt --route upscale --source-run RUN --source-candidate CANDIDATE --scale 2 --purpose "Enlarge the selected image while preserving its content." --model MODEL_ID --service SERVICE_ID --out-dir work/enlargement
```

The input owner verifies and selects the retained image bytes, records the
originating run and candidate, and creates the ordinary upscale choices. The
upscale has its own requested result, scale and assessment. The earlier prompt,
generation criteria, review and completion remain with the earlier image;
they are available as evidence and are not reinterpreted as upscale controls.
Preparation records the selected candidate as the parent basis while the
actual source image still matches it. Selecting another source later changes
that binding. Nothing is sent, selected or adopted by drafting or preparation.
Use `--source-image` instead for an explicit local image; it cannot be combined
with the captured-candidate selector. These upscale selectors, `--scale` and
`--purpose` apply only to `--route upscale`.

### Start an existing-image edit

For a generated candidate without an accepted Studio slot, reopen its saved
input with `--from-run RUN --operation amend` and the actual `--request-file`.
Create that draft first and declare the actual `--retain` and `--change` owners.
Follow its current inspection and reading actions for the selected source,
target and stage, including additional material required as those choices change.
Select its image file from `derived_from.source_run.input_reuse.captured_outputs`;
[retained output selection](#keep-branches-and-reopen-completed-work) describes
the source acquisition and reference owners. Bind that image as the task's
`accepted-source` and `scene` reference, and declare the change and preservation
under [the semantic edit contract](semantic-instruction-edit.md#author-and-bind-the-task).
This task source needs no Studio slot acceptance or canonical adoption. Keep
the existing review findings and the other results. A prepared result's later
edit belongs to an explicit [work revision](production-work-plan.md#revise-the-result-or-items);
creating a draft alone does not replace the plan's prepared run.

To change depicted content of an accepted Studio image, select the image by its
Studio character and slot:

```bash
python scripts/production_workflow.py draft-inputs --root STUDIO --operation amend --request-file request.txt --route generation --execution dispatcher --edit-character CHARACTER --edit-slot SLOT --new-task "Replace the background of the accepted image." --out-dir work/edit
```

Use `--execution external` for a host call. The draft selects the image with
its exact slot acceptance as the scene reference and the applied `accepted-source`,
writes an editable edit plan beside the choices and carries the applicable
Production Specification, controls and validation selection of the run that
produced the image, including every subject and its explicit mapping. Sheet
adoption is not required; an applicable adopted identity keeps its separate
canonical proof. What changes and stays, the instruction text, criteria and
result destination remain unanswered and are reported together. The result may
use the source slot or a deliberately different slot. Follow
[Semantic instruction editing](semantic-instruction-edit.md#start-from-the-accepted-image)
for the complete flow.

When the target differs from the source run's prepared request, the next action
uses `retarget` with that parent run. Supply its actual reason. Reopened choices
are assessed again, including edits that restore the original target.
The saved context identifies its source, so the build can continue from the
choices file without reconstructing the source command or choosing a new generated output path. Preserve the context
beside its choices. Inspect the emitted request before preparing or sending it.

### Edit the owning authored field

| Authored area | Edit here | Builder responsibility |
| --- | --- | --- |
| `work-basis.json` | Acquire the request and source bytes through Authoring work; select applications, subjects and retained requirements. Acquire a deliberate adaptation as its own source. | Resolve current applications into task sources and preserve complete acquired originals alongside selected content |
| `target` | One selected catalog model and service, acquired model file, or evidenced external interface | Acquire that target and derive its model identity, offering, specification bindings and reference transport inputs |
| `authoring.task` | Direction, criteria and applicable task choices | Bind materialized inputs and the current source applications into the task |
| `authoring.delivery.file` | Directly editable text, or a JSON document with an optional `field` key/index array; translation notes only for an actual translation | Read the exact selected content and bind its delivered bytes |
| `authoring.documents` | Selected settings and specialist files with `{ "file": "path", "field": ["key"] }`; omit `field` to select the entire file | Read each editable owner, materialize derived content and bind task references |
| `authoring.generation` | Count, seed, continuity and applicable generation choices | Combine these choices with the selected target in the declared generation input |
| `authoring.references` | Ordered source selection, uses, exclusions, subject scope and transport choice | Rebuild the prepared set, attachment order, board placement and content hashes |
| `authoring.upscale` | Selected source, scale, settings, guidance and applicable evidence | Build the upscale declaration for the selected target and reuse its valid evidence |
| `validation` | The request-validation mode, selected contract or evidence, and execution policy | Resolve that evidence against the same acquired target and derive its exact binding |
| `task_changes.semantic_edit` | The Studio path of the editable edit plan of an existing-image edit | Bind the plan to the scene reference, the applied `accepted-source` and the declared criteria |

When a JSON application selects part of a source, the compiler can publish that
selected content at the task source's `path` and retain the complete original
under its derived `origin: {path, sha256}`. The source's derived `applications`
contains `{id, pointer, subjects, requirement}` for each actual application.
Its ordered pointers produce one selected value or, for several applications,
an ordered array of their values. Snapshot checks bind that content to the
complete original. Acquiring the exported task restores each application's
subject and requirement relationships independently of canonical identity
metadata. The compiler owns these files and bindings; acquire changed material
or update the application through the source context command.

### Select dispatcher image inputs

`authoring.references.image_input` selects how a dispatcher image input is
formed from the references. `null` writes no image input. The mirrored form `{}`
uses the other reference choices, such as a Studio source in
`additional_references`: preparation writes one image-input row per prepared
source, with its reference ID, role, prepared carrier and the authority that
preparation gave it as `use_for` and `do_not_transfer`. The carriers lie under
the new input's directory; a semantic edit matches its scene reference to the
applied `accepted-source` by the file's bytes. The explicit form is a plan with
its own `references` rows (`id`, `role`, `file`, `use_for`, `do_not_transfer`,
optional `subject_uses`), `external_request: null` and an optional
`prepared_references` path. It then owns the reference order, and the other
reference selections stay empty. Without `prepared_references`, each file is an
ordinary supplied image. With it, the existing set keeps its sources, adoption
and authority and each row takes the plan's reference ID. `choices.target`
supplies the plan's model in both forms.

`task_changes.semantic_edit` names the edit plan
(`schemas/authoring/semantic-edit-plan.schema.json`) whose `source` is the scene
reference ID. The edit draft writes it beside the choices; the draft and
preparation report each unanswered part as
`task_changes.semantic_edit.edit.target`, `.edit.change`, `.edit.preserve` or
`.review_criteria`, with `file` naming the plan. Edit the plan file in place.

### Preserve authored authority

These are separate meanings within one editable source. Criteria remain based
on the commission. A selected plot or other adopted specialist artifact retains its own approval and version; work that does not use it needs no empty substitute. A prompt
wording edit does not by itself require rewriting the plot or criteria.
The builder does not infer new approval, source authority or semantic agreement
from successful file assembly. Existing grants remain subject to their actual
scope; a new run does not inherit an exact execution authorization or claim.

### Select and change the target

Edit `choices.target` once. A catalog selection has `kind: "catalog"`, the
canonical `model` ID and selected `service`; an external host using that model
also declares the evidenced wire `operation`. A target-specific authored prompt
can select `kind: "acquired"` with `model_file` for a supplied model definition.
An unlisted image interface uses `kind: "external"`: its `model` contains the
requested identity, `target.service`, `target.model_identifier`,
`target.operation`, input contract and acquired evidence. Its optional
`reference_model` selects the catalog model needed to prepare canonical
references for that interface. Portable authored text can leave `target` null.
For target-specific authored text, keep its execution mode, native parameters,
syntax and vocabulary record with that same target selection.

The input owner projects that selection into compiled generation and upscale
inputs, the selected Production Specification and model-facing reference
bindings. Keep model and service selection at `choices.target`; the builder
writes their other representations. `choices.validation` selects the policy
and evidence for the request, without a second editable model or offering.
The complete public artifacts retain the derived target declarations needed
to interpret them independently.

For example, reopen a saved request with another selected catalog target:

```bash
python scripts/production_workflow.py draft-inputs --root STUDIO --from-run RUN --operation amend --request-file request.txt --model MODEL_ID --service SERVICE_ID --out-dir work/next-target
```

The draft retains the saved content, source definitions, references and authored
choices. Read the selected target's complete current guidance and assess how
the existing expression, controls and reference uses apply to it. Reuse a
completed reading whose source editions, operation and model scope cover the
new selection. Reuse evidence where its declared applicability still holds.
A different target alone does not justify erasing valid content, resetting
choices or discarding those records. Change the affected choices and let their
owners rebuild the deterministic consequences. Missing evidence or unresolved
judgment remains explicit at the field that needs it.

To prepare a target or runtime change with lineage to the earlier dispatcher or external image
run, use the edited choices directly:

```bash
python scripts/production_workflow.py retarget --root STUDIO --from RUN --choices work/next-target/choices.json --reason "Apply the selected target to the retained depiction." --prepare
```

Without `--prepare`, `retarget` checks the input without publishing a run.
The parent supplies lineage; its saved input and results remain intact.
The new request uses current applicable source evidence, guidance and controls.
It receives no submission claim or exact-request authorization from its parent.
Existing grants still apply according to their actual scope. Follow
[Input variations](production-variation.md) for the complete retarget contract.

### Keep branches and reopen completed work

Select `draft-inputs --from-run RUN --operation compose|amend --out-dir DIRECTORY`
for the current work. Supply the actual changed request with `--request-file FILE`.
The saved source catalog keeps original identity bytes, subject assignments,
selectors and scoped authority available, including information acquired through
a reference or state graph. The agent applies the sources relevant to this
candidate and retains the requirements the current request relies on.

Both operations seed the draft with the selected candidate's meaningful authored
content, editable documents and current source applications. `amend` starts from
the actual selected baseline and retains its identity source boundary and the
choices outside the declared change. `compose` owns a fresh current source
selection, with the previous candidate available for comparison. The
request determines which relationships to retain or reconsider; a property name
does not determine the operation. Follow [Authoring work](authoring-work.md) for
the candidate and its exact change contract. Resolve the proposed construction
within delegated authority and ask only for necessary authorial decisions.

The same boundary applies while opening a draft. If constructor choices such
as `--apply-source` would add an identity source to an `amend`, drafting refuses
before publishing the directory or opening new work. Its compose action retains
the selected task or run and the supplied request, source, target, stage and
runtime arguments. The saved source defines the retained boundary; constructor
arguments cannot redefine it.

To continue the current edits in a new compose, select their choices directly:

```bash
python scripts/production_workflow.py draft-inputs --root STUDIO \
  --choices work/amend/choices.json --out-dir work/new-compose
```

`--choices` selects this compose operation; it needs no content-reuse switch.
The current request, prompt bytes, parameters, document field selectors,
direction, criteria, recording choices and target carry into independent
editable files. The selected reading and authoring stage remain visible for
their current applicability checks. The original saved run remains comparison
evidence. Current source owners produce the new identity inventory and dependent
bindings; a historical derived witness alone never activates an old reference.
Current grants are checked against their actual operation and scope. Execution
claims and run-specific decisions remain with the runs that own them.

| Intended change | Operation |
| --- | --- |
| Change prompt wording, pose, expression or controls while retaining identity evidence | `amend` |
| Reorder the same reference uses with the same bytes, subjects, scope and authority | `amend` |
| Add, remove or replace an identity source | New `compose` |
| Change identity selectors, subjects, reference authority or accepted proof | New `compose` |
| Add or remove an environment or prop source with no identity effect | `amend` |
| Generate another result from the exact prepared input | `repeat` |

#### Continue a proposed identity replacement

Suppose a saved synthetic shell candidate uses source `design` at revision A,
and the current request selects revision B. Open an amend to retain its other
content, edit the prompt as requested, and acquire a descriptor whose `id` is
`design` and whose `path` selects B:

```bash
python scripts/production_workflow.py draft-inputs --root STUDIO \
  --from-run RUN --operation amend --out-dir work/amend
python scripts/production_workflow.py acquire-source --root STUDIO \
  --choices work/amend/choices.json --source-row inputs/design-b.json
```

The second command returns `IDENTITY_SOURCE_CHANGED` with
`cause: retained-identity-source-changed`, `draft_operation: amend` and a
`content` change for `design`. Its `evidence_owner` names the retained context;
`inspect_action` opens that evidence. The primary `repair_action` names the
unique captured candidate choices and an unused output directory. Run that
complete returned command. The new compose contains B and the edited prompt,
including when the original B file is no longer present. The original amend
and saved run still contain A. Inspect the new choices, resolve any changed
source applications and criteria, complete their applicable reading, then run:

```bash
python scripts/production_workflow.py check --root STUDIO --choices work/amend-compose/choices.json
python scripts/production_workflow.py prepare --root STUDIO --choices work/amend-compose/choices.json
```

Use the output directory actually returned by the repair when that name already
exists. `check` and `prepare` still validate the final current source selection;
creating or checking a compose performs no external generation.

For an image run, `--from-run` restores its authored inputs, including the images
that the run consumed. It does not select a captured output as the next edit's
input. The result's `derived_from.source_run.input_reuse` distinguishes these
and lists captured candidate IDs with their retained files. Choose the intended
output and its current use; the draft's `authoring_guide.source_acquisition`
reaches the existing source-row contract and command. Select the media at
`external.image_input.references` or `authoring.references` for the current
execution. Definitions, documents and applications already restored need no
re-entry. The summary keeps source metadata and actions; its source-run
`read_action` opens complete input evidence without repeating the saved task and
reading index in that summary.

Create one directory per intended branch, edit its owning files and follow the
current action. Both operations use the same editable authoring interface and
ordinary preparation. The builder recomputes request fields, media positions,
hashes and bindings from those choices. A target selection retains the need to
author wording and source applications appropriate to it.

For requested alternatives or a broad reconsideration, compare the current
editable works while developing their constructions:

```bash
python scripts/production_workflow.py compare-inputs --root STUDIO \
  --choices work/first-draft/choices.json --choices work/second-draft/choices.json
```

Repeat `--choices` for the actual works under consideration. The command reads
the current selected files and resolves task-local definitions from the current
Production Specification. It passes those actual values and their acquired
bases to [Authoring work comparison](authoring-work.md#compare-actual-candidates).
The same derived report exposes retained definitions and requirements, complete
candidate inputs, and shared or differing source applications. Use it to
reconsider a governing authored choice within the current commission, then
continue editing the owning files.

Unfinished candidates can be compared. The command returns an intermediate
read-only view; it updates neither the choices, acquired bases, source files
nor saved history. A changed definition appears in the comparison without
publishing its derived source files. Comparison provides no completed-input or
artistic-quality verdict. Refresh it after consequential edits; ordinary saving
and preparation still read and check the current owners.

When several independent drafts remain pending, `inspect-inputs` returns
`selection_required` and an `input_options` action for each. Choose the intended
draft with `inspect-inputs --choices PATH`; the report acquires only that draft
and exposes its unresolved fields and next command. Other registered branches
remain explicit comparison actions without being reread or contributing stale
diagnostics to the selected work. A later creation time alone does not choose
the user's intended branch. Separate drafts can be prepared and compared; no
inspection or preparation automatically sends all branches to a provider.
The selected draft also owns its saved result and any offered completion
command. A newer save from another branch remains a comparison. If the selected
file is unreadable, repair that file first; an unrelated reading cursor or saved
result cannot supply its continuation. Explicit inspection of that other run
still verifies its complete saved evidence.
Remove the directory of a draft that is no longer wanted: a published draft
whose directory is gone leaves the pending branches, and one remaining draft
needs no explicit selection. A draft whose creation was interrupted before its
directory was published stays listed with the command that resumes it.

Completion belongs to the saved result and its earlier scope. For another
authorized revision after its work task has closed, name the new work goal:

```bash
python scripts/production_workflow.py draft-inputs --root STUDIO --from-run RUN --operation compose --request-file request.txt --new-task "Revise the requested character prompt." --out-dir work/revision
```

This opens a new task, retains the production series and source content, and
registers the new editable location. The supplied request file preserves the
actual commission for production and review. The goal names the work for
navigation; it may summarize the request. Earlier requests and candidates remain
available in their source roles. The earlier task, result and completion stay
intact. The new task opens when its draft is produced; a refused command
opens no work. Task-specific grants and exact execution decisions remain with
their owning tasks; record current authority for new work at its normal
boundary. Add `--new-task GOAL` to the captured-result upscale command in the
same way when the source's work has ended. An already open task is never
replaced by this flag. To continue within that task, either use its own source
normally or explicitly bind another source with `--task-id ACTIVE_TASK_ID`.

The saved context carries the explicit work binding. Later inspection, saving,
preparation and retargeting resolve that same binding without requiring it to
be copied into generated tasks. Ordinary same-target preparation from a saved
run records revision lineage as well; reviews, selections, claims and completion
are never treated as judgments of the new bytes.

An explicit `build-inputs` export registers the exact task, report and generated
input bytes. In the owning Studio, `prepare --task EXPORTED_TASK` verifies that
publication and preserves the same source lineage. Its ordinary continuation
still names the editable choices. Edit those choices and build another export
when the content changes; changing generated files makes the publication no
longer match its registered source. An input package moved to another Studio
retains its source declarations in the report, but that separate Studio cannot
claim a verified local parent without the corresponding registered run evidence.

[Model request evidence](model-evidence.md#the-request-validation-record) states when a task needs an authored request validation record.
An incomplete selection returns named unresolved fields and leaves the source
task unchanged. When a canonical external reference needs an actual upload,
the builder can publish its carriers and input report for that next action,
without publishing an executable task or provider request.
An explicit `--task FILE` or `--from-run RUN` can also select the build's source.
A saved run supplies its captured task and exact delivery, so the operator does
not copy a task into another editing document. Reopening keeps the selected
revision's source and media bytes available under the new draft, including
identity sources and upload carriers. Its declared file selectors point at
those copies; original files may have changed or disappeared. Retained bounded
world, moment and scene inputs use their source run's captured graph. Selecting
a replacement uses that selection's current content and applicability.
Reassess changed source use and expression at their owning choices. Explicit `task_changes` overlays
select changed source, depiction, route or review fields; use the current
`authoring` content for ordinary editing. Authority and task identity retain
their owners.

For external work, [External request inputs](production-external-inputs.md) owns the native request, media mappings and actual upload evidence.

For identity-bearing work, construct the character's forms, details,
relationships and performance in the chosen scene from its applicable definition
at that source's original authority.
Choose the text and reference views that communicate that depiction through
the same source and criterion choices. Follow
[source to input and review coverage](../character-identity-contract.md#source-to-input-and-review-coverage)
to bind that construction to original identity sources, their scene treatment,
actual text or reference carriers and whole-subject review against original sources. The
authoring context and input report expose the derived inventory, including
identity references and state-contract owners already selected elsewhere.
The report distinguishes explicit scene bindings from unbound original source
values. Bind the concrete obligations this scene must carry, preserving exact
source, subject, carrier and review relationships. Unbound source values remain
whole-subject comparison context; they create no requirement to show every part
or write an exclusion for each part beyond the frame. The hard whole-subject
review still compares the result with the complete applicable source, at its
original authority and the current change scope. Original identity sources
retain their meaning while the authored rendition supplies this scene's depiction.

### Resume input authoring

Interruption can occur during authoring, including while an older run exists.
Inspect the open work task with:

```bash
python scripts/production_workflow.py inspect-inputs --root STUDIO
python scripts/production_workflow.py status --root STUDIO
```

`inspect-inputs` without a source selector reads the current plan's selected
unfinished inputs. When a reopened work revision has no plan, it reads every
input registered since the ledger's recorded reopen boundary. It keeps all
current branches; a later creation time does not select just one. Earlier
inputs remain in `comparison_inputs` with explicit inspection actions, without
rechecking their unresolved choices as current work. For example, reopening a
one-image task and drafting three new images exposes all three new inputs and
keeps the earlier image as a comparison. A new plan can select that earlier
input again, and `--choices PATH` can inspect it directly without changing the
current work or plan selection.

`status.current_task.authoring`, `studio.py status` and session entry expose the
same editing locations and continuation commands. The report names existing
`choices.json`, its context, published input tasks and reports, partial route
reading, completed source-delivery records, and the last recorded check when one
exists. Continue those files and actions after compaction. A source selector
still performs the ordinary inspection of that task or saved run.

Each saved draft keeps its producer's registered pack runtime. For a draft
whose producer recorded no runtime, `inspect-inputs` can use an explicit
`--state-file`, `--cache-dir` and `--managed-root` selection, with repeatable
`--pack-root` paths. The report's reading and continuation actions retain that
selection. Without explicit paths, that draft uses the caller's current
runtime. Inspection preserves the saved registration, source files and runs;
different branches resolve their models within their own selected runtimes.

The builders register each output location before publication. Recovery can
therefore find a directory that was published before its caller returned.
The reader records committed page ranges and the saved cursor. Recovery offers
the existing continuation or replay action and preserves completed delivery records. Its separate fresh-context action delivers the complete current knowledge again. Merely inspecting saved state does not issue another key or claim that the present agent read it.
Unanswered choices remain unanswered, and a saved check is diagnostic history;
preparation and execution still evaluate their actual current inputs and authority.

`scripts/production_authoring_state.py` owns these discovery pointers under
`work/tasks/TASK/authoring/`. They identify work owned by that ledger task and
do not replace its inputs, reading receipts, run records or author decisions.
Inspection reads the existing files without regenerating them or loading a
catalog merely to discover a saved path.

When a draft cannot establish its source boundary, use the reported cause and
the complete `next_action.argv` or `next_actions` entry. Each action retains the
active Python environment, installed script, Studio and available source
selection. The same structured diagnostic appears in compilation and current
authoring state; it identifies the owning file and necessary correction.

| Reported cause | Continue from its owner |
| --- | --- |
| `AUTHORING_DRAFT_UNREGISTERED` | Inspect the task's registered inputs and continue the source draft. A copied context cannot establish a new registration by itself. |
| `AUTHORING_DRAFT_REGISTRATION_INVALID` | Inspect and repair the registration that identifies the task and draft location. |
| `AUTHORING_CONTEXT_MISSING` or `AUTHORING_CONTEXT_MISMATCH` | Draft from the registered source using the returned unused output location. Existing editable content remains available for continuation. |
| `IDENTITY_SOURCE_CHANGED` with `retained-identity-source-changed` | Run the returned compose repair. For an existing draft, its `--choices` selects the captured current candidate; its separate inspection action opens the retained amend evidence. |
| Other `IDENTITY_SOURCE_CHANGED` causes | Correct the named source origin, selector or authority evidence at its owner. The specific cause determines the repair. |
| `IDENTITY_SOURCE_UNAVAILABLE` | Inspect the named source and restore or explicitly replace it before drafting its application. |

These diagnostics distinguish provenance and file-state failures from creative
judgment. Restoring a registration, context or source supplies no new identity
adoption or approval. Keep valid content and evidence, and update the choices
whose source or applicability changed. [Production diagnostics](production-diagnostics.md)
owns the diagnostic and exit-status contract.

The report compares the saved build's source and choices with the editable
content. A later edit remains pending even when its earlier build has already
been prepared. Continue the reported working copy; do not treat the older
run's request as the current draft. An incomplete edit remains visible with
its diagnostic rather than selecting an older input silently.

The authoring context gathers the work goal, current choices, unresolved
fields, source roles and paths to original or saved source bytes. Inspect the
actual documents and images needed for the next judgment. These views preserve
existing evidence and grant no approval. The older run keeps its own execution
and result-recovery actions, which remain available independently of editing.
## Scene preparation and reusable authoring input

Use [Scene Persona Material](scene-persona.md) to preserve a full-reading result for one scoped scene.
Add `scene-persona` to the task features and name local selectors as `scene_materials: [{"plan": "scene-plan.json", "bundle": "scene-material"}]`.
Preparation checks the complete source files and deterministic documents, stores their dependencies, and includes the document in `consumer.authoring_materials`.
The agent interprets the material into the selected depiction's present
circumstances, visible state, performance and relationships. Supply the
contextual premises that make those instructions intelligible in the actual
model input. Complete authoring material remains available to the author;
its presence in the consumer does not establish what the renderer receives.
Source definitions, internal keys and review evidence remain in the authoring context.
Viewpoint limits and exact submitted inputs keep their own boundaries.
Public material requires an explicit content hash and accepted-by or basis instead of a search for its producer.

For intake of existing source text, use [Source Material](source-material.md).
For observed host trials, use [Agent Evaluation](agent-evaluation.md); process success is not proof of task completion or expressive quality.
For recurring failures, use [Repair Analysis](repair-analysis.md) over actual reviews, then the repair and authorization process.
None of these commands adopts or sends.
