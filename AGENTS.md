# character-prompt-builder

Turn a short character idea, a detailed production brief, or an approved recurring-character state into a coherent image-generation package: prompts, scoped negative prompts, and canonical reference material; send it to the service the model record names, and keep every generated image in a studio beside the request that produced it.

Generated file. Edit `hosts/shared/repository-guide.md.template`.

```
<repo>/
  README.md CHANGELOG.md CONTRIBUTING.md DEPENDENCIES.md LICENSE
  package-manifest.toml pyproject.toml requirements-core.txt
  requirements-visual.txt requirements.txt requirements-tested.txt
  SKILL.md                                        the skill, and the plugin root
  .claude-plugin/ .codex-plugin/ .agents/ hooks/ MANIFEST.json      generated
  hosts/shared/                                   templates for the generated
  references/ scripts/ schemas/ templates/ config/ packs/ agents/
  examples/ .github/ .gitattributes .gitignore
```

`SKILL.md` sits at the plugin root rather than under a `skills/` directory. A
plugin with no `skills/` directory and no `skills` manifest field is loaded as a
single skill, and declaring the field would suppress that.

Commands are written with `python`. Use `python3` where that name is not on the
path, which is the default on macOS and on Debian and Ubuntu. Paths are written
from the directory holding `SKILL.md`, which is wherever the Skill is installed,
not from the working directory.

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
Run `python scripts/render_contract.py model --model MODEL_ID` to read the exact model's guidance card.
The Production Specification owns `render_intent`; Generation Packages seal the resolved control decisions.
Preparation shows the complete request and refuses an unselected or unavailable control.
Execution verifies the sealed package again, so a changed control is refused before sending.

## Where character work lives, and how a result is made

```
python scripts/studio.py init --out STUDIO --studio-id <id> --title "<title>"
python scripts/studio.py character add <character-id> --studio STUDIO
python scripts/production_workflow.py check --root STUDIO --task <task.json>
python scripts/production_workflow.py prepare --root STUDIO --task <task.json>
python scripts/production_workflow.py draft-execution --root STUDIO --run <run-id> --grant <grant-id> --out <decisions.json>
python scripts/production_workflow.py execute --root STUDIO --run <run-id> --decisions-file <decisions.json>
python scripts/production_workflow.py resume --root STUDIO --run <run-id>
python scripts/production_workflow.py status --root STUDIO --budget
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
reserves the budget, performs the declared handoff and records every returned
image. `resume` recovers the same execution, and `status --budget` shows each
run's next command and each grant's remaining amount. `variant` prepares changed
input, and `repeat` prepares another run of the same input. A request is
checked against the service's own parameter schema, stored in the pack as
observed, before anything is sent. The credential is read from the
environment variable the service record names, or from that variable in an MCP
server's `env` block in the host configuration, and is never written anywhere.
It is sent only to the host the transport pins.

## What the Skill conforms to

The Agent Skills specification, which belongs to no single host. It fixes what
every host reads and what every host refuses:

- `name` at most 64 characters and `description` at most 1024. A host refuses
  more than that.
- The body under 500 lines, and under 5000 tokens once loaded, because a host
  loads all of it the moment the Skill activates.
- References one level deep from `SKILL.md`. A file reached only through another
  file may be read in part rather than in full.
- Scripts are executed rather than read into context.

`scripts/validate.py` refuses a body over 500 lines or over 5000 tokens,
estimated as characters divided by four. It also settles that every reference
document is reached from a `SKILL.md` link or from a route or feature `SKILL.md`
names, and that every script entrypoint other than a test module is named by
routed documentation. `scripts/run_checks.py` names every test module.

## Source ownership and change discipline

This repository owns its runtime, documentation, schemas, examples and tests.
Data exchange follows explicit public artifact contracts.
Implement the current format directly as the initial product contract.
Update producers, validators, templates and fixtures together when that contract changes.

- Keep implementation details local to their owning product and generate derived files from their declared sources.
- Use explicit identifiers, evidence and declared constraints for mechanical checks; the responsible author evaluates meaning and acceptance.
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

`.claude-plugin/`, `.codex-plugin/`, `.agents/`, `hooks/`, `MANIFEST.json`,
`config/integration-capabilities.json` and the handoff envelope template are
generated from `[package]` in `package-manifest.toml`, and
`config/implementation-files.json` from the import closure of the production
modules, with the digest of each module. A preparation refuses an index whose
modules changed since it was written. Edit the metadata and the templates,
never the generated files.

The required checks are in [CONTRIBUTING.md](CONTRIBUTING.md), and
[Release Validation](references/release/validation.md) is the sole authority for
publication. Neither is copied here, because a copy drifts from the document it
claims to follow.

## Writing for a reader

These rules apply to every file a person reads: README, CONTRIBUTING, CHANGELOG,
the references, the templates, docstrings and commit messages.

- Say what a thing does, as an action: "the tool records every returned
  candidate". State a boundary at most once per section, and as who decides:
  "the author decides when a candidate becomes canon", not "the tool does not
  decide".
- One idea per sentence, about twenty words. Three or more items become a list.
- Prefer the general word. Where a product term must appear because the tools
  use it, put the general phrase beside it at its first use and use the general
  word afterward. Do not add a glossary, a preamble about the document itself,
  or a section that explains why other sections repeat.
- Show a real example next to any claim about output: an actual command's output
  or an actual record, trimmed, and labeled synthetic when it is a fixture.
- Delete a repeated principle and refer to the place it is stated. Longer is
  not safer.
- ASCII punctuation, no em or en dashes, English throughout.
- After changing README.md, run `python scripts/readme_smoke_test.py` and keep
  the executable example blocks byte-identical unless the commands changed.

## Entry point

`SKILL.md`
