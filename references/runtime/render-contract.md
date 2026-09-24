# Rendering choices and execution controls

Resolve the intended finish and the exact interface before composing a final image prompt.
A rendering choice never changes identity, age, proportions, wardrobe, story, or authority.
The agent decides meaning; the tools validate explicit choices and preserve their provenance.

## Choose the finish

`python scripts/render_contract.py presets` lists reusable starting points.
Choose a preset or author a custom intent with `preset: null`.
Keep six axes independent: medium, dimensionality, linework, shading, surface, and detail.
The presentation field separately describes the artifact, such as a portrait, diagram, panel, or product view.
A vector-like appearance does not promise a vector file. Output encoding belongs to the interface controls.

Record who chose the direction (`user` or `agent`) and why.
Ask about a material ambiguity; otherwise choose deliberately within the user's open creative space.
Use regional overrides for a genuinely mixed treatment, naming each region and its reason.
Do not combine mutually exclusive whole-image treatments into an accidental average.
The registry is a discovery aid, not a closed list of all possible media.

```bash
python scripts/render_contract.py intent --preset flat-graphic --mode text-to-image \
  --chosen-by agent --reason "A restrained graphic treatment supports the requested icon." \
  --presentation "single illustration" --out render-intent.json
python scripts/render_contract.py validate-intent render-intent.json --draft
```

The draft has no invented prompt words. Retrieve wording under the skill's retrieval gate first.
Then fill `prompt_expression` with the exact authored span that expresses the finish.
Include every regional expression in the final prompt as well.
`validate-intent` without `--draft` requires that wording.
The generation builder also checks that it actually appears in the authored prompt.
This proves inclusion, not semantic correctness or model effectiveness; the agent reviews those separately.

`templates/render-intent.template.json` provides the custom form.
A template with unresolved axes is not a valid generation input.
`schemas/render-intent.schema.json` owns the public structure.
The Production Specification contains the intent, and its current-state contract remains authoritative.

## Read the model's guidance

After runtime activation, inspect the selected model and its exact service:

```bash
python scripts/render_contract.py model --model MODEL_ID --service SERVICE_ID
python scripts/catalog_cli.py inspect <model-id>
```

The first command prints one complete guidance card. Catalog inspection prints a card for each offering.
Both resolve models from every enabled pack, including registered and user-installed packs.
Pass the same state, cache, managed root, and extra pack roots to every model-aware command.
The prompt-dialect command resolves the model, dialect, and writing guide in that same runtime.
The prompt-dialect report and route reading with `--model` include the same cards.
They expose recommended positive and negative text, merge mode, parameter recommendations,
size choices, prompt slot order, evidence basis, limitations, and every mode's controls.
Read this output before preparing model-specific wording or values.
A model change means a new card, prompt review, parameter resolution, and authorization scope review.
Never replace the selected provider or model with another image tool merely because it is available.

Recommendations live in the model's existing `recommended_parameters`,
`recommended_positive_prompt`, and `recommended_negative_prompt` fields.
`execution_profile` belongs to the exact offering, or to a host-only model with no offering.
The profile's controls point to recommendation names; they do not duplicate the values.
One interface never inherits another interface's capabilities implicitly.

A card may report `ready_for_parameter_resolution: false` for an unconfigured model.
Its catalog entry remains readable, but generation requires an authored execution profile.
Record exact provider documentation or stored schema evidence where available.
Distinguish provider documentation, curated starting points, measured findings, and synthetic fixtures.
Stored evidence is not a claim that a remote API was checked today.
A quality finding needs its own measured scope; a successful request proves only acceptance.
Never turn one image, dictionary hit, or different engine's result into a universal model recommendation.

## Declare controls by operation

Every mode names its media semantics and its controls using exact request paths.
Nested controls use dotted paths in the profile and nested JSON objects in authored parameters.
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

For exposed sampling controls, declare steps, guidance, sampler, parser, and other meaningful controls explicitly.
For a managed instruction model, mark unavailable controls as backend-managed instead of fabricating them.
A source-image denoising value applies only to a mode that exposes that control.
A style reference is not automatically an img2img seed; the selected transport must match the intended influence.
Weights on adapters, guidance inputs, and other optional features need their own declared paths and schemas.
Keep source identity, rendering influence, composition influence, and transport roles separate.

`schemas/model-execution-profile.schema.json` defines the profile.
Validate a proposed profile with:

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

The output distinguishes explicit values, model recommendations, unselected features,
dispatch-required controls, non-applicable controls, and backend-managed controls.
Each decision includes its reason. The plan retains both authored and effective parameters.
`schemas/render-contract.schema.json` describes its public structure; runtime verification also checks derivation and hashes.
Unknown or incomplete input fails with a nonzero exit and a concrete error; it creates no partial plan.
The CLI creates a new output file and refuses to overwrite one.

The Generation Package builder compiles this contract from its Production Specification.
Its commitment includes the chosen intent, complete model card, recommendations, and resolved controls.
Verification recomputes the decisions and checks the active interface against the pinned card.
Dispatch checks explicit seed and count, compiles the real request, and checks the wire values again.
Transport adapters do not fill absent sampling, rendering, or output parameters behind this check.
Existing request-schema, reference, studio, cost, and authority checks still apply.

The dispatcher prints the rendering choice before the complete request preview.
Read the final positive and negative transport and all applied values from that preview.
A prompt-only answer uses the same deliberate finish choice and model guidance when a target is named,
but does not need a submission authorization or an invented model when none was requested.

## Preserve an image during enlargement

An upscale request also carries `render_intent`, with `execution_mode: upscale`.
Choose the source finish deliberately, preserving its declared treatment unless a change is authorized.
An interface without a text channel uses an empty `prompt_expression`; it does not receive invented prompt fields.
A guided upscaler includes the retrieved expression in its explicit guidance prompt.
The offering maps the neutral `scale` setting to its actual request field in `parameter_keys`.
The upscale profile declares that field and every other setting, including unavailable seed and count controls.
Pass the intent file to both request preparation and dispatch with `--render-intent`.
The sealed request retains the complete resolved contract beside the source evidence.

## Extension and verification

Author a profile for the interface actually exposed, not for a similarly named family.
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

The tests cover explicit choices, unsupported inputs, conditional controls, profile drift,
parameter overrides, nested paths, request tampering, and model guidance visibility.
They establish contract behavior, not artistic quality.
