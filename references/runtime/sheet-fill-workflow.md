# Sheet fills, evidence and adoption

Read [Character Sheet Discipline](character-sheet-discipline.md) for authored identity and layout, [Production Execution](production-execution.md) for exact request approval, and [Adoption Workflow](adoption-workflow.md) for Production candidates. These tools never infer acceptance from image presence, a successful request or numerical similarity.

## One artifact and one selection contract

A slot has `current`, `candidates`, `history` and `fill_policy`. `current` is null or an artifact plus its recorded approval. Candidates are immutable artifacts; history holds prior selections and their approval evidence. An artifact names the exact image, dimensions, media type, hash and provenance hash. `.fills/artifacts/<artifact_id>/` keeps those bytes, the complete package and request/response evidence where applicable, and recursively pinned source artifacts. `.fills/approvals/` retains decisions and the evidence bytes they cite.

Generation and model-upscale artifacts carry their respective packages. A crop, local resize, shared image or scale composition carries its operation recipe and exact sources rather than pretending it was generated. Source slot IDs alone are insufficient: every source includes its immutable artifact ID and pixel hash. Model upscales retain source and output carriers together with their Production run binding.

Creating a candidate does not alter the accepted-source dependency digest. Adopting a replacement changes that digest, updates image and provenance together, and retains the old selection. The full original sidecar remains in captured input evidence. Do not edit image paths, hashes or histories by hand. They are runtime-owned, not browser authoring fields. `publication.json` beside each immutable artifact records its first local publication time separately from the hashed creation recipe; the gallery labels this as recorded/published time, not a provider-certified creation time.

## Safe author edits, including a stale browser

Initialize the sidecar with `character_sheet.py init` or `studio.py character add`, then import that current `sheet-data.json` into the reusable HTML editor. Export downloads a uniquely named `character-sheet-edit`, not a replacement sidecar. The edit contains before/after values of `fields`, `tables` and `fill_policies` only. Apply the downloaded file to the selected sheet:

```bash
python scripts/sheet_workflow.py apply-edit --sheet SHEET_JSON --edit DOWNLOADED_EDIT_JSON
```

Under the sheet lock, only touched keys are compared and applied. A field or table changed by another author causes `SHEET_EDIT_CONFLICT` and no partial write; independent keys merge. Tables are compared as whole named tables, not cell-by-cell merges. Reapplying an already applied edit is a no-op. New CLI adoptions, candidates and history are never imported from the browser, even when its screen is old. Reload the committed sidecar before the next edit round. Never rename an exported edit to `sheet-data.json` or overwrite the canonical sidecar with a stale full snapshot. An agent should also construct this authored edit contract instead of replacing runtime state while updating identity text.

## Sequential panel execution

Render `panel-fill-requests.json` first. Author a complete Production task per selected panel, including its prompt, model/mode, parameters, seed, interface evidence and recording target. No creative field is synthesized by the runner. The requested width and height must match the renderer's `target.generation_w` and `target.generation_h`; render with supported `--panel-geometries` when a model has fixed geometry choices.

A [sheet-fill-plan](../../schemas/authoring/sheet-fill-plan.schema.json) is Studio-relative. Each reference explicitly names a slot and role. An artifact ID pins a known acceptance; null elects the current accepted artifact at the preparation boundary. Neither form selects a candidate. The resolved artifact is then frozen in the batch journal, the reference preparation and the exact request shown for approval.

```json
{
  "artifact_type": "sheet-fill-plan",
  "manifest": "characters/hero/sheet/model-fill/panel-fill-requests.json",
  "sheet": "characters/hero/sheet/sheet-data.json",
  "results": "characters/hero/sheet/model-fill/results",
  "panels": [
    {"request_id": "canon.primary", "task": "tasks/anchor.json", "references": []},
    {"request_id": "canon.side", "task": "tasks/side.json", "references": [
      {"slot": "canon.primary", "artifact_id": null, "role": "identity"}
    ]}
  ]
}
```

