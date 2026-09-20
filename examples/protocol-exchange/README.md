# Public artifact exchange example

```text
python examples/protocol-exchange/run_example.py --out EXAMPLE_DIRECTORY
python scripts/protocol_contract_smoke_test.py
```

Choose a new `EXAMPLE_DIRECTORY`. The example resolves a character-free room state, exports it, verifies the received bundle and checks a fully linked shot request. It writes the command log and validation results. It does not generate media or record acceptance.

`fixture-index.json` classifies the public artifact samples. `schema-only-synthetic` fixtures exercise field shapes and content hashes; their reference hashes do not prove that source media exists. `worked-example` fixtures derive from the supplied examples. `scene/` contains the workshop designs, states, cameras and projections used for complete binding checks. Its subject designs are examples, not protocol defaults.

See the [semantic contract](../../protocols/semantics.md) for the rules exercised here.
