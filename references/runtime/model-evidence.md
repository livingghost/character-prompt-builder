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
The compiler checks every control whatever the mode.

## The request validation record

Every Generation Package and prepared run carries one request validation record:

- `mode` and `target` (service, model identifier, operation);
- `service_execution_sha256`, `offering_contract_sha256` and `transport_sha256`: the hashes of the service record, of the offering with its model record and policy, and of the transport module;
- `contract` and `evidence`: the path and hash of the schema, plan or observed profile, and of its witness;
- `execution_policy`: the path and hash of the operator's policy, or null;
- `unmeasured`: what the evidence does not establish.

The builder and the compiler derive a `target-schema` record when all of these hold:

- the request uses the authored rendition, with no selected references and no bounded production context;
- the operation is not an upscale;
- the model's offering names an observed schema in an active pack.

That record names the pack file as both contract and evidence and has no execution policy.
Every other request takes an authored record.
`production_inputs.py build-inputs` builds it from a validation choice, and the package builder takes `--request-validation-file`.
The tools derive `unmeasured` from the evidence and refuse a record whose list was edited.

A synthetic authored record, trimmed, from `examples/state-aware-pilot/generated/request-validation.json`:

```json
{"mode": "target-schema",
 "target": {"service": "synthetic-host", "model_identifier": "gpt-image-2.5-flare", "operation": "generation"},
 "contract": {"path": "synthetic-validation/6869870cd69c35fe/contract.json", "sha256": "8fc608f3..."},
 "evidence": {"path": "synthetic-validation/6869870cd69c35fe/acquisition.json", "sha256": "036408fe..."},
 "execution_policy": {"path": "synthetic-validation/6869870cd69c35fe/policy.json", "sha256": "a42d3281..."},
 "unmeasured": []}
```

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

## Adopt an observed profile

`observe_model_schema.py attach-probe` reads the selected `--run`: its saved request, authorization, transport outcome and output bytes.
It reads only the files the run's formal events hold as evidence, and makes no network call or execution claim.
Without `--adoption`, it only records the trial.

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

Use `production_workflow.py variant --root STUDIO --from RUN --changes-file changes.json --prepare`.
The source is a prepared input; a captured image or an observed profile is not required.
The changes file follows `schemas/authoring/production-changes.schema.json`:

```json
{"changes": {"parameter:steps": 22}, "reason": "Compare one explicitly declared parameter."}
```

The execution plan lists the mutable fields and their types, and the compiler rechecks the affected input contracts.
A changed fixed parameter cannot reuse an observed profile outside its measured tuple.
A new request receives its own assessment and authorization under the current grant.
An observed image that motivates a revision stays authored source evidence with its candidate and review.

Use `production_workflow.py retarget --from RUN --task TASK --reason TEXT --prepare` for a model or service change.
The task supplies the new target's execution profile, guide reading, retrieval assessment and validation evidence.
See [Production execution](production-execution.md#change-the-target-explicitly) and the [generation example](../../examples/generation/README.md).

`scripts/test_model_observation.py` and `scripts/request_validation_smoke_test.py` exercise these contracts on synthetic evidence.
