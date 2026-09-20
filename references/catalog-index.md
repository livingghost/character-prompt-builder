# Catalog Index

This index describes 1 explicitly configured default pack. User-owned and third-party packs remain outside these totals. `python scripts/pack_cli.py list` reports the active set selected by user state.

## Totals

| Record family | Count |
|---|---:|
| `domain-realization` | 6 |
| `model` | 2 |
| `module` | 88 |
| `profile` | 1 |
| `scene` | 4 |
| `style-family` | 4 |
| **All default-pack records** | **105** |

## Record roles

| Role | Count |
|---|---:|
| `curated` | 95 |
| `vocabulary` | 10 |

`curated` records contain complete production knowledge. `vocabulary` records provide compact model-legible names and options. These are different jobs, not a quality ranking.

## Atomic module categories

| Category | Count |
|---|---:|
| `aesthetic-touch` | 4 |
| `body-build` | 3 |
| `body-language-cue` | 9 |
| `camera` | 8 |
| `coat-palette` | 3 |
| `composition` | 7 |
| `creature-anatomy` | 20 |
| `emotion-nuance` | 2 |
| `gender-presentation` | 3 |
| `lens` | 2 |
| `lighting` | 10 |
| `photography-style` | 8 |
| `rendering` | 6 |
| `species` | 3 |

## Domains

```json
{
  "animal": 6,
  "anthropomorphic-animal": 42,
  "creature": 33,
  "human": 7,
  "hybrid": 42,
  "robot": 4,
  "shared": 62
}
```

## Runtime-derived search cache

Pack-authored records and search rows are authoritative. The active pack state is materialized in a disposable SQLite cache that refreshes automatically when pack content, activation state, selected resource providers, or cache-builder logic changes.

Use `python scripts/catalog_cli.py inspect <record-id>` for the complete canonical record and compact linked-asset activation summary. Add `--out <path>` when the complete UTF-8 JSON record should be written instead of printed. Use `asset-lookup <record-or-asset-id> --summary` for compact asset IDs and technical roles, and full `asset-lookup` only for artifact resources, media, paths, hashes, and ownership needed by planning. Use `catalog_cli.py batch --input <json-file-or-stdin>` for several ordered queries so the active catalog and index load once. For linked visual evidence, build one record-scoped plan with `python scripts/build_reference_use_plan.py --record-use <record-id>=<intended-influence> ...`, then materialize the canonical `prepared-reference-set` before generation-package construction. Use `python scripts/pack_cli.py resource <name>` for selected named-resource resolution. `python scripts/catalog_html.py --pack-tree packs --output catalog` discovers every explicit pack below `packs/` and writes a split inspector. Its script-free `index.html` links to the Visual Evidence gallery, linked-preset gallery, kind browsing, pack summaries, and the separate search page. Complete records live on per-record pages, while `data/record-asset-map.json` records both canonical-record-to-Visual-Evidence and reverse relationships. See `references/maintenance/catalog-export.md`.
