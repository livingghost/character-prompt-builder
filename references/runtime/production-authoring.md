# Production authoring

Compose or amend the actual candidate through [Authoring work](authoring-work.md).
Edit its commission, selected depiction and source use at their owning locations.
Save authored text or prepare an image request from those same choices. The author
judges meaning; the input owners derive paths, hashes and repeated bindings.

## Assemble authored choices

### Discover input structures

`draft-inputs` returns `authoring_guide` and retains it in `context.json`. Use its
`explain_action` to locate the current editable files and the contracts of the
selected fields before writing them:

```bash
python scripts/production_workflow.py explain-inputs --root STUDIO --choices work/input/choices.json
python scripts/production_workflow.py explain-inputs --root STUDIO --choices work/input/choices.json --field authoring.documents.negative_provenance
python scripts/production_workflow.py explain-inputs --root STUDIO --choices work/input/choices.json --field target.model
python scripts/production_workflow.py explain-inputs --root STUDIO --choices work/input/choices.json --field external
python scripts/production_workflow.py explain-inputs --root STUDIO --choices work/input/choices.json --field external.image_input.external_request
python scripts/production_workflow.py explain-inputs --root STUDIO --choices work/input/choices.json --field authoring.task.recording
python scripts/production_document_contracts.py explain production_spec
python scripts/production_document_contracts.py explain production_spec --pointer /properties/subjects/items
python scripts/production_document_contracts.py validate negative_provenance STUDIO/work/input/negative_provenance.json
```

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
default full view remains available with `--view full`. Summarizing changes
neither the checks performed nor the command's exit status.
`inspect-inputs` applies the [current-work navigation contract](production-workflow.md#open-the-current-work):
bounded input, reading and decision lists retain `total`, `omitted` and the
complete report location in their `<name>_summary`. Its `diagnostics` owns each
unresolved finding once; input rows and `context.input` use `diagnostic_ids`.
Repeated reading commands use `action_ref` to their executable summary location.
Every distinct unresolved finding remains visible even when its branch is
outside the displayed list. Complete source changes, hashes and historical
notes remain available in the saved report.

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
procedures stay with their operation owners. Sparse discovery receives its
general construction basis during depiction; explicitly adding `finishing`
requires the whole specialist. Other specialists without an explicit scoped
profile remain complete. A profile refines only selected documents and never
activates an unrelated specialist. The selected model card and applicable
resource instructions remain complete. The prompt-knowledge boundary is also
delivered through the reader.

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
same-context reading supplies every required body.

Source states have explicit meanings: `pending` has no delivered bytes;
`partial` has some delivered ranges and still needs the rest; `delivered` has
complete source coverage in this snapshot; and `known` comes from an explicitly
selected complete reading whose source is unchanged. `same_context_required`
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
`actions.next` to read the first missing required section. A source selector
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
`actions.all` explicitly delivers every remaining required byte in bounded pages.
Each executable action provides an `argv` argument array, operation name
`command: read`, and a `reason`. Execute the full `argv`. Continuations restore
the exact pack runtime from their snapshot; those arguments need no repeated
entry on every page.
It is also available when starting a new reading:

```bash
python scripts/execution_routes.py read reference-artifacts --operation author --execution authored --root STUDIO --feature sparse-retrieval --all
```

Every body response is one JSON object. Read its `body` entries in order. Each
entry contains exact source text in `text` and its kind, path, hash and byte range
in `metadata`. A document body binds the complete original source with
`source_sha256` and `source_size`, and its delivered interval with `source_start`,
`source_end`, `sha256` and `size`. Page `start` and `end` are offsets within that
body; adding `source_start` gives the original document offsets. Top-level `metadata` identifies the selected scope. `progress`
reports required, reused, delivered and remaining source bytes; section and replay
progress also report the bytes left in that selected delivery. Source text and
control fields are separate, so text inside a document cannot become an action.
`--page-bytes N` sets the source-byte budget, which defaults to 16,384 bytes.
It applies to section and full deliveries alike and preserves UTF-8 boundaries.

Follow `actions.continue` while the selected section or full delivery has another
page. When a section ends, `actions.continue` becomes `null`; if required material
remains, choose another indexed section or use `actions.next` or `actions.all`.
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

For another operation in the same active context, use the actual next draft's
reading action and append `context_reuse.arguments` from a completed result.
`context_reuse.operations` offers inspection of the current operation; it does
not choose the next operation, destination or candidate. The arguments carry
repeatable `--known-reading KEY` selections. The reader compares exact source kind, path,
content and resource/model scope, together with the exact source interval, then
delivers every missing
or changed required range. A complete earlier full source can cover a later
required section, and several complete earlier ranges can cover parts of a
broader requirement. Their union never certifies an unread gap. A scope change
indexes those missing intervals explicitly before any current reading is issued.
Choose sections or `actions.all` to complete the current reading. When no new
bytes are needed, `actions.all` checks the current sources and issues the current
record without repeating unchanged bodies.

For curation, the actual draft supplies its destination and source owner.
Moving from slot acceptance to sheet adoption uses that draft's `reading_action`
and the same explicit retained keys. Shared sections remain known only through
those keys, and additional canonical-use sections are delivered before completion.

When changing model, service, features, route, destination or source kind, begin an index with the actual
selections and the `context_reuse.arguments` of complete readings still known in
this context. Model and resource scope are independent of shared documents: a
changed model preserves unchanged workflow knowledge and requires its own card.
A changed required document delivers all its required ranges again; a changed
resource delivers its complete selected body. An unneeded specialist
or pack release/lock change does not discard unchanged required knowledge. These
reads preserve prepared inputs and authored decisions; delivery evidence does not
rewrite creative work.

##### Rebuild knowledge in a fresh context

A new agent, compacted conversation or lost source context opens the index for the
operation now needed, with no `--known-reading` selections. Use
`actions.restart` (also referenced by `context_reuse.fresh_context`) or the fresh-context action in
Studio status. Restart retains the selected task scope and existing authoring
files while making no assertion of retained knowledge. Continue the work's saved
choices and current phase; a fresh context need not repeat completed production
operations. A ledger, partial pages or historical key alone never supply knowledge.
An incomplete reading cannot contribute known bodies.

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

The final `reading.record` is complete when issued. Set `choices.reading.reading_key`
to that issued key. The input owner resolves the exact document editions, selected
resource scope and delivered model guidance from the issuance. When authoring a
task directly, name the emitted file as `task.route_reading`.

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
draft with `inspect-inputs --choices PATH`; the report then exposes that draft's
unresolved fields and next command. A later creation time alone does not choose
the user's intended branch. Separate drafts can be prepared and compared; no
inspection or preparation automatically sends all branches to a provider.
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
relationships and performance in the chosen scene from its adopted definition.
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

`inspect-inputs` without a source selector reads the task's saved authoring
state. `status.current_task.authoring`, `studio.py status` and session entry expose the same editing locations and continuation commands. The report names existing
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
