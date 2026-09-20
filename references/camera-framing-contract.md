# Camera Framing Contract

A camera label is not enough to reproduce a preset. The Camera Framing Contract records the subject-to-camera relationship, frame occupancy, crop landmarks, and perspective consequences that must remain stable across generations.

## Why it exists

Terms such as close-up, waist-up, low angle, or portrait lens leave too much room for the target model to decide the crop. A scene that depends on complete ears, crossed wrists, a necklace, and a belt line can drift into a chest-up crop, a full-body image, or an over-wide close view unless those obligations are separately recorded.

## Required measurements

Use subject-relative measurements first. A metre estimate is useful only when the subject is roughly human sized.

- `shot_scale`: the body range visible in the frame.
- `distance_class`: a practical distance band.
- `subject_relative_distance`: distance expressed in head heights, visible torso heights, full body heights, subject widths, or metres.
- `human_scale_distance_equivalent_m`: optional real-world equivalent for a human-sized subject.
- `camera_height`: a stable anatomical, mechanical, or environmental landmark.
- `pitch_degrees`, `yaw_degrees`, `roll_degrees`: numeric camera orientation.
- `lens_equivalent_mm` and `projection_behavior`: the likely perspective envelope.
- `frame_occupancy`: subject height and width as a percentage of the image.
- `coverage_landmarks`: the top, bottom, left, and right boundaries of the intended crop.
- `eye_line_position`: where the eye or primary sensory line sits in the frame.
- `nearest_form`: the body part, prop, or structure closest to the lens.
- `perspective_scale_change`: which forms enlarge or compress because of camera proximity.
- `required_visible_elements`: elements that must remain inside the frame.
- `allowed_offscreen_elements`: elements that may continue outside the frame.
- `stability_invariants`: explicit guards against pullback, over-cropping, or wide-angle distortion.
- `horizon_and_vanishing`: where the horizon line sits in the frame and where the dominant vanishing point falls, when the scene contains converging structure.

## Perspective anchors for environment-forward frames

A shot whose framing depends on architecture, ground plane, or receding structure is under-specified by camera height and pitch alone. Two frames can share both and still differ completely because their horizon sits at a different height and their lines converge toward a different point. Name three things and the framing is pinned: the horizon's height in the frame, the vanishing point's position (including which edge it sits beyond, or that the view is two-point with convergence to both sides), and which surface occupies the near ground.

Convergence direction is also the most reliable way to say where the camera stands without naming coordinates. A promenade whose lines run to a vanishing point at the right edge is being watched from beside it; the same promenade converging at frame center is being watched from on it. Prefer this construction over camera-position prose whenever the environment carries the composition.

These anchors are positive construction, not exclusions. A negative such as "no vanishing point" cannot correct a perspective the positive text is still requesting; restate the geometry instead.

Perspective compliance is a capability check as much as a wording choice. Subject-specialized checkpoints often ignore explicit horizon and vanishing-point instructions and fall back to the composition cluster of their training subject, while instruction-following general models honour the same sentence directly. When two or three attempts at an explicit perspective produce the same unrequested composition, the wording is not the problem: route the plate to a model that follows spatial instructions, and keep the specialized checkpoint for the subject it was trained on.

## Measurement discipline

Prefer ranges over false precision. Measure occupancy and crop against the depicted subject, not the source canvas in pixels. A frame may intentionally let shoulders or an extended hand exceed 100 percent of subject-width occupancy while the central identity features remain inside the image.

Separate camera enlargement from stable anatomy. A near forearm enlarged by a mild wide lens does not become an identity proportion. The Character Identity Contract owns stable size relationships; the Camera Framing Contract owns perspective enlargement.

## Reference-image extraction sequence

1. Identify the shot scale from the highest and lowest visible body landmarks.
2. Record the exact top, bottom, left, and right crop anchors.
3. Estimate subject height and width occupancy.
4. Locate camera height relative to a stable subject landmark.
5. Estimate pitch, yaw, and roll from face, torso, floor, wall, or water lines.
6. Identify the nearest form and compare its scale with the same form farther from the lens.
7. Estimate a lens range from distortion and compression rather than from mood.
8. Name every element that must stay visible for the scene to remain the same scene.
9. Name every element that may safely remain offscreen.
10. Add at least three stability invariants.

## Scene and production ownership

A reusable base scene stores its canonical camera contract when framing is load-bearing. A Production Specification resolves that contract for the current subject, aspect ratio, and target image. An Asset Render Specification uses the same structured contract. A user-requested camera change may adapt the contract, but the change must be deliberate and all dependent crop obligations must be recomputed.
