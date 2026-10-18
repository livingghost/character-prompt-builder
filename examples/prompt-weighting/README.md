# Explicit weighting example

This is a synthetic, non-executable illustration. No service request is sent,
no provider capability is inferred, and no user approval is generated. Use
[Explicit Prompt Weighting](../../references/runtime/prompt-weighting.md) for the
normal model selection, Production preparation and authorization procedure.

```sh
python examples/prompt-weighting/build_example.py
python examples/prompt-weighting/build_example.py --check
python scripts/prompt_dialect.py --weighting compel
```

`positive.txt` uses Compel nested/suffix weights and independent `.and()` chunks.
`negative.txt` uses `.blend()` in the separately declared negative channel.
`parameters.json` shows the native parser field; its geometry/steps are examples,
not recommended settings. A real chosen model and mode must allow every value.

`inspection.json` retains exact input strings, clauses, numeric coefficients,
character ranges and an advisory recommendation audit. Its native request uses
Runware field names but an intentionally nonexistent model identifier and fixed
task UUID. Do not send this preview as an API request. The sdEmbeds section shows
its different grammar without claiming equivalent embeddings or images.

For normal task files, author the selected parameters in `generation.parameters`
and the exact negative text in `generation.negative`. The ordinary positive
prompt remains the task's declared delivery; do not add an unrelated top-level
prompt/negative field. Follow the existing negative-policy and integrated
fallback requirements; this feature does not infer an alternative rendition.

The inspector preserves compound scope. A reusable positive recommendation is
visible but not automatically prepended outside `.and()`. Put any required text
inside the intended clauses, prepare again, and approve the resulting complete
request. Do not infer that `.and()` binds two character identities to different
screen regions.
