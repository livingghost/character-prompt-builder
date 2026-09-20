# Distinctive Detail Specification

Distinctive details are identity-scale features whose exact placement and construction matter. They include scars, healed cuts, tattoos, birthmarks, freckles, wrinkles, calluses, paw pads, claws, chipped tips, ear notches, broken horns, asymmetrical markings, piercings, missing fur, worn casing, dents, seams, and comparable features.

This specification keeps a detail from collapsing into a vague tag such as `scarred` or `tattooed`. Record only what can be stated from the user brief, a clear reference, a selected preset, or a user-confirmed inference. Hidden continuation behind clothing, hair, fur, crop, or another body part remains unspecified.

## Extraction order

Describe each detail in this order.

1. Feature type: the physical class, such as pigment marking, scar, depression, raised tissue, notch, missing segment, chipped hard surface, tattoo, wrinkle cluster, callus, piercing, wear, or material damage.
2. Subject-relative location: the subject's left and right, never the viewer's, plus the body region and a local anatomical or mechanical landmark. Example: `subject's right cheek, beginning one eye-width below the outer eye corner`.
3. Landmark relation: where the feature begins, ends, or sits relative to stable landmarks such as the eye corner, nostril, ear base, shoulder cap, elbow crease, claw base, horn ring, panel seam, or joint axis.
4. Count and distribution: an exact count when the reference is clear, otherwise bounded language such as `three to five sparse marks`, `one compact cluster`, or `distributed across the outer forearm`.
5. Relative size: measured against the local region rather than pixels. Useful forms include `one quarter of the ear height`, `about one iris diameter`, `spanning half the shoulder cap`, or `covering roughly ten percent of the visible forearm`.
6. Shape and path: straight, curved, branching, crescent, banded, irregular, triangular, puncture-like, or clustered geometry. For a linear feature, state the start, end, and path.
7. Orientation: relative to the anatomical axis, such as vertical, horizontal, diagonal, circumferential, radial, following the muscle fiber, following a scale row, or crossing a seam.
8. Color and value relationship: relative color language such as `two values darker than the local fur`, `desaturated pink against pale skin`, or `cool charcoal ink`. Use an exact color only when the user supplies it.
9. Depth and relief: a physical category such as flat pigment, shallow discoloration, shallow depression, raised line, thickened callus, deep notch, chipped edge, missing segment, engraved groove, or inset component.
10. Edge and texture: crisp, feathered, healed, ragged, smooth, cracked, glossy, matte, fibrous, scaly, or worn edges.
11. Surface interaction: how the feature affects the surrounding material. Fur parts around a scar, a tattoo follows skin curvature, a notch interrupts the ear silhouette, a chip shortens one claw, or a dent bends a robot panel highlight.
12. Age or condition: fresh, healing, healed, faded, weathered, polished by use, callused, recently chipped, or old and softened.
13. Visibility and occlusion: the camera or pose conditions required for visibility. Example: `visible in three-quarter left views; partly covered by the collar in frontal views`.
14. Identity priority: `signature` for identity-defining details, `supporting` for stable secondary features, and `optional` for scene-dependent decoration.
15. Source confidence: explicit user input, clearly observed reference evidence, approximate reference evidence, a selected preset, or user-confirmed. Ask one focused question when an identity-critical detail is ambiguous.

## Scale guidance

Use relative anchors rather than invented precision. These bands are descriptive aids rather than mandatory labels:

- pinpoint: under about 2% of the local region
- small: about 2-5%
- medium: about 5-15%
- large: about 15-30%
- dominant: over about 30%

A linear feature also states length and width separately. A scar may be long but narrow, and a tattoo broad but shallow.

## Prompt-facing rule

Write the visible target affirmatively. Example: `a healed narrow diagonal scar crosses the subject's right eyebrow and ends above the outer eye corner`. Store nearby failures in diagnostic fields rather than in the positive prompt.

## Reuse and locking

A production specification may include several distinctive details per subject. A series lock preserves signature and supporting details with the same subject-relative location, laterality, size relationship, shape, color relationship, depth, and visibility rules. Scene lighting may change their apparent value; their location and size stay locked.

## Storage locations

- reusable curated examples: enabled `module` records in category `distinctive-detail`
- per-image or per-series structured records: `subjects[].distinctive_details` in the production specification
- reusable blank record: `templates/distinctive-detail-template.json`
- structural validation: `schemas/distinctive-detail.schema.json`

## Corpus-derived observation guide

Read `references/reference-corpus-detail-observation.md` for corpus-derived guidance. It covers feature-class-specific anchors, style-normalization tests, confidence thresholds, and transient-versus-stable classification derived from the retained reference corpus. Use `templates/distinctive-detail-observation-template.json` before creating or locking a new record from images.
