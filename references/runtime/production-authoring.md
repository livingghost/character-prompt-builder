# Production authoring

Edit the commission, selected depiction and source use at their owning locations. Save authored text or prepare an image request from those same choices. The author judges meaning; the input owners derive paths, hashes and repeated bindings.

## Assemble authored choices

### Discover input structures

`draft-inputs` returns `authoring_guide` and retains it in `context.json`. Use its
`explain_action` to locate the current editable files and the contracts of the
selected fields before writing them:

```bash
python scripts/production_workflow.py explain-inputs --root STUDIO --choices work/input/choices.json
python scripts/production_workflow.py explain-inputs --root STUDIO --choices work/input/choices.json --field authoring.documents.negative_provenance
python scripts/production_document_contracts.py explain production_spec
python scripts/production_document_contracts.py validate negative_provenance STUDIO/work/input/negative_provenance.json
```

`explain-inputs` reads the chosen draft without compiling a request or loading
past runs. It distinguishes a field required in the draft schema from a choice
that still needs an actual value before preparation. Select `--field` for one
field or `authoring.documents.NAME` for its current source and complete contract.
The document registry supplies required and permitted keys, the canonical
schema when one exists, the logical validator otherwise, examples and remaining
contextual checks. A document-level success does not establish request readiness.

The [complete first-input example](../../examples/input-authoring/README.md)
creates all selected inputs and prepares one reference-guided image in a fresh
Studio with no previous run. Use it to understand the relationships; start the
actual work from its own draft and actual authority. The [state-aware
pilot](../../examples/state-aware-pilot/README.md) owns the additional complete
state-derived artifacts when those features apply.

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

`artifact_type` belongs only to contracts that declare that discriminator.
Inspect the selected document's permitted keys rather than copying fields from
another kind. `owner-direction.json` is not a reserved artifact type: an original
commission may be prose or structured data, with its source role and locator in
the task. The task's production direction has its own declared schema.

After preparation, inspect the returned `status --run RUN` action for that
request. Unqualified `status` inspects all registered runs and has broader cost.
Both forms report source changes separately from the saved request's execution
requirements; neither requires restoration of edited original files.

Use [Craft consultation](craft-consultation.md) while deciding what to write or revise.
Open the work task before reading or drafting its inputs, using
`work_ledger.py begin --studio STUDIO --goal TEXT --step TEXT`. Reuse its task ID
through input authoring and preparation. The input builders and route reader
save their progress under that task automatically.

### Select and read the current knowledge

Begin with the route, current operation, actual execution kind, applicable
features and selected model or prompt family. `author` and `save` select the
applicable authoring contract; `prepare`, `execute`, `review` and `adopt` select
their complete operation contracts. Take `authored`, `external` or `dispatcher`
from the task. An omitted operation uses the route's declared default, shown by
`execution_routes.py inspect ROUTE --execution EXECUTION`.

```bash
python scripts/execution_routes.py read reference-artifacts --operation author --execution authored --root STUDIO --feature sparse-retrieval
```

The first response is a source and heading index, with `mode: "index"`, an empty
`body`, and `reading: null`. It reports the selected operation, execution,
features and model; each source's exact content hash, byte size and selection
owners; and all pending headings. `progress.required_bytes` measures the complete
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

Inspect that scope before reading. Choose the operation actually in progress
and the specialists the task uses. For example, `studio-placement` selects the
complete contract for correcting an existing iteration's current scene or slot;
ordinary image creation does not select that correction. Preparation and execution
receive the complete [diagnostic-handling contract](production-diagnostic-navigation.md).
Consult the linked global code catalog when resolving the reported failure.
Headings guide navigation within a selected source; they never silently remove
prerequisites, constraints, exceptions or recovery instructions from its required
contract.

The index supplies an exact `selector` for each source available to read and each
heading. An explicitly `known` source has a null selector; if its text is no longer
available, start a fresh index without that known-reading assertion. Use its
`section_selection.argv` plus `--section SELECTOR` to read that choice, or execute
`actions.next` to read the first missing required section. A source selector
reads that entire source; a heading selector reads its exact byte segment up to
the next heading. Markdown headings inside fenced examples are not sections.
Writing-guide sections, dialect records and model offering cards have their own
exact JSON segments, including the source opening and closing bytes.

```bash
python scripts/execution_routes.py read --snapshot SNAPSHOT --section SELECTOR --root STUDIO
```

Use the complete returned invocation when a custom ledger or pack runtime is
selected. `actions.index` reopens the saved index and its current coverage.
`actions.all` explicitly delivers every remaining required byte in bounded pages.
Each executable action provides an `argv` argument array, the same invocation
quoted in `command`, and a `reason`. Execute the full `argv` or `command`.
It is also available when starting a new reading:

