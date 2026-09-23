# Saved evidence after an input change

This synthetic example prepares a local run and reserves one synthetic output.
It runs the real `resume` command before and after changing the delivery source.
The report retains the unused reservation and names the inputs that need attention.
The fixture uses local files and makes no service calls.

Run from the skill directory:

```bash
python examples/resume-recording/build_example.py
python examples/resume-recording/build_example.py --check
```

[The recorded summary](report.json) contains actual command results from this fixture.
The author controls execution and acceptance through the normal production permissions.
