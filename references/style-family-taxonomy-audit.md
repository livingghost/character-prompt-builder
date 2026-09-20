# Style-Family Taxonomy Audit Contract

This contract defines the evidence and boundary review for concrete style families. Pack-specific family decisions, release histories, and canonical IDs belong in a resource owned by the pack being audited.

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

## Pack-owned audit resource

When the selected pack state provides `cpb-resource:style-family-taxonomy-audit`, resolve it from the explicitly selected provider. Record accepted and rejected family decisions there using exact current IDs, evidence sets, excluded content, and nearest-family comparisons. The audit must agree with the provider's machine-readable taxonomy and catalog.

Validate a released pack through its exact one-pack
`scripts/pack_release_gate.py` invocation after changing a family. Use
`scripts/style_family_audit.py` only as a focused development diagnostic with
the same explicit pack runtime. Structural success confirms ID and
schema integrity; artistic justification still depends on the recorded
evidence and boundary tests.
