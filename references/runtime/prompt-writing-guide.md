# Prompt Writing Guide Runtime

## Activation

Use this runtime when a final prompt is rendered as portable text or for a named model or interface, or when the user asks about any of these:

- prompt order
- comma-separated tags
- parentheses, square brackets, and explicit weights
- LoRA strength
- negative-prompt handling
- Textual Inversion
- prompt-length pressure
- controlled comparison of one term

Resolve the rendition at the scope requested. An exact model or interface uses
its active record and one adapter; an external target can use acquired provider
evidence while recording a missing catalog definition. A family-oriented text
draft uses the applicable family guidance and keeps checkpoint and execution
choices open. A portable prompt uses interface-neutral guidance. Preserve the
depiction through each of these scopes.

## Resolve the active guide

Each model family reads a prompt its own way: rating terms, multi-word tag spellings, working weights, and the blocks of a rendition and their order all differ. A rule proven on one family and handed to another can change the request without the intended effect.

The model record's `prompt_input` identifies the selected input workflow and
its evidence. Tag-based records also name their owning family in
`prompt_dialect`; the `prompt-dialects` resource and scoped guide sections
describe that family's rendition. Resolve the active model in one step:

```bash
python scripts/prompt_dialect.py --model <model-id>
```

It returns:

- the exact input mode, forms, vocabulary IDs, basis and vocabulary-search requirement;
- that family's tag grammar, block order, and quality, rating, period, and inert vocabulary;
- the guide sections that apply, and the sections withheld because they belong to another family;
- the record's own recommended text, parameters, and sizes.

A descriptive record uses its declared natural-language or structured-caption
forms. An unresolved record remains unresolved; absence of a tag family does
not establish prose input. A `none` record has no text prompt surface.
`--list` names available families; `--dialect <id>` supplies a family's guidance
for inspection or a family-oriented text draft. A requested tag rendition still
uses the actual dictionary search described in [Vocabulary](prompt-vocabulary.md).
Family guidance establishes no individual model's input contract or execution
readiness. For an unknown external
target, omit `--model` from route reading and retain interface-neutral wording
until acquired evidence establishes the input contract. Reading a family
section supplies no unsupported parser syntax.

Add a family by adding a dialect entry with its sources; the scripts stay unchanged. Its regression test is `scripts/prompt_dialect_smoke_test.py`. `schemas/prompt-dialect.schema.json` validates the dialect resource, and `schemas/prompt-writing-guide.schema.json` validates the guide.

Read the complete `guide.universal` and `guide.dialect` sections returned by the
resolver before writing the final model-facing rendition. The `withheld` list
identifies sections for other families and needs
no further read for this rendition. The selected model report also supplies its
guidance card; catalog execution fields need inspection when the requested
handoff or execution uses them. Reuse complete applicable guidance already read
in the current context.

Resolve the guide on its own through the same explicit pack state when its
resource is needed for direct inspection:

```bash
python scripts/pack_cli.py resource prompt-writing-guide
```

When reading the resource directly, read its universal sections and the complete
sections belonging to the selected family. When no enabled pack binds a guide,
continue under the selected adapter and exact model or provider evidence.

## Interface rendition

