# SDXL and ComfyUI Adapter

Use this adapter for an active SDXL-lineage checkpoint in a characterized local or hosted workflow. ComfyUI is a workflow host; a graph loading another model family uses that model's adapter. Image execution first completes [Image Generation Runtime](../runtime/image-generation.md). Conversation-only rendition follows [Prompt-only Core](../runtime/prompt-only-core.md) and uses the applicable text-conditioning knowledge without generation setup.

## Prompt and negative rendition

Read the [Prompt Writing Guide Runtime](../runtime/prompt-writing-guide.md) after selecting the exact checkpoint and workflow. When a `prompt-writing-guide` provider is selected, apply its tag ordering, prompt-pressure, attention, LoRA, negative, embedding, and controlled-comparison rules only where the active parser and graph support them.

Use the requested form and the exact checkpoint's evidenced vocabulary and ordering. [Interface rendition](../runtime/prompt-writing-guide.md#carry-the-construction-into-supported-means) owns adaptation of the whole picture and the distinction between supported approximation and unmet requirements. A tag rendition uses tags; a descriptive rendition uses supported prose. Preserve the full depiction at its source without pasting it into a tag input. Apply record-owned positive or negative recommendations under their merge mode and scope, rather than requiring a quality block or a second universal block order.

An observed output may introduce marks, framing or props associated with a learned content cluster. Judge whether they conflict with the commissioned picture before changing its terms or exclusions. Required overlaps, crop and graphic treatment remain part of the intended picture.

For an image-to-image pose change, assess preservation and movement separately under the actual denoising and conditioning setup. An initial image can resist a large pose change, but does not establish an absolute pose lock. Use the [Character Repose Workflow](../runtime/character-repose-workflow.md) to choose available means and review the result.

## Sampling behavior

Read the exact checkpoint, loaded components, parser and graph before selecting controls. Related workflows can use different encoders, prediction types, conditioning and image operations. The record and platform own what a request may set. The [Prompt Writing Guide Runtime](../runtime/prompt-writing-guide.md) owns prompt-side judgment.

**Encoder layers.** The standard ComfyUI core SDXL path uses CLIP-L and CLIP-G, selects their penultimate hidden layers (-2), concatenates the token features and also uses CLIP-G's pooled output. The same text can therefore have both token-level and pooled conditioning roles. Diffusers v0.35.1's standard SDXL pipeline also defaults to the penultimate layer, but its `clip_skip=n` selects hidden layer `-(n+2)`. Copying a UI's "clip skip 2" into that parameter does not select the default layer. Match the loaded encoders, selected layers and host convention; a derivative or custom node may use another path. These implementation facts do not predict how literally a particular tag will be drawn.

**Token spans.** The standard SDXL CLIP encoders use sequences of 77 positions, normally leaving 75 for prompt tokens after start and end markers. This is neither 75 words nor 75 tags. ComfyUI core's standard CLIP path tokenizes, pads and encodes longer input in chunks, then concatenates the encoded sequences. Each chunk has its own transformer context; accepting a long string does not turn it into one long attention window. Keep a consequential attribute near its subject and inspect actual token boundaries when available. Later chunks are not necessarily discarded, and an earlier position does not guarantee a stronger visual effect.

The bare Diffusers v0.35.1 SDXL pipeline truncates text at the tokenizer's `model_max_length`; a separate embedding library can supply another long-prompt path. AUTOMATIC1111 implements chunking with its own boundary rules and `BREAK`. ComfyUI core's standard tokenizer does not implement that A1111 `BREAK` operation. Select the actual parser and encoding path before relying on either behavior. Remove redundant restatement before losing required concepts, and retain any unmet requirement at its source. A controlled image comparison can investigate placement, but one concept appearing or disappearing does not prove truncation or parser behavior.

**CFG scale.** In a compatible classifier-free guidance pipeline, the setting changes the combination of positive and unconditioned or negative predictions. It is separate from a token's emphasis weight; [weight and channel semantics](#text-weights-and-conditioning-channels) explains that distinction. Select the range from the exact checkpoint and workflow. Excessive contrast, color shifts and weaker adherence are observed outcomes to investigate, not a universal threshold. Distilled or differently guided workflows can require different handling.

