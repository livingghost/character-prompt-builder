# Species architecture reference

## Conditional catalog examples

Every literal catalog ID in this document is actionable only when its owning pack is present, enabled by the selected state, and the exact ID resolves in the active catalog. If an example ID is absent, use the morphology contracts and geometry guidance directly, search enabled records for genuinely matching knowledge, or proceed without preset support. Never substitute an unrelated ID or assume that an external-pack example belongs to the default pack.

## Canonical morphology layer

Species scaffold heuristics are diagnostic aids, not the complete anatomy record. For a recurring subject, original species, hybrid, ordinary animal, creature, robot, or android, use the canonical stack in [Morphology and species contracts](morphology-and-species-contracts.md):

1. `species-morphology-profile` declares the valid body topology, feature counts, attachments, surfaces, expression channels, capabilities, population variation, meaningful absences, and near-species differences.
2. `individual-morphology-contract` resolves exact measurements, counts, instance IDs, markings, asymmetries, damage, grooming, nails or claws, tools, and personal expression behavior for one subject.
3. `resolved-morphology` carries the shot-visible anatomy after state, pose, clothing, crop, and occlusion are applied.

Do not use a scaffold family as a substitute for the species profile. A fictional species can be defined entirely through direct topology and feature records without borrowing a real species noun.

A species noun in a prompt is both an identity statement and a geometry vote: every mention can re-summon that species' default proportions from the generator prior. This reference records prompt-prior scaffold families so authors and composing agents can diagnose facial architecture before choosing geometry wording. It is not a complete biological taxonomy, and it does not authorize a silent species substitution. Enabled `module` records in category `species` stay deliberately minimal; this document carries the family-level geometry they invoke.

## How to use

When the user or Character Identity Contract states a species, preserve that identity. Read the target design's face, compare its ear shape, ear set, ear orientation, muzzle reach, muzzle depth, nose proportions, jaw mass, cheek volume, and eye placement against the scaffold families below, then write species-neutral geometry that supports the requested identity.

Use a second species noun only when the user approves a disclosed scaffold modification. The agent must state which identity wording is being supplemented, which scaffold noun is being introduced, and why the change is necessary. A Character Identity Contract outranks the scaffold heuristic.

Reverse calibration follows the same order: measure the reference geometry first and compare it with the family rows. When the selected pack state provides `cpb-resource:species-scaffold-map`, also consult the resource resolved from its explicitly selected provider. Preserve the approved identity and use direct geometry wording for any mismatch or absent resource. Ears carry three independent axes: shape, set, and orientation. A diagnosis or record states all three.

Mixed designs are normal in kemono and hybrid art. Their coat, tail, markings, horns, mane, hairstyle, and other visual carriers can preserve identity while the face uses carefully described geometry. The package still treats any different species noun as an explicit modification, not an invisible implementation detail.

An enabled pack may also carry curated `creature-anatomy` module records that state one lineage's anthro anatomy grammar (surface, ears, muzzle, limbs, appendage, and lineage-tied dimorphism). Retrieve the matching record by lineage name and use it as generic species-neutral anatomy knowledge beneath the identity contract: it supplies the drawable baseline, while the user's declared species and the identity contract keep authority over the actual subject.

The map covers every current species ID. A `direct-geometry-required` result means the family table does not supply a strong enough prior, so the prompt must carry the geometry directly. See `references/prompt-composition-geometry.md` and the troubleshooting entry "Calibrate the species scaffold while preserving the identity anchor."

## Reference-based feline and canine disambiguation

The user statement and Character Identity Contract are the species authority. A stylized reference may enlarge feline ears, sharpen one ear tip, compress a canine muzzle, or distort the outer contour through low-angle perspective. Those effects do not authorize a silent family relabel.

When feline and canine silhouettes appear ambiguous, inspect three correlated systems before choosing geometry language:

1. **Muzzle projection and shadow:** a large-feline muzzle is short, deep, broad, and nearly parallel-sided, so its side-plane and under-muzzle shadow remain compact and block-like. A canine muzzle projects farther and narrows toward the nose, producing a longer wedge-shaped shadow.
2. **Ear architecture:** large felines usually carry rounded or softly squared tips with substantial base width; wolf-like and upright-eared canines usually carry pointed tips and a high-set triangular outline. Record shape, set, and orientation separately. Stylized exceptions remain possible, so ears support the decision rather than deciding it alone.
3. **Nose-pad depth and placement:** a stylized feline nose pad often reads relatively thin front-to-back and sits close to the blunt facial front. A canine nose pad usually reads thicker and projects at the terminal end of the muzzle. Use form and cast shadow rather than black color alone.

Markings, fangs, ruffs, and body mass are weaker family cues because both families share them in anthropomorphic art. Route the complete face through one selected scaffold, then preserve the supplied coat, markings, identity details, and expression.

## Family architectures

### Canine (wolves, foxes, jackals, dholes, dogs, coyote, raccoon-dog)

