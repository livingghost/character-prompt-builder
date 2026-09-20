# Model Prompt Recommendation Contract

Verified: 2026-08-25

## Admission rule

A reusable model recommendation is committed only when a model publisher or identifiable model creator provides reusable prompt text or a named provider preset for that exact model or revision. Examples, generic prompting advice, and community folklore stay out of the defaults. User-authored semantic text remains authoritative and keeps its full length whatever room a recommendation needs.

## Core-owned model decision

The core release evaluates only the model records owned by `packs/commons`.

| Pack | Model record | Decision | Rationale |
|---|---|---|---|
| `commons` | `gpt-image-2.5-flare` (OpenAI GPT Image 2.5 Flare) | No fixed reusable default adopted | Model guidance is task-specific; the core does not commit one universal positive or negative string. |
| `commons` | `grok-imagine-image-2.0` (xAI Grok Imagine Image 2.0) | No fixed reusable default adopted | Model guidance is task-specific; the core does not commit one universal positive or negative string. |

## Nondefault-pack boundary

Model records in user-owned or third-party packs belong to those packs. Their IDs, aliases, provider limits, prompt recommendations, negative presets, provenance, and inventory stay out of this core reference and out of core regression fixtures.

When a non-bundled pack is explicitly enabled, runtime behavior comes from that pack's validated model record. The record itself must carry any admitted recommendation and its provenance. The core stays as it is when an owner changes, adds, or removes a model in a separate pack.

Core model-contract tests therefore use:

- the package-owned default model record for integration coverage; and
- synthetic in-memory records for transport modes, limits, upscaler classes, recommendation merging, and rejection cases.

A user-owned pack stays unread by them, contributes nothing to an expected model count, and lends none of its model IDs as test fixtures.

## Maintenance rule

Before publishing a core release, verify that:

1. core documentation leaves the current contents of a non-bundled pack unenumerated;
2. core tests pass with only `packs/commons` present;
3. tests that need additional models create synthetic fixtures in a temporary directory or in memory;
4. full-package construction may preserve and validate explicitly included packs while keeping their contents out of core defaults and expected test data.
