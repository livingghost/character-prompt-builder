# Explicit prompt weighting

Use this alongside the [Prompt Writing Guide](prompt-writing-guide.md) when a target
exposes `promptWeighting`. A model's learned family (`prompt_dialect`) chooses its
vocabulary and writing conventions. The selected service, offering and execution
mode choose the weighting parser. A family name never authorizes a native control.

## Choose the interface before writing parser syntax

Run `pack_cli.py ready`, resolve the model and choose its execution mode first.

```sh
python scripts/prompt_dialect.py --model MODEL_ID --service SERVICE --mode text-to-image --weighting compel
python scripts/prompt_dialect.py --weighting compel
```

The first command reports the family and the exact control schema from that
model/offering/mode, and fails when it does not allow the requested grammar. The
second describes grammar only; it is not evidence that a provider model accepts
it. For example, Runware's SDXL page lists `compel` and `sdEmbeds`, while its FLUX.1
Schnell page lists only `sdEmbeds` as the actual allowed value. Generic explanatory
text mentioning both is not a substitute for the selected model's control schema.

Write the native choice in the existing generation parameter file:

```json
{"width": 1024, "height": 1024, "steps": 30, "promptWeighting": "compel"}
```

These numbers illustrate file shape, not defaults. The model's geometry and
control schema must accept the actual values. Pass that file as the usual
`generation.parameters` task input or the builder's `--parameters` file. There
is no model ID suffix, a second service adapter, or a new weighting service.
Without a selected native control, CPB uses `literal` inspection: it neither
inserts `promptWeighting` nor guesses Compel from punctuation. A required control
may resolve an explicit record recommendation through normal parameter handling;
an optional control is not automatically activated by a recommendation.

## Author the matching rendition

| Intent | sdEmbeds rendition | Compel rendition |
|---|---|---|
| Explicit fragment weight | `(blue eyes:1.2)` | `(blue eyes)1.2` |
| Repeated emphasis | `((blue eyes))` | `(blue eyes)++` |
| Reduced emphasis | `[blue eyes]` | `(blue eyes)-` |
| Parentheses without an explicit suffix | Apply implicit emphasis | Group the phrase without implicit emphasis |
| Separate conditioning clauses | Do not assume Compel operators apply | `("solo, blue eyes", "forest, soft lighting").and()` |
| Weighted blend of clauses | Do not assume Compel operators apply | `("blue eyes", "green eyes").blend(1, 0.8)` |

The examples demonstrate grammar, not interchangeable embeddings or expected
image quality. Compel's documented `+` multiplier is 1.1 per suffix and `-` is
0.9 per suffix. sdEmbeds-style square-bracket reduction uses the reciprocal of
1.1; it is not the same numeric reduction. Write explicit weights when comparing
setups and review the images, rather than claiming parser equivalence.

Compel parentheses group multi-word phrases; a suffix after one word weights that
word, not an entire preceding sentence. Quoted/grouped clauses keep internal
commas and nested weights. Backslash escapes keep literal delimiters from acting
as parser instructions. Keep intended punctuation and grouping explicit.

`.and()` encodes independent conditioning chunks; it does not assign subjects to
spatial regions or guarantee identity separation. `.blend()` combines weighted
conditioning. The inspector retains each clause, coefficient, fragment weight
and source range. It does not calculate embeddings, image composition, token
capacity or the resulting appearance. Signed coefficients need author review;
lexical overlap alone does not establish their combined effect.

The local inspector recognizes the upstream forms `.attend(weight)`, `.add()` as
an alias of `.and()`, and the final `no_normalize` option to `.blend()`. They are
upstream grammar forms, not a promise that every hosted build enables them.
Use the provider-documented subset for ordinary service work. The selected
model's validated interface evidence still owns what can be sent.

Prompt-to-prompt `.swap()`, arbitrary method calls and `useLora`/`withLora` macros
are not implemented in CPB's hosted-text grammar. They need distinct pipeline or
resource support; select LoRAs through the service's declared native controls.
`BREAK` is not a Compel conjunction. CPB never translates `BREAK`, `AND`, brackets
or colon weights into another parser's operators by guessing the author's intent.

## Inspect the complete request, not a flattened tag list

