# Saved evidence after an input change

This synthetic example prepares a local authored run, records an explicit
synthetic authorization, and reads the real `resume` result before and after
changing its delivery source. Neither preparation nor authorization reserves a
generation request. The example checks that no reservation was created.

Saved history stays intact and readable. The changed source is independently
reported through `freshness_codes` and blocked execution readiness; a successful
status read is not permission to execute stale inputs. Inspect the changed source
before preparing its intended replacement. The fixture uses local files and
makes no service calls.

Run from the skill directory:

```bash
python examples/resume-recording/build_example.py
python examples/resume-recording/build_example.py --check
```

[The recorded summary](report.json) contains actual deterministic command results
from this fixture, not reconstructed or invented execution events.
