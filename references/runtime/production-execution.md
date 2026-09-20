# Production execution

Every artifact-bearing task uses the existing work ledger and one production lifecycle. First
read [Production direction](production-direction.md) and [Production permissions](production-permissions.md).
Author the purpose, selected expression, evidence criteria and authority rather than inferring
them from the existence of files. Selection is not adoption, preparation is not consent, and
hash equality is not artistic success. Discussion without an artifact does not require a run.

## Inputs and preparation

Start the work task with `scripts/work_ledger.py --studio PROJECT begin --goal TEXT --step TEXT`.
Put its task UUID into a production task matching `schemas/authoring/production-task.schema.json`.
The draft in `templates/realization/production-task.json` must be completed with real source and
approval documents; it is not an executable example or an authorization.

A task records route, optional features, full sources and exact locators, `delivery`, at least one observable criterion,
optional verified `world_views`/`moment_views`, `direction`, `authority`, `artifact`, and
`execution`. Source dispositions are `applied` or `considered-not-used`, with a reason for either. Resolve material uncertainty before preparation; an unresolved label is not a valid source disposition. `artifact` declares text, JSON, image, video, audio or binary, and
`execution` declares authored, external or dispatcher work. An image task must not label its
result binary to avoid image checks. Route features determine required source roles and reads.

```text
python scripts/execution_routes.py inspect development
python scripts/production_workflow.py prepare --root PROJECT --task task.json
python scripts/production_workflow.py status --root PROJECT --run RUN
```

Preparation pins task, full source bytes, verified bounded state views, implementation/read
contract, authority and its evidence, and the bounded consumer. It creates a UUIDv7 run under
`production/` and links it to the open work task. No runtime import depends on another product.
`delivery.transport=authored-rendition` sends the authored text with selected expression directives.
`bounded-context` also sends explicitly bounded criteria and state views. Neither sends private
dossiers or rejected options. This projection does not replace careful prompt authoring.

## Authorize the handoff

```text
python scripts/production_workflow.py handoff-intent --root PROJECT --run RUN --recipient RECIPIENT --method manual
python scripts/production_workflow.py draft-authorization --root PROJECT --run RUN --grant GRANT --intent handoff-intent.json --out request.json
python scripts/production_workflow.py authorize --root PROJECT --run RUN --file request.json
python scripts/production_workflow.py handoff --root PROJECT --run RUN --recipient RECIPIENT --method manual --authorization RECEIPT_SHA
```

Save the intention JSON emitted by the first command as `handoff-intent.json`; complete the
unapproved request from actual authority before `authorize`. Method is conversation or manual
for authored work, manual for external work, and dispatcher for dispatcher work. The exact
recipient and prepared consumer are bound to this direction authorization.

For an external tool, get `external-intent --count N`, authorize its submit request, then use
`claim-external --count N --authorization SHA` before the host executes the exact bounded input.
For dispatcher generation, build a package with `--production-root PROJECT --production-run RUN`.
A dispatcher dry run prints the JSON under "production submission intent (not permission)"; save and authorize that exact payload with
an actual quoted upper bound, then send with `--production-authorization SHA`. Existing pack,
reference, plot, target capability and service checks remain in force. A package without the
production binding is a low-level artifact, not completion of a routed task.

## Capture the actual result

```text
python scripts/production_workflow.py capture --root PROJECT --run RUN --artifact result.png --note "Origin and limits"
python scripts/production_workflow.py draft-review --root PROJECT --run RUN --candidate CANDIDATE_SHA --out review.json
python scripts/production_workflow.py review --root PROJECT --run RUN --file review.json
```

Capture preserves exact bytes and inspects the declared medium. Images must decode; JSON and
text must parse; video/audio require measured streams from ffprobe. Dispatcher captures must
match its already recorded downloaded results. External captures cannot exceed the claimed
count. Duplicate identical capture receipts do not create another result. A media header or
probe is a processing check, not evidence of an observed expression or a listened-to sound.

A review names reviewer, actual observations, every criterion's check, optional supplemental
`evidence`, repairs, unresolved matters and conclusion. Each observation names `evidence`
(`candidate` or a supplemental evidence ID), a locator, observed fact, interpretation and
limitations. Supplemental entries record path, kind, relation and limitations; their actual
bytes are measured and pinned, not trusted from their filenames.

Locators are `whole`; `description` with text; one-based inclusive `lines` or `bytes` with start/end;
`image-region` with normalized x/y/width/height; or `time` with an integer stream index and
explicit decimal-string `start_seconds`/`end_seconds`. Refer to the schema for exact fields.
Time intervals must lie within that measured stream, not merely the container. A motion check
needs a nonzero actual video interval; audio needs an audio stream. Neither whole-file labels
nor two still images prove intervening motion. Text or binary evidence cannot pass an image check.
A `pass` must cite observations supporting the criterion's declared evidence kind. Automatic
blackness/static detection is not an artistic failure verdict.

Hard criteria must pass before selection. Advisory criteria may remain unassessed with reasons.
Unresolved matters or a new failing review block the previous selection. Review is authored
judgment with located evidence, not automatic aesthetic scoring or audience approval.

