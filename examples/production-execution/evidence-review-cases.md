# Evidence review cases

These neutral synthetic cases are authored teaching examples. Their prompts
illustrate input judgment; hypothetical candidate descriptions state what a
reviewer would have to inspect in an actual artifact. They supply no observations
of generated images or evidence of model quality for a real production run.

Use the existing task criteria, direction and review fields. The author judges
meaning; scripts check evidence references, record structure and state. No
keyword classifier can decide the interpretations in these examples.

## 1. Poster hierarchy and letterform construction

**Contract.** A fictional public workshop needs a poster that communicates the
event, time and place. The exact text is "OPEN WORKSHOP", "SATURDAY 10 AM-4 PM"
and "RIVER HALL". The event title is primary; the time and place form an easily
found secondary group. Decorative geometry and letterforms are open.

**Source role.** The author uses a paper photograph only to choose the field's
color and surface. For this teaching case, stipulate a warm ivory color with
faint fine grain; no actual photograph has been inspected. The photograph's
crop, border and camera angle have no assigned role. Only the following text
reaches the renderer.

**Complete delivered input.**

> Create one flat 2D event poster with a warm ivory field and faint fine grain.
> Set "OPEN WORKSHOP" as the dominant headline. Group "SATURDAY 10 AM-4 PM" and
> "RIVER HALL" below it at a smaller but clearly readable size. Use dark
> lettering with strong contrast and generous spacing around each information
> group. Place simple geometric decoration around the information without
> competing with it. Include exactly those three text strings.

**Requested judgment.** Does this prompt establish a usable hierarchy for the
event information?

**Supported answer.** The input gives the title priority and groups the time
and location as secondary information. Contrast, spacing and decoration serve
that hierarchy. The assigned paper qualities are carried in text, so the
renderer needs no access to the authoring photograph. The prompt is sufficient
for this requested judgment. Exact letter terminals and the placement of each
grain mark can vary. Further specifications for them have no identified role
in the poster's information hierarchy.

The time string remains an exact requirement even though it is secondary.
Reviewing its accuracy serves that requirement; designing every letter's
geometry is a different task. A generated poster would still need inspection
for actual text, hierarchy and legibility at its intended display scale. The
prompt's completeness supplies no observation of that output.

**A construction-study contract.** A separate exercise teaches the difference
between the capital letters E and F. A suitable complete input is:

> Draw capital E and F as a flat black letterform construction study on white.
> Align their baselines and cap heights. Give both the same vertical stem,
> top arm and shorter middle arm, with equal stroke thickness. Give E an
> additional bottom arm as long as its top arm. Use straight rectangular
> strokes and enough space between the letters to compare their construction.

