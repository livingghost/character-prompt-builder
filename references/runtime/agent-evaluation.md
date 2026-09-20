# Evidence from actual agent execution

The runner measures an explicitly selected host on authored task prompts. It launches the configured command, retains its output and records elapsed time. It simulates nothing and estimates nothing; an exit code is process status rather than artistic success.

Use the existing evaluation study and artifact review to judge the results. This runner supplies process evidence and `measurements.json`; the production ledger remains the single source of authority. Conditions may use this skill, no skill, or another explicitly configured host. A historical release is optional as a comparison condition.

## Define the task and comparison conditions

Save a JSON study with `purpose`, `repetitions`, `cases` and `conditions`. Repetitions must be positive. Each case and condition combination receives its own directory, so their identifiers must work as portable filename components.

### Task cases

A case describes what the host receives and which deliverables must be present when it stops.

| Field | Meaning |
|---|---|
| `id` | Identifier for this task case. |
| `prompt` | Project-relative UTF-8 prompt file. |
| `inputs` | Explicit project-relative files copied into the trial. |
| `expected_outputs` | Required relative file paths under the trial's output directory. An empty list is appropriate only for a case that requires no output files. |
| `criteria` | Authored review criteria retained for later judgment, not automatically graded by the runner. |

The trial uses the verified input copy as its prompt; a later edit to the original leaves the approved prompt as it was. Other input files and an optional skill copy are checked against the inspected plan before copying.

### Host conditions

A condition describes an actual executable and how to invoke it. A host name in a label is a description; it says nothing about whether the host is installed or supported.

| Field | Meaning |
|---|---|
| `id` | Identifier for the condition. |
| `host_label` | Human-readable description of the selected host. |
| `model_label` | Declared model, or an explicit statement that a fixture is not a model. |
| `argv` | Executable and separate arguments. This is an array, not a shell command string. |
| `skill` | Project-relative directory to copy, or `null` for no supplied skill. |
| `timeout_seconds` | Maximum permitted duration of the local command. |
| `metrics` | Optional selector for host-provided telemetry, otherwise `null`. |

The whole-argument placeholders are:

- `{prompt}`;
- `{prompt_file}`;
- `{workspace}`;
- `{inputs}`;
- `{outputs}`;
- `{skill}`.

Use only placeholders that the configured command actually supports. Prompt text is passed as data rather than inserted into shell source.

Keep credentials outside the study and command arguments. A host can have credentials and settings of its own; its payment authority and network permissions are the host's own configuration, outside the runner.

## Select telemetry without inventing it

Optional `metrics` contains `match_pointer`, `match_value` and `pointers`. The last matching JSON record on stdout is the selected telemetry record. `pointers` can map `total_tokens`, `tool_calls`, `triggered` and `completed` to fields in that record using JSON pointers.

A measurement that is absent, null, malformed, negative or incorrectly typed remains unknown: the runner records it as unknown instead of coercing a string or estimating a token count from text length. Token and tool counts must be nonnegative integers; trigger and completion observations must be Boolean values.

These are host-reported values rather than independently authenticated counters. The host's own claim of completion is recorded separately from process status, expected-output presence and subsequent quality review.

## Inspect before executing

Run inspection from the installed skill directory. Replace `PROJECT`, the study path and the new output directory with your actual paths.

```sh
python scripts/agent_evaluation.py inspect --root PROJECT --study study.json --out evaluation/observed-run
```

Inspection launches nothing. Review in the returned plan:

- the commands;
- the executable identity;
- the inputs;
- the skill files;
- the output location;
- the repetition count.

After explicitly approving that exact plan, run:

```sh
python scripts/agent_evaluation.py run --root PROJECT --study study.json --out evaluation/observed-run --approve-plan EXACT_PLAN_CONTENT_SHA256
```

Any change to the study, a declared input, the executable or the copied skill changes the plan, and the supplied hash must match the plan that will run. This confirmation approves the plan only; service charges still require their own separate production or payment authority.

## Inspect the retained files

Each case, condition and repetition receives its own workspace, with inputs, an optional skill copy and outputs kept apart. The run also retains:

- its prompt;
- its command;
- stdout and stderr;
- elapsed time;
- exit code;
- expected-output diagnostics.

`result.json` carries sealed `agent-evaluation-run` evidence. Actual output files and logs have content hashes. `measurements.json` supplies `values`, `basis` and `evidence_path` to the existing evaluator, which verifies the retained log and output commitments before consuming those measurements.

`results.json` summarizes the trials. It distinguishes:

- `execution_ok`: every command finished with the expected executable status, free of any timeout or log-limit failure;
- `evidence_complete`: required output files were retained, output collection reported zero issues, and logs are untruncated;
- `ok`: both of the above are true;
- `quality_verdict`: remains `not-reviewed` until a separate review is performed.

A command that exits with zero but omits a required deliverable therefore fails the study. An unavailable executable, a failed launch, a failed process or a timeout is recorded rather than silently retried. Log overflow is also a failure, even when the host exits before the polling loop observes it.

## Interpret the result

Judge each of these separately:

- triggering;
- procedural compliance;
- source understanding;
- expression;
- task completion.

File existence says nothing about meaningful content, and host-reported completion is a claim rather than an independent quality assessment.

For scene Persona work, include:

- cross-section dependencies;
- partner-specific exceptions;
- intentional unknowns;
- unchanged reuse;
- changes to unquoted originals;
- scope expansion;
- work without human characters.

Evaluate the total actual work and the resulting expression; a shorter entrance document earns nothing for its brevity alone.

## Operational limits

A fresh directory is a workspace rather than an operating-system security sandbox, so run trusted commands with approved arguments. They keep the executing user's permissions and environment, may reach the network and may use host credentials; the runner leaves remote spending unbounded.

The executable file and declared inputs are pinned; transitive libraries, remote services and host-global configuration stay outside those commitments. Prompts and logs remain in the evidence, so keep secrets out of them.

Input and log limits protect I/O only; they are neither semantic reading budgets nor permission to cut required definitions. Logs are kept whole. A log that exceeds the operator budget stops the run, is recorded as `operator_budget_exceeded`, and leaves that trial incomplete with its measurements unknown.

## Run the software regression tests

```sh
python scripts/agent_evaluation_smoke_test.py
```

These tests use a labeled Python fixture rather than a language model. They check:

- recording;
- missing-output refusal;
- the verified prompt copy;
- log overflow;
- timeouts;
- tampering;
- readable failure evidence.

They establish nothing about a real host's performance or about improvement in artistic quality.

## Production integration checks

[`reimplementation_smoke_test.py`](../../scripts/reimplementation_smoke_test.py) exercises scene-material reuse, authoring-only delivery, approved upscale dispatch and offline recording recovery. These deterministic checks leave model quality and token use unmeasured.

## Execution resources

The approved condition owns its optional timeout and log budget; a default byte ceiling is absent, and logs are kept whole. `timeout_seconds: null` disables the application deadline; `max_log_bytes` may be omitted or set to null. See [Resource handling](../resource-handling.md) for budget failures, complete evidence retention and host-level containment.
