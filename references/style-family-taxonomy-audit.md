# Style-Family Taxonomy Audit Contract

## Required evidence matrix

For every family, evaluate recurring behavior on all eight axes:

| axis | required question |
|---|---|
| line | Is contour hierarchy or edge treatment recognizably different? |
| form | Is mass modeled, flattened, faceted, rounded, or cut out differently? |
| shadow and value | Is value grouping or shadow topology distinct? |
| highlight | Is highlight placement, hardness, or density distinct? |
| color | Is palette structure distinct beyond one scene's illumination? |
| surface | Is texture or polish behavior distinct beyond temporary wetness or wear? |
| background | Does background treatment recur independently of one location? |
| detail hierarchy | Is attention allocated in a repeatable, transferable way? |

## Boundary tests

1. Scene-leakage test: remove subject, species, body build, clothing, camera, location, props, relationship, text, and temporary effects. The remaining grammar must still be coherent.
2. Cross-scene transfer test: apply the grammar to materially different scenes. A family that collapses outside one setup is scene knowledge.
3. Nearest-family boundary test: name the closest canonical family and state the durable difference.
4. Decomposition test: prefer an existing family plus scene or atomic modules when that composition explains the evidence completely.

## Family record fields

Each style-family record carries its review:

- `status`: `retained`, `revised-and-generalized` or `new`.
- `evidence_basis`: scenes showing the finish; a revised or new family lists three or more.
- `recurring_axes`: six or more of the eight axes.
- `excluded_scene_attributes`: two or more attributes kept out of the grammar.
- `nearest_family` and `boundary`: the closest other family, in any enabled pack, and the durable difference.
- `review_notes`: eight or more words for a revised or new family.
- `deferred_candidates`: proposals compared with this family and kept out of the catalog.

`scripts/style_family_audit.py` applies these rules across every enabled pack's families. After changing a family, run `scripts/pack_release_gate.py` on the released pack and its dependencies. Structural success confirms ID and schema integrity; artistic justification rests on the recorded evidence and boundary tests.