**Sampler and steps.** The sampler selects the iterative solver, the scheduler selects the noise levels or times it traverses, and the step count determines its sampling schedule's length. These choices jointly affect the result; a checkpoint's Euler ancestral recommendation does not select every host's scheduler. A deterministic sampler does not imply that changing the step count leaves a picture unchanged. Preserve sampler, scheduler, steps, CFG, seed, dimensions, model, encoders and additional conditioning during a controlled prompt comparison. Use the checkpoint's applicable recommendations for a new trial.

**Seed.** A seed identifies an initial random state in the recorded implementation, not a character identity. Reproduction also depends on the loaded weights, conditioning, scheduler, software and numerical execution. A changed prompt may preserve some structure or change it substantially; assess identity from the actual result.

**Denoising strength.** In a characterized image-to-image pipeline, strength selects how much noise or how much of a denoising schedule is applied to the initial image. Lower and higher values change the balance between preservation and reconstruction, but do not partition changes into guaranteed categories such as style, shape and identity. Inspect both the requested edit and preserved structure, including small markings and facial details.

**Two-pass enlargement.** Use the exact checkpoint's supported sizes and training guidance; later derivatives need not share an original base's resolution. Inspect repeated bodies, changed proportions and composition drift when enlarging. A supported two-pass workflow can generate at a suitable size, enlarge and refine with image-to-image. Tiled processing can introduce local disagreement and seams, so judge the complete assembled image. A dedicated upscaler is a separate operation with its own contract.

**Inpainting.** Inspect the mask semantics, initialization, crop, padding, denoising and final blending of the actual workflow. A mask alone does not guarantee unchanged pixels outside it. Processing a crop can give a small part more working resolution while losing surrounding context. Preserve relevant identity and contact information, and inspect the seam and unedited scene in the returned image.

**Initial image, ControlNet and IP-Adapter.** These mechanisms condition a result differently. Availability, compatibility and effects belong to the loaded versions and workflow.

| Mechanism | Intended contribution | What to verify |
|---|---|---|
| Initial image in img2img | Image content used to initialize reconstruction | Preserved appearance, allowed change and drift under the actual strength and schedule |
| Compatible ControlNet and guide | Conditioning from an evidenced structural signal such as edges, depth or pose | Guide quality, model compatibility, strength, timing and whether the resulting structure serves the request |
| Compatible IP-Adapter and reference | Image conditioning whose subject, style or identity scope depends on the adapter | Loaded variant, reference contribution, influence and retained identity or treatment in the output |

Neither a mechanism's name nor a reference attachment establishes identity fidelity. A selected LoRA, identity-specific adapter or combined workflow needs its own evidence and compatible execution. Offer a different model only as an explicit alternative when it is needed and available; do not replace the selected target silently.

**Detail and scale.** Count, contacts, repeated small structures, glyphs and reflections can be difficult for a selected checkpoint. Diagnose the actual failure against the commissioned whole rather than hiding difficult parts or isolating them in a new frame by default. Preserve required scale, crop and overlap. Better wording, a different supported construction, a local edit or an acknowledged limit can each be appropriate; a longer prompt or a mask is not a universal repair.

**Resolution and aspect.** Use the exact checkpoint's known working sizes and the host's dimension rules. Assess unusual aspect ratios and resampling in context. Cropping is an option only when it preserves the required construction; it is not a default replacement for the requested frame.

Structural conditioning varies by host: hosting platforms gate adapters by architecture, and a derivative family may lack any ControlNet or identity-adapter. Confirm availability from the platform inventory before planning a structural channel. When none exists, say so rather than substituting an image-to-image seed for a structural guide.

Send the complete verified negative prompt through separate conditioning. Use `separate-field` only when the loaded model and graph expose that channel. ComfyUI itself is a workflow host; the model record is the authority on behavior.

## Text weights and conditioning channels

ComfyUI core's standard CLIP implementation supplies a concrete example. Its
token weighting transforms contextual token vectors around an empty-input
baseline:

```text
weighted = empty + weight * (contextual - empty)
```

