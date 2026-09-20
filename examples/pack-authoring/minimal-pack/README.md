# Minimal Example Pack

This directory is an editable development pack. Validate it and generate its release inventory with:

```bash
python scripts/pack_cli.py validate examples/pack-authoring/minimal-pack
python scripts/pack_cli.py build-lock examples/pack-authoring/minimal-pack
python scripts/pack_cli.py validate examples/pack-authoring/minimal-pack --released
```

Before publishing it, run the exact one-pack release gate documented in
[Release Validation](../../../references/release/validation.md) with an isolated state,
dedicated cache, and explicit managed root. The gate performs structural and
catalog checks even when a pack has no evaluation resources.

The example remains outside the active catalog until it is installed or its parent directory is supplied as a pack root and the pack is explicitly enabled.