Use the actual request IDs from the manifest, not this example's assumed layout. Every panel needs a distinct task path. Later stages require their declared accepted anchor; selecting all canonical views is not an implicit default. The active model and offering decide the allowed reference count and transport. One selected anchor is the standard panel workflow, not a global one-image service constraint.

```bash
python scripts/sheet_workflow.py batch-init --root STUDIO --plan sheet-plan.json
python scripts/sheet_workflow.py batch-list --root STUDIO --limit 20
python scripts/sheet_workflow.py batch-run --root STUDIO --state RETURNED_STATE_PATH --grant GRANT_ID
```

This prepares eligible panels, writes unapproved decision drafts and pauses for the author. Review the complete requests and `prompt_check`, then obtain actual approval and supply the completed decisions through a JSON map from request ID to Studio-relative decision file. Merely passing `--grant` grants no new authority.

```bash
python scripts/sheet_workflow.py batch-run --root STUDIO --state RETURNED_STATE_PATH --decisions-file approved-panels.json
python scripts/sheet_workflow.py batch-run --root STUDIO --state RETURNED_STATE_PATH --unreceived-only
```

Uploads, sends and polling use the normal sealed Production execution path, sequentially. A later stage remains blocked until its anchor is explicitly adopted. Each result exports the full-size `<result_file>` and adjacent `.package.json`, `.request.json`, `.response.json`, `.answer.json`, portable package companions and `.artifact.json`. The result marker is written last. Wrong-size/non-PNG output stays captured in Studio and is not mislabeled as a valid panel result.

`--unreceived-only` recovers existing runs and repairs absent exports. Unsent, sent-but-unknown, saved-response and partially downloaded states remain distinct. It never treats a missing PNG as permission to send again. An intentional redo authors a new task/plan and calls `batch-init` without `--state` to allocate a new attempt. The prior candidate, result files and current selection remain intact. An explicitly supplied journal is reusable only for the same plan path and captured plan, manifest and task contents; a different input reports `BATCH_PLAN_CONFLICT` before submission. Recovery uses `batch-run`, not reinitialization.

### Automatic folders and discovery

`results` in the plan is a base directory, not the folder into which every round writes the same PNG. The runner allocates the UTC day, microsecond timestamp, batch ID and per-request slug. No round counter or output filename has to be invented by the operator:

```text
<results-base>/
  latest.json                          newest received result pointer per request
  YYYY-MM-DD/HHMMSSffffffZ-BATCH_ID/
    batch.json                         default attempt journal
    inputs/plan.json                   frozen selected plan
    inputs/manifest.json               frozen renderer manifest
    panels/REQUEST_SLUG-HASH/
      inputs/task.json                 captured author task
      inputs/resolved/                 prepared reference selectors, when used
      decisions/execution/DIGEST.json  exact unanswered execution draft
      results/owner.json               batch/request/journal ownership
      results/PANEL.png                this attempt's output only
      results/PANEL.package.json       package and portable reference companions
      results/PANEL.request.json       exact sent request
      results/PANEL.response.json      image response
      results/PANEL.answer.json        complete service answer
      results/PANEL.artifact.json      last-written completion marker
work/batches/BATCH_ID.json              small discovery index pointing to the journal
```

An explicit `--state` changes the journal path only; result folders remain owned and distinct. Result ownership and preexisting output conflicts are checked before the first send. The journal persists the run ID before preparation; an interrupted prepare is recovered by that exact ID rather than scanning past runs. A different series with damaged historical files does not become a hidden prerequisite. The required predecessor in the same production series remains strictly verified, including protected criteria.

Once sent, recovery needs the frozen run/plan/manifest and saved output evidence, not the old editable task, plan or manifest. It never fabricates missing authority or repairs a damaged immutable source by substitution. Recovery of an older attempt cannot move `latest.json` back over a newer received result. `latest.json` is only a convenience pointer; artifacts, adoption and the gallery's source records remain authoritative.

`batch-list --limit N --offset N` returns newest attempts first with their journal, home, panel run IDs and status. A damaged journal is an unavailable entry, not a reason to omit other attempts. Exit statuses follow Production: 0 complete, 2 input or ownership defect, 3 normal approval/configuration wait, 4 execution recovery or unknown outcome. Completion means received candidates, not adopted artwork.

