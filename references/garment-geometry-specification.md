# Garment Geometry Specification

A garment name is discovery vocabulary rather than a construction. Garments use the declared-structures form described in [Declared Structures Runtime](runtime/declared-structures.md). The common contract records garment identity, its authored class, coverage, structures, continuity and provenance. Shoulders, sleeves, a waist, front/back panels and leg openings are all optional.

## Declare the actual construction

Record only components that exist or whose explicit absence matters. Each component has a stable ID, location, presence and geometry properties. Describe support, attachment, openings, edges, material, thickness, local color, layer order and pose response where load-bearing. Link components with parent or attachment IDs when they belong to this contract. A covering on a ring, a distributed mesh or a one-piece shell is described in its own terms rather than through a humanoid garment pattern.

Detailed garment construction is ordinary authored geometry on the relevant component. Describe a seam, opening, support band or panel only where it is part of this garment. Keep different components separately identified when their connections or independent changes matter.

## Landmarks, state and visibility

Anchor edges to authored carrier landmarks rather than assumed human anatomy. Examples might use a collarbone, hinge, rim, vent, joint or control node; these are illustrations rather than required parts. Record the actual support and motion: which edge shifts, where material bunches or stretches, which openings change, and which surfaces are occluded.

Keep the carrier complete beneath a covering where its identity says it is complete. Fabric movement leaves structure in place. A hidden identity feature stays defined, and clothing stays closed and in place rather than opened or removed to display every known feature. Clothing state may change while identity stays as it is, unless an approved contract explicitly owns that garment.

## When detail is needed

Use a structured garment contract when an opening, asymmetric construction, support path, layer boundary, clearance or motion response determines the requested design. A short prompt for an ordinary garment skips the exhaustive panel inventory. Use the minimum details that settle the actual construction rather than the shortest list from a preset.

Checks must preserve intended coverage, attachment and the declared topology. They must reject a missing referenced component or incompatible duplicate, and they must accept a garment that merely lacks a sleeve, waistband or inseam.
