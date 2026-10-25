# Model request evidence

The operator chooses the target, the source documents, the settings to try and the trial scope.
The tools keep what was acquired, sent and returned, and refuse evidence recorded for another target.

## Validation modes

| Mode | Required basis | Not established by that basis |
| --- | --- | --- |
| target-schema | The exact target interface's acquired input contract | Visual effect or artistic quality |
| observed-profile | A saved request and acquired output under its exact fixed conditions | Untried values and combinations |
| bounded-probe | An explicit question, fixed conditions, change factor and authorized limits | That the unknown behavior is already verified |

A grant lists the modes it allows in `submission_validation_modes`.
A bounded probe does not bypass malformed input, unavailable controls or missing authority.
Dispatcher compilation checks every declared control whatever the mode.
External image-input preparation checks the exact authored fields against acquired schema rules and records unmeasured rules explicitly.

## The request validation record

Every Generation Package and dispatcher run carries one request validation record:

- `mode` and `target` (service, model identifier, operation);
- `service_execution_sha256`, `offering_contract_sha256` and `transport_sha256`: the hashes of the service record, of the offering with its model record and policy, and of the transport module;
- `contract` and `evidence`: the path and hash of the schema, plan or observed profile, and of its witness;
- `execution_policy`: the path and hash of the operator's policy, or null;
- `unmeasured`: what the evidence does not establish.

The builder and the compiler derive a `target-schema` record when all of these hold:

- the request uses the authored rendition, with no selected references;
- the operation is not an upscale;
- the model's offering names an observed schema in an active pack.

That record names the pack file as both contract and evidence and has no execution policy.
Every other request takes an authored record.
`production_workflow.py build-inputs` builds it from a validation choice, and the package builder takes `--request-validation-file`.
The tools derive `unmeasured` from the evidence and refuse a record whose list was edited.

