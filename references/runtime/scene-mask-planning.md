# Source-bound masks for scene generation

Activate `scene-mask-planning` with `generation` or `repose` when the chosen
dispatcher interface accepts a native mask and the task needs an explicit region.
Instruction-only edits use [Semantic instruction editing](semantic-instruction-edit.md).
The actor owns the change, identifies every visible
part involved, and checks the boundaries. The planner checks those declarations
and sends the resulting mask through the normal production dispatcher.

## Source and region selection

Use the current adopted source when the task requires canon. Keep the Studio's
reference selection and adoption evidence. Declare that same source as an
applied task source and as the single image-to-image reference. Its image bytes
must match the source bound to the mask.

Author `templates/scene-mask-plan.template.json`. Paths are relative to the
Studio root. Each input has its SHA-256. A region has an explicit identifier,
a binary grayscale image, a role and extraction provenance. Roles are `garment`,
`extension` and `protect`; white marks the named region and black marks its
complement. Masks and source must share dimensions and normalized orientation.

Read the image and the requested changes before selecting regions. Account for
separated visible fragments of the same sleeve and for overlapping subjects.
A long sleeve needs a declared extension over a currently exposed forearm.
New headwear needs its own placement area. Hidden regions remain hidden; a
script does not invent them. Use available segmentation tools to propose regions
and add included/excluded points or revise the contours where they are wrong.
When no suitable segmenter is available, record manual contour provenance.
The planner assembles annotations; it does not infer a correct segmentation.

List intended parts in `required`, independently of `selected`. This catches a
known required part omitted from selection. It cannot discover a part missing
from both the annotations and the intent. Review the source for that omission.
Place other subjects, faces and any fixed visible detail in `protect` regions.
The agent completes extraction and correction under the existing delegation;
the user is asked only about genuinely unresolved design decisions.

## Fit a proposed boundary to source pixels

For an existing garment boundary, the same command can refine an annotation
against the source image. Author `templates/scene-mask-refinement.template.json`.
Its `plan` pins the source-bound mask plan by path and SHA-256. Each selected
refinement names a garment region, an inward/outward search width in source
pixels, iterations and seed. Optional `foreground` and `background` fields
pin same-canvas binary point or stroke masks; otherwise use explicit `null`.

```
python scripts/scene_mask_planner.py refine --root STUDIO --plan refine.json --out masks/refined-01
python scripts/scene_mask_planner.py build --root STUDIO --plan masks/refined-01/refined-plan.json --out masks/attempt-01
```

`scene_mask_refinement.py` uses OpenCV GrabCut with certain and probable
foreground/background classes. It changes only the declared boundary band.
Protection stays certain background. The interiors of the complete edit and
each separately visible part remain foreground, so fitting adjacent parts does
not open holes at their seams. A component with no certain foreground asks the
agent for included points or a smaller inward band instead of discarding it.
Extension and protection regions are copied unchanged: pixels cannot determine
where a new sleeve or headwear should extend.

The output retains the original image, pins the refined region PNGs and records
changed pixels, hard-constraint checks, versions, seeds and input hashes. It
contains a normal mask plan and an overlay, not a completed semantic review.
Continue through `build`, inspect actual edges and complete the ordinary review
before `bind`. Updating the source or any inputs invalidates the refinement.
An existing output directory is preserved; new attempts use a new directory.

This operation fits boundaries around an annotation supplied by the agent. It
does not identify characters, discover missing parts or prove garment quality.
A refinement that follows the wrong visible edge must be corrected with points
or rejected. It uses the skill environment's OpenCV and NumPy dependencies.
The request sent to the image model still comes from the normal mask binding.

## Build and review

```
python scripts/scene_mask_planner.py build --root STUDIO --plan mask-plan.json --out masks/attempt-01
```

An invalid assembly writes diagnostics and a preview but no usable mask bundle.
A valid assembly writes `mask.png`, `bundle.json`, `report.json`, `overlay.png`
and an unanswered `review-template.json`. Explicit edit/protection collisions,
missing required pixels and unresolved decisions block the bundle. Feathering
softens inward and never expands nonzero pixels into protection. Extensions
are declared regions, not guessed dilation around an entire subject.

