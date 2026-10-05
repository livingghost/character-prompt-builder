# Interchange

Use this protocol to receive or deliver a selected public artifact. Check its type, identifiers, required features and content commitments, then apply the project's review and adoption rules for the requested purpose.

## Exact artifact exchange

`protocols/contract-manifest.json` lists every member of the installed contract with its SHA-256: each schema, each template, each protocol document, the semantic rules and the validator. `protocols/semantics.md` defines the meaning of the records and hashes.

In these commands, replace `PROJECT` with the project directory and choose the artifact and output paths for the task.

```text
python scripts/protocol_exchange.py check-installed
python scripts/protocol_exchange.py inspect --root PROJECT --artifact state.json
python scripts/protocol_exchange.py export --root PROJECT --artifact state.json --out outgoing
python scripts/protocol_exchange.py verify --root PROJECT --bundle incoming
```

An exchange directory contains exactly `artifact.json`, `contract.json` and `manifest.json`. `export` creates a new directory and leaves an existing output in place. `verify` checks the member set, byte hashes, schema closure, semantic rules, validator and artifact constraints; a bundle sealed by another validator is refused. An optional `--contract FILE` on inspect and export names the expected descriptor under `PROJECT`.

Artifact source paths are provenance. Obtain selected media and verify their hashes before using them; validating an artifact does not inspect its referenced media.

## Profile-aware exchange

`config/integration-capabilities.json` declares the installation's `produces` and `consumes` operations. Profiles name supported artifact types and required or optional features. A declaration's hash identifies its content, not an actor or permission.

```text
python scripts/validate_integration.py
python scripts/build_interchange_envelope.py --profile shot-request --payload PROJECT/request.json --payload-type shot-request --payload-id REQUEST-1 --out PROJECT/outgoing
python scripts/validate_integration.py --direction consumes --envelope PROJECT/incoming/envelope.json --declaration PROJECT/incoming/declaration.json --payload-root PROJECT/incoming
```

The profile bundle contains `artifact.json`, `declaration.json` and `envelope.json`. Its payload ID must match the actual artifact. The envelope binds its type, ID, exact bytes, declaration and features. Use `produces` to check an export and `consumes` to check a receipt, including when the declarations happen to be identical.

The envelope carries `contract_set_sha256`, the sender's sealed protocol set digest from `protocols/contract-manifest.json`. Receipt compares it with the receiving installation's sealed digest and refuses the envelope when they differ, naming both digests. [Protocol Set](../README.md) says how two installations reach the same digest.

An unknown required feature stops interpretation. Preserve unknown optional features without claiming to understand them. Existing output stays in place, and failed staging does not establish a completed delivery.

## Review and adoption

Retain provenance and effective range with an `external-contract-reference` when required. A valid artifact can still be a proposal. Content verification, media inspection, adoption and permission to generate are separate decisions. Exchange only the selected artifact and the records its contract requires.
