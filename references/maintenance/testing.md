# Maintenance testing

Use this reference when changing the Skill's implementation, schemas, templates,
instructions or executable examples. It defines the shared check environment,
execution procedure and subsystem coverage. Use the sections that apply to the
changed behavior. Ordinary production follows its runtime procedures.

## Contents

- [Required checks](#required-checks)
- [Documentation checks](#documentation-checks)
- [Creative-direction evaluation](#creative-direction-evaluation)
- [Release identity checks](#release-identity-checks)
- [Public protocol conformance](#public-protocol-conformance)
- [Production execution checks](#production-execution-checks)
- [Model contract tests](#model-contract-tests)
- [Persona and narrative development changes](#persona-and-narrative-development-changes)
- [Prompt-only contract changes](#prompt-only-contract-changes)
- [World realization and portrayal-principle changes](#world-realization-and-portrayal-principle-changes)
- [Moment query checks](#moment-query-checks)
- [Rendering contracts](#rendering-contracts)

## Required checks

Use the locked environment described in [Dependencies](../../DEPENDENCIES.md#uv-project-environment).
From the skill directory, synchronize it with `uv sync --locked`.
Run the commands with that environment's Python, or prefix each Python invocation
with `uv run --locked`. For a Studio working directory, use the project's
`--project` selection and absolute script paths described in Dependencies.

`python scripts/run_checks.py` runs every test suite once, in parallel, the same way CI does.
For the complete maintenance check, run:

```bash
python scripts/check_dependencies.py --capability sheet --capability temporal-media
python scripts/run_checks.py
```

In a source checkout, check the changed files with `git diff --check`.

Read-boundary and concurrency changes also exercise
`python -m unittest test_production_read_model test_execution_replay test_reference_read_model` from
`scripts/`. These tests use product-owned synthetic data, concurrent SQLite
writers, rollback and corruption cases. Preserve the guarantees at a new
read boundary and before an external effect when reducing repeated I/O.
Test actual retained state and conflicts instead of requiring every writer
to acquire a particular global lock. A shared prepared test template is
immutable; each test owns a copied Studio and restores its mutable runtime
settings before use.

Studio publication checks in `iterative_workflow_smoke_test.py` exercise an
older supplied read model, overlapping processes, retried event receipts and
events arriving during cleanup. `test_production_read_model.py` verifies that
publication starts a fresh Production read boundary inside an older caller.
`test_reference_read_model.py` preserves current selection, exact source bytes
and completed adoption evidence while sharing one decoded model per build.
Test-owned SQLite connections must close before their temporary directories
are removed; the connection transaction context alone does not close them.

`test_pack_read_model.py` checks input/build interleavings, source removal after
acquisition, same-size/same-mtime edits, disabled-pack isolation, one acquisition
per selected file and snapshot capture from the catalog's own input.
`test_schema_read_model.py` checks immutable schema ownership, root isolation,
lazy references, keyword coverage, diagnostic order and standalone validation.
Run-view tests distinguish shared read-only state from editable exports and
verify compiled artifacts against the bytes that publication checking acquired.
Reference tests exercise multiple identity/continuity sources together, owned
writes, transaction changes and fresh publication boundaries. Count operations
in these cases independently of uninstrumented wall-time measurements.

The full runner includes the subsystem suites below. Use their individual
commands for focused diagnosis and reuse completed full-run results for those suites.

The runner uses a temporary copy of the declared product files, including
source-owned CI and source-control settings when present. Independently authored
packs stay outside that copy. It starts the commands with `CPB_HOME` at one scratch configuration directory whose pack state enables the shipped packs alone:

- every `scripts/*_test.py` suite;
- every `scripts/test_*.py` unittest module, as `python -m unittest <module>` from `scripts/`;
- every example's `build_example.py --check`;
- the validators and the default pack audit.

`--only SUBSTRING` keeps the commands whose label or command contains SUBSTRING, such as the suites of one subsystem. `--list` prints the commands without running them, and `--jobs N` sets how many run at once. For a focused diagnosis:

```bash
python scripts/run_checks.py --only render_contract
```

The runner prints one line per finished command, then the slowest ten and the log tail of each failure, and exits 1 when any command failed:

```
[ 63/109]    58.5s  exit 0  python scripts/production_resume_smoke_test.py
...
slowest:
    199.8s  python scripts/production_workflow_smoke_test.py
    157.1s  cd scripts && python -m unittest test_production_execution
...
FAILED (exit 1): python scripts/release_management_smoke_test.py  log <out>/061.log
...
109 commands: 105 passed, 4 failed in 379.7s with 8 workers
```

A test that needs a configuration directory of its own takes it from `production_fixtures.scratch_home(folder)` or `scratch_home_dir(folder)`.

`python scripts/validate.py .` checks the structure and contracts of the tree.

For any core or pack publication, [Release Validation](../release/validation.md) is the sole exact authority for environments, commands, pack isolation, acceptance, package verification, and metadata ordering.

## Documentation checks

Run `python scripts/readme_smoke_test.py` after changing user-facing examples. It executes the marked example commands in temporary directories and verifies outputs and source-change behavior; live-send examples are checked without contacting a service. Keep the surrounding explanations accurate as well: executable commands do not establish prose completeness or artistic quality.

After changing README.md, run the same README smoke suite and keep the executable
example blocks byte-identical unless the commands changed. The full runner
includes this suite.

## Creative-direction evaluation

Use [Agent workflow design](agent-workflow-design.md#evaluation) when changing
how the Skill selects or reviews a depiction. Automated validation checks
declared geometry and source contracts; it cannot establish that the picture
serves the commission. Exercise the updated Skill with independent agents that
receive only the Skill, a raw realistic request and the environment needed to use it.
Do not tell them which weakness is being investigated, which picture is expected,
or that they must demonstrate diversity. Retain the exact input and first response
before supplying feedback; keep incomplete attempts and failures as results.

Separate purpose-directed tasks from open creation. For claims about an initial
proposal from sparse input, supply only an ordinary topic or the user's actual
short request. Do not add a desired expression, hand action, mood, medium,
palette, spatial scale, focal relationship, camera or crop to make the expected
answer easier to reach. Even without shot terminology, those additions can steer
the picture. Choose the request set before observing answers, give each
first-proposal task a fresh context, and retain every result, including repeated
or unsuitable choices.
Do not treat purpose-directed success as evidence against a default in open
creation, or label an agent's own scene detail as user-supplied intent.

Also cover different stated purposes, a declared author style, a requested
whole-design view and a local edit with scene and framing already fixed. First
assess what each proposal actually develops and whether it retains the
commissioned content, subject roles and stated use. An incidental occurrence
of the requested character does not preserve a character commission. Assess
each first proposal as an entire picture: emotional register, visual language,
palette and light, mark and surface treatment, distance/crop, useful visible
information and scoped exclusions together. Compare recurring combinations of
these choices across the sample as well as their fit to each request. Preserve
declared style, adopted scenes and local edits; a coherent series can properly
repeat choices. A close view, whole figure, environmental view or repeated frame
can all be appropriate. Distinguish justified repetition from an unchosen
default. Do not use novelty quotas, mandatory or random rotation, prohibited
media or lists of prompt words as artistic acceptance tests.
Check instruction and template defaults separately so successful prose does
not hide a conflicting authoring surface. Use new contexts after corrections.
When the workflow includes a conception study, retain its actual preselection
descriptions, consulted source material and separate assessment. Distinguish
the alternatives constructed, the grounds of selection and their rendition in
the final proposal. A retrospective list of rejected ideas cannot establish
that comparison took place; different technique names cannot establish that
the alternatives tested a consequential visual choice.
Also exercise complete subject prompts with rendering left to the model.
Preparation and prompt/model retries must preserve those actual inputs without
requiring a medium, invented selection reason or fictitious finish span.
Verify preservation of explicit rendering constraints separately from that
unselected state.

Report the Skill revision, model, setup, exact requests, first responses,
observed fit and limitations of this sample separately from structural test
results. A model-unspecified proposal tests portable authoring only. A claim
about target-specific wording also needs that exact target's input evidence
and actual vocabulary work where required. Neither a rendering preset nor a
dictionary hit establishes learned effect. A prompt proposal is no evidence of generated-image quality or a
guarantee across all agents and briefs. State recurring art direction plainly,
including mood, expression patterns, visual language, palette/light, mark/surface
and framing.
Different subject names or scenes, a few suitable counterexamples or answers
prompted toward a target picture do not establish the absence of a habitual
art direction. Observed recurrence alone does not identify its cause; limit
causal claims to what comparable evidence supports, and cross-model claims to
the models actually exercised.
Keep run-specific transcripts outside runtime resources and future evaluation
contexts.

## Release identity checks

Use `python scripts/release_contract.py` and the `scripts/release_management_smoke_test.py`
suite to check changes to release metadata. The full runner includes that suite;
a focused diagnosis can run it directly. CI and release publication enforce the
same contract. Tagged publication also checks `--tag` against `v` plus the
canonical release. [Release Validation](../release/validation.md) owns publication
sequencing and acceptance.

## Public protocol conformance

Authoring, state, reference preparation, prompt composition, generation,
and adoption each keep their own source of authority. A deployment may perform
all of them within one workspace. No stage implies an external application.

The optional exchange interface is defined by public artifact types, schema
closures, explicit capability declarations and content-addressed payloads.
Use [Protocol Exchange](../protocol-exchange.md) to validate those data.
A received record is not an approval, an instruction to run a tool, or evidence
that referenced media has been obtained. Internal source trees, release schedules
and private project stores are not exchange inputs.

Run conformance checks before publication:

```bash
python scripts/protocol_exchange.py check-installed
python scripts/validate_integration.py
python scripts/public_boundary_smoke_test.py
python scripts/protocol_contract_smoke_test.py
```

A selected required feature must be supported. Optional fields are retained as
inert evidence only under the declared preservation policy. Correcting an invalid
artifact is explicit authoring work; validation never guesses its intended meaning.

## Production execution checks

The [synthetic generation example](../../examples/generation/README.md) is the executable production entry path.
[test_production_cli.py](../../scripts/test_production_cli.py) builds every scenario option and runs the commands each one prints.
The full runner above covers the public contracts through these developer checks; an ordinary production call reads none of them.

| Contract | Executable checks |
|---|---|
| Evidence, transactions and operation diagnostics | [test_production_foundation.py](../../scripts/test_production_foundation.py), [test_production_operations.py](../../scripts/test_production_operations.py) |
| Fixed runtime snapshot reuse and irreversible-boundary checks | [test_runtime_snapshot.py](../../scripts/test_runtime_snapshot.py) |
| Exact execution and handoff boundaries | [test_production_execution.py](../../scripts/test_production_execution.py), [test_production_boundaries.py](../../scripts/test_production_boundaries.py) |
| Current grants, execution ownership and result records | [execution_lifecycle_smoke_test.py](../../scripts/execution_lifecycle_smoke_test.py) |
| Input variants and explicit target changes | [test_production_variation.py](../../scripts/test_production_variation.py), [test_production_retarget.py](../../scripts/test_production_retarget.py) |
| Public commands, JSON files and standard input | [test_production_cli.py](../../scripts/test_production_cli.py), [test_production_file_input.py](../../scripts/test_production_file_input.py) |
| Candidate evaluation and canonical adoption | [test_production_review.py](../../scripts/test_production_review.py), [test_production_adoption.py](../../scripts/test_production_adoption.py) |
| Imported package attribution, adoption recovery and current reference evidence | [studio_smoke_test.py](../../scripts/studio_smoke_test.py), [feature_workflow_smoke_test.py](../../scripts/feature_workflow_smoke_test.py), [studio_reference_smoke_test.py](../../scripts/studio_reference_smoke_test.py) |
| Model trials and observed schemas | [test_model_observation.py](../../scripts/test_model_observation.py) |

Tests use labeled synthetic approvals and local transports, never real credentials.
A passing test is evidence of its checked contract, not a visual quality judgment or a release certification.

## Model contract tests

Organize executable tests by schema, rendering, reference and transport behavior.
Keep named model targets and their expected outcomes in shared fixture data.
Extend the data when adding a model instead of creating another model-specific test module.

`scripts/model_contract_smoke_test.py` owns shared model semantics using synthetic records.
`scripts/model_schema_numeric_test.py` owns numeric and conditional schema behavior.
`scripts/model_capability_smoke_test.py` applies `scripts/fixtures/model_capability_cases.json` to every bundled executable offering.
The case matrix supplies independent valid inputs, rejected inputs and expected outcomes; missing offering coverage fails the suite.
Derive expected limits from the recorded provider evidence when authoring cases, then keep assertions independent of the production definition being tested.

```bash
python scripts/run_checks.py --only model_capability
```

Use neutral synthetic prompts and local images. Test request construction without sending provider requests.
Validate independently authored packs through their own evaluation resources, following [Release Validation](../release/validation.md#pack-release-gate).

## Persona and narrative development changes

Keep the full persona form as the default for both initialization and later additions. Preserve
custom forms and explicit `--blank`; do not equate a syntactically filled form with adoption or
creative quality. Follow `references/runtime/narrative-development.md` for the creative handoff.
Run `python scripts/persona_workflow_smoke_test.py` and
`python scripts/narrative_authoring_smoke_test.py` after changes to this route. `scripts/run_checks.py`
runs both in CI.

Contextual voice and embodied-performance changes also require
`python scripts/character_performance_smoke_test.py
python scripts/authorial_intent_smoke_test.py`. This covers the advisory expression audit,
full-form propagation and route boundaries; it does not grade fictional distinctiveness. Preserve
source-language forms, adoption boundaries, current-state ownership and existing custom forms.

## Prompt-only contract changes

When modifying runtime instructions, preserve the complete requirements, reasoning aids and
procedures needed for the requested prompt work. Separate applicable uses through explicit routes
and conditional references whose full contents remain discoverable and readable. Moving detail
must preserve the conditions that activate it and the evidence needed to use it correctly.
Inspect the reading footprint together with actual task completion; a smaller footprint alone
does not establish an improvement. Run:

```bash
python scripts/runtime_read_footprint.py
python scripts/validate_prompt_semantics.py --self-test
python scripts/prompt_artifact_smoke_test.py
python scripts/prompt_plot_smoke_test.py
python scripts/narrative_contract_smoke_test.py
python scripts/scene_plot_contract_smoke_test.py
```

Do not make reference transport files mandatory when no reference is selected. Do not replace semantic camera or anatomy validation with prose alone.

## World realization and portrayal-principle changes

Run `python -B scripts/world_realization_smoke_test.py`, the example inspect/build/verify
workflow, and `python -B scripts/portrayal_principles.py validate` when changing the current
source/state/view coordination. Verify that new entrypoints remain reachable from `SKILL.md`.
These tests use freshly authored current records and assess no image quality. Keep source material,
author-facing state and consumer exports separate; do not add a second world/event authority.

## Moment query checks

When changing temporal resolution or moment-backed production, run
`python scripts/story_context_smoke_test.py`, `python scripts/world_realization_smoke_test.py`
and `python scripts/production_workflow_smoke_test.py`. The [Story Context example](../../examples/story-context/README.md)
exercises actual query commands and the prepare-to-complete path. Keep diagnostic
output, consumer selections and approval decisions distinct.

## Rendering contracts

Model-interface changes update execution profiles, schemas, request transport, fixtures, and documentation together.
Run `python scripts/render_contract_smoke_test.py` and `python examples/render-contract/build_example.py --check`.
Then run model, generation, request, dispatch, and repository checks in the synchronized environment.
Rendering presets are subject-neutral choices, not provider effectiveness claims.
