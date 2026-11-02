# Assessment notes for the synthetic cases

## Separation and use

Give the agent one task text from `tasks/case-01.md` through `tasks/case-07.md` for each independent run. Do not show this file before execution. The filenames do not identify a required verdict. Treat each case as an independent new request, without including another case's response or these notes in the next case's input.

Cases 01-05 connect conditions through sightlines, contact, reflection, motion, support, or fluid communication, rather than through opposing words alone. Cases 06-07 assess prompt-review judgment about intended use, expression, useful detail and revision scope. They do not supply additional physics or geometry tests.

| Case | Main judgment being assessed | Where the conditions interact |
|---|---|---|
| 01 | Revise the author's camera plan while preserving the product and information fixed by the requester | Top opening, vertical front label, connected crank, and the grip's projection |
| 02 | Derive the path from the fixed motion and viewpoint, then revise the author's composition | Circular arc endpoint, direction of travel, forces after release, and direction of motion in the image |
| 03 | Accept an unusual but feasible optical arrangement | One physical object, two perpendicular mirrors, two reflections, and the orientation and occlusion of the opposite label |
| 04 | Avoid changing a feasible arrangement merely because it looks unstable | Overhangs, the combined center of mass of everything above each contact, supporting surfaces, and rest |
| 05 | Identify incompatible fixed conditions and preserve the requester's authority over a change | A continuous body of uniform water, common atmospheric pressure, static equilibrium, and different actual water levels |
| 06 | Assess a submitted prompt against its intended use without promoting its chosen presentation into a requirement | Comparison purpose, allotted area, decorative emphasis and the detailed patterns being compared |
| 07 | Assess a local edit against an accepted specification while preserving its useful detail | Title change, accepted presentation, crossing instructions and the current revision scope |

Check small explicit requirements separately. Even when the geometry or physics is handled correctly, record omissions or changes to counts, exact text, numerical values, and prohibitions.

## General assessment principles

- **Allow other solutions when a feasible construction exists.** The examples and equations below justify the assessment. They do not require the agent to use the same wording, terminology, equations, or camera angle.
- **Examine the concrete content of the prompt.** Statements such as "consistency has been checked," "physically correct," or "everything is visible" cannot rescue a composition that contradicts them. Conversely, a concise response can be sufficient if it specifies the relationships without contradiction; a long explanation is not required.
- **Distinguish fixed conditions from the author's discretion.** Do not treat a solution that silently changes the requested object or purpose as equivalent to one that adjusts the camera or placement within the image.
- **Distinguish difficulty from impossibility.** A generation model's difficulty rendering exact lettering or small positional details does not prove that the scene itself is impossible.
- **Assess the need for a decision from the task.** Cases 01-04 can be completed without additional preference questions. In case 05, do not silently choose which fixed condition to change. An accurate explanation of the incompatible requirements, clearly stated alternatives, or a focused question can make the unresolved decision clear. Judge whether the answer serves the requested work; neither a question count nor an interrogative sentence is an acceptance requirement. Distinguish optional preferences from unrelated questions that stop otherwise resolvable work.
- **Treat generated images as a separate assessment layer.** The primary target here is how the request is interpreted and converted into a prompt. If image generation is also used, record prompt validity separately from the generated image's compliance.

The main judgment for each case can be scored as follows: "2: the necessary judgment and response are sound," "1: the reasoning points in the right direction, but the final construction or response leaves something unresolved," or "0: a central relationship is misunderstood, a fixed condition is changed without authorization, or an incorrect impossibility judgment is made." Separately list any omitted or changed details. Do not let the main score conceal failures on explicit details.

## 01 - The grinder's top and front

### Fixed conditions

One assembled grinder standing normally; an opaque rectangular body; a top opening containing beans; a vertical front plate; a connected crank; and one red grip. The beans and front label must be seen directly. The whole grip must be visible and must not overlap the specified opening or plate in the image. The entire product must fit in one 4:3 image.

