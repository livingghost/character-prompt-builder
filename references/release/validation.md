# Release Validation

Use this document only for publishing a core release or a pack release. Ordinary prompt and prompt-artifact runtime must leave it unloaded. Release validation is an exact-profile gate, not an artistic-quality claim.

## Contents

- [Core release environment](#core-release-environment)
- [Where each check runs](#where-each-check-runs)
- [Documentation and skill gates](#documentation-and-skill-gates)
- [Pack release gate](#pack-release-gate)
- [Search and reference acceptance](#search-and-reference-acceptance)
- [Fresh-session integration gate](#fresh-session-integration-gate)
- [Publication and metadata](#publication-and-metadata)
- [Release reports](#release-reports)
- [First-use activation and bundled integrity](#first-use-activation-and-bundled-integrity)
- [Production execution verification](#production-execution-verification)
- [Executable README examples](#executable-readme-examples)

## Core release environment

Install and verify the exact Tested profile with the Python 3.12 that CI uses. Run this check with that Python; it creates the environment at `../cpb-tested` and installs the pins into it once you confirm:

```bash
python scripts/check_dependencies.py --tested --venv ../cpb-tested --install
```

Run every other check with that environment's Python. The Tested profile also requires ffprobe from FFmpeg, and the same command installs it through the system package manager.

Core and Visual profiles support development and task-specific runtime; only the Tested profile validates publication. The tested pins lie inside the Visual ranges, and the tested check refuses a pin outside them. Each of these blocks publication:

- missing pin
- import failure
- functional dependency failure
- real SVG render failure
- reference-runtime failure
- generation-commitment failure
- visual-evidence workflow failure

## Where each check runs

Each test suite runs once per change, in one place:

- `python scripts/run_checks.py` runs every test suite and check command once, in parallel, with `CPB_HOME` at one scratch configuration directory whose pack state enables the shipped packs alone. It exits 1 when any command fails. CI runs it once per operating system.
- `python scripts/validate.py .` checks the invariants of the tree: structure, manifests, metadata, contracts, documentation and content conformance. It runs no test suite.
- `python scripts/package.py` builds the release and validates the stage once with `validate.py`. It checks the extracted copy by inventory and file hashes, then runs a short installed smoke.

A suite passes by exiting 0 after running at least one test, with none skipped. Run one suite directly for a targeted diagnosis, for example `python scripts/pack_smoke_test.py`. These check commands are not suites, and a person runs them directly too:

- `python scripts/release_contract.py --tag v<release>` checks the product release identity and binds a publication tag to it;
- `python scripts/refusal_coverage.py scripts/scene_plot.py scripts/scene_plot_contract_smoke_test.py` checks that a case in the suite names every refusal the reader can make;
- `python scripts/runtime_read_footprint.py` measures the reads the manifest selects.

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
python -B scripts/pack_cli.py build-lock --directory <pack-dir>
```

Create a state that registers the positional pack directory first and then the directory of each required dependency, enables exactly those pack UUIDs in that order with the dependencies sorted, and selects the positional pack for each of its named logical-resource bindings and the declaring dependency for each other name. A pack without dependencies therefore runs alone. The gate counts the pack's own records and families inside that runtime, and its audits judge the whole runtime. Use a dedicated empty cache and an existing dedicated managed root. Keep the report outside the pack:

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

For craft consultation changes, require search scope, full records, explicit decisions, atomic application, and unassessed reviewer questions. Assess actual output quality separately.

Report dependency prerequisites separately from contract assertions; a suite must not print a fully passed contract count while returning an undifferentiated environment failure.

## Fresh-session integration gate

Run the end-to-end integration script from a clean session, with known IDs and conversation history absent:

```bash
python scripts/fresh_session_runtime_smoke_test.py
```

The script requires a complete, independently managed content pack in the explicit pack runtime. When that prerequisite is missing, report the integration prerequisite as unmet. None of these stands in for it:

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

After the runner and the validator pass in the exact Tested environment:

1. Run `python scripts/rebuild_metadata.py` and confirm only intended metadata changes; generated inventories are rebuilt, never hand-edited.
2. Build with `python scripts/package.py`; the working tree is never zipped directly.
3. Verify the reports the packager writes beside the archive: the generated `<archive>.sha256` file, and in `archive-check.json` the `zip_crc_ok`, `deterministic_rebuild`, `stage_extracted_tree_match` and `installed_smoke` fields, together with `stage-extracted-tree-check.json`, `installed-smoke.json` and `validation-read-only-check.json`.
4. If a content pack changed, advance its UTC CalVer, rebuild its lock, and run its gate with the state described above, dedicated cache, explicit managed root, and report outside the pack.
5. If visual tooling changed, check the Visual profile with `python scripts/check_dependencies.py --profile visual`, then run the runner again in the Tested environment.
6. Validate every non-bundled pack independently. The core allowlist contains only the bundled commons pack; a separately distributed pack stays outside the core archive unless explicitly included.

The packager rejects symbolic links at source, staging, tree-hash, and ZIP boundaries. Regenerate canonical metadata and manifests after file moves, then verify the staged and extracted trees contain exactly the declared release inventory and each routed document appears exactly once.

The release inventory applies only to the stage built by `scripts/package.py`.
It includes runtime files, installed validation suites and their fixtures, plus host plugin metadata needed to load the skill.
It excludes `.github/`, `.gitattributes`, `.gitignore` and caches.

Source archives preserve the development tree, including CI workflows and source-control settings.
Build them from the source tree, not from the release stage or `release.include`.
Release exclusions never authorize deleting source files.
Keep source archives and release archives separately named.

Commit release metadata only after code, documentation, tests, pack locks, and generated inventories agree. Canonical pack records and visual evidence stay unchanged when the goal is merely to make a core documentation or runtime test pass.

## Release reports

`scripts/package.py` writes these reports to `--reports-dir`, or beside the archive when that option is absent:

```text
staged-validation.json            the validate.py report on the stage
stage-extracted-tree-check.json   the extracted inventory and file hashes against the stage
installed-smoke.json              each installed command, its exit status and seconds
validation-read-only-check.json   whether validation and the smoke left their trees unchanged
archive-check.json                the archive: digests, CRC, rebuild and release identity
package-summary.json              the final report, also printed on standard output
release-success.json              written last; it binds the summary by its digest
```

The installed smoke runs from the extracted copy, with `CPB_HOME` at one scratch configuration directory whose pack state enables the shipped packs alone:

- `pack_cli.py ready --only <commons pack id>`, with a scratch state, cache and managed root;
- `production_workflow.py --help`;
- `session_entry_points.py`, from inside the extracted tree;
- `examples/generation/build_example.py --out <scratch dir>`, then the `prepare_argv` it prints.

The final report keeps this shape. Trimmed output of a real run:

```json
{
  "ok": true,
  "package": "character-prompt-builder",
  "version": "2026.10.04.1",
  "content_sha256": "9592674000bcfd574d558f19eb2db9769b8c85112dd1462bbda712d52ca7809f",
  "publication_mode": "fresh-attempt-archive-last",
  "staged_validation": {"files": 888, "manifest_files": 887, "tested_dependencies": 6, "default_pack_records": 105},
  "stage_extracted_tree_match": true,
  "installed_smoke": {"ok": true, "seconds": 8.39, "commands": ["commons-only pack runtime", "production workflow help", "session entry", "synthetic generation example", "synthetic prepare"]},
  "staged_validation_read_only": true,
  "installed_smoke_read_only": true,
  "transport": "synthetic only"
}
```

## First-use activation and bundled integrity

`config/pack-initialization.json` enables all discovered packs only while the selected state file is absent, and `ready` persists that result. Existing explicit state is preserved: deliberately disabled packs remain disabled. `config/default-pack-state.json` remains the minimal core-release catalog seed and leaves first-use activation of additional supplied packs unrestricted.

The actual bundled `packs/commons` directory with the commons UUID is core-managed. A `pack.lock.json` is absent there by design: core source inventory and `MANIFEST.json` commit it together with the project, and pack validation still checks its schema and files. `lock` and pack release-lock creation refuse that directory rather than recreating an unnecessary lock. The exemption is bound to that path rather than to a manifest flag, so a copy of commons and every other pack still need a lock to be released or installed. The release gate reports a live core inventory for commons in place of a lock. Every external pack's lock stays in place and at full strength.

## Production execution verification

The runner covers the production suites, the unittest modules and every example that offers `--check`. These examples write a new directory, so a person runs them directly:

- `python examples/production-execution/run_example.py --out <new-directory>`
- `python examples/production-execution/repair_example.py --out <new-directory>`
- `python examples/generation/build_example.py --out <new-directory>`, then the `prepare_argv` it prints
- `python examples/story-context/run_example.py --out <new-directory>`, which records each command and artifact of the moment path

The production fixtures supply explicitly synthetic authority; they grant no spending permission and establish no artistic quality.

`scripts/execution_contract.py` owns integrity and file I/O. `scripts/production_binding.py` binds a run's consumer to its Generation Package. It also holds the studio-path, new-output and diagnostic helpers that the package builder, verifier, dispatcher preview and `production_spec.py draft` share.

## Executable README examples

Run `python scripts/readme_smoke_test.py` from the product root after changing
user-facing instructions. The [README smoke test](../../scripts/readme_smoke_test.py):

- executes the marked examples in fresh temporary directories;
- verifies their files and source-change behavior;
- checks local documentation links;
- checks live command signatures without contacting a provider.

The runner runs this same test. Passing examples leave prose
completeness, Persona understanding, expressive quality and the full tested
dependency environment uncertified.

Validate a completed reading record with `python scripts/route_reading.py RECORD --root STUDIO`.
The checker reports issuance and quotation integrity; the operator assesses its application to the current task.
