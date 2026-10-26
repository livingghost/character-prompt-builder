# Production knowledge discovery

Use this document for open expressive choices, sparse briefs and unresolved
craft questions. Discovery exposes relevant records and the active knowledge's
scope before the agent commits to a construction. Follow
[Production direction](production-direction.md#choose-the-expression) for the
choice and user interaction.

## Contents

- [Activation](#activation)
- [Anchor extraction](#anchor-extraction)
- [Translation boundary](#translation-boundary)
- [Read the discovery result](#read-the-discovery-result)
- [Catalog workflow](#catalog-workflow)

## Activation

Typical sparse anchors include subject domain; species or body plan; build or proportion; coat, skin, casing, or primary body color; permanent head-hair presence, section map, texture, color, and silhouette; permanent mane, ruff, facial-hair, crest, or other regional-covering boundaries; age appearance; gender presentation; and one identity accessory or occupation. Scene, role, wardrobe, pose, performance, gaze, camera, crop, composition, lighting, environment, mood, style family, and render profile may remain open only when the brief does not state them.

Representative sparse briefs may specify only a subject type plus two or three identity anchors, such as age with occupation, chassis shape with one optic, or species with build and coat color.

An explicit subject and setting can still leave the way information is presented
open. Query the communication problem as well as subject-specific construction.
When all relevant choices are fixed, use focused `search` or `inspire` for the
remaining craft need; there is no reason to invent competing presentations.

The three catalog jobs are distinct:

```text
recommend -> discover candidate knowledge and available scope
search or inspire -> retrieve a known craft need
inspect -> read one selected canonical record in full
```

Record names and IDs are not required for `recommend`, `search`, or `inspire`; selected IDs are post-selection internal identifiers for inspection and adoption. Treat an unknown ID as an error rather than guessing or silently substituting another record. Apply this authority order:

```text
explicit user anchors
-> meaning of the whole brief
-> image intent
-> selected art direction
-> inspected production knowledge
-> the studio defaults
```

Recommendation output is not an adopted record. It cannot override anchors, turn lexical score into artistic judgment, promote suggestions into identity, require catalog terms, force needless clarification, or erase unmatched wording.

## Anchor extraction

Normalize only explicit meaning and retain evidence for each interpretation. Identity facts are not the only anchors: a stated role, garment, accessory, pose, gesture, performance, gaze, camera, crop, composition, light, environment, mood, or style remains fixed too. Do not infer an unstated optional scene or style choice as an anchor.

Each `anchor_evidence` row always contains `facet`, `value`, `source`, `reason`, and `confidence`. Include `source_span` and `governed_noun` when query-local lexical evidence exists; structured or domain evidence may omit them.

Example analyzer evidence:

```json
{
  "normalized_anchors": {
    "domain": ["human"],
    "age": ["elderly"],
    "role": ["botanist"],
    "wardrobe": ["blue field jacket"]
  },
  "anchor_evidence": [
    {
      "facet": "wardrobe",
      "value": "blue field jacket",
      "source": "blue field jacket",
      "source_span": "blue field jacket",
      "governed_noun": "field jacket",
      "reason": "the color modifies the garment noun",
      "confidence": "explicit"
    }
  ]
}
```

Structured query input is separate:

```json
{
  "canonical_query": "elderly human botanist blue field jacket",
  "domain": "human",
  "anchors": {
    "age": ["elderly"],
    "role": ["botanist"],
    "wardrobe": ["blue field jacket"]
  },
  "source_brief": "original wording in any language",
  "source_language": "und",
  "unresolved_terms": []
}
```

Keep modifiers attached to their governed noun or property:

```text
blue fur -> coat palette
blue eyes -> eye_feature
blue lighting -> lighting
blue jacket -> wardrobe
blue room -> environment
black head hair -> head hair and hair color
long wavy hairstyle -> head hair, style, and texture
short chin beard -> facial hair
full neck mane -> mane
bounded cheek ruff -> ruff
crown and ear fur tufts -> head-fur placement
paired swept horns -> head feature
```

Apply the same rule to `glossy`, `wet`, `old`, `damaged`, `formal`, `athletic`, `broad`, and `oversized`; a glossy coat, glossy armor, glossy floor, and glossy cel finish belong to different facets. If the deterministic analyzer cannot resolve a meaningful term, retain it in `terms_without_alias` or an ambiguity diagnostic:

```text
elderly human botanist
-> domain: human
-> age: elderly
-> terms_without_alias: botanist
```

Treat that result as an action queue: interpret the term semantically, preserve it directly in the direction, author a canonical-English alias or search profile when it is reusable, or add the missing catalog knowledge. Never substitute `researcher` for `botanist` merely because a researcher record exists. Never assign an ambiguous modifier to a stable anchor merely because the word is associated with that facet elsewhere in the index.

## Translation boundary

Translate the user's whole brief semantically into concise canonical English before retrieval. Preserve modifier scope, relationships, negation, uncertainty, and unresolved meaning. Do not translate token by token.

The calling agent performs semantic translation and supplies the structured query. The deterministic, AI-free catalog CLI does not interpret multilingual free-form meaning. `source_brief` and `source_language` are opaque audit metadata and never drive lexical scoring; `canonical_query` and structured anchors are English retrieval language. The package contains controlled English aliases, not per-language dictionaries.

An AI-free client may provide the same structured input directly; semantic translation remains that client's responsibility.

Start from [the catalog query template](../../templates/catalog-query-template.json) when preparing structured input. Use `--query-json` when source wording, language, or explicit facet control must remain auditable:

```bash
python scripts/catalog_cli.py recommend \
  --query-json templates/catalog-query-template.json \
  --limit 8
```

## Read the discovery result

`recommend` returns `mode: knowledge-discovery` with:

| Field | Use |
| --- | --- |
| `query_request`, `query_analysis` | Read the query, explicit anchor evidence, modifier scope and unresolved wording. |
| `scope` | Confirm the domain and active source packs. |
| `candidates` | Compare compact record summaries, authored functions, applicability, grouping and textual match evidence. |
| `catalog_inventory` | See the scoped kinds, categories, tiers and authored facet summaries available for further questions. |
| `vocabulary` | See the resolved optional dictionary, category counts and lexical category matches. |
| `inspection_queue` | Locate the returned candidate records for full inspection. |
| `terms_without_alias` | Preserve meaning that the lexical index has not resolved. |

The inventory is derived from active canonical records. Facet examples are
bounded; their counts and `truncated` flags distinguish examples from complete
value coverage. New records and categories enter this inventory through the
same record projection. The dictionary contributes terms and categories without
being presented as curated construction knowledge.

When a relevant facet is truncated and its remaining values could affect the
choice, expand that returned facet name through `--inventory-facets`. The option
accepts comma-separated names from the current inventory and exposes their full
authored values. It works for any facet name; no technique list is maintained
in the command. For example, when these names are present:

```bash
python scripts/catalog_cli.py recommend "make a small feature readable" \
  --inventory-facets communication_goal,expression_structure --limit 8
```

Unknown names produce a query diagnostic. Use this targeted expansion or an
appropriate focused query when the initial summaries do not expose enough
alternatives. Do not treat the first few examples as all available forms.

Read candidates for what they help communicate and the conditions in which
that construction works. Search their relevant category or described function
when a summary exposes another useful question. Inspect the complete record
before applying it. A candidate can contribute one relationship without its
example's style, setting or other incidental choices.

No result constitutes a complete art direction or automatic selection. An
empty candidate list means that this query found no sufficiently relevant
record; the inventory remains available for exploration. Counts and lexical
rank prove neither suitability nor the impossibility of an authored expression.
Keep subject anchors and source authority intact while deciding whether a
technique fits. Use an authored construction when no inspected record fits,
and record that choice through the ordinary retrieval workflow.

## Catalog workflow

The active search coverage is the union of packs enabled by the selected state after dependency, replacement, and conflict resolution. Inspect it instead of relying on prose counts:

```bash
python scripts/catalog_cli.py stats
```

Inventory counts are not a closed ontology and do not imply one dedicated record for every natural-language concept. Coverage can be multilayered: `affection` may retrieve an expression, hand-placement record, composition, and embracing scene; `work` may retrieve an occupation, pose, prop, and scene; `bathing` may combine environment, scene, and temporary wetness state when the active packs contain them.

Retrieval may use stable identity; facial expression; coordinated body language; emotional tone; pose and gesture; activity; situation; relationship; theme; temporary state; and content intensity when canonical records carry that evidence. Content-intensity retrieval preserves prompt knowledge and does not authorize downstream execution.

Broad words need a contextual noun when available. `play` may mean recreation, sport, music, game play, or teasing; `work` may mean office, craft, maintenance, rescue, or performance; `serious` may mean focused, stern, solemn, restrained, or dangerous; `love` may mean romance, family care, protection, companionship, or devotion. Preserve the broad intent and add context such as `playing guitar`, `office work`, `serious monitoring`, or `protective affection` rather than choosing one meaning silently.

Run recommendation with the same explicit state, cache, managed root, and additional pack roots used for later operations. A simple canonical-English call is also valid:

```bash
python scripts/catalog_cli.py recommend \
  "observation reaction attention sequence" \
  --limit 8
```

Before or after choosing the direction, retrieve a known craft need directly:

```bash
python scripts/catalog_cli.py search \
  "ball near camera raised knee low angle" \
  --kind scene \
  --domain anthropomorphic-animal
```

Layered focused retrieval is also available:

```bash
python scripts/catalog_cli.py inspire \
  "protective bedside size contrast warm window light" \
  --categories composition,camera,lighting,hand-placement,pose-action,emotion-nuance \
  --domain anthropomorphic-animal \
  --core-limit 3 \
  --style-family-limit 3 \
  --realization-limit 2 \
  --profile-limit 3 \
  --archetype-limit 2
```

For a worker-portrait question, another complete focused call is:

```bash
python scripts/catalog_cli.py inspire \
  "warm window low angle worker portrait" \
  --categories camera,lighting,outfit,head-gaze \
  --domain anthropomorphic-animal
```

`inspire` returns `aesthetic_cores`, `style_families`, `domain_realizations`, `render_profiles`, `subject_archetypes`, and atomic `categories`, plus `axis_coverage`; empty groups are valid. Subject archetypes own stable morphology, palette, marking logic, proportions, and identity equipment, and adopted automatic identity constraints enter the prompt.

Base scenes are available only through `search --kind scene`; recipes require `search --include-recipes`. Normal search groups variants; use `--ungrouped` only for exact inventory or variant comparison.

Use one catalog process for independent questions at the same stage:

```bash
python scripts/catalog_cli.py \
  --state-file pack-state.json \
  --cache-dir catalog-cache \
  --managed-root managed-packs \
  batch --input catalog-batch.json > catalog-batch-results.json
```

The input is one ordered JSON array; each request has a unique `request_id` and its own query contract:

```json
[
  {"request_id":"identity","command":"search","canonical_query":"muscular black panther","kind":["archetype"],"domain":"anthropomorphic-animal","limit":6},
  {"request_id":"scene","command":"search","canonical_query":"low-angle athletic action","kind":["scene"],"domain":"anthropomorphic-animal","limit":6}
]
```

Parse the complete saved JSON, not a terminal excerpt. The response preserves request order and keeps query-local errors beside their `request_id`; an invalid active catalog aborts the whole batch.

Each focused query must express one coherent unresolved craft question for identity, scene, camera, lighting, outfit, grooming, or another craft role while preserving every load-bearing anchor and modifier relationship. Prefer three to six distinctive content words when they express that complete question. Split queries when the questions are materially different, including the all-empty recovery described below; never truncate an anchor, negation, relationship, or modifier scope merely to satisfy a word count. Inspect every adopted result:

```bash
python scripts/catalog_cli.py inspect <record-id>
```

`inspect` returns the complete canonical record and a compact linked-asset activation summary. It does not return complete asset resources. Run full `asset-lookup` for every selected record before final prompt delivery or image-generation packaging, even when the compact activation summary reports no link and even when the evidence is not ultimately adopted. `asset-lookup --summary` is an optional technical-role preview only and cannot satisfy that gate.
Use `inspect <record-id> --out <path>` when the complete record should go to UTF-8 JSON instead of stdout.

## Runtime failure rules

Preserve unresolved wording and inspect full records before adoption. Reject an
incompatible candidate even when it has useful assets. A query with no result
does not prove absent coverage. In focused `inspire` output, read
`query_token_count`, `axis_coverage` and any `retrieval_note`. When every requested
group or category is empty, separate materially different questions and retry
them with concise wording that retains each load-bearing relationship and
modifier. Three to six distinctive content words can help expose query dilution;
they are not a limit that permits discarding meaning. Use the inventory to
investigate another relevant category. Against a large pack, use one `batch`
process for independent questions, then inspect each selected record and its
actual linked evidence.

Search-profile authoring, aliases, facets, grouping policy, and evaluation belong to [Search Discovery Maintenance](../maintenance/search-discovery.md), not this runtime path.
