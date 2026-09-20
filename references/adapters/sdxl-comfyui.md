# SDXL and ComfyUI Adapter

Use this adapter only for an active SDXL-lineage checkpoint, including the tag-trained derivative families, or a ComfyUI graph whose loaded model has a declared record, local or hosted. Complete [Image Generation Runtime](../runtime/image-generation.md) first.

## Prompt and negative rendition

Read the [Prompt Writing Guide Runtime](../runtime/prompt-writing-guide.md) after selecting the exact checkpoint and workflow. When a `prompt-writing-guide` provider is selected, apply its tag ordering, prompt-pressure, attention, LoRA, negative, embedding, and controlled-comparison rules only where the active parser and graph support them.

Use a focused positive prompt that preserves the selected art direction, subject relationships, and construction. When the active record carries recommended positive or negative prompts, adopt them as the quality block and the base negative and build on top of them. Local checkpoints and LoRAs may need evidence-backed vocabulary adaptation; the concept and medium stay as chosen.

When the loaded model's record declares a tag-trained lineage, render the master as comma-separated tags in the record's declared vocabulary, in this order:

- a leading quality block
- identity
- body
- palette and marking zones
- expression
- pose
- view
- environment
- finish

Translation is a rendition of the master prose, never a paste of it, and the census clauses must survive it. Expect these families to add unrequested cultural furniture, such as emphasis marks, drawn borders, and register-typical props, and negate what the picture forbids.

An image-to-image seed on these families locks the pose together with the individual; pose-change tags lose against it, and only state details pass through. To move a character to a new pose, use the [Character Repose Workflow](../runtime/character-repose-workflow.md) rather than raising strength.

## Sampling behavior

These are properties of the lineage, whatever the interface. The record and the platform decide which of them a request may set. The [Prompt Writing Guide Runtime](../runtime/prompt-writing-guide.md) owns the prompt-side rules.

**CLIP skip.** The conditioning comes from one chosen hidden layer of the text encoder. This lineage is trained on the penultimate layer, and its tag-trained derivatives keep that assumption; a platform exposes the choice as clip skip or a layer index. It changes how literally tags are read while the prompt stays the same, so check it first when tag response shifts unexpectedly.

**Token spans.** Each text encoder has a fixed context of 77 tokens. Two are the start and end markers, so one encoding pass conditions on about 75 tokens of prompt. The interface, rather than the checkpoint, decides what happens to a longer prompt. Some truncate at the limit and drop the tail. Others cut the prompt into pieces, encode each with its own markers, and concatenate the results; a phrase straddling a cut is then encoded as two fragments, and a color can bind to the wrong part. `BREAK` and its equivalents place that cut deliberately. Before writing past one window, test the active interface: put one tag past the window that nothing else in the prompt would draw, generate, and see whether it appears. A platform may also gate the long-prompt path behind a flag documented for something else, such as a prompt-weighting mode; a prompt sent without that flag is silently cut. Keep words that must bind together adjacent, and put the terms that matter first in a negative list. Treat the tail of a long prompt as unreliable.

**CFG scale.** Classifier-free guidance conditions each step on the prompt and on the negative text, and moves away from the second. Above the band a checkpoint was tuned for, guidance hardens edges and burns color; the tag-trained derivatives are usually tuned low.

**Sampler and steps.** Ancestral and other stochastic samplers add noise as they run, so the picture keeps changing as the step count changes; deterministic samplers settle and stop moving past a point. A sampler is therefore a creative choice rather than a neutral setting carried between runs.

**Seed.** A seed reproduces a rendering when model, prompt, size, sampler, steps and CFG scale are identical. It carries no identity: once the prompt changes, the same seed returns a different individual.

**Denoising strength.** An image-to-image pass redoes the last fraction of the trajectory named by strength. It inherits the rest from the input. Low values restyle a picture that already holds its composition; middle values redraw shapes and faces; high values decide the picture again. Small features go first. A marking or a thin brow occupies few pixels, so it is re-decided from the prompt rather than read from the input.