```bash
python scripts/execution_routes.py read reference-artifacts --operation author --execution authored --root STUDIO --feature sparse-retrieval --all
```

Every body response is one JSON object. Read its `body` entries in order. Each
entry contains exact source text in `text` and its kind, path, hash and byte range
in `metadata`. Top-level `metadata` identifies the selected scope. `progress`
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

The actions retain the selected environment's Python, installed script, absolute
reading ledger, Studio when present, byte budget and exact pack runtime, including
additional discovery roots. A snapshot fixes the route, operation, execution,
features, model, prompt family and explicit same-context sources. A page cursor
also fixes its delivery selection. `--reading-ledger` selects the ledger.
Otherwise an explicit `CPB_READS_LEDGER` takes priority, followed by the specified
or current Studio's ledger, then the configured home ledger.

The reader preserves every required byte and issues a reading only after complete
coverage and a fresh check of actual documents, resources and selected-model
contents. Its record retains whole-source hashes and the original issuance of
every reused body. A source change during reading names the changed owners and
provides `actions.restart`, which opens a new current index. A new reading checks
its ledger before publishing an index or source body. Following a document link,
viewing a heading index or retaining a file path alone does not deliver that
source's contents.

For another operation in the same active context, use the appropriate
`context_reuse.operations` action from a completed result. For example,
`context_reuse.operations.execute` indexes the current execute contract using
complete knowledge retained from preparation. These commands carry repeatable
`--known-reading KEY` selections. The reader compares exact source kind, path,
content and resource/model scope, then delivers new or changed bodies in full.
Choose sections or `actions.all` to complete the current reading. When no new
bytes are needed, `actions.all` checks the current sources and issues the current
record without repeating unchanged bodies.

When changing model, service, features or route, begin an index with the actual
selections and the `context_reuse.arguments` of complete readings still known in
this context. Model and resource scope are independent of shared documents: a
changed model preserves unchanged workflow knowledge and requires its own card.
A changed required document or resource is delivered fully. An unneeded specialist
or pack release/lock change does not discard unchanged required knowledge. These
reads preserve prepared inputs and authored decisions; delivery evidence does not
rewrite creative work.

A new agent, compacted conversation or lost source context opens the index for the
operation now needed, with no `--known-reading` selections. Use
`context_reuse.fresh_context`, `actions.restart` or the fresh-context action in
Studio status. Restart retains the selected task scope and existing authoring
files while making no assertion of retained knowledge. Continue the work's saved
choices and current phase; a fresh context need not repeat completed production
operations. A ledger, partial pages or historical key alone never supply knowledge.
An incomplete reading cannot contribute known bodies.

An acquired model outside the catalog uses `--model-file FILE` in place of
`--model`. A relative path is resolved within the Studio. The reader selects the
same complete model and writing guidance, binds its exact edition, and retains
its source for continuation and fresh-context reading. This source matches
`choices.target.model_file` when saving target-specific text; the input owner
derives the compiled task target from that selection.

## Use the delivered knowledge

Read interface guidance; resolve the optional `prompt-writing-guide` and read the complete selected guide before final rendition. Preserve authored meaning while applying its syntax and target evidence. Inspect complete selected knowledge records for actual construction questions. A selected specification records the depiction; its fields do not prescribe sentence order or independent criteria of success. For character reuse, resolve actual reference coverage and stage targets.

The final `reading.record` is complete when issued. Set `choices.reading.reading_key`
to that issued key. The input owner resolves the exact document editions, selected
resource scope and delivered model guidance from the issuance. When authoring a
task directly, name the emitted file as `task.route_reading`.

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

- `inspect-inputs` gathers the current task, authored content, source roles, recorded candidates and unresolved choices.
- `draft-inputs` creates `choices.json` as the editing source and a separate `context.json` for provenance and the selected starting point. `choices.target` owns the model and service selection. `choices.authoring` holds meaningful task decisions, selectors for editable delivery and selected documents, and reference-use choices. The original files own their content; the context file owns derived provenance.
- `save --choices FILE` saves an authored revision; `prepare --choices FILE` compiles the current editable sources and prepares a model request. Both use the same input owners. `build-inputs` exports the derived files when a separate input package is wanted; it is not a required step before saving or preparation.

Start a new authored text task without first constructing a production-task file:

```bash
python scripts/production_workflow.py draft-inputs --root STUDIO --route prompt-only --artifact text --execution authored --out-dir work/first-draft
python scripts/production_workflow.py save --root STUDIO --choices work/first-draft/choices.json
```

