# Artifact reviews and evaluation evidence

## Purpose and boundary

Read this to export an inspectable production record or to assess actual completed attempts. Both are derived views of the existing production workflow rather than a second state ledger; model requests, repair authorization, candidate selection and canon adoption stay with the production authority operations. A file hash identifies bytes only; artistic success, consent and observations are separate matters.

Use the smallest requested operation: a prompt discussion needs neither a study nor a permanent project, while a persistent export needs an existing workspace outside the installed skill. Criteria belong to the user's task; genre, language, human subject, plot, cast size, medium duration and composition are all open. Constancy, ambiguity, silence, absence, recurrence and deliberate omission can be successful results.

## Export a production review

After capture or review, present every candidate and its observations when review is requested. Use:

```sh
python scripts/artifact_review.py --project WORK --run RUN_ID --out reviews/inspection
```

The command reads:

- the existing prepared task;
- pinned source bytes;
- the exact consumer (the downstream writer, actor or renderer);
- receipts;
- all captured candidates;
- all reviews;
- selections;
- completion state.

The output contains static `index.html`, `review.json`, content-addressed attachment files and a byte inventory. Original captured bytes are shown even when the workspace files have changed, and those changes are prominently marked stale. Corrupt saved objects stop the export, and uninspected or absent media stays absent rather than invented. Text previews are bounded, while downloadable bytes remain complete. HTML and SVG source files are inert text attachments, shown as text rather than executed.

An export is an immutable snapshot rather than a live dashboard; use a distinct output folder for another snapshot. Exports stay under the workspace `reviews/` directory, and the command rejects:

- a path that escapes the workspace;
- a symlink;
- an installed-skill destination;
- an existing export destination.

Build and publish use a project lock and a staged directory, and every production receipt stays as it was.

A review is a record rather than an authorization. Continue selection, repair or adoption through the existing production authority operations, with the exact inputs and operation scope; a choice shown on a report is information rather than new permission.

## Define an evidence study

A study connects actual production run receipts to task-specific criteria. Conditions are arbitrary declared execution configurations rather than required product versions, and an old/new comparison is optional. Cases distinguish `observed-use` from `constructed-case`, and the origin note must state provenance honestly: a generated fixture is a constructed case rather than an audience study or a model-quality measurement.

```json
{
  "purpose": "Assess whether these recorded attempts met their own task criteria.",
  "cases": [{
    "id": "case-a",
    "origin": "constructed-case",
    "origin_note": "An authored test; not an observed user production.",
    "inputs": ["brief.txt"],
    "criteria": [{"id": "authored-criterion", "dimension": "declared effect", "kind": "expressive", "text": "Exact criterion text from the production task."}]
  }],
  "conditions": [{"id": "condition-a", "description": "Describe the actual tools, controls, and constraints."}],
  "trials": [{"id": "attempt-a", "case": "case-a", "condition": "condition-a", "run": null, "candidate": null, "measurements": null}]
}
```

The null run above is explicitly **not executed**. For a real attempt, set `run` to its production run ID and `candidate` to the exact captured candidate receipt hash. Each run appears at most once, because multiple outputs from one run are one attempt rather than independent repeated attempts. The full production review still shows every candidate, and the summary reports total captured candidates so the explicitly selected study sample is visible. A run with zero captured outputs uses a null candidate; a run with outputs must name one rather than silently choosing the best.

Input paths must match the actual prepared project's pinned dependency bytes. Criterion IDs and text must exactly match the run's task; a matching ID with altered meaning is rejected. Dimensions are authored free text. Kinds distinguish `technical`, `behavioral`, and `expressive` evidence; expression and reader/viewer response are judged on their own, beyond any technical check.

```sh
python scripts/evaluation_evidence.py --project WORK --study study.json --out evaluations/evidence
```

The export preserves:

- the study;
- source bytes;
- chosen output bytes;
- consumer details;
- review reasons;
- stale dependencies;
- condition descriptions;
- trial states;
- descriptive aggregate statistics.

`pass`, `fail`, `not-assessed`, `not-applicable`, and `missing` are distinct; a not-run attempt or an unreviewed output keeps its own state rather than becoming a failure or a zero-duration success. Each condition and case origin is reported separately, with assessment coverage and counts of not-run/no-candidate/not-reviewed/reviewed attempts. Keep constructed tests and real use in separate pools, and treat descriptive counts as description rather than causality.

## Optional measured execution data

`measurements` may name a project-relative JSON file, or be null:

```json
{"values":{"elapsed_seconds":null,"total_tokens":null,"tool_calls":null},"basis":"Explain the actual measurement method.","evidence_path":"execution.log"}
```

The record and source log bytes are preserved. Counts must be nonnegative integers; elapsed time must be finite and nonnegative. Missing values stay null; character-to-token conversions, invented timings and missing-data zeros are all disallowed. A single sample has no sample standard deviation. These remain operator-reported measurements supported by recorded bytes rather than independently verified telemetry.

## Concealed-condition review cards

```sh
python scripts/evaluation_evidence.py --project WORK --study study.json --out evaluations/cards --blind
```

This exports shuffled generic sample labels, criteria and outputs, and leaves out condition names and operator summaries. Keep the separate mapping under `evaluation-keys/` away from reviewers. The same authored criteria appear on each corresponding card. Blinding is the operator's judgment: inspect outputs and embedded metadata for identifying clues before calling the study blinded, because the tool leaves metadata and evidence untouched and generic labels alone leave blinding unproven. Export the evidence summary separately for the operator.

## Failure and interpretation

These stop the operation before publication:

- invalid paths;
- mismatched inputs/criteria;
- unknown candidates;
- corrupt saved bytes;
- repeated run sampling.

A current-source change is reported in reviews; an evidence study that claims the changed input is the original case is rejected. An artifact may be technically valid yet expressively unsuccessful, so the agent must inspect actual media to record a judgment; an automated aggregate falls short of an inspection.

Run `python scripts/evidence_tools_smoke_test.py` for constructed integration tests. A pass demonstrates evidence handling rather than improved generated-image, video or writing quality.

## Observed trials and repair hypotheses

[Agent Evaluation](agent-evaluation.md) runs only an explicitly confirmed host
command and records process output, exact input/artifact hashes and provided
metrics; a missing token count stays unknown rather than estimated. Feed
verified trials to the existing evaluation evidence command, and compare host
behavior and actual products separately. [Repair Analysis](repair-analysis.md)
reads existing run reviews, groups like criteria and records alternative cause
hypotheses, proposed changes, protected requirements and acceptance checks; it
executes nothing and keeps the production ledger as the only canonical one.
