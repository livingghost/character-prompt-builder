# Studio Runtime

Activate this document when character work will outlive one session: a character whose sheet is filled over days, images that are generated again and again until one is accepted, and decisions that get reversed. A studio is where that work lives, with its trail. Authoring that accumulates decisions a later draft reuses is such work, with or without an image: it gets its studio before the first draft that will be revised, and a narrative series can live inside it. Ordinary one-off prompt work and a one-off answer need no studio.

## Contents

- [Why a studio](#why-a-studio)
- [Layout](#layout)
- [The work trail](#the-work-trail)
- [Every image with what produced it](#every-image-with-what-produced-it)
- [Failed dispatch recovery](#failed-dispatch-recovery)
- [Session entry](#session-entry)
- [Validation](#validation)
- [What leaves a studio](#what-leaves-a-studio)

## Why a studio

Two things go wrong when character work has no home of its own. Generated images pile up with nothing that says which settings produced which, so the next day's generation drifts in quality and nobody can say why. And a session that loses its context mid-task, or a new session picking the work up, cannot tell what was done, what was being done, and what comes next. A studio answers both: every generated image is an iteration recorded with the exact request that produced it, and the open task is written down step by step as it is done.

## Layout

```bash
python scripts/studio.py init --out <dir> --studio-id <id> --title "<title>"
```

```text
<studio>/
  studio.json                 id, title, when it was created, the characters
  work/current.json           the open task: goal, steps, which are done, what is next, what it is blocked on
  work/ledger.jsonl           every task opened, every step done, every note, every finish; append only
  characters/<id>/
    sheet/                    the Character Sheet (sheet-data.json and its renders)
    iterations/<it-id>/       one directory per generated image: result, request, response, package
    iterations.jsonl          one record per iteration: slot, status, hashes, service, seed
    accepted/<slot>.<ext>     the image accepted for each slot
  packages/                   Generation Packages built here
  runs/<run-id>/              dispatch journal, exact request and answer, package and downloaded results
  prompts/                    reviewed prompt artifacts that belong to no single iteration
  story/narrative/            a narrative series, when the studio holds authoring
```

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
python scripts/work_ledger.py finish --studio <dir>
```

Mark each step as it is done, not at the end. A step that is not written down is a step the next session does again or skips. `finish` refuses while a step is not done; `abandon --reason` closes a task that will not be finished. `block` records the question the task waits on, so a session that resumes asks it instead of guessing. `show` prints where the task stands; `studio.py status` prints the same beside every character's slots and candidates.

A checkpoint is a `note` or a `step` written at a boundary where loss would cost work: after a relevant instruction or correction arrives, when a draft or decision is ready and before it is presented, before a switch of task or route, and before and after an external operation. It records what was decided, where it was written, and the next safe operation; a candidate awaiting the author's answer is written down here with the question. Written is not saved: read the files back before a cumulative reply claims them. A checkpoint is neither a production result nor an adoption nor permission to publish.

## Every image with what produced it

A generation sent through `scripts/dispatch.py` is recorded by the dispatcher itself, one iteration per returned image, with nothing for the agent or the owner to remember; that is the ordinary path, and [Image Generation Runtime](image-generation.md) describes it. Only an image obtained some other way (a host with no transport, a model exposed on no service) is recorded by hand, before anything else is done with it:

```bash
python scripts/studio.py iterate --studio <dir> --character C02 --slot base.front \
  --result <file> --package <generation-package.json> --request <request.json> --response <response.json> \
  --note "heavier build than it-0003"
```

The iteration keeps a copy of the result, the Generation Package it was built from, the request exactly as it was sent (model identifier, every parameter, the seed, the media by id), and what the service answered. Each copy is hashed. The service and the seed are read from those files, so an iteration says precisely how to make its image again.

A slot is what an image is for: `base.front`, `outfit.back`, `expression.calm`. Accepting an iteration for its slot copies the image to `accepted/` and marks the previously accepted one superseded, never deleted. Each acceptance is kept with its time and the iteration it replaced, so accepting an earlier image again is one more entry and the slot's history stays readable:

```bash
python scripts/studio.py accept --studio <dir> --character C02 --iteration it-0006
python scripts/studio.py reject --studio <dir> --character C02 --iteration it-0005 --reason "jaw too narrow"
```

`recipe` reads the accepted iteration's recorded request and verifies its retained files.
The `settings` omit the run's own identifiers and seed, which the layout recorded with the request names; `request` retains the exact original input.
The reported seed comes from the stored response or request, with its evidence.

```bash
python scripts/studio.py recipe --studio <dir> --character C02 --slot base.front
```

Use `--iteration` with an exact iteration ID to inspect a candidate without accepting it.
The result identifies its current status, source files and verified hashes.
See the [candidate recipe example](../../examples/candidate-recipe/README.md) for synthetic output.
The next request needs current validation and authorization; a retained recipe records evidence rather than permission.

`gallery.html` and `gallery.json` in the studio root list every image of the studio in the order it was generated, each beside the request as it was sent, the model and service, the seed, the status, and each acceptance with what it replaced. The prompt and the negative are read from the fields the dispatcher recorded with the request, and a negative that was not sent shows as none sent; a request recorded without those fields is listed field by field. They exist from `init` and every command that records something (`character add`, `iterate`, `accept`, `reject`) rewrites them, so they are current without anyone asking; `python scripts/studio.py gallery` exists only for a record edited by hand. Both are built from the iteration records and nothing else, so an image that is not in the gallery is an image that was not recorded, and `validate_studio.py` refuses a gallery that does not match the records.

## Failed dispatch recovery

Generation references are copied into the run, reverified beside the saved
package, and uploaded from those saved copies rather than live author files.
A package changed during snapshotting is refused before upload.

Before upload or submission, the dispatcher validates the character registration,
slot, iteration log and local recording destinations. A send also probes write
access. A dry run reads these inputs without creating a run or sending media.

Each send creates a unique `runs/<run-id>/` directory before the first upload.
`run.json` records progress and the iterations already saved. `request.json` is
written before submission; `answer.json` is written before interpreting or
fetching results. The package, reference companion, individual responses and
completed downloads remain there after later failures. Upscales retain the source
and each output under `upscale.references/`, with relative paths that also resolve
inside the recorded iteration. Authentication credentials are not journaled.

A failed run is not a reason to resend automatically. A failure while `sending`
means the service outcome may be unknown. Inspect the retained answer and the
studio's iteration log first; a gallery-write failure can happen after an
iteration row has already been written. When the answer was saved,
`python scripts/production_workflow.py recover-recording --root PROJECT --run RUN_ID`
downloads what the run lacks and records the missing iterations without sending
again. Do not delete the journal until recovery is complete. The journal does not promise recovery from loss of the storage device.

`scripts/dispatch_recovery_smoke_test.py` exercises preflight, dry runs, refusal,
empty responses, upload, submission, download and recording failures using
mocked service calls; it never contacts an image service.

## Session entry

`scripts/session_entry_points.py` finds the studio the working directory belongs to and prints the open task first: goal, steps done, the next step, and what it is blocked on. It prints them whether or not a pack runtime exists; text authoring resumes without one. A studio it cannot read is named with the problem in one line, and the report goes on. Read that before doing anything else; if a task is open, continue from `next`; if none is open, read the last finished tasks and ask what to do. Do not reconstruct the state of the work from chat history when the trail is there.

Resume in this order: bind the project, read the trail and the open task, read the applicable originals for the next operation, compare any new instruction with what is saved, then take the next safe operation. Do not repeat an answered question, revive a rejected idea, resend a completed generation, or treat a pending candidate or a held draft choice as adopted. Report what is saved by its actual guarantee: a local checkpoint read back, an export verified, a remote write with an unknown outcome, or a stale resume record. None of these is "backed up"; when writing is unavailable, say what is unsaved and hand over a recoverable export instead of accumulating decisions as if they were safe.

## Validation

```bash
python scripts/validate_studio.py <dir>
```

Refuses a manifest that is not what `init` writes, a character listed without a directory or on disk without a listing, a character id that ends in a dot or differs from another only by case, an iteration whose files are missing or whose hashes moved, a slot accepted twice, an accepted iteration whose copy under `accepted/` is missing or differs, an acceptance that names no other iteration of its slot, and a work trail the ledger cannot account for. `scripts/studio_smoke_test.py` exercises all of it on a temporary studio.

## What leaves a studio

An accepted image leaves the studio as a file with its hash, through a Generation Package or an interchange envelope. Nothing outside the studio is asked to hold the studio's iterations, and the studio holds no other tool's files.

## Adoption and resumption

Use [Adoption Workflow](adoption-workflow.md) when "accept" also means use as the next reference or register in the catalog. Candidate-only acceptance deliberately does not imply either scope. `studio status` and `validate_studio.py` now report stale sheet bindings and incomplete adoption steps. Resume the exact approved operation; never paper over a pending journal by sending a package with an old image.


## Artifact evidence and completion

For a saved deliverable, continue through [Production Execution](production-execution.md). Preserve this document's own interpretation, retrieval, approval and adoption boundaries. Prepare the exact inputs, capture the real output, bind review and selection to it, then complete and close the work task. `scripts/production_workflow.py status`, `impact` and `resume` recheck dependencies and artifact bytes. A progress checkbox, a search hit or a newly created image is not production completion or canonical adoption.
