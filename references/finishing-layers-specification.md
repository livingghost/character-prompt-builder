# Finishing Layers Specification

## 1. Purpose

A subject can generate different pictures through its visual construction.
This reference supplies knowledge for choosing that construction while an
image is conceived, and for resolving or observing its treatment. These layers
are not a cosmetic pass after the subject and scene have already determined
the picture. Use them within the conception study and selected direction.

Load this document when an open visual treatment needs construction knowledge,
when a delivered prompt keeps producing the right subject in the wrong finish,
or when the request names or implies any of these:

- a rendering medium
- a photographic look
- a 3D or toy presentation
- type or logo elements inside the image
- an environment-forward composition

## 2. The five finishing layers

Resolve the layers relevant to each depicted scope. A fixed choice is an
anchor; an open choice follows the selected production direction. Flat graphics
and lettering can be complete without a physical camera or lighting setup.

1. Medium grammar describes the marks and surfaces of a treatment: flat cel, watercolor, photograph, 3D render, clay, pixel art, or another authored treatment. Apply it at its selected scope through the [render intent](runtime/render-contract.md). Mixed treatments need defined relationships and boundaries, including deliberate transitions or material combinations within one subject.
2. Optical system is how the frame sees. It covers focal behavior (telephoto compression, wide-angle stretch, fisheye), focus falloff (depth of field, blurry foreground or background), exposure character (overexposure, film grain, halation, chromatic aberration), and lens-era cues (film stock looks, analog artifacts).
3. Light architecture is the physical arrangement: source count, direction, size, and color; named setups when photographic (three-point, Rembrandt, butterfly, split, rim); environment behavior when scenic (golden hour, blue hour, overcast, volumetric fog, crepuscular rays). Light architecture is physical; the medium grammar decides how it is drawn.
4. Material response is how surfaces answer the light within the chosen medium: PBR separation for 3D, glistening or wet highlights, subsurface warmth, metallic versus matte versus translucent, toy-surface smoothness, fabric weave. A material term that contradicts the medium (photoreal skin pores on a vinyl figure) is a layer conflict to resolve rather than to stack.
5. Presentation finish realizes the construction selected in Production direction. It covers the treatment of backgrounds, borders, lettering, diagrams and other components, plus relevant post effects. A form's familiar furniture is used only where it serves the intended content and hierarchy.

## 3. Composition order

Develop presentation, component relationships and visual treatment together
through [Production direction](runtime/production-direction.md). A particular
optical relationship, light behavior or material construction can originate an
idea as well as realize it. Compare actual candidate pictures before selecting
the direction, then resolve the relevant layers coherently. A selected family
or profile contributes within its assigned scope. Preserve both local coherence
and the chosen relationship between different treatments.

Investigate unresolved construction or wording questions under
[Prompt-only Core](runtime/prompt-only-core.md#knowledge-and-sources). A brief,
reference or selected style family may already resolve a layer. Descriptive and
portable wording needs a search only where a question remains. Choose the
source that can answer it and inspect complete selected records at their
applicable scope.

The dictionary carries dedicated categories for typography and logo design,
landscape and atmosphere, photography parameters, illustration technique, 3D
rendering and materials, and toy and figure finish. Catalog modules cover
recurring layer choices in rendering, lens, lighting and aesthetic-touch
categories. Use these resources according to the actual question; each layer
need not use both systems or have its own query. Preserve the selected finish's
necessary detail when composing its wording.

The selected model's `prompt_input` separately governs rendition. A `tag-based`
input requires real [dictionary search and vocabulary selection](runtime/prompt-vocabulary.md#select-wording-for-a-tag-based-model)
for the actual prompt, even when its finishing choices and intended terms are
already understood. Record actual investigations under
[Saved prompt artifacts](runtime/prompt-only-core.md#saved-prompt-artifacts).
A layer's presence alone requires no retrieval entry.

## 4. Observation contract

When reading finishing layers from a reference image or SVG evidence, record per layer:

- the observed behavior, in the layer's own vocabulary;
- whether it is load-bearing for the request or incidental to the source;
- which layer owns each visible effect: wet highlights belong to material response rather than lighting, and a vignette belongs to presentation rather than optics;
- conflicts between source layers and the requested medium, resolved explicitly (preserve, rescope, or replace) rather than averaged.

A source's finishing layers stay out of subject identity. A character observed in one photograph remains open to every other finish.

## 5. Layer-specific cautions

- Type and logo elements: text inside an image is a designed object with its own letterform, weight, material, and effect vocabulary. Distinguish requested text (an anchor, described precisely: lettering style, finish, placement) from generation-hygiene text (watermarks and stray signatures, excluded by the negative policy). Models vary sharply in text fidelity; on weak-text targets, prefer fewer, larger, simpler words and say so in the delivery notes.
- Environment-forward frames: when the environment is the subject or co-subject, give it the same layered treatment as a character rather than a single location noun. That means depth planes (foreground interest, mid-ground, background), sky and weather behavior, and atmospheric perspective.
- Renderer names (octane, specific engines): on most targets these are style cues rather than literal renderer selection. Use them for the look they connote, and prefer describing the actual visible qualities (soft edges, ambient occlusion, display lighting) alongside or instead of the name.
- Quality-tag stacks: quality vocabulary belongs to the target interface's convention (see the model adapter) rather than to the finishing layers. A quality stack resolves none of the five layers.
