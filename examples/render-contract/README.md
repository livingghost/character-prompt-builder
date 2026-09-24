# Explicit rendering and controls

This synthetic example resolves a flat illustration and a fictional diffusion interface.
Its numbers are test data, not recommended settings for a real provider.

```bash
python examples/render-contract/build_example.py --check
```

The command reads the model, intent, parameters, and prompt beside this file.
It resolves recommendations, prints a human-readable summary, verifies the contract,
and checks an exact synthetic wire request. It creates no image and makes no network call.
Use `--out PATH` to save a new contract; an existing file is never replaced.

See [Rendering choices and execution controls](../../references/runtime/render-contract.md)
for profile authorship, failure modes, and production use.
