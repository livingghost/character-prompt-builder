# Content Packs

Content packs are Character Prompt Builder's distribution unit for searchable production knowledge and supporting resources. Presets are pack records. Visual Evidence records, evidence artifacts, preview thumbnails, policies, and lookup resources remain in the same owner pack as the records that use them.

Core scripts, shared schemas, and generic runtime templates are not optional content and do not become packs.

## Identity and release

Every pack has a stable UUIDv7 `pack_id` and an independent UTC CalVer `release` in `YYYY.MM.DD.N`. The current manifest and record schemas are the complete parser contract, and every dependency names one pack by UUID rather than one release.

```text
<pack>/
  pack.json
  pack.lock.json
  records/*.json
  resources/**
  README.md
  LICENSE
```

Released and installed external packs require a valid generated lock. The actual core-managed `packs/commons` has no separate lock and is committed by the project inventory. The manifest declares records, resources, capabilities, dependencies, replacement intent, and logical-resource bindings. See [Pack Format Specification](references/pack-format-specification.md) for the complete schema contract.

A Visual Evidence record is a searchable asset whose declared evidence artifacts may include a faithful archival vector, structural guide, color audit, saturation evidence, specular audit, mask, or supporting metadata. An artifact may use SVG when a vector file is required, but the file format does not name the feature. Several Visual Evidence records and evidence artifacts may participate in one result through distinct record-scoped roles; the runtime never assumes that one file represents the whole request.

## Runtime activation

`pack-state.json` is the complete authority for registered discovery roots, enabled UUIDs, and logical-resource providers. Once a state exists, discovering a pack does not enable it and enabling it does not change its providers. First-use initialization instead enables all discovered packs and selects additional unambiguous providers.

State resolution is deterministic: an explicit `--state-file` path wins; otherwise commands use the persistent user state at `~/.character-prompt-builder/pack-state.json` under the user home directory on every platform; while the selected file does not exist, `config/pack-initialization.json` enables all discovered packs over the minimal core-release seed in `config/default-pack-state.json`. An existing explicit state is never merged or silently reset. `python scripts/pack_cli.py state-init` persists the resolved state file once and reports every discovered pack with its enabled status, including `disabled_discovered_packs`.

Use [Pack State Runtime Quickstart](references/runtime/pack-state-quickstart.md) when a prompt task needs a non-bundled pack or provider. It covers explicit state, cache freshness, and the requirement to use one context for catalog, planning, materialization, and verification.

The bundled commons pack is separately authored and minimal. Other user-owned and third-party packs may be added, enabled, disabled, updated, and removed independently. Storage location is not a taxonomy and does not make a pack default, local, cloud, or third-party.

### Owner-maintained libraries

A directory such as `packs/<owner-library>`, when present in a working tree or a full distribution, is owner-maintained content. It remains a normal pack: full-package construction and catalog export may preserve and validate it, and an explicit pack state may enable and use it. Its presence enables it on fresh runtime initialization, without making its records core-release catalog dependencies.

Core documentation, runtime defaults, and regression expectations must not depend on that library's current record IDs, aliases, model inventory, counts, search results, or evaluation history. Tests that need non-bundled content create synthetic packs in temporary directories. This boundary protects ownership without deleting, moving, renaming, or excluding the library itself.


## Prompt-vocabulary resources

A pack may bind `prompt-vocabulary` to a dictionary that validates against [`schemas/prompt-vocabulary.schema.json`](schemas/prompt-vocabulary.schema.json). The resource remains ordinary owner-authored pack content. Core code resolves it through explicit pack state and never assumes one pack name, current dictionary size, or current term inventory. The search helper returns lexical candidates only; the Skill-using agent decides whether and how to use them.

## Prompt-writing-guide resources

A pack may bind `prompt-dialects` to a JSON resource that validates against [`schemas/prompt-dialect.schema.json`](schemas/prompt-dialect.schema.json). One entry per model family states the tag grammar it reads, the blocks a rendition is built from and their order, and the quality, rating, period, and inert vocabulary that acts on it. A model record names its family in `prompt_dialect` and a guide section names the families it applies to, so knowledge proven on one family never reaches another. Add a family by adding an entry; no core code changes. `scripts/prompt_dialect.py` resolves a model to its family and the rules that apply.

A pack may bind `prompt-writing-guide` to a JSON guide that validates against [`schemas/prompt-writing-guide.schema.json`](schemas/prompt-writing-guide.schema.json). When a provider is selected and a target interface is known, the Skill reads the complete guide during final rendition. The guide supplies prompt-construction knowledge; it does not inject example text, select vocabulary, override a model record, or make content decisions for the agent. Core tests use synthetic guides and never depend on an owner pack's current rules or examples.

## Maintenance and distribution

Use [Pack Maintenance](references/maintenance/packs.md) for:

- pack creation and validation;
- root registration and activation changes;
- provider selection;
- lock construction;
- install, update, remove, and quarantine;
- cache diagnosis;
- conflicts and replacements;
- HTML catalog export;
- default, user-owned, and third-party ownership rules.

Use [Release Validation](references/release/validation.md) for exact one-pack evaluation and core publication gates.

Pack discovery, caching, inspection, export, copying, and distribution preserve authored records and resources. They do not summarize, compress, deduplicate, split, or merge content. Semantic consolidation is a separate reviewed authoring change with a lossless field union and explicit reference remapping.

## Catalog and reference responsibilities

The interfaces are deliberately separated:

- `catalog_cli.py inspect <record-id>` returns the complete canonical record and a compact linked-asset activation summary;
- `asset-lookup --summary` returns compact asset IDs and technical artifact roles;
- full `asset-lookup` returns planning details, including active ownership, artifacts, resources, media, paths, and hashes;
- `reference_runtime.py plan` activates evidence through `RECORD_ID=INTENDED_INFLUENCE` declarations;
- `reference_runtime.py execute` materializes one canonical prepared-reference-set.

Discovery does not activate a reference. Planning does not create a second source authority. For prompt plus SVG delivery, use [Prompt Artifact Reference Runtime](references/runtime/reference-prompt-artifacts.md). For model-facing rasterization and generation, use [Image Generation Runtime](references/runtime/image-generation.md).

## Command entry points

```text
pack_cli.py init, validate, build-lock
pack_cli.py state-init
pack_cli.py root-add, root-remove, list, inspect
pack_cli.py enable, disable
pack_cli.py install, update, remove
pack_cli.py cache-status, cache-refresh
pack_cli.py resources, resource
pack_cli.py provider-list, provider-select, provider-clear
```

Successful command results and handled operation reports are JSON. Usage errors and operation failures exit nonzero with English diagnostics.

## First-use activation and bundled integrity

`config/pack-initialization.json` enables all valid discovered packs only while the selected state file is absent. `state-init` persists that result. Existing explicit state is never overwritten: deliberately disabled packs remain disabled, and selected resource providers remain selected. `config/default-pack-state.json` remains the minimal core-release catalog seed, not a restriction on first-use activation of additional supplied packs.

The actual bundled `packs/commons` directory with the commons UUID is core-managed. It has no `pack.lock.json`; core source inventory and `MANIFEST.json` commit it together with the project, and pack validation still checks its schema and files. `lock` and pack release-lock creation refuse that directory rather than recreating an unnecessary lock. The exemption is path-bound, not a manifest flag: external, installed, copied, and user-library packs still require their release lock. The release gate reports a live core inventory for commons, not a nonexistent lock. Do not remove or weaken any external pack's lock.
