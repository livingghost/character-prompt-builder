# Correct an iteration's current slot

A Studio iteration retains its original recording slot, image, request,
response, Generation Package and Production origin. Its current placement is
a separate curation decision. Reassigning the iteration preserves those bytes
and its review, selection and completed production evidence. It generates no
image and creates no replacement iteration.

Use this operation when an image belongs in another scene or when the initial
recording destination was mistaken. A different destination can also be an
intentional choice for an edited variant. The edit source and the result's
destination need not be the same slot.

## Draft the exact correction

Read `studio.py status` for current placement and acceptance. A moved image
also names its original recording slot. Select the exact existing iteration:

```bash
python scripts/studio.py draft-reassignment --studio STUDIO \
  --character CHARACTER --iteration ITERATION --slot DESTINATION --out reassignment.json
```

The draft binds the iteration's character, recorded slot, image hash and
Production candidate when present. It records the current placement decision,
source slot, destination slot and both slots' current acceptance receipts.
Complete `by`, `at` and `reason` from the actual decision. `at` is an ISO
timestamp with its timezone. The script does not choose an approver or invent
the reason for the correction. Keep the derived subject and expected states
as drafted; draft again if the relevant choices have changed.

```bash
python scripts/studio.py reassign --studio STUDIO --file reassignment.json
```

The result reports `recorded_slot`, `source_slot`, `destination_slot`,
`current_slot`, the committed placement digest and the unchanged image hash.
`current` says whether this exact correction still determines placement.
`acceptance_transferred` says whether this decision moved a current Studio
acceptance; `acceptance_current` says whether that transferred acceptance is
still current. A historical retry can therefore succeed while reporting that
a later choice is now current.

## Candidate and accepted-image behavior

A candidate moves as a candidate. Its review and disposition remain with
their existing owner. A multi-image request has one iteration per output;
select the iteration to move. Other outputs stay where they are, even when
their image bytes happen to be identical.

For an accepted image, reassignment also records the author's acceptance at
the destination. The decision's expected destination receipt identifies the
image it supersedes. The original slot becomes empty when this image held
its acceptance; an earlier superseded image is not restored automatically.
The new accepted copy has the same image hash. Every earlier acceptance and
supersession remains recorded at the slot where it occurred.

Existing sheet candidate membership follows the corrected placement. Current
canonical artwork and historical sheet approvals have their own authority,
described below. Gallery, recipe, status, acceptance and new adoption use
current placement. The immutable Production recording declaration continues
to describe the original capture. Recovery locates the same candidate by its
Production origin and output index rather than generating or importing it
again because its slot changed.

## Canonical adoption stays explicit

A reassignment does not move canonical approval. If the iteration still has
a current sheet adoption, withdraw that exact adoption before moving it. An
accepted move also requires withdrawal of current canonical artwork at its
destination before replacing the destination's Studio acceptance. The
`PLACEMENT_SOURCE_ADOPTED` diagnostic names the exact slot and commands:

```bash
python scripts/sheet_workflow.py draft-withdrawal --sheet SHEET_JSON \
  --slot SLOT --out withdrawal.json
python scripts/sheet_workflow.py withdraw --sheet SHEET_JSON \
  --decision-file withdrawal.json --evidence-root EVIDENCE_ROOT
```

Complete the withdrawal's actual author decision and evidence before applying
it, following [Sheet fills](sheet-fill-workflow.md). Withdrawal retains the
artwork and previous approval as history. Draft reassignment again afterward.
The retained iteration can then receive a fresh destination approval through
[Adoption Workflow](adoption-workflow.md). Its prior Generation Package,
review and completed work remain available. A previous catalog publication
keeps its own locked evidence; relocation does not rewrite that publication.

An old live reference no longer identifies the current accepted destination
after the relevant decision changes. A package that already archived the
source keeps verifying its exact earlier evidence. Recover an already sent
operation from that retained package and result.

## Conflict, integrity and recovery

The event store commits one append-only decision under the character's
existing journal owner. Its replay checks the immutable iteration origin and
previous placement. The accepted copy, journal transfer and sheet candidate
membership are recoverable consequences. The operation uses the existing
sheet owner while checking and changing its membership; display publication
follows the formal effect.

`PLACEMENT_CONFLICT` means the candidate moved or a relevant source or
destination acceptance changed after drafting. Inspect the current state and
draft again if the new correction is still intended. A stale draft never
overwrites the intervening decision.

`PLACEMENT_PROJECTION_PENDING` means the decision committed but a derived
file write was interrupted. Repeat `studio.py reassign --file` with that same
decision file. It recovers the accepted copy and membership without another
generation or a duplicate acceptance. If a later placement or acceptance now
owns the result, the retry reports that state without restoring the older
one. `studio.py sync` repairs deferred gallery, reference and activity views;
it does not manufacture a missing author decision.

`PLACEMENT_RECORD_CORRUPT` means recorded placement evidence disagrees with
its immutable origin or ordered predecessor. Restore the exact committed
record or original evidence from a verified Studio copy. Editing the original
iteration slot, prepared task, image hash or Production origin is not a
placement correction.