This is not a multiplier on the amount of a visible feature. At weight zero,
that token position reaches the empty baseline, but other tokens were encoded
in the original context and the pooled output is not scaled by this transform.
Zeroing a token therefore need not equal deleting its text. A negative numeric
weight is not a reliable logical negation.

Without a CFG override, ComfyUI combines the model predictions as:

```text
prediction = negative_prediction + CFG * (positive_prediction - negative_prediction)
```

Token weighting changes a condition used to obtain a prediction; moving a term
to the negative channel changes the other prediction. They are not interchangeable
with each other or with changing CFG. In this standard equation CFG 1 cancels
the negative contribution; differently guided or overridden workflows need their
own interpretation. Neither equation measures a tag's visual success rate.

In the same ComfyUI core parser, `(term)` has implicit weight 1.1 and
`(term:1.2)` supplies an explicit value; `(term:0.8)` is a lower-value example,
not a recommended universal setting. Escape literal parentheses as `\(` and
`\)`. Explicit numeric weights replace inherited weights in that parser, so
`((term:1.2))` must not be assumed to multiply like AUTOMATIC1111 nesting.
Its standard tokenizer implements neither A1111's square-bracket reduction nor
its `BREAK` operation. The bare Diffusers SDXL pipeline does not supply these
parsers merely because it accepts the same text. The sampling section above scopes the encoders and chunking; implementation
sources are listed below. These examples do not add a ComfyUI backend
to CPB's hosted-text inspector.

## Reference forwarding

Use the loaded model's catalog record for accepted media and reference behavior, or an explicit reviewed workflow transport. Forward only verified carriers and parameters. Stop when the graph is unable to accept the complete planned reference set, or when its negative transport is uncharacterized.

When designing or auditing a ComfyUI-specific node or chained partial-construction workflow, read [ComfyUI Integration Notes](../comfyui-integration-notes.md). Prompting an existing characterized graph leaves that product-design provenance note unloaded.

## Provider-backed recommendations

Automatically merge reusable positive or negative recommendations only from the resolved model record, using its merge mode and provenance. This admission rule governs defaults; it does not prohibit an author from choosing quality, period, rating, content or exclusion terms for the current picture from the exact target's documented controls and examples. Select each term for its intended contribution and keep an example, an authored trial and an observed effect distinct. A sample's entire quality or negative stack is not thereby a reusable default. User-authored semantic text is kept in full rather than truncated to make room.

## Implementation evidence

The encoder and long-input descriptions above refer to ComfyUI core's [SDXL encoders](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy/sdxl_clip.py), [CLIP tokenizer and encoder](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy/sd1_clip.py) and [CLIPTextEncode node](https://github.com/Comfy-Org/ComfyUI/blob/master/nodes.py), with `master` inspected on 2026-11-15 rather than a pinned release; the [Diffusers v0.35.1 SDXL implementation](https://github.com/huggingface/diffusers/blob/v0.35.1/src/diffusers/pipelines/stable_diffusion_xl/pipeline_stable_diffusion_xl.py); and [AUTOMATIC1111's documented prompt features](https://github.com/AUTOMATIC1111/stable-diffusion-webui/wiki/Features). Match the selected installation and custom nodes before applying their implementation-specific behavior.

The official [SDXL pipeline documentation](https://huggingface.co/docs/diffusers/api/pipelines/stable_diffusion/stable_diffusion_xl), [SDXL ControlNet interfaces](https://huggingface.co/docs/diffusers/api/pipelines/controlnet_sdxl) and [IP-Adapter guide](https://huggingface.co/docs/diffusers/using-diffusers/ip_adapter) describe specific implementations and compatible components. They do not establish that a separately hosted checkpoint exposes the same operations or achieves the same result.

The ComfyUI examples use core `master` as inspected on 2026-11-15, without a
pinned release. Match the deployed implementation; custom nodes and CFG overrides
can differ.

- [ComfyUI CLIP parser and token weighting](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy/sd1_clip.py)
- [ComfyUI CFG combination](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy/samplers.py)
- [AUTOMATIC1111 attention parser](https://github.com/AUTOMATIC1111/stable-diffusion-webui/blob/master/modules/prompt_parser.py)
