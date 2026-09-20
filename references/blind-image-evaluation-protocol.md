# Blind Image Evaluation Protocol

This protocol evaluates generated images. It is separate from structural validation, search regression, package hashes, and SVG fidelity checks.

## Evidence boundary

A release may claim generated-image evidence only when the evaluated outputs, complete model inputs, target identity, target version, settings, repeat method, and scoring record are preserved together. A structural evaluation case is not an image-quality result. A retrieval pass is not evidence that the generated image is better.

## Comparison design

For each brief:

1. freeze the target model, model version, interface, resolution, sampling settings, and available reference inputs;
2. prepare anonymous prompt conditions, such as no retrieval, broad retrieval, and curated retrieval;
3. keep all non-prompt settings identical;
4. use the same seed when the target supports it, otherwise use a declared repeat count;
5. randomize output order and conceal the prompt condition from reviewers;
6. score prompt quality and image quality separately;
7. preserve every output, including failures, until the comparison record is sealed.

## Image scoring dimensions

Score each dimension independently and record visible reasons:

- brief fulfillment;
- identity and body-plan fidelity;
- camera, crop, support, and contact fidelity;
- expression and body-language coherence;
- representation grammar and medium fidelity;
- material and accessory fidelity;
- unwanted artifacts;
- overall preference.

Do not replace dimensions with one overall score. A visually attractive image can still fail identity, geometry, or prompt adherence.

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
- per-dimension scores and reasons;
- output artifact hashes;
- exclusions and failed runs;
- conclusion scope and unresolved questions.

## Coverage

Report domain and language coverage with the results. Do not generalize an anthropomorphic-animal-heavy or English-heavy study to humans, ordinary animals, robots, creatures, hybrids, or other languages without matching evidence.

## Release claims

Until a completed blind study is bundled, describe the release as structurally and behaviorally validated, not image-quality proven.