**Two-pass enlargement.** Composition breaks above the trained resolution of roughly one megapixel. Bodies repeat and heads duplicate. The trained buckets are multiples of 64 around one megapixel (1024x1024, 896x1152, 832x1216, 768x1344, 640x1536 and their transposes). For another ratio, keep the pixel count near one megapixel with both sides multiples of 8. The hires-fix pattern reaches a larger frame in two steps: render inside the trained size, enlarge, then run a low-strength image-to-image pass over the enlargement. Refining the enlargement as overlapping tiles adds detail but conditions each tile separately, so a feature that must match across the picture can drift between tiles. A dedicated upscaler model is a separate operation with its own contract.

**Inpainting.** A masked pass leaves the unmasked pixels untouched. Two settings decide the result: what the masked area starts from (the original pixels, a fill, or fresh noise), and whether the region is processed in the whole frame or cropped out and rendered alone. Cropped, a small region receives the model's full working resolution, so a face of a few hundred pixels comes back with detail a whole-frame pass lacks. The masked part is still redrawn from the prompt, so it needs the same identity evidence as a full render. Mask padding and a blurred mask edge hide the seam.

**Reference image, seed image, ControlNet, IP-Adapter.** Three mechanisms carry an existing appearance into a new image on this lineage. Each preserves something different.

| Mechanism | Preserves | Does not preserve |
|---|---|---|
| img2img seed image | appearance and pose together, below the denoising strength at which the pose could change | either, above that strength: the face changes first |
| ControlNet guide (Canny, Depth, OpenPose) | pose, reliably | appearance; alongside a seed image at low denoising strength it has no visible effect at any weight or control mode |
| IP-Adapter | a general style at best | a face; on the tag-trained derivatives it often shifts color first |

An image that needs both a known face and a new pose is therefore out of reach for a denoising strength, which only selects which of the two is lost. Use a trained LoRA, or a second model that accepts reference images and can be prompted for a different angle.

**Fragile parts and scale.** What this lineage draws worst is countable and small. That means fingers, toes, teeth, the links of a chain, the mesh of a net, lettering, and reflections. The error is drawn at whatever size the part occupies, so scale decides whether it matters. A hand across a wide shot is a few pixels of suggestion; the same hand in a close insert is the subject, and every wrong digit is visible. Two hands meeting on one object at close scale fails most often. Ask for such a part large only when the picture is about it, and then give it the frame to itself. Where the part is incidental, leave it out of the text so the framing can leave it out of the picture. The repair is a second pass over a mask rather than a longer prompt.

**Resolution buckets.** Training uses a set of width and height pairs. A size far from those pairs stretches anatomy and repeats elements, and an unusual aspect shows it first in faces and hands. Choose a trained pair and crop afterwards.

Structural conditioning varies by host: hosting platforms gate adapters by architecture, and a derivative family may lack any ControlNet or identity-adapter. Confirm availability from the platform inventory before planning a structural channel. When none exists, say so rather than substituting an image-to-image seed for a structural guide.

Send the complete verified negative prompt through separate conditioning. Use `separate-field` only when the loaded model and graph expose that channel. ComfyUI itself is a workflow host; the model record is the authority on behavior.

## Reference forwarding

Use the loaded model's catalog record for accepted media and reference behavior, or an explicit reviewed workflow transport. Forward only verified carriers and parameters. Stop when the graph is unable to accept the complete planned reference set, or when its negative transport is uncharacterized.

When designing or auditing a ComfyUI-specific node or chained partial-construction workflow, read [ComfyUI Integration Notes](../comfyui-integration-notes.md). Prompting an existing characterized graph leaves that product-design provenance note unloaded.

## Provider-backed recommendations

Apply only recommendations declared by the resolved model record, using its merge mode and provenance. User-authored semantic text is kept in full rather than truncated to make room.
