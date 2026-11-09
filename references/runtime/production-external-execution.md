# External host execution

Use this contract for `execution: external`, together with [Prepared request execution](production-request-execution.md), [Permissions](production-permissions.md) and [Recovery](production-recovery.md). The route reader delivers each complete body. The selected host owns authentication and the actual call.

For an external image task, the same `draft-execution` and `execute` commands validate the two decisions, record their separate authorizations, hand the input to its declared service and claim one host call. `execute` returns an `external-execution-instruction` with `host_request` with the exact request, target and supplied-media bindings. The host invokes its named tool once with that input, then receives the actual result as described below. The local command itself does not invoke an external host tool. A claimed external run cannot be executed again; recover that call after interruption.

## External and manually executed work

External non-image work uses `handoff-intent`, `draft-authorization`, `authorize` and `handoff` for its actual handoff, followed by its separately authorized `external-intent` and `claim-external` boundary. Locally authored text uses the saved-revision operation described in [Authored storage](production-authored-storage.md).

External image work uses the shared `draft-execution` and `execute` flow above. Set the task's `image_input`; existing-scene edits also activate `semantic-instruction-edit` and declare `semantic_edit`. Preparation exposes the complete exact request. The submit grant must allow the binding's validation mode and have `request_scope: null`; dispatcher scope cases use their own request contract. Existing explicit authority may supply that grant without another confirmation. The claim commits execution ownership and the external-send boundary before returning the request to the host. Reading a claim again does not permit a second call.

Receive the actual host response and returned files in one operation:

```sh
python scripts/production_workflow.py receive-external --root STUDIO --run RUN --response evidence/response.json --artifact result.png --reason "The host returned its final response and image."
```

Repeat `--artifact` for several local files. For an image encoded inside the actual response, use `--image-pointer '["result", "image"]'`; repeat it for several fields. The selected value must be a base64 string or an image data URL. Downloaded remote files use `--artifact`. The command decodes and measures each image, stores its bytes and captures it before recording settlement. It performs no provider call, image review, selection or adoption.

The runtime derives the claim, authorized executor, output count, hashes and content-addressed receipt path from the run and actual files. The generated receipt follows `schemas/production-external-receipt.schema.json`. The executor supplies the observed outcome reason and `--pending` when the host has not finished. An optional `--cost-pointer` selects an actual response object containing `currency` and a decimal-string `amount`; without such evidence, usage stays unknown. Native provider responses remain saved in full. No estimate or absent charge becomes zero.

Optional `--call`, `--request-pointer` and `--model-identity-pointer` select real host-call evidence for comparison with the prepared request. A mismatch retains already captured images and prevents a false matching receipt. Every capture commits before settlement, so an interrupted operation can be repeated with the same actual response and files to finish acquisition and recording. It reuses identical image bytes and never sends again. Recovery uses saved production evidence even when original creative sources or grant evidence have moved. Final accounting does not complete artistic review.

For a further external trial, use `draft-inputs --from-run RUN`, edit the relevant source files, then `prepare --choices FILE`. The source run and its earlier candidates remain intact. A changed target requires its explicit model/interface evidence and applicable route reading; a changed depiction still requires its own input review. For a changed target, `retarget --from RUN --choices FILE --reason REASON --prepare` uses the same compiler and records the previous exact request as lineage. Dispatcher `variant` and `repeat` retain their declared same-target purposes. `production_direction_smoke_test.py` exercises external decisions and reception with synthetic local files and no provider call.

## Prepared JSON and recorded host-call evidence

`request-preview.json` and `execution-plan.prepared_request_sha256` identify
exact prepared arguments. They do not prove that a host invoked its tool.
The external claim pins those arguments and grants one call under the ordinary
handoff and authorization lifecycle. Keep the actual response and saved call
record when the host exposes it.

Supply the actual call record directly when receiving its result. This synthetic example selects the recorded arguments and tool identity without authoring a receipt:

```sh
python scripts/production_workflow.py receive-external --root STUDIO --run RUN --response evidence/response.json --artifact result.png --call evidence/host-call.json --request-pointer '["arguments"]' --model-identity-pointer '["tool"]' --reason "The host returned its final response and image."
```

`request_pointer` selects the actual recorded argument object. For endpoint or
tool identity, `model_identity_pointer` selects its exact recorded value; use
null when identity lives in the request's model field. The saved call must
match the prepared request and declared endpoint/tool. Using the prepared JSON
itself, another file with the same bytes, or the runtime's generated execution instruction fails as call evidence.

Settlement returns `request_evidence.status: matched-recorded-call` when the
actor's recorded call matches. Without `--call`, it returns `not-provided`;
result capture and accounting still work. The receipt and supplied call record
remain immutable evidence. A mismatch fails comparison without deleting already
captured results. A matching actor-attested record does not establish provider
execution, visual reference influence, artistic success or acceptance. Those
claims need their own response and image review evidence.
