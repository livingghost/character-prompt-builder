# Prompt Writing Guide Runtime

## Activation

Use this runtime when a final prompt must be rendered for a named model or interface, or when the user asks about any of these:

- prompt order
- comma-separated tags
- parentheses, square brackets, and explicit weights
- LoRA strength
- negative-prompt handling
- Textual Inversion
- prompt-length pressure
- controlled comparison of one term

Adapt the selected depiction to one exact interface and adapter. Catalog targets
use their active model records; external generation or editing may use acquired
provider evidence while recording a missing catalog definition.

## Resolve the active guide

Each model family reads a prompt its own way: rating terms, multi-word tag spellings, working weights, and the blocks of a rendition and their order all differ. A rule proven on one family and handed to another can change the request without the intended effect.

The `prompt-dialects` resource holds one entry per family, a model record names its family in `prompt_dialect`, and a guide section names the families it applies to. Resolve all of it for the active model in one step:

```bash
python scripts/prompt_dialect.py --model <model-id>
```

It returns:

- that family's tag grammar, block order, and quality, rating, period, and inert vocabulary;
- the guide sections that apply, and the sections withheld because they belong to another family;
- the record's own recommended text, parameters, and sizes.

A record that lacks a family returns only universal sections. `--list` names available families; `--dialect <id>` answers for an evidenced family without a record. For an unknown external target, omit `--model` from route reading and apply only interface-neutral sections until evidence establishes a parser. Reading a family section does not authorize its syntax.

Add a family by adding a dialect entry with its sources; the scripts stay unchanged. Its regression test is `scripts/prompt_dialect_smoke_test.py`. `schemas/prompt-dialect.schema.json` validates the dialect resource, and `schemas/prompt-writing-guide.schema.json` validates the guide.

Resolve the guide on its own through the same explicit pack state when only its rules are wanted:

```bash
python scripts/pack_cli.py resource prompt-writing-guide
```

Read the complete resolved guide before writing the final model-facing rendition. When no enabled pack binds a guide, continue under the selected adapter and exact model or provider evidence.

## Application sequence

1. Finish the master depiction from selected requirements and purposeful choices. Make the whole image clear before refining attributes and necessary exclusions.
2. Select the exact interface, its catalog record or acquired external contract, and one adapter.
3. For a catalog target, resolve service weighting through [Explicit Prompt Weighting](prompt-weighting.md) and its family through `scripts/prompt_dialect.py --model <model-id>`. An external target uses only parser behavior its evidence supports. Rules for another family stay unapplied.
4. Preserve that whole depiction while applying the target's hierarchy and visible-scope guidance. Keep the identity and construction detail the image requires.
5. Apply parser-specific separators, attention syntax, LoRA notation, negative transport, embeddings, or editor shortcuts only when the active interface supports that exact behavior.
6. Search the pack's prompt vocabulary for each planned element through `scripts/catalog_cli.py search` or read the dictionary directly. Inspect definitions, usage notes and the selected model's evidence before choosing wording. Membership supplies vocabulary evidence; the author decides whether a term or descriptive phrase carries the intended meaning.
7. Render selected vocabulary terms into one coherent prompt. Search results and guide examples are candidates and grammar demonstrations rather than automatic prompt expansion or boilerplate.
8. Review the final rendition against the image intent, anchors, production or semantic edit plan, adapter contract and evidenced recommendations.

The Skill-using agent decides which rules are relevant. The exact model or provider contract decides what the interface can receive. The guide governs rendition; image intent and visual authority remain with their owning plans.

## Weighting and prompt pressure

Use attention weighting only to express a real priority in a compatible parser. Large weights are the wrong repair for contradictory anatomy, camera, action, or reference roles. Parentheses, square brackets, and numeric weights are interface syntax rather than universal prompt language.

A weight changes emphasis; it does not establish what a term means or which subject it concerns. Resolve ambiguous wording and reference roles before raising its weight. Use dictionary definitions and target observations as evidence, then inspect the result. An unlisted descriptive phrase may still be appropriate; absence from a dictionary is not a semantic verdict.

