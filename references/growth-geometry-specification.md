# Growth Geometry Specification

Growth is any authored structure carried by or projecting from another structure. Hair, fur, filaments, feathers, plates and quills are examples rather than mandatory slots. A category name by itself settles nothing about position, material, number or presence. A fixed menu of body regions is not the common model. Missing data is not an instruction to invent anatomy.

## Authoring

Use `representation: "declared-structures"` and a map of author-owned IDs. See [Declared Structures Runtime](runtime/declared-structures.md) for the executable contract, validation and authority boundary. Start from `templates/growth-geometry-template.json`; its empty map says nothing about universal absence.

For each relevant structure declare location, presence and the dimensions needed to reconstruct it. Geometry keys are open vocabulary. Useful questions include boundary, direction, density, grouping, silhouette role, relative or absolute dimensions, color, finish and clearance. They are prompts for judgment rather than fields that every structure must fill. A continuous fluid layer may leave individual strands undescribed, and an isolated projection may leave digits out.

Independent structures remain independent. Use stable IDs and explicit parent, attachment and local override relationships. An overall surface and a local exception coexist rather than replace each other. Existing, absent, unknown and outside the current crop are four distinct states. Temporary wetness, disorder or compression stays in current state; permanent shape changes need the appropriate approval.

## Detailed geometry

Any region, including an unnamed one, uses ordinary geometry properties. Select the construction details that make the declared design reproducible:

- Boundary and attachment: where the structure begins and ends on its carrier, using the declared carrier's landmarks; how its base joins or clears adjacent structures.
- Direction: growth, fall or flow axes, including reversals, part origins and breaks.
- Density and grouping: coverage, edge thinning, and the size and separation of clumps, tufts, strands, barbs, rows or plates where those units exist.
- Silhouette and volume: the contour contributed by the growth, the viewing angles that expose it, and lift or compression relative to its carrier.
- Dimensions and cross-section: length against an explicit landmark or carrier ratio, exposed length, thickness, taper, curvature and a round, flat, ribbon, wedge or other authored section.
- Color, surface and response: base, root, tip and accent zones in relation to the carrier rather than the current illumination; surface finish, gravity and motion response, and continuity under occlusion.

A declared strand arrangement can add a section map, hairline or flow origin, shaved or trimmed zones, ties and accessories, and clearance around adjacent features. Section names follow the actual design rather than a required fringe, crown, temples or nape. A style name alone leaves section geometry and landmark-based length undetermined.

A base covering and independently designed hair, mane, ruff or facial growth use distinct IDs and boundaries. A cheek ruff implies nothing about a shoulder mane, and a surface color patch or jaw shadow counts as growth only when the source establishes it. For declared brows or lashes, separate permanent shape, density, length and color from expression angles, makeup and cast shadow.

These details refine structures already established by the design or evidence. They leave the set of structures unchanged, and every property stays optional. Record explicit absence only when it is an actual anchor.

## Terminal structures

Use `templates/terminal-growth-contract-template.json` for an authored ending or projection. Its entries use the same `structures` map. Declare the carrier, boundary, dimensions and material that matter to this design. A digit-mounted claw may describe its relation to a digit; a rim projection describes its rim. Each is declared on its own terms, and one implies nothing about the other.

Where relevant, specify exposed or free-edge length, shape, taper and curvature, thickness, base transition, decoration, wear and per-structure differences. Bind each visible ending to its declared carrier; hidden count stays unknown. Retraction belongs to current state while extended geometry remains part of the design. A molded or mechanical ending can describe seams, material and articulation. Perspective shortening leaves the underlying dimensions unchanged.

## Resolved authority in state-aware packages

`scripts/state_protocol.py` exposes `resolve_growth_geometry()` as the shared resolver for reference plans, asset render specifications and state graph validation. It starts with `stable_identity.growth_geometry`. An approved Era Contract can explicitly replace it at `approved_changes.growth_geometry`; an approved Form Contract can replace it at `surface_system.growth_geometry`. These are complete declarations rather than inferred patches or natural-language rewrites. Each supplied contract must belong to the same character and reference the exact parent identity hash. Proposed and superseded changes stay outside canon.

An Appearance Variant declares its complete geometry in the top-level `growth_geometry` rather than inside `appearance_definition`. Only changed JSON pointers explicitly named by the resolved identity's `variant_fields` are permitted. Those pointers start at `/stable_identity/growth_geometry/`, for example `/stable_identity/growth_geometry/structures/edge-filaments/geometry/color`. A variant leaves its own permissions and the identity locks as they are. Descriptive phrases such as `removable polish` grant nothing machine-readable.

Current `appearance_state.grooming` is carried uninterpreted as one `grooming_state` entry: `/appearance_state/grooming = ` followed by canonical JSON (sorted keys, compact separators). It preserves wetness, disorder, compression, or polish condition while the declared shape, color and boundaries stay as declared. Both the production subject and the render specification's `subject_resolution` must carry the exact resolved geometry, including this condition annotation. The render builder fills a missing geometry field and rejects a conflicting supplied one rather than silently replacing authored input. A form-aware render requires the state snapshot that binds the form hash; a standalone render applies a form only with traceable provenance.

The regression suite for these constraints is `scripts/growth_resolution_smoke_test.py`. It covers authorized changes, wrong parents, missing approval, fixed-shape drift, temporary conditions and lossless reference/render handoff. Package integrity says nothing about whether generated pixels follow the geometry; rendered images still need inspection.
