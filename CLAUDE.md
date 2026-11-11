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

Saved work obtains linked runtime guidance and selected-model knowledge through
the route reader under [Continue the requested operation](#continue-the-requested-operation-in-its-studio).
Read the complete selected material. Conversation-only answers read applicable
documents directly, without a route or Studio. Reuse complete current material
already delivered in this context; a fresh context reads the necessary material
again.

## Choose rendering and inspect model controls

Image work includes feature `render-contract` for `references/runtime/render-contract.md` in that read.
Use `python scripts/render_contract.py presets` when choosing an authored rendering treatment, then record who chose it and why. The operation alone is sufficient when rendering remains with the model.
The selected-model route read supplies the complete guidance card, including input contracts, use-case advice and author preferences.
`python scripts/render_contract.py model --model MODEL_ID` serves independent model inspection; production uses the card delivered with its selected route.
An external target absent from the catalog uses acquired provider evidence and the ordinary external execution branch.
Existing-image edits also require an exact semantic edit binding.
Shared image inputs bind each subject's reference uses and the exact external request.
Interpret source records into a depiction that the model can resolve from its actual prompt and media.
Develop what is present, what happens and how its parts relate. Use constraints to refine that intended construction.
Keep internal identifiers, source paths and production commentary in their owning records.
Apply scoped model use-case guidance and current author selection preferences.
The editable `render_intent` records the operation and binds any authored rendering declaration to its prompt span. A selected Production Specification can own it; an ordinary delivery can own it directly. External tasks retain a selected declaration as an applied source.
Preparation shows the complete request. Dispatcher packages seal resolved controls; external bindings pin the authored request and evidence.

## Continue the requested operation in its Studio

```sh
python scripts/studio.py init --out STUDIO --studio-id <id> --title "<title>"
python scripts/production_workflow.py status --root STUDIO
python scripts/execution_routes.py read <route> --operation <operation> --execution <execution> --root STUDIO
python scripts/production_workflow.py draft-inputs --root STUDIO --route <route> --artifact <artifact> --execution <execution> --out-dir work/draft
```

Open the work task before drafting. Register a character only when the work has
an owning character; authored text and an ordinary image need no placeholder.
Select `author`, `save`, `prepare`, `execute`, `review` or `adopt` for the current
operation and take `authored`, `external` or `dispatcher` from the task's execution
kind. Add the applicable specialist features. Include `--model MODEL`
and the selected `--service SERVICE`, `--model-file FILE` for an acquired model,
or `--dialect ID` for family-only work. The reader delivers the complete operation
and execution contract and selected knowledge. Continue every page to its delivery record.
An earlier source-delivery record alone does not supply knowledge to a new context.
The reader returns JSON: read each `body` segment, follow `actions.continue`
until null, and retain `reading.record`. In the same context, supply complete
prior keys with repeatable `--known-reading` or follow `context_reuse.operations`;
the reader delivers missing or changed bodies and records their provenance.
Fresh contexts read the applicable bodies again without discarding production work.

Edit the draft's files and authored choices. Task direction, independent criteria,
source use, expression and controls stay with their responsible author. The
compiler derives bindings, reference positions and file hashes:

```sh
python scripts/production_workflow.py save --root STUDIO --choices work/draft/choices.json
python scripts/production_workflow.py prepare --root STUDIO --choices work/draft/choices.json
```

Use the operation requested: `save` records authored text, while `prepare` makes
an inspectable model request. `save --draft` preserves unfinished choices.
Completed target-specific text uses the model's grammar and actual dictionary
search for a tag target, including when no image is generated. `check --choices`
is an optional diagnostic, and `build-inputs` exports the derived inputs when
that separate output is needed. Ordinary descriptive preparation needs no unused
plot, specification, creative-intent or retrieval placeholders. A selected
specialist document still follows its full contract.

[Studio Runtime](references/runtime/studio.md) owns the workspace and candidates.
[Production workflow](references/runtime/production-workflow.md) locates each
complete operation contract. The status and session-entry reports expose the
current source files, partial reading and next action. After a content edit,
compile those source files again; previous saved revisions and prepared inputs
remain intact. `draft-inputs --from-run` restores a captured revision, with
`--task-id` when reopening it under another active work task.

For dispatcher generation, preparation publishes the verified Generation Package,
exact request and execution plan together. The author's actual authorization
supplies the decisions for `draft-execution` and `execute`. Execution checks that
authority, claims the operation, performs its handoff and records returned media.
`resume` recovers that same operation after interruption. `status` exposes its
submission, media and actual next command. `variant` prepares changed input;
`repeat` prepares another run of the same input. Offering-attributed parameter
contracts constrain the request before anything is sent.
For another model or service, reopen with `draft-inputs --from-run --model --service`
and follow [Change the target](references/runtime/production-variation.md#change-the-target-explicitly).
The current target and evidence selectors own regeneration of request validation;
carry meaningful content and references through that same editable workflow.

The offering's service ID selects its Studio authentication configuration. [Studio authentication](references/runtime/studio-authentication.md)
owns one entry per service in the Studio's private `credentials.json`:
`api_key` holds its saved value, or `api_key_env` names its runtime environment
variable. Follow the existing source and the owner's choice. Prepare the service
entry before giving the owner the actual file path and JSON Pointer. Pause edits
while the owner fills the saved string and saves. An environment source reads
its named variable from the executing process. Once the chosen source is
available, check that service and the target run's authentication selection and
readiness, then continue its reported next action. The claim records the service
and nonsecret source, including the variable name for an environment source.
Authenticated recovery requires that recorded source; replacing its value
supports rotation. Saved values remain available independently of environment
variables. The private JSON is excluded from ordinary production inputs,
artifact registration and Skill packaging. A whole Studio folder copy includes
it. The value is supplied separately to the transport and sent only to its
accepted host. Local key availability and submission authority are separate
checks.

External host tools use the same preparation, review and capture owners.
Follow the execution contract's `draft-execution` and `execute` decisions,
then invoke the returned host request once. `receive-external` takes the actual
response and images, derives their records and settles that call. `task.image_input` binds original images,
their uses and the exact provider request. `task.semantic_edit` owns requested
changes, preservation and review of an existing image.
For a further external trial, restore sources with `draft-inputs --from-run`,
edit the chosen changes, then use `prepare --choices` on that draft.
Use `status` or `resume` after interruption and recover the existing host result.
During authoring, `inspect-inputs --root STUDIO` locates the open work task's
saved choices, published inputs and partial route reading, including new edits
beside an existing run. Continue those files
and returned actions; the discovery record supplies no judgment or permission.

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

Apply [Agent workflow design](references/maintenance/agent-workflow-design.md)
when changing authoring, execution or recovery. It owns the shared design
criteria for agent judgment, derived inputs, phase context and task continuity.

This repository owns its runtime, documentation, schemas, examples and tests.
Data exchange follows explicit public artifact contracts.

Apply a clean-state design: treat the new specification as if it had been present
from the beginning. Reconsider the affected responsibilities, structure and
implementation from first principles, and replace superseded paths at their
owners instead of layering corrective exceptions over them.

Do not preserve or guarantee compatibility with previous APIs, data formats,
configuration or behavior. Do not retain or introduce compatibility layers,
aliases, old-version branches or fallback paths for superseded contracts. Do not
add tests whose sole purpose is to verify incompatibility with superseded behavior.

Compatibility is not a maintenance requirement, and deliberate incompatibility
is not a goal. Do not add rejection, deletion, reset or obstruction merely to
prevent existing work from carrying forward. Preserve content, choices and
evidence that remain meaningful under the current design; reassess their actual
applicability when the selected inputs or target change. Do not invalidate
otherwise applicable work solely because it originated before the change.

Keep generation provenance and later curation decisions separate. Placement or
canonical withdrawal retains the exact result and historical completion; it
records its own authored target and evidence. A retry of an earlier decision
must not restore state that a later decision replaced. Follow the owning read
and mutation boundaries in [Agent workflow design](references/maintenance/agent-workflow-design.md).

Scope ordinary navigation and display updates to the current or affected work.
Keep explicit historical inspection and repair available. Reuse a derived
display only under its complete content-dependency contract; it supplies no
permission or validation result to an effect boundary. Author meaningful
adoption choices once and derive their operation bindings without requiring
manual hashes or intermediate authorization documents.

Preserve necessary requirements, authored knowledge and the material needed for
judgment under [Writing for a reader](#writing-for-a-reader). Update producers,
validators, templates and fixtures together when their contract changes.

Creative defaults follow
[Production direction](references/runtime/production-direction.md#form-a-prompt-from-an-idea).
Ground the first proposed picture as a whole in the intended effect and actual
source authority: emotional register, visual language, palette and light, mark
and surface treatment, framing and visible detail. Derive exclusions and review
criteria from those choices. Agent convenience and easy completeness checks do
not justify requiring a whole figure, intact frame margins or any other fixed
composition. Keep deliberate crop distinct from damaged anatomy, and preserve
meaningful full-figure uses as well as selective views. Respect the author's
declared style, adopted scenes and local edits when correcting an unchosen
default. Correct habitual choices at their decision owners and contributing
defaults; do not substitute another favorite mood, medium or shot, impose novelty
quotas or random rotation, or prohibit media or prompt words.
Generic authoring templates leave unchosen art direction unresolved. Scripts
validate authored constraints without choosing the picture. Assess changed
guidance with independent first proposals for different realistic briefs under
[creative-direction evaluation](references/maintenance/testing.md#creative-direction-evaluation).
Evaluate open creation from topics or actual sparse requests; adding focal
content or stylistic cues to elicit a target picture invalidates that claim.
Retain exact requests, first answers and failures. Compare art direction across
the sample, not only camera choices: different subject names or scenes do not
establish that a habitual mood, visual language, palette or surface has changed.
First assess whether each proposal still develops the commissioned content,
subject roles and stated use. A character becoming incidental to another
subject is not improvement through variety. Open detail does not authorize an
invented commission. Exact selected-model evidence constrains proposed means;
portable wording and dictionary membership do not demonstrate a visual effect.
Rendering choices may remain with the image model. A complete prompt need not
name a medium or finish; authoring and preparation must not fabricate either
to populate metadata. Preserve applicable explicit choices through retries.
Report repeated choices as well as suitable variation, within the observed
conditions and models and the causal evidence available.

- Keep implementation details local to their owning product and generate derived files from their declared sources.
- Use explicit identifiers, evidence and declared constraints for mechanical checks; the responsible author evaluates meaning and acceptance.
  Do not implement semantic validation with regular expressions, keyword matching, or interpretation dictionaries that require entries for each new feature.
- Place neutral synthetic examples under `examples/` and preserve the user's material in their own studio.
- Give each text-encoding test one necessary non-ASCII fixture, distributing script coverage across tests.
- Report executed checks separately from unverified behavior, including incomplete runs and environmental failures.
- An agent acts on what a command prints, on `--help` and on a search of the documents and code.
  A change that adds or alters a reported state or value, an option, a refusal or a diagnostic updates those surfaces with it:
  the report gives the meaning or the next action, the diagnostic names its repair in `required_action` instead of the default text,
  `--help` describes the option or value, and the routed document and the diagnostic code table say the same.
  Follow [Context for judgment](references/maintenance/agent-workflow-design.md#context-for-judgment).

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

The product's own tests run from a temporary copy of its declared files, with
source-owned CI and source-control settings when present. The checks enable the
shipped packs alone. Release catalog validation uses those pack roots directly;
independently authored packs have their own release gates.

`.claude-plugin/`, `.codex-plugin/`, `.agents/`, `hooks/`, `MANIFEST.json` and
`config/integration-capabilities.json` are generated from `[package]` in
`package-manifest.toml`, and `config/implementation-files.json` from the import
closure of the production modules, with the digest of each module. A
preparation refuses an index whose modules changed since it was written. Edit
the metadata and the templates, never the generated files.

Follow [Maintenance testing](references/maintenance/testing.md) for check execution
and subsystem coverage. [Release Validation](references/release/validation.md)
owns the publication sequence and acceptance conditions.

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
- Teach the desired result and the actions that produce it. Keep constraints
  scoped to the properties or operations they govern, and carry the selected
  content into the deliverable. Ground requirements in the commission,
  applicable adopted definitions and intended use. Treat the author's chosen
  method as a means whose success is judged against those requirements.
- State durable product facts, rules and evidence in records and artifacts.
  Keep task-specific work instructions, work reports, process notes, decision
  histories, session narratives and conversation quotations out of product artifacts.
  Generalize task-specific lessons into reusable guidance.
  A measurement's evidence (when, what, the result) is a fact; the story of
  producing it is not.
- ASCII punctuation, no em or en dashes, English throughout.
- For README changes, follow [Documentation checks](references/maintenance/testing.md#documentation-checks),
  including preservation of executable example blocks when their commands stay the same.

## Entry point

`SKILL.md`
