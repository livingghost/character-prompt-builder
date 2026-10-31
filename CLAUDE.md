# character-prompt-builder

Turn a short character idea, a detailed production brief, or an approved recurring-character state into a coherent image-generation package: prompts, scoped negative prompts, and canonical reference material; send it to the service the model record names, and keep every generated image in a studio beside the request that produced it.

Generated file. Edit `hosts/shared/repository-guide.md.template`.

```
<repo>/
  README.md CHANGELOG.md CONTRIBUTING.md DEPENDENCIES.md LICENSE
  package-manifest.toml pyproject.toml uv.lock .python-version requirements.txt
  SKILL.md                                        the skill, and the plugin root
  .claude-plugin/ .codex-plugin/ .agents/ hooks/ MANIFEST.json      generated
  hosts/shared/                                   templates for the generated
  references/ scripts/ schemas/ templates/ protocols/ config/ packs/ agents/
  examples/ .github/ .gitattributes .gitignore
```

`SKILL.md` sits at the plugin root rather than under a `skills/` directory. A
plugin with no `skills/` directory and no `skills` manifest field is loaded as a
single skill, and declaring the field would suppress that.

The skill uses one uv environment for runtime work and validation. Follow
[Dependencies](DEPENDENCIES.md#uv-project-environment) to synchronize it. Commands
written with `python` run through `uv run --locked` or with the synchronized
environment's interpreter. Paths are relative to the directory holding `SKILL.md`,
which is wherever the skill is installed.

When the working directory is a Studio, preserve it and select the installed skill
explicitly:

```sh
uv run --locked --project /absolute/path/to/character-prompt-builder python /absolute/path/to/character-prompt-builder/scripts/session_entry_points.py
```

Use that same project and absolute script paths for later commands. Child tools
inherit the selected environment's Python through `sys.executable`.

## Before anything reads a pack

```
python scripts/pack_cli.py ready
```

Resolving the pack runtime is a session-entry precondition, not a maintenance
step. `ready` exits 1 until the author settles each `decide:` line it prints.
`scripts/session_entry_points.py` is what a host runs on `SessionStart`; it
reports what the state file settles and says so where it cannot answer, because
discovery reads every record in every root and that is the runtime's work.

## Choose rendering and inspect model controls

Image work reads `references/runtime/render-contract.md`.
Run `python scripts/render_contract.py presets` to inspect finish choices, then record who chose the intent and why.
Run `python scripts/render_contract.py model --model MODEL_ID` for a catalog target's complete guidance card.
An external target absent from the catalog uses acquired provider evidence and the ordinary external execution branch.
Existing-image edits also require an exact semantic edit binding.
Shared image inputs bind each subject's reference uses and the exact external request.
Interpret source records into a depiction that the model can resolve from its actual prompt and media.
Keep internal identifiers, source paths and production commentary in their owning records.
Apply scoped model use-case guidance and current author selection preferences.
The Production Specification owns dispatcher `render_intent`; external tasks retain it as an applied source.
Preparation shows the complete request. Dispatcher packages seal resolved controls; external bindings pin the authored request and evidence.

## Where character work lives, and how a dispatcher result is made

```
python scripts/studio.py init --out STUDIO --studio-id <id> --title "<title>"
python scripts/studio.py character add <character-id> --studio STUDIO
python scripts/production_workflow.py check --root STUDIO --task <task.json>
python scripts/production_workflow.py prepare --root STUDIO --task <task.json>
python scripts/production_workflow.py draft-execution --root STUDIO --run <run-id> --grant <grant-id> --out <decisions.json>
python scripts/production_workflow.py execute --root STUDIO --run <run-id> --decisions-file <decisions.json>
python scripts/production_workflow.py resume --root STUDIO --run <run-id>
python scripts/production_workflow.py status --root STUDIO
```

`references/runtime/studio.md` defines the studio, its iterations and its
candidates, and `references/runtime/production-execution.md` defines the run.
`scripts/session_entry_points.py` prints the studio the working directory
belongs to and its open task first; when it reports none, `init` comes before
any sheet or generation work.

The task declares the character, slot and model inputs. `check` runs every check
of `prepare` and creates no run. Preparation publishes the verified Generation
Package, exact request and execution plan together. The author fills the drafted
decision file from the actual approval. Execution checks current authority,
claims the execution, performs the declared handoff and records every returned
image. `resume` recovers the same execution, and `status` shows each
run's next command and actual submission and image records. `variant` prepares changed
input, and `repeat` prepares another run of the same input. A request is
checked against the service's own parameter schema, stored in the pack as
observed, before anything is sent. The credential is read from the
environment variable the service record names, or from that variable in an MCP
server's `env` block in the host configuration, and is never written anywhere.
It is sent only to the host the transport pins.

External host tools use the same `check`, `prepare`, review and capture owners.
Follow Production Execution's handoff, exact authorization, `claim-external`,
host call and `settle-external` branch. `task.image_input` binds original images,
their uses and the exact provider request. `task.semantic_edit` owns requested
changes, preservation and review of an existing image.
Each further external trial gets its own task, request and preparation.
Use `status` or `resume` after interruption and recover the existing host result.

## What the Skill conforms to

Character Prompt Builder uses the
[Agent Skills specification](https://agentskills.io/specification). Its format
requires `name` and `description`, limited to 64 and 1024 characters respectively.
The specification recommends keeping the main instructions below 5000 tokens,
keeping `SKILL.md` below 500 lines, and making referenced material reachable
without deep chains of links. Detailed resources are loaded when the task needs
them. These recommendations do not establish identical refusal or delivery
behavior across hosts.

This repository enforces its own entry document limits in `scripts/validate.py`.
It rejects `SKILL.md` above 500 lines or 5000 estimated tokens, counting the whole
file and rounding characters divided by four upward. The estimate is a local
validation measure rather than a tokenizer result. Preserve complete detailed
instructions in the routed resources when organizing the entry document.

The validator also checks that every reference document is reached from a
`SKILL.md` link or from a route or feature `SKILL.md` names. Every script
entrypoint other than a test module is named by routed documentation, and
`scripts/run_checks.py` names every test module. Run scripts for supported
operations; read their implementation when maintaining or investigating those
operations. Verify host support and actual delivery separately from these local
checks.

## Source ownership and change discipline

This repository owns its runtime, documentation, schemas, examples and tests.
Data exchange follows explicit public artifact contracts.
Design the owning components from first principles, as if the current design had been present from the beginning.
Replace superseded implementation paths instead of layering corrective exceptions over them.
Do not add backward-compatibility implementations or tests whose sole purpose is to verify incompatibility with superseded behavior.
Update producers, validators, templates and fixtures together when that contract changes.

- Keep implementation details local to their owning product and generate derived files from their declared sources.
- Use explicit identifiers, evidence and declared constraints for mechanical checks; the responsible author evaluates meaning and acceptance.
  Do not implement semantic validation with regular expressions, keyword matching, or interpretation dictionaries that require entries for each new feature.
- Place neutral synthetic examples under `examples/` and preserve the user's material in their own studio.
- Give each text-encoding test one necessary non-ASCII fixture, distributing script coverage across tests.
- Report executed checks separately from unverified behavior, including incomplete runs and environmental failures.

Prepare a release commit only after local validation and packaging agree.
Add its CHANGELOG section above the earlier ones, with what changed for a user.
Squash intermediate maintenance edits into that release commit.
Publish a UTC CalVer version with a push and inspect its matching CI run.
Tags and hosted releases require a separate instruction.

## Working on this repository

```
python scripts/rebuild_metadata.py   regenerate the derived files
python scripts/run_checks.py         run every test suite once, in parallel
python scripts/validate.py .         the repository-wide diagnostic
python scripts/package.py            build the release and check the extracted copy
```

The product's own tests and release checks run on a commons-only pack state
(`pack_cli.py ready --only <commons-id>`), so a personal pack never changes
their result.

`.claude-plugin/`, `.codex-plugin/`, `.agents/`, `hooks/`, `MANIFEST.json` and
`config/integration-capabilities.json` are generated from `[package]` in
`package-manifest.toml`, and `config/implementation-files.json` from the import
closure of the production modules, with the digest of each module. A
preparation refuses an index whose modules changed since it was written. Edit
the metadata and the templates, never the generated files.

The required checks are in [CONTRIBUTING.md](CONTRIBUTING.md), and
[Release Validation](references/release/validation.md) is the sole authority for
publication. Neither is copied here, because a copy drifts from the document it
claims to follow.

## Writing for a reader

These rules apply to every file a person reads: README, CONTRIBUTING, CHANGELOG,
the references, the templates, docstrings and commit messages.

- State what a thing does and who decides: "the tool records every returned
  candidate" and "the author decides when a candidate becomes canon". Keep the
  conditions, limits and evidence needed to apply those statements correctly.
- Give sentences and paragraphs a clear purpose. Use lists for parallel items
  or ordered steps, while preserving the relationships and explanations that
  make the information usable. Length alone does not determine completeness.
- Prefer familiar words and explain required product terms where the reader
  encounters them. Retain the distinctions and definitions needed for each use.
- Show a real example beside a claim about output. Include the input, output
  and context needed to assess the claim, and label a synthetic fixture as such.
  An excerpt must identify its scope and keep the evidence relevant to the claim.
- Preserve supported behavior, authored knowledge and the material needed for
  judgment when revising instructions. Before considering removal, examine the
  mechanism, theory or function from multiple relevant perspectives and establish
  that it is complete within its intended scope. Inspect its requirements,
  implementation, dependent uses, examples and failure cases. Establishing that
  completeness is a prerequisite; it does not itself justify any deletion.
- A passing test suite, current nonuse or similar wording alone establishes
  neither completeness nor lack of need. Preserve the material needed to examine
  unresolved dependencies and to support future extensions of the intended
  design. After establishing completeness, assess each proposed deletion's
  effects and verify that every affected use retains its behavior, explanatory
  basis and necessary information.
- Repeated wording or a shorter replacement alone is insufficient reason to
  delete material. Keep explanations that supply another perspective, expose a
  dependency, support a different check or make a local procedure understandable.
  Consolidate only when those functions survive, the complete owning source is
  reachable, and the affected procedures and references remain usable. State the
  reason in the change review and verify the resulting behavior and meaning.
- State durable product facts, rules and evidence in records and artifacts.
  Keep task-specific work instructions, work reports, process notes, decision
  histories, session narratives and conversation quotations out of product artifacts.
  Generalize task-specific lessons into reusable guidance.
  A measurement's evidence (when, what, the result) is a fact; the story of
  producing it is not.
- ASCII punctuation, no em or en dashes, English throughout.
- After changing README.md, run `python scripts/readme_smoke_test.py` and keep
  the executable example blocks byte-identical unless the commands changed.

## Entry point

`SKILL.md`
