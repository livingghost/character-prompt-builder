# Synthetic craft consultation

This local example runs the public consultation and application commands.
The authored synthetic choices are written in `build_example.py`, rather than inferred from search rank.
The report records actual command results, not model-image quality or user approval.

From the skill root:

```sh
python examples/craft-consultation/build_example.py
python examples/craft-consultation/build_example.py --check
```

Use `--workspace` with a new external path to retain the original task, consultation, authored decisions, and applied task.
`report.json` records the complete-source check and the reviewer question carried to its declared criterion.
The output has `execution_ready: false`, `external_effect: false`, and `budget_effect: none`.
The real candidate still needs normal preparation, scoped authority, generation or capture, and review.

Read the skill's craft consultation reference for field definitions and handling of stale inputs or existing directories.
