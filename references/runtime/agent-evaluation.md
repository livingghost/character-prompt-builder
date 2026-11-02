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
| `prompt` | Studio-relative UTF-8 prompt file. |
| `inputs` | Explicit studio-relative files copied into the trial. |
| `expected_outputs` | Required relative file paths under the trial's output directory. An empty list is appropriate only for a case that requires no output files. |
| `criteria` | Authored review criteria retained for later judgment, not automatically graded by the runner. |

Define whether the case requests creation, critique or revision, and what result
would complete that request. A critique can conclude that its supplied draft is
sufficient; it need not produce a replacement file. Author independent, neutral
tasks across different purposes and subject domains. Keep the worked teaching
examples separate from the inputs used to measure agent behavior.

The trial uses the verified input copy as its prompt; a later edit to the original leaves the approved prompt as it was. Other input files and an optional skill copy are checked against the inspected plan before copying.

For a live interaction study, select a host that retains the actual turns and
provide them as execution evidence. A prior transcript authored into a task is
a supplied-context case, not a measurement of a live continuation. The runner
records the configured host; it does not supply a conversation controller.

For a trial of unprompted creative depth, cast admission or persistence, the prompt carries no reminder to add an origin, to consider the surroundings, to save, or to ask before naming a person. The author's answer to an admission request the agent raises correctly is a scripted response among the case inputs, not a correction. The worked example of [Cast Admission and Persona Depth](cast-and-persona-depth.md) lists cases of this kind.

### Host conditions

A condition describes an actual executable and how to invoke it. A host name in a label is a description; it says nothing about whether the host is installed or supported.

| Field | Meaning |
|---|---|
| `id` | Identifier for the condition. |
| `host_label` | Human-readable description of the selected host. |
| `model_label` | Declared model, or an explicit statement that a fixture is not a model. |
| `argv` | Executable and separate arguments. This is an array, not a shell command string. |
| `skill` | Studio-relative directory to copy, or `null` for no supplied skill. |
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

Run inspection from the installed skill directory. Replace `STUDIO`, the study path and the new output directory with your actual paths.

