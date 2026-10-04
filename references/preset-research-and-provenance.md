# Preset Research and Provenance

## Purpose

The catalog collects reusable visual production knowledge for original character and subject imagery. It supports humans, anthropomorphic animals, ordinary animals, creatures, hybrids, and robots.

## Sources of knowledge

Production knowledge may be developed from:

- user-supplied reference images
- public documentation for image-generation systems
- visual taxonomies and tag systems used for discovery
- anatomy, photography, costume, material, animation, illustration, design, and cinematography references
- independently authored production examples and evaluations

Packs do not redistribute third-party prompt databases or source code. When source-backed visual evidence is requested, CPB stores derived path SVG and JSON artifacts without embedding or externally referencing the source raster. Signatures, logos, franchise identifiers, censor overlays, and source-specific text are never promoted into reusable canonical preset knowledge.

## Reference-derived aesthetic work

The initial aesthetic corpus was derived from development references supplied in conversation. Those references were largely anthropomorphic character illustrations. Their recurring knowledge was separated into:

- universal aesthetic cores for cross-domain appeal and visual taste
- anthropomorphic domain realization and surface modules
- shared and domain-specific aesthetic-touch modules
- render profiles, scenes, corrections, and archetypes where appropriate

This separation prevents one source domain from becoming the assumed form of all subjects.

## Adding material from other domains

Future human, ordinary-animal, creature, hybrid, and robot references should be reviewed for recurring production decisions.

Use this classification:

```text
cross-domain appeal, hierarchy, viewer relationship, shape, light, or finish
→ universal aesthetic core

one domain's anatomy, behavior, expression, surface, locomotion, or contact
→ domain realization or domain-specific aesthetic-touch module

medium mechanics
→ render profile

spatial staging
→ base scene

one isolated craft choice
→ atomic module
```

Aesthetic cores are not produced by deleting nouns from a domain-specific description. They are manually rewritten around genuinely transferable visual principles.

## Tag and taxonomy research

Tag systems can improve vocabulary coverage and retrieval, but tags are discovery evidence rather than complete production direction. Imported terms should be normalized into current canonical records, reviewed for domain and scope, and stored as vocabulary unless full curated production knowledge is authored.

## Provenance fields

`cpb-resource:provenance` stores the binding pack's source categories, licensing notes, curation notes, and current counts. It does not claim ownership of external source material. When no enabled pack binds it, no provenance resource is implied.

## Review standard

All curated additions follow `references/preset-authoring-standard.md`. Important new retrieval behavior receives regression cases. Important creative behavior receives blind-evaluation cases.
