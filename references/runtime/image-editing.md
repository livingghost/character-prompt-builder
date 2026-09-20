# Pinned image editing in a production run

Use this path when the selected realization needs a crop, size change, rotation,
or alpha composite of existing still images. These are deterministic pixel
operations, not instruction-based regeneration. Their limits belong to this
executor, not to the genres, subjects or styles the Skill can handle.

## Activation and input

Read Production Execution, Production Direction and Production Permissions.
Select the `image-edit` feature when resolving the current route. The task's
`artifact` is `image`; prepare its complete direction, sources, delivery and
explicit authority, then hand off the exact consumer. A source must be an
applied task source or an already captured candidate, with an exact SHA-256.
A discovered catalog image is not an applied source merely because it exists.

Author `templates/realization/image-edit.json` against
`schemas/authoring/production-image-edit.schema.json`. Fill every placeholder.
The plan has the prepared `input_sha256`, primary `source` (path and hash),
ordered `operations`, a new PNG `output`, exact `targets`, an optional reviewed
`repair`, a reason and limitations. Composite inputs have their own path/hash.

The supported operations are:

- `crop`: integer `[left, top, right, bottom]` within the current canvas.
- `resize`: positive integer width/height, using Lanczos resampling.
- `rotate`: finite degrees, an explicit expanded-canvas choice and a fill color.
- `composite`: a pinned still image, integer x/y placement and opacity in [0, 1].

Each intermediate canvas must have positive dimensions. The operation list has no guessed count ceiling.
Actual memory allocation and installed decoder safety checks still apply; no decoder protection is disabled.
not an implicit first-frame conversion. Color management and artistic intent
are not inferred. The executor converts decoded inputs to RGBA and emits PNG;
inspect the result when profiles, typography, precision or fidelity matter.

## Bind the operation to existing authority

```
python scripts/image_edit.py intent --root PROJECT --run RUN --plan edit.json
python scripts/production_workflow.py draft-authorization --help
python scripts/production_workflow.py authorize --root PROJECT --run RUN --file edit-authorization.json
python scripts/image_edit.py execute --root PROJECT --run RUN --plan edit.json --authorization RECEIPT_SHA256
```

Use the exact JSON returned by `intent` when drafting authorization. The existing
production grant must permit `edit` and the returned targets. Complete its reason
and stop assessments from actual user authority. The command does not grant its
own permission. The plan, source bytes, reviewed repair and destination are
bound into that intent; changing them requires a new matching authorization.

An edit consumes a grant use, including on an uncertain or failed attempt. It
produces one new candidate, not an external model submission; submission output
and spending limits are not a substitute for an edit grant. Cumulative usage
continues across preparations and reviewed child runs of the same task.

## Repair without losing the review

A reviewed primary source must identify the candidate receipt and a repair ID
from its latest review. Actual operation targets must be within that repair's
`targets`. Do not hide an existing review by relabeling its file as a new source.
The candidate/repair link is checked again immediately before output retention.
A new review invalidates a previously prepared edit intent.

Pixel operations realize the existing production contract. Their targets are
`delivery` or declared `decision:ID` values; they cannot change criterion text,
protected source definitions, purpose or the selected direction. To change
those authoring inputs, use the reviewed `revision-intent` / `revise` path from
Production Execution. The resulting child run requires its own handoff and
fresh candidate observations. No prior pass or selection carries over.

The new PNG is registered in the same run with its plan, inputs and operation
receipt. Inspect it, record a new review, explicitly select it and complete the
run. The source candidate stays unchanged. A failed review must record at least
one concrete repair or a nonempty unresolved issue; uncertainty does not require
inventing a correction that has not been justified.

## Failure and recovery

The claim is durable before rendering. After rendering, current inputs,
authority and the latest review are checked again; exact output bytes are then
retained before publication. Existing outputs, internal record paths and input
paths are never overwritten.

After an interruption, repeat the same `execute` command only to recover an
already retained output and its candidate record. It does not render again or
consume a fresh grant use. If no output was retained, the executor refuses the
retry: inspect the claim and obtain explicit authority for a new attempt. A
changed review, revoked authority, changed input or conflicting output prevents
publication under the stale permission. This is not a pixel undo operation.

`python scripts/image_edit_smoke_test.py` tests real pixels, bounds, permissions,
repair lineage and interruption. `examples/production-execution/image_edit_example.py`
keeps a complete synthetic reviewed edit with outputs. Its test declarations
are not user approval, and shape/color assertions are not artistic evaluation.
