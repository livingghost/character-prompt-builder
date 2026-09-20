# Finishing Layers Specification

## 1. Purpose

A correct subject leaves a character prompt unfinished. The same subject reads completely differently as a cel illustration, an 85mm photograph, a matte clay render, or a collectible figure shot. This reference defines the finishing layers that turn a correct subject into a complete image, and the observation contract for reading them from evidence.

Load this document when a delivered prompt keeps producing the right subject in the wrong finish, or when the request names or implies any of these:

- a rendering medium
- a photographic look
- a 3D or toy presentation
- type or logo elements inside the image
- an environment-forward composition

## 2. The five finishing layers

Every complete image resolves all five layers, explicitly or by default. An unstated layer is an open creative choice; a stated one is an anchor.

1. Medium grammar is what the image physically pretends to be: flat cel, painterly, watercolor, photograph, 3D render, clay sculpt, vinyl figure, pixel art. One image, one dominant medium. Mixed grammars need an explicit boundary; a painted character over a photographic backdrop is a stated design rather than a drift.
2. Optical system is how the frame sees. It covers focal behavior (telephoto compression, wide-angle stretch, fisheye), focus falloff (depth of field, blurry foreground or background), exposure character (overexposure, film grain, halation, chromatic aberration), and lens-era cues (film stock looks, analog artifacts).
3. Light architecture is the physical arrangement: source count, direction, size, and color; named setups when photographic (three-point, Rembrandt, butterfly, split, rim); environment behavior when scenic (golden hour, blue hour, overcast, volumetric fog, crepuscular rays). Light architecture is physical; the medium grammar decides how it is drawn.
4. Material response is how surfaces answer the light within the chosen medium: PBR separation for 3D, glistening or wet highlights, subsurface warmth, metallic versus matte versus translucent, toy-surface smoothness, fabric weave. A material term that contradicts the medium (photoreal skin pores on a vinyl figure) is a layer conflict to resolve rather than to stack.
5. Presentation finish is the packaging of the whole frame. It covers backdrop treatment (solid color, gradient, detailed environment), post effects (bloom, vignette, color grading), border and composition furniture, and display idioms (product shot, blind-box presentation, reference sheet, poster layout with text zones).

## 3. Composition order

Resolve the layers top-down after the subject and scene are fixed: medium first, because it constrains everything below; then optics; then light; then materials; then presentation. When a selected style family or render profile already owns a layer, that record is the authority, and prompt text restates nothing that conflicts with it.

During prompt assembly, run one vocabulary lookup per resolved layer (see the Prompt Vocabulary Runtime). The dictionary carries dedicated categories for typography and logo design, landscape and atmosphere, photography parameters, illustration technique, 3D rendering and materials, and toy and figure finish. Catalog modules exist for the recurring layer choices (rendering, lens, lighting, aesthetic-touch categories); search them before hand-composing a layer.

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