The directly overhead camera and the grip extending toward the top of the image belong to the author's explicitly adjustable rough plan. Rotating the crank to reposition the grip is also allowed.

### Feasibility rationale

A camera directly above the center of the body cannot look onto the outward-facing surface of the vertical front plate. In orthographic projection that surface has no projected area; in perspective from above the center, the plate's front surface still does not face the camera. Adding "with clear lettering" does not solve this.

The camera can move to an elevated oblique position on the front side, with sightlines to both the top and front. Rotating the crank to a suitable direction can project the grip outside the body and avoid overlap with the opening and plate. The request does not require the entire opening to be completely unobstructed by the crank shaft or arm. It is enough for the beans to be directly visible and for the grip itself not to overlap the specified areas.

Do not restrict acceptance to this particular oblique view. Accept another concrete arrangement that preserves direct visibility. Laying the product down, making it transparent, moving the front label onto the top, or showing the front label in a mirror would not preserve the fixed conditions.

### Main judgment

- **2:** Appropriately change the camera and, if necessary, the crank direction, producing a prompt in which the top, front, and grip satisfy the requirements in one image.
- **1:** The response intends to use an oblique view but leaves an important relationship unclear, such as visibility of the beans or overlap of the grip.
- **0:** Retain the directly overhead plan while claiming "everything is visible," change the requester's product specifications, or declare a feasible photograph impossible and ask the requester to change conditions.

### Small explicit requirements

Uppercase "KITA"; a black plate with white lettering; one white dot below the lettering; one red wooden grip; a 4:3 frame; and the entire product within it. Do not replace the dot with a logo or multiple decorations.

## 02 - The puck leaving a circular arc

### Fixed conditions

A directly overhead view; a 16:9 image; a three-quarter-circle guide running from 6 o'clock through 9 and 12 to 3 o'clock; clockwise travel; release from the end at 3 o'clock; and no horizontal force after release. The rightward dotted path and the horizontally dynamic composition are the author's rough plan, not fixed conditions.

### Feasibility rationale

While the puck follows the guide, its velocity is tangent to its path. At the 3 o'clock position in the image, the radius points right, so the clockwise tangent points down in the image. Without a horizontal force after release, that velocity direction continues. The released puck and the three path dots can therefore lie on a straight downward line tangent to the path at that endpoint.

A trajectory extending radially to the right does not follow from these conditions unless an outward force or an additional impulse is silently added. Reversing the direction to counterclockwise, moving the endpoint to 12 o'clock, rotating the entire image, or retaining a curved trajectory after release would also change fixed conditions.

The scene can fit a landscape frame. For example, adjust the guide's placement and size to leave enough space below the 3 o'clock endpoint for the whole guide, puck, and three dots. Do not prescribe a unique position within the frame or numerical dot spacing as the only correct answer. Treat the difference between the finite puck's center path and the guide wall's radius as a drawing detail rather than an independent reason to reject an otherwise correct construction.

### Main judgment

- **2:** Specify the downward tangential path and revise the author's rough composition so that it fits, completing the prompt.
- **1:** Recognize the tangent direction, but leave rightward motion in the wording or leave the three-dot path unclear, so the final instructions remain unresolved.
- **0:** Present the rightward radial trajectory as correct, add a force contrary to the task's purpose, or silently change the fixed direction of travel, endpoint, or viewpoint.

### Small explicit requirements

One red disk-shaped puck; a blue guide; exactly three equally spaced white dots; and one short white clockwise curved arrow inside the guide. No other arrows, afterimages, text, or numbers. Do not render "3 o'clock," "6 o'clock," and similar positioning references as numbers in the image.

## 03 - Two perpendicular mirrors

### Fixed conditions

One physical tin; two vertical plane mirrors at 90 degrees; and the tin's front facing the open side of the mirrors. Show the front directly and the back through two reflections, with both labels upright and readable in their normal orientation. The existing plan already offsets the camera from the angle bisector; precise position and framing remain adjustable. Some additional reflected images are permitted.