Input choices select `contract` and `evidence` with strings; the built record
adds their byte hashes. An active observed schema uses the same
`@pack/<source_pack>/<offering.schema_snapshot>` selector in both fields.
The [typed input-choice example](../../examples/input-assembly/README.md#validation-choices)
shows how to derive that selector from catalog inspection. A Studio copy of an
observed envelope retains its content but does not become active pack evidence.

The [image-input plan](../../schemas/authoring/image-input-plan.schema.json) owns the model, ordered reference uses and exact external request for both reference generation and semantic editing. An edit additionally binds its intended changes and preserved properties through [Semantic instruction editing](semantic-instruction-edit.md). A saved request and a matching schema establish preparation; only independent recorded submission evidence can establish that those bytes reached the host call.

External image runs retain `external_request.schema_validation` in their pinned shared image-input binding.
It records `target-schema` when an acquired schema is selected, or `bounded-probe` with `schema-unavailable` otherwise.
Their exact submit authorization must use an allowed validation mode and `request_scope: null`.
Dispatcher scope cases require a sealed dispatcher request and cannot authorize this external path.
Record any required exact-operation grant from the principal's existing authority; this rule creates no extra confirmation step.

A synthetic authored record, trimmed, from `examples/state-aware-pilot/generated/request-validation.json`:

```json
{"mode": "target-schema",
 "target": {"service": "synthetic-host", "model_identifier": "gpt-image-2.5-flare", "operation": "generation"},
 "contract": {"path": "synthetic-validation/6869870cd69c35fe/contract.json", "sha256": "8fc608f3..."},
 "evidence": {"path": "synthetic-validation/6869870cd69c35fe/acquisition.json", "sha256": "036408fe..."},
 "execution_policy": {"path": "synthetic-validation/6869870cd69c35fe/policy.json", "sha256": "a42d3281..."},
 "unmeasured": []}
```

## Execution policy for reference delivery

Selected reference bindings need an explicit `reference_instruction_transport`
in the authored execution policy. Set `choices.validation.execution_policy` to
that policy's string selector, such as `"inputs/execution-policy.json"`.
The following templates show the required fields for `authored-rendition`.
Replace the uppercase values and hash placeholders before use.

`inputs/execution-policy.json`:

```json
{"artifact_type": "execution-policy",
 "target": {"service": "SERVICE", "model_identifier": "MODEL_IDENTIFIER", "operation": "WIRE_OPERATION"},
 "text_dialect": "PROMPT_DIALECT",
 "reference_instruction_transport": {
   "mode": "authored-rendition",
   "contract": {"path": "inputs/reference-render-contract.json", "sha256": "<SHA256_OF_SAVED_CONTRACT_BYTES>"}},
 "basis": {"path": "inputs/transport-basis.txt", "sha256": "<SHA256_OF_SAVED_SOURCE_BYTES>", "locator": "SOURCE_SECTION"}}
```

`inputs/reference-render-contract.json`:

```json
{"artifact_type": "reference-render-contract",
 "target": {"service": "SERVICE", "model_identifier": "MODEL_IDENTIFIER", "operation": "WIRE_OPERATION"},
 "dialects": ["PROMPT_DIALECT"],
 "mode": "authored-rendition",
 "fields": [],
 "basis": {"path": "inputs/transport-basis.txt", "sha256": "<SHA256_OF_SAVED_SOURCE_BYTES>", "locator": "SOURCE_SECTION"}}
```

Use the validation record's exact target in both files, including the selected
service's wire operation. `text_dialect` matches the model record's
`prompt_dialect`, and the contract's `dialects` includes that value. Select the
transport using the applicable model and service guidance; retain its source
bytes and identify the relevant section in each `basis`. The two bases may
share a source when it supports both choices. Studio paths inside these files
are relative to the Studio root, not to the JSON file's directory; named
`@pack/...` selectors retain their active pack root. Compute hashes from the
final saved file bytes and update the references whenever those bytes change.

With `mode: "authored-rendition"`, the agent interprets the checked attachment
mapping into the final prompt. Keep `fields: []`. The [reference delivery
contract](reference-delivery.md) supplies actual image positions, panel regions
and source scopes for that judgment. `native-fields` uses only the provider's
evidenced reference controls declared in the contract; `not-supported` leaves
reference instruction delivery unavailable. Without reference bindings,
`reference_instruction_transport` may be null.

The [synthetic policy](../../examples/state-aware-pilot/generated/synthetic-validation/999c2597753319e4/policy.json)
and [reference render contract](../../examples/state-aware-pilot/generated/synthetic-validation/999c2597753319e4/references.json)
provide complete saved examples. Author the target, dialect, policy choice and
source witnesses for the selected execution. Internal context remains authoring
input; request acceptance and the image's use of references require their own
structural and semantic review.

## Import a schema and publish it

`observe_model_schema.py schema` records a target's own schema with its acquisition evidence.
Supply `--root`, the exact service, model, operation and acquisition document.
`--pointer` selects the schema inside the response with a JSON Pointer.
A local envelope overlay keeps its own source, apart from the acquired schema.

`observe_model_schema.py reference` keeps the source model's identity.
Its relationship document says why the operator considered that source.
Its schema stays reference material, never an observation of the execution target.

Select the source with `--pack` and publish to a new `--out-pack` directory with an explicit release and entry ID.
The importer validates the complete new pack and rebuilds its lock; the source pack stays unchanged.
The pack owner activates the new pack through the ordinary runtime commands.

The importer writes the observed schema the offering's `schema_snapshot` names, and the offering's `schema_contract` and `schema_acquisition` witnesses.
It takes `model_id`, `service`, `model_identifier`, `observed_at` and `source` from the selected record and the acquisition.
`schemas/observed-parameter-schema.schema.json` is that file's contract.
One check applies it, with the model record and offering, in pack validation, request building, request validation and the importer.
A file with another top-level key, artifact type, model ID, service, identifier or date fails when its pack is validated.

The [model evidence example](../../examples/model-evidence/README.md) runs the import through the CLI. Its synthetic report:

```json
{"acquired_response_unchanged":true,"activation_required":true,"budget_effect":"none","external_effect":false,"new_pack_valid":true,"schema_content_matches":true,"source_records_unchanged":true,"synthetic":true,"target":{"model_identifier":"vendor:offered@1","operation":"imageInference","service":"runware"}}
```

## Design a trial

`schemas/authoring/model-trial-plan.schema.json` holds the plan.
The plan names one `purpose`; the compiler never infers it from words in the question:

- `request_acceptance`: the service accepts the exact request;
- `field_support`: a field is available;
- `visual_effect`: a parameter changes the image in a stated way;
- `reference_influence`: a reference reaches a stated scope;
- `output_quality`: the output meets a stated quality.

The plan records the question, change factor, fixed conditions, comparison, observation targets, decision method, handling of an indeterminate result, any deviation from the model's recommendations with its reason, quantity, cost conditions and stop conditions.
A trial is one external request with one output; the request's output count and the run's dispatch claims must match the plan's `quantity`.
A visual question needs settings that give a judgeable image.
A trial of a recommendation itself may use values outside it.
No model's steps or cost example becomes a default for other models.

## Keep kinds of evidence apart

An adoption decision names each observation by kind:

- `provider_statement`: what the provider's description says, never shown as measured behavior;
- `request_acceptance`: the service accepted the request;
- `observed_output`: a captured output of this trial, by its sha256;
- `measurement`: a measured property of a captured output, with its `method`, its `scope` (model, service, mode, settings and reference conditions) and its `limitations`;
- `hypothesis`: an explanation not yet tested.

API acceptance never answers a visual question; a visual purpose needs an `observed_output` or a `measurement`.

## Record use-case suitability on its owner

An offering may carry `use_case_guidance`, validated by [the guidance schema](../../schemas/model-use-case-guidance.schema.json).
Its parent offering fixes the model version and service. Each entry adds an operation, a declared use case and a recommendation:

- `discourage`: choose another suitable candidate for this use by default;
- `consider`: retain this candidate within the evidence's stated conditions;
- `unknown`: the source leaves this use unresolved.

Every entry keeps an ID, reason and `basis` containing kind, source, observation date and limitations.
`provider-statement`, `user-report`, `observed-outcome` and `author-preference` remain distinct evidence kinds.
An observed refusal describes its saved request and conditions; it never establishes every version's behavior.
Missing guidance remains unknown without generating a warning for every unmeasured scope.

A synthetic offering entry:

```json
{"id":"reported-portrait-refusals","operation":"generation","use_case":"benign-minor-depiction",
 "recommendation":"discourage","reason":"The author reports frequent refusals in this bounded use.",
 "basis":{"kind":"user-report","source":"Synthetic author report.","observed_at":"2026-10-18",
 "limitations":["A reported experience, not a measured rate or provider prohibition."]}}
```

Personal family preferences belong to their author's pack policy or complete home override, as [Render contract](render-contract.md#apply-the-authors-model-selection-preferences) defines.
The active runtime selects one whole policy resource. Model identifiers and schema observations retain their catalog owners.
Keep personal reports and choices in that pack or the user's Studio. Public examples use synthetic sources.
An author's `no-discouragement` leaves a model eligible for assessment; it does not erase an applicable offering limitation.

## Diagnose a failed generation before changing models

Keep the failed request, provider answer and captured outputs under their existing Production and Studio owners.
Author a [generation failure assessment](../../schemas/authoring/generation-failure-assessment.schema.json) as ordinary task evidence.
The category states what the saved evidence supports:

| Category | Evidence and next decision |
| --- | --- |
| `provider-moderation` | The provider explicitly identifies a moderation block. Review its reason and applicable scope. |
| `provider-refusal` | The provider refuses the request, with the cause still requiring review. |
| `authentication`, `quota`, `rate-limit` | Resolve access or service conditions using the recorded operational evidence. |
| `timeout`, `transport` | Recover the existing request state before deciding whether another request is needed. |
| `request-schema`, `reference-input` | Correct the exact request or media contract. |
| `output-artifact` | Review an observed identity, anatomy, wardrobe, composition or output defect. |
| `unknown` | Retain uncertainty while inspecting the saved response and execution evidence. |

Run the local evidence check:

```bash
python scripts/render_contract.py diagnose --root STUDIO --failure inputs/failure-assessment.json
```

Paths in the assessment resolve from the Studio root. Its evidence file is bound by SHA-256.
When the failed request used a catalog record, add `--model MODEL_ID` and the same active pack runtime. The tool verifies that record's service and exact interface identifier against the saved target before applying catalog-ID preferences. For a target outside the catalog, omit `--model`; exact-interface preferences still apply. A different catalog model cannot supply the failure's identity.
Provider-response evidence names an exact JSON Pointer and value in the saved response.
The tool checks those bytes and that signal. The responsible agent interprets the provider's documented meaning.
A hypothesis remains `unknown`; a generic error message or a missing image alone never proves a moderation cause.
The [synthetic failure fixture](../../examples/model-evidence/failure-assessment.json) and [response](../../examples/model-evidence/failure-response.json) show the complete pair.

For `unknown`, matching entries with explicit `reported_failure` and `user-report` provenance can identify restrictions as one possible explanation.
An aesthetic preference or quality report retains `reported_failure: null` and establishes no restriction-related cause.
Known timeouts, access failures, request defects and visual artifacts retain their own diagnosis even on a discouraged model.
For a permitted request whose model suitability caused a refusal, use `render_contract.py assess` to identify compatible alternatives.
Record the reason and comparison in `direction.decisions`; prepare each chosen alternative through the ordinary execution path.
This diagnostic command performs no retry, model switch or moderation-setting change.

Provider interfaces expose different signals. OpenAI documents `error.code = moderation_blocked` in its [image-generation guide](https://developers.openai.com/api/docs/guides/image-generation).
Google's [Interactions safety guide](https://ai.google.dev/gemini-api/docs/safety-settings) documents structured error codes for blocked requests.
xAI's [image guide](https://docs.x.ai/developers/model-capabilities/images/generation) documents the `respect_moderation` response field.
These are facts about the named interfaces. Acquire a service's own response contract before interpreting another service's fields or codes.

## Adopt an observed profile

`observe_model_schema.py attach-probe` reads a selected dispatcher `--run`: its saved request, authorization, transport outcome and output bytes.
It reads only the files the run's formal events hold as evidence, and makes no network call or execution claim.
Without `--adoption`, it only records the trial.
External host captures retain their request, response, output and review as Studio observations.
They do not satisfy this dispatch-journal importer or acquire an observed profile automatically.

An observed profile needs all of these:

- a completed one-output trial with its recorded request and response;
- an output this trial captured;
- an adoption decision, by `schemas/authoring/model-profile-adoption.schema.json`, for the plan's run, target, question and purpose, with `conclusion: "supported"`, the actor, the decision time and at least one unmeasured scope;
- a new pack for it, which its owner activates.

An indeterminate or refuted trial stays an observation.
The observed profile fixes the sampling, seed, geometry, output count, and media roles and dimensions it was observed with.
New content receives a new request hash and review under the same observed profile.
A changed fixed value needs a new bounded trial or a valid target schema.
The observation time is the recorded send or capture time, so an export of unchanged evidence keeps the same bytes.

## Compare inputs and change the target

For dispatcher inputs, use `production_workflow.py variant --root STUDIO --from RUN --changes-file changes.json --prepare`.
The source is a prepared input; a captured image or an observed profile is not required.
The changes file follows `schemas/authoring/production-changes.schema.json`:

```json
{"changes": {"parameter:steps": 22}, "reason": "Compare one explicitly declared parameter."}
```

The execution plan lists the mutable fields and their types, and the compiler rechecks the affected input contracts.
A changed fixed parameter cannot reuse an observed profile outside its measured tuple.
A new request receives its own assessment and authorization under the current grant.
An observed image that motivates a revision stays authored source evidence with its candidate and review.

For a dispatcher model or service change, use `production_workflow.py retarget --from RUN --task TASK --reason TEXT --prepare`.
The task supplies the new target's execution profile, guide reading, retrieval assessment and validation evidence.
See [Production execution](production-execution.md#change-the-target-explicitly) and the [generation example](../../examples/generation/README.md).

For another external trial, author a separate task with its exact request, then run `check` and `prepare`.
Existing-image edits also retain their source and reference scopes in a semantic plan.
Keep the source run or reviewed candidate as ordinary comparison evidence when it motivates the new trial.
External tasks do not use the dispatcher's `variant`, `repeat` or `retarget` commands.

`scripts/test_model_observation.py` and `scripts/request_validation_smoke_test.py` exercise these contracts on synthetic evidence.
