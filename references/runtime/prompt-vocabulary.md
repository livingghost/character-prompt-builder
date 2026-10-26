# Prompt Vocabulary Runtime

## Activation

Use this runtime when the image direction is already understood but the agent needs broader English wording, an alternate phrase, category browsing, or a compact image-prompt term. It supplements catalog records; it does not replace art direction, canonical-record inspection, model adaptation, or the agent's judgment. The lookup is not optional polish: during prompt assembly, run one vocabulary search per distinct visual element before the wording is final, prefer a fitting dictionary term as the compact model-legible tag, and keep hand-composed wording wherever no term fits or prose carries the meaning (see [Prompt Composition Runtime](prompt-composition.md), Prompt assembly and review).

A prompt-vocabulary resource is ordinary pack-owned knowledge. It does not decide which entries are appropriate, label entries for exclusion, or inject search results automatically. The Skill-using agent selects, combines, rewrites, or ignores results according to the request and active image interface. After term selection, use the [Prompt Writing Guide Runtime](prompt-writing-guide.md) for final ordering, supported weighting syntax, and model-facing rendition.

## Resolve the active dictionary

Resolve the logical resource from the same explicit pack state used by the task:

```bash
python scripts/pack_cli.py resource prompt-vocabulary
```

Pass the resolved file to the search command. When no enabled provider supplies the optional resource, continue without it.

## Search

```bash
python scripts/search_prompt_vocabulary.py "low angle" \
  --dictionary DICTIONARY_JSON --record lookups.json --element camera
```

`--record` appends the query and its returned terms to the retrieval record under that element.

Run the searches for every element in one process with `--queries`, which takes a JSON object literally, from a file, or from `-` for stdin:

```bash
python scripts/search_prompt_vocabulary.py --dictionary DICTIONARY_JSON --record lookups.json \
  --queries '{"camera": ["low angle"], "lighting": ["soft light", "rim light"]}'
```

Each query is recorded under its element exactly as a single search records it.

Restrict an ambiguous lookup by category:

```bash
python scripts/search_prompt_vocabulary.py "soft light" \
  --dictionary DICTIONARY_JSON \
  --category Lighting \
  --limit 12
```

Browse categories without loading the complete dictionary into prompt context:

```bash
python scripts/search_prompt_vocabulary.py \
  --dictionary DICTIONARY_JSON \
  --list-categories
```

`--dictionary` may be repeated when the caller deliberately searches several resolved dictionaries. Results rank in this order:

- the exact term or alias;
- terms and aliases holding every query word;
- terms and aliases holding the query inside a longer word, such as `rainbow` for `rain`;
- entries whose description holds the query, or the query words the term lacks;
- entries holding only some of the query words.

Results are lexical candidates rather than adopted prompt text.

## Read a finished prompt

```bash
python scripts/search_prompt_vocabulary.py   --dictionary DICTIONARY_JSON   --read prompt.txt   --negative negative.txt
```

Readback returns the written terms with every matching dictionary definition,
including category guidance, aliases and usage notes. Several definitions may
share a spelling. An unmatched term reports lookup coverage, not invalidity.
Use the complete prompt and selected interface to decide which meanings apply.
This lookup reads comma-separated phrases literally, preserving punctuation
and numeric content. For weighted or compound conditioning, use
`check_tag_prompt.py` with the interface's explicit parser selection under
[Prompt Writing Guide](prompt-writing-guide.md#read-the-rendition-back-before-it-is-sent).

The same reading is what a user is shown before a run when the decision is theirs, beside a rendering in their language.

## Data contract

Categories have an English `name`, an English `description`, and entries. Each entry requires only `term`; `aliases` and an English `description` are optional. The resource stores no per-entry source metadata, review state, content gate, exclusion flag, or automatic-use decision.

The command fails without partial results when the file is missing, malformed, invalid against `schemas/prompt-vocabulary.schema.json`, contains duplicate normalized terms inside one category, repeats a term as its own alias, receives an empty query, receives a `--queries` value that is not an object of element names and queries, or receives an invalid limit.

## Regression

```bash
python scripts/prompt_vocabulary_smoke_test.py
```

The regression creates a fictional temporary dictionary. It also searches the commons dictionary for `solo` and `cable knit` and checks only the ranking order: the exact term first, and entries holding every query word above entries holding one.