Assume nothing about a universal 75-token ceiling: prompt capacity, chunking, and truncation are properties of the active encoder and workflow. Keep high-priority construction early when the interface is tag-oriented, and keep required semantics even when a remembered number argues for cutting them.

Remove incidental detail that contributes no requirement or selected effect. Retain all specificity needed for identity, visible construction and the chosen scene, even when that requires a detailed prompt. Preserve the complete canonical identity and scene state at their owners. An omitted detail needs no replacement permission, exclusion or instruction to reveal it.

Use the `negative-policy` resource to assess applicable sources; a tag family's form is the `negative_form` that `scripts/prompt_dialect.py` returns. Keep required exclusions and corrections scoped to their intended subject, region or failure. Resolve a real contradiction by returning to the brief and source authority, then revise the conflicting wording. A repeated word across channels can carry different scopes; the author judges the combined meaning. When exclusions accumulate, return to the [selected depiction](prompt-composition.md#select-the-depiction): repair a missing target or unclear scope before adding another boundary. Retain necessary exclusions.

## Controlled comparison

When the task is to test whether a term, placement, weight, LoRA strength, or negative token changes the result, follow the guide's controlled-comparison section. Hold the remaining generation conditions constant and change one variable at a time. Record reference content and ordering as well as prompt and settings. If several change, compare the complete setups without attributing improvement to one change. Treat a result as bounded evidence, not a universal model verdict.

## Read the rendition back before it is sent

Inspect the exact rendition with the selected parser before reviewing its meaning. Structural checks locate broken delimiters, malformed weights, invalid conditioning clauses, unsupported channels and declared length violations. The report also retains dictionary and dialect evidence for the author's reading.

```bash
python scripts/check_tag_prompt.py --weighting sdEmbeds --dictionary <prompt-vocabulary/dictionary.json> --prompt "<the rendition>" --negative "<the negative>" --model <model-id>
python scripts/check_tag_prompt.py --weighting sdEmbeds --dictionary <prompt-vocabulary/dictionary.json> --prompt "<the rendition>" --dialect <dialect-id>
```

The example assumes an explicitly selected sdEmbeds parser; use `--weighting compel` for Compel or `literal` when no weighting control is selected. Independent conditioning clauses are checked separately and the original text is retained.

The checks read the resolved vocabulary resource and retain matched definitions, usage notes and declared dialect guidance. `--model` adds the record's declared prompt lengths and negative channel. `--dialect` names an evidenced family directly; an unknown ID is answered with the available IDs. Dictionary absence, repeated words, count terms, rating terms or lexical overlap do not establish a semantic failure.

Output is JSON on stdout with `syntax`, parsed `channels`, structural `findings` and the resolved dialect evidence. A `problem` describes a mechanical contract violation and returns exit status 1. A dictionary path that is not a file exits with a message. Preparation blocks mechanical problems; the author reads the complete positive and negative rendition with its actual media and judges the resulting picture. Its regression test is `scripts/check_tag_prompt_smoke_test.py`.

## Failure policy

Four shortcuts are refused:

- guessing parser support from a model family name;
- copying a sample quality stack as a default;
- converting a Textual Inversion token into generic prose;
- assuming a negative channel exists.

When guide advice conflicts with a reviewed model record or adapter, the model record and adapter own the transport. When interface behavior is unknown, keep the semantic prompt portable and stop before claiming unsupported syntax or parameters.

## Regression

```bash
python scripts/prompt_writing_guide_smoke_test.py
```

The regression uses a fictional temporary guide. It leaves every owner-maintained pack's current rules, examples, wording, and section count uninspected and unfixed as expectations.

### Final-request dictionary evidence

For a model with `prompt_dialect`, `prepare` checks the actual sealed positive and
negative text after model recommendations and transport conversion. Mechanical
`problem` findings stop preparation. The complete dictionary and dialect evidence
is saved in `execution_plan.prompt_check` for the existing rendition review.
Inspect that evidence with the complete request before approving it. A known word
can still be wrong for the intended anatomy or garment, and an unlisted phrase
can express it correctly. Fix the authored wording when meaning is wrong.