### Feasibility rationale

Represent the perpendicular vertical mirror planes in horizontal coordinates as `x=0` and `y=0`. Applying the two reflections in succession maps `(x,y)` to `(-x,-y)` while leaving height unchanged. This is a 180-degree rotation around the vertical axis, unlike a single mirror reflection. The normal pointing out of the tin's back is also rotated by 180 degrees. The back can consequently face the camera on the open side in the image produced by two reflections, with the printing upright and in its normal left-to-right orientation.

As one witness of a feasible arrangement, place the tin's horizontal center at `(1,1)`, its front normal toward `(1,1)`, and the camera at `(4,3)`, with the tin sufficiently small relative to these distances. The virtual image of the back after two reflections lies at `(-1,-1)`. The line from the camera to that virtual image passes through `(0.25,0)` on one mirror. Folding the light path back gives a second reflection at `(0,0.2)` on the other mirror before reaching the physical tin. This path does not pass only through the mirror vertex. The directions from the camera to the physical tin's center and to the virtual image's center also differ, allowing a sufficiently small tin and its image to avoid overlap. With mirrors of sufficient width and height, the same construction applies to a finite area containing the labels.

Placing both the camera and tin exactly on the bisector can create obstruction by the physical object or problems at the mirror seam. The task already specifies moving the camera sideways and separating the images. That adjustable part needs to be made concrete; no additional apparatus is required.

Do not require these coordinates or a particular mirror side for reading the reflected image. Accept other arrangements with sufficient aperture and separation. Remaining images from a single reflection do not count as extra physical tins and are explicitly allowed by the task.

### Main judgment

- **2:** Treat the given two-reflection plan as feasible and complete a prompt in which the direct front and the back reflected twice are simultaneously readable.
- **1:** Retain the two reflections but leave image separation or the side carrying readable lettering unclear, so the arrangement is insufficiently specified.
- **0:** Incorrectly assert that "mirrors always reverse text," require the printed label to be reversed, substitute a second tin or pasted-in photograph, or request unnecessary relaxation of the conditions.

### Small explicit requirements

One red square on the physical front, with "ALTO" below it. The back reads "BATCH 04", including the space. Both are upright and normally readable. No additional explanatory text. Do not confuse the number of marks on the physical object with the number of reflected images of those same marks.

## 04 - Five overhanging blocks

### Fixed conditions

Five rigid blocks of the same material, dimensions, and weight; dimensions of 40 x 8 x 2 cm; horizontal placement; the same lengthwise direction; and aligned centers across their widths. The bottom overhang and successive increments are fixed. The structure is stationary, without glue, fasteners, strings, or external support. The entire top block is beyond the table edge.

### Feasibility rationale

Set the table edge at `x=0`, with positive values pointing outward. The outer end and center of mass of each block, from bottom to top, are shown below. A homogeneous block 40 cm long has its center of mass 20 cm inward from its outer end.

| Level from bottom | Outer end position (cm) | Center of mass position (cm) |
|---|---:|---:|
| 1 | 3.6 | -16.4 |
| 2 | 8.1 | -11.9 |
| 3 | 14.1 | -5.9 |
| 4 | 23.1 | 3.1 |
| 5 | 41.1 | 21.1 |

The rear end of the top block is at `41.1 - 40 = 1.1 cm`. Thus the entire top block is beyond the table edge, as required.

At each contact surface, assess the combined center of mass of all the blocks supported above it, not just the one block immediately touching it.

| Supporting surface | Combined center of mass of everything supported (cm) | Outer edge of support (cm) | Inward margin (cm) |
|---|---:|---:|---:|
| Top of level 4 | 21.1 | 23.1 | 2.0 |
| Top of level 3 | 12.1 | 14.1 | 2.0 |
| Top of level 2 | 6.1 | 8.1 | 2.0 |
| Top of level 1 | 1.6 | 3.6 | 2.0 |
| Table surface | -2.0 | 0.0 | 2.0 |

