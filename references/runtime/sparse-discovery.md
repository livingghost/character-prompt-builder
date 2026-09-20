# Sparse-Brief Discovery Runtime

Use this document when a brief fixes only a few stable anchors while several outcome-defining axes remain open. Sparse discovery proposes materially different finished-image directions; it does not replace language understanding or art direction.

## Contents

- [Activation](#activation)
- [Anchor extraction](#anchor-extraction)
- [Translation boundary](#translation-boundary)
- [Direction cards](#direction-cards)
- [Catalog workflow](#catalog-workflow)

## Activation

Typical sparse anchors include subject domain; species or body plan; build or proportion; coat, skin, casing, or primary body color; permanent head-hair presence, section map, texture, color, and silhouette; permanent mane, ruff, facial-hair, crest, or other regional-covering boundaries; age appearance; gender presentation; and one identity accessory or occupation. Scene, role, wardrobe, pose, performance, gaze, camera, crop, composition, lighting, environment, mood, style family, and rendering profile may remain open only when the brief does not state them.

Representative sparse briefs may specify only a subject type plus two or three identity anchors, such as age with occupation, chassis shape with one optic, or species with build and coat color.

Skip recommendation when the brief already defines the outcome axes. Use focused `search` or `inspire` after forming the direction.

The three catalog jobs are distinct:

```text
recommend -> explore coherent outcome directions
search or inspire -> retrieve a known craft need
inspect -> read one selected canonical record in full
```

Preset names and IDs are not required for `recommend`, `search`, or `inspire`; selected IDs are post-selection internal identifiers for inspection and adoption. Treat an unknown ID as an error rather than guessing or silently substituting another record. Apply this authority order:

```text
explicit user anchors
-> meaning of the whole brief
-> image intent
-> selected art direction
-> inspected production knowledge
-> project defaults
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
  --directions 4
```

## Direction cards

Return three or four cards when the active catalog supports materially different outcomes. Each card contains:

```text
id
title
what_you_get
why_it_fits
preserves
permanent_identity_preserves
scene_specific_character_state
terms_without_alias
adds
adjustable
fixed_component_overrides
preset_ids
inspection_queue
open_axes_after_card
```

`fixed_component_overrides` is populated when an explicit style, camera, or light replaces the corresponding discovery-lane default. It records the fixed replacement rather than silently presenting the lane default as selected; otherwise the field remains empty.

The complete `recommend` result contains:

```text
mode
query_analysis
identity_candidates
identity_modules
domain_realizations
direction_cards
terms_without_alias
note
```

`query_analysis` contains:

```text
query
canonical_query
normalized_query
source_brief
source_language
domain
normalized_anchors
anchor_evidence
modifier_scope_evidence
open_axes
matched_alias_phrases
terms_without_alias
```

`what_you_get` is the ordinary-language outcome; `preset_ids` and `inspection_queue` are post-selection internal identifiers for later inspection, not adopted knowledge. A useful card answers:

1. What would the finished picture look and feel like?
2. Which user anchors remain fixed?
3. Which scene, camera, lighting, wardrobe, or style choices are proposed?
4. Which choices can vary without breaking the direction?
5. Which canonical records implement the result?

Cards differ on outcome-defining axes, not labels. Four minor variants of one athlete portrait are not four directions. A close glossy portrait, athletic action, warm everyday scene, and regal nocturnal portrait are distinct.

`cpb-resource:discovery-lanes`, resolved from the explicitly selected provider, supplies compatible clusters rather than finished recipes. A preferred scene is eligible only when it respects every explicit domain, species, palette, role, wardrobe, accessory, environment, pose, gesture, performance, and staging anchor. Returning a card without a scene record is better than importing a conflict.

The recommender scores lanes against the caller's canonical-English query and explicit facets, preserves fixed anchors and open axes, and returns a diverse set.

A lane must not force a shark-specific water scene onto a wolf merely because both records contain `blue` or `muscular`; a species-specific scene needs explicit compatibility or an adaptable scene contract.

Group near-duplicate variants under one discovery family so they cannot occupy the whole result set. Preserve `discovery_group` and `variant_of` information for inspection.

When the user asks for possibilities, present cards in visual language. When the user asks for an immediate prompt or image, choose the strongest coherent card without asking solely about optional open axes.

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
  "elderly human botanist" \
  --domain human \
  --directions 4
```

After choosing a direction, retrieve one known craft need directly:

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

After selecting a card, use one catalog process for all independent queries:

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

Never lock a lane suggestion, average cards, force an incompatible scene, let related variants crowd out distinct outcomes, omit unresolved wording, or adopt from an excerpt. One empty result does not prove absent coverage. Read `query_token_count`, `axis_coverage`, and any `retrieval_note` from the complete response. When every requested group and category is empty, or when `retrieval_note` reports that every requested atomic category is empty, separate materially different craft questions and retry each with three to six distinctive words before declaring coverage absent. Preserve every load-bearing anchor and modifier relationship; this is focused recovery from query dilution, not arbitrary shortening. If the batch has no anchor-compatible record with required linked evidence, preserve all anchors and run one focused recovery search for the missing scene, style, or other craft role. Asset presence never outranks compatibility: reject an incompatible asset-bearing record, then inspect and run asset lookup on every recovery candidate before adoption. Against a large pack, use one `batch` process instead of parallel CLI processes, then inspect every adoption completely.

Search-profile authoring, aliases, facets, grouping policy, and evaluation belong to [Search Discovery Maintenance](../maintenance/search-discovery.md), not this runtime path.
