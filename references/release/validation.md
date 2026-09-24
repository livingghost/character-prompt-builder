# Release Validation

Use this document only for publishing a core release or a pack release. Ordinary prompt and prompt-artifact runtime must leave it unloaded. Release validation is an exact-profile gate, not an artistic-quality claim.

## Contents

- [Core release environment](#core-release-environment)
- [Core validation sequence](#core-validation-sequence)
- [Documentation and skill gates](#documentation-and-skill-gates)
- [Pack release gate](#pack-release-gate)
- [Search and reference acceptance](#search-and-reference-acceptance)
- [Fresh-session integration gate](#fresh-session-integration-gate)
- [Publication and metadata](#publication-and-metadata)
- [First-use activation and bundled integrity](#first-use-activation-and-bundled-integrity)
- [Production execution verification](#production-execution-verification)
- [Executable README examples](#executable-readme-examples)

## Core release environment

Install and verify the exact Tested profile with the Python 3.12 that CI uses. Run this check with that Python; it creates the environment at `../cpb-tested` and installs the pins into it once you confirm:

```bash
python scripts/check_dependencies.py --tested --venv ../cpb-tested --install
```

Run every other check with that environment's Python. The Tested profile also requires ffprobe from FFmpeg, and the same command installs it through the system package manager.

Core and Visual profiles support development and task-specific runtime; only the Tested profile validates publication. Each of these blocks publication:

- missing pin
- import failure
- functional dependency failure
- real SVG render failure
- reference-runtime failure
- generation-commitment failure
- visual-evidence workflow failure

## Core validation sequence

Run the repository's complete validator and the focused suites affected by this design:

```bash
python scripts/check_dependencies.py --profile core
python scripts/catalog_cli_runtime_smoke_test.py
python scripts/search_discovery_smoke_test.py
python scripts/reference_runtime_smoke_test.py
python scripts/reference_runtime_cli_contract_test.py
python scripts/state_generation_smoke_test.py
python scripts/growth_resolution_smoke_test.py
python scripts/structure_neutrality_smoke_test.py
python scripts/dispatch_recovery_smoke_test.py
python examples/state-aware-pilot/build_example.py
python scripts/validate_state_protocol.py .
python scripts/validate_integration.py
python scripts/package_security_smoke_test.py
python scripts/generation_payload_smoke_test.py
python scripts/pack_smoke_test.py
python scripts/documentation_contract_smoke_test.py
python scripts/validate.py .
```

These regression-only entrypoints remain individually discoverable for targeted diagnosis; CI runs every one of them, and the complete validator and packager decide which run in a publication gate:

```bash
python scripts/dependency_check_smoke_test.py
python scripts/stdio_encoding_smoke_test.py
python scripts/catalog_html_smoke_test.py
python scripts/default_release_smoke_test.py --state-file config/default-pack-state.json --cache-dir <dedicated-cache-dir> --managed-root <existing-managed-dir>
python scripts/eval_runtime_smoke_test.py
python scripts/render_contract_smoke_test.py
python examples/render-contract/build_example.py --check
python scripts/model_contract_smoke_test.py
python scripts/nondefault_pack_isolation_smoke_test.py
python scripts/upscale_package_smoke_test.py
python scripts/character_sheet_smoke_test.py
python scripts/pack_release_identity_smoke_test.py
python scripts/bundled_pack_gate_smoke_test.py
python scripts/pack_release_gate_smoke_test.py
python scripts/release_contract.py
python scripts/release_management_smoke_test.py
python scripts/release_file_operations_smoke_test.py
python scripts/release_startup_smoke_test.py
python scripts/interchange_envelope_smoke_test.py
python scripts/state_pointer_smoke_test.py
python scripts/shot_request_smoke_test.py
python scripts/session_entry_smoke_test.py
python scripts/narrative_contract_smoke_test.py
python scripts/narrative_authoring_smoke_test.py
python scripts/persona_workflow_smoke_test.py
python scripts/character_performance_smoke_test.py
python scripts/authorial_intent_smoke_test.py
python scripts/world_realization_smoke_test.py
python scripts/portrayal_principles.py validate
python scripts/world_coherence_smoke_test.py
python scripts/scene_plot_contract_smoke_test.py
python scripts/refusal_coverage.py scripts/narrative.py scripts/narrative_contract_smoke_test.py scripts/narrative_authoring_smoke_test.py
python scripts/refusal_coverage.py scripts/scene_plot.py scripts/scene_plot_contract_smoke_test.py
python scripts/narrative_corpus.py --check
python scripts/seal_contract.py --check
python scripts/service_profile.py runware
python scripts/studio_smoke_test.py
python scripts/validate_studio.py <studio-dir>
python scripts/dispatch_smoke_test.py
python scripts/generation_geometry_smoke_test.py
python scripts/check_tag_prompt_smoke_test.py
python scripts/prompt_dialect_smoke_test.py
python scripts/batch_plan_smoke_test.py
```

In a Visual environment, also run:

```bash
python scripts/check_dependencies.py --profile visual
python scripts/visual_evidence_smoke_test.py
```

`scripts/package.py` repeats the exact dependency and visual gates against both staged and extracted release trees. Packaging keeps its full gates even after validation passed in the source tree.

## Documentation and skill gates

Require all of the following:

- `SKILL.md` frontmatter contains only `name` and `description`;
- `SKILL.md` is at most 500 lines and at most 5000 tokens estimated as characters divided by four, both enforced by `scripts/validate.py`;
- optional runtime, model, maintenance, and release documents are reachable through truthful conditional links in the graph rooted at `SKILL.md`, or through a route or feature `SKILL.md` names;
- prompt-artifacts stays independent of image-generation, state-aware, maintenance, and release documents;
- model adapter files contain only their named target family;
- the runtime document graph contains only current single-purpose authorities;
- all updated project content is English;
- project Markdown, JSON text, examples, and generated manifests are free of the Unicode em dash;
- schemas, CLI outputs, and flags expose only the current canonical contract, and each rule has one authority.

When the host environment provides the official skill-creator validator, run its `quick_validate.py` against the repository root. The validator is host-installed tooling rather than part of this repository; skip this step when it is absent.

## Pack release gate

After pack authoring, advance its release when content changed and build the lock:

```bash
python -B scripts/pack_cli.py build-lock <pack-dir>
```

Create an exact-pack state that registers only the positional pack directory, enables only that pack UUID, and selects that UUID for every and only its named logical-resource bindings. Use a dedicated empty cache and an existing dedicated managed root. Keep the report outside the pack:

```bash
python -B scripts/pack_release_gate.py <pack-dir> \
  --state-file <absolute-exact-pack-state.json> \
  --cache-dir <absolute-dedicated-cache-dir> \
  --managed-root <absolute-existing-managed-dir> \
  --report-out <absolute-report-path-outside-pack>
```

The gate validates the released structure, lock, exact derived catalog, and every suite in the pack-owned `release-evaluation-contract`. A pack that lacks evaluation resources needs no invented suite or placeholder contract. Focused and sparse retrieval assertions stay in the pack that owns the records they name.

Passing establishes declared preservation, structure, and known retrieval behavior, and says nothing about whether a recommendation is artistically strong.

Read [Blind Image Evaluation Protocol](../blind-image-evaluation-protocol.md) only when making a generated-image quality claim. Structural, retrieval, package, and SVG-fidelity results count for nothing as image-quality evidence.

## Search and reference acceptance

For search changes, require modifier-scope cases, ID-free retrieval, grouping, direction diversity, and preservation of explicit anchors. A four-query batch must load one active catalog once, preserve request order, isolate per-query diagnostics, and match sequential results.

For inspection changes, require the complete canonical record plus compact linked-asset IDs, and exclude any complete resource or resolved-path payload. Full artifact details remain exclusive to `asset-lookup`; summary mode returns only compact technical inventory.

For reference changes, require:

- prompt-artifact source/delivered hash equality
- model-transport derivation
- Surface and Lighting resolution
- state eligibility
- transactional publication
- exact companion boundaries
- verifier-only host forwarding

Report dependency prerequisites separately from contract assertions; a suite must not print a fully passed contract count while returning an undifferentiated environment failure.

## Fresh-session integration gate

Run the end-to-end integration script from a clean session, with known IDs and conversation history absent:

```bash
python scripts/fresh_session_runtime_smoke_test.py
```

The script requires a complete, independently managed content pack in the explicit pack runtime. It is deliberately excluded from the bundled-commons release gate, because that pack lies outside the bundled commons release. When that prerequisite is missing, report the integration prerequisite as unmet. None of these stands in for it:

- substituting preknown record IDs
- weakening the assertions
- treating a smaller bundled fixture as equivalent coverage

The retrieval brief is:

```text
muscular anthropomorphic black panther
```

The test uses:

- explicit pack state
- sparse recommendation
- batch identity and scene queries
- full selected-record inspection
- asset activation lookup for every record
- a scene `pose-camera` plan
- `structural-line-tone` and `subject-mask`
- prompt-artifacts materialization
- source/delivered SVG hash verification

Assert that gaze, expression, mouth state, perspiration, outfit, lighting, and any other scene-conditioned presentation belong to identity authority only inside its declared influence.

Assert nothing about subjective artistic score, and reach records through retrieval rather than preknown IDs. Report the complete prompt-path document and the consumed-CLI word measurement, treating the measurement as information rather than a fixed pass/fail ceiling and keeping every detail. Ensure four queries launch a single catalog process rather than four.

## Publication and metadata

Publication checks the installed source, local public contract, declared resources
and executable fixtures. External installation and coordinated release are outside
the gates. Optional exchange uses explicit declarations and exact public artifact
bytes. Reject unsupported required features, and retain optional evidence only under
its declared policy. Validation and receipt leave generation and canon changes
unauthorized.

```bash
python scripts/public_boundary_smoke_test.py
python scripts/protocol_contract_smoke_test.py
```

After the exact Tested environment passes the full sequence above:

1. Run `python scripts/rebuild_metadata.py` and confirm only intended metadata changes; generated inventories are rebuilt, never hand-edited.
2. Build with `python scripts/package.py`; the working tree is never zipped directly.
3. Verify the reports the packager writes beside the archive: the generated `<archive>.sha256` file, and in `archive-check.json` the `zip_crc_ok`, `deterministic_rebuild`, and `stage_extracted_tree_match` fields, together with `stage-extracted-tree-check.json` and `validation-read-only-check.json`.
4. If a content pack changed, advance its UTC CalVer, rebuild its lock, and run the exact one-pack gate with its own state, dedicated cache, explicit managed root, and report outside the pack.
5. If visual tooling changed, run the Visual development checks and then repeat the mandatory Tested gate.
6. Validate every non-bundled pack independently. The core allowlist contains only the bundled commons pack; a separately distributed pack stays outside the core archive unless explicitly included.

The packager rejects symbolic links at source, staging, tree-hash, and ZIP boundaries. Regenerate canonical metadata and manifests after file moves, then verify the staged and extracted trees contain exactly the declared release inventory and each routed document appears exactly once.

The release inventory applies only to the stage built by `scripts/package.py`.
It includes runtime files, installed validation suites and their fixtures, plus host plugin metadata needed to load the skill.
It excludes the development-only `tests/` bridge, `.github/`, `.gitattributes`, `.gitignore` and caches.

Source archives preserve the development tree, including tests, CI workflows and source-control settings.
Build them from the source tree, not from the release stage or `release.include`.
Release exclusions never authorize deleting source files.
Keep source archives and release archives separately named.

Commit release metadata only after code, documentation, tests, pack locks, and generated inventories agree. Canonical pack records and visual evidence stay unchanged when the goal is merely to make a core documentation or runtime test pass.

## First-use activation and bundled integrity

`config/pack-initialization.json` enables all discovered packs only while the selected state file is absent, and `ready` persists that result. Existing explicit state is preserved: deliberately disabled packs remain disabled, and selected resource providers remain selected. `config/default-pack-state.json` remains the minimal core-release catalog seed and leaves first-use activation of additional supplied packs unrestricted.

The actual bundled `packs/commons` directory with the commons UUID is core-managed. A `pack.lock.json` is absent there by design: core source inventory and `MANIFEST.json` commit it together with the project, and pack validation still checks its schema and files. `lock` and pack release-lock creation refuse that directory rather than recreating an unnecessary lock. The exemption is bound to that path rather than to a manifest flag, so a copy of commons and every other pack still need a lock to be released or installed. The release gate reports a live core inventory for commons in place of a lock. Every external pack's lock stays in place and at full strength.

## Production execution verification

For the artifact-bearing execution path, run:

- `python scripts/execution_routes.py validate`
- `python scripts/production_direction_smoke_test.py`
- `python scripts/production_workflow_smoke_test.py`
- `python scripts/production_resume_smoke_test.py`
- `python scripts/production_inputs_smoke_test.py`
- `python scripts/production_input_model_smoke_test.py`
- `python scripts/route_reading_smoke_test.py`
- `python scripts/visual_continuity_smoke_test.py`
- `python scripts/request_contract_smoke_test.py`
- `python scripts/request_validation_smoke_test.py`
- `python scripts/reservation_lifecycle_smoke_test.py`
- `python scripts/production_series_smoke_test.py`
- `python examples/input-assembly/build_example.py --check`
- `python scripts/studio_recipe_smoke_test.py`
- `python examples/resume-recording/build_example.py --check`
- `python examples/candidate-recipe/build_example.py --check`
- `python examples/production-execution/run_example.py --out <new-directory>`
- `python examples/production-execution/repair_example.py --out <new-directory>`

The production fixtures supply explicitly synthetic authority; they grant no spending permission and establish no artistic quality.

`scripts/execution_contract.py` owns integrity/I/O; `scripts/production_binding.py` connects the package builder, verifier and dispatcher. Run `python scripts/runtime_read_footprint.py` to measure actual manifest-selected reads.

The moment path is covered by `python scripts/story_context_smoke_test.py` and
`python examples/story-context/run_example.py --out EXAMPLE_DIRECTORY`. The latter
requires a new output directory and records each command and artifact.

## Executable README examples

Run `python scripts/readme_smoke_test.py` from the product root after changing
user-facing instructions. The [README smoke test](../../scripts/readme_smoke_test.py):

- executes the marked examples in fresh temporary directories;
- verifies their files and source-change behavior;
- checks local documentation links;
- checks live command signatures without contacting a provider.

CI and the repository validator run this same test. Passing examples leave prose
completeness, Persona understanding, expressive quality and the full tested
dependency environment uncertified.

Validate a completed reading record with `python scripts/route_reading.py RECORD --root PROJECT`.
The checker reports issuance and quotation integrity; the operator assesses its application to the current task.

## Model request workflow checks

The dispatcher preview, attributed evidence import, and candidate variation each have a dedicated regression entry point.
Run `scripts/production_variation_smoke_test.py`, `scripts/schema_observation_smoke_test.py`, `scripts/dispatch_preview_smoke_test.py`.
Their synthetic providers exercise request recording and recovery separately from image quality or author acceptance.

## Craft consultation

Run `scripts/craft_consultation_smoke_test.py` and the `examples/craft-consultation/build_example.py --check` CLI example. Check search scope, full records, explicit decisions, atomic application, and unassessed reviewer questions. Assess actual output quality separately.
