# Protocol Exchange

Use public artifacts to deliver or receive state, morphology, reference, adoption and viewpoint records. The [contract registry](../protocols/contract-manifest.json) lists public types and schema dependencies; the [semantic rules](../protocols/semantics.md) define their interpretation and content hashes. The [schema path mapping](../config/protocol-layout.json) locates the definitions used by the validator.

## Inspect, export and verify

Replace `PROJECT` with the project directory and select the artifact paths for the task.

```text
python scripts/protocol_exchange.py check-installed
python scripts/protocol_exchange.py describe --type state-snapshot
python scripts/protocol_exchange.py inspect --root PROJECT --artifact state/snapshot.json
python scripts/protocol_exchange.py export --root PROJECT --artifact state/snapshot.json --out exchange/snapshot
python scripts/protocol_exchange.py verify --root PROJECT --bundle received/snapshot
```

`describe` identifies the complete schema dependency closure and semantic commitment. Optional `--contract FILE` on inspect/export specifies the expected descriptor. `export` creates `artifact.json`, `contract.json` and `manifest.json` in a new directory. `verify` checks that exact set, its byte hashes, the contract and artifact constraints. It does not inspect referenced media or approve canon.

Keep a received proposal proposed until the relevant review and adoption decision. Exchange only the selected artifacts and their required records, not entire persona dossiers or production histories.

## Bind state and shot evidence

[Shared State](../protocols/shared-state/README.md) resolves approved events at the requested scene and story point. Presentation order does not advance state. A scene context must agree with its snapshots in scene, timeline and time.

[Viewpoint](../protocols/viewpoint/README.md) separates camera ownership, knowledge scope, audition and visible projection. A `shot-request` names the applicable morphology, identity, state, scene, camera and projection. Character maps may be empty for a view without characters.

Use `scripts/shot_request.py` with every referenced artifact for complete verification:

```text
python scripts/shot_request.py request.json --require-complete --species-profile C01=species.json --individual-morphology C01=morphology.json --identity C01=identity.json --state C01=snapshot.json --scene-context context.json --camera-spec camera.json --shot-projection projection.json
```

Omit the character options for a character-free request. Without `--require-complete`, missing named artifacts are reported in `unverified_bindings`, with `complete: false`. Do not report this as fully verified lineage.

## Source references

A reference binding records its role, structured source, intended influence, unsupported assumptions and story range. A supplied-file source identifies bytes; a pack-artifact source also records catalogue provenance. `resolved_path` locates the source used to create the record. It is not opened by exchange validation. Obtain and inspect the selected media before using it, checking the recorded hash. Retain the received artifact and record any new binding separately.

## Profile envelopes

A profile declares artifact types and required or optional features. Receipt needs the envelope, its declaration and exact payload. Use `produces` to check an export or `consumes` to check a receipt; declaration hashes do not select the direction.

```text
python scripts/validate_integration.py
python scripts/build_interchange_envelope.py --profile shot-request --payload-type shot-request --payload PROJECT/request.json --payload-id REQUEST_ID --out PROJECT/exchange/request
python scripts/validate_integration.py --direction consumes --envelope PROJECT/received/request/envelope.json --declaration PROJECT/received/request/declaration.json --payload-root PROJECT/received/request
```

The profile bundle contains `artifact.json`, `declaration.json` and `envelope.json`. Check the payload ID, schema, exact bytes, declaration and feature support. Unknown required features prevent interpretation. Unknown optional features remain uninterpreted evidence.

## Checks and interrupted output

`scripts/protocol_contract.py` validates structural and intrinsic constraints. `scripts/temporal_state.py` resolves state changes; `viewpoint_protocol.py` validates cameras and continuity records. Run `scripts/protocol_contract_smoke_test.py` and `scripts/public_boundary_smoke_test.py` for their conformance cases. The [exchange example](../examples/protocol-exchange/README.md) demonstrates state resolution, export, receipt and complete shot binding with synthetic data.

Interrupted staging or a retained `.exchange-lock` is not completed delivery. Inspect the interrupted operation before clearing a reservation, and verify a complete bundle before using it. Recovery does not approve a proposal or determine whether a generation succeeded.
