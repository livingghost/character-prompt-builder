# Studio Runtime

Activate this document when character work will outlive one session: a character whose sheet is filled over days, images generated again and again until one is accepted, and decisions that get reversed. A studio is the directory where that work lives: the sheet, the runs, the gallery and the trail. Authoring that accumulates decisions a later draft reuses is such work, with or without an image: it gets its studio before the first draft that will be revised, and a narrative series can live inside it. Ordinary one-off prompt work and a one-off answer need no studio.

## Contents

- [Why a studio](#why-a-studio)
- [Layout](#layout)
- [Service authentication](#service-authentication)
- [The work trail](#the-work-trail)
- [Every image with what produced it](#every-image-with-what-produced-it)
- [Record a missing generation package](#record-a-missing-generation-package)
- [Failed send recovery](#failed-send-recovery)
- [Session entry](#session-entry)
- [Validation](#validation)
- [What leaves a studio](#what-leaves-a-studio)
- [Adoption and resumption](#adoption-and-resumption)
- [Production-owned candidates](#production-owned-candidates)
- [Artifact evidence and completion](#artifact-evidence-and-completion)

## Why a studio

Two things go wrong when character work has no home of its own. Generated images pile up with nothing that says which settings produced which, so the next day's generation drifts in quality and nobody can say why. And a session that loses its context mid-task, or a new session picking the work up, cannot tell what was done, what was being done, and what comes next. A studio answers both: an iteration is a generated image the studio recorded with the exact request that produced it, and the open task is written down step by step as it is done.

## Layout

```bash
python scripts/studio.py init --out <dir> --studio-id <id> --title "<title>"
```

```text
<studio>/
  studio.json                 id, title, defaults, when it was created, the characters
  credentials.json            optional private API key or environment source for each service
  work/current.json           the open task: goal, steps, which are done, what is next, what it is blocked on
  work/ledger.jsonl           task events and actual answers; append only
  work/tasks/<task-id>/       current task snapshot and immutable prior revisions
  work/batches/<batch-id>.json small attempt index; points to its owned result tree
  work/activity/events/      immutable redacted operator events
  work/activity/timeline.*   rebuildable chronological JSONL and Markdown views
  logs/operations/<day>/<id>/ automatic CLI diagnostics, console streams and artifact hashes
  characters/<id>/
    sheet/                    the Character Sheet (sheet-data.json and its renders)
    iterations/<it-id>/       one directory per generated image: result, request, response, package
    iterations.jsonl          one record per iteration: slot, status, hashes, service, seed
    accepted/<slot>.<ext>     the image accepted for each slot
  packages/                   Generation Packages built here
  runs/<run-id>/              the journal of one send: exact request and answer, package and downloaded results
  prompts/                    reviewed prompt artifacts that belong to no single iteration
  story/narrative/            a narrative series, when the studio holds authoring
```

`init` records project preferences and workflow defaults:

- `default_render_profile`, `null` unless `--default-render-profile` names a selected project preference;
- `default_creative_latitude`, `directed` unless `--default-creative-latitude` names another;
- `default_interaction_mode`, `balanced` unless `--default-interaction-mode` names another;
- `default_style_family`, `null` unless `--default-style-family` names a selected project preference.

An unselected rendering preference leaves the treatment to the current
[production direction](production-direction.md); initialization selects no
medium, palette, light or emotional register. A catalog profile is available
knowledge, not an implicit substitute for `null`. Preserve an explicitly
selected project profile or family and apply its actual scope under the
commission. Existing adopted treatments and the preserved parts of a local
edit keep their authority; a new project preference does not rewrite them.

`python scripts/studio.py character add <id> --studio <dir> [--profile ...]` adds a character with a blank sheet in `sheet/`; the Character Sheet workflow then runs in that folder as [Character Sheet Discipline](character-sheet-discipline.md) describes, with `SHEET_DIR` being `characters/<id>/sheet`.

A narrative series is initialized into its own subdirectory, `python scripts/narrative_init.py --out <studio>/story ...`, and [Narrative Authoring](../narrative-authoring.md) owns its files. The studio manifest lists no series; `validate_studio.py` leaves the subdirectory to the narrative checks. Registering a visual character with `character add` comes when an image is wanted, not before.

## Service authentication

Use [Studio authentication](studio-authentication.md) to configure the service ID selected by the model's offering. The Studio's optional private `credentials.json` has one entry per service. Its `api_key` field holds a saved value, or its `api_key_env` field names a runtime environment variable. Models offered by the same service use that entry. The Agent follows the existing configuration and the credential owner's chosen method.

For a runtime environment source, the Agent configures the intended variable:

```bash
python scripts/studio.py credentials prepare SERVICE --environment LOCAL_API_TOKEN --studio STUDIO
```

Execution reads that variable from its own process when it needs authentication. The JSON records only the name. The Agent checks the same service and target run once the value is available. `set --from-env` instead copies the variable's current value into the service's saved `api_key` field.

For a saved-value source, use the offering's selected service ID to inspect the
configuration and prepare the private input file:

```bash
python scripts/studio.py credentials status SERVICE --studio STUDIO
python scripts/studio.py credentials prepare SERVICE --studio STUDIO
```

The Agent prepares the required service entries before handing the JSON to the owner and pauses its own edits until saving is complete. Give the returned `input.path`, the service name and `input.json_pointer`. The owner fills `api_key` directly under that service name and saves valid JSON. An empty string reports input pending; repeated preparation preserves existing values and environment sources. Saving completes the owner's input step.

This handoff requires access to the same file the Agent prepared. After saving, the Agent checks that service and the target run's authentication selection and readiness before continuing its next action. Status keeps the values private while reporting the selected source and availability.

The authentication owner defines source changes, rotation, removal and recovery of an execution's recorded source. An explicit `prepare --environment NAME` selects the live variable; `prepare --stored` prepares a saved field when changing from the environment and retains an existing saved value. Hidden terminal input, stdin and environment import supply saved values through `set`. Each service has one current authentication source.

The private JSON is excluded from ordinary production inputs, artifact registration and Skill packaging. A whole Studio folder copy includes it; copied saved values are independent of the original file, while environment entries read variables from the new process. Follow the authentication document when moving or sharing a Studio. The API key supplies service access, and the run's grants and exact request approval authorize its operation.

## The work trail

The work ledger follows Production tasks from planning and authoring through verified completion of their deliverables. Studio administration completes through each command's result and [operation record](operation-logs.md), which retain its outcome and diagnostics.

Open a task before production work that takes more than one step, and write the steps down:

```bash
python scripts/work_ledger.py begin --studio <dir> --goal "C02 base front" \
  --step "generate three candidates from the recipe of C01" \
  --step "present them and record the choice" \
  --step "accept the chosen one for base.front"
python scripts/work_ledger.py step --studio <dir> 1 --note "it-0004 to it-0006"
python scripts/work_ledger.py block --studio <dir> "which of the three, or another round"
python scripts/work_ledger.py show --studio <dir>
```

Mark each step as it is done, not at the end. A step that is not written down is
a step the next session does again or skips. Close the task by naming its actual
completed run:

```bash
python scripts/work_ledger.py finish --studio STUDIO --run RUN
```

`finish` requires the run explicitly and identifies its owning task. It refuses
while that task has an unfinished step, an unanswered author question or lacks
verified completion for the named run. It can close the suspended owning task
while leaving another active task in place. It marks no unfinished step as done
and supplies no missing answer. Repeating an already recorded closure returns
that closure. If work remains, resolve it through the owning task's ordinary
workflow.

`abandon --reason` closes a task that will not be finished; once the task has a
prepared production run, it also requires `--actor`. `block` records the question
the task waits on, so a resumed session asks it instead of guessing. `show`
prints where the task stands; `studio.py status` prints the same beside every
character's slots and candidates, and the scene materials a persona change
reaches.

### Answers, returning to an earlier step, and temporary task switches

`block` returns a unique `question_id`. Read the actual answer and record it with
`respond` before taking the next action that depends on it. Keep the question,
answer, speaker and applicable candidate identities together; an ordinary `note`
does not resolve the question. A revised choice uses a new question rather than
rewriting the earlier answer.

```bash
python scripts/work_ledger.py respond --studio STUDIO --question-id QUESTION_ID --answer "Actual answer" --actor "Actual speaker"
python scripts/work_ledger.py reopen --studio STUDIO --from-step 1 --reason "Actual reason to revisit design" --actor "Actual decision maker"
python scripts/work_ledger.py suspend --studio STUDIO --reason "Await another choice while independent work proceeds"
python scripts/work_ledger.py begin --studio STUDIO --goal "Independent work" --step "Plan"
python scripts/work_ledger.py suspend --studio STUDIO --reason "Return to the earlier character"
python scripts/work_ledger.py resume-task --studio STUDIO --task-id PREVIOUS_TASK_ID
```

`respond` may additionally bind `--evidence STUDIO_RELATIVE_FILE` and repeated `--candidate ID` values. It records an answer, not generation or adoption approval. `reopen` snapshots the previous revision, including completed steps and linked run, before resetting the chosen and later steps. It neither deletes results nor changes any accepted artwork. `suspend` preserves questions, notes and the next step; only one task is active, and `resume-task` does not implicitly suspend a different task. `show` includes suspended task IDs and open question IDs so the next session need not reconstruct these from chat. Terminal tasks cannot be resumed as active work.

The ledger's `at` records when the entry was written. If an answer is recovered
later, append its record at the current time and bind the original instruction
with `--evidence`. Identify the original message or passage, including its source
timestamp when available, in the answer. Preserve uncertainty when the decision
time is unavailable; do not backdate the ledger or infer the answer time from a
later action. The recovered answer remains distinct from any required generation
or adoption approval.

The prior run in the same explicit production series is still a protected-criteria dependency. Neither reopening a work step nor switching tasks is a means to discard that authority history.

A checkpoint is a `note` or a `step` written at a boundary where loss would cost work: after a relevant instruction or correction arrives, when a draft or decision is ready and before it is presented, before a switch of task or route, and before and after an external operation. It records what was decided, where it was written, and the next safe operation; a candidate awaiting the author's answer is written down here with the question. Written is not saved: read the files back before a cumulative reply claims them. A checkpoint is neither a production result nor an adoption nor permission to publish.

## Every image with what produced it

`python scripts/production_workflow.py execute` records each returned image as a Production candidate. A task with a `recording` destination also projects that candidate into the selected character iteration; a characterless output remains with its work task and run. [Production execution](production-execution.md) locates the execution and review contracts. Record an image obtained another way (a host with no transport, a model exposed on no service) by hand before using it as a character iteration:

```bash
python scripts/studio.py iterate --studio <dir> --character C02 --slot base.front \
  --result <file> --package <generation-package.json> --request <request.json> --response <response.json> \
  --note "heavier build than it-0003"
```

The iteration keeps a copy of the result, the Generation Package it was built from, the request exactly as it was sent (model identifier, every parameter, the seed, the media by id), and what the service answered: the image's response, and the whole answer, kept once for every image it returned. Each copy is hashed. The service and the seed are read from those files, so an iteration says how to make its image again.

A slot is what an image is for: `base.front`, `outfit.back`, `expression.calm`. Accepting an iteration for its slot copies the image to `accepted/` and marks the previously accepted one superseded, never deleted. Each acceptance is kept with its time and the iteration it replaced, so accepting an earlier image again is one more entry and the slot's history stays readable:

```bash
python scripts/studio.py accept --studio <dir> --character C02 --iteration it-0006
python scripts/studio.py reject --studio <dir> --character C02 --iteration it-0005 --reason "jaw too narrow" --actor "ACTUAL_DECISION_MAKER"
```

`recipe` reads the accepted iteration's recorded request and verifies its retained files.
The `settings` omit the run's own identifiers and seed, which the layout recorded with the request names; `request` retains the exact original input.
The reported seed comes from the stored response or request, with its evidence.

```bash
python scripts/studio.py recipe --studio <dir> --character C02 --slot base.front
```

Use `--iteration` with an exact iteration ID to inspect an iteration without accepting it.
The result identifies its current status, source files and verified hashes.
See the [candidate recipe example](../../examples/candidate-recipe/README.md) for synthetic output.
The next request needs current validation and authorization; a retained recipe records evidence rather than permission.

`gallery.html` and `gallery.json` are generated projections of recorded Studio iterations **and** the sheet's current, candidate and historical artifacts. Imported artwork, local crops, model upscales, shared panels and local scale diagrams therefore remain visible; a file merely lying in an arbitrary folder is not treated as a recorded result. Matching iteration/slot artifacts are shown once, not duplicated when the sheet registers the same generated image.

The default order is newest **recorded/received or published time** first, normalized to absolute time with a deterministic tie break. Acceptance time and filesystem modification time never reorder creation history. A service's exact response is retained, but its internal generation timestamp is not invented. The page header's build time describes the view, not when every image was generated.

The page provides oldest/newest order, full recorded-detail search, current/candidate/not-selected/history/unavailable filters, UTC-date filtering and 40-entry pages with lazy images. Only the current page's cards enter the browser document. The small HTML shell loads compact card metadata from its companion directory; complete prompts, negative prompts, settings, media values, decisions and acceptance history live on each entry's **Full details and recorded evidence** page. Those pages link to the exact recorded request, response, package and artifact provenance when present. The complete JSON inventory retains every projected field.

Opening the gallery reads the compact index, not every full detail. Text search reads each entry's complete searchable text through local scripts, including entries outside the displayed page, and releases that text after matching. It reports progress and unreadable or changed entry files; incomplete search is never reported as a complete negative result. Changing the query cancels the previous scan. Order, state and date filters apply across the complete matching set. The HTML, detail pages, images and scripts work when opened directly from the filesystem; they require no server or fetch API.

The browser remembers filters in session storage and, while visible with automatic refresh enabled, reloads every 30 seconds except during an active search. That refresh only reloads files already written by a command; it is not a hidden generator, watcher, network service or background job. Global search still has to examine the complete searchable history. A larger history therefore increases search work and the compact index, while the landing HTML and active card count remain bounded.

Views update after iteration recording, formal Production decisions, sheet candidate registration/adoption and local edits. Author questions and revisions also update the activity views. `studio.py status` and `studio.py sync` repair missing or stale generated views from source records:

```bash
python scripts/studio.py status --studio STUDIO
python scripts/studio.py sync --studio STUDIO
python scripts/studio.py gallery --studio STUDIO
```

A display failure does not roll back a committed image or decision. A warning and `work/activity/projections-pending.json` mark repair work; inspect saved results and run `sync`, never resubmit to fix a gallery. A broken historical image, request or run is visibly unavailable on its entry rather than hiding other images. Actual use of a selected source still requires its exact hashes and approval. `validate_studio.py` remains a whole-studio audit, distinct from a scoped production operation.

One owner operation records its durable changes first and publishes the affected views at its outer completion boundary. Nested candidate registration, slot acceptance and sheet adoption therefore share one refresh; Production adoption publishes after its `adoption-result` is committed. Work notes, questions and task revisions update the activity timeline without rebuilding artwork or reference views. A deferred display failure remains attached to the successful operation receipt as a projection warning, and pending activity receipts remain repairable by `sync`. Each event emission creates independent dirty receipts, including a retry of an existing event. A publisher observes its receipts before reading the source records and acknowledges only that observed work after successful publication. Receipts that arrive during publication remain pending.

For a read operation, `StudioRead` holds the parsed manifest, stored iteration rows, sheet state and the verified Production run values that its callers need. Reference checks, readiness and status receive that same read model explicitly. Reading destination syntax and reference indexes does not project unrelated historical runs. A continuity build shares the read model across its selected references and verification stages. A later public operation creates a new read model, so changed or withdrawn selections and damaged evidence are rechecked.

Artwork publication begins by acquiring its publication boundary and reloading the read model. A model populated before that boundary cannot publish an older inventory or acknowledge newer receipts. Gallery and active-reference publication share this fresh model, and `status` uses the values built during its repair pass. The activity timeline has its own publication boundary. Both boundaries order publishers without holding the locks used to change canonical Studio records.

Read-only reference checks do not acquire a Studio writer lock. Immutable activity/artwork publication uses exclusive filesystem publication and exact existing-content verification. Mutable canonical state is serialized by its owner: the manifest, one character's iteration/adoption/accepted-image updates, one sheet's selection compare-and-swap, and the task ledger's current pointer plus saved task. Generated-view publishers coordinate only their own output groups. Sheet evidence verification and view building occur outside the sheet selection lock. These scopes prevent lost updates without serializing unrelated readers or character mutations.

The primary gallery in the Studio root is the auto-updated view. Its `gallery.assets/` directory contains the compact index, shared runtime and styles, and stable per-entry detail and search files. The generated ownership record identifies that directory as part of this view. A status or review change replaces the affected entry's generated files; it does not create successive unreachable page versions. Files whose content is unchanged keep their bytes and modification times, and an unchanged gallery keeps its original build timestamp. Source records are still checked to build the complete inventory. A changed inventory rewrites `gallery.json` and the compact index as needed.

`gallery --out PATH` is an explicit additional snapshot with its own companion directory and links rebased to the Studio; it is not a second subscribed view. Updating the primary view leaves that snapshot's pages and data unchanged. For example, a synthetic Studio containing `subject/it-0001` and `subject/it-0002` displays two compact cards and two linked detail pages; changing the second entry's disposition updates its detail and the current inventory while the first detail is reused. Both entries and their original evidence remain available.

Do not hand-edit generated gallery files, `latest.json`, or the activity timeline. Keep author inputs, immutable evidence, per-attempt exports and generated displays in their declared folders; no automatic cleanup deletes formal images, requests, answers, approvals or history.

### Record a missing generation package

When an imported iteration was recorded before its original Generation Package
was available, attach that package to the same iteration:

```sh
python scripts/studio.py attach-package --studio STUDIO --character C02 --iteration it-0006 \
  --package ORIGINAL_PACKAGE --evidence SOURCE_EVIDENCE --actor "ACTUAL_RECORDER" \
  --reason "How the source evidence relates this package to the retained image"
```

Keep the package's original reference companion beside it, or supply its actual
directory with `--package-companion`. `SOURCE_EVIDENCE` is the real source
material establishing the relationship, such as retained request/result records
or the owner's attributed statement. The recorder judges that relationship;
the runtime validates and preserves the supplied bytes. Constructing new inputs
does not recover an image's original generation provenance.

The operation records the attachment time, recorder, reason, source locations
and hashes and keeps the package, its companions and the source evidence
together. It preserves the image, iteration ID, original recording time,
acceptance history and imported ownership. A `production_binding` in the
original package remains source evidence; it creates no selection or authority
in the source run. When the source run is in this Studio, the attachment checks
its exact input and candidate image. Production-owned rows retain their own
recorded package and recovery owner.

Repeating the same attachment is idempotent. A different existing package or
conflicting evidence is reported for inspection rather than replacing the
retained record. After attachment, use [Adoption Workflow](adoption-workflow.md)
with the same iteration and actual approval. Sheet publication also retains the
attachment record and source evidence with its immutable artwork.

## Failed send recovery

`execute` copies the run's package and reference companion into the send's journal.
The references are verified again there and uploaded from those saved copies, never from live author files.
A package changed during that copy is refused before upload.

Before any execution claim, upload or submission, `execute` checks the recording destination:

- the character registration and the slot;
- the iteration log;
- the sheet-panel condition and the subject mapping;
- write access to the Studio.

The dispatcher preview checks the character, the slot, the iteration log and write access the same way. It creates no journal and sends no media. Only `execute`, and `resume` before a new send, recheck the sheet-panel condition and the subject mapping.

Each send creates a unique `runs/<run-id>/` directory before the first upload.
`run.json` records progress and the iterations already saved.
`request.json` is written before submission; `answer.json` is written before interpreting or fetching results.
The package, reference companion, answer, each image's response and completed downloads remain there after later failures.
Upscales retain the source and each output under `upscale.references/`, with relative paths that also resolve inside the recorded iteration.
Production records the nonsecret credential selection with the execution claim. The authentication value is supplied separately to the transport and is absent from the authored request and model artifacts by construction. The provider's returned answer remains exact evidence; its arbitrary contents are not universally scrubbed. [Studio authentication](studio-authentication.md#logs-and-saved-evidence) defines the distinction between local secret storage, redacted diagnostics and saved responses.

A failed run is not a reason to resend automatically.
A failure while `sending` means the service outcome may be unknown.
[Production execution](production-recovery.md#status-and-resume) shows how `resume` asks the provider and records an outcome.
Inspect the retained answer and the studio's iteration log first; a gallery-write failure can happen after an iteration row is written.
When the answer was saved, `python scripts/production_workflow.py resume --root STUDIO --run RUN_ID` downloads what the run lacks.
It records the missing iterations without sending again.
Do not delete the journal until recovery is complete.
The journal does not promise recovery from loss of the storage device.

`scripts/dispatch_recovery_smoke_test.py` exercises these failures with mocked or loopback service calls and never contacts an image service:

- preflight, preview and refusal;
- empty responses;
- upload, submission and download;
- recording.

## Session entry

`scripts/session_entry_points.py` finds the studio the working directory belongs to and prints the open task first: goal, steps done, the next step, and what it is blocked on. It prints them whether or not a pack runtime exists; text authoring resumes without one. A studio it cannot read is named with the problem in one line, and the report goes on. Read that before doing anything else; if a task is open, continue from `next`; if none is open, inspect suspended tasks before the last finished tasks and resolve the intended continuation. Do not reconstruct the state of the work from chat history when the trail is there.

Resume in this order: bind the studio, read the trail and the open task, read the applicable originals for the next operation, compare any new instruction with what is saved, then take the next safe operation. Do not repeat an answered question, revive a rejected idea, resend a completed generation, or treat a pending candidate or a held draft choice as adopted. Report what is saved by its actual guarantee: a local checkpoint read back, an export verified, a remote write with an unknown outcome, or a stale resume record. None of these is "backed up"; when writing is unavailable, say what is unsaved and hand over a recoverable export instead of accumulating decisions as if they were safe.

## Validation

```bash
python scripts/validate_studio.py <dir>
```

It refuses:

- a manifest that is not what `init` writes;
- a character listed without a directory, or on disk without a listing;
- a character id that ends in a dot or differs from another only by case;
- an iteration whose files are missing or whose hashes moved;
- a slot accepted twice, or an accepted iteration whose copy under `accepted/` is missing or differs;
- an acceptance history that names an iteration of another slot;
- an imported iteration without `external-import` provenance, or a rejection that names no actor;
- a Production row that stores an evaluation, disposition or other judgment field, or whose run cannot be read;
- a Production candidate a dispatcher run recorded for this studio with no iteration row;
- a stale sheet binding or an incomplete adoption step;
- a gallery that differs from what the records produce;
- a work trail the ledger cannot account for.

A Production row names exactly its run and candidate, and its judgment comes from that run.
An unreadable run is reported, never reclassified as an imported image.
A candidate without a row names the command that records it (synthetic, trimmed):

```text
Error: production run 01a10325-016d-77e5-87f2-fdeae61b82c8: candidate 55a6aed965b7a6ea42d7f986ffc9ead442407539a92c9dc8d422fee0d5f0ab7d has no iteration row in characters/robot; python scripts/production_workflow.py resume --root C:\...\studio --run 01a10325-016d-77e5-87f2-fdeae61b82c8 records it
1 error(s)
```

`studio.py status` reports the same stale bindings and incomplete adoption steps.
`scripts/studio_smoke_test.py` exercises every check on a temporary studio.

## What leaves a studio

An accepted image leaves the studio as a file with its hash, through a Generation Package or an interchange envelope. Nothing outside the studio is asked to hold its iterations, and the studio holds no other tool's files.

## Adoption and resumption

Use [Adoption Workflow](adoption-workflow.md) when "accept" also means use as the next reference or register in the catalog.
Accepting an iteration for its slot implies neither scope.
Resume the exact approved operation; never paper over a pending journal by sending a package with an old image.

## Production-owned candidates

A candidate is an output production registered in its run.
`execute` and `resume` register each acquired candidate before recording its iteration.
The iteration keeps that run and candidate identity, and recording it again changes nothing.
An external import is identified as external and never acquires an invented Production run.

A Production row's `status` is on the adoption axis only:

- `candidate`: not the slot's accepted image;
- `accepted`: the slot's accepted image;
- `superseded`: replaced by a later acceptance;
- `unavailable`: a candidate whose run cannot be read; an accepted or superseded row keeps its status and carries `production_diagnostic`.

It is never `rejected`.
The gallery reads the evaluation, disposition, unassessed criteria and diagnostics from the run and shows them beside the status.
It labels a reason "selection reason" or "disposition reason"; "rejection reason" belongs to imported images only.
After the synthetic partial-review scenario of `examples/generation/build_example.py` records its disposition, `gallery.json` holds, trimmed:

```json
{"iteration_id": "it-0001", "slot": "candidate", "status": "candidate",
 "production": {"run": "01a10325-016d-77e5-87f2-fdeae61b82c8", "candidate": "55a6aed965b7a6ea..."},
 "evaluation": "nonconforming", "disposition": "not_selected", "unassessed_criteria": ["output"],
 "production_diagnostic": null, "selection_diagnostics": [],
 "reason": "Rejected on the observed colour failure; the output criterion stays unassessed.",
 "decision_kind": "disposition"}
```

On a Production row, `studio.py reject --actor ACTUAL_DECISION_MAKER --reason REASON` records `not_selected` through the run's disposition.
It follows the same rules as `production_workflow.py disposition` and writes no rejected flag of its own.
This remains available after the run completes, once another iteration has
replaced any current acceptance of that candidate. A never-accepted candidate
needs no replacement. The gallery shows the recorded nonselection and status
stops counting it as a waiting candidate. The original completion, work task,
image and review remain recorded. The same image bytes in an independently
imported iteration do not make a disposition or acceptance decision for either
iteration.
`studio.py accept` requires the candidate to be its run's current selection.
Every hard criterion must have a supported pass or an explicit owner acceptance
of its assessed nonpass; an unassessed hard criterion still needs review:

```text
Error: SELECTION_REQUIRED: The candidate is not the current selection of its run.
```

A partial review may justify stopping, and a preference may justify not selecting a conforming image.
Neither fills unobserved criteria.
A missing or corrupt run marks a candidate row `unavailable` and adds `production_diagnostic` to every row of that run; editing the iteration row cannot bypass it.
`recipe` still reads such a row from the request the Studio keeps and returns the run's diagnostic (synthetic, trimmed):

```json
{"iteration_id": "it-0001", "source_status": "unavailable",
 "production_diagnostic": {"code": "ARTIFACT_MISSING", "phase": "integrity",
   "message": "A published artifact is missing.", "run": "01a10325-016d-77e5-87f2-fdeae61b82c8"}}
```

### Selection, adoption and withdrawal

Use Production `draft-acceptance` and `accept` when the owner chooses an existing
reviewed candidate for its Studio slot. The operation reuses the original run,
candidate and iteration, records the exact slot decision and completes the run.
Its `studio-slot` selection and Studio acceptance receipt identify the same
candidate and destination. Accepted departures remain visible in the review and
evaluation. No image is imported again, and no new work task is needed.

When the requested result includes sheet or catalog reuse, use Production
`adoption-intent` and `adopt` under separate approval and authorization. The same
procedure can use the selected candidate after the source run completes or is
abandoned. It appends its own adoption evidence and preserves the original
production decision and closure. For imported iterations, the Studio
owns plain slot acceptance and [Adoption Workflow](adoption-workflow.md) owns
sheet or catalog binding.
[Production execution](production-adoption.md#select-optionally-adopt-and-finish)
gives the procedures and the rules that withdraw a selection.

## Artifact evidence and completion

Continue the commissioned operation through [Production workflow](production-workflow.md). Authored revisions use [Authored storage](production-authored-storage.md) and have their actual save, delivery and review status. Model execution prepares exact inputs and captures real results; choosing an existing candidate retains that evidence and its acceptance scope. Bind review and selection to the exact candidate. Complete the requested result before closing its owning work task.

`status`, `impact` and `resume` report current dependencies and artifact integrity. A new selection checks current authority; completion verifies the saved decision and its required destination. Canonical adoption is its own recorded decision, independent of saving or receiving an artifact.


## Iteration infrastructure

`studio_gallery.py` builds the complete chronological inventory, publishes the small gallery shell and per-entry detail/search assets, and reuses unchanged generated files. `templates/studio-gallery.js` owns local-script search, filters and the bounded card document; `templates/studio-gallery.css` owns the shared presentation. `studio_activity.py` appends redacted operator transitions and rebuilds the timeline; neither owns image acceptance or external execution. Public commands are `studio.py status`, `sync`, `gallery` and the task commands in `work_ledger.py --help`. Synthetic regression coverage is in `studio_smoke_test.py`, `studio_gallery_smoke_test.py`, `sheet_attempts_smoke_test.py` and `iterative_workflow_smoke_test.py`.

## Story timeline projection

When state inputs or a narrative series in the Studio or its `story/` subdirectory
are present, `studio.py sync` also updates [Story Timeline](story-timeline.md).
The view can read narrative and scene drafts before a state ledger exists.
Authoring sources must identify one series; empty scaffolds do not select a series, and authored
sources in both conventional locations produce an explicit selection failure.
Explicit accepted scene artwork uses the same adoption refresh. This story-order view is separate from the
recorded-time gallery and operator activity history.