`compose_sheet_panel_fills.py` displays reduced copies on the scaffold. `--register-sidecar SHEET_JSON --only SLOT` records full-size candidates, each with its own adjacent package or result marker; it is not adoption. For a genuine masked-board result, `harvest_sheet_render.py --register-sidecar SHEET_JSON --generation-package PACKAGE` records crops with their exact full-board source lineage. Neither tool binds a single unrelated package to multiple independently generated panels.

## Review evidence

```bash
python scripts/sheet_workflow.py review --spec review-spec.json
```

Without `--out`, review allocates `.fills/reviews/UTC-DATE/TIME-ID/` under the anchor sheet and returns `output_directory`. Explicit `--out` must name a new directory. Repeated reviews never overwrite earlier measurements or images.

A review spec has `anchor`, `candidates`, `regions`, `cell_size` (default example: 500) and `pairs_per_page` (example: 6). Every artwork selector contains `sheet`, `slot`, `artifact_id`, a unique `label`, and `head` (integer `[x,y,width,height]` or null). Sheet paths are relative to the spec. The anchor must be currently accepted; candidate selectors require exact IDs and may inspect candidates, current or history. A missing head rectangle is displayed as missing evidence, not inferred anatomy.

Each HSV region contains `id`, `hue` (degrees, possibly crossing zero), `saturation` and `value` (both 0..1), `minimum_pixels`, and `rois` mapping artwork labels to explicit rectangles. An omitted ROI measures the whole image. Example region:

```json
{"id":"coat","hue":[10,55],"saturation":[0.25,1],"value":[0.1,1],"minimum_pixels":100,"rois":{}}
```

The output contains full-body and head comparison pages, their hashes, exact artwork descriptors, all thresholds and rectangles, population counts, medians and signed differences. Transparent pixels are excluded. Insufficient selected pixels produce null medians/differences, never a false zero. Color measurements do not assess shape, markings, topology or identity. The author makes and records the adoption decision. One operation shares verification by exact artifact descriptor; it decodes only the anchor and the current page of candidates. Pagination therefore limits retained decoded images, not just the eventual display layout.

## Local derivatives, model upscales and sharing

Consider an accepted-image crop before generating a detail already visible in that image. A deterministic crop or resize still needs review: cropping can exclude required anatomy, and an upscaler may modify identity-bearing detail.

```bash
python scripts/sheet_workflow.py crop --sheet SHEET_JSON --source-slot canon.primary --target-slot parts.detail --rectangle 100 200 300 400
python scripts/sheet_workflow.py share --sheet SHEET_JSON --source-slot size.reference --targets share-targets.json
```

`--local-scale` explicitly applies Lanczos resizing, not a model. For a model upscale, author the normal upscale request from the immutable crop image, then add `upscale.derivation` to its Production task: `{"sheet":"characters/hero/sheet/sheet-data.json","slot":"parts.detail","artifact_id":"<exact-id>"}`. It accepts a recorded crop candidate or a current source, pins the descriptor before submission and retains it through recovery. The task still declares model, scale, recording target and approvals normally.

A share-targets file is a nonempty list of `{"sheet":"relative/sheet-data.json","slot":"size.reference"}`. Shared pixels and source acceptance are copied with their lineage; every destination gets a candidate and requires its own adoption.

For declared scale diagrams, run `python scripts/sheet_workflow.py compose-scale --spec scale-spec.json`. The spec names target `sheet`, `slot`, `pixels_per_unit`, `padding`, `gap`, `background`, and `sources`. Each source has `sheet`, `slot`, `bbox` `[x,y,width,height]`, `height`, `measurement_top`, `baseline` and `label`. Measurement y coordinates are in the full source image; the explicit segment from top to baseline represents the declared height. Accepted source pixels are scaled by that segment and aligned on one baseline. The tool does not infer whether ears, hair, footwear or tails belong to the measurement. It retains geometry and exact source artifacts in the resulting candidate.

## Explicit adoption and redo

Production candidates use `production_workflow.py` review, selection and adoption under their exact Production claim. Local derivatives and explicitly external imports use:

