# Declared Structures Runtime

## Activation and authority

Use this workflow when authoring or revising a growth, frame, terminal, garment or topology contract, especially when a specialized example fails to fit. It applies equally to familiar and unfamiliar designs; a structural record is optional for a short prompt draft.

The user anchors and the currently adopted design decide; examples are open-ended. A head, face, digits, paired limbs, skeletal tissue or clothing panels come from a declaration rather than from a species, material, category or template. An agent may propose a coherent new construction within creative latitude; the author decides whether it becomes canon, and a local edit keeps its local scope.

## Authoring form

Growth, terminal, frame and garment contracts use `representation: "declared-structures"`. Their `structures` object is keyed by stable author-owned IDs, and each entry supplies:

- an open-vocabulary `kind`;
- an explicit `location`;
- `presence`;
- a `geometry` object whose named properties contain authored text.

Names and materials are open vocabulary too.

An empty map means this contract declares nothing, which is different from declaring every part absent. `presence: "absent"` is an explicit negative assertion and `unknown` preserves uncertainty; both use an empty geometry with zero geometry claims, while `present` and `partial` need at least one actual geometry property. Omission leaves canon unchanged: a local edit still compares against the adopted baseline, and dummy records for inapplicable parts are unnecessary.

Use `parent_id` for containment, `attachment_ids` for explicit connections and `overrides` for local exceptions. IDs refer to entries in the same map; an external carrier is named in `location` rather than duplicated locally. An override names its target ID and the exact geometry properties that differ; both structures keep their own values, the local one beside the global one. Validation fails on:

- missing references;
- self references;
- containment cycles;
- override cycles;
- repeated rules;
- overrides of undeclared properties.

Physical attachment rings are allowed. Overlap described in natural language remains the agent's responsibility: resolve overlapping regions explicitly rather than averaging them silently.

Detailed construction uses the same `geometry` map: name the properties this design needs, such as a section boundary, edge curvature, support seam, material transition or other authored detail. No anatomical helper or separate specialist contract is selected, and a property named in one example stays optional for other structures.

## Execute and inspect

Resolve paths relative to the installed `SKILL.md` directory. These local contract checks run on the installed skill alone; pack activation is unnecessary for them.

```bash
python scripts/structure_contract.py --help
python scripts/structure_contract.py validate templates/growth-geometry-template.json --kind growth-geometry
python scripts/structure_contract.py inspect examples/declared-structures/lattice-growth.json --kind growth-geometry
python scripts/validate_prompt_semantics.py examples/declared-structures/asymmetric-topology.json
python scripts/structure_neutrality_smoke_test.py
```

Input is one JSON contract and a declared kind. `validate` prints `ok` and `errors`; `inspect` also returns a detached read view with source pointers and the full unchanged source contract. Both return nonzero on invalid data and only read: they write nothing, call no API and create no approval. Duplicate JSON keys, invalid types and unknown fields fail rather than being silently discarded. The regression suite covers schemas, references, authorization, search scope and document examples.

## Semantic plan

For preflight plans use `structure_plan.expected_counts`, `assigned_structures` and `primary_actions`; components and actions use `structure_id`. Kinds, sides and owners are declared rather than guessed. Counts are total upper bounds across the declared inventory rather than a visibility obligation or a reason to invent hidden parts; optional `expected_by_owner` and `side_limits` impose only the specified limits. Duplicate IDs, excessive counts, invalid references and incompatible actions still fail. Sides come from declarations; a total of two is insufficient reason for a left/right rule.

## Generation, references and edits

Identity, morphology, production, asset-render and state graph checks all use the same schemas. Growth resolution keeps exact approvals and JSON-pointer grants. A color grant can name `/stable_identity/growth_geometry/structures/edge-filaments/geometry/color`; it does not authorize another part, a topology or a rewrite of the grants.

State annotations describe current conditions separately. Occlusion changes what to render while what exists stays as declared. Translate local geometry to locally scoped prompt wording. A format or schema check proves the record's shape and leaves prose and generated pixels unproven.

An identity supplies explicit `reference_views` when building a reusable reference bundle. Each keyed view declares `view`, `framing`, `coverage_tokens` and a complete camera contract, chosen against actual coverage needs; the planner adds none, including head, bust and paired-limb views. Missing view declarations block that branch with an actionable error while a prompt-only draft proceeds.

Individual measurements may use `structure_measurements`; head and limb ratios are optional there. A lineage records its authored cross-structure constraints in `structure_coherence_rule`. Morphology starters contain an explicitly replaceable carrier specimen, a starting point rather than an approved default or a mandatory organ inventory.

Growth authoring details are in [Growth Geometry Specification](../growth-geometry-specification.md); frame and morphology ownership remain in [Morphology and Species Contracts](../morphology-and-species-contracts.md).
