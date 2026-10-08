# Studio Runtime

Activate this document when character work will outlive one session: a character whose sheet is filled over days, images generated again and again until one is accepted, and decisions that get reversed. A studio is the directory where that work lives: the sheet, the runs, the gallery and the trail. Authoring that accumulates decisions a later draft reuses is such work, with or without an image: it gets its studio before the first draft that will be revised, and a narrative series can live inside it. Ordinary one-off prompt work and a one-off answer need no studio.

## Contents

- [Why a studio](#why-a-studio)
- [Layout](#layout)
- [The work trail](#the-work-trail)
- [Every image with what produced it](#every-image-with-what-produced-it)
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

`init` records the defaults a request that leaves them open starts from:

- `default_render_profile`, `profile-clear-2d-illustration` unless `--default-render-profile` names another;
- `default_creative_latitude`, `directed` unless `--default-creative-latitude` names another;
- `default_interaction_mode`, `balanced` unless `--default-interaction-mode` names another;
- `default_style_family`, none unless `--default-style-family` names one.

`python scripts/studio.py character add <id> --studio <dir> [--profile ...]` adds a character with a blank sheet in `sheet/`; the Character Sheet workflow then runs in that folder as [Character Sheet Discipline](character-sheet-discipline.md) describes, with `SHEET_DIR` being `characters/<id>/sheet`.

A narrative series is initialized into its own subdirectory, `python scripts/narrative_init.py --out <studio>/story ...`, and [Narrative Authoring](../narrative-authoring.md) owns its files. The studio manifest lists no series; `validate_studio.py` leaves the subdirectory to the narrative checks. Registering a visual character with `character add` comes when an image is wanted, not before.

## The work trail

Open a task before any work that takes more than one step, and write the steps down:

```bash
python scripts/work_ledger.py begin --studio <dir> --goal "C02 base front" \
  --step "generate three candidates from the recipe of C01" \
  --step "present them and record the choice" \
  --step "accept the chosen one for base.front"
python scripts/work_ledger.py step --studio <dir> 1 --note "it-0004 to it-0006"
python scripts/work_ledger.py block --studio <dir> "which of the three, or another round"
python scripts/work_ledger.py show --studio <dir>
```

Mark each step as it is done, not at the end. A step that is not written down is a step the next session does again or skips. `finish` refuses while a step is not done, an author question is unresolved, or the current Production run lacks verified completion. `abandon --reason` closes a task that will not be finished; once the task has a prepared production run, it also requires `--actor`. `block` records the question the task waits on, so a session that resumes asks it instead of guessing. `show` prints where the task stands; `studio.py status` prints the same beside every character's slots and candidates, and the scene materials a persona change reaches.

### Answers, returning to an earlier step, and temporary task switches

`block` returns a unique `question_id`. Read the actual answer, then record its resolution explicitly; an ordinary `note` is not a resolution. A new question records a revised choice rather than rewriting the first answer.

```bash
python scripts/work_ledger.py respond --studio STUDIO --question-id QUESTION_ID --answer "Actual answer" --actor "Actual speaker"
python scripts/work_ledger.py reopen --studio STUDIO --from-step 1 --reason "Actual reason to revisit design" --actor "Actual decision maker"
python scripts/work_ledger.py suspend --studio STUDIO --reason "Await another choice while independent work proceeds"
python scripts/work_ledger.py begin --studio STUDIO --goal "Independent work" --step "Plan"
python scripts/work_ledger.py suspend --studio STUDIO --reason "Return to the earlier character"
python scripts/work_ledger.py resume-task --studio STUDIO --task-id PREVIOUS_TASK_ID
```

`respond` may additionally bind `--evidence STUDIO_RELATIVE_FILE` and repeated `--candidate ID` values. It records an answer, not generation or adoption approval. `reopen` snapshots the previous revision, including completed steps and linked run, before resetting the chosen and later steps. It neither deletes results nor changes any accepted artwork. `suspend` preserves questions, notes and the next step; only one task is active, and `resume-task` does not implicitly suspend a different task. `show` includes suspended task IDs and open question IDs so the next session need not reconstruct these from chat. Terminal tasks cannot be resumed as active work.

The prior run in the same explicit production series is still a protected-criteria dependency. Neither reopening a work step nor switching tasks is a means to discard that authority history.

A checkpoint is a `note` or a `step` written at a boundary where loss would cost work: after a relevant instruction or correction arrives, when a draft or decision is ready and before it is presented, before a switch of task or route, and before and after an external operation. It records what was decided, where it was written, and the next safe operation; a candidate awaiting the author's answer is written down here with the question. Written is not saved: read the files back before a cumulative reply claims them. A checkpoint is neither a production result nor an adoption nor permission to publish.

## Every image with what produced it

`python scripts/production_workflow.py execute` records each returned image as an iteration. [Production execution](production-execution.md) describes that path. Only an image obtained some other way (a host with no transport, a model exposed on no service) is recorded by hand, before anything else is done with it:

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

The page provides oldest/newest order, character/slot/prompt search, current/candidate/not-selected/history/unavailable filters, UTC-date filtering and 40-entry pages with lazy images. The browser remembers filters in session storage and, while visible with automatic refresh enabled, reloads every 30 seconds. That refresh only reloads a file already written by a command; it is not a hidden generator, watcher, network service or background job. The JSON inventory remains complete.

Views update after iteration recording, formal Production decisions, sheet candidate registration/adoption and local edits. Author questions and revisions also update the activity views. `studio.py status` and `studio.py sync` repair missing or stale generated views from source records:

```bash
python scripts/studio.py status --studio STUDIO
python scripts/studio.py sync --studio STUDIO
python scripts/studio.py gallery --studio STUDIO
```

A display failure does not roll back a committed image or decision. A warning and `work/activity/projections-pending.json` mark repair work; inspect saved results and run `sync`, never resubmit to fix a gallery. A broken historical image, request or run is visibly unavailable on its entry rather than hiding other images. Actual use of a selected source still requires its exact hashes and approval. `validate_studio.py` remains a whole-studio audit, distinct from a scoped production operation.

The primary gallery in the Studio root is the auto-updated view. `gallery --out PATH` is an explicit additional snapshot with links rebased to the Studio; it is not a second subscribed view. Do not hand-edit the primary gallery, `latest.json`, or activity timeline. Keep author inputs, immutable evidence, per-attempt exports and generated displays in their declared folders; no automatic cleanup deletes formal images, requests, answers, approvals or history.

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
Authentication credentials are not journaled.

A failed run is not a reason to resend automatically.
A failure while `sending` means the service outcome may be unknown.
[Production execution](production-execution.md#status-and-resume) shows how `resume` asks the provider and records an outcome.
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
`studio.py accept` requires the candidate to be its run's current selection, which needs every hard criterion reviewed and passed:

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

A Production candidate becomes the slot's adopted image through `select`, `adoption-intent`, `adopt` and `complete`; the Studio accepts the iteration at `adopt`.
[Production execution](production-execution.md#select-optionally-adopt-and-finish) gives each step and the rules that withdraw a selection.

## Artifact evidence and completion

For a saved deliverable, continue through [Production Execution](production-execution.md). Preserve this document's own interpretation, retrieval, approval and adoption boundaries. Prepare the exact inputs, capture the real output, bind review and selection to it, then complete and close the work task. `scripts/production_workflow.py status`, `impact` and `resume` recheck dependencies and artifact bytes. A progress checkbox, a search hit or a newly created image is not production completion or canonical adoption.


## Iteration infrastructure

`studio_gallery.py` builds a chronological index and browser controls from existing owners. `studio_activity.py` appends redacted operator transitions and rebuilds the timeline; neither owns image acceptance or external execution. Public commands are `studio.py status`, `sync`, `gallery` and the task commands in `work_ledger.py --help`. Synthetic regression coverage is in `studio_smoke_test.py`, `sheet_attempts_smoke_test.py` and `iterative_workflow_smoke_test.py`, including actual browser checks where Chromium/Playwright is installed.