```bash
python scripts/sheet_workflow.py draft-adoption --sheet SHEET_JSON --slot parts.detail --artifact ARTIFACT_ID
python scripts/sheet_workflow.py adopt --sheet SHEET_JSON --decision-file RETURNED_DRAFT_FILE --evidence-root EVIDENCE_DIR
```

The default draft is `.fills/drafts/adoption/DIGEST.json`; `draft_file` names it in the command output. A matching existing draft is returned for inspection, not overwritten. Use the file, not the surrounding CLI response, as the decision. The draft has blank author, timestamp, reason and evidence fields. Fill them from the actual decision, including a relative evidence path, exact SHA-256 and locator. Adoption compare-and-swaps the `expected_current` artifact from the draft. A changed current selection requires a new review, not silent overwrite. Repeating an already committed decision is idempotent. A local decision cannot bypass a Production candidate's separate adoption claim.

Inspect selections with `python scripts/sheet_workflow.py status --sheet SHEET_JSON`. Redo is candidate creation plus the same review/adoption process; no destructive reset or separate compatibility path exists.

## Dismiss a candidate

A candidate that should not be adopted is dismissed with a stated reason:

```bash
python scripts/sheet_workflow.py reject --sheet SHEET_JSON --slot canon.primary --artifact ARTIFACT_ID --by "the author" --reason "wrong fur tone"
```

The rejection removes the candidate from the slot and records a `sheet-candidate-rejected` event with the author and reason in the studio activity log, so a review round's dismissals read together by reason in the timeline. The immutable artifact stays in the sheet's store; importing the same bytes again reproduces the same artifact ID.

## Return to a previous candidate

```bash
python scripts/sheet_workflow.py reoffer --sheet SHEET_JSON --slot canon.primary --artifact HISTORICAL_ARTIFACT_ID
python scripts/sheet_workflow.py status --sheet SHEET_JSON --slot canon.primary --state-filter candidate --limit 20
python scripts/sheet_workflow.py status --sheet SHEET_JSON --disposition not_selected --limit 20
```

`reoffer` adds the exact historical artifact ID to candidates without reimporting, changing provenance or adopting it. A new actual decision can accept it; history retains both earlier selections. Production-origin artifacts continue through Production review/selection/adoption, never a local bypass. Their `not_selected` status is projected from the run's formal disposition; keeping their bytes in candidates is not a request to present them as undecided again.

## Large histories and local diagnostics

`status` supports `--slot`, `--state-filter current|candidate|history`, `--disposition`, `--limit` (1..500), `--offset` and `--metadata-only`. Results are sorted by recorded/publication time descending. Only the requested page has its image files verified; unavailable entries include diagnostics. Small provenance metadata may be read to sort/filter the collection. `--metadata-only` is a display optimization and never qualifies an image for reference use or adoption.

A damaged unused candidate or former selection does not block an independent crop or preparation. The exact current source, chosen candidate, approval and recursive dependencies used by an operation remain strictly checked. A needed damaged source must be repaired before that operation; it is not silently replaced by another image.

Studio gallery and activity views update after candidate registration, adoption and local derivatives. Read [Studio Runtime](studio.md#every-image-with-what-produced-it) for chronological filters and `studio.py sync`, and [Operation diagnostics](operation-logs.md) for automatic logs and their limits.

## Implementation and verification

Public entry: `sheet_workflow.py --help`. `sheet_batch.py` owns attempts and recovery; `sheet_edits.py` owns authored compare-and-apply; `sheet_artifacts.py` owns exact artwork and adoption; `sheet_inventory.py` owns paginated status; `sheet_review.py` owns comparison evidence. Outputs and errors are described above; none of these helpers grants authority. Synthetic checks are `sheet_artifacts_smoke_test.py`, `sheet_batch_smoke_test.py`, `sheet_attempts_smoke_test.py`, `sheet_review_smoke_test.py`, `iterative_workflow_smoke_test.py`, and `character_sheet_browser_smoke_test.py`. The latter browser cases run real Chromium when that optional dependency is available.
