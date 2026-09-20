# Moment-to-artifact example

Run from the directory containing `SKILL.md`:

```text
python examples/story-context/run_example.py --out EXAMPLE_DIRECTORY
python scripts/story_context_smoke_test.py
```

Choose a new output directory. The script authors synthetic state with two
concurrent activities, an unresolved commitment and different knowledge for two
entities. It queries order 15 between changes, selects one scoped depiction and
a persona period plus creator intent, then prepares, hands off, records, reviews,
selects and completes a handwritten output. The full command log is saved.

This is a test scenario, not a genre, cast or event template. `inputs/` contains
the same input records for direct inspection. Query fields for activities and
commitments are authored collection pointers, not required special fields. The
tests also cover a character-free world and unrelated record types.

Approval fields and review statements here are synthetic fixture data. No image
model is called and the example does not adopt a new canonical fact. See
[Story Context](../../references/runtime/story-context.md) for the task flow.