Between those calls, author the commission's selected depiction, delivery,
source roles, independent criteria and current knowledge selections. The open
work task supplies its identity. Select the actual execution kind and route;
new image work additionally needs its target, rendering and input evidence.
Unresolved choices stay explicit. `save --draft` preserves them with unfinished text. A completed target-specific prompt and an executable request apply their required input and vocabulary contracts; a saved draft does not certify either.

To edit existing work, draft with `--task FILE` or `--from-run RUN` instead of
the new-task selectors. Add `--model MODEL_ID` and `--service SERVICE_ID` when
selecting another target for that draft. Edit the same source files, then save
or prepare that draft.
Reopening a run restores editable source copies and reference media from its
captured inputs. Original working files may have changed or been removed.
Validation sources use automatic `@run/RUN/STUDIO_PATH` selectors; nested source
locators stay within that captured revision. Each new package retains the
qualified evidence it used for the next continuation. Select a current Studio
file explicitly when replacing a source, policy or evidence document. That
choice acquires its current contents and preserves the earlier run separately.
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
python scripts/production_workflow.py draft-inputs --root STUDIO --route upscale --source-run RUN --source-candidate CANDIDATE --scale 2 --purpose "Enlarge the selected image while preserving its content." --model MODEL_ID --service SERVICE_ID --out-dir work/enlargement
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

To change depicted content of an accepted Studio image, select the image by its
Studio character and slot:

```bash
python scripts/production_workflow.py draft-inputs --root STUDIO --route generation --execution dispatcher --edit-character CHARACTER --edit-slot SLOT --new-task "Replace the background of the accepted image." --out-dir work/edit
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

| Authored area | Edit here | Builder responsibility |
| --- | --- | --- |
| `target` | One selected catalog model and service, acquired model file, or evidenced external interface | Acquire that target and derive its model identity, offering, specification bindings and reference transport inputs |
| `authoring.task` | Direction, criteria, declared source use and applicable task choices | Bind materialized inputs into the task |
| `authoring.delivery.file` | Directly editable text, or a JSON document with an optional `field` key/index array; translation notes only for an actual translation | Read the exact selected content and bind its delivered bytes |
| `authoring.documents` | Selected settings and specialist files with `{ "file": "path", "field": ["key"] }`; omit `field` to select the entire file | Read each editable owner, materialize derived content and bind task references |
| `authoring.sources` | Declared text or JSON source content by source ID | Preserve source roles and locators, write the selected body and update its path |
| `authoring.generation` | Count, seed, continuity and applicable generation choices | Combine these choices with the selected target in the declared generation input |
| `authoring.references` | Ordered source selection, uses, exclusions, subject scope and transport choice | Rebuild the prepared set, attachment order, board placement and content hashes |
| `authoring.upscale` | Selected source, scale, settings, guidance and applicable evidence | Build the upscale declaration for the selected target and reuse its valid evidence |
| `validation` | The request-validation mode, selected contract or evidence, and execution policy | Resolve that evidence against the same acquired target and derive its exact binding |
| `task_changes.semantic_edit` | The Studio path of the editable edit plan of an existing-image edit | Bind the plan to the scene reference, the applied `accepted-source` and the declared criteria |

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
python scripts/production_workflow.py draft-inputs --root STUDIO --from-run RUN --model MODEL_ID --service SERVICE_ID --out-dir work/next-target
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

Create one draft directory for each intended model or prompt variation using
`draft-inputs --from-run RUN --out-dir DIRECTORY`. Each draft starts from the
selected saved bytes. Change the prompt, target, parameters, reference uses or
other meaningful choices in that draft, then follow its current action. The
builder recomputes request fields, media positions, hashes and bindings from
those choices. It preserves unchanged criteria, source meanings and applicable
evidence. A prompt change does not require a different medium or composition,
and a model change does not invent equivalent syntax or reference capability.

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
python scripts/production_workflow.py draft-inputs --root STUDIO --from-run RUN --new-task "Revise the requested character prompt." --out-dir work/revision
```

This opens a new task, retains the production series and source content, and
registers the new editable location. The earlier task, result and completion
stay intact. The new task opens when its draft is produced; a refused command
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
actual text or reference carriers and independent whole-subject review. The
authoring context and input report expose the derived inventory, including
identity references and state-contract owners already selected elsewhere.
Complete uncovered definitions at those choices. Canonical identity sources
stay at their owning paths while the authored rendition supplies this scene's
depiction.

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
| `IDENTITY_SOURCE_CHANGED` | Inspect the current identity source and reassess its application and criteria. A live task can supply a new draft; a saved run exposes its retained evidence for explicit source selection. |
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
