# Synthetic model evidence

This local exercise uses an invented schema source and a synthetic model record.
The example runs `scripts/observe_model_schema.py schema` through its public CLI.
It compares the published response bytes, selected schema, and unchanged source record.

```sh
python examples/model-evidence/build_example.py
python examples/model-evidence/build_example.py --check
```

The actual [report](report.json) records target identity and source preservation.
The temporary source, publication directory, and fixtures are removed after inspection.
No service is contacted and no production authority is consumed.
The schema source here is synthetic; the report makes no claim about a real provider.

## Scoped model choice and failure evidence

[selection-preferences.json](selection-preferences.json) is a synthetic author preference, not provider policy.
Its family selector applies only to one invented service and two explicitly named uses.
An ordinary depiction of a minor remains a separate use case from prohibited content.
A pack can bind this file as its `model-selection-preferences` resource.
[Render contract](../../references/runtime/render-contract.md#apply-the-authors-model-selection-preferences) defines policy ownership and the complete home override.
Inspect the current author's selected preferences:

```sh
python scripts/render_contract.py preferences
```

[failure-assessment.json](failure-assessment.json) binds [failure-response.json](failure-response.json) by its byte hash and exact response signal.
Check that local pair with:

```sh
python scripts/render_contract.py diagnose --root examples/model-evidence --failure failure-assessment.json
```

The result reports `category: provider-moderation`, `policy_relevance: explicit-provider-moderation` and `automatic_retry: false`.
The invented provider code only demonstrates the evidence format.
`scripts/test_model_suitability.py` covers scoped preference persistence, exact external identifiers, reference limits, changed evidence and distinct operational failures.