Ears usually tall, pointed, upright, and set high on the skull, with breed-specific
folding or shortening where the approved identity requires it. The muzzle projects
forward relative to its depth and usually tapers along its length. The nose pad sits
at the forward tip and often reads as a thicker rounded volume with a visible lower
edge or underside in profile and low-angle views. A visible stop separates brow and
bridge. The jaw follows the taper and the chin stays comparatively light. In flat 2D
art, the projecting muzzle often produces a longer wedge-shaped shadow beneath the
front of the face. Carriers include brush tail, fangs, and neck ruff. The noun summons
a forward-projecting tapered snout and pointed-ear prior; dog breeds shift it
(bullmastiff and boxer shorten and deepen it, borzoi lengthens it, fennec enlarges the
ears), and the raccoon-dog remains canine despite the raccoon-like mask.

### Feline (tigers, lions, leopards, jaguar, panther, cougar, lynx, cats)

Ears usually short, rounded, wider than tall, and set toward the sides, with rounded
upright tips; stylized kemono designs may lengthen or sharpen the ear silhouette, so
ear shape remains supporting evidence rather than the sole classifier. The muzzle is
short and deep, with compact reach against generous bridge-to-jaw depth and side
planes that stay near parallel toward a blunt front. The nose is broad and wider than
tall, often reading in stylized art as a flatter thin dark plate set high on the muzzle,
with the mouth directly beneath and a compact chin. Heavy jaw and cheek mass keep the
front broad. In flat 2D art, the compact muzzle often produces a short block-like shadow
beneath the nose and mouth rather than a long wedge. Carriers include long tail,
retractile claws, chest ruff in stylization, and mask, stripe, or rosette markings. The
noun summons the short deep face for free; lynx and caracal add ear tufts, cheetah
lightens the build and narrows the face, and house cats enlarge the eyes and shorten the
muzzle further.

### Ursine (brown, black, polar, panda, sun bear)

Ears small, round, set wide and high on a massive skull. Muzzle short to
medium and thick, round in cross-section, ending in a rounded ball with a
large nose pad wrapping forward. Little visible stop; the forehead flows
into the bridge. Heavy neck, jowly jaw. Carriers: stub tail, huge paws,
shoulder hump on brown bears. The noun summons roundness everywhere; polar
lengthens and lowers the head, panda carries the eye patches.

### Hyena (spotted, striped, brown)

Feliform despite the dog-like look. Ears rounded (spotted) or tall and
pointed (striped), set wide. Muzzle broad, deep, blunter than a canine's,
on a massive skull with an extremely heavy jaw. High shoulders sloping to
low hips. Carriers: spotted or striped coat, mane along the spine, bone-
crushing grin. The noun summons the sloped back and heavy neck.

### Mustelid (otters, ferret, badger, wolverine, skunk)

Ears small, low, rounded. Muzzle short and rounded on a small skull, the
head flowing into a long low flexible body. Carriers: thick tapering tail,
short limbs, masks and dorsal stripes. Wolverine and badger deepen the jaw
and widen the skull toward a small-bear read.

### Procyonid (raccoon, red panda)

Ears short, rounded, often pale-rimmed. Muzzle short and pointed with a
delicate taper, on a rounded face with a bandit mask. Carrier: the ringed
tail. Distinct from the raccoon-dog, which is canine.

### Bovid and caprine (bull, bison, buffalo, yak, goat, ram)

Ears lateral, often below the horns. Muzzle long, deep, and squared, with
a broad flat front and wide-set nostrils on a naked muzzle pad. Horns are
the primary carrier and sit on the skull, ahead of the ears. Massive neck
on bulls and bison; goats and rams lighten the skull and add the beard and
the rectangular pupil.

### Cervid (deer, elk, reindeer, moose)

Ears large, lateral, mobile. Muzzle long and slim with a soft taper and a
small dark nose; moose deepens and overhangs it heavily. Antlers, not
horns, are the carrier, branching and seasonal. Slim neck against the
bovids' mass.

### Equine (horse, zebra)

Ears tall, mobile, set high. Head long and deep as one wedge from brow to
lip, with the nostrils flaring at a squared front and the mouth low. Mane
along the crest and the tail carrier. Zebra adds the stripe system.

### Suid (boar, warthog)

Ears pointed to rounded, lateral. Muzzle long and cylindrical, ending in
the flat mobile disc of the snout. Tusks curve from the lower jaw, and the
warthog adds facial wattles. Heavy wedge-shaped skull into a thick neck.

### Lagomorph (rabbit, hare)

Ears very tall, the dominant carrier. Muzzle tiny and rounded with the
split lip and constant nose; large eyes set lateral and high. Hare
lengthens limbs and ears and leans the face.

### Rodent (squirrel, rat, mouse)

Ears round, prominent. Muzzle small, pointed, whiskered, with prominent
incisors as the carrier. Squirrel carries the plume tail, rat the naked
tapering one.

### Marsupial (kangaroo)

Ears tall, rounded-tipped, mobile. Muzzle long, slim, deer-like with a
clean taper. Carriers: the counterbalancing tail, the long haunches, the
pouch line in stylization.

### Primate (gorilla)

Ears small, flat to the skull. Face flat with a heavy brow ridge, broad
flat nose, and a deep protruding jaw; the muzzle reads as jaw mass, not as
a snout. Carriers: the sagittal crest, silver saddle, knuckle-walk arms.

