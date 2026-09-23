# Repeated-failure analysis from existing reviews

Use recorded evidence to improve an unsuccessful result, so that each retry builds on the last instead of starting a new guess. Begin with the original request, the protected source definitions and the latest review of each actual candidate. A prompt alone is no evidence of a failed output, and an attempt count is no evidence of its cause.

## Select the runs to analyze

Run the command from the installed skill directory and use a new project-relative output directory:

```sh
python scripts/repair_analysis.py --root PROJECT --run RUN_ID --run ANOTHER_RUN_ID --out analysis/observed-failures
```

The tool reads existing production evidence and groups failed checks by the actual criterion definition, since a local criterion ID is something another task might reuse. Multiple candidates from one run remain one run rather than independent trials.

## Read the evidence before proposing a cause

`analysis.json` and `analysis.md` are derived views; the original production ledger remains authoritative. The Markdown is meant to be read in full rather than used only as an index into the JSON.

For each source run, the report shows:

- the input commitment;
- the review receipt head;
- current/stale status;
- changed dependencies.

For each failure group, it shows the complete criterion and distinct run and candidate counts.

Each occurrence retains its run, candidate, review receipt, local criterion ID and reviewer reason. The cited observations are printed with their actual structured locations, such as a text range, image region or media interval. The report prints only recorded observations.

Three things stay distinct:

- the observation, which is what was inspected;
- the reviewer reason, which interprets that observation;
- a cause hypothesis, which is a further proposal that still needs testing.

## Author a repair hypothesis

After reading the evidence, an agent or reviewer can prepare a `hypotheses.json` object with a `hypotheses` array. Each item contains the following fields.

| Field | Purpose |
|---|---|
| `hypothesis_id` | Identifies this proposal. |
| `group_ids` | Links it to actual failure groups in the selected runs. |
| `explanation` | States the proposed cause without presenting it as established fact. |
| `alternatives` | Keeps competing explanations visible. |
| `proposed_change` | Describes the specific change to test. |
| `protected_requirements` | States what the repair must preserve. |
| `acceptance_check` | Describes the observation that would establish the intended improvement. |
| `scope` | Limits the proposal to the relevant work or conditions. |

To retain those proposals with the evidence:

```sh
python scripts/repair_analysis.py --root PROJECT --run RUN_ID --out analysis/proposed-repair --hypotheses hypotheses.json
```

Every hypothesis must cite a real failure group, and its status remains `hypothesis-not-established`. The readable report keeps evidence groups, explanation, alternatives, proposed change, protected requirements, acceptance check and scope as separate sections, so each survives a compressed summary.

An empty alternative list leaves the existence of alternatives open, and an empty protected-requirement list leaves the original task's requirements in force.

## Apply an accepted repair through the production workflow

Carry an accepted scoped proposal into the existing production repair procedure, whose authorization, input invalidation, review and selection rules still apply. This analysis submits no further request, adopts no generated reference, mutates no canon and rewrites no Persona.

When the proposed change expands a scene's participants, knowledge, topic, purpose or other prepared conditions, reopen its Persona preparation: an omitted definition still exists.

## Limits of repeated-failure analysis

A repeated failure proves nothing about whether the scene is too complex, whether a Persona rule should be removed or whether a different model must be purchased. None of the following exists:

- an automatic retry threshold;
- a genre taxonomy;
- a face-only rule;
- compulsory simplification;
- permanent negative-prompt learning.

The report analyzes the latest review per candidate; earlier review receipts remain in the original run, untouched by the summary. Inspect them when the history of changing judgments matters.

## Consult reusable corrections

Use the returned consultation action to investigate a craft question drawn from the recorded failure. Read [Craft consultation](preset-consultation.md) for complete sources, scoped application, and reviewer questions. Preserve the observed evidence and protected requirements when choosing a correction.
