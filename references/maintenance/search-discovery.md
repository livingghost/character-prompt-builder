# Search Discovery Maintenance

Use this document only when adding or changing search metadata, discovery lanes, catalog retrieval behavior, sparse-direction behavior, or pack-owned retrieval evaluations. Runtime agents should use [Sparse-Brief Discovery Runtime](../runtime/sparse-discovery.md).

## Contents

- [Authority and index model](#authority-and-index-model)
- [Search profiles](#search-profiles)
- [Facet authoring](#facet-authoring)
- [Modifier-scope authoring](#modifier-scope-authoring)
- [Direction lanes and diversity](#direction-lanes-and-diversity)
- [Representative coverage cases](#representative-coverage-cases)
- [Coverage changes and evaluation ownership](#coverage-changes-and-evaluation-ownership)
- [Maintenance command index](#maintenance-command-index)

## Authority and index model

Canonical pack records own search evidence. The cache projects those records into a disposable many-to-many English index; never edit cache rows by hand. Facets are discovery projections, not production authority. They do not replace the complete record or justify knowledge absent from it.

Each derived association records at least a record ID, scoped facet, evidence source, and weight:

```json
{
  "id": "record-id",
  "facet": "coat_palette",
  "source": "search_alias",
  "weight": 1.0
}
```

One phrase may point to several records, and one record may be reached through many aliases, structured fields, outcome summaries, and facets. Broad terms remain broad until query context disambiguates them. Exact labels and tags remain useful, but ordinary descriptive phrases must also reach records through those authored and derived associations.

Preserve these retrieval axes when the canonical record supports them:

| Intent | Primary record owners | Typical searchable evidence |
| --- | --- | --- |
| stable identity | archetype, species, body-build, coat-palette, marking, distinctive-detail, grooming contracts | species, body plan, silhouette, palette, markings, eyes, persistent scars, identity equipment, head-hair construction, mane, ruff, facial hair, regional covering boundaries |
| facial expression | expression | lid line, brow angle, eye openness, mouth and tongue geometry, blush, tears, gaze direction |
| coordinated body language | body-language-cue, expression, emotion-nuance, gesture, hand-placement, pose-action, head-gaze, scene | gaze target, posture, hands, feet, contact, blush, breath, ears, tail, whiskers, wings, optics, manipulators, indicators, timing |
| emotional tone | emotion-nuance, mood-palette, expression, scene | happy, sad, jealous, grumpy, affectionate, embarrassed, serious, moved, vigilant |
| pose and gesture | pose-action, gesture, hand-placement, leg-placement, head-gaze, scene | crouching, leaning, embracing, pointing, visor touch, hand on thigh, raised fist |
| activity | pose-action, occupation, prop, scene | working, monitoring, bathing, reading, driving, playing music, sports, resting |
| situation | base scene, environment, weather, season, time-of-day | pool duty, sunset beach, snowy onsen, office work, festival, disaster training |
| relationship | scene, aesthetic core, hand-placement, composition | affection, rivalry, protection, caregiving, mutual embrace, size contrast |
| theme | scene, mood-palette, aesthetic core, explicit search facets | summer vitality, aquatic safety, solitude, recovery, work fatigue, play, duty |
| temporary state | effect, skin-detail, animal-surface, state projection, scene | wetness, sweat, dirt, injury, blush, tears, heat, cold, fatigue |
| content intensity | scene, correction, distinctive detail, expression, emotion-nuance, pose-action, hand-placement, explicit search facets | graphic injury, body horror, restraint, medical alteration, grotesque detail, disturbing atmosphere, adult erotic content, sexual intimacy, sensuality, nudity, fetish context |

Content intensity facets, including graphic, violent, medical, nude, erotic, sexual, and other intense content, are prompt-knowledge retrieval facets treated the same as any other facet. Keep `intimacy_context` distinct from `erotic_context`, `sexual_context`, and `nudity_context`; close, affectionate, familial, or emotionally intimate content is not automatically erotic.

Field-aware scoring additionally distinguishes species, subject domain, body build, proportion, coat or body palette, eye features, wardrobe and accessories, role, pose and gesture, camera and composition, lighting, environment and atmosphere, mood and aesthetic, and style and medium.

## Search profiles

Every curated record's derived profile contains:

```text
aliases
outcome_summary
discovery_group
variant_of, when applicable
facets
anchor_signature
```

Supply at least three natural canonical-English aliases that do not repeat only the exact ID or label. After caller-side semantic translation, cover visible outcome, camera or viewer relationship, emotional or functional use, and the construction problem solved when supported. An outcome summary describes the image the record can help produce, not merely the record name; keep it concise enough for a direction card and concrete enough for comparison with another result.

Reject aliases that copy the exact label three times, merely replace hyphens in the ID, or use one unexplained internal category name. Useful aliases describe visible and usable results, for example:

```text
shiny muscular animal close portrait
low camera chest dominant character image
hard cel shadow with broad body sheen
```

Assign one `discovery_group` to records representing the same underlying family. Use `variant_of` for a more specific member. Normal search groups near duplicates and returns related variants under the representative; ungrouped output is maintenance, audit, and exact-inventory tooling only.

The index may derive conservative trailing noun phrases from curated atomic labels, such as `baseball cap` from `fitted baseball cap`. It must not derive broad scene or archetype suffixes such as `close portrait`, because those create false exact matches across materially different outcomes.

## Facet authoring

State visible evidence explicitly through scoped facets. Useful keys include:

```text
emotion, expression, body_language, gaze, mouth_action
hand_action, leg_action, appendage_action, physiology, mechanical_signal
performance_intent, interpretation, pose, activity, situation, theme
relationship, viewer_relationship, role, environment
head_hair, hair_style, hair_texture, hair_color
facial_hair, mane, ruff, head_fur_placement, head_feature
content_intensity, adult_content, erotic_context, sexual_context
nudity_context, fetish_context, consent_context, intimacy_context
```

Do not invent a facet absent from the canonical source, or use facets to replace the complete production record. Do not infer jealousy from any side-eye, affection from any touch, or danger from any weapon. Preserve a broad alias when supported, then add construction or situation that distinguishes its readings.

Project coordinated cues as ordinary-language evidence: flushed cheeks, half-lidded eyes, tongue display, hands gripping a hem, ears angled toward the target, tail-tip flick, whiskers forward, narrowed optic aperture, paused manipulator, or ventilation pulse. Keep broad cues context-sensitive. `Tongue out` can be playful, overheated, effortful, appetitive, teasing, or adult sensual; `crossed arms` can be watchful, authoritative, displeased, cold, or resting.

## Modifier-scope authoring

Search profiles and regression cases must preserve the governed noun or property. Domain words such as `anthropomorphic` are not body-build modifiers. Hair modifiers remain with hair or crown nouns; garment modifiers remain with garment nouns. An ambiguous word must stay unmatched or explicitly ambiguous rather than becoming a stable anchor through index association alone.

Required scope cases include:

```text
anthropomorphic black panther
broad crown clumps
athletic shorts
muscular black panther
tall maintenance robot
blue fur
blue eyes
blue lighting
blue clothing
blue room
```

Record source span, governed noun, adopted facet, and reason in analyzer evidence. Preserve intended existing cases such as `tall maintenance robot` while preventing unrelated words from entering body build.

## Direction lanes and diversity

An authored discovery lane contains one outcome thesis, one preferred style family, optional compatible scenes, camera and lighting treatments, environment and mood vocabulary, intended use, and variation guidance. It is not a recipe.

Preferred scenes require explicit compatibility with every fixed domain, species, palette, role, wardrobe, accessory, environment, pose, gesture, performance, and staging anchor. A direction without a scene is better than a conflicting scene. Ensure cards differ materially and group near-duplicate variants.

When adding or promoting a curated record:

1. Preserve full production knowledge under [Preset Authoring Standard](../preset-authoring-standard.md).
2. Add an outcome summary and at least three natural aliases.
3. Add scoped facets only for supported evidence.
4. Assign discovery group and variant relationship when applicable.
5. State compatible and incompatible use when misapplication is plausible.
6. Add short, ID-free sparse-query regression cases when the record represents a useful discovery path.
7. Update the authoritative search profile and regression cases in the owning record and pack resources. The derived cache refreshes when enabled packs or source files change; never edit cache rows directly.

Vocabulary records may remain compact. Their labels, tags, prompt wording, and category contribute lexical recall; do not fabricate curated structure solely to improve rank.

## Representative coverage cases

Keep ordinary, ID-free coverage cases for supported records, including:

```text
fun playful expression
sad melancholy expression
happy joyful smile
affection loving embrace
jealous expression
grumpy displeased expression
provocative challenging smirk
embarrassed bashful blush
serious focused expression
emotionally moved tearful smile
watchful monitoring posture
bathing in a hot spring
working in an office
playing for recreation
adult sensual or erotic reclining flirt pose
```

A successful hit proves textual retrieval evidence, not automatic adoption. The owning pack's declared suite remains authoritative for which cases its records support.

## Coverage changes and evaluation ownership

Every substantial addition to expression, emotion, pose, activity, situation, relationship, theme, or content-intensity knowledge must update aliases and facets, demonstrate an ordinary short query without ID or exact label, add a regression case for a new concept or gap, group variants, and record unresolved coverage honestly.

Pack-owned records imply pack-owned tests. Focused cases belong to the pack's `catalog-search-regression`; sparse cases belong to `sparse-discovery-evaluation`; exact counts belong to its `release-evaluation-contract`. Core owns no evaluation corpus, so pack-owned cases have nowhere else to be duplicated to.

The selected pack's logical `catalog-search-regression` resource is the authority for concrete representative query strings and expected hits. A passing hit proves textual retrieval evidence only; it is not automatic adoption. Inspect the complete canonical record before use.

Every sparse-discovery evaluation must cover:

- one-to-four-word identity briefs;
- canonical structured queries translated from multiple source languages;
- the body-build synonym family `muscular`, `muscled`, `powerful`, and `broad-built`;
- modifier scope such as `blue fur` versus `blue eyes` versus `blue lighting`;
- retrieval without exact preset labels or IDs;
- variant grouping and minimum direction diversity;
- preservation of explicit identity anchors;
- preservation of explicit role, wardrobe, accessory, camera, and lighting anchors;
- exclusion of identity candidates that conflict with explicit coat, species, or domain anchors;
- domain-safe rejection of incompatible preferred scenes; and
- visibility of unresolved user wording.

Core retrieval regression tests use canonical English. Multilingual integration tests belong at the agent boundary: they verify that source briefs normalize to the same English anchors and preserve unresolved meaning; they do not create locale dictionaries.

Run all declared suites through the exact one-pack gate in [Release Validation](../release/validation.md). Deterministic passing proves known retrieval and structural behavior, not artistic quality.

The exact-pack state enables only the positional pack and selects it for every and only its named-resource bindings. The gate validates the released lock, exact derived cache, declared search and sparse suites, and every other suite in that pack's contract without consulting ambient or bundled default state.

When comparing `curated`, `vocabulary`, and no-preset retrieval strategies, read [Tier Strategy Evaluation](presets.md#tier-strategy-evaluation). Do not load it for ordinary profile authoring or runtime search.

## Maintenance command index

For focused diagnostics while authoring a selected pack's evaluation resources, use one explicit pack runtime:

```bash
python scripts/search_regression.py --state-file <state.json> --cache-dir <cache-dir> --managed-root <managed-dir> --pack-root <pack-root>
python scripts/sparse_discovery_eval.py --state-file <state.json> --cache-dir <cache-dir> --managed-root <managed-dir> --pack-root <pack-root> --no-write
```

These commands are maintenance diagnostics, not the publication gate. Release the suite only through the exact one-pack contract in Release Validation.

## Anatomical neutrality in lexical inference

`head_hair` and other specialist facets are retrieval categories, not universal anatomy. Bare hair or an unfamiliar located structure is retained without selecting a head; head-specific inference requires an explicit location or selected style. A coat without a resolved wearing or covering context stays unresolved. Tool or non-head horn wording does not assert a head feature. Structured anchors remain authoritative, while lexical candidates never become approved identity. `structure_neutrality_smoke_test.py` covers empty and populated indexes.
