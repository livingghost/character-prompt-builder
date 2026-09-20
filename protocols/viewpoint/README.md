# Series Viewpoint Protocol

This public protocol separates camera ownership, narrative focalization, point of
audition, shot geometry, visible obligations and viewpoint transitions. Its
[registry](../contract-manifest.json) and [semantic rules](../semantics.md) are
shared; the sending and receiving projects remain independent.

## Public artifacts

| Artifact | Responsibility |
|---|---|
| viewpoint-profile | A declared camera and continuity grammar. Bundled profiles are optional presets. |
| scene-viewpoint-plan | A scene's selected defaults and ordered shot references. |
| shot-camera-spec | Position, movement, axis, eyeline, crop, ownership, visibility and anchors. |
| viewpoint-transition | An editorial bridge with explicit trigger and continuity requirements. |
| shot-continuity-ledger | Derived shot/transition commitments and unresolved continuity. |
| shot-visual-projection | Identity, state, relationships and environment actually expressed in the shot. |
| shot-request | A neutral request for a frame, reference or production prompt, with exact artifact commitments. |

There is no mandatory global protagonist or viewpoint in this contract. A project
may choose external aligned third person, objective external, over-the-shoulder,
embodied first person, device first person or fixed diegetic observation. The profile
chosen for a scene is a production decision, not a wire-format selection.

## Separation rules

Camera ownership is physical; focalization is about attention and permitted
knowledge; audition is sonic. They do not change each other automatically.
Embodied first-person requires a declared body owner and body-based movement;
an external full-body self-view needs a separate deliberate construction.
A viewpoint transition alone neither approves an event nor changes canon.

A shot request's character-keyed morphology, identity and state maps agree in
membership and may all be empty. In a complete binding check, its context, camera
and projection agree in scene, shot, profile and hashes. Schema-valid references
alone do not prove that the receiving project possesses the referred files.

## Tools

```bash
python scripts/viewpoint_protocol.py validate camera.json
python scripts/viewpoint_protocol.py build-ledger --help
python scripts/shot_request.py request.json --help
python scripts/protocol_exchange.py describe --type shot-request
```

See [protocol exchange](../../references/protocol-exchange.md) for exact bundle
verification and complete binding checks. Private production runs, persona records,
world bases and model controls are not implied dependencies of a shared request.