[Production direction](production-direction.md#choose-the-expression) owns the
depiction and its ongoing construction judgment. Use this guide to carry that
meaning into the actual interface, including during revision. Interface
evidence can expose a wording problem or a consequential limitation; resolve
the affected question within that same direction and authorized scope.

For an exact target, select the interface, its catalog record or acquired
external contract, and one adapter. A family-oriented draft uses that family's
supported common wording; model-specific recommendations stay with an exact
selection. A portable rendition keeps interface-neutral wording while the
target remains open. For a catalog target,
resolve service weighting through [Explicit Prompt Weighting](prompt-weighting.md)
and its family through `scripts/prompt_dialect.py --model <model-id>`.
An external target uses only parser behavior its evidence supports. Rules for
another family stay unapplied.

Honor the requested input form within the target's evidenced capabilities.
A request for tags receives tags; a request for descriptive direction receives
prose. Evidence that a model accepts both forms does not select a mixture.
Retain the complete intended depiction in the authoring context and adapt its
realization to what the selected input can express. Apply
parser-specific separators, attention syntax, LoRA notation, negative transport,
embeddings or editor shortcuts only when the active interface supports that
exact behavior.

Investigate unresolved wording through the catalog, vocabulary or relevant
source. For a tag-based rendition, use the mandatory search in
[Vocabulary](prompt-vocabulary.md#select-wording-for-a-tag-based-model) for its
actual positive and negative terms. Reading a dictionary or knowing a term
does not replace that search. Inspect candidate definitions, usage notes and
the selected model's evidence. Prefer existing vocabulary, including a close
synonym, when it preserves the intended meaning, scope and degree. An unlisted
expression can preserve a requirement that the available terms would lose or
change. Retain such wording in the requested input form with its intended use.
Descriptive input needs no invented terminology investigation when its sources
already suffice.

Search results and guide examples supply candidates and grammar demonstrations.
Membership establishes wording evidence rather than image correctness or
learned effectiveness. Integrate useful wording at its selected scope; a source
or populated field needs no separate clause when its meaning is already carried
by the prompt and supplied media.

The Skill-using agent decides which rules are relevant. The exact model or provider contract decides what the interface can receive. The guide governs rendition; image intent and visual authority remain with their owning plans.

### Carry the construction into supported means

Transfer the intended picture, not the surface form of another model's prompt.
A prose instruction can bind an actor, action, location, condition and degree
in one sentence. A list of individually relevant tags may leave those relations
unbound. Conversely, a model's learned compact term can express a useful visual
construction more directly than an explanation. Resolve the actual target's
behavior through its evidence and inspect the generated image.

Before rendition, distinguish the requirements that must survive from the
chosen means that can change. The request's subject, required copy, intended
effect and adopted design remain applicable as requirements, even when a target
cannot realize them all. A particular layout, lighting device or verbal
formulation may be an agent-selected means. Change an open means when target
evidence requires it. Keep an exact requirement unresolved when no available
method can satisfy it; wording alone cannot remove that limitation.
The [visual construction reference](../finishing-layers-specification.md)
supplies relationships to consider while making that choice.

| Construction to preserve | Rendition question |
| --- | --- |
| A recognizable subject in a new situation | Which appearance details are supported by actual delivered media, which must be expressed in text, and does the target support that reference operation? |
| A gesture or interaction | Do the selected terms express who acts on what, or only name the participants and objects? Retain a supported phrase or conditioning method where the relationship needs it. |
| A hierarchy of large shapes, light and detail | Which terms describe the visible organization? A mood or quality label alone does not carry the selected contrast, spacing or focal relationship. |
| Interlocking bodies, lettering, objects or graphic marks | Which form covers which at the consequential crossing, with what opacity and extent? A generic overlap or foreground term can leave the intended relation unresolved. |
| A designed object with a function | Which shape, attachment, contact or in-use evidence makes the function visible? Preserve that construction rather than reducing the design to its theme name. |
| Several views or multiple subjects | Can this target bind the views and subjects coherently in one request? Use supported regional controls or actual separate operations when required and available. |
| Exact readable copy | Can this target produce the required spelling, script, size and placement? Preserve the copy and choose an evidenced text or composition operation when generation alone is insufficient. |

A tag rendition selects visual concepts using the dictionary's recorded meanings
and usage, with the target's vocabulary and ordering. Start from what makes the whole reference
recognizable: the relationship of large forms, the color and value treatment,
the density and movement, the viewpoint and surface, and the depicted content.
Choose a compatible combination that approaches that effect within the target's
ability. This is a new rendition of the picture, not a sentence-by-sentence
conversion of a descriptive prompt. More tags do not necessarily preserve more
meaning; conflicting concepts, dilution and unbound attributes can move the
whole result away from the source.

Separate the depicted content from the checkpoint's learned controls. Subject,
action, viewpoint, material, light and color terms describe the selected picture.
Quality, aesthetic, period, rating and dataset controls can condition a different
part of its learned distribution; they do not supply a missing composition or
set output pixels. Select them for the intended treatment and exact version.
A quality ladder supplies alternatives, not a requirement to stack every band;
a period label refers to that model's corpus grouping, not the current date.
Use the selected dialect's evidence and scoped guide to decide which controls
contribute, and leave an unneeded category unfilled.

Training-caption order, a publisher's example and a reusable recommended prefix
are different evidence. Preserve the exact target's documented groups where
applicable, then keep related content together under the selected encoder and
parser. Neither a quality-first family baseline nor a training order proves a
single optimal sequence for every picture. During a comparison, hold order fixed
unless placement is the change being investigated.

Use the available vocabulary to suggest a construction at the precision it can
support. A perspective or motion term can influence a whole picture without
specifying every limb; a palette or lighting term can influence its treatment
without assigning each color to a precise region. Keep remaining uncertainty
explicit in the handoff. Do not append prose instructions or turn them into
comma-separated pseudo-tags. Use weights through the selected parser to adjust
a concept's influence. An unlisted tag or parser token remains available under
the selected input form and parser; the dictionary is not a whitelist. Quality prefixes,
negative stacks and parser syntax retain their exact model and interface scope.

If a requested detail is beyond the selected tag input, retain it in the
source specification and say what the tag rendition approximates or cannot
control. A useful approximation should still pursue the whole visual effect;
it need not retreat to an ordinary unobscured character portrait. Offer another
production method only when it serves an unmet requirement and its actual
availability is established. An optional alternative does not silently replace
a requested tag prompt, and a proposed later operation is not completed work.
Natural-language direction remains a separate rendition for a compatible model.

Treat reference images, regional conditioning, masks, pose controls, embeddings
and composition tools as actual capabilities with separate contracts. A model
family name supplies none of them. When a target has no suitable reference
input, a text description may carry recognizable features, but it does not
establish the same identity fidelity as an observed reference-conditioned
result. Record the actual input and assess that limitation against the task.

Readable text and integrated lettering can require different production
methods. Typesetting can preserve an exact message placed on the image surface.
It does not by itself create a character's contact with a letter, lettering
wrapped around a curved object, or a sign's physical light and occlusion.
Choose a supported operation that preserves the selected relationship, then
inspect the complete assembled result. Keep the exact copy at its owner and
record any separately executed generation, editing or composition. A proposed
later step is unfinished work, not a successful rendition. Do not remove fixed
copy or relabel decorative pseudo-lettering as the requested text to fit a
target's weakness.

Read compact wording for its effect on the complete construction. For example,
a monochrome figure against a colored graphic field needs the treatments to
remain in their assigned regions. Global color and monochrome terms can compete
without expressing that division. A group thrusting from depth needs near and
far figures, overlap and a shared direction; a group tag plus a foreshortening
tag leaves those relations open. A small rider on a thick, compressed vehicle
needs their scale contrast, not a global cute treatment that makes both equally
small. Use searched terms for the parts they actually name and a supported
phrase or control for the unresolved relation. Check the entire resulting
picture, including any default framing or treatment that those terms introduce.
When a crossing organizes the picture, preserve its specific parties and degree
through rendition. An opaque mark across a body, an outlined word behind it and
a pattern printed on clothing are different constructions. Dictionary terms
for their parts do not establish that a particular target can bind the relation;
use supported phrasing or controls and inspect the returned image. A readability
repair must retain the commissioned construction or acknowledge the changed
relationship.

Keep a model's weak text handling separate from its visual vocabulary. A
tag-oriented model may express an extreme crop, grouped dark masses, floating
objects, colored rim light or a drawn surface without reliably forming a
specific sentence. Preserve those expressive choices when resolving the text
method. Equally, substituting an empty rectangle for lettering that supports a
body loses a spatial relationship, even if the rectangle is reserved for later
copy. Plan the actual image, glyph shape, support and final assembly together
when that relationship is required. These are construction questions, not
claims that any named checkpoint or unverified control can execute them.

A picture made by a different engine establishes only that engine's response
to its exact input. Its ability to interpret a tag sequence or additional prose
cannot validate the target checkpoint's vocabulary response, binding, text,
negative handling or reference support. Do not count such images or their
similarity scores as target-model results. When a cross-engine illustration is
useful and authorized, retain its exact input, actual engine and separate
purpose. Target-specific generation remains untested until that target runs.

## Describe the intended result first

Lead a prose rendition with the artifact or edit and its desired result, then
establish the situation needed to understand its action, appearance,
relationships, degree and reference uses. The receiving model has the delivered
input; the agent's conversation and source records are separate knowledge.
Supply the premises selected through
[Production direction](production-direction.md#choose-the-expression) where
they make dependent instructions intelligible. Narrative or emotional intent
can guide the current performance, including subtlety or a requested double
reading. Keep authoring conclusions beyond this depiction at their owners.
A tag interface retains its evidenced hierarchy and uses supported terms and
channels for the closest available realization. Keep requirements beyond that
input's control in the handoff under the adaptation procedure above; do not
translate source notes into additional image tasks.

Write the selected depiction as direct instructions. Adopted design properties
state what the subject is; the chosen scene states what it is doing and how it
appears here. Keep investigation history, selection commentary and routine
confidence qualifiers in the authoring context. Include source roles, conditions
or uncertainty in the delivered input when they change the intended depiction
or how the receiving model should use its references.

Use the direct name of an activity, state or relationship when it carries the
intended meaning. A useful concept can carry a connected visual construction:
`selfie` relates subject and camera, `foreshortening` relates near and far form,
and `translucent glass` relates a material to transmitted light. Understand that
construction before choosing its wording. A familiar term can be more suitable
than a detailed physical explanation, while a broad label can leave the central
action unresolved. "Holding a tool" does not preserve "passing a tool to a
colleague." Keep the latter relationship through a phrase or supported tag
combination when one dictionary entry cannot express it.

Select concepts for the desired appearance, then retain its distinguishing
choices. A glass bird, a bird inside a glass vessel and a bird-shaped reflection
require different constructions despite sharing nouns. Material, viewpoint,
performance and finish words can work together; they are not independent
slots to maximize. Add wording for a meaningful distinction, an explicit fine
requirement or an evidenced target weakness. A faithful recreation can require
many such distinctions. Ordinary consequences of a selected concept need no
separate clause unless the intended result depends on controlling them.

Keep each word's contribution at its own scope while combining it with the
others. Clothing state and visible extent are different choices. An emphasized
feature can remain in a detailed surrounding scene; emphasis does not select
one depth-of-field treatment. A reciprocated action specifies the participants'
involvement, while their exact orientation is a staging choice. Develop the
combination that carries the picture, including a needed relation or degree
when a compact term leaves it open.

Use the dictionary to discover related concepts as well as canonical spellings
and close synonyms. Read the definitions and their modifier scope before
selecting a candidate. A lexical definition explains a word; a model-scoped
observation supports a claim about its response. Neither a dictionary entry nor
a successful sample proves that a term is a universal quality control. Quality
labels, artist or style identifiers, embeddings and parser syntax retain their
actual scope. Translate the visual function when moving between interfaces;
do not preserve an unexplained token merely because it occurred in a source.

For a corrective rendition, state the selected replacement or remaining quality
before refining its boundaries. Carry its necessary premises and the preserved
meaning from the accepted baseline and assigned references. A direct exclusion
is complete when only that boundary matters. Required negation, modifier scope and a
supported negative channel remain available; an affirmative alternative need
not be invented for each exclusion. Judge how the full input defines the wanted
image, rather than counting negatives or requiring positive-only wording.

Synthetic example: the requested result is a richly decorated hall with a calm
visual hierarchy. "Carved bands frame broad arches, with quiet wall areas
between them" states a possible result. A required exclusion of lettering can
remain alongside it. The carving and spacing explain the desired richness and
order; the exclusion protects a different boundary. If a later image is too
cluttered, revise the distribution and density while retaining the requested
decoration, then reread the complete input with its references.

## Weighting and prompt pressure

Use attention weighting only to express a real priority in a compatible parser. Large weights are the wrong repair for contradictory anatomy, camera, action, or reference roles. Parentheses, square brackets, and numeric weights are interface syntax rather than universal prompt language.

A weight changes conditioning; it does not establish what a term means or which subject it concerns. Resolve ambiguous wording and reference roles before raising its weight. Reducing a positive weight, removing its term and moving the term to a negative channel are not generally equivalent; use [weight and channel semantics](prompt-weighting.md#weights-and-conditioning-channels) to choose the intended operation. Use dictionary definitions and target observations as evidence, then inspect the result. An unlisted descriptive phrase may still be appropriate; absence from a dictionary is not a semantic verdict.

Assume nothing about a universal 75-token ceiling: prompt capacity, chunking, and truncation are properties of the active encoder and workflow. Read the applicable model adapter for its encoder, parser and guidance behavior, selected under [Interface rendition](#interface-rendition). A token is neither a word nor a tag, and concatenated chunks are not one long transformer context. Keep consequential concepts together within the supported path, and keep required semantics even when a remembered number argues for cutting them.

Remove incidental detail that contributes no requirement or selected effect. Retain all specificity needed for identity, visible construction and the chosen depiction, even when that requires a detailed prompt. Preserve the complete canonical identity and scene state at their owners. An omitted detail needs no replacement permission, exclusion or instruction to reveal it.

Use the `negative-policy` resource, available through `python scripts/pack_cli.py resource negative-policy`, to assess applicable sources; a tag family's form is the `negative_form` that `scripts/prompt_dialect.py` returns. Keep required exclusions and corrections scoped to their intended subject, region or failure. A source example's negative can exclude an intentional medium, layout or color treatment, so select its terms by their role in this picture. Resolve a real contradiction by returning to the brief and source authority, then revise the conflicting wording. A repeated word across channels can carry different scopes; the author judges the combined meaning. When exclusions accumulate, use [Production direction](production-direction.md#observe-and-repair) to resolve a missing target or unclear scope before adding another boundary. Retain necessary exclusions.

## Controlled comparison

When the task is to test whether a term, placement, weight, LoRA strength, or negative token changes the result, follow the guide's controlled-comparison section. Hold the remaining generation conditions constant and change one variable at a time. Record reference content and ordering as well as prompt and settings. If several change, compare the complete setups without attributing improvement to one change. Treat a result as bounded evidence, not a universal model verdict.

## Read the rendition back before it is sent

Inspect the exact rendition with the selected parser. Structural checks locate broken delimiters, malformed weights, invalid conditioning clauses, unsupported channels and declared length violations. The report also retains dictionary and dialect evidence for the author's reading.

This inspection supplies the exact positive and negative channels, controls,
actual media and parser evidence to the ongoing judgment in
[Observe and repair](production-direction.md#observe-and-repair). Keep any
missing premise, changed meaning or added task with its assessment in the
existing review. A source instruction can govern an author's state or adoption
decision without belonging in the renderer's request. Equally, a prior event can be
necessary context for the current performance even though it is outside the
frame. Preserve that distinction in translations, revisions and transport.

```bash
python scripts/check_tag_prompt.py --weighting sdEmbeds --dictionary <prompt-vocabulary/dictionary.json> --prompt "<the rendition>" --negative "<the negative>" --model <model-id>
python scripts/check_tag_prompt.py --weighting sdEmbeds --dictionary <prompt-vocabulary/dictionary.json> --prompt "<the rendition>" --dialect <dialect-id>
```

The example assumes an explicitly selected sdEmbeds parser; use `--weighting compel` for Compel or `literal` when no weighting control is selected. Independent conditioning clauses are checked separately and the original text is retained.

The checks read the resolved vocabulary resource and retain matched definitions, usage notes and declared dialect guidance. `--model` adds the record's declared prompt lengths and negative channel. `--dialect` names an evidenced family directly; an unknown ID is answered with the available IDs. Dictionary absence, repeated words, count terms, rating terms or lexical overlap do not establish a semantic failure.

Output is JSON on stdout with `syntax`, parsed `channels`, structural `findings` and the resolved dialect evidence. A `problem` describes a mechanical contract violation and returns exit status 1. A dictionary path that is not a file exits with a message. Preparation blocks mechanical problems; the author reads the complete positive and negative rendition with its actual media and judges the resulting picture. Its regression test is `scripts/check_tag_prompt_smoke_test.py`.

## Failure policy

Four shortcuts are refused:

- guessing parser support from a model family name;
- automatically adopting a sample quality or negative stack as a reusable default;
- converting a Textual Inversion token into generic prose;
- assuming a negative channel exists.

The default restriction does not prohibit selecting individual documented controls
for the current rendition. The author chooses their content, channel, placement
and supported weight from the intended picture and exact-target evidence, even
when no reusable recommendation string is declared. Keep that decision distinct
from an automatic merge and from a claim of measured improvement.

When guide advice conflicts with a reviewed model record or adapter, the model record and adapter own the transport. When interface behavior is unknown, keep the semantic prompt portable and stop before claiming unsupported syntax or parameters.

## Regression

```bash
python scripts/prompt_writing_guide_smoke_test.py
```

The regression uses a fictional temporary guide. It leaves every owner-maintained pack's current rules, examples, wording, and section count uninspected and unfixed as expectations.

### Final-request dictionary evidence

For an explicitly tag-based model, preparation requires the searched vocabulary
selection for its text, target and parser. Verification performs the searches
again against the current dictionary and selected dialect. Missing evidence or
an unresolved wording choice cannot be replaced with an empty construction
record or a claim that the terms were already understood.

`prepare` also checks the actual sealed positive and negative text after model
recommendations and transport conversion. Mechanical
`problem` findings stop preparation. The complete dictionary and dialect evidence
is saved in `execution_plan.prompt_check` for the existing rendition review.
Inspect that evidence with the complete request before approving it. A known word
can still be wrong for the intended anatomy or garment, and an unlisted phrase
can express it correctly. Fix the authored wording when meaning is wrong.