Inspect the overlay at source resolution and enlarge contact boundaries, small
fragments and image edges. Complete a separate review file with the bundle
hash, reviewer, `ready` or `reject`, observations for every selected/protected
region and unresolved issues. The geometry report cannot approve its own
semantic correctness. Changing the source, regions or feathering changes the
bundle and requires a matching review.

```
python scripts/scene_mask_planner.py bind --root STUDIO --bundle masks/attempt-01/bundle.json --review masks/review-01.json --guidance inputs/garment-reference.png --out masks/binding-01.json
```

`--guidance` is optional and names one ordinary image. Keep its role in the
prompt explicit. The binding records the reference bytes; model acceptance of
a reference field is not proof that it improves the output.
This guidance is supplementary dispatcher media, not a row in the Prepared Reference Set.
When a semantic edit requires that image as a scoped reference, use a supported
external field binding rather than claiming this auxiliary channel passed the semantic reference matcher.

## Use the existing production pipeline

Set `generation.mask_binding` to `masks/binding-01.json` and add
`scene-mask-planning` to `features` in the task. Select the target's declared
`image-to-image` mode with seed-image media. Read the route again after changing
features. Preserve the existing prompt retrieval, authority and recording data.
Do not fill a template with personal character or pack identifiers as defaults.

```
python scripts/production_workflow.py check --root STUDIO --task task.json
python scripts/production_workflow.py prepare --root STUDIO --task task.json
python scripts/production_workflow.py draft-execution --root STUDIO --run RUN --grant GRANT --out decisions.json
python scripts/production_workflow.py execute --root STUDIO --run RUN --decisions-file decisions.json
```

Both `check` and `prepare` verify the binding, rebuild its pixel mask and match
its source to the actual source-image transport. Mask and optional guidance
become separate, ordered media entries in the sealed request. The selected
model offering must expose their native fields. A missing field, conflicting
parameter assignment, different source or different dispatch size blocks the
request. The model and sampler are never replaced to pass these checks.

All source, region, review and mask files are dependencies of the prepared run.
They are checked before external effects. Uploads, send, output retention and
interrupted recovery use the existing dispatcher; this feature adds no second
network runner. A resumed send recovers its own task instead of repeating it.
Each result is a candidate. The author retains acceptance and canon adoption.

## Inspect the returned image

```
python scripts/scene_mask_planner.py compare --root STUDIO --binding masks/binding-01.json --candidate iterations/returned.png --out reviews/mask-01
```

This writes changed-pixel counts outside the mask and a difference image.
It does not restore source pixels, composite a corrected result or approve an
outfit. Inspect clothing continuity, residual old garments, contact shadows,
body scale, hand anatomy and faces on the original returned image. Keep input
quality, service validation and artistic quality as separate outcomes.

Reuse unchanged region files for the same source hash. New poses or crops need
new coordinate-bound annotations. Give each attempt a new output directory and
keep parent lineage in the ordinary production variant/review records. A
rejected candidate is not a new adopted source.

## Executable synthetic example and tests

```
python examples/scene-mask/build_example.py --out ../scene-mask-demo
python scripts/scene_mask_planner_smoke_test.py
python scripts/scene_mask_execution_smoke_test.py
python scripts/scene_mask_refinement_smoke_test.py
```

The example uses constructed shapes, a synthetic service and explicitly
synthetic authority. It executes mask assembly, request compilation, media
upload, a local fixture send, candidate storage and pixel comparison. That
checks the execution chain, not a real model's garment quality. The tests also
exercise stale inputs, source mismatch, coverage, protected boundaries,
unsupported model fields, recovery and preserved source files.

Runware's native inpainting mask convention is documented in
https://runware.ai/docs/learn/image-inpainting. An exact model's schema and
observed result, rather than that general guide, decide its available controls.

OpenCV documents the four GrabCut mask classes and mask initialization at
https://docs.opencv.org/4.10.0/d3/d47/group__imgproc__segmentation.html.