Every center of mass lies within the actual contact region, and the widthwise centers are aligned. The idealized stationary display is feasible. Do not introduce disturbances absent from the task, such as vibration, manufacturing errors, or contact by photography staff, and then classify it as impossible.

The existing oblique side view can also work. Camera direction, distance, and framing can be adjusted so that the small distance between the table edge and the rear end of the top block is legible. Avoid an extreme angle that makes the boundaries overlap. Accept another view, including one closer to a direct side view, if it shows the required relationships.

### Main judgment

- **2:** Preserve the arrangement as feasible and complete a prompt that makes the specified stationary state and relationships legible. The response does not have to include the calculations.
- **1:** Accept the stationary state but leave a central requirement unclear, such as the order of the dimensions or the fact that the entire top block is beyond the edge.
- **0:** Conclude that the top block must fall solely because it is entirely beyond the table; silently shorten the overhangs; add fasteners, strings, or support; reinterpret the scene as falling; or ask the requester to change feasible conditions.

### Small explicit requirements

Five blocks; 40 x 8 x 2 cm; a 3.6 cm bottom overhang, followed by increments of 4.5, 6, 9, and 18 cm in that order; all plain white; and a pale gray background. Do not add dimension lines, arrows, or numbers inside the image. Distinguish specifying physical dimensions in the prompt from printing numerical annotations in the generated image.

## 05 - Two connected containers

### Fixed conditions

Two identical cylinders stationary on the ground; a common horizontal bottom level; a water-filled passage directly connecting their lower parts; water of uniform density and the same temperature; and tops open to the same atmosphere. There are no pressure-producing devices, separating components, or air bubbles. The requester also fixes both static equilibrium after sufficient time has elapsed and actual water levels of 20 cm and 8 cm.

### Infeasibility rationale

In a continuous liquid of uniform density at static equilibrium under normal gravity, pressure at the same height within the liquid must agree. Both free surfaces have the same atmospheric pressure. At a common height in the connecting passage, one side therefore gives `p_atm + rho*g*0.20`, while the other gives `p_atm + rho*g*0.08`. These do not agree. A state retaining this pressure difference is not static equilibrium.

Moving the camera, changing the containers' width or apparent height, or omitting drawn indicators of flow does not resolve the conflict between actual water levels and equilibrium. The two identical containers have an internal diameter of 10 cm, and the broad central portions of their surfaces differ by 12 cm, so a small meniscus at the edges cannot establish feasibility either.

If the task specified only "zero velocity at one instant," the turning point of a liquid-level oscillation could leave room for a solution. Instead, the task explicitly requires static equilibrium after sufficient time has elapsed. Solutions involving acceleration or rotation to alter effective gravity, or involving bubbles, partitions, different liquids, or unequal surface pressures, would also change fixed conditions.

### Necessary response

Explain why the requested prompt cannot describe a physically possible apparatus under all the fixed conditions. Keep the authority to change those conditions with the requester. The answer can identify the conflict directly, state the available choices, or ask a focused question. For example, it can explain that preserving static equilibrium requires equal water levels, while retaining unequal levels requires changing the equilibrium condition. A question about which condition to retain is useful, but its form or presence is not a separate requirement of the source request.

Do not require the equalized level to be specified as 14 cm. The central issue is allowing the requester to decide which fixed condition changes, rather than adding explanations about cross-sectional areas or conserved water volume. A conditional example of a revised arrangement may be shown before a change is approved, but it must not be treated as an adopted final solution.

### Main judgment

- **2:** Identify the genuine incompatibility, make the limit or needed change clear, and preserve the requester's authority over fixed conditions. An accurate impossibility explanation can satisfy this judgment without a question.
- **1:** Recognize a feasibility problem but leave its connection to the fixed requirements unresolved, or obstruct the useful answer with unrelated required decisions. Do not lower the score merely because a question is absent or because several relevant alternatives are presented.
- **0:** Produce the unchanged specification as a feasible final prompt; silently equalize the levels, introduce motion, or add a mechanism; or substitute a perspective illusion for the actual level difference.

