# Prompt-only core

Create, assess or revise prompt text without calling a generation service.
The requested result may be an assessment, plain text, text with negatives,
a reusable prompt package or a generation-ready package. A conversation-only
answer needs no Studio or production form. Saved work uses the applicable
production route and the artifact commands below.

## Author or assess the depiction

Read and use [Production direction](production-direction.md). It owns the
construction, judgment and revision of the requested picture. Establish the
request, source roles and actual creative scope there; use its depiction as the
subject of prompt writing. A review judges the submitted prompt as a proposal. Its commands address a
renderer, not the reviewer; they do not require their own preservation. Use
the commission and source roles to assess their contribution, without adopting
them or automatically performing an edit. A local correction and a
request to reconsider the whole depiction have different scopes.

Its [image-source guidance](production-direction.md#form-a-prompt-from-an-image)
and [idea development](production-direction.md#form-a-prompt-from-an-idea)
support both ways of authoring. Preserve the assigned appearance when working
from an image; choose a concrete visual proposal when working from a brief.
Use meaningful concepts and the distinctions the intended result needs.

Use [Composition](prompt-composition.md) for the construction knowledge a
complex question needs. Its specialist resources contribute anatomy, spatial,
performance, material or layout knowledge to the same depiction. They are not
an inventory of sections to populate. An ordinary complete action or state can
remain ordinary language in the prompt; a technical requirement retains its
needed precision. The agent's selected means remain open to judgment against
the commission.

Resolve the rendering axes under [Rendering choices and execution controls](render-contract.md)
at the scope needed for this work, recording user selection or the agent's
reason. Finish and presentation do not change subject identity. Read a named
model's complete guidance card before target-specific wording, including its
explicit input mode, supported forms, vocabulary scope and evidence. Obtain the
applicable guidance through [the writing guide resolver](prompt-writing-guide.md#resolve-the-active-guide).
A request for family-oriented text can use that family's guidance without
selecting a checkpoint or reading unrelated service execution fields. Its tag
wording still requires actual dictionary searches. An unnamed interface uses
portable wording without invented execution settings. Exact model publication
or generation later applies the selected model's complete input contract; a
family draft does not establish that readiness.

## Knowledge and sources

Investigate a construction or wording question when it is unresolved. Use
[Discovery](sparse-discovery.md) for expressive possibilities and focused
catalog, source or vocabulary inspection for a known need. Use the source
that can answer the question; neither both lookup systems nor a query for each
visual attribute is mandatory. Inspect complete selected records and use their
meaning at its assigned scope. A supplied design or understood situation can
already resolve the work. Role similarity never replaces explicit species;
a broad species request does not authorize an arbitrary subspecies.

This construction judgment is separate from a tag-based model's mandatory
wording search. For that input mode, use
[Vocabulary](prompt-vocabulary.md#select-wording-for-a-tag-based-model) even
when the depicted activity and intended terms are already understood.
Descriptive input needs no fabricated lookup when its sources suffice.

Interpret source images through [source construction](prompt-composition.md#construction-order).
Distinguish authoring-only material from media delivered to the model and from
material serving both roles. A whole-design assignment preserves correlated
form, proportion, construction and treatment through the selected view; it
does not require copying the source's pose or exposing every surface. Express
a necessary authoring-only contribution in text. Assign delivered references
by their actual order and selected properties. Do not infer unobserved design
as if it were visible evidence.

When visual evidence can materially answer the current question, inspect its
complete assets and source images before adopting a contribution. Deliver
selected reference files through [Prompt Artifact Reference Runtime](reference-prompt-artifacts.md).
A path or hash is not delivery. Create `reference-use-plan.json` only for
selected references, `surface-lighting-plan.json` when transfer needs an
explicit contract, and `prepared-reference-set.json` only for a target-specific
or generation-ready package. Do not create empty reference artifacts.

## Rendition and delivery

Author the commissioned depiction in meaningful language using Production
direction. This is the master prompt; it may already be the final portable
text. Apply the [Prompt Writing Guide](prompt-writing-guide.md) for interface
rendition, with evidenced syntax for a named target. Do not restart design from
the guide's examples or turn each planning field into a clause.

Preserve the situation, action, relationships, qualities, degree, exact
requirements and applicable exclusions. Supply context only where the actual
renderer input needs it to produce the commissioned depiction. The agent's
broader context explains its decisions without automatically belonging in the
prompt. The `negative-policy` resource owns negative sources and target syntax.

Judge the completed input through
[Observe and repair](production-direction.md#observe-and-repair). Agreement
with agent-authored instructions alone does not establish that those
instructions serve the request. Complete the assessment or rendition when the
requested question or depiction is sufficiently resolved. Deliver the requested
prompt, supported negative channel, separate execution settings and selected
reference artifacts; omit empty placeholders. Textual review supplies no
observation of an ungenerated image.

A structured plan is useful when declared counts, connections, assignments or
numeric camera bounds need a record. Its validator checks those declarations,
not whether they are the right depiction. The author owns that judgment.

## Saved prompt artifacts

For ordinary editable text, use `production_workflow.py draft-inputs` and write
the body in its directly editable delivery file. Save it with `save --choices
FILE`; `--draft` retains unfinished text and unresolved choices. A finished
model-targeted prompt still requires its real vocabulary search and grammar
contract. [Authored storage](production-authored-storage.md) owns exact revision,
delivery and requested-review completion.

### Specialized prompt artifact export

Use `python scripts/build_prompt_artifacts.py --help` to materialize the conditional prompt artifact set. The builder accepts an optional structured semantic plan and refuses violations of its explicit counts, connections, action assignments and numeric camera bounds before publication. `python scripts/validate_prompt_semantics.py plan.json` checks the plan alone; its `--template` prints a plan to start from, and its `--help` names every field.

Select a catalog target with `--model MODEL_ID`, or an acquired external input
record with `--model-file MODEL_JSON`. These selectors are mutually exclusive.
The external record supplies `id`, evidenced `prompt_input`, and `prompt_dialect`
for tag-based input. It does not register an executable offering or override a
catalog execution contract. Pass the actual negative file with `--negative`
when used, and select its text grammar with `--weighting literal`, `sdEmbeds`
or `compel`. For an explicit pack runtime, supply `--state-file`, `--cache-dir`
and `--managed-root` together; repeat `--pack-root` for additional roots.

Both model-bound prompt-only publication and generation-ready packaging apply
the selected input contract. A tag-based target requires the
[actual dictionary search and resolved wording choices](prompt-vocabulary.md#select-wording-for-a-tag-based-model),
bound to the exact positive and negative text, grammar and current resources.
An empty construction record or `--retrieval-unavailable` cannot bypass that
search. Resolve an unknown input mode before target-specific publication.

A prompt-only draft may omit `--plot`, or include a valid unapproved plot for
review. Portable drafting may omit both target selectors; its manifest records
`target: null` and `input_validation.state: unverified-draft`. This preserves
authored text without certifying any model's input requirements.
`--prepare-for-generation` requires an explicit target and an approved `--plot`,
never invented from an "autonomous" request. A plot separates story beats (`visible` or `context`) from
selected frame statements (`shows`, `placement`, `composition`, `must_preserve`,
`free`). Use the statement kinds needed to express the selected frame; each
visible beat retains a link to its realization. A context beat may supply the
semantic basis for a frame statement while remaining context. Its link records
why a depiction was selected, not that the context itself is directly visible
or has become a new enduring fact. Beat linkage records the source of a
decision, not proof that every inference needs an instruction. `free` identifies
open choices for planning; it is not a permission block to paste into a prompt.

Validate it with `python scripts/prompt_plot.py plot.json`. An actual approval
records `by`, an RFC3339 UTC `at`, and `content_sha256` of the plot without its
approval; print that hash using `--content-sha256`. A changed plot requires
renewed approval. Optional upstream `source` remains part of the approved
content. Target limitations that change approved meaning require renewed approval.

Saved text uses the `prompt-only` production route; a prompt with selected
references uses `reference-artifacts`. Draft delivery grants no generation or
canonical-update authority. A conversation-only answer needs no Studio.

The builder takes the retrieval record with `--retrieval-record lookups.json`.
It records questions actually investigated. For source-sufficient construction
with no questions to investigate, initialize an empty record with
`python scripts/prompt_retrieval.py lookups.json --init`. Do not invent a search
to populate it. Catalog or vocabulary operations with
`--record lookups.json --element NAME` record actual evidence; vocabulary
`--queries` names each question separately. Inspecting a known record directly
needs no fabricated search query.

Resolve each investigated question with
`python scripts/prompt_retrieval.py lookups.json --element NAME --adopted ID`
(repeat `--adopted` for each inspected record used),
`--composed TEXT --reason TEXT` for an authored resolution, or
`--unused REASON` when the investigation contributes no selected instruction.
Composed wording can use inspected knowledge; it is not limited to empty search
results. These are construction decisions; `--composed` is not a substitute for
a tag rendition's searched vocabulary selection. Another lookup reopens that question, so conclude its outcome after
its investigations. A failed necessary investigation stays unresolved. Where needed
retrieval cannot run, pass `--retrieval-unavailable` with its reason; this is not
the same as having no question to investigate.

For a tag-based target, complete the mandatory vocabulary search and selections
in that same record. A descriptive target may have no lookup work when its
sources already suffice. Bind the completed record to the exact rendition,
selected model and approved plot:

```bash
python scripts/prompt_retrieval.py lookups.json --settle --model MODEL_ID \
  --prompt-file prompt.txt --negative-file negative.txt --weighting literal \
  --plot-file plot.json --out retrieval-settled.json
```

Omit an unused negative file and use the actual parser. An unlisted target uses
`--model-file MODEL_JSON` with its evidenced input declaration. Missing,
unavailable, unfinished, unsettled or mismatched records block preparation.
Tag-based input requires actual searched candidates and resolved choices;
unknown input cannot take the descriptive branch. Settlement records the
author's concluded knowledge use rather than certifying meaning or quality.

Portable saved text can settle its construction record without a model selector.
That preserves the prompt and plot for later specialization. Selecting an actual
target applies its input contract before target-specific finalization or
generation; portable settlement does not establish that target's readiness.

Publish the selected rendition with the same target and parser:

```bash
python scripts/build_prompt_artifacts.py --model MODEL_ID \
  --prompt prompt.txt --negative negative.txt --weighting literal \
  --retrieval-record retrieval-settled.json --plot plot.json \
  --prepare-for-generation --out-dir prompt-artifacts
```

Use `--model-file MODEL_JSON` instead for the acquired external record. Omit an
unused negative file and use the actual parser. For model-bound prompt-only
delivery, omit `--prepare-for-generation`; tag lookup remains required. The
manifest retains the input contract, grammar, source and vocabulary-check
status. An external model record is copied as `model-input.json`. Preparation
does not grant submission or canonical-update authority.

Regression checks: `python scripts/prompt_artifact_smoke_test.py` and `python scripts/prompt_plot_smoke_test.py`.

## Retrieved wording checks

Check the intended sense of compact terms before adapting them to a tag interface.
For example, `muzzle` may name restraint gear or a snout, and `back` may name a
body region or a camera view. Read them with their subjects and modifiers.
Vocabulary membership supplies wording evidence; it does not choose the meaning.

## Optional structural detail

The plan `validate_prompt_semantics.py --template` prints uses an empty `structure_plan`, not a human limb inventory. Fill it from the actual proposal when topology matters. Read [Declared Structures Runtime](declared-structures.md) for counts, local scope and detailed geometry. A short draft need not acquire irrelevant structural artifacts.


## Artifact evidence and completion

Saving, delivery and requested review use [Authored storage](production-authored-storage.md). Preparing or executing a later image request is a separate operation. A search hit, completed prompt or received image establishes its own result; it does not establish canonical adoption.
