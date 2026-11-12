# Saved evidence after an input change

This synthetic example prepares a local authored run, records an explicit
synthetic authorization, and reads the real `resume` result before and after
changing its delivery source. Neither preparation nor authorization reserves a
generation request. The example checks that no reservation was created.

The saved input and recorded history stay intact. After the delivery source is
edited, `freshness_notices` reports `SOURCE_CHANGED` with warning severity,
`freshness_diagnostic_codes` stays empty, and readiness and the next action stay
the same. The selected run continues with its saved input. Prepare a new run when
the edited delivery is the intended input. Execution still uses the operation's
current authorization. The example also compares the exact saved prepared data,
consumer and event history before and after the edit. It uses local files and
makes no service calls.

Run from the skill directory:

```bash
python examples/resume-recording/build_example.py
python examples/resume-recording/build_example.py --check
```

[The recorded summary](report.json) contains actual deterministic command results
from this fixture, not reconstructed or invented execution events.
