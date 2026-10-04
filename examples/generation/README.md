# Complete synthetic generation task

This example has a synthetic pack, model, recorded lookup, full task, approved fixture plot, criteria and authority.
Its transport creates a small PNG locally. It makes no network request and demonstrates no AI image quality.
Its approval belongs only to the fixture and never authorizes a real service.

From the Skill installation:

```sh
python examples/generation/build_example.py --out /absolute/path/to/synthetic-case
```

The command prints a `prepare_argv` array and saves it as `prepare-argv.json` in the new directory.
Pass that array to Python's `subprocess.run` without a shell, or run the same displayed arguments directly.
`--task task.json` is relative to the explicit studio root, not the current directory.

The studio contains these authored inputs, none of them an incomplete template:

- the task, with one applied source and a material decision that compares two options with their tradeoffs;
- the specification, plot, prompt, parameters and creative intent;
- the route reading, retrieval record and synthetic validation contract;
- the synthetic grant file and its basis.

## Check, prepare and inspect

`check` runs every check of `prepare` and creates no run. Replace `prepare` by `check` in `prepare-argv.json` to run it.
Its report lists each check with its state, every diagnostic, the request preview and the execution plan, with `run` null.

`prepare` publishes the same compiled result as a run. A real trimmed output of the synthetic case:

```json
{
  "ok": true,
  "run": "01a102d2-aa6a-745d-8aa6-ccd0cfeaa210",
  "input_sha256": "e09f3ac62dfc4b272928899db31579f2a2ebb3b13bb4b340a92ab8987289c057",
  "request_preview": {"operation": "generate", "model": "synthetic:robot",
    "prompt": "A flat graphic portrait of a simple synthetic robot standing against a plain background.",
    "width": 32, "height": 32, "steps": 20, "count": 1},
  "execution_plan": {
    "quantities": {"uses": 1, "outputs": 1},
    "cost": {"currency": "USD", "amount": "0", "basis": "Aggregate ceiling for the explicitly listed external effects: send: ..."},
    "readiness": {"state": "authorization_required", "executable": false, "diagnostics": [{"code": "AUTHORIZATION_REQUIRED", "severity": "warning", "phase": "readiness"}]},
    "mutable_fields": {"parameter:steps": {"schema": {"type": "integer", "minimum": 1}, "required": false,
      "value_form": "inline", "checks": ["execution-profile", "execution-controls", "request-compilation"],
      "rebuild": ["package", "request"], "protected_criteria": "recheck"}}}
}
```

Inspect the run and the automatic operation logs with:

```sh
python scripts/production_workflow.py status --root /absolute/path/to/synthetic-case/studio --budget
python scripts/production_workflow.py logs --root /absolute/path/to/synthetic-case/studio
python scripts/production_workflow.py logs-export --root /absolute/path/to/synthetic-case/studio --out exported-logs
```

`--out` names a new directory relative to `--root`; an existing one is refused.

## Variant and repeat

A parameter variant uses a JSON file matching `schemas/authoring/production-changes.schema.json`:

```json
{
  "changes": {"parameter:steps": 22},
  "reason": "Compare one declared parameter under the same synthetic fixed inputs."
}
```

```sh
python scripts/production_workflow.py variant --root STUDIO --from RUN --changes-file changes.json --prepare
python scripts/production_workflow.py repeat --root STUDIO --from RUN --prepare
```

Each produces a distinct run. Neither copies an authorization, dispatch claim, review or selection.
The new run keeps its derived task and replaced inputs in its own `inputs` directory.
`repeat` retains the input and semantic request digests.
The exact final request still needs an actual assessment and authorization before execution.
Use `draft-execution` to write its unanswered decision file.

A changed prompt or reference is checked again with retrieval, render intent, transport and recording.
Supply an explicitly reassessed `retrieval-record` when a changed prompt no longer matches that record.

## Scenario options

Each option below prepares one situation in a new studio and prints its commands as `scenario.next`.
Decisions, reviews and releases that a scenario records are made by the labeled synthetic fixture operator.
`scripts/test_production_cli.py` runs every option and its commands.

| Option | What the printed commands show |
|---|---|
| `--include-prompt-change` | `variant` changes the prompt and supplies the reassessed retrieval record. |
| `--include-reference` | `variant` adds a prepared reference set and the `reference-guided` mode to a run without references. |
| `--include-sheet` | `execute` records the output into the character sheet slot `canon.primary`. |
| `--include-scope-shortage` | `status` names the missing grant target, and `execute` exits 3 before any reservation. |
| `--include-budget-change` | `authority-import` replaces the grant with a larger cost limit, and `status --budget` shows it. |
| `--include-outcome-unknown` | `resume` asks for the lost answer without sending again, then `draft-outcome` writes the statement form. |
| `--include-partial-review` | `disposition` rejects a candidate on one failed criterion; the other criterion stays unassessed. |
| `--include-release` | `status --budget` shows the reservation, and `draft-release` and `release-reservation` release it. |
| `--include-log-export` | `prepare`, `logs` and `logs-export --without-streams` record, list and export the operation logs. |

The release request needs its actor, reason and evidence filled in before `release-reservation`.

## Explicit target comparison

Create a new fixture studio with both synthetic targets:

```text
python examples/generation/build_example.py --out TARGET_EXAMPLE --include-retarget
```

Follow `prepare-argv.json` for the original task and retain its returned run ID.
The builder also writes `studio/retarget/task.json`. It preserves the same
creative sources and work identity, but selects `cpb-synthetic-alternate`, its
own validation evidence and newly recorded retrieval/reading applications. The
alternative execution profile permits steps 10 through 24; the fixture explicitly chooses
22. These are synthetic test constraints, not advice for a real image model.

```text
python scripts/production_workflow.py retarget --root TARGET_EXAMPLE/studio --from ORIGINAL_RUN --task retarget/task.json --reason "Compare the explicitly selected synthetic target." --prepare --state-file TARGET_EXAMPLE/runtime/state.json --cache-dir TARGET_EXAMPLE/runtime/cache --managed-root TARGET_EXAMPLE/runtime/managed --pack-root TARGET_EXAMPLE/runtime/packs/example
```

Use absolute installation and studio paths from another current directory.
This prepares a new request without sending it. A request for the alternative
target requires its own actual execution authority. The sample decisions remain
synthetic and authorize no real provider. `test_production_retarget.py` exercises
this CLI, missing evidence, the new execution profile, source reading and parent-receipt
isolation with no network generation.


## Local upscale and recovery

Use `--include-upscale` when constructing the example. `studio/upscale/task.json` contains an explicit input declaration for a synthetic 32 by 32 PNG enlarged by a factor of two. Prepare it with the same runtime arguments as the generation example, then inspect the request and execute using the common decision file procedure. The source and output are protocol fixtures, not generated artwork. The synthetic upload and send make no network request.

```sh
python examples/generation/build_example.py --out EXAMPLE --include-upscale
python scripts/production_workflow.py prepare --root EXAMPLE/studio --task upscale/task.json --state-file EXAMPLE/runtime/state.json --cache-dir EXAMPLE/runtime/cache --managed-root EXAMPLE/runtime/managed --pack-root EXAMPLE/runtime/packs/example
python scripts/production_workflow.py resume --root EXAMPLE/studio --run RUN_ID
```

`resume` uses a saved answer to restore missing output registration without another upload or send. A source removed after submission does not erase the saved answer, input image or resulting candidate. New execution still checks current sources, authority and pack selection.
