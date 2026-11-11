# Rendering choices and execution controls

Carry the requested depiction and any selected rendering constraints into the
actual model input, and resolve the exact interface for the request.
Preserve applicable identity, age, proportions, wardrobe and story; a rendering
choice supplies no authority to revise them.
The agent decides meaning; the tools validate explicit choices and preserve their provenance.

## Choose the visual treatment

Use [Production direction](production-direction.md#form-a-prompt-from-an-idea)
to develop the commissioned content and its visual realization together.
Choose which properties need control for this work and leave other choices to
the image model. A complete prompt may specify the subject and requested
content without naming a medium or prescribing a finish. That is a completed
direction, not an unfinished taxonomy. Actual prompt and assigned-source
requirements remain authoritative when no separate rendering declaration is
selected.

When selecting a treatment, compare what different choices make the viewer
experience in the proposed picture. Form abstraction, mark rhythm, edges, value
structure, color, light and surface behavior can change its force, pace, spatial
relationships and emotional reading. Let that knowledge inform the conception
as it develops. A fixed medium, adopted treatment or bounded edit retains its
actual scope.

When an exact target is selected, read its [model guidance](#read-the-models-guidance)
while considering model-dependent means. Its checkpoint, active adaptations,
input workflow and available reference or control paths constrain realization.
An input grammar does not establish a model's range of styles. A rendering
preset describes an authored intent, not a capability promised by every model.
Consult [model evidence](model-evidence.md#keep-kinds-of-evidence-apart) for what
the available basis actually establishes. With no target, develop a portable
proposal without claiming that its treatment has been demonstrated.

For an authored treatment, choose the behavior that makes the interpretation particular. Naming a
medium leaves decisions about forms, marks, tonal relationships and surfaces
open. Explain a treatment's contribution through what it does in this image;
generic warmth, polish or readability alone cannot distinguish it from other
plausible treatments. Resolve the visual behavior needed for the intended
effect without turning every available technique into a prompt clause.

When choosing additional rendering constraints, read `python scripts/render_contract.py presets` and
use [discovery](sparse-discovery.md#conceive-the-open-picture) before committing
to it. The presets expose construction envelopes, not a closed set of art
directions or evidence that a treatment fits. Inspect relevant full knowledge
for the concrete alternatives in the conception study, reusing complete
material already delivered in the current context. Use a fitting preset or
author a custom intent with `preset: null`. A custom intent records only the
selected constraints among medium, dimensionality, linework, shading, surface
and detail. Omit an axis when this intent adds no constraint on it; do not fill
the field with an invented process, substrate or texture. Every supplied value
must express an actual choice. An empty `axes` object is valid when no extra
constraints from this taxonomy are selected. Absence neither selects a default
nor removes a user requirement or an adopted source property.

Carry selected visual constraints into the actual text or assigned media.
Assess the requested depiction and the contributions that were selected;
completion does not require prescribing every aspect the model can resolve.
Preserve explicit choices and source requirements at their actual scopes.
The six fields document selected treatment; none supplies an execution control.
The `presentation` field records the resulting construction, such as a portrait,
diagram, panel sequence or product view.
A vector-like appearance does not promise a vector file; output encoding
belongs to the interface controls.

Selecting a named preset adopts its complete axis envelope, which must match
the preset exactly. The `intent --preset` command creates that full selection.
Use a custom declaration with `preset: null` when selecting only part of a
preset's knowledge or authoring other constraints. No omitted custom axis is
filled from a preset.

Apply a selected profile or recipe at its assigned scope. A selection for its
rendering treatment carries the relevant medium and visual behavior. Its
sample camera, crop, pose, emotional register, palette, visibility, margins and
coverage exclusions transfer only when the direction also selects those
contributions. A source can supply a coherent complete presentation; preserve
its related choices when that is the assigned use. Keep the actual adopted
contributions in the existing direction and render intent.

An authored rendering declaration records who chose it (`user` or `agent`) and why.
Ask about a material ambiguity; otherwise choose deliberately within the user's open creative space.
The base axes record selected constraints on the shared treatment. Regional overrides assign
different treatment to a named subject, part, layer or area, with its reason
and visible expression. A scope may overlap another or sit within one subject;
it need not form a separate panel. Resolve which treatment governs each
affected property and how the scopes meet. Author a custom intent when a
selected combination is the treatment itself.
Each regional override names a nonempty subset of the same known axes. It can
select a local constraint even when the corresponding base axis is absent.
The agent may choose a mixed treatment within delegated creative space.
An explicit fixed medium or protected source region remains authoritative.
The registry is a discovery aid, not a closed list of media.

## Select the operation and optional rendering declaration

`execution_mode` owns the operation used to resolve the interface's controls
and media transport. It is required for generation independently of style.
This complete declaration adds no rendering constraint:

```json
{"artifact_type":"render-intent","execution_mode":"text-to-image"}
```

Create it directly, or use:

```bash
python scripts/render_contract.py intent --mode text-to-image --out render-intent.json
```

`templates/render-intent.template.json` supplies that operation-only form.
Choose the actual operation when preparing an image request. No model selection
or operation record is required merely to write conversation-only prompt text.
Neither this form nor an unselected axis clears a requirement in the prompt,
an adopted image or an assigned source. The exact prompt and source bindings
retain those requirements.

An optional authored rendering declaration adds `preset`, `axes`,
`presentation`, `selection`, `prompt_expression` and `regional_overrides`
together. This synthetic custom example selects linework without a medium:

```json
{
  "artifact_type": "render-intent",
  "execution_mode": "text-to-image",
  "preset": null,
  "axes": {"linework": "continuous dark contours"},
  "presentation": "single illustration",
  "selection": {"chosen_by": "user", "reason": "The fixture author selected the contour treatment."},
  "prompt_expression": "Use continuous dark contours.",
  "regional_overrides": []
}
```

Selecting a named preset constructs its complete declaration:

```bash
python scripts/render_contract.py intent --preset flat-graphic --mode text-to-image \
  --chosen-by agent --reason "A restrained graphic treatment supports the requested icon." \
  --presentation "single illustration" --out render-intent.json
python scripts/render_contract.py validate-intent render-intent.json --draft
```

The selected-preset draft leaves its prompt wording to the author. Resolve the selected model's
input workflow below, then fill `prompt_expression` with the exact authored span
that describes the visible finish. A tag-based rendition searches its vocabulary;
a descriptive rendition can use sufficient supplied knowledge directly.
Include every regional expression in the final prompt as well.
Preset names, choice reasons and provenance stay in the intent record.
`validate-intent` without `--draft` requires that wording.
The generation builder also checks that it actually appears in the authored prompt.
This proves inclusion, not semantic correctness or model effectiveness; the agent reviews those separately.

An operation-only declaration needs no presentation, selection reason or finish
span. When a rendering declaration is selected, complete its actual prompt
expression before generation and preserve every supplied constraint. Keep the
declared text-free upscale behavior below.
`schemas/render-intent.schema.json` owns the public structure.
Dispatcher intent is owned by the editable generation choices or their selected Production Specification. A direct task can supply `generation.render_intent`; the authoring selector `{ "document": "delivery" }` binds the actual editable text. External image work retains the same intent as an applied task source.
The chosen source's identity and current-state authority remain separate from rendering.

## Read the model's guidance

After runtime activation, inspect the selected model and its exact service:

```bash
python scripts/render_contract.py models --operation upscale --service SERVICE_ID
python scripts/render_contract.py model --model MODEL_ID --service SERVICE_ID
python scripts/catalog_cli.py inspect <model-id>
```

`models` lists the matching models and offerings, their complete guidance cards,
and an executable inspection action for each one. Omit `--service` to compare
all registered offerings for the operation. Each action retains the selected
pack runtime. `model` prints one complete guidance card; catalog inspection
prints a card for each offering. These commands resolve every enabled pack.
Pass the same state, cache, managed root, and extra pack roots to every model-aware command.
The prompt-dialect command resolves the model, dialect, and writing guide in that same runtime.
The prompt-dialect report and route reading with `--model` include the same cards.
They expose recommended positive and negative text, merge mode, parameter recommendations,
size choices, prompt slot order, evidence basis, limitations, and every mode's controls.
The card also exposes the exact `prompt_input` declaration, its owning
`prompt_dialect` where applicable, and `requires_vocabulary_search`.
Read this output while choosing model-dependent means and before preparing
model-specific wording or values. Check a consequential style or technique
against its actual scoped guidance and observations; dictionary membership
alone proves neither training membership nor the requested effect. A supported
input field also does not establish expressive success.
A model change means a new card, prompt review, parameter resolution, and
authorization scope review. Retain the applicable visual intent while
reassessing how the new target can realize it. Use evidenced wording and
supported adaptations or references where appropriate; do not assume a medium
name will transfer the appearance or silently substitute the subject or target.
Never swap the selected provider or model for another image tool merely because it is available.

Recommendations live in the model's existing `recommended_parameters`,
`recommended_positive_prompt`, and `recommended_negative_prompt` fields.
`execution_profile` belongs to the exact offering, or to a host-only model with no offering.
Its controls point to recommendation names; they do not duplicate the values.
One interface never inherits another interface's capabilities implicitly.

### Prompt input

The required `prompt_input` contract distinguishes these workflows:

| Mode | Input and authoring consequence |
| --- | --- |
| `tag-based` | The selected workflow uses tags and named vocabularies. Search existing wording before finalizing the rendition, even if the model also accepts prose. |
| `descriptive` | Use the declared natural-language or structured-caption form. Investigate construction and wording questions as needed. |
| `unresolved` | The actual model, version or input behavior is not established. Retain a portable depiction and resolve the evidence before target-specific finalization. |
| `none` | The selected operation has no text prompt surface. Supply its evidenced media and controls. |

`forms`, `vocabularies`, and nonempty `basis` are present for every mode.
Unresolved and no-prompt records keep both arrays empty. Descriptive records
have no tag vocabulary scope. Tag-based records include `tags` in `forms`,
name their vocabulary IDs and declare `prompt_dialect` as the owning family.
Other modes omit `prompt_dialect`. These declarations are independent of the
service's weighting parser and of whether an execution offering is configured.

Read each basis statement at its stated model, family, adapter, operation or
author-selection scope. An adapter that routes among several models does not
establish the eventual model's input. A family may accept more than one form;
this does not remove a selected tag workflow's search requirement. See
[Model request evidence](model-evidence.md#prompt-input-evidence) for authoring
the contract and [Vocabulary](prompt-vocabulary.md#select-wording-for-a-tag-based-model)
for the existing retrieval and settlement flow.

A card may report `ready_for_parameter_resolution: false` for an unconfigured model.
Its catalog entry remains readable, but Generation Package dispatch requires an authored execution profile.
The card's `readiness` keeps four questions separate:

| Field | What its status establishes |
| --- | --- |
| `parameter_profile` | Whether the selected interface declares the controls used for parameter resolution |
| `service_operation` | Whether the acquired service and transport expose the requested operation; catalog-only inspection says `not-acquired` |
| `validation_evidence` | Whether evidence is still required, selected by the author, declared by the offering, or already acquired |
| `request_check` | Whether an exact request has been checked; ordinary model inspection reports `not-performed` |

An available profile is not evidence that a schema exists or a request was
accepted. `unresolved` names the responsible choice and the action needed for
dispatcher preparation. An explicit target schema, bounded probe or adopted
observed profile can supply validation when the offering has no default schema.
Preparation checks the selected evidence and exact request; sending still
requires its own authority and authentication.
An execution profile's `basis.kind` is `provider-documentation`, `curated-starting-point`, `measured` or `synthetic`.
A `measured` basis names the adopted observed request profile it rests on, by its path inside the pack and its SHA-256.
No other kind names one.
A synthetic basis from `scripts/render_contract_smoke_test.py`, trimmed:

```json
{"kind": "measured", "source": "Synthetic adopted trial.", "limitations": ["One request tuple."],
 "observed_profile": {"path": "resources/observed-profiles/trial/profile.json", "sha256": "aaaaaaaa..."}}
```

`render_contract.py model` verifies that observed profile through request validation in `observed-profile` mode before it shows the card.
A `measured` claim the pack cannot prove is refused (synthetic, from the same test):

```json
{"ok": false, "errors": ["a measured basis names an adopted observed request profile: resources/dialects.json"]}
```

[Model request evidence](model-evidence.md#keep-kinds-of-evidence-apart) keeps the kinds of evidence apart.

## Apply the author's model selection preferences

Guidance cards include `use_case_suitability` beside the interface controls.
They combine the selected offering's `use_case_guidance` with current author preferences.
The catalog owns model facts. The author owns the model selection policy.
Preference reading selects one complete source in this order:

1. `model-selection-preferences.json` under `CPB_HOME`, or `~/.character-prompt-builder` while unset, supplies the user-owned override.
2. The active pack runtime resolves the named `model-selection-preferences` resource through its existing rank and conflict rules.
3. An absent override and resource produce an empty preference set with a null source.

The [pack resource contract](../maintenance/packs.md#core-interpreted-resource-contracts) keeps each policy in its declaring pack.
Resolution reads that resource in place and selects the whole file; it never copies or merges policies into another owner.
A missing pack state leaves pack preferences inactive. Preference inspection never initializes or activates discovered packs.
An explicit home override with `entries: []` selects the empty policy. Skill updates preserve the override.
Invalid selected files and unresolved resource conflicts are reported as errors.
Inspection records the source path and hash, plus pack UUID and relative path when a pack supplies the file.
Catalog caches retain resource ownership; each preference read uses the selected source bytes.

Inspect the selected preferences, or validate and install a complete home override:

```bash
python scripts/render_contract.py preferences
python scripts/render_contract.py preferences --file author-model-preferences.json
```

The [preference schema](../../schemas/model-selection-preferences.schema.json) gives each entry an explicit family selector, service, operations and use cases.
`family` is a descriptive name. `model_patterns` match catalog IDs or exact interface identifiers with case-sensitive shell patterns.
A selected policy may address models from other active packs or exact external interfaces while remaining in its owner pack.
A null service applies the author's preference across services. Declare a service when the report covers only that interface.
`discourage` excludes a default recommendation for the matching use. `no-discouragement` records the author's deliberate choice to leave it eligible.
Both retain their reason, source, date and limitations; neither becomes provider policy or a measured success rate.
`reported_failure` names an explicitly reported `provider-refusal` or `provider-moderation`, with `user-report` provenance.
Use null for preferences without such a report, including aesthetic, speed and cost choices.
The [synthetic example](../../examples/model-evidence/selection-preferences.json) demonstrates the complete file.

For a relevant use, assess input conditions and alternatives together:

```bash
python scripts/render_contract.py assess --model MODEL_ID --service SERVICE_ID \
  --use-case USE_CASE --mode reference-guided --reference-count 4 \
  --alternative-model OTHER_MODEL_ID
```

Repeat `--use-case` and `--alternative-model` for additional declared uses and candidates.
`--service` names only the selected target's interface. Each alternative uses its sole catalog offering, or `--alternative-model MODEL_ID=SERVICE_ID` selects one explicitly. A multi-service alternative needs that explicit choice. Unresolved alternatives retain a reason in `alternative_resolution_errors` without discarding the selected assessment or other candidates. `suggested_models` names each candidate's model, service and exact interface identifier.
The agent understands the brief and declares applicable use cases using existing author context.
Do this during ordinary model selection and failure review, without requiring the user to classify every request.
Prompt keywords alone never determine the use case.
`benign-minor-depiction` identifies ordinary depictions of minors independently from prohibited content.
`policy-sensitive-use` is an author-declared selection scope; record the actual permitted purpose in the task's direction.
Each stage uses its own mode, reference count and applicable preference scope.
Use the number of physically transmitted images after attachment deduplication or explicit board preparation, not the number of logical subject/use assignments.

The assessment returns scoped recommendations, their evidence, input compatibility and `suggested_models`.
A candidate must meet the declared mode and recorded reference limit and have no matching discouragement.
An unknown use-case history produces no automatic warning and no claim that a model is restriction-free.
The agent checks applicable rules and the actual intended content before preparing a permitted request through the ordinary execution owner.
Changing model, disabling moderation, disguising the request or automatic resubmission is never a diagnostic action.

A target outside the catalog can still use family preferences:

```bash
python scripts/render_contract.py assess --model-identifier EXACT_IDENTIFIER --service SERVICE_ID \
  --operation generation --use-case USE_CASE --mode reference-guided --reference-count 2
```

This reports author preferences while interface compatibility remains unknown until the target's controls are acquired.
Preference inspection, assessment and diagnosis honor the same `--state-file`, `--cache-dir` and `--managed-root` runtime arguments for catalog and external targets.
Preserve the assessment as an applied task source and cite the selection reason in `direction.decisions`.
Parameter contracts keep their own immutable interface controls; preference changes affect new selection decisions and leave those controls intact.

## Declare controls by operation

Every mode names its media semantics and its controls using exact request paths.
Nested controls use dotted paths in the execution profile and nested JSON objects in authored parameters.
Its `prompt_syntax` declares the grammar used for prompt inspection: a fixed/default
grammar and, where exposed, the native control path and value-to-grammar mapping.
The mapping belongs to this mode's interface evidence. A field's spelling never
selects a parser by itself. See [Explicit prompt weighting](prompt-weighting.md)
for the shared declaration and a synthetic nested-control example.
Every mode states a seed and output-count disposition, including interfaces that expose neither.

| Status | Behavior |
| --- | --- |
| `required` | Supply an explicit value or resolve a single authored recommendation. |
| `optional` | Leave the feature unselected unless the author supplies a value. |
| `not-applicable` | Show the reason and reject any transmitted value, including null. |
| `backend-managed` | Show that the interface exposes no control; never invent its internal value. |

A numeric recommendation range is not a chosen value. The agent or user must choose within it.
An optional feature does not activate because another field opens its JSON envelope.
Unsupported names, case mismatches, non-finite values, and unknown modes fail resolution.
Value schemas validate types and limits; the mode's `parameter_schema` validates cross-field combinations.
For example, it can require either explicit width and height or a named resolution, but not both.
Schema defaults never substitute for parameter decisions.

For exposed sampling controls, declare steps, guidance, sampler, parser, and other meaningful controls.
For a managed instruction model, mark unavailable controls as backend-managed instead of fabricating them.
A source-image denoising value applies only to a mode that exposes that control.
A style reference is not automatically an img2img seed; the selected transport must match the intended influence.
Weights on adapters, guidance inputs, and other optional features need their own declared paths and schemas.
Keep source identity, rendering influence, composition influence, and transport roles separate.

Validate a proposed execution profile against `schemas/model-execution-profile.schema.json`:

```bash
python scripts/render_contract.py validate-profile execution-profile.json
```

## Resolve and inspect the exact input

After resolving the selected target and rendering intent, compile a local plan without a paid request. Required tag retrieval and any selected plot approval keep their own contracts:

```bash
python scripts/render_contract.py compile --model MODEL_ID --service SERVICE_ID \
  --intent render-intent.json --parameters parameters.json --prompt-file prompt.txt \
  --reference-count 0 --out render-contract.json --text
```

Keep native execution settings in the selected interface's declared request fields.
The output distinguishes explicit values, model recommendations, unselected features,
dispatch-required controls, non-applicable controls, and backend-managed controls.
Each decision includes its reason. The plan retains both authored and effective parameters.
`schemas/render-contract.schema.json` describes its public structure; runtime verification also checks derivation and hashes.
Unknown or incomplete input fails with a nonzero exit and a concrete error; it creates no partial plan.
The CLI refuses to overwrite an existing output file.

The Generation Package builder compiles this contract from the selected rendering intent, using the Production Specification when it owns that intent.
Its commitment includes the chosen intent, complete model card, recommendations, and resolved controls.
Verification recomputes the decisions and checks the active interface against the pinned card.
Preparation compiles the real request with the task's seed and count and checks the wire values again.
An optional seed remains omitted when unselected; a selected seed must reach the
request unchanged. A required seed needs an explicit value, and a backend-managed
seed remains absent.
Transport adapters do not fill absent sampling, rendering, or output parameters behind this check.
Request-schema, reference, studio, cost and authority checks apply as well.

The dispatcher preview prints the rendering choice before the complete request.
Read the final positive and negative transport and all applied values from that preview.
Review how the finish contributes to the whole depiction, with its required
identity detail and scoped exclusions, before approving the exact request.
A prompt-only answer preserves any selected rendering constraints and uses model guidance when a target is named,
but does not need a submission authorization or an invented model when none was requested.

## External image work

An external task uses the exact host's acquired contract when no catalog profile exists.
Record the missing definition and requested identifier through [Image Generation](image-generation.md#choose-execution).
Existing-image changes also follow [Semantic instruction editing](semantic-instruction-edit.md) to bind their source and reference scopes.
Resolve supported request fields and any selected rendering constraints.
Preserve the source finish when an edit leaves it fixed. An external image
request needs no separate render-intent source when none is selected. Keep a
selected declaration in an applied task source with role `render-intent` and
validate it with:

```bash
python scripts/render_contract.py validate-intent STUDIO/inputs/render-intent.json
```

For an authored rendering declaration, check that its `prompt_expression`
appears in the final instruction with the intended scope.
Retain that file and the exact request as applied task sources. Semantic edit preparation also checks its acquired request schema when present.
It does not compile an execution profile or a dispatcher render contract for an absent model.
Only evidence-backed controls enter the request; unavailable controls remain absent.

## Preserve an image during enlargement

An upscale request also carries `render_intent`, with `execution_mode: upscale`.
An operation-only declaration is sufficient when no additional rendering
constraint is selected; the source and its applicable treatment remain bound.
Preserve the declared source treatment unless a change is authorized. An
interface without a text channel receives no invented prompt fields. If an
authored rendering declaration is selected for that operation, its
`prompt_expression` stays empty. A guided upscaler includes any selected
rendering expression in its actual guidance prompt; guidance alone does not
require a rendering declaration.
The offering maps the neutral `scale` setting to its actual request field in `parameter_keys`.
The upscaler's execution profile declares that field and every other setting, including unavailable seed and count controls.
Its recipe can describe source-image and scale selection without a rendering
slot. A text-free interface does not require an invented style or prompt.
`native_scale_factor` describes the network's native enlargement. The separate
`supported_scale_factors` field describes known request factors; an absent or
null value means those API factors remain unknown. Never derive an API enum
from a model name or native factor. The exact offering profile and selected
request evidence constrain the requested scale. A factor that the schema of the
profile's scale control refuses is `CONTROL_NOT_AVAILABLE` at the declaration's
`scale_factor`, and its repair names that control.
Pass the intent file with `--render-intent` to `production_binding.py`, and to `dispatch.py --upscale` for its preview.
The sealed request retains the complete resolved contract beside the source evidence.

## Extension and verification

Author an execution profile for the interface actually exposed, not for a similarly named family.
Retain the provider's true spelling, supported modes, value constraints, and unavailable controls.
Give synthetic examples a synthetic basis and never ship them as measured provider advice.
The agent owns recipe application and conflict review; deterministic code does not infer art direction from keywords.

`render_contract_lib.py` owns validation, resolution, cards, commitments, and wire checks.
`render_contract.py` is its public command interface.
`render_contract_fixtures.py` contains only explicitly synthetic test constructors.
The example resolves and verifies a contract for a fictional interface without sending a generation request:

```bash
python examples/render-contract/build_example.py --check
python scripts/render_contract_smoke_test.py
python scripts/model_contract_smoke_test.py
```

The tests cover explicit choices, unsupported inputs, conditional controls, execution profile drift,
parameter overrides, nested paths, request tampering, and model guidance visibility.
They establish contract behavior, not artistic quality.
