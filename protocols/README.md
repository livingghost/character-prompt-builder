# Protocol Set

This directory holds one public protocol set: the schemas, templates and documents under `protocols/`, the semantic rules in `protocols/semantics.md` and the validator `scripts/protocol_contract.py`. `protocols/contract-manifest.json` lists every member with its SHA-256 and seals the set under `contract_set_sha256`. That digest is the set's identity. Two installations hold the same set when their digests are equal.

## Changing the set

1. Edit `protocols/` and `scripts/protocol_contract.py` in one installation.
2. Replicate both, byte for byte, to every installation that exchanges artifacts with it.
3. Run `python scripts/seal_contract.py` in each installation.
4. Confirm that every installation reports the same `contract_set_sha256`.

One changed byte in one member changes the digest. `python scripts/seal_contract.py --check` says whether sealing would move anything.

## Exchange

An interchange envelope carries the sender's `contract_set_sha256`. Receipt compares it with the receiving installation's sealed digest and refuses the envelope when they differ. The refusal names both digests. Replicate and seal again, then send again.
