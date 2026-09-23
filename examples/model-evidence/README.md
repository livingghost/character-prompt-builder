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
