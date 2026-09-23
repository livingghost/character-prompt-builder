# Adoption Workflow

Activate this route when acceptance means "use this as the next reference" or "register this reference for reuse". Plain `studio.py accept` is candidate-only acceptance and leaves the sheet, catalog and canonical state contracts unchanged. The operator records actual owner consent; the CLI cannot check whether it is truthful.

## Input and scope

Use `python scripts/adoption_workflow.py --help` and `adopt --help`. Inputs are an existing Studio character, an iteration recorded with its source image and committed Generation Package, and a JSON approval. Record a missing package before adoption; file presence is not provenance. The approval contains exactly these required fields:

```json
{
  "scope": "sheet",
  "influence": "identity",
  "character": "C01",
  "iteration_id": "it-0002",
  "slot": "base.front",
  "image_sha256": "REPLACE_WITH_THE_RECORDED_IMAGE_SHA256",
  "by": "RECORD_THE_ACTUAL_APPROVER",
  "at": "RECORD_THE_ACTUAL_RFC3339_UTC_TIME"
}
```

These placeholders are deliberately unusable as authorization: read the iteration's recorded hash and record only real approval. `scope` is `sheet` or `catalog`. `influence` uses the ordinary reference vocabulary: `identity`, `pose-camera`, `outfit`, `surface-finish`, `lighting`, `environment`, `prop-accessory`, or `local-color`. Optional fields are `note`, `license`, and, for catalog scope, `registration_record_sha256`.

Identity-image adoption binds visual evidence only; the authored Identity/Era/Form/Appearance Contracts, story-state transitions and execution permission stay with their own owners. An outfit-only image must use a non-identity slot, leaving `base.*` and `canon.*` as they are. Normal scene clothing stays in the scene. See [Revision Contract](revision-contract.md).

## Adopt, inspect, resume

```bash
python scripts/adoption_workflow.py --studio ./studio --character C01 adopt \
  --iteration it-0002 --approval ./approval.json
python scripts/adoption_workflow.py --studio ./studio --character C01 status
python scripts/adoption_workflow.py --studio ./studio --character C01 references \
  --out ./supplied-selection.json
```

The workflow:

- holds the Studio recording lock;
- validates image/package hashes and safe paths;
- accepts the candidate;
- copies the full-size image and portable package companions into the sheet;
- updates only the selected slot;
- writes `sheet/active-references.json`.

Historical iterations and unaffected slots stay as they were. `references` exports the exact supplied-file selection consumed by the existing reference preparer, in that preparer's own format.

Completion states are `candidate-accepted`, `sheet-bound`, and `catalog-registered`. The durable `adoptions/<iteration>.json` records `next_action` and a failure when a step cannot finish. Repeat the same command with the same approval and destination to resume; it is idempotent and adds no image iteration. A pending pre-acceptance operation is visible too. The operating system releases the recording lock when a process ends, even a killed one, so repeat the approved command and leave `.production.lock` in place.

`studio status` and `validate_studio.py` report stale sheet bindings and incomplete adoption. Accepting a new image through candidate-only `studio accept` while an older image is bound leaves status incomplete; resolve adoption before sending. Before upload or send, the dispatcher checks that a package includes a current adopted identity source under identity authority and rejects superseded sources under their adopted influence. First-generation work, before any identity is adopted, is permitted. A package handed to an external host must pass this Studio check before leaving, because portable package verification alone sees only a Studio it was given.

## Register an image for mixed pack references

The supplied-file path stays separate from pack-backed evidence; keep that provenance boundary intact and every locked pack unedited. To combine this identity with pack pose/outfit/environment evidence in one ordinary Reference Use Plan, first obtain explicit `catalog` approval.

Write one canonical module record conforming to the module branch of `schemas/pack-record-file.schema.json`. Give it a globally distinct ID, supported meaning and search terms, and keep scene details out of identity. Example structure:

```json
{
  "id": "my-c01-identity-20260915",
  "label": "C01 approved identity",
  "curation_status": "curated",
  "category": "species",
  "prompt": "REPLACE_WITH_THE_ACTUALLY_APPROVED_IDENTITY_DESCRIPTION",
  "domains": ["shared"],
  "tags": ["character identity"],
  "search_terms": [{"phrase": "C01 character identity", "facet": "identity", "weight": 1, "source": "author"}]
}
```

Compute its canonical digest with the same function used by the approval validator:

```bash
python -c "import json,sys; sys.path.insert(0,'scripts'); from revision_contract import digest; print(digest(json.load(open('registration-record.json',encoding='utf-8'))))"
```

The new catalog approval must match the same character, iteration, slot and image, and include this value in `registration_record_sha256`. Choose a new pack directory, outside commons and every existing pack:

```bash
python scripts/adoption_workflow.py --studio ./studio --character C01 \
  --state-file ./pack-state.json --cache-dir ./catalog-cache adopt \
  --iteration it-0002 --approval ./catalog-approval.json \
  --registration-record ./registration-record.json --pack-dir ./adopted-c01-pack
```

Output is a new UUID-identified pack with the canonical record, a linked raster asset, a `studio-adoption-receipt`, and a release lock. Its technical role is `adopted-reference`, not a falsely labeled archival vector. Both plan construction and active plan validation enforce the receipt-approved influence stored on the locked asset; other visual dimensions are excluded. New image registration defaults to `UNLICENSED`; an explicit license must be part of the approval, not inferred from the project's software license.

The operation adds and enables that pack in the selected runtime; it never rewrites an existing pack or silently selects conflicting resource providers. A completed sheet adoption can be promoted to catalog scope with a new record-bound approval. After catalog activation:

1. restart retrieval under the changed runtime;
2. obtain the new record with `catalog_cli.py inspect-many`;
3. plan with `reference_runtime.py plan --use <record-id>=identity` together with other inspected pack evidence;
4. execute that single plan and feed its prepared set into normal generation packaging.

The local `studio-adoption-receipt` is distinct from the story-state `adoption-receipt`: identity contracts, story ranges, registry versions, and state-aware eligibility still follow [State-Aware Series Runtime](state-aware-series.md).

## Failures and regression

Unknown characters/iterations, wrong hashes, altered sources, symlinks, invalid module records, mismatched approval, unsupported influence, competing pack IDs, incomplete registration and stale identity sources block the operation. An existing registration destination is accepted only when its locked pack and approval belong to this exact adoption; otherwise it is never overwritten. A failed registration retains the completed sheet binding and reports the remaining step, not complete adoption.

Run `python scripts/feature_workflow_smoke_test.py`. It covers replacement, history, stale-source rejection, scope, path/hash changes, failure before and after acceptance, registration, retry, complete reference-plan preparation and verification, and mock dispatch against a mocked service. [Workflow Walkthrough](workflow-walkthrough.md) exercises the same public builder entrypoints.


## Artifact evidence and completion

For a saved deliverable, continue through [Production Execution](production-execution.md), preserving this document's interpretation, retrieval, approval and adoption boundaries. Prepare the exact inputs, capture the real output, bind review and selection to it, then complete and close the work task. `scripts/production_workflow.py status`, `impact` and `resume` recheck dependencies and artifact bytes. A progress checkbox, a search hit or a newly created image is not production completion or canonical adoption.
