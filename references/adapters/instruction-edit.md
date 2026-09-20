# Instruction-Edit Adapter

## Purpose

Use this adapter for image models that transform one or more supplied images from a natural-language edit instruction. The adapter governs change scope, preservation clauses, identity consistency, and edit intent. Transport channels remain model-record capabilities and are not inferred from the adapter family.

## Instruction construction

Read the [Prompt Writing Guide Runtime](../runtime/prompt-writing-guide.md) before final rendition. Apply its interface-neutral hierarchy and visible-scope rules to the edit instruction, but do not import Stable Diffusion attention syntax, LoRA calls, embedding tokens, or tag formatting unless the exact active model record supports them.

1. Open with the requested change and the affected subject or region.
2. State what must remain unchanged, especially permanent identity, body construction, markings, clothing continuity, camera, and background elements outside the change scope.
3. Describe the desired visible result affirmatively.
4. Keep presentation state such as pose, expression, gaze, wind, wetness, and temporary styling outside permanent identity unless the request explicitly fixes it.
5. Respect the active model record's `max_reference_images`, prompt-character limits, supported resolutions, output count, and aspect behavior.

## Negative transport

Read `negative_transport_mode` from the active model record. Some instruction-edit models expose only one prose field and therefore use `integrated-critical`; others, including records that declare a separate negative field, use `separate-field`. Never discard the portable negative merely because the editing adapter is prose-oriented. Merge only provider-backed recommendations recorded with provenance, and never truncate the user-authored semantic instruction to make room for a recommendation.

## Reference handling

Preserve source order and role. A model-specific reference limit is a hard gate in planning, preparation, packaging, and verification. Do not silently drop an excess reference or substitute another artifact.
