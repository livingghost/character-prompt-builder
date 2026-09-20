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

Art direction comes first: form the image intent, preserve every user anchor, complete semantic planning, and select the active model record and adapter before rendering.

## Resolve the active guide

Each model family reads a prompt its own way: rating terms, multi-word tag spellings, working weights, and the blocks of a rendition and their order all differ. A rule proven on one family and handed to another spends budget and steers nothing.

The `prompt-dialects` resource holds one entry per family, a model record names its family in `prompt_dialect`, and a guide section names the families it applies to. Resolve all of it for the active model in one step:

```bash
python scripts/prompt_dialect.py --model <model-id>
```

It returns:

- that family's tag grammar, block order, and quality, rating, period, and inert vocabulary;
- the guide sections that apply, and the sections withheld because they belong to another family;
- the record's own recommended text, parameters, and sizes.

A record that lacks a family is reported as a non-tag target, and only the universal sections come back. `--list` names the families the resource carries, and `--dialect <id>` answers for a family that lacks a record.

Add a family by adding a dialect entry with its sources; the scripts stay unchanged. Its regression test is `scripts/prompt_dialect_smoke_test.py`.

Resolve the guide on its own through the same explicit pack state when only its rules are wanted:

```bash
python scripts/pack_cli.py resource prompt-writing-guide
```

When a selected provider exists, read the complete resolved JSON before writing the final model-facing rendition, rather than a remembered excerpt. When every enabled provider lacks the optional resource, continue under the active adapter and model record alone.

## Application sequence

1. Finish the master prompt free of parser-specific notation.
2. Select the exact model record, interface, and adapter.
3. Resolve the active model's family and the rules that apply to it with `scripts/prompt_dialect.py --model <model-id>`. A rule from a section that names a different family stays unapplied.
4. Apply interface-neutral construction rules that improve hierarchy, concision, visible scope, and controlled testing.
5. Apply parser-specific separators, attention syntax, LoRA notation, negative transport, embeddings, or editor shortcuts only when the active interface supports that exact behavior.
6. Render selected vocabulary terms into one coherent prompt. Search results and guide examples are candidates and grammar demonstrations rather than automatic prompt expansion or boilerplate.
7. Review the final rendition against the image intent, anchors, Production Specification, adapter contract, and model-record recommendations.

The Skill-using agent decides which rules are relevant. The active adapter and model record decide what the interface can receive. The guide's authority ends at the rendition; the requested concept, medium, identity, scene state, visual authority, and negative-transport contract lie outside it.

## Weighting and prompt pressure

Use attention weighting only to express a real priority in a compatible parser. Large weights are the wrong repair for contradictory anatomy, camera, action, or reference roles. Parentheses, square brackets, and numeric weights are interface syntax rather than universal prompt language.

A weight raises attention on the tokens of a term. Binding the term to the thing the writer meant is a separate matter, and that distinction decides whether a weight helps or harms. On a term the checkpoint was trained on, the attention lands where the term already lands, and the weight is a priority. On an untrained term, the attention lands wherever those tokens reach on their own, and the weight multiplies that. An invented marking name at high weight puts the marking wherever the picture has room for it, and an invented garment name dresses the wrong part. So confirm that the vocabulary knows a term before weighting it. When it lacks the term, the repair is a term the surface knows, or a reference image, rather than a larger number. A term that must be invented is written plain and checked in the result.

Assume nothing about a universal 75-token ceiling: prompt capacity, chunking, and truncation are properties of the active encoder and workflow. Keep high-priority construction early when the interface is tag-oriented, and keep required semantics even when a remembered number argues for cutting them.

A non-load-bearing off-frame detail may be omitted from the model-facing rendition when it consumes scarce prompt capacity or visibly damages the current frame. Preserve it in canonical identity or scene state when continuity still owns it.

A negative channel is for qualities that arrive uninvited. Before adding a term to it, check whether a positive term is requesting the quality being suppressed; if so, remove that positive term instead. Negatives that contradict live positives fight inside one representation and usually damage the wanted content along with the unwanted. A negative list that grows across successive revisions is a symptom of an unresolved positive-side cause rather than of a thorough exclusion policy.

## Controlled comparison

When the task is to test whether a term, placement, weight, LoRA strength, or negative token changes the result, follow the guide's controlled-comparison section. Hold the remaining generation conditions constant and change one variable at a time. Treat the result as evidence for that exact setup rather than as a universal rule.

## Read the rendition back before it is sent

A tag rendition can be wrong in ways the returned image leaves unreported:

- a numeric weight written where it fails to bind leaves its digits in the prompt as text;
- a repeated tag spends budget for nothing;
- a term sits in both the prompt and the negative;
- two terms the vocabulary itself calls opposed ask for different pictures.

```bash
python scripts/check_tag_prompt.py --dictionary <prompt-vocabulary/dictionary.json> --prompt "<the rendition>" --negative "<the negative>" --model <model-id>
```

The checks read the resolved vocabulary resource rather than a list kept in the script. They use:

- a category the resource marks as describing one figure at a time;
- the terms it names as putting more than one figure in the picture;
- the terms each entry declares it opposes.

With `--model` the rendition is also held to the record's declared prompt lengths and negative channel, and to its family. The family checks report more than one rating or period term from that family's set, a term the family lacks, and an explicit weight outside the range the family works in.

Output is JSON on stdout with a `findings` list. A problem is a statement about the rendition's own grammar or about a pair the vocabulary calls incompatible; a note is a reading worth confirming, such as a term missing from the vocabulary or a chunk after a break that lacks a count tag. The exit status is 1 when a problem is reported, and the command exits with a message when the dictionary path is anything but a file. The check only reports; which finding to act on is the agent's decision. Its regression test is `scripts/check_tag_prompt_smoke_test.py`.

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