```sh
python scripts/check_tag_prompt.py --dictionary DICTIONARY_JSON --model MODEL_ID --weighting compel --prompt '("solo, blue eyes", "forest, soft lighting").and()' --negative 'lettering+, watermark'
```

Resolve `DICTIONARY_JSON` with `pack_cli.py resource prompt-vocabulary`; the
standalone checker takes that file explicitly. Normal Production preparation
resolves the active dictionary automatically. The standalone `--weighting` must
match the planned native parameter; inspection alone does not authorize a request.

During normal `prepare`, the syntax comes from the resolved parameter and the
actual wire layout. Both positive and negative fields are parsed after model
recommendations, negative-channel selection and reference instructions. Mixed
syntax, broken delimiters, ignored trailing text, non-finite weights or invalid
clause arity stop preparation. The final request bytes are not rewritten by the
inspector. Vocabulary checks run within each conditioning clause, and the report
keeps `channel`, `clause` and character ranges so the author can locate a finding.
A repeated term in two independent clauses is not a duplicate in a single clause.
The combined picture is still an author review, not a mechanically proven result.

`execution_plan.prompt_check` stores the selected syntax, parsed channels,
findings, dictionary meanings and the verified model-recommendation audit beside
the full request. A target without a
learned tag family still receives syntax checks, without pretending prose is
booru vocabulary. Dictionary notes and clause-meaning notes are not approval.

## Recommendations and shared reference instructions

A model's automatic tag-list merge must not flatten commas inside weighted groups
or duplicate the author's entire compound expression. For a simple weighted
prompt, additions remain independent tags and the authored fragment retains its
exact bytes. For `.blend()` or `.and()` expressions, automatic positive/negative
recommendations stay visible as advisory audit entries, with
`conditioning-clauses-preserved; author places recommendations explicitly`.
The author places any necessary shared guidance inside the intended clauses,
then prepares and approves that complete rendition. Optional recommendations
are not silently copied into every clause or dropped without a recorded reason.

When the record's optional recommendation itself uses another syntax (for example
an sdEmbeds `(term:1.2)` recommendation while Compel is selected), it is retained
as visible advice with `recommendation-syntax-mismatch; author supplies matching
grammar`. CPB does not translate it, apply its old parser's numeric semantics, or
rewrite the selected model record. The author can place any wanted guidance in
the appropriate authored clause and approve the resulting request. Invalid
**authored** text is still an error, not an advisory recommendation.

The same boundary applies to reference/policy prefix text. A prefix that leaves
an entire compound outside the supported grammar is refused rather than guessed
into its clauses. Select a declared native reference mechanism or author the
instructions into the clause scope explicitly. Do not bypass the final request
check to send a textually different prompt.

## Approval, recording and recovery

Changing `promptWeighting`, clause text, coefficient or the final negative channel
changes the sealed request. The normal complete-request approval, current input
checks and one-send execution claim apply. Recorded response recovery uses the
fixed package, grammar choice and text; it does not convert an old request into a
new grammar or send it again after a timeout. This extends the existing Production
path, not an out-of-band generation shortcut.

No Python `compel`, PyTorch, Transformers, browser, API SDK or other parser package
is required. CPB uses a bounded standard-library inspector; the provider performs
conditioning. Its supported structural grammar is not a replacement for every
upstream parser extension or a prediction of provider image behavior.

## Example and verification

[The synthetic example](../../examples/prompt-weighting/README.md) generates a
reproducible inspection report and a native Runware-shaped request without network
I/O or approval. Tests are `prompt_weighting_smoke_test.py` and
`prompt_weighting_execution_smoke_test.py`, plus existing generation, state-aware,
transport and recommendation regressions. They use synthetic models and fixtures,
never an owner's private pack. No browser-launching tests are added.

## Sources

Reviewed 2026-10-09. The first three are provider declarations; the last two are
upstream grammar. A feature in upstream Compel is not proof of hosted model support.

- [Runware prompts and weighting](https://runware.ai/docs/learn/prompts)
- [Runware SDXL native control](https://runware.ai/docs/models/sdxl)
- [Runware FLUX.1 Schnell allowed control](https://runware.ai/docs/models/flux-1-schnell)
- [Compel syntax reference](https://github.com/damian0815/compel/blob/main/doc/syntax.md)
- [Compel parser implementation](https://github.com/damian0815/compel/blob/main/src/compel/prompt_parser.py)
