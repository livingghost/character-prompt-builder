# Synthetic candidate recipe

The script records synthetic local bytes and reads their recipe through the public CLI.
It compares studio files before and after inspection. The candidate remains unaccepted.
The selected response seed and original request stay distinct in the [actual report](report.json).
The example performs local recording only. It measures evidence handling, not artwork quality.

Run from the skill root:

```text
python examples/candidate-recipe/build_example.py
python examples/candidate-recipe/build_example.py --check
```

Select an existing candidate explicitly:

```text
python scripts/studio.py recipe --studio STUDIO --character CHARACTER --slot SLOT --iteration ITERATION
```

Choose an exact iteration ID from the studio record. Subsequent execution uses current validation and its own authorization.