## Review, repair and a new execution

The same review carries repairs (`id`, decision IDs, observation indices, operation, changed
targets, reason). Author a revised task or input files. `revision-intent` compares the whole
prepared input, checks the reviewed scope, and returns an exact `edit` payload:

```text
python scripts/production_workflow.py revision-intent --root PROJECT --run RUN --task revised-task.json --candidate CANDIDATE_SHA --repair REPAIR_ID
python scripts/production_workflow.py revise --root PROJECT --run RUN --task revised-task.json --candidate CANDIDATE_SHA --repair REPAIR_ID --authorization EDIT_RECEIPT_SHA
```

Reserve the returned edit intent using the authorization steps above. `revise` creates a new
run linked to the parent candidate, latest review, specific repair and exact changed input.
The new run requires its own direction/submit authorization and real evidence. Its preparation
does not restore used budget or transfer the parent's passing checks. Changed approval evidence
requires new authority rather than a repair that silently grants itself more power.

## Select, optionally adopt, and finish

```text
python scripts/production_workflow.py draft-selection --root PROJECT --run RUN --candidate CANDIDATE_SHA --out selection.json
python scripts/production_workflow.py selection-intent --root PROJECT --run RUN --file selection.json
python scripts/production_workflow.py select --root PROJECT --run RUN --file selection.json
python scripts/production_workflow.py complete --root PROJECT --run RUN
```

Fill the selection reason and authorized actor, obtain its intention, reserve a **select**
authorization, and put the receipt SHA in `selection.authorization` before `select`. It binds
candidate, latest review and all selection fields. `delivery-only` selection does not change
canon. For canonical use, `adoption-intent` and `adopt` require the owning Studio character,
iteration and approval plus their own **adopt** authorization. Catalog scope additionally uses
`--registration-record`, `--pack-dir` and the same explicit pack runtime arguments as the owner.
Only then may a `studio-adoption` selection cite the actual owner record. Completion verifies it.

Work-ledger finish checks the current production completion. Preparations, merely generated
images, draft reviews or a task with no selected actual artifact are not finished production.

## Inspect and recover without execution

`impact` compares current sources, routed implementation and recorded outputs with their pinned
bytes and reports declared dependency effects, including transitive decisions and criterion IDs.
It does not infer meaning from a hash. It is distinct from `status`; both are read-only.
`resume` reports the safe next step and never sends, spends or renders. Missing files, expired
or exhausted authority, changed inputs and uncertain submissions require resolution, not a new
automatic call. `recover-recording` resumes the same dispatcher journal from acquired bytes only.

Executable fixtures in `examples/production-execution/` demonstrate these commands with explicit
synthetic authority. They are processing tests, not user instructions or artwork-quality proof.


## Processing regression checks

Run these checks from the skill root. The fixtures supply explicitly synthetic authority;
they neither grant real spending permission nor establish artistic quality.

```text
python scripts/production_direction_smoke_test.py
python scripts/production_workflow_smoke_test.py
python examples/production-execution/run_example.py --help
python examples/production-execution/repair_example.py --help
```

The direction suite checks meaningful choices, bounded consumer instructions, media evidence,
scoped authorization and reviewed repairs. The workflow suite also checks existing generation,
recording, Studio adoption and completion boundaries. They use no peer skill installation.

## Deterministic pixel realization

Read [Image Editing](image-editing.md) for the `image-edit` feature. Its exact
intent binds the plan, pinned input pixels, latest reviewed repair and new PNG
path to an existing edit authorization. This creates a candidate in the current
run, not a new selected direction or an inherited review. Contract changes still
use `revision-intent` and `revise`. Every failed review needs a concrete repair
or a nonempty unresolved issue; unresolved work may be recorded without inventing
a solution. Retained image outputs can be republished without rerendering.

## Inspectable production evidence

After capture or review, a requested inspection export uses the same prepared sources, consumer, receipts and actual bytes through [Evidence Review](evidence-review.md). Exporting a report or study is read-only with respect to production and canon. Continue decisions through the authority-bearing workflow; exported observations never authorize a new action.

## Scene preparation and reusable authoring input

Use [Scene Persona Material](scene-persona.md) to preserve a full-reading result for
one scoped scene. Add `scene-persona` to the task features and name local selectors
as `scene_materials: [{"plan": "scene-plan.json", "bundle": "scene-material"}]`.
Production preparation checks the complete source files and deterministic documents,
stores their dependencies, and includes the document in `consumer.authoring_materials`.
Do not concatenate this author-only material into a generation prompt. Exact public
instructions, viewpoint limits and submitted inputs retain their own boundaries.
Public material requires an explicit content hash and accepted-by/basis instead of
searching for its producer. It carries snapshot-only source integrity.

For intake of existing source text, use [Source Material](source-material.md).
For observed host trials, use [Agent Evaluation](agent-evaluation.md); process success
is not proof of task completion or expressive quality. For recurring failures, use
[Repair Analysis](repair-analysis.md) over actual reviews, then the existing repair
and authorization process. None of these commands automatically adopts or sends.
