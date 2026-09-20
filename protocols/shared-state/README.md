# Shared State Protocol

This public contract describes authored identity, morphology, state, reference
selection and adoption. It creates neither a shared application nor a new owner
of either project's data. A project may fill every required role on its own.

The [registry](../contract-manifest.json) and [semantic contract](../semantics.md)
are normative. Their SHA-256 commitments, not product names or guessed format
numbers, identify the installed contract. All schema reference dependencies ship
locally, and [protocol exchange](../../references/protocol-exchange.md) verifies
selected artifacts using only its installed public contract.

## Boundaries

- A species profile states only declared lineage possibilities; an individual
  morphology contract fixes one authored realization. A visual identity contract
  connects them and may name a visual authority. No anatomy is inferred from a name.
- State events and processes own approved temporal changes. Snapshots and scene
  projections are derived. A snapshot edit does not alter canon.
- World and character snapshots name a scene and timeline explicitly. Character
  snapshots selected into a scene must match its actual world state and time.
- Expiry is on individual changes. A temporary-until-cleared change needs an
  explicit exclusive expiry or an actual approved clearing event. Scene-local
  changes are applied only to their named scene. Processes carry interruption policy.
- A reference source, its transported rendition, a selected reference, a generated
  candidate and an adoption decision are different records. Returned media is not
  automatically canon. Routing hints identify responsible roles, not applications.
- Canonical content hashing excludes only the registered self-hash field. Hashless
  artifacts, such as identity and event records, are committed by external references.
  All-zero template hashes are not valid exchange commitments.

## Commands

```bash
python scripts/protocol_exchange.py check-installed
python scripts/state_protocol.py validate artifact.json
python scripts/state_protocol.py resolve-world --help
python scripts/state_protocol.py extract-character --help
python scripts/state_protocol.py build-context --help
python scripts/state_protocol.py build-projection --help
python scripts/state_protocol.py select-references --help
```

Validation checks structural and temporal rules. Review the evidence and record
approval and adoption for the intended use separately.
