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

### Keep the tested revision reproducible

Regenerate host guides, manifests and implementation indexes from their declared
source owners. After changing implementation, run `scripts/rebuild_metadata.py`
before checks or sample builders that enforce the installed module index.
An `IMPLEMENTATION_CHANGED` refusal identifies stale installation metadata; retain
that failed attempt and correct the source/index relationship before assessing
the behavior. Do not patch captured hashes or relax the refusal to make it pass.

Executable examples can retain exact routed documents and reading evidence.
When those inputs change, rebuild the affected canonical example with its own
builder, such as `examples/state-aware-pilot/build_example.py`, and regenerate
metadata again after its outputs change. Preserve user Studios and historical
trial artifacts separately from these product-owned synthetic examples.

Record the source inventory and hashes used for the focused checks, full required
gates and package. Verify the final archive against that source, including its
generated metadata, release identity and extracted contents. Reuse completed
checks for an unchanged snapshot; later edits are a new verification boundary.
Keep incomplete runs and their logs, and state whether a result is an executed
pass, a skipped environment-specific case, synthetic coverage or unverified
behavior. A successful package check does not replace the test suites, an agent
trial or a platform that was not exercised. Follow
[workflow trial records](agent-workflow-design.md#workflow-trial-records) for
operator effort, independent review and causal assessment of mistakes.

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
publication reuses an owned decision's successor and observes another writer's
commit before using an older caller's state.
`test_reference_read_model.py` preserves current selection, exact source bytes
and completed adoption evidence while sharing one decoded model per build.
Test-owned SQLite connections must close before their temporary directories
are removed; the connection transaction context alone does not close them.

`test_pack_read_model.py` checks input/build interleavings, source removal after
acquisition, same-size/same-mtime edits, disabled-pack isolation, one acquisition
per selected file and fixed-runtime inputs taken from the catalog's own input.
`test_schema_read_model.py` checks immutable schema ownership, root isolation,
lazy references, keyword coverage, diagnostic order and standalone validation.
Its dispatch checks reuse one owned schema while changing the supplied instance;
schema execution plans retain constraints, not earlier validation outcomes.
Alternative and condition predicates stop at a decisive mismatch. Ordinary
validation preserves all diagnostics in order, and oneOf reports the exact
number of matching alternatives. Shared sheet artwork is acquired once within
a complete sidecar check; a later check acquires its files again.
Run-view tests distinguish shared read-only state from editable exports and
verify compiled artifacts against the bytes that publication checking acquired.
Owned JSON tests preserve first duplicate-key diagnostics, nested immutability,
editable-copy aliases, explicit memo entries and scalar subclass copy behavior.
They count actual object opens across publication checking and evidence
interpretation, preserve streaming for objects beyond the retained byte
budget, and check same-size/same-mtime corruption at a new boundary.
Candidate display tests measure acquisition independently of complete status:
registered input and event evidence remain checked, while unrelated compiled
artifacts are acquired by the complete audit and mutation owners. Display
values cannot substitute for a complete run. New operations and forced reads
acquire current stored content. Successful transactions retain owned inputs;
rollback restores their predecessor and invalidates abandoned writer handles.
Tests count publication reads and complete history replays across save and
display stages, and detect external edits even with unchanged event count and
tail. Journal tests verify that newly written JSON is consumed from memory and
that a new recovery call reads its persisted state.
Reference tests exercise multiple identity/continuity sources together, owned
writes, transaction changes and fresh publication boundaries. Count operations
in these cases independently of uninstrumented wall-time measurements.

Construct a synthetic pack's complete records before its first catalog build.
Fixture configuration belongs to that construction; later source edits exercise
the actual catalog refresh. Shared input templates may supply immutable source
material, while each test owns its editable Studio and any custom preparation.
Live-pack and runtime-state changes use independent construction.

Sheet planning tests inspect the same geometry, coverage, prompts and drawing
instructions that image publication consumes. Keep actual rasterization,
fallback text, masks, panel composition and harvesting under image-level
checks. `test_sheet_drawing_scope.py` covers text bounds and image-operation
equivalence alongside `character_sheet_smoke_test.py`'s complete sheet workflow.

The full runner includes the subsystem suites below. Use their individual
commands for focused diagnosis and reuse completed full-run results for those suites.

The runner uses a temporary copy of the declared product files, including
source-owned CI and source-control settings when present. Independently authored
packs stay outside that copy. It starts the commands with `CPB_HOME` at one scratch configuration directory whose pack state enables the shipped packs alone:

- every `scripts/*_test.py` suite;
- every `scripts/test_*.py` unittest module, as `python -m unittest <module>` from `scripts/`;
- every `examples/*/*.py` script that offers `--check`, such as an example's `build_example.py --check`;
- the validators and the default pack audit.

`--only SUBSTRING` keeps the commands whose label or command contains SUBSTRING,
such as the suites of one subsystem. `--list` prints the commands without running
them. The automatic concurrency is the smaller of four and the available CPU
count. Availability comes from the process CPU count when supported, then
process affinity, then the reported CPU count. This cap limits contention
between independent suites; it is not a measured optimum or a memory budget.
`--jobs N` explicitly sets how many commands run at once, including values above
that cap. The runner supplies `CPB_CHECK_CHILD_WORKERS` to nested CLI-help
batches as `min(4, max(1, available CPUs // selected jobs))`. Each outer command
receives a share of the available CPU capacity for its batch. Direct invocation
of the documentation suite uses up to four available CPUs for those probes.
Each CLI-help key has one result owner for the command batch. Commands requesting
the same key share its completed result; different keys can run concurrently,
including different subcommands of one script.
Tests of concurrent product operations still exercise their declared concurrency.
For a focused diagnosis:

```bash
python scripts/run_checks.py --only render_contract
```

The runner first prints its worker selection, CPU counts, Python, platform and
default temporary directory. Fixtures using the system's default temporary
location create their work there; I/O costs also depend on its filesystem. It prints one
line per finished command, then the slowest ten and the log tail of each failure,
and exits 1 when any command failed. Illustrative output:

```
workers: 4 (automatic); available CPUs: 8 (os.sched_getaffinity); logical CPUs: 8
CLI-help workers per suite: 2
temporary files: <temporary directory>
runtime: CPython 3.12.14; <platform>
python: <project>/.venv/bin/python
[ 63/109]    58.5s  exit 0  python scripts/production_resume_smoke_test.py
...
slowest:
    199.8s  python scripts/production_workflow_smoke_test.py
    157.1s  cd scripts && python -m unittest test_production_execution
...
FAILED (exit 1): python scripts/release_management_smoke_test.py  log <out>/061.log
...
109 commands: 105 passed, 4 failed in 379.7s with 4 workers
elapsed phases: setup 0.100s; copy 0.800s; commands 378.000s; cleanup 0.800s
```

`summary.json` retains that execution `context`, the selected `jobs`, total
`seconds` and `timings_seconds` for `setup`, `copy`, `commands` and `cleanup`.
Total elapsed time starts with configuration and context setup and ends after
the temporary source copy is removed; final summary writing and printing follow
that measurement. The command phase includes pack runtime preparation and all
selected commands. Each command's own `seconds` measures its subprocess while
the selected workload is running, including time waiting for CPU or storage.
Compare timings with the same command selection, worker count and execution
environment; the slowest-command list alone does not identify a bottleneck.

A test that needs a configuration directory of its own takes it from `production_fixtures.scratch_home(folder)` or `scratch_home_dir(folder)`.

`python scripts/validate.py .` checks the structure and contracts of the tree.

For any core or pack publication, [Release Validation](../release/validation.md) is the sole exact authority for environments, commands, pack isolation, acceptance, package verification, and metadata ordering.

## Documentation checks

Release startup checks import the ordinary runtime in a fresh process.
Their `runtime_import.release_declaration_reads` report records any release
declarations opened during those imports. Runtime product identity and release
syntax belong to `package_identity`; explicit package checks acquire and
validate release declarations and dependency metadata.

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

For a dialogue study, give the requester role the ordinary situation and raw
material available to that person. Let it produce actual messages and choose
attachments. Keep an unchanged record of each message and when each source
became available to the author. A nonexpert role need not produce an inventory
of immutable features, dislikes or design criteria. Requiring such an inventory
can create constraints that the commissioned task never supplied. If a study
uses a stipulated persona or preservation requirements, declare those as study
conditions and limit its conclusions accordingly. Do not pass private notes or
the evaluator's interpretation through the relay as user requirements.

Distinguish discovering an unspoken preference through dialogue from rebuilding
a supplied reference. A hidden favorite cannot govern an initial response that
has not received it. For reconstruction, supply the source and actual change
scope; distinguish author-only inspection from generator conditioning. Evaluate
the whole source relationship after the declared changes, separately from the
requester role's satisfaction and from compliance with its explicit words.
Neither a satisfied simulated requester nor a matching feature list establishes
close reconstruction. When the role setup or available information changes,
retain it as a new condition. Compare Skill revisions on the same information
boundary before attributing a difference to the revision.

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
Use one ordinary author per runtime case. User-role agents and independent
evaluators are maintenance instruments; keep that setup out of the Skill's
production prerequisites. For a conception comparison, retain its actual
preselection descriptions, consulted sources and resulting judgment. Distinguish
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
Evaluate the requested input forms separately: tag output remains tags and
descriptive output remains prose. A reader understanding a sentence does not
establish that the selected image model can follow it. Separate prompt-form
compliance, evidence for the selected vocabulary, and actual target-model image
performance. Cross-engine illustrations and their scores belong to the engine
that produced them; an unavailable target has no generated-image success rate.
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
| Diagnostic code table, exit statuses and guidance links | [documentation_contract_smoke_test.py](../../scripts/documentation_contract_smoke_test.py) |
| Fixed runtime snapshot reuse and irreversible-boundary checks | [test_runtime_snapshot.py](../../scripts/test_runtime_snapshot.py) |
| Exact execution and handoff boundaries | [test_production_execution.py](../../scripts/test_production_execution.py), [test_production_boundaries.py](../../scripts/test_production_boundaries.py) |
| Current grants, execution ownership and result records | [execution_lifecycle_smoke_test.py](../../scripts/execution_lifecycle_smoke_test.py) |
| Input variants and explicit target changes | [test_production_variation.py](../../scripts/test_production_variation.py), [test_production_retarget.py](../../scripts/test_production_retarget.py) |
| Public commands, JSON files and standard input | [test_production_cli.py](../../scripts/test_production_cli.py), [test_production_file_input.py](../../scripts/test_production_file_input.py) |
| Candidate evaluation and canonical adoption | [test_production_review.py](../../scripts/test_production_review.py), [test_production_adoption.py](../../scripts/test_production_adoption.py) |
| One instruction across selection and canonical use, numbered grant choice, retained partial claims, imported provenance and historical retry | [test_production_curation.py](../../scripts/test_production_curation.py) |
| Current placement, historical acceptance and interrupted reassignment | [test_studio_placement.py](../../scripts/test_studio_placement.py), [test_production_acceptance.py](../../scripts/test_production_acceptance.py), [test_scene_slot_workflow.py](../../scripts/test_scene_slot_workflow.py) |
| Accepted scene edits, subject continuity and canonical withdrawal | [test_production_edit_inputs.py](../../scripts/test_production_edit_inputs.py), [visual_continuity_smoke_test.py](../../scripts/visual_continuity_smoke_test.py), [sheet_artifacts_smoke_test.py](../../scripts/sheet_artifacts_smoke_test.py) |
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

`runtime_read_footprint.py` counts the selected original document ranges, rather
than every byte in their containing files. It reports `selected_bytes`, full
`source_bytes`, complete-source versus section selection and static lexical
words. Model cards, pack resources, command metadata and host tokens are outside
that measurement; the route reader's `progress` includes its actual delivered
knowledge bodies. Compare new composition and each retained amendment separately.
For the current actual draft, use
`python scripts/runtime_read_footprint.py --root STUDIO --choices work/input/choices.json`.
The choices owner derives its stage, declaration and actual differences.

`test_amendment_reading_profiles.py` checks definition expansion, view and
reference scope, numeric controls versus finishing, retarget dependencies,
recording, complete union coverage and stage-independent retained knowledge.
`test_production_reading_scope.py` checks the actual editable and final-task
owners. `route_reading_smoke_test.py` checks content delivery, current section
reuse, fresh-context reading and exact model knowledge separately.

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
