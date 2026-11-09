# Prompt Vocabulary Runtime

## Activation

Use this runtime to discover expressive forms through category browsing or to
find English wording for a selected construction. It also owns the required
dictionary search for every selected `tag-based` model rendition. Discovery can precede the
direction choice; compact terms alone do not explain a form's purpose or make
it appropriate. Inspect applicable production records and use
[Production direction](production-direction.md#choose-the-expression) to choose.
During prompt assembly, use the
[selected construction and wording questions](prompt-composition.md#catalog-retrieval-and-inspection)
as retrieval elements. Search their meanings together where a relationship or
modifier determines the wording. Prefer a fitting term for a compact tag and
keep authored wording wherever no term fits or prose carries the meaning (see
[Prompt Composition Runtime](prompt-composition.md), Prompt assembly and review).

A prompt-vocabulary resource is ordinary pack-owned knowledge. It can contain
corpus vocabulary, aliases and authored descriptive wording. Dictionary
membership does not certify a term as a Danbooru or e621 tag, establish training
membership or promise a learned visual effect. The selected model's vocabulary
IDs and family evidence supply the lookup and usage scope. The agent selects,
combines or rewrites candidates according to their meaning in the commissioned
depiction. After selection, use the [Prompt Writing Guide Runtime](prompt-writing-guide.md)
for ordering, supported weighting syntax and model-facing rendition.

## Resolve the active dictionary

Resolve the logical resource from the same explicit pack state used by the task:

```bash
python scripts/pack_cli.py resource prompt-vocabulary
```

Pass the resolved file to the search command. A tag-based rendition requires
the active dictionary and owning dialect resources. If they are unavailable,
resolve that resource need before completing its model-specific wording.
Descriptive and portable work can proceed from sufficient sources without a
dictionary; a missing resource never changes the target's input mode.

## Select wording for a tag-based model

Read the selected model's `prompt_input` and its basis first. The tag-based
workflow requires real searches even when the author knows the terms or the
model also supports natural language. Use the existing draft retrieval record;
initialize it with `python scripts/prompt_retrieval.py lookups.json --init` when
needed. A conversation-only prompt can use temporary files without creating a
Studio.

A family-oriented tag draft with no selected checkpoint uses the family's
declared vocabulary scope, the active dictionary and the actual `Search`
commands below. Inspect the returned definitions and read back the complete
rendition under that family's grammar. This supplies searched wording for the
draft; model-bound saving or preparation uses the exact-model path that follows.

```bash
python scripts/prompt_retrieval.py lookups.json --search-vocabulary \
  --model MODEL_ID --prompt-file prompt.txt --negative-file negative.txt \
  --weighting literal
```

Omit `--negative-file` when there is no negative channel. Select the actual
weighting parser rather than copying the example's `literal`. An unlisted
target uses `--model-file MODEL_JSON` instead of `--model`; the file supplies
its exact identity and evidenced `prompt_input`, plus `prompt_dialect` for a
tag-based workflow.

The command searches every parsed term in the positive and negative clauses.
It records returned candidates, complete matching definitions, the model's
input contract, parser and resource hashes. Exact terms and aliases receive
dictionary choices automatically. That is lexical resolution; the author still
chooses the applicable sense and judges whether it serves the depiction.

For unresolved expressions, prefer an existing term or close synonym when it
preserves meaning, scope and degree. Revise the text and search the rendition
again. When available vocabulary does not carry the required distinction,
retain the authored expression with its reason:

```bash
python scripts/prompt_retrieval.py lookups.json --retain-wording "AUTHORED_PHRASE" \
  --reason "WHY_AVAILABLE_WORDING_CHANGES_THE_REQUIRED_MEANING" \
  --query "RELATED_CONCEPT" --model MODEL_ID --prompt-file prompt.txt \
  --negative-file negative.txt --weighting literal
```

`--query` is repeatable and optional; use it for a useful conceptual or synonym
search. Retaining wording executes the searches again and keeps the candidate
evidence beside the author's reason. An empty result does not forbid the
expression, and a similar-looking result does not make it appropriate. Preserve
necessary specificity instead of narrowing the picture to the dictionary.

For a conversation-only prompt, complete the searched choices and read back the
rendition; no plot, approval or settlement artifact is needed. For saved
generation, settle the record under
[Prompt-only Core](prompt-only-core.md#saved-prompt-artifacts). Vocabulary choices
bind the prompt channels, input contract, parser and resource content.
Preparation re-runs the search and verifies that binding; an empty construction
list cannot bypass it. The existing rendition review assesses meaning;
dictionary membership adds no semantic approval or image-quality verdict.

`scripts/prompt_vocabulary_selection.py` owns this selection and its
verification. The command, package preparation and external image-input
preparation share its model-bound search behavior.

## Search

```bash
python scripts/search_prompt_vocabulary.py "low angle" \
  --dictionary DICTIONARY_JSON --record lookups.json --element camera
```

`--record` appends the query and its returned terms to the retrieval record under that element.

Batch the selected questions in one process with `--queries`, which takes a JSON object literally, from a file, or from `-` for stdin:

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