```sh
python scripts/agent_evaluation.py inspect --root STUDIO --study study.json --out evaluation/observed-run
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
python scripts/agent_evaluation.py run --root STUDIO --study study.json --out evaluation/observed-run --approve-plan EXACT_PLAN_CONTENT_SHA256
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

Judge the observed work against the current case's purpose and requirements.
Use [Observe and repair](production-direction.md#observe-and-repair) and the
[Creative Evaluation Rubric](../evaluation-rubric.md) to assess the answer the
case requested. Distinguish these aspects:

- triggering;
- procedural compliance;
- source understanding;
- selection of useful questions and sufficient evidence;
- expression;
- task completion.

Inspect what the agent establishes, preserves, investigates or changes and how
those actions contribute to the requested result. A correct small requirement
and an incidental variation can demand different amounts of work. Evaluate a
proposed repair by the issue it resolves, and a completed review by whether its
conclusion is supported. Look for the effect of whole-artifact understanding
on those choices. A sound explanation of the purpose followed by unrelated
local checking does not show that the understanding guided the work. Judge the
requirements the agent inferred against the actual brief, not merely against
its own acceptance conditions. File existence says nothing about meaningful
content, and host-reported completion is a claim rather than an independent
assessment.

For scene Persona work, include:

- cross-section dependencies;
- partner-specific exceptions;
- intentional unknowns;
- unchanged reuse;
- changes to unquoted originals;
- scope expansion;
- work without human characters.

Evaluate the total actual work and the resulting expression. Reading fewer
words, producing more findings or adding more detail earns nothing by itself.

### Prompt meaning

Give each fresh agent the task and its actual sources, including their declared
uses. Keep expected interpretations, assessor notes, repairs and teaching
answers out of that input. Judge the resulting prompt, critique or necessary
clarification against the brief. Use complementary cases; one case need not
exercise every dimension:

- A completed draft already communicates its purpose and satisfies its fixed
  requirements. Assess the review's conclusion and the value of any proposed
  further work. Include interacting instructions and several successful
  realizations, not only short or fully fixed drafts. For a study of compound
  construction, include a workable combination of orientation, connections,
  state, viewing conditions or information layout that a superficial check
  might reject. Assess the construction that supports acceptance.
- A candidate's conditions can coexist, but the review question concerns how
  its chosen organization, performance or emphasis serves a stated purpose.
  Assess the consequences the agent identifies and the support for its
  conclusion, including sufficiency when justified. Pair this with detailed
  work whose construction effectively serves its purpose, so simplification
  or compulsory criticism cannot substitute for judgment. Include reviews
  with an independent brief and reviews where intended purpose must be
  inferred from the candidate. Keep assessment, adoption and editing distinct.
- A fine distinction is incidental to one artifact but central to a different
  task. Assess the precision each purpose requires, including explicit small
  requirements that remain fixed in either setting.
- Feedback changes the question being reviewed or the scope of a requested
  revision. Assess whether the next action addresses that scope and retains
  requirements the author has not changed. An acknowledged correction followed
  by continued work on the same unsupported premise is not recovery. Include
  tasks completed without corrective feedback as well.
- Opposing properties belong to different subjects, regions or supported
  moments. The result should preserve their scopes and complete the depiction.
- Paraphrased requirements demand incompatible states of the same subject and
  region at the same moment. Fixed anchors need a decision; a conflicting draft
  choice should be repaired within the agent's authority. Include cases whose
  conflict emerges only when several individually plausible conditions share
  one arrangement, rather than only directly opposing property words. Require
  the assessor to follow the relevant dependency and the repair's consequences.
  Vary which source fixes a camera, layout, mechanism or precise visible detail,
  so a generic preference to change one kind of condition cannot pass.
- A reference supplies identity while its pose differs from the requested
  action. The source's unassigned state must not displace the target state.
- A source is available only during authoring. Assess how its assigned
  contribution reaches the delivered input, and whether observed properties
  remain distinct from inferred construction. Include actually delivered media
  with different declared roles in other cases.
- Some source evidence is unavailable for the requested assessment. Judge
  affirmative and negative claims by their actual support, and distinguish a
  limited conclusion from a defect or a required change to uninspected work.
- A crop, action or exclusion changes the intended event despite valid syntax.
  Assess fidelity to the event, not just the presence of its objects.
- A prompt satisfies every exclusion while omitting a wanted quality, degree,
  relationship or finish. Assess whether the revision establishes the target
  from the brief or supplied evidence rather than adding further prohibitions.
- A qualified exclusion limits an extreme of a wanted quality. Preserve that
  quality and its intended strength without inferring its opposite.
- An explicit exclusion leaves its alternatives open. Preserve the boundary
  without inventing an unnecessary positive choice or dropping the exclusion.
- Story knowledge, source provenance, native controls and assessment notes
  accompany a brief. Judge the resulting visible scene and the ownership of
  those inputs; a prompt must not become a copy of its preparation records.

Inspect the complete positive and negative text, media and native controls.
Test the actual transport when it changes scope or emphasis. For visual
observation, provide the actual image and inspect what the host perceived.
A stipulated description tests reasoning from that description, not image
perception. Record the actual input boundary and available evidence.

Distinguish what result the agent understood, whether the conditions can
coexist, how the proposed construction serves that result, and what an actual
output demonstrates. These are judgments to substantiate, not required report
headings. A fluent restatement does not establish joint feasibility; a possible
construction does not by itself establish effective expression. Nor does
finding a different attractive treatment establish a defect. Evaluate how the
agent prioritizes consequences, including exact small requirements, rather than
rewarding easily demonstrated discrepancies or a predetermined verdict. A
repaired prompt must preserve the fixed request and support the revised
construction; detecting a conflict alone does not demonstrate a successful
repair. Allow successful unfamiliar solutions, retained sufficient drafts and
appropriately bounded uncertainty.

Use the [worked construction cases](../../examples/production-execution/evidence-review-cases.md#8-a-working-transmission-and-a-conflicting-design-choice)
to understand these distinctions. The separate
[synthetic task set](../../examples/production-execution/compound-construction/README.md)
provides execution inputs and assessor notes in other domains. Give each task
without its assessor notes, and build fresh tasks when studying generalization
beyond these examples. Do not reuse a user's scene or a renamed version as a
test of generalization. Judge the observed responses themselves; adding cases
to documentation supplies no behavioral result.

Record reasons and outputs, then judge meaningful completion, useful repairs,
unnecessary work, refusals and loss of anchors separately. A schema-valid plan
or a satisfied review field does not demonstrate successful semantic reasoning.
Evaluate prompt quality and generated-image quality from their respective
artifacts. Teaching examples and deterministic fixtures establish neither a
real host's judgment nor the quality of an uninspected image.

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

[`reimplementation_smoke_test.py`](../../scripts/reimplementation_smoke_test.py) exercises scene-material reuse, authoring-only delivery, approved upscale dispatch and recording recovery without resubmission. These deterministic checks leave model quality and token use unmeasured.

## Execution resources

The approved condition owns its optional timeout and log budget; a default byte ceiling is absent, and logs are kept whole. `timeout_seconds: null` disables the application deadline; `max_log_bytes` may be omitted or set to null. See [Resource handling](../resource-handling.md) for budget failures, complete evidence retention and host-level containment.

## Evaluate craft reuse

Use [Craft consultation](craft-consultation.md) to connect consulted knowledge to the task. Evaluate the search scope, complete-source reading, and the fit of the borrowed relationship. Inspect actual outputs for preserved constraints, deliberate changes, and unrelated material introduced by adaptation. Treat an appropriate nonuse decision as valid. Measure useful reuse and avoided repeated work; lookup counts and record counts do not establish quality.