Here the shared structure and additional bottom arm are the subject. Their
alignment, thickness and correspondence require close inspection. The reviewer
chooses the necessary precision from the current purpose under
[Observe and repair](../../references/runtime/production-direction.md#observe-and-repair).

## 2. Alignment and insertion

**Contract.** An assembly illustration must show a rigid peg inserted into a
guide hole. The view is open, but the insertion must be assessable.

**Hypothetical first observation.** The peg's visible shaft aligns with the
hole's axis. A housing hides the peg tip and the entrance to the hole.

**Comparison.** Alignment supports a possible insertion path but cannot settle
whether the peg enters the hole. Record the obscured connection and an
`indeterminate` verdict for insertion. If a clear view instead shows the peg
ending short of the entrance, that gap supports `fail`. Select a view that
exposes the required connection when it is otherwise hidden. Do not infer
insertion from the completed assembly described in the brief, or require every
internal surface to become visible.

## 3. Laughter and intended emotional meaning

**Contract.** A comic portrait shows an adult laughing with delight. No
particular mouth, eyebrow or hand gesture is fixed.

**Hypothetical first observation.** The mouth is open, the eyes are wide, the
brows are drawn high together, and the shoulders and hands appear tense.

**Comparison.** An open mouth alone does not establish laughter. Read the
combined face and posture: if they clearly communicate a frightened gasp,
that conflicts with the requested delight. If the crop or rendering leaves
laughter and alarm unresolved, use `indeterminate` rather than assigning an
emotion from the prompt. Record the visible features separately from their
emotional interpretation. Repair the combined performance when that mismatch
is established, without imposing a single mouth shape or gesture on every
depiction of laughter.

## 4. Current contact and an earlier or later event

**Contract.** A mechanic currently presses a release button. The button and
fingertip must show contact; earlier and later hand positions are background.

**Hypothetical first observation.** The fingertip ends above the button, with a
clear visible gap between them.

**Comparison.** The present-contact criterion fails. A source note that the
button was pressed earlier, or a prompt saying the mechanic is about to press
it, cannot turn this gap into current contact. Rebuild the selected instant
and physical relationship. If the contact region is occluded, record what is
hidden and use `indeterminate` instead of inventing either contact or a gap.

## 5. An unexpected valid composition

**Contract.** A diagram compares the open and closed states of one valve with
the same component identity and clear state labels. Arrangement is open.

**Expected construction.** The author imagined two side-by-side views.

**Hypothetical first observation.** Two clearly labeled views are stacked
vertically, retaining corresponding shapes and showing the specified opening
in the open state and closure in the closed state.

**Comparison.** The layout differs from the author's imagined arrangement but
can satisfy the declared criteria. Inspect the actual component and state
details before passing them. No repair is justified solely by the vertical
arrangement. A selected composition becomes a hard criterion only when its
source actually requires it.

## 6. An unpeopled artifact and useful evidence scale

**Contract.** A terrain image must show a continuous water channel through a
gap in a raised ridge. No character, emotion or temporal phase is relevant.

**Incomplete delivered input.** "A raised ridge and a water channel in a
quiet terrain study."

**Competing realizations.** The water can run along the ridge or terminate in
front of it. Both fit the input but miss the required connection. Specify the
channel continuing through the ridge opening and choose a view that exposes
that passage. Extra texture detail cannot replace the missing spatial carrier.

**Hypothetical first observation.** Water is visible on both sides, but the
opening is hidden by the ridge crest. The through-connection remains
`indeterminate`; the reviewer does not reconstruct hidden geometry from the
prompt. A different oblique view can succeed when it reveals the same required
connection. This procedure needs no invented persona or action record.

## 7. Intentional ambiguity within declared limits

**Contract.** A graphic should permit both a vessel and two facing profiles to
be read from the same central silhouette. Either may be noticed first. Both
readings must remain available; no emotional relationship is prescribed.

**Hypothetical first observation.** The central light shape has a vessel-like
rim, narrow neck and base. Its two contours also form facing forehead, nose,
lip and chin profiles against the dark surrounding areas.

**Comparison.** Those observed contours can support both permitted readings.
A reviewer noticing one first is not a failure. If detail clearly destroys one
contour, record that contradiction; if resolution prevents judging it, use
`indeterminate`. Do not repair the work into one unambiguous object merely to
make the review easier. One review does not prove that every audience will
perceive both readings.

## 8. A working transmission and a conflicting design choice

**Contract.** An instruction diagram must explain a working belt transmission.
Two equal pulleys have parallel shafts and are viewed from the same shaft-end
side. A taut belt runs without slipping, and both pulleys turn clockwise in
that view. The designer may choose the belt routing and diagram arrangement.
There are no additional pulleys, gears or independent drives.

**Draft delivered input.**

> Draw a clean mechanical diagram of two equal pulleys on parallel shafts,
> viewed from the same shaft-end side. Connect them with a taut crossed belt,
> with the two belt spans crossing between the pulleys. Show a clockwise
> rotation arrow on each pulley. Depict one working transmission with no belt
> slip and no additional drive components.

**Requested judgment.** Can this diagram explain the specified transmission?

**Comparison.** The arrows, belt contact and routing concern the same working
mechanism. Following belt motion around a crossed route gives opposite pulley
rotation directions when observed from the same shaft-end side. Saying that
both arrows are clockwise does not make that route transmit the requested
motion. Reading one pulley from the opposite end would change a fixed viewing
condition. Adding a drive component would change the specified mechanism.

The crossed route is the designer's choice. Replace it with an open route
while retaining the two pulleys, common viewing side and clockwise rotation.
One complete repair is:

> Draw a clean mechanical diagram of two equal pulleys on parallel shafts,
> viewed from the same shaft-end side. Connect them with a taut open belt:
> two uncrossed straight spans join the corresponding upper and lower tangent
> points, with the belt wrapping around the outer side of each pulley. Show a
> clockwise rotation arrow on each pulley. Depict one working transmission
> with no belt slip and no additional drive components.

**Supported answer.** The repair describes a common route in which both pulley
rotations agree with the belt motion. It changes the selected routing, rather
than preserving the crossed design by changing the requested motion. If a
different brief fixes a crossed belt and opposite rotations, that construction
is valid. Crossings are not generally prohibited. No diagram has been rendered
here; the analysis establishes a construction, not successful image generation.

## 9. Opaque parts with a valid shared viewing path

**Contract.** A technical diagram explains a clear viewing path through two
parallel opaque plates. Their circular openings share one axis. The front
plate's opening is wider than the rear plate's; a small red disk beyond both
plates is centered on that axis. The view is orthographic along the axis.
The front plate is gray and the rear plate blue. Show the disk through the
openings and the blue face visible within the larger front opening. The full
rear outline and a measurement of plate separation are not requested.

**Complete delivered input.**

> Draw an orthographic technical view along the common axis of two circular
> openings in parallel opaque plates. The gray front plate has an 80 mm
> opening and the blue rear plate a 40 mm opening. Center a 10 mm red disk
> beyond the rear opening on the same axis. Show the gray plate around its
> opening, the blue rear face inside that opening, and the red disk through
> the smaller rear opening. Keep both plates intact outside their apertures.

**Supported answer.** This is a coherent shared projection. Rays through the
large front opening reach an annular area of the blue rear face; rays through
both openings can reach the smaller red disk. Opacity outside the apertures
does not block that path. The rear outline is hidden without violating the
contract. The requested colors and size relationships remain precise.

Changing the camera, making a plate transparent or adding a cutaway has no
identified purpose here. Complexity and partial visibility are not defects.
In an actual image, inspect the opening boundaries, exposed blue area and
disk position. The schematic alone would not establish an unrequested distance
between the plates.

## 10. Fixed mechanism states requiring a decision

**Contract.** A single schematic depicts one current state of a rigid
rectangular gate. Its hinge is fixed to the left post. Its closed position
spans the two fixed posts; in that position, a hole at the free edge aligns
with a hole in the right post. A rigid locking pin must remain fully seated
through those same two holes. The same gate must be swung 90 degrees open
from that closed position about its left hinge. The parts stay intact and attached;
there are no slots, flexible joints, moving posts or separate state views.
The requester explicitly fixes all of these conditions.

**Requested judgment.** Prepare the schematic prompt, or identify a decision
needed to make the request coherent.

**Comparison.** Keep the two posts and left hinge fixed while considering the
specified swing. The gate's free-edge hole moves around the hinge, away from
the stationary right-post hole. A rigid pin cannot remain fully seated through
both separated holes under those same conditions. The difficulty follows from
the shared connections and motion, not from how demanding the drawing is.

**Supported answer.** Explain this conflict and ask which operating state to
retain: the open gate with the locking pin released, or the gate secured at the
right post with the pin engaged. The author cannot silently withdraw the pin,
bend it, move a post, or overlay another moment. Unlike the selected routing in
case 8, the conflicting state is explicitly fixed here. A decision is necessary
for this case; it does not create an approval requirement for ordinary camera
or layout choices.

## Apply the cases to an actual review

For a competing-realization review, follow the
[input-reader procedure](../../references/runtime/prompt-composition.md#competing-realization-test).
Give the reader the exact delivered text, controls and media, including only
reference roles carried in that input. Withhold planning criteria, the preferred
construction, history and rejected candidates. First establish what complete
depiction the input communicates. For an interacting construction question,
trace the relevant conditions through one arrangement, state and presentation;
distinguish a workable construction, a supported conflict and an unresolved
construction. Restating the demanded result does not establish coexistence.
Then compare that reading with the
authoritative request and applicable sources. If the same reviewer performs
both steps, provide the request and sources after the input-only reading.
Reconsider derived criteria against those sources; they are interpretations,
not additional authority.

For a returned artifact, first provide only the candidate and necessary access
information. Record observations with locators before revealing the criteria
and intended portrayal. Then compare with the prepared requirements and any
applicable references. Distinguish later criterion-guided inspection from the
first reading. If one production context performs both roles, record author
self-review and the limitation; do not call it independent or a blind study.

Use `pass`, `fail`, `indeterminate`, `not-assessed` and `not-applicable` for
their existing meanings. An inconclusive hard criterion cannot support
selection. Link each failure to the responsible repair or an unresolved issue.
A repair addresses the requirement, construction, presentation, rendition,
reference, realization or execution layer implicated by the evidence. Preserve
the previous candidate and review, and follow ordinary task and authorization
requirements for another external request.
