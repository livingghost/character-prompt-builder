# Adoption Workflow

Activate this route when acceptance means "use this as the next reference" or
"register this reference for reuse". Acceptance for a Studio slot leaves the
sheet, catalog and canonical state contracts unchanged. When the request is
only to choose an existing Production candidate for its slot, use
[the compact acceptance operation](production-adoption.md#accept-an-existing-candidate-for-its-studio-slot).
For an externally imported iteration, `studio.py accept` owns that slot decision.
When the requested result includes sheet or catalog reuse of a Production
candidate, use its canonical adoption procedure below. The selected candidate
remains available for this separate operation after its source run completes or
is abandoned, with the actual current adoption approval and authorization.
The operator records actual owner consent; the CLI cannot check whether it is
truthful.

## Input and scope

Use `python scripts/adoption_workflow.py --help` and `adopt --help`. `adoption_workflow.py adopt` serves imported iterations. For a Production candidate it refuses and names `production_workflow.py adopt`, in the order [Studio Runtime](studio.md#selection-adoption-and-withdrawal) gives (synthetic, trimmed, exit 2):

```json
{"ok": false, "diagnostics": [{"code": "INPUT_CONSISTENCY_ERROR", "severity": "error", "phase": "adoption",
  "message": "it-0001 is a Production candidate; adopt it with production_workflow.py adopt under its own adopt authorization",
  "required_action": "Correct the declared input and retry the operation."}]}
```

Every failure of this command prints that form, with the exit status its codes
select in [Production diagnostics](production-diagnostics.md#exit-codes). A
diagnostic whose producer knows the repair, such as `ADOPTION_PACKAGE_REQUIRED`
or `ADOPTION_RECORD_CORRUPT`, names it in `required_action`.

An externally imported iteration uses this workflow for sheet or catalog
adoption. Production `draft-adoption` diagnoses that ownership before recording
an adoption claim. Inspect the iteration's actual provenance and choose its
owner; a Production candidate retains its original run and iteration through
acceptance and adoption.

Inputs are an existing Studio character, an iteration recorded with its source
image and committed Generation Package, and a JSON approval. Use Studio's
[`attach-package` operation](studio.md#record-a-missing-generation-package) to attach a missing original package to the same
imported iteration, with evidence of its relationship to that image. The
iteration's identity, creation time and acceptance history remain unchanged.
File presence alone establishes no generation provenance. Select the actual
iteration, scope and influence; the adoption owner derives the subject:

```bash
python scripts/adoption_workflow.py --studio ./studio --character C01 draft \
  --iteration it-0002 --scope sheet --influence identity --out ./approval.json
```

The draft contains exact `character`, `iteration_id`, `slot` and `image_sha256`
from the recorded image. It leaves `by` and `at` null. Fill those fields only from
the actual approval and its RFC3339 UTC time; the draft grants no permission and
changes no candidate or canonical state. `scope` is `sheet` or `catalog`.
`influence` uses the ordinary reference vocabulary: `identity`, `pose-camera`,
`outfit`, `surface-finish`, `lighting`, `environment`, `prop-accessory`, or
`local-color`. Optional fields are `note`, `license`, `continuity_decision`, and,
for catalog scope, the derived `registration_record_sha256`.

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
- accepts the iteration;
- copies the full-size image and portable package companions into the sheet;
- updates only the selected slot;
- writes `sheet/active-references.json`.

Historical iterations and unaffected slots stay as they were. Reference readiness
follows the accepted iteration's own adoption evidence and approved influence,
including when another iteration retains identical image bytes. `references`
exports that exact supplied-file selection in the reference preparer's own format.

Adoption progress states are `candidate-accepted`, `sheet-bound`, and `catalog-registered`. The durable `adoptions/<iteration>.json` records `next_action` and a failure when a step cannot finish. Repeat the same command with the same approval and destination to resume; it is idempotent and adds no image iteration. A pending pre-acceptance operation is visible too. The operating system releases the recording lock when a process ends, even a killed one, so repeat the approved command and leave `.cpb.lock` in place. A later authored withdrawal stays in the sheet history and does not rewrite that completed adoption record.

`status` uses the same source checks as adoption preflight. Each binding's
`adoption` view names its owner, Production origin when present, `source_ready`
and diagnostics. Source readiness supplies no approval. An imported image
without a package reports `record-generation-package`; a usable Production
candidate reports `adopt-production-candidate`, and an imported candidate with
its retained package reports `adopt-with-sheet-scope`. Selection or evidence
problems name their own inspection or repair step. A slot-only acceptance is a
valid Studio state, so a missing optional reference binding does not itself
make `validate_studio.py` fail.

If the sheet or catalog write finished before Production recorded its result,
status reports `record-adoption-result` and reference export remains blocked.
Repeat `production_workflow.py adopt --run RUN --claim CLAIM` to finish that
retained operation; the binding's `ADOPTION_RESULT_MISSING`
diagnostic gives that exact command. The active-reference view refreshes from
the committed result; `studio.py sync` can rebuild it after a display failure.

The adoption owner carries one parsed Studio read model through source eligibility, the exact Production claim and sheet preparation. It records journal progress and canonical files before requesting a display update. The outer Production operation commits its result before the single shared refresh, so an intermediate sheet bind does not publish a reference that still lacks its Production result. `studio_activity` owns publication of `active-references.json`; the adoption journal and sheet sidecar remain authoritative. A failed refresh reports retained committed work and a repair action instead of undoing the adoption.

`studio status` and `validate_studio.py` report stale sheet bindings and incomplete adoption. Accepting a new image through a plain `studio accept` while an older image is bound leaves status incomplete; resolve adoption before preparing the next run. Preparation and the package builder check each subject recorded under a Studio character. They refuse an incomplete adoption, and a package without the character's current adopted identity image among its prepared references. First-generation work, before any identity is adopted, is permitted.

### Withdraw current canonical reuse

To stop using one current sheet image as a canonical reference, record a sheet
withdrawal. The Studio's accepted iteration and Production selection stay in
place. The image, package, original approval and completed run remain available.
The author decides who withdraws the adoption, when, why and what evidence records
that decision; the draft derives the exact sheet, slot, artifact and acceptance.

```sh
python scripts/sheet_workflow.py draft-withdrawal \
  --sheet STUDIO/characters/C01/sheet/sheet-data.json --slot scene.arrival \
  --evidence-path AUTHOR_EVIDENCE --evidence-locator "withdrawal instruction" \
  --evidence-root EVIDENCE_DIR \
  --out withdrawal.json
```

Select the actual author evidence with a path relative to `--evidence-root` and
a meaningful locator within that file. The tool measures the selected bytes and
records their SHA-256; do not calculate or edit that derived value. Fill `by`,
`at` and `reason` in the draft. `at` is the actual timezone-aware decision time.
Then apply the actual decision:

```sh
python scripts/sheet_workflow.py withdraw \
  --sheet STUDIO/characters/C01/sheet/sheet-data.json \
  --decision-file withdrawal.json --evidence-root EVIDENCE_DIR
```

If the evidence has not yet been selected, omit all three evidence options to
create an incomplete draft. Rerun `draft-withdrawal` with those options and the
same `--out` to fill its unresolved evidence while preserving authored fields.
The command refuses to replace evidence already pinned in that file. A changed
evidence choice requires a new draft file and a new actual decision.

The operation stores immutable withdrawal evidence, retains the exact former
acceptance in history, and clears only that slot's current canonical adoption.
It compares the complete acceptance and original decision, including when a
later adoption uses identical pixels. A changed target requires inspecting the
new current adoption and drafting a new withdrawal if that is still intended.
Repeating an applied withdrawal returns its receipt without clearing a newer
adoption. No historical image automatically becomes current.

A later Studio acceptance can supersede the iteration while its earlier sheet
adoption remains in place. Withdraw that exact completed adoption to end its
canonical scope; the newer Studio acceptance stays unchanged. Withdrawal
verifies the retained approval and completed adoption evidence. An interrupted
adoption still needs its recorded adoption command to finish, including its
Production result when applicable, before withdrawal can proceed.

`adoption_workflow.py status` reports `withdrawn` with the ending decision and a
next action for a new adoption. Its other binding states are
`candidate-accepted` for Studio acceptance without a current matching canonical
binding, `sheet-bound` for completed sheet reuse, `catalog-registered` for
completed sheet and catalog reuse, and `unavailable` when the accepted reference
cannot be verified. A deliberate withdrawal is a complete canonical state; a
missing or damaged binding without that decision remains a repair problem.

To adopt the retained iteration again, draft a new approval through the same
adoption workflow and record the actual new decision. The draft uses its current
Studio placement. If the author also wants a slot correction, withdraw the live
adoption first, use the Studio reassignment operation, and then draft the new
adoption at that destination. A Production candidate keeps its original run,
candidate, image and review and needs its own new adoption authorization. An
earlier completed adoption command only recovers its historical receipt; it does
not restore withdrawn canon. Each approval and replaced adoption journal is
retained under its content hash.

Withdrawal ends this sheet adoption's live reference scope. It does not revoke
an exported file or a separately registered, locked pack, and it does not change
authored identity or story-state contracts. Those uses keep their own authority.
Already prepared `studio-artifact` references become stale for a new send;
recovery of an already returned result uses its recorded proof archive.

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
  "search_terms": [{"phrase": "C01 character identity", "facet": "identity", "weight": 1, "source": "author"}],
  "scaffold": {"family": "direct-geometry-required", "confidence": "fallback"}
}
```

Select the authored record when drafting catalog approval:

```bash
python scripts/adoption_workflow.py --studio ./studio --character C01 draft \
  --iteration it-0002 --scope catalog --influence identity \
  --registration-record ./registration-record.json --out ./catalog-approval.json
```

The owner validates the canonical module and records its exact
`registration_record_sha256` beside the image subject. Complete only actual
approval fields. Adoption rechecks both subjects, so changing the image or
record does not reuse an earlier approval. Choose a new pack directory, outside
commons and every existing pack:

```bash
python scripts/adoption_workflow.py --studio ./studio --character C01 \
  --state-file ./pack-state.json --cache-dir ./catalog-cache adopt \
  --iteration it-0002 --approval ./catalog-approval.json \
  --registration-record ./registration-record.json --pack-dir ./adopted-c01-pack
```

Output is a new UUID-identified pack with the canonical record, a linked raster asset, a `studio-adoption-receipt`, and a release lock. Its technical role is `adopted-reference`, not a falsely labeled archival vector. Both plan construction and active plan validation enforce the receipt-approved influence stored on the locked asset; other visual dimensions are excluded. New image registration defaults to `UNLICENSED`; an explicit license must be part of the approval, not inferred from the project's software license.

The operation adds and enables that pack in the selected runtime; it never rewrites an existing pack. A completed sheet adoption can be promoted to catalog scope with a new record-bound approval. After catalog activation:

1. restart retrieval under the changed runtime;
2. obtain the new record with `catalog_cli.py inspect-many`;
3. plan with `reference_runtime.py plan --use <record-id>=identity` together with other inspected pack evidence;
4. execute that single plan and feed its prepared set into normal generation packaging.

The local `studio-adoption-receipt` is distinct from the story-state `adoption-receipt`: identity contracts, story ranges, registry versions, and state-aware eligibility still follow [State-Aware Series Runtime](state-aware-series.md).

## Failures and regression

Unknown characters/iterations, wrong hashes, altered sources, symlinks, invalid module records, mismatched approval, unsupported influence, competing pack IDs, incomplete registration and stale identity sources block the operation. An existing registration destination is accepted only when its locked pack and approval belong to this exact adoption: its adoption receipt names this approval, this Studio and the pack's own ID. Otherwise it is never overwritten. A failed registration retains the completed sheet binding and reports the remaining step, not complete adoption.

Run `python scripts/feature_workflow_smoke_test.py`. It covers:

- replacement and history;
- stale-source rejection;
- scope;
- path and hash changes;
- failure before and after acceptance;
- registration and retry;
- complete reference-plan preparation and verification;
- a synthetic `execute` that records its returned image.

[Workflow Walkthrough](workflow-walkthrough.md) prepares a run through the same public entrypoints.


## Artifact evidence and completion

Production candidates retain their original run, capture and review through
acceptance and adoption. For an open production task, complete the selected
scope through [Production Execution](production-execution.md), then close that
run's owning work task. Later adoption appends its own evidence while preserving
the original task's closure and completed scope. An imported iteration retains
its imported provenance and follows
this workflow's durable adoption journal. Preserve the interpretation, approval
and scope boundaries above. A progress checkbox, a search hit or the presence of
an image establishes neither completed adoption nor approval to reuse it.
