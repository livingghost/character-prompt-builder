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

Resolve the layers relevant to each depicted scope. A fixed choice is an
anchor; an open choice follows the selected production direction. Flat graphics
and lettering can be complete without a physical camera or lighting setup.

1. Medium grammar describes the marks and surfaces of a treatment: flat cel, watercolor, photograph, 3D render, clay, pixel art, or another authored treatment. Apply it at its selected scope through the [render intent](runtime/render-contract.md). Mixed treatments need defined relationships and boundaries, including deliberate transitions or material combinations within one subject.
2. Optical system is how the frame sees. It covers focal behavior (telephoto compression, wide-angle stretch, fisheye), focus falloff (depth of field, blurry foreground or background), exposure character (overexposure, film grain, halation, chromatic aberration), and lens-era cues (film stock looks, analog artifacts).
3. Light architecture is the physical arrangement: source count, direction, size, and color; named setups when photographic (three-point, Rembrandt, butterfly, split, rim); environment behavior when scenic (golden hour, blue hour, overcast, volumetric fog, crepuscular rays). Light architecture is physical; the medium grammar decides how it is drawn.
4. Material response is how surfaces answer the light within the chosen medium: PBR separation for 3D, glistening or wet highlights, subsurface warmth, metallic versus matte versus translucent, toy-surface smoothness, fabric weave. A material term that contradicts the medium (photoreal skin pores on a vinyl figure) is a layer conflict to resolve rather than to stack.
5. Presentation finish realizes the construction selected in Production direction. It covers the treatment of backgrounds, borders, lettering, diagrams and other components, plus relevant post effects. A form's familiar furniture is used only where it serves the intended content and hierarchy.

## 3. Composition order

Choose presentation and component relationships through
[Production direction](runtime/production-direction.md) before refining their
finish. Within each treatment, resolve medium, relevant optics and light,
material response and finishing detail together. A selected style family or
profile contributes within that scope. Preserve both local coherence and the
chosen relationship between different treatments.

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
