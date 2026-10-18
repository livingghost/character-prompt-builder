# Exact reference delivery

Read this when preparing or inspecting model-facing reference attachments. Package dispatch uses one committed prepared reference set.
External instruction edits use the original-file mapping in [Semantic instruction editing](semantic-instruction-edit.md).
Both paths retain each source's bytes, order and authority; their transport artifacts are not interchangeable.

## Selection and authority

Retrieve applicable production knowledge and inspect each selected source before preparing it. Decide what the source may control, what it must leave alone, and why this request needs it. Choose only task-relevant sources rather than filling an arbitrary count. A model's observed attachment limit is an execution constraint, unlike a fixed aesthetic reference quota.

Identity, current expression, wardrobe, lighting, pose and camera are different scopes; a transient state propagates only when requested, whatever identity the source shows. Express each source's `controls` and `must_not_control` authority scopes explicitly. Identical positive and excluded scopes are contradictory and rejected. The script leaves synonyms and semantic conflicts to the agent, who resolves them against the actual source and current intent.

For supplied files in an instruction edit, use `prepare_generation_references.py
--semantic-edit-plan-file PLAN --studio STUDIO` with output paths under
[Semantic instruction editing](semantic-instruction-edit.md#prepare-supplied-references-for-dispatch).
This path derives exact scopes from the authored plan. Ordinary supplied
selections retain conservative role authority; state and pack sources retain
their own scope owners.

The ordinary supplied-selection input is an ordered JSON array with exactly
`role` and `source` per item. A synthetic example:

```json
[{"role": "scene", "source": {"kind": "supplied-file", "reference_id": "scene",
  "resolved_path": "/absolute/studio/inputs/product-scene.png"}}]
```

The preparer measures media type and hashes; omit those fields from this input.
For exact edit scopes, author `use_for` and `do_not_transfer` in the semantic
plan instead. An empty declared exclusion array remains empty in that path.

## Bind the actual transport

The following prepared-set commands apply to reference-runtime and Generation Package delivery.
An external semantic request uses its declared field paths and upload evidence instead.

After rendering or copying the actual transports, the reference preparation runtime derives the canonical prompt preamble from their actual order. For multi-image input, logical reference 1 corresponds to actual attachment 1. For a single-board input, every logical reference points to attachment 1 and its exact panel rectangle in pixels from the top-left, and a board with several source panels consumes one model image slot in total. Source hashes, transport hashes, roles and panel rectangles must agree with the prepared set.

The map and its prompt text are generated only after those transports exist. Do not retain an earlier numbering scheme, hand-rewrite the canonical preamble, or tell a model to use attachment 2 when only a board is attached. The board instruction distinguishes source panels from desired output composition and requests a collage only when the author's target does.

```sh
python scripts/reference_delivery.py --prepared-set prepared.json --package-root WORK
```

This inspection validates the complete prepared set and shows its attachment mapping and canonical instruction; it submits and mutates nothing. Normal preparation uses the same functions through `prepare_generation_references.py` and `reference_runtime.py`; the map is part of the exact preamble bound into generation packaging rather than an operator report alone.

For prompt-artifacts, SVG-bundle, or no-reference delivery, never claim that model-visible attachments were sent. An unsupported target or missing selected transport is an explicit failure rather than silent reference omission. Targets and their observed limits are resolved from actual model records rather than fixed service names in this procedure.

Run `python scripts/reference_delivery_smoke_test.py` and the existing reference runtime tests. They test mappings and transport contracts, not whether a generator actually follows them.
