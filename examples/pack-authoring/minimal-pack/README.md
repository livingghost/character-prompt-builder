# Minimal Example Pack

This synthetic directory is an editable development pack. It is used once its directory is registered and its UUID from `pack.json` enabled; a new pack of your own starts with `python scripts/pack_cli.py init PATH --name NAME`, which does both.

```bash
python scripts/pack_cli.py root-add examples/pack-authoring/minimal-pack
python scripts/pack_cli.py enable PACK_ID
```

Build its lock only to publish it, then run the exact one-pack release gate in
[Release Validation](../../../references/release/validation.md) with an isolated
state, dedicated cache, and explicit managed root:

```bash
python scripts/pack_cli.py build-lock examples/pack-authoring/minimal-pack
```
