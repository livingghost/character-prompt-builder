# Blind Image Evaluation Protocol

This protocol evaluates generated images. It is separate from structural validation, search regression, package hashes, and SVG fidelity checks.

## Candidate review and comparison studies

An ordinary production review decides whether one candidate meets its declared
criteria. Follow
[Production Execution](runtime/production-review.md#observe-before-interpreting)
to record direct artifact observations before applying the intended reading.
A separate observer can receive only the artifact before seeing its brief;
record that input boundary and its limits. When the producer reviews in the
same context, call it author self-review, not independent review.

The [competing-realization test](runtime/prompt-composition.md#competing-realization-test)
examines what a delivered prompt and its media permit before generation. It is
also distinct from a study of returned image quality. Neither procedure alone
supplies anonymous conditions, randomized presentation or comparable trials.
Use the comparison design below when claiming controlled blind-study evidence.

## Evidence boundary

A release may claim generated-image evidence only when the evaluated outputs, complete model inputs, target identity, target version, settings, repeat method, and scoring record are preserved together. A structural evaluation case is not an image-quality result. A retrieval pass is not evidence that the generated image is better.

## Comparison design

For each brief:

1. freeze the actual request, information boundary, target model, model version, interface, resolution, sampling settings, and available reference inputs;
2. prepare anonymous prompt conditions, such as no retrieval, broad retrieval, and curated retrieval;
3. keep all non-prompt settings identical;
4. use the same seed when the target supports it, otherwise use a declared repeat count;
5. randomize output order and conceal the prompt condition from reviewers;
6. score prompt quality and image quality separately;
7. preserve every output, including failures, until the comparison record is sealed.

Record unavailable controls as unavailable. An unexposed seed or backend version
limits causal and reproducibility claims; it does not become a known constant.
When dialogue supplies new information, compare the conditions at the same
information boundary or report the different boundaries explicitly. A change
to the requester setup, reference access or revision budget is a separate
condition. [Creative-direction evaluation](maintenance/testing.md#creative-direction-evaluation)
owns realistic requester and author roles.

## Image scoring dimensions

Read each complete image before applying the prompt, author rationale or
expected feature list. For a source comparison, inspect source and candidate
at comparable viewing sizes, with their identities concealed in the first
reading where the study permits. Preserve that observation before introducing
the actual brief, source roles and allowed changes. Explain the experience
created by the picture and the relationships that produce it: what attracts
attention, what holds together, how the viewer meets the subject, and what
continued looking reveals. Detail inspection follows a consequential question
from that reading, rather than defining the image's purpose in advance.

Then judge overall fulfillment and the dimensions relevant to the commission,
each with visible reasons. Applicable dimensions include:

- brief fulfillment;
- the organization and effect of the complete picture;
- identity and body-plan fidelity;
- camera, crop, support, and contact fidelity;
- expression and body-language coherence;
- representation grammar and medium fidelity;
- material and accessory fidelity;
- unwanted artifacts;
- overall preference.

Keep overall preference, whole-picture fulfillment and local correctness
distinct. A visually attractive image can fail identity, geometry or prompt
adherence. Conversely, accurate details can belong to a different construction
that fails the intended experience. For a reconstruction, explain the decisive
relationships that survive or change after accounting for permitted subject,
copy and design substitutions. Separate fidelity to the visible sample from
fidelity to an accompanying prompt when they differ. The prompt establishes
what was requested of the model, not what the image achieved.

Retain local findings without averaging away a missing central relationship or
using an overall preference to conceal a required failure. A source's partial
visibility, ambiguity or delayed readability can contribute to its construction;
judge them at the scope the commission establishes. The evaluation is neither a
count of present techniques nor a universal preference for clear boundaries,
complete figures, legible text or greater complexity. Record unsupported and
uninspected claims separately from observed passes and failures.

## Required record

A completed study records:

- evaluation ID and date;
- brief ID and language;
- subject domain;
- target model and version;
- complete prompts and negative transport;
- model settings, seed, or repeat protocol;
- reference artifacts and hashes;
- randomized presentation order;
- reviewer count and review method;
- actual reviewer inputs, reading order and source availability;
- per-dimension scores and reasons;
- output artifact hashes;
- exclusions and failed runs;
- conclusion scope and unresolved questions.

## Coverage

Report domain and language coverage with the results. Do not generalize an anthropomorphic-animal-heavy or English-heavy study to humans, ordinary animals, robots, creatures, hybrids, or other languages without matching evidence.

## Release claims

Until a completed blind study is bundled, describe the release as structurally and behaviorally validated, not image-quality proven.
