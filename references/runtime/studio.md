# Studio Runtime

Activate this document when character work will outlive one session: a character whose sheet is filled over days, images that are generated again and again until one is accepted, and decisions that get reversed. A studio is where that work lives, with its trail. Ordinary one-off prompt work needs no studio.

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
```

`python scripts/studio.py character add <id> [--profile ...]` adds a character with a blank sheet in `sheet/`; the Character Sheet workflow then runs in that folder as [Character Sheet Discipline](character-sheet-discipline.md) describes, with `SHEET_DIR` being `characters/<id>/sheet`.

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

## Every image with what produced it

A generation sent through `scripts/dispatch.py` is recorded by the dispatcher itself, one iteration per returned image, with nothing for the agent or the owner to remember; that is the ordinary path, and [Image Generation Runtime](image-generation.md) describes it. Only an image obtained some other way (a host with no transport, a model exposed on no service) is recorded by hand, before anything else is done with it:

```bash
python scripts/studio.py iterate --studio <dir> --character C02 --slot base.front \
  --result <file> --package <generation-package.json> --request <request.json> --response <response.json> \
  --note "heavier build than it-0003"
```

The iteration keeps a copy of the result, the Generation Package it was built from, the request exactly as it was sent (model identifier, every parameter, the seed, the media by id), and what the service answered. Each copy is hashed. The service and the seed are read from those files, so an iteration says precisely how to make its image again.

A slot is what an image is for: `base.front`, `outfit.back`, `expression.calm`. Accepting an iteration for its slot copies the image to `accepted/` and marks the previously accepted one superseded, never deleted, so a change of mind is one more line in the record and the old choice stays readable:

```bash
python scripts/studio.py accept --studio <dir> --character C02 --iteration it-0006
python scripts/studio.py reject --studio <dir> --character C02 --iteration it-0005 --reason "jaw too narrow"
```

`recipe` reads the accepted iteration's request back without the parts that name a run (seed, task id, delivery settings), so a later generation starts from the settings that produced the accepted image rather than from memory:

```bash
python scripts/studio.py recipe --studio <dir> --character C02 --slot base.front
```

A model record's offering and the service record say what the service accepts; the recipe says what was accepted here. The two together are what a later session sends.

`gallery.html` and `gallery.json` in the studio root list every image of the studio in the order it was generated, each beside the prompt, the model and service, every setting as sent, the seed, the status, and what it supersedes. They exist from `init` and every command that records something (`character add`, `iterate`, `accept`, `reject`) rewrites them, so they are current without anyone asking; `python scripts/studio.py gallery` exists only for a record edited by hand. Both are built from the iteration records and nothing else, so an image that is not in the gallery is an image that was not recorded, and `validate_studio.py` refuses a gallery that does not match the records.

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
iteration row has already been written. Record only missing downloaded images
using `studio.py iterate`, preserving the saved request, per-image response,
package and its companion. Use `--package-companion <saved-companion-dir>` on the CLI, or
`package_companion` on the Python `studio.iterate()` API, for the latter. Do not delete the journal until recovery is
complete. The journal does not promise recovery from loss of the storage device.

`scripts/dispatch_recovery_smoke_test.py` exercises preflight, dry runs, refusal,
empty responses, upload, submission, download and recording failures using
mocked service calls; it never contacts an image service.

## Session entry

`scripts/session_entry_points.py` finds the studio the working directory belongs to and prints the open task first: goal, steps done, the next step, and what it is blocked on. Read that before doing anything else; if a task is open, continue from `next`; if none is open, read the last finished tasks and ask what to do. Do not reconstruct the state of the work from chat history when the trail is there.

## Validation

```bash
python scripts/validate_studio.py <dir>
```

Refuses a manifest that is not what `init` writes, a character listed without a directory or on disk without a listing, an iteration whose files are missing or whose hashes moved, a slot accepted twice, an accepted iteration whose copy under `accepted/` is missing or differs, and a work trail the ledger cannot account for. `scripts/studio_smoke_test.py` exercises all of it on a temporary studio.

## What leaves a studio

An accepted image leaves the studio as a file with its hash, through a Generation Package or an interchange envelope. Nothing outside the studio is asked to hold the studio's iterations, and the studio holds no other tool's files.

## Adoption and resumption

Use [Adoption Workflow](adoption-workflow.md) when "accept" also means use as the next reference or register in the catalog. Candidate-only acceptance deliberately does not imply either scope. `studio status` and `validate_studio.py` now report stale sheet bindings and incomplete adoption steps. Resume the exact approved operation; never paper over a pending journal by sending a package with an old image.


## Artifact evidence and completion

For a saved deliverable, continue through [Production Execution](production-execution.md). Preserve this document's own interpretation, retrieval, approval and adoption boundaries. Prepare the exact inputs, capture the real output, bind review and selection to it, then complete and close the work task. `scripts/production_workflow.py status`, `impact` and `resume` recheck dependencies and artifact bytes. A progress checkbox, a search hit or a newly created image is not production completion or canonical adoption.