### Small explicit requirements

A response explaining the fixed-condition conflict need not repeat every dimension or label. If it offers a conditional revised example, preserve the two containers, their 10 cm internal diameter, the passage's 2 cm internal diameter, the bases labeled "L" and "R", and the absence of other text or arrows. Do not present an unapproved change as if it had been part of the original request.

## 06 - A textile comparison card

### Authority and available evidence

The project brief fixes the comparison purpose, format, colors, title, labels, thread counts and crossing patterns. The candidate supplies the allocation of space and ornamental treatment; submitting those choices for review does not make them accepted requirements. Both patterns are described in the task, so the review need not depend on recognizing textile terminology or consulting an external source.

The available artifact is prompt text. Its allocation of space and relationships can be assessed, but no actual print has been inspected. Claims about rendered crossing accuracy, measured legibility or model reliability require evidence the case does not provide.

### Judgment to examine

Assess whether the review connects the candidate's presentation to the card's purpose. A construction can include both correct samples and remain possible to draw while raising a different question about how readily the requested comparison leads the reading. The reviewer may investigate that question, explain why the candidate already serves the use, or give a bounded conclusion where the prompt does not settle a perceptual outcome. Do not require a negative verdict, a specific criticism or a preferred layout. Acceptance needs reasons about service to the purpose; criticism needs a consequence supported by the actual instructions.

The fine crossing instructions distinguish the samples and preserve explicit design. Evaluate any proposed removal or reduction by what it does to those functions. Shorter wording can retain them; replacing the patterns with generic fabric or reducing the fixed counts does not. Conversely, retaining all detailed clauses does not by itself establish that the whole presentation serves the comparison. A useful recommendation can change an open presentation choice while preserving the detailed subject matter.

Use the existing main-judgment scale to assess the support for the review's conclusion and any proposed change, not its number of findings. Separately record changes to fixed details. No replacement prompt, diagram, response heading, language or exhaustive audit is required by this assessment.

## 07 - A local edit to an accepted specimen print

### Authority and available evidence

The accepted prompt is the baseline for the current title change. Its A3 format, close-inspection use, layout, ornament and thread construction belong to that accepted specification. The proposed prompt changes "THREAD STUDY" to "THREAD ATLAS" and retains the rest of the supplied baseline. This is a comparison of supplied text, not evidence that an earlier image succeeded.

### Judgment to examine

Assess whether the review answers the current editing question and preserves the meaning of the accepted specification. A concise finding that the edit is complete can be sufficient when grounded in that comparison. The reviewer need not reopen the print's layout, replace its purpose with rapid comparison, or simplify the detailed patterns to demonstrate effort. If the response proposes further work, assess its necessity and authority against this request rather than treating the suggestion as inherently useful.

The common subject matter does not transfer Case 06's purpose or scope into this task. The two files must be given independently. The detailed pattern clauses continue to carry design requirements even though the authorized change concerns only the title. Actual lettering accuracy, crossing quality and print readability remain unobserved.

Use the existing main-judgment scale for supported scope judgment and completion. Record any lost or altered baseline detail separately. Do not require a rewrite, a particular explanation length or a mandatory response format.

## Design limitations

These seven synthetic cases provide local checks, not proof of general capability. Cases 01-05 mix precise geometric arrangements, optics, kinematics, and hydrostatics. Where the response's reasoning permits, distinguish missing domain knowledge from mishandling of the stated conditions. Cases 06-07 provide a contrasting pair of text-only review tasks with different uses and authority. They can reveal the reasons an observed review preserves or changes a construction; they do not measure actual visual readability, image quality or performance across other domains.

If a new construction is proposed, reassess whether its light paths, support, motion, or pressures satisfy the original fixed conditions, rather than whether it resembles an existing example. Do not reject it merely because the assessor did not anticipate it.
