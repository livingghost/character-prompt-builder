# Prompt Vocabulary Runtime

## Activation

Use this runtime while defining a character and when finding English wording
for a selected construction. Category browsing can help discover expressive
forms. It also owns the required dictionary search for every selected
`tag-based` model rendition. Discovery can precede the direction choice;
compact terms alone do not explain a form's purpose or make it appropriate.
Inspect applicable production records and use
[Production direction](production-direction.md#choose-the-expression) to choose.
During prompt assembly, use the
[selected construction and wording questions](prompt-composition.md#catalog-retrieval-and-inspection)
as retrieval elements. Search their meanings together where a relationship or
modifier determines the wording. Prefer fitting terms or close synonyms that
preserve meaning, scope and degree. Keep authored wording where no term fits
or supported prose carries the meaning, including within a mixed rendition.
Honor an explicitly exclusive input form and retain genuinely unresolved
requirements with their limits (see
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

Pass the resolved file to the search command. Character-definition authoring
uses it as described below, even before a target model is selected. A tag-based
rendition requires the active dictionary and owning dialect resources. If they
are unavailable, resolve that resource need before completing its model-specific
wording. Descriptive and portable work can retain precise authored wording when
a dictionary is unavailable; record the research gap instead of claiming a
dictionary match. A missing resource never changes the target's input mode.

## Define a character with usable wording

Research wording while creating or materially revising the
[character definition](production-direction.md#establish-the-character-for-this-use).
The agent does this work without waiting for the user to request a lookup or
supply technical terms. Develop the intended meaning and its usable wording
together, including the distinctions that matter in construction, appearance,
surface, clothing, equipment and bodily or functional expression. Use the
subject's actual structures and the task's scope; these are possible areas of
research, not mandatory fields or a human anatomy checklist.

Follow the definition's current depth. Research the distinctions being
developed for this proposal and add mappings when later work makes another
detail relevant. The first idea does not need a complete vocabulary for every
future outfit, expression or state. Open design choices can remain open;
dictionary coverage does not decide how much of the character must be settled.
Make useful provisional choices within delegated scope and show their meaning
so the user can respond in ordinary language.

Group related meanings into useful searches. A selected expression may need
eye opening, mouth shape and gaze together; a material choice may need its
finish, pattern and coverage together. Resolve the active dictionary and run
the actual [Search](#search) commands, batching related questions with
`--queries` and recording them with `--record`. Reuse the task's retrieval
record, initializing one with
`python scripts/prompt_retrieval.py lookups.json --init` when absent; temporary
files suffice for conversation work. Reuse applicable earlier investigations
and mappings, and research additions, changed scope or unresolved distinctions.
Neither a separate search for every attribute nor a dictionary match for every
word is required.

If a search cannot run, identify the unavailable resource or operation and
continue the precise definition with authored wording and that research gap.
An execution failure is not evidence that the dictionary lacks a term. A
successful search with no fitting candidate leaves authored wording necessary
within the examined scope; it does not prove exhaustive absence. Preserve that
difference without turning wording research into an approval step for creative
proposals.

Inspect the complete selected entries, including category guidance, aliases,
other senses sharing the spelling and any usage notes. The [readback](#read-a-finished-prompt)
command can read a temporary file of candidate phrases before a final prompt
exists. Search rank, a familiar spelling or an emotion label does not establish
a semantic match. Compare the candidate's actual meaning, scope and degree
with the intended individual definition. Where the inspected entries supply no
fitting term, retain precise authored wording that carries the missing
distinction; state the remaining limitation when the intended form itself is
still unresolved.

Write the corresponding wording beside the meaningful definition in its
existing owner. A short paragraph or table can show:

- the concrete definition, its applicable conditions and permitted variation;
- the selected dictionary terms or aliases, their applicable sense and the
  dictionary resource and category that identify the inspected entries;
- authored phrases needed to preserve distinctions the terms do not carry,
  with a brief reason where the gap is consequential;
- the relevant element in the existing retrieval record, or a concise source
  and query note when no persistent record is being kept.

Shared source and query notes can cover a group of related definitions.

For words that combine age, physique, role or other meanings, distinguish the
selected visual sense from the character's established facts. Consult the
target's evidence and actual observations for its effect, rather than deriving
that effect from dictionary membership. When ambiguity is consequential,
record the selected sense and any completing phrase in the existing definition
or authoring note. Use [Interface rendition](prompt-writing-guide.md#choose-terms-for-their-intended-visual-sense)
to carry it into the prompt. Do not infer canonical age from a keyword,
automatically prohibit or replace a class of terms, or require annotations
for every word.

For example, a definition may retain a closed mouth with gently raised corners
and eyes still open. If the inspected dictionary entry supplies a suitable
smile term but leaves eye opening unspecified, list that term with its actual
source and keep the authored eye-opening phrase beside it. The broader term
does not replace the more precise definition. This is a synthetic authoring
example, not a claim that any particular dictionary contains that entry.

Keep these associations with the property's existing description or notes:
Persona PHYSICAL for its embodied repertoire, the applicable Identity or
Appearance owner for visual properties, or the current scene for a local
choice. When presenting a character definition or concrete design proposal,
show the corresponding usable wording with the details it expresses, even
when the user has not asked for tags. A short parenthetical or a few paired
lines can do this in conversation; use ordinary explanations and keep commands,
internal paths and long lookup logs in the working record. Distinguish searched
dictionary wording from authored phrases. Present only the associations for
details being developed, not a vocabulary inventory or another questionnaire.
Reuse the pairing on later turns and show changed associations with changed
details; unchanged notes need not be repeated.

A final prompt by itself does not preserve this association: a reader cannot
tell which words were inspected or which concrete meaning they were chosen to
carry. If an explicit output restriction permits only the prompt, retain the
pairing in the existing definition source or temporary authoring notes rather
than adding unrequested output. Do not defer the pairing until prompt delivery,
leave the selected words only in a search log, create another canon, or use
the Persona's spoken Vocabulary Registry for image prompt terms. The generic search record preserves queries and returned term
names; the definition's wording note preserves the chosen source, sense and
authored completion. It is not a model-bound vocabulary selection record.

Preserve the complete definition as authority. A term's availability does not
adopt a design choice, supply undeclared anatomy or establish a model's learned
effect. Without a selected model, the correspondence is semantic authoring
material. Later prompt assembly selects the applicable wording, carries any
necessary authored relationships and resolves it again under the actual
model's input contract, vocabulary scope and parser. The model-bound procedure
below remains responsible for that rendition's lookup and verification.

## Select wording for a tag-based model

The selected-model read returns `prompt_authoring.vocabulary`, including the
search action, vocabulary scope and owning dialect. Use that result without
first classifying the model's text forms. Honor an explicit tags-only request;
otherwise follow the returned writing guidance under
[interface rendition](prompt-writing-guide.md#interface-rendition). A required
search applies even when the author knows the terms or prose is also available. Choose
the concepts that work together to carry the commissioned picture: its broad
organization, treatment and expressive effect as well as depicted objects.
Use the existing draft retrieval record;
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
its exact identity and any acquired input declaration. The script keeps absent
form metadata unresolved without asking the author to choose a category.

The same command resolves the selected model's search requirement. When lookup
is not required, it returns that result and the writing guidance without
inventing vocabulary selections. A no-text operation rejects supplied text.
When lookup is required, it searches every parsed term in the positive and negative clauses.
It records returned candidates, complete matching definitions, the model's
input contract, parser and resource hashes. Exact terms and aliases receive
dictionary choices automatically. That is lexical resolution; the author still
chooses the applicable sense and judges whether it serves the depiction.

For unresolved expressions, compare existing terms and close synonyms at their
actual meaning, scope and degree. Revise the text and search the rendition
again. When available vocabulary does not carry the required distinction,
retain suitable authored wording in the requested input form with its reason:

```bash
python scripts/prompt_retrieval.py lookups.json --retain-wording "AUTHORED_PHRASE" \
  --reason "WHY_AVAILABLE_WORDING_CHANGES_THE_REQUIRED_MEANING" \
  --query "RELATED_CONCEPT" --model MODEL_ID --prompt-file prompt.txt \
  --negative-file negative.txt --weighting literal
```

`--query` is repeatable and optional; use it for a useful conceptual or synonym
search. Retaining wording executes the searches again and keeps the candidate
evidence beside the author's reason. This records a lexical decision; it does
not establish that the target understands the expression. The selected input
contract and requested form govern its use. An empty result does not forbid an
authored phrase, and a similar-looking result does not make it appropriate.
Preserve necessary specificity instead of narrowing the picture to the dictionary.

When neither fitting tags nor supported authored wording can carry a distinction, use
[interface rendition](prompt-writing-guide.md#carry-the-construction-into-supported-means)
to choose the closest supported construction and explain its remaining limits.
Keep required detail in the source specification without pretending that every
part has entered the model's conditioning. Supported prose can carry necessary
relationships, but its length, comma separators or an invented tag spelling
alone does not establish a missing capability.

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

Use this dictionary readback for literal comma-separated term renditions or a
temporary phrase list. For a natural prose prompt, read the complete text to
assess its meaning, modifier scope, relationships and omissions. Use targeted
phrase lookup for an actual wording question. Splitting prose at commas does
not establish its meaning or provide a semantic quality check. A selected
model's required vocabulary work still follows the exact-model procedure above,
including when its rendition contains both terms and prose.

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
