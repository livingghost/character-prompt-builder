# Camera Framing Contract

A camera label alone may not reproduce a selected frame. The Camera Framing
Contract records the camera relationships, coverage and perspective constraints
that the commissioned depiction actually needs. Choose the frame through
[Production direction](runtime/production-direction.md#choose-the-expression)
before recording those constraints.

## When a frame needs a contract

Use this contract when the author selects a repeatable frame or the image's
purpose depends on particular camera geometry. A requirement such as readable
interaction can admit several frames. Select a camera for its contribution,
not simply because one was imagined first.

Only requested or meaning-bearing coverage belongs in visibility obligations.
Follow [instruction selection](runtime/prompt-composition.md#select-the-depiction)
before committing the shot. Whole-subject coverage, a detail view and an
environment-led view can each serve a particular commission. Inspecting every
design feature is not a reason to require all of them in the commissioned image.
An intentional crop leaves the underlying design intact and is not evidence of
missing anatomy.

The [authoring template](../templates/camera-framing-contract-template.json)
starts as `{}`: no camera constraints have been selected. Every field is
optional. Add only the chosen facts and constraints; omitted fields impose no
coverage, distance, occupancy, lens, margin or offscreen rule. An empty
`allowed_offscreen_elements` list does not require every unlisted element to be
visible. Visibility obligations are declared in `required_visible_elements` or
the other selected coverage instructions.

When exact repetition is commissioned, record enough geometry to reproduce that
particular frame. Its necessary precision follows from the purpose and source
evidence, not from filling every schema field. The author judges whether those
chosen measurements are sufficient. Supplied values retain their type, range
and complete nested-object checks. They are not all instructions to paste into
the model-facing text.

## Selected framing and measurements

Use subject-relative measurements first. A metre estimate is useful only when the subject is roughly human sized.

- `shot_type`: the intended kind and purpose of the view.
- `shot_scale`: the subject extent visible in the frame.
- `distance_class`: a practical distance band.
- `subject_relative_distance`: distance expressed in head heights, visible torso heights, full body heights, subject widths, or metres.
- `human_scale_distance_equivalent_m`: optional real-world equivalent for a human-sized subject.
- `camera_height`: a stable anatomical, mechanical, or environmental landmark.
- `pitch_degrees`, `yaw_degrees`, `roll_degrees`: numeric camera orientation.
- `lens_equivalent_mm` and `projection_behavior`: the likely perspective envelope.
- `frame_occupancy`: subject height and width as a percentage of the image.
- `framing_and_crop`: the selected boundaries and their relationship to the depiction.
- `coverage_landmarks`: the top, bottom, left, and right boundaries of the intended crop.
- `eye_line_position`: where the eye or primary sensory line sits in the frame, when applicable.
- `reference_landmark_position`: another authored landmark's position, when needed.
- `nearest_form`: the body part, prop, or structure closest to the lens.
- `perspective_scale_change`: which forms enlarge or compress because of camera proximity.
- `required_visible_elements`: elements that must remain inside the frame.
- `allowed_offscreen_elements`: elements that may continue outside the frame.
- `focal_sequence`: the selected order of attention within this depiction.
- `stability_invariants`: the conditions needed to retain the selected frame, such as an authored coverage boundary or perspective relationship. Record the actual conditions without padding the list to a fixed count.

For converging structure, describe the horizon and dominant vanishing point in
`framing_and_crop` or `lens_or_perspective` at the scope they constrain.

## Perspective anchors for environment-forward frames

A shot whose framing depends on architecture, ground plane, or receding structure is under-specified by camera height and pitch alone. Two frames can share both and still differ completely because their horizon sits at a different height and their lines converge toward a different point. Name three things and the framing is pinned: the horizon's height in the frame, the vanishing point's position (including which edge it sits beyond, or that the view is two-point with convergence to both sides), and which surface occupies the near ground.

Convergence direction is also the most reliable way to say where the camera stands without naming coordinates. A promenade whose lines run to a vanishing point at the right edge is being watched from beside it; the same promenade converging at frame center is being watched from on it. Prefer this construction over camera-position prose whenever the environment carries the composition.

These anchors are positive construction, not exclusions. A negative such as "no vanishing point" cannot correct a perspective the positive text is still requesting; restate the geometry instead.

Perspective compliance is a capability check as much as a wording choice. Subject-specialized checkpoints often ignore explicit horizon and vanishing-point instructions and fall back to the composition cluster of their training subject, while instruction-following general models honour the same sentence directly. When repeated attempts miss a specified perspective, inspect competing framing demands, references and controls before attributing the result to the model. A comparison with a suitable alternative tests the observed setup rather than proving a universal limit.

## Measurement discipline

Prefer ranges over false precision. Measure occupancy and crop against the depicted subject, not the source canvas in pixels. A frame may intentionally let shoulders or an extended hand exceed 100 percent of subject-width occupancy while the central identity features remain inside the image.

Separate camera enlargement from stable anatomy. A near forearm enlarged by a mild wide lens does not become an identity proportion. The Character Identity Contract owns stable size relationships; the Camera Framing Contract owns perspective enlargement.

## Reference-image extraction sequence

Apply the following observations where they matter to the assigned reference
use. Reproducing an exact frame can need the full set; transferring a design or
lighting contribution does not adopt the source camera.

1. Identify the shot scale from the highest and lowest visible subject landmarks.
2. Record the exact top, bottom, left, and right crop anchors.
3. Estimate subject height and width occupancy.
4. Locate camera height relative to a stable subject landmark.
5. Estimate pitch, yaw, and roll from face, torso, floor, wall, or water lines.
6. Identify the nearest form and compare its scale with the same form farther from the lens.
7. Estimate a lens range from distortion and compression rather than from mood.
8. Separate observed crop from elements the target image must visibly communicate.
9. Record explicit offscreen allowances only when they resolve an actual coverage requirement.
10. Record the stability invariants needed to reproduce the selected frame.

## Scene and production ownership

A reusable base scene stores its canonical camera contract when framing is
load-bearing. A Production Specification resolves that contract for the current
subject, aspect ratio and target image. An Asset Render Specification uses the
same structured contract. Carry a prior camera forward at its adopted scope;
its presence in an earlier draft alone does not establish a new requirement.
When a camera change is within the commissioned scope, revise the affected
coverage obligations together and preserve unrelated design and authored work.
