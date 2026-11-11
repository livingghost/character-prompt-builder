# Production authoring

Edit the commission, selected depiction and source use at their owning locations. Save authored text or prepare an image request from those same choices. The author judges meaning; the input owners derive paths, hashes and repeated bindings.

## Assemble authored choices

Use [Craft consultation](craft-consultation.md) while deciding what to write or revise.
Open the work task before reading or drafting its inputs, using
`work_ledger.py begin --studio STUDIO --goal TEXT --step TEXT`. Reuse its task ID
through input authoring and preparation. The input builders and route reader
save their progress under that task automatically.

### Read the route to completion

Begin with the route, current operation, actual execution kind, applicable features and the target's model or prompt family. Select `--execution authored`, `external` or `dispatcher` from the task. `--operation author` and `save` deliver the applicable authoring contract; `prepare`, `execute`, `review` and `adopt` deliver their complete owning contracts for that execution. Omit the operation to use the route's declared default, shown by `execution_routes.py inspect ROUTE --execution EXECUTION`. Every route read is paged by default, with at most 16,384 source bytes per page. Use `--page-bytes N` to select another source-byte budget:

```bash
python scripts/execution_routes.py read reference-artifacts --operation author --execution authored --root STUDIO --feature sparse-retrieval --page-bytes 16384
```

Each invocation returns one JSON object. Read its `body` array in order: each
entry contains the exact source text in `text` and its kind, path, content hash
and byte range in `metadata`. The top-level `metadata` identifies the selected
route, operation, execution, features and model. `progress` reports newly
delivered, remaining, reused and total required source bytes. Source text and
control fields are separate, so text inside a document cannot become an action.

While `actions.continue` is an action object, execute its complete `argv`
argument array or the same invocation quoted in `command`. Its `reason` explains
the action. At completion, `actions.continue` is explicitly `null`, and `reading`
contains the issued `key`, the `reading.record` path and its absolute location.
An incomplete page has `reading: null` and `context_reuse: null`. Stop paging at
the terminal null; use the completed reading for the current task.
`actions.replay` delivers that page again. `actions.restart` reads the complete
current scope from the beginning. If the host truncates output, replay with a
smaller `--page-bytes` budget, then follow the returned continuation. Studio
status also exposes the saved reading and its recovery action if no complete
JSON response reached the agent. A successful command alone does not establish
that truncated text was read.

The actions retain the selected environment's Python, installed script,
absolute reading ledger, Studio when present, page budget and exact pack
runtime, including additional discovery roots. A cursor fixes its route,
operation, execution, features, selected model, prompt family and explicit
same-context sources. `--reading-ledger` selects that ledger. Otherwise an
explicit `CPB_READS_LEDGER` location takes priority, followed by the specified or
current Studio's ledger, then the configured home ledger.

The complete required scope includes the operation's prerequisites, constraints,
exceptions and recovery instructions as well as route and specialist knowledge.
Authored text receives its save, delivery and review contract. An external
request receives the native request and host-call contract; dispatcher work
receives its package, authentication and transport contract. Following links
does not deliver their bodies. The reader preserves every required source byte
and issues a current reading only after complete coverage and a fresh check of
actual document, resource and selected-model contents. A source change during
paging names the changed owners and provides a restart action. A new reading
checks its ledger first: a ledger that cannot be read is reported before any
body is delivered.

For a later operation in the same active context, execute the appropriate
`context_reuse.operations` action from a completed result. For example,
`context_reuse.operations.execute` reads the current execute contract using
complete knowledge retained from preparation. These executable commands include
repeatable `--known-reading KEY` selections for the completed readings in that
context. The reader combines their complete bodies, compares exact kind, path,
content and model/resource scope, and delivers each new or changed body in full.
It issues a reading for the requested current operation after that union is
complete. The issuance retains the origin of every reused body. A prepare
receipt plus an execute receipt can therefore supply unchanged bodies for
review without repeating them, while new review instructions still arrive.

When changing the model, service, features or route, begin the current read
with those actual selections and the `context_reuse.arguments` from readings
still known in this context. Resource and model scope are checked independently
of shared documents: a changed model does not erase unchanged workflow
knowledge, and an old model card does not substitute for the new one. A changed
required document or resource is delivered fully. An unneeded specialist or
pack release/lock change does not discard unchanged required knowledge. These
reads preserve prepared inputs and authored decisions; they update delivery
evidence, not the creative work.

A new agent, a compacted conversation or lost source context starts a complete
read with no `--known-reading` selections. Use `context_reuse.fresh_context`,
`actions.restart`, or the fresh-context action in Studio status. Restart keeps
the selected task scope but carries no assertion of retained knowledge. A saved
ledger, partial pages or reading key alone never supply knowledge. Select a
known reading only when its complete bodies remain available in the current
context; an incomplete read cannot contribute known bodies.

An acquired model definition outside the catalog uses `--model-file FILE` in place of `--model`. A relative file is resolved within the Studio. The reader delivers the same complete model and writing guidance, binds its exact edition, and retains its source for page continuation and fresh-context reading. This source matches `choices.target.model_file` when saving a target-specific prompt; the input owner derives the compiled task's target from that selection.

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
with the captured-candidate selector.

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
| `authoring.documents` | Selected settings and any required specialist material, inline or `{ "file": "path", "field": ["key"] }` | Read their owning files, materialize derived content and bind task references |
| `authoring.sources` | Declared text or JSON source content by source ID | Preserve source roles and locators, write the selected body and update its path |
| `authoring.generation` | Count, seed, continuity and applicable generation choices | Combine these choices with the selected target in the declared generation input |
| `authoring.references` | Ordered source selection, uses, exclusions, subject scope and transport choice | Rebuild the prepared set, attachment order, board placement and content hashes |
| `authoring.upscale` | Selected source, scale, settings, guidance and applicable evidence | Build the upscale declaration for the selected target and reuse its valid evidence |
| `validation` | The request-validation mode, selected contract or evidence, and execution policy | Resolve that evidence against the same acquired target and derive its exact binding |

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
not copy a task into another editing document. Reassess changed source use and expression at their owning choices. Explicit `task_changes` overlays
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
