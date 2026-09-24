# Contributing to Character Prompt Builder

Thank you for improving Character Prompt Builder. It is an art-direction and prompt/reference Skill first; pack management, cache construction, and deterministic support tools serve that creative workflow. Contributions must preserve the separation among creative judgment, canonical production knowledge, deterministic support tools, series-owned state, and actual generation evidence.

## Project principles

- The agent remains the semantic and creative engine. Scripts retrieve, validate, hash, package, and preserve lineage; they do not replace art direction.
- User anchors outrank presets. A preset may support a selected direction but may not silently redefine the brief.
- Art direction exists before catalog adoption. Retrieval fills production gaps after the intended image is understood.
- A concrete style family is one coherent finish grammar, not a bag of interchangeable tags.
- Curated positive fields describe desired construction affirmatively. Failure modes and nearby misreadings remain scoped diagnostic knowledge.
- Generated media remains evidence until explicitly accepted.
- Visual contracts, event chronology, asset lineage, scene state, target binding, run evidence and adoption each have a responsible project record. Preserve those responsibilities rather than assigning them to an external application.
- Runtime text uses ASCII punctuation. Unicode em dash and en dash characters are not permitted.

## Before editing

Read the documents relevant to the change:

- [Preset System Contract](references/preset-system-contract.md)
- [Preset Authoring Standard](references/preset-authoring-standard.md)
- [Preset Workflow](references/preset-workflow.md)
- [Aesthetic Language](references/aesthetic-language.md)
- [Style Family Taxonomy Audit Contract](references/style-family-taxonomy-audit.md); resolve `cpb-resource:style-family-taxonomy-audit` from the selected provider for pack-specific decisions
- [Sparse-Brief Discovery Runtime](references/runtime/sparse-discovery.md)
- [Preset Maintenance](references/maintenance/presets.md)
- [Search Discovery Maintenance](references/maintenance/search-discovery.md)
- [Reference Corpus Visual Technique Observation](references/reference-corpus-visual-technique-observation.md)
- [Shared State Protocol](references/state-protocol.md)

Use Python 3.11 or newer. Core scripts use the standard library only. [Release Validation](references/release/validation.md) exclusively owns the exact publication environment and sequence, including the uv commands that create CI's Python 3.12 environment.

[`requirements-visual.txt`](requirements-visual.txt) holds each supported version range and [`requirements-tested.txt`](requirements-tested.txt) each release-validation pin; `requirements.txt` and the `pyproject.toml` `visual` extra read the ranges. When a distributed script changes a third-party import, update those two files, `DEPENDENCIES.md` and the checker's import names together. Do not list transitive packages unless package code imports them directly.

## Repository ownership map

- [SKILL.md](SKILL.md) owns the runtime router and core invariants; [references/runtime/](references/runtime/) owns conditional detailed runtime contracts.
- [packs/commons/](packs/commons/) is the minimal shipped commons pack.
- [PACKS.md](PACKS.md) defines the commons pack and independently authored additional packs.
- The repository-only `.gitignore` keeps the commons pack tracked while excluding every other pack below `packs/` unless project policy explicitly changes.
- [references/](references/) owns stable method and authoring documentation.
- [scripts/](scripts/) owns deterministic support and validation tools.
- [examples/](examples/) owns canonical reproducible examples.
- [package-manifest.toml](package-manifest.toml) owns product release metadata and the release allowlist.
- [MANIFEST.json](MANIFEST.json) is generated product-build metadata and must not be edited by hand.

Do not duplicate ownership. When information belongs to an existing canonical file, update that file and leave a link or pointer elsewhere.

## Preset contributions

### Choose the correct record type

Use an atomic module for one bounded production decision. Use a base scene for staging, support, contact, gaze, depth, and crop. Use a rendering profile for medium mechanics. Use a concrete style family only when line, form, value, highlight, color, surface, background, detail hierarchy, and domain overlays form one inseparable grammar.

Do not create a style family merely because a reference introduces a new subject, outfit, location, pose, palette, or mood. Compare the finish with the nearest existing families and record the actual production distinction.

### Curated records

A curated record must satisfy the [Preset Authoring Standard](references/preset-authoring-standard.md). It needs executable visual knowledge, adaptation invariants, nearby misreadings, valid domains, and enough detail to guide production instead of repeating its label.