### Crocodilian and monitor (crocodile, alligator, monitor, komodo)

Head one long flat wedge, jaw-dominant, the eyes and nostrils riding on
top. Alligator rounds the snout that the crocodile keeps in a V; monitors
narrow it and add the forked tongue. Ears are absent as shapes; carriers
are scale plates, dorsal ridge, and the heavy tail.

### Avian (eagle, raven, owl)

The beak replaces the muzzle entirely: raptors hook it, corvids straighten
it, owls bury a short one in the facial disc. Ears are absent as external
shapes (owl tufts are feathers). Carriers: feather regions, talons, tail
fans. A face calibrated in muzzle language cannot land on an avian
scaffold; the beak needs its own geometry.

### Marine (shark, orca)

No external ears. Shark carries the underslung jaw beneath a pointed
rostrum with gill slits as the signature; orca carries the rounded
melon-fronted head, the eye patch, and the dorsal fin. Smooth-skin
surfaces, not fur.

### Mythic (dragon, gryphon, hellhound, werewolf, dire wolf)

Composite by definition: state which family supplies each region. A
default dragon reads reptilian-equine in the head with horns free-placed;
a gryphon is avian forward of the shoulders and feline behind; hellhound
and dire wolf are heavy canines with the mass turned up; a werewolf is a
canine scaffold on a human frame. Because the priors are weaker here, the
prompt must carry more of the geometry itself.

## Confusable pairs

Canine versus feline is the costly one: both carry fangs, ruffs, and
tails, but the ears (tall pointed high versus short rounded low) and the
muzzle ratio (long tapering versus short deep parallel) separate them at a
glance, and a short-deep-faced design prompted as a wolf will fight the
canine prior indefinitely. Raccoon versus raccoon-dog share the mask and
split at the skeleton: procyonid ringed tail against canine build. Hyena
versus canine split at the sloped back, the rounded ears, and the outsized
jaw. Bear versus heavy canine split at the ball muzzle with the wrapping
nose pad against the blunt-fronted muzzle with the nose riding high.
Fennec versus small feline split at the muzzle taper despite the shared
ear scale.

## Reference diagnosis when feline and canine cues compete

The user or approved Character Identity Contract is authoritative. The diagnostic is
there to preserve that identity, not to replace it. In stylized 2D references, classify
from a bundle of evidence rather than one conspicuous feature.

Use this order:

1. **Muzzle reach and depth.** A large feline keeps a short deep muzzle with a broad
   front and near-parallel side planes. A canine projects farther and usually tapers.
2. **Shadow footprint.** When perspective or coat markings obscure the visible outline,
   inspect the shadow under the nose, lip line, and lower muzzle. A compact feline face
   tends to make a short block-like shadow; a projecting canine muzzle tends to make a
   longer wedge-shaped shadow.
3. **Nose profile.** A stylized large feline often carries a flatter thin dark nose plate
   high on the compact front. A canine often carries a thicker rounded nose pad at the
   forward end of the muzzle.
4. **Ear-tip architecture.** Rounded large-feline tips and pointed canine tips are useful
   supporting evidence. Stylization, cropping, pose, and hybrid design can alter this cue,
   so it does not overrule stronger muzzle, nose, and shadow evidence.
5. **Cheek and jaw mass.** Large felines keep broad cheek pads and a heavy compact jaw.
   Canines retain more forward flow from bridge through muzzle and a lighter tapering chin.

Describe the complete approved scaffold affirmatively. If a generator keeps drifting, search the active catalog for a correction that explicitly covers feline/canine face-scaffold drift, inspect the resolved record, and review all five axes before changing any species wording. Core guidance must not assume that an optional pack supplies a particular correction ID.

## Reverse lookup

Tall pointed high-set ears with a long tapering muzzle, a longer wedge-shaped muzzle shadow, and a thicker nose pad at the terminal tip: canine. Short rounded or softly squared ears with a short deep parallel-sided muzzle, a compact block-like muzzle shadow, a relatively thin broad nose high and close to a blunt front, and heavy jaw mass: feline. Small round
wide-set ears on a massive round skull, ball muzzle with a wrapping nose
pad: ursine. Rounded ears, heavy blunt jaw, high shoulders over low hips:
hyena. Small low ears on a small head leading a long low body: mustelid.
Mask face, short pointed muzzle, ringed tail: procyonid. Horns ahead of
lateral ears over a squared deep muzzle: bovid. Branching antlers over a
slim soft-tapered muzzle: cervid. One long deep head-wedge with a squared
lip front and high ears: equine. Cylinder muzzle ending in a flat disc,
lower tusks: suid. Ears taller than the skull over a tiny muzzle:
lagomorph. Prominent incisors under a small pointed muzzle: rodent. Flat
face, brow ridge, jaw mass without a snout: primate. One flat jaw-wedge
with top-mounted eyes: crocodilian. A beak: avian. No ears and smooth
skin: marine. When a reference matches one row in the face and another in
the body, scaffold the face by its row and state the body's family
separately.
