# External request inputs

Author the exact request for the selected host or provider. Keep its complete target evidence, native controls and actual media mappings together. Shared source authority and reference-use meaning follow [Image input](production-image-inputs.md).

## Contents

- [Edit the request and media choices](#edit-the-request-and-media-choices)
- [Exact target and provider schema](#exact-target-and-provider-schema)

## Edit the request and media choices

For external image work, a draft restores `external.image_input`, the native
`external.request` object or array, and the recorded `external.media_slots`.
The request holds independent provider controls. Each reference owns its
intended uses and actual `transport.value` with evidence; add, remove or
reorder those rows in the image-input choice. The builder derives media fields
and attachment positions from the declared mapping, preserving unrelated text
and controls. With one homogeneous media-array mapping, a new reference can
omit its field position. Ambiguous mappings remain an explicit choice.

An existing plan can also be selected as
`external: {"image_input": "inputs/selected-plan.json"}`. The builder
materializes the prompt from the single delivery source and the target, count
and media values from the plan's acquired field mappings. It writes the exact
request and image-input plan, measures evidence hashes, validates the input
and shows its substantive changes. A supplied hash remains a commitment to
the selected evidence. Input assembly invents no uploaded value, grant or
satisfied judgment. The media-slot record and repeated request values are
derived context rather than additional editing locations.
When the source plan binds a canonical prepared set, edit its ordered source
choices in `external.reference_delivery.choices`; its `target_model` retains
the canonical preparation target. The image-input rows then retain only each
reference ID and its actual transport evidence. The builder derives the full
reference scope and source bindings from the canonical choices.

A changed carrier cannot reuse an earlier upload merely by updating a hash.
The input report names each generated carrier and the unresolved transport
field. Upload the selected carrier through the service's actual operation,
then select its saved evidence, returned value and `transport.uploaded_file`
in the same draft. Prepare the same editable choices after selecting that transport evidence. The owner chooses a new immutable output location. The builder compares
the uploaded file's bytes with the current carrier before materializing the
request. It performs no upload or generation itself.
The [synthetic input assembly example](../../examples/input-assembly/README.md) contains complete commands, choice fields, and actual output.

## Exact target and provider schema

`model` records the requested name, catalog status, canonical record when
present, selected target and saved lookup evidence. A missing catalog record
is recorded explicitly and can proceed as an external trial. It is not a
catalog capability or a proven rendering result. `target.operation` comes
from the selected interface's wire contract, not the render execution mode.
`model.prompt_input` states the evidenced input mode and forms. A tag-based
target also names its `prompt_dialect`. A known service/model offering retains
its catalog input contract even when an authored plan labels it missing;
an external declaration cannot reclassify that offering to skip vocabulary
search. Resolve an unknown checkpoint's input contract before finalizing text.

Save one exact request JSON. `external_request` names its relative file and
field paths as arrays of keys and array indices. It declares `prompt_field`,
`model_field`, optional `operation_field`, optional `count_field`, expected
`count` and ordered `reference_fields`. Each reference field includes the
reference ID, exact uploaded value and pinned upload evidence. Every selected
reference is covered. Each declared media field shape is checked across all
array positions. For example, `images[*].uri` covers every such URI, including
inside nested arrays. A mixed content array may retain text-only entries.
References with identical prepared carrier hashes and media types can bind
the same media field when its value also matches. This includes different
sources assigned to regions of one prepared board. Their distinct logical
scopes, attachment number and board regions remain recorded. For direct
inputs without a prepared set, shared fields require identical source bytes.

For tag-based input, also declare `negative_field` (null when absent), the
interface's `prompt_syntax`, and `vocabulary_record` with `path`, `sha256` and
`locator` selecting the ordinary prompt retrieval record. Search that exact
prompt and negative text with `prompt_retrieval.py --search-vocabulary` using
the catalog `--model`, or an acquired `--model-file` for an external target.
`prompt_syntax` declares a default grammar and either `control: null` for a
fixed grammar or a control's exact field path and native-value mapping. For
example, a synthetic interface can map `controls.text_mode: "weighted"` to
`compel`; the request field name itself has no grammar meaning. Use the grammar
selected by the actual request when searching its vocabulary.
When the catalog offering has an execution profile, the applied render intent's
mode determines its grammar. Preparation checks the external request's grammar
against that mode; a native operation name does not select a rendering mode.
Preparation repeats the dictionary search and checks the selected terms against
the actual request fields. Existing wording is preferred when it preserves the
intended meaning; a needed authored expression retains its comparison reason.
No plot is required solely to use the external vocabulary record. A descriptive
target does not acquire a tag-search obligation from this binding.
The saved binding retains the inspection and the model constraints it used.
Reading that binding inspects its exact text again with the pinned grammar and
limits, rejects recorded problems, and requires the saved inspection to match.
It does not read a mutable model catalog to reinterpret a saved request.

Inspect the reference mapping before saving the final request:

```sh
python scripts/reference_delivery.py --image-input-plan STUDIO/inputs/image-input.json --studio STUDIO
```

This reads the authored plan and returns `bindings`. `--studio` resolves a
declared canonical prepared set and its source subject assignment. Original
supplied inputs need only the plan's structure at this step. Interpret the
source scopes, subject assignments and precedence into the final prompt using
the images the target receives. Keep request field paths and internal keys in
the binding record.

`check` and `prepare` verify the saved request's exact prompt, ordered media
mapping and source bytes. The agent completes the existing `rendition_review`
against that entire input, bound to `image_input.binding_sha256`. Apply the
[prepared-request readback](production-request-execution.md#execute-the-prepared-request) to its scoped
depiction, supplied context, actual reference use and production ownership,
including a text-only request's empty image set. A changed prompt, scope,
subject assignment, priority or image position requires that meaning review
again. Dispatcher review uses its compiled request and actual image order or
board regions, bound to the request hash.

For model identity carried in a parameter, `model_field` selects that exact
parameter. If the interface selects a model through an endpoint or tool, use
`model_field: null` with `model_identity` containing `kind` (`endpoint` or
`tool`), exact `value` and saved `evidence` (`path`, `sha256`, `locator`). Do not
add a model parameter the provider does not support. Evidence ties the selected
endpoint/tool to `model.target`; the later host-call record separately shows
which endpoint/tool was used. `operation_field` and `count_field` are null when
those parameters are absent. Record the expected output count explicitly.

An optional `schema: {"path": "inputs/schema.json", "sha256": "...", "pointer": []}`
selects an acquired request schema. An empty pointer selects the whole document;
a nested pointer may select an encoded schema string inside a tool response.
Validation checks supported structural and numeric constraints, including
per-image byte size and dimensions from the actual prepared carrier bytes,
or from the original image bytes for direct inputs. A shared board is measured
as the one image bound to its request field. Unsupported
keywords remain in `schema_validation.unmeasured`. An unavailable schema yields
`bounded-probe` with `schema-unavailable`; an acquired schema yields
`target-schema`. Neither state establishes effective reference use or image
quality. Authority must cover the actual mode and exact-operation request.

Prompt text equals production delivery exactly, including whitespace. A task
with applied `production-spec` or `render-intent` sources runs the common
Production Specification and render validators. The render expression must
appear in delivery, the declared model must agree, and subject assignments
must resolve against the specification's cast. Subject-assigned references
require that specification. State-aware specifications also require their
canonical prepared selection and existing state artifact graphs. External tasks
may name shared files as `generation: {"production_spec": "inputs/spec.json",
"state_graphs": "inputs/graphs.json"}` without dispatcher parameters, plot or
recording fields. `state_graphs` is a JSON array of the existing subject artifact
graphs; each is validated by the existing graph owner. Stateless scenes do not
require it. External preparation does not require a catalog
rendering capability that has not been acquired; such limits remain explicit.