Positive-facing fields must be affirmative. Put applicable exclusions in the resolved `cpb-resource:negative-policy` from the explicitly selected provider, the selected medium boundary, an activated correction, or an explicit user exclusion. Scene failure modes and module misreadings remain diagnostic-only.

### Vocabulary records

Vocabulary records are compact names and model-legible options. Do not inflate them into incomplete pseudo-blueprints. Runtime art direction and curated production knowledge provide the construction logic.

### Reference-derived work

Add source-backed Visual Evidence only when the user has supplied the source for this work and accepts the resulting derived evidence artifact in SVG format. The package must not embed or externally reference the raster payload. Source rights are not changed by vector derivation. Signatures, logos, protected identifiers, censor overlays, and source-specific text must not be promoted into reusable preset knowledge. Follow [Preset Research and Provenance](references/preset-research-and-provenance.md) and the generic [Source Notes](references/maintenance/presets.md#source-notes) contract. Record pack-specific history in `cpb-resource:source-notes` and cluster decisions in `cpb-resource:reference-cluster-mapping`, each resolved from the explicitly selected provider.

Separate stable anatomy from perspective, source placement from rendered light grammar, visible eye direction from inferred viewer relationship, stable identity from temporary state, and reusable craft from source-specific artifacts.

For anthropomorphic and creature identities, do not collapse human-like head hair, base fur or covering, mane, ruff, facial hair, and regional hair or fur into one tuft description. Stable entries define presence, boundaries, silhouette, section map, landmark-based length, density, direction, texture, color, clearance, and continuity as applicable. Temporary wetness, disorder, compression, sweat response, and styling remain scene-specific state unless an approved identity or appearance contract owns them.

### IDs and taxonomy

Canonical catalog IDs are stable semantic identifiers. When a taxonomy change changes an ID, update every internal reference, search profile, evaluation case, discovery lane, and documentation link in the same contribution. Every stored ID must resolve directly to a current record.

## State and the shot-request boundary

Stable identity belongs in a Character Identity Contract. Event-derived changes belong in state snapshots. A Visual State Projection decides what the current camera must show. Observed output remains evidence, not canon.

Validate an Adoption Receipt against the relevant artifact and scope. Receipt verification does not make the decision itself. Studio adoption and story-state adoption keep their own owners; do not create a second registry to handle exchange.

Shot handoff changes must keep the [shot-request schema](schemas/viewpoint/shot-request.schema.json), [template](templates/handoff/shot-request.template.json), [shot-request validator](scripts/shot_request.py), and [protocol documentation](references/state-protocol.md) aligned.

## Internal artifact governance

Core internal artifacts do not carry independent counters. Only distribution systems carry release identifiers; operational content is bound by hashes.

Internal schemas, protocols, templates, state artifacts, production specifications, generation packages, catalog indexes, and validation payloads do not carry independent release counters. Their identity and integrity come from:

- `artifact_type` where the artifact family needs an explicit discriminator;
- the current structural schema and validator shipped in the same product release;
- immutable semantic identifiers;
- canonical content hashes;
- `derived_from`, `supersedes`, effective story range, and other domain lineage where applicable.

Do not add fields such as `schema_version`, `protocol_version`, `manifest_version`, `package_version`, `revision`, or `adopted_version` to internal artifacts. Do not add `-v1`, `-v2`, or similar revision suffixes to protocol artifact IDs. When meaning changes, create a new semantic ID and record its lineage instead of incrementing a counter on the old ID.

The JSON Schema `$schema` declaration is intentionally retained. It identifies the external JSON Schema dialect used by validators; it is not a Character Prompt Builder artifact version.

External target evidence may include an API version, model version, editor build, or documented surface identifier when that value is necessary to reproduce an actual submission. Keep such values scoped to the target evidence they describe.

## Documentation

Run `python scripts/readme_smoke_test.py` after changing user-facing examples. It executes the marked example commands in temporary directories and verifies outputs and source-change behavior; live-send examples are checked without contacting a service. Keep the surrounding explanations accurate as well: executable commands do not establish prose completeness or artistic quality.

Keep the [README](README.md) focused on users, capabilities, installation, normal operation, evidence boundaries, and limitations. Contributor-only release and version-management details belong in this guide.

Every file path mentioned in the README must be a Markdown link unless it is part of a literal shell command inside a fenced code block. All file links must resolve inside the package. Keep canonical instructions and reference documents in English.

The writing rules in the repository guide apply here and to every reference, template and changelog entry:

- Say what a thing does, as an action: "the tool records every returned
  candidate". State a boundary at most once per section, and as who decides:
  "the author decides when a candidate becomes canon", not "the tool does not
  decide".
- One idea per sentence, about twenty words. Three or more items become a list.
- Prefer the general word. Where a product term must appear because the tools
  use it, put the general phrase beside it at its first use and use the general
  word afterward. Do not add a glossary, a preamble about the document itself,
  or a section that explains why other sections repeat.
- Show a real example next to any claim about output: an actual command's output
  or an actual record, trimmed, and labeled synthetic when it is a fixture.
- Delete a repeated principle and refer to the place it is stated. Longer is
  not safer.
- ASCII punctuation, no em or en dashes, English throughout.
- After changing README.md, run `python scripts/readme_smoke_test.py` and keep
  the executable example blocks byte-identical unless the commands changed.


## Product release management

The product release uses UTC CalVer: `YYYY.MM.DD.N`. `N` begins at 1 on a new UTC date and advances for each additional release that day. Preserve the dated release history; never reuse a published release identifier for different content.

- [package-manifest.toml](package-manifest.toml) is the authority for product name, release CalVer, `version_scheme`, `release_timezone`, license, release filename, and release allowlist.
- [pyproject.toml](pyproject.toml) represents the same release in normalized PEP 440 spelling (`YYYY.M.D.N`), not in a separate release scheme. Host plugin metadata and the distribution inventory are generated from the canonical manifest.
- Runtime scripts read product metadata through [scripts/package_metadata.py](scripts/package_metadata.py). Do not introduce hard-coded duplicate product release constants.
- Prepend the current release entry to [CHANGELOG.md](CHANGELOG.md), retaining prior entries and their original dates. A change log records released product content; it is not an internal artifact revision counter.
- Run `python scripts/release_contract.py` and `python scripts/release_management_smoke_test.py`. CI and release publication enforce the same contract; tagged publication also checks `--tag` against `v` plus the canonical release.
- The allowlist names packaged examples and the bundled commons pack explicitly. Additional installed packs do not become core distribution members implicitly.
- Rebuild generated metadata and executable examples before packaging. Runtime schemas, scenes, protocols, and evidence retain their content-based identities.

Content packs have independent UTC CalVer releases and stable UUIDv7 identities. The pack release describes the pack itself. The current manifest and record schemas are the complete parser contract: schema or semantic failure is reported directly. Every pack dependency names one dependency pack by UUID, not one of its releases. Read [PACKS.md](PACKS.md), [Pack Maintenance](references/maintenance/packs.md), [Pack Format Specification](references/pack-format-specification.md), and [Catalog Cache Lifecycle](references/catalog-cache-lifecycle.md) before changing pack behavior.

Searchable SVGs and evidence are `asset` records with pack-owned `primary_resource`, nonempty `resource_refs`, and matching artifact hashes. Stable runtime policies and indexes use manifest `resource_bindings`. If a locked pack changes, increment its UTC CalVer and rebuild `pack.lock.json`.

Generation packaging treats the reviewed prompt, negative, and one canonical `prepared-reference-set` object as one committed input. Catalog `inspect` returns the complete canonical record plus a compact linked-asset activation summary; `asset-lookup --summary` returns compact asset IDs and technical roles; full `asset-lookup` returns pack ownership, artifact resources, paths, media, and hashes for planning. None activates or prepares a reference. The required record-based path is full record inspection -> `scripts/reference_runtime.py plan` with one explicit `--record-use RECORD_ID=INTENDED_INFLUENCE` per adopted record -> `scripts/reference_runtime.py execute` -> Generation Package build -> verification. Use the same complete pack runtime context at every stage. The planner rejects an intended influence that the complete canonical record does not affirmatively support. The plan owns artifact choice, semantic role, precedence, source authority, prohibited influence, and the Surface and Lighting Plan. `preserve` lighting authority requires an item with `intended_influence=lighting` and `technical_role=faithful-archival-vector`; `specular-audit` alone remains candidate highlight evidence. Surface-plan `source_evidence_roles` contains those qualifying items' unique semantic roles and must exactly match the plan validator's recomputation. Execution validates those sources against the active runtime and writes the sole canonical prepared reference set, including the embedded plan and hashes, actual prompt artifacts or exact model-facing transports, and an explicit zero-reference reason when applicable. Generation builders then copy committed carriers into `<out-stem>.references/`, rebase the canonical set to those self-contained paths, and publish the companion directory with the package JSON as one transaction.

For state-aware work, pass the complete finalized Reference Selection to that same executor with `--reference-selection`. It constrains eligibility and supplies state scope inside the canonical pipeline. State-aware model-facing rows must preserve the selection and hash plus every row's binding ID, covered state, intended influence, review dimensions, unsupported or occluded state, and unsupported assumptions. This origin remains mandatory when state scope is present. Preserve each source separately from its exact model-facing transport, commit both hashes, and keep plan order. Never infer a reference from conversation context, bypass state eligibility, substitute a nearby artifact, drop a selected image, re-rasterize after verification, expand a reference's authority, or continue as prompt-only after a selected reference fails.

Request-supplied files enter through `scripts/prepare_generation_references.py --supplied-selection-file`, whose input accepts only explicit `supplied-file` sources with stable request-scoped IDs. It emits the same canonical prepared reference set. Pack-owned sources always enter through the Reference Use Plan and reference runtime; the supplied-file boundary rejects pack-artifact rows and fabricated pack ownership.

Reference-contract changes must keep [`schemas/reference-use-plan.schema.json`](schemas/reference-use-plan.schema.json), [`schemas/surface-lighting-plan.schema.json`](schemas/surface-lighting-plan.schema.json), [`schemas/prepared-generation-reference.schema.json`](schemas/prepared-generation-reference.schema.json), [`schemas/prepared-reference-set.schema.json`](schemas/prepared-reference-set.schema.json), [`schemas/reference-selection.schema.json`](schemas/reference-selection.schema.json), [`templates/reference-use-plan.json`](templates/reference-use-plan.json), [`templates/surface-lighting-plan.json`](templates/surface-lighting-plan.json), [`templates/prepared-reference-set.json`](templates/prepared-reference-set.json), [`templates/generation-package-template.json`](templates/generation-package-template.json), reference-runtime planning and execution, package build, verification, user-facing output, and model-adapter documentation synchronized. The Generation Package accepts exactly one canonical prepared-reference-set object and commits its hash. `gpt-image-2.5-flare` accepts declared PNG, JPEG, and WebP inputs. Its SVG path is a deterministic safe rasterization of the same selected artifact to a committed PNG transport; do not replace the source with another structural or palette artifact.

Cache construction, indexing, catalog export, packaging, and copying are one-to-one transformations of authored records and search rows. They must not summarize, compress, merge, or drop authored detail, provenance, or search associations. Rename fields only through an explicitly approved schema change. Any intentional semantic merge is separate reviewed catalog-authoring work: prove common semantic authority, form a field-by-field lossless union, and publish an explicit ID and reference remapping. Otherwise retain both records as related variants.


## Public protocol conformance

Authoring, state, reference preparation, prompt composition, generation,
and adoption each keep their own source of authority. A deployment may perform
all of them within one workspace. No stage implies an external application.

The optional exchange interface is defined by public artifact types, schema
closures, explicit capability declarations and content-addressed payloads.
Use [Protocol Exchange](references/protocol-exchange.md) to validate those data.
A received record is not an approval, an instruction to run a tool, or evidence
that referenced media has been obtained. Internal source trees, release schedules
and private project stores are not exchange inputs.

Run conformance checks before publication:

```bash
python scripts/protocol_exchange.py check-installed
python scripts/validate_integration.py
python scripts/public_boundary_smoke_test.py
python scripts/protocol_contract_smoke_test.py
```

A selected required feature must be supported. Optional fields are retained as
inert evidence only under the declared preservation policy. Correcting an invalid
artifact is explicit authoring work; validation never guesses its intended meaning.

## What the Skill conforms to

The Agent Skills specification, which belongs to no single host. It fixes what
every host reads and what every host refuses:

- `name` at most 64 characters and `description` at most 1024. A host refuses
  more than that, and `validate_skill_frontmatter_contract` refuses it here first.
- The body under 500 lines, and under 5000 tokens once loaded, because a host
  loads all of it the moment the Skill activates. `SKILL_MAX_LINES` and
  `SKILL_MAX_ESTIMATED_TOKENS` refuse both here first; the token figure is
  characters divided by four, because no local tokenizer exists.
- References one level deep from `SKILL.md`. A file reached only through another
  file may be read in part rather than in full.
- Scripts are executed rather than read into context.

`scripts/validate.py` also settles that every reference document is reached
from a `SKILL.md` link or from a route or feature `SKILL.md` names, and that
every script entrypoint is named by routed documentation.

## Required checks

For ordinary contribution work, start with the Core profile and run the focused smoke test for each subsystem changed:

```bash
python scripts/check_dependencies.py --profile core
python scripts/<affected-subsystem>_smoke_test.py
git diff --check
```

The optional aggregate runner `python -m pytest tests/` executes every smoke suite as a subprocess, including the regression-only entrypoints that no release gate runs; pytest is a development tool and is not a shipped dependency. Documentation changes require `python scripts/documentation_contract_smoke_test.py`. Retrieval changes require the search and catalog runtime suites. Reference, state, integration, visual, and pack changes require their focused suites and dependency profile. A contributor may run `python scripts/validate.py .` for a repository-wide diagnostic, but that does not replace publication validation.

For any core or pack publication, [Release Validation](references/release/validation.md) is the sole exact authority for environments, commands, pack isolation, acceptance, package verification, and metadata ordering.

## Persona and narrative development changes

Keep the full persona form as the default for both initialization and later additions. Preserve
custom forms and explicit `--blank`; do not equate a syntactically filled form with adoption or
creative quality. Follow `references/runtime/narrative-development.md` for the creative handoff.
Run `python scripts/persona_workflow_smoke_test.py` and
`python scripts/narrative_authoring_smoke_test.py` after changes to this route. The new suite is
also discovered by the pytest bridge and runs explicitly in CI.

Contextual voice and embodied-performance changes also require
`python scripts/character_performance_smoke_test.py
python scripts/authorial_intent_smoke_test.py`. This covers the advisory expression audit,
full-form propagation and route boundaries; it does not grade fictional distinctiveness. Preserve
source-language forms, adoption boundaries, current-state ownership and existing custom forms.

## Release procedure

Release maintainers must follow [Release Validation](references/release/validation.md) from environment setup through final metadata agreement. This contributor guide intentionally does not copy that sequence; update the release authority itself when the publication contract changes.

## License of contributions

Character Prompt Builder is licensed under the [GNU General Public License version 3 only](LICENSE). By submitting a contribution, you agree that it may be distributed under that license. The project intentionally does not name a copyright holder in the LICENSE file. Do not add personal attribution there unless the project owner explicitly requests it.

## Prompt-only contract changes

When modifying runtime instructions, keep the shortest prompt-only route small and preserve all displaced detail in conditional references. Run:

```bash
python scripts/runtime_read_footprint.py
python scripts/validate_prompt_semantics.py --self-test
python scripts/prompt_artifact_smoke_test.py
python scripts/prompt_plot_smoke_test.py
python scripts/narrative_contract_smoke_test.py
python scripts/scene_plot_contract_smoke_test.py
```

Do not make reference transport files mandatory when no reference is selected. Do not replace semantic camera or anatomy validation with prose alone.

## World realization and portrayal-principle changes

Run `python -B scripts/world_realization_smoke_test.py`, the example inspect/build/verify
workflow, and `python -B scripts/portrayal_principles.py validate` when changing the current
source/state/view coordination. Verify that new entrypoints remain reachable from `SKILL.md`.
These tests use freshly authored current records and assess no image quality. Keep source material,
author-facing state and consumer exports separate; do not add a second world/event authority.

## Moment query checks

When changing temporal resolution or moment-backed production, run
`python scripts/story_context_smoke_test.py`, `python scripts/world_realization_smoke_test.py`
and `python scripts/production_workflow_smoke_test.py`. The [Story Context example](examples/story-context/README.md)
exercises actual query commands and the prepare-to-complete path. Keep diagnostic
output, consumer selections and approval decisions distinct.

## Rendering contracts

Model-interface changes update execution profiles, schemas, request transport, fixtures, and documentation together.
Run `python scripts/render_contract_smoke_test.py` and `python examples/render-contract/build_example.py --check`.
Then run model, generation, request, dispatch, and repository checks under the required dependency profile.
Rendering presets are subject-neutral choices, not provider effectiveness claims.
