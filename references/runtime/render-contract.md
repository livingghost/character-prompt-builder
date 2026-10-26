# Rendering choices and execution controls

Resolve the intended finish and the exact interface before composing a final image prompt.
A rendering choice never changes identity, age, proportions, wardrobe, story, or authority.
The agent decides meaning; the tools validate explicit choices and preserve their provenance.

## Choose the finish

`python scripts/render_contract.py presets` lists reusable starting points.
Choose a preset or author a custom intent with `preset: null`.
Keep six axes independent: medium, dimensionality, linework, shading, surface, and detail.
The presentation field records the construction chosen under
[Production direction](production-direction.md#choose-the-expression), such as
a portrait, diagram, panel sequence or product view. A rendering preset or
studio default supplies finish within that choice; it does not choose the
presentation or require a single continuous scene.
A vector-like appearance does not promise a vector file. Output encoding belongs to the interface controls.

Record who chose the direction (`user` or `agent`) and why.
Ask about a material ambiguity; otherwise choose deliberately within the user's open creative space.
The base axes describe the shared treatment. Regional overrides assign
different treatment to a named subject, part, layer or area, with its reason
and visible expression. A scope may overlap another or sit within one subject;
it need not form a separate panel. Resolve which treatment governs each
affected property and how the scopes meet. Author a custom intent when a
selected combination is the treatment itself.
The agent may choose a mixed treatment within delegated creative space.
An explicit fixed medium or protected source region remains authoritative.
The registry is a discovery aid, not a closed list of media.

```bash
python scripts/render_contract.py intent --preset flat-graphic --mode text-to-image \
  --chosen-by agent --reason "A restrained graphic treatment supports the requested icon." \
  --presentation "single illustration" --out render-intent.json
python scripts/render_contract.py validate-intent render-intent.json --draft
```

The draft has no invented prompt words. Retrieve wording under the skill's retrieval gate first.
Then fill `prompt_expression` with the exact authored span that describes the visible finish.
Include every regional expression in the final prompt as well.
Preset names, choice reasons and provenance stay in the intent record.
`validate-intent` without `--draft` requires that wording.
The generation builder also checks that it actually appears in the authored prompt.
This proves inclusion, not semantic correctness or model effectiveness; the agent reviews those separately.

`templates/render-intent.template.json` provides the custom form.
A template with unresolved axes is not a valid generation input.
`schemas/render-intent.schema.json` owns the public structure.
The Production Specification contains dispatcher intent. External image work retains the same intent as an applied task source.
The chosen source's identity and current-state authority remain separate from rendering.

## Read the model's guidance

After runtime activation, inspect the selected model and its exact service:

```bash
python scripts/render_contract.py model --model MODEL_ID --service SERVICE_ID
python scripts/catalog_cli.py inspect <model-id>
```

The first command prints one complete guidance card. Catalog inspection prints a card for each offering.
Both resolve models from every enabled pack.
Pass the same state, cache, managed root, and extra pack roots to every model-aware command.
The prompt-dialect command resolves the model, dialect, and writing guide in that same runtime.
The prompt-dialect report and route reading with `--model` include the same cards.
They expose recommended positive and negative text, merge mode, parameter recommendations,
size choices, prompt slot order, evidence basis, limitations, and every mode's controls.
Read this output before preparing model-specific wording or values.
A model change means a new card, prompt review, parameter resolution, and authorization scope review.
Never swap the selected provider or model for another image tool merely because it is available.

Recommendations live in the model's existing `recommended_parameters`,
`recommended_positive_prompt`, and `recommended_negative_prompt` fields.
`execution_profile` belongs to the exact offering, or to a host-only model with no offering.
Its controls point to recommendation names; they do not duplicate the values.
One interface never inherits another interface's capabilities implicitly.

A card may report `ready_for_parameter_resolution: false` for an unconfigured model.
Its catalog entry remains readable, but Generation Package dispatch requires an authored execution profile.
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

After retrieval and plot approval, compile a local plan without a paid request:

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

The Generation Package builder compiles this contract from its Production Specification.
Its commitment includes the chosen intent, complete model card, recommendations, and resolved controls.
Verification recomputes the decisions and checks the active interface against the pinned card.
Preparation compiles the real request with the task's seed and count and checks the wire values again.
Transport adapters do not fill absent sampling, rendering, or output parameters behind this check.
Request-schema, reference, studio, cost and authority checks apply as well.

The dispatcher preview prints the rendering choice before the complete request.
Read the final positive and negative transport and all applied values from that preview.
Review how the finish contributes to the whole depiction, with its required
identity detail and scoped exclusions, before approving the exact request.
A prompt-only answer uses the same deliberate finish choice and model guidance when a target is named,
but does not need a submission authorization or an invented model when none was requested.

## External image work

An external task uses the exact host's acquired contract when no catalog profile exists.
Record the missing definition and requested identifier through [Image Generation](image-generation.md#choose-execution).
Existing-image changes also follow [Semantic instruction editing](semantic-instruction-edit.md) to bind their source and reference scopes.
Resolve the visible finish and supported request fields before composition. Preserve the source finish when an edit leaves it fixed.
Keep the final intent in an applied task source with role `render-intent` and validate it with:

```bash
python scripts/render_contract.py validate-intent STUDIO/inputs/render-intent.json
```

The author checks that its `prompt_expression` appears in the final instruction with the intended scope.
Retain that file and the exact request as applied task sources. Semantic edit preparation also checks its acquired request schema when present.
It does not compile an execution profile or a dispatcher render contract for an absent model.
Only evidence-backed controls enter the request; unavailable controls remain absent.

## Preserve an image during enlargement

An upscale request also carries `render_intent`, with `execution_mode: upscale`.
Choose the source finish deliberately, preserving its declared treatment unless a change is authorized.
An interface without a text channel uses an empty `prompt_expression`; it does not receive invented prompt fields.
A guided upscaler includes the retrieved expression in its explicit guidance prompt.
The offering maps the neutral `scale` setting to its actual request field in `parameter_keys`.
The upscaler's execution profile declares that field and every other setting, including unavailable seed and count controls.
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
