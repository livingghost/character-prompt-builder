# Changelog

## 2026.10.04.2

- The test fixture that copies a studio reads the Windows junction tag only where the platform defines it, so `scripts/run_checks.py` passes on Linux again. 2026.10.04.1 failed three suites of its Linux lane on that lookup.

## 2026.10.04.1

- One public path runs an image task: `check`, `prepare`, `draft-execution`, `execute`, `resume`, `variant`, `repeat`, `retarget`, `status` and `logs`. `SKILL.md`, the routes, `--help` and the examples show the same command forms.
- `check` and `prepare` share one compiler. `check` reports every check, the request preview and the execution plan, and creates no run, authorization or reservation.
- `prepare` compiles in a staging directory and publishes the run in one step. `recover-publication` registers an interrupted publication. `staging-cleanup` lists compiler leftovers with their eligibility, and `--operation ID --apply` removes one ended operation's eligible items.
- A JSON input option of the production commands, the package builders and the dispatcher takes a file or `-` for stdin. The run keeps the bytes it read. `--task` and `--artifact` take files only.
- File arguments are relative to `--root` with `/` separators, or absolute inside the project. The production commands, package builders, verifier and dispatcher refuse an existing `--out` and keep it.
- Every command reports a failure as common diagnostics with a code, severity, phase, file, pointer, message and required action. A synthetic example: `{"ok": false, "diagnostics": [{"code": "OUTPUT_ALREADY_EXISTS", "severity": "error", "phase": "output", "file": "exported-logs", "pointer": null, "message": "--out names an existing file, which is kept: exported-logs", "required_action": "Choose a new --out.", "blocked_checks": [], "option": "--out"}]}`.
- The production commands, the package builder and verifier, and the dispatcher share one set of exit codes. 0 is success and 1 an internal error. 2 is an input defect and 3 waits for permission or configuration. 4 is an execution failure or unknown outcome, and 130 an interruption.
- Preparation stores each input and each cited evidence reading by path and SHA-256. A later ledger append keeps an earlier approval valid.
- A source deleted after preparation leaves the run intact, and `status` reports the deletion as `SOURCE_CHANGED` under freshness.
- A run fixes the pack runtime it binds: model, service, resources and retrieval records, each by pack, path and SHA-256. A drift check before every external effect reports a disabled pack, a missing record, a changed file or a changed pack release.
- A pack without a lock file can serve a run; a pack with one is verified against it.
- `variant --changes-file` changes the fields the execution plan declares as mutable, starting from any prepared run. `--candidate` names the candidates the change answers.
- Each mutable field states its schema, value form, the checks it reruns, what it rebuilds and its effect on protected criteria.
- `retarget` with an unchanged target adopts the current pack runtime. A different model or service always goes through `retarget`.
- `authority-import --expected-event` replaces the grant, and a budget change applies without preparing the run again. `status --budget` shows used, outstanding and remaining amounts grant-wide, with `run_share` for one run.
- An authorization receipt binds one exact operation, and `execute` reuses existing receipts under the current grant.
- A release names its reservation ID and follows `schemas/authoring/production-release.schema.json`, which `draft-release` and `release-reservation` both check.
- `work_ledger.py abandon --reason TEXT --actor NAME` records `abandoned` on each open run of the task. An abandoned run refuses new authorization and accepts capture, settlement and release.
- When a send's answer is lost, `resume` asks the provider once through the transport's `lookup` and never sends again.
- `draft-outcome` and `resume --outcome-file` record an evidenced statement that the provider holds no task. The reservation then becomes releasable.
- `status` follows `schemas/authoring/production-status.schema.json`. Each run reports preparation, readiness, submission, capture, registration, review and disposition separately, with the next command.
- Production owns review, disposition and selection. `candidate-status` shows a candidate's evaluation and its disposition as two fields.
- A run holds one current selection. A disposition of the selected candidate withdraws it, except while the Studio holds that candidate as its accepted image. A newer review of the selected candidate also ends the selection.
- Canonical adoption runs in one order: a delivery-only `select`, `adoption-intent` and `adopt`, an optional `studio-adoption` selection, then `complete`.
- `schemas/observed-parameter-schema.schema.json` is the one contract for a stored observed schema. A keyword the request check does not evaluate is listed in `unmeasured`.
- [Model request evidence](references/runtime/model-evidence.md) is the single entry for validation modes, the request validation record, trial plans, kinds of evidence and observed-profile adoption.
- A `measured` execution profile names the observed profile it rests on, and `render_contract.py model` verifies that profile before showing the card.
- Every CLI call records a local [operation log](references/runtime/operation-logs.md) with credentials redacted. `logs` lists them, `logs-export` copies them with a manifest, and `logs-cleanup` deletes diagnostic logs only.
- `pack_cli.py validate` takes `--pack ID_OR_NAME` or an absolute `--directory`, and returns the pack manifest with its validation report.
- `dispatch.py` previews the exact request of a prepared run and sends nothing. `execute` sends.
- `examples/generation/build_example.py` builds a complete synthetic workspace that makes no network request. Its scenario options cover a prompt change, a reference, a sheet slot and a scope shortage. Others cover a budget change, an unknown outcome, a partial review, a release and a log export.
- `status`, `draft-execution`, `execute` and `resume` verify a run's live sources once per call, and the step before an external effect verifies them again. A path check reads each entry once. A catalog search compiles its colour patterns once.
- A studio root given through a directory junction records the same studio-relative paths as the resolved root, in `resume`, `status` and Studio recording.
- Content pack identity, activation and commands are described in [Pack Format Specification](references/pack-format-specification.md), [Pack State Quickstart](references/runtime/pack-state-quickstart.md) and [Pack Maintenance](references/maintenance/packs.md), and the visual evidence bundle in [Derived Visual Evidence](references/derived-visual-evidence.md). `PACKS.md` and `VISUAL-CORPUS.md` are removed.
- A test suite runs once per artifact. `scripts/run_checks.py` runs every suite in parallel, each with a home whose pack state enables the shipped packs alone; CI calls it once. `scripts/validate.py` checks the invariants of the tree and runs no suite. `scripts/package.py` validates the stage once and checks the extracted copy by inventory, hashes and an installed smoke of five commands. The pytest bridge under `tests/` is removed.
- `package_full.py` builds the full release with the shipped commons, which `MANIFEST.json` verifies and which has no lock. Every other staged pack needs its lock.
- A pack's release gate runs it with its required dependencies: the state names the pack directory first and one directory per dependency, and a shared vocabulary such as the style-family taxonomy may come from a dependency. `package_full.py` builds that state for each staged pack.
- A file below a pack root that is not the manifest, the lock, a top-level README, NOTICE or LICENSE, or matched by a declared glob is a validation error, so a stray file cannot enter a lock.
- `config/implementation-files.json` records the digest of each module it was computed from. Preparation refuses an index whose modules changed since, as `IMPLEMENTATION_CHANGED` naming the module, with `scripts/rebuild_metadata.py` as the fix.
- The README is an overview for a first-time reader: what the product does, who it is for, installation, first commands, the send commands and a map of the references by topic. Command transcripts, troubleshooting and per-feature steps live in the references the map links, such as [Production Execution](references/runtime/production-execution.md), [Upscale Adapter](references/adapters/upscale.md) and [DEPENDENCIES.md](DEPENDENCIES.md).
- Each named resource is the whole file of the highest-ranked enabled pack that binds it, so a pack that requires the commons supersedes it. A pack outranks the packs it requires, and the state's `pack_order` orders packs that neither requires; two unordered packs that bind one name with different files are one `ready` decision naming both. Records merge across packs, and a record ID that several packs define resolves by the same rank.
- `project-defaults` is renamed `pack-defaults` and resolves by pack rank like every other name. The commons binding and file carry the new name; another pack that binds `project-defaults` renames its binding.
- The pack state holds `pack_roots`, `enabled_packs` and `disabled_packs`, and nothing chooses one pack per resource. A state file that still holds `resource_providers` is refused; delete that key once. `provider-list`, `provider-select` and `provider-clear` are gone from `pack_cli.py`.
- Every command and the test runner read the configuration directory that `CPB_HOME` names, which is `~/.character-prompt-builder` while `CPB_HOME` is unset.
- The documentation and messages use one word per idea: studio for the working directory, pack, record, run and execution, iteration and candidate, render profile and character profile.
- Commons pack release 2026.10.04.1: the stored Grok Imagine observed schema follows the observed-schema contract.

## 2026.09.24.3

- Keep development tests, CI workflows and source-control settings in source archives; apply release exclusions only when staging a release.
- Describe examples and request checks by their operation: synthetic input, request preview, and recovery without resubmission.

## 2026.09.24.2

- Release archives retain executable tests and fixtures while excluding source-control and CI configuration.
- Host plugin metadata stays in the release so installed skills remain discoverable.
- Model wording guidance resolves the selected model and its resources through one active pack runtime, including external packs.

## 2026.09.24.1

- Resolve rendering intent across independent finish axes, with attributed selection and scoped mixed-media overrides.
- Display model prompt guidance and mode-specific parameter policies during inspection and preparation.
- Seal explicit parameter decisions into Generation Packages and verify them against the active interface and final request.
- Reject unconfigured interfaces, implicit range selection, unavailable controls, and transport-side parameter injection.
- Add synthetic examples and regression coverage for rendering and execution contracts.

## 2026.09.23.7

- The changelog keeps one section per release, newest first. The release check requires the newest section to be the current release, and every section to be a release with notes, each once.

## 2026.09.23.6

- A scene reads only the parts of a Persona it needs. `persona_units.py` divides a Markdown Persona into headings and fields, each with a content hash that leaves template comments out, and a second hash that reports a heading or field whose name alone changed as renamed.
- A scene plan names each definition by anchor. The build requires the Persona core in every scene and the Persona of the phase the chapter falls in. An image also needs the appearance, unless the studio has adopted the character's identity image, which the material then records.
- A scene material states its medium, and a task that makes an image or video refuses a material prepared for text. In a studio, the series lives under `story/` and the studio is the root.
- `scene_persona.py draft` starts a plan from a scene plot. `scene_persona.py impact` lists every scene a Persona change reaches, with the runs and studio images made from it, and `studio.py status` prints the count and the command.
- `seal_contract.py` also seals the public contract manifest.

## 2026.09.23.5

- Where no task is open, `work_ledger.py show`, `studio.py init` and every command that needs a task print the command that opens one.
- A value that fits none of a field's alternatives is reported on one line with what each alternative still needs, for example `$.camera.pitch_degrees: value matches none of the 2 alternatives: expected type ['number'], got str; or expected constant 'unspecified'`.

## 2026.09.23.4

- `production_spec.py draft` writes the smallest valid Production Specification for a first or one-off image. Morphology references are required only with an identity contract, open detail is stated as "unspecified", and errors come back as deduplicated JSON.
- A route reading record asks for quotations and reasons only for the documents the author applies. A prompt answered in conversation reads no route, and `--dialect ID` reads one prompt family's guide sections.
- `--continuity recurring` needs an accepted identity image; the first images of a new character are `undecided`.
- The package builder activates the render profile and style family negative sources, and a tag family writes each as its dialect's negative form.
- `check_tag_prompt.py --dialect ID` runs the family checks without a model record and reports a family term inside a longer tag.
- Vocabulary search runs many queries in one process and ranks whole words first. Retrieval records keep every adopted record per element.
- The semantic plan checker prints a template and refuses unknown fields.
- The task and authority templates name the commands and forms they need, and the submission intent names each input file by path and SHA-256.

## 2026.09.23.3

- Rasterize SVG and character sheets with resvg-py, which installs from pip alone on every platform.
- Write every command's output, and read and write every text file, as UTF-8 whatever the locale code page is.
- A service record names its transport, and every transport meets `scripts/transport_contract.py`. A send without a definite answer is journaled as indeterminate and never repeated.
- Install a dependency profile with `check_dependencies.py --install` after the user confirms, into a virtual environment with `--venv` where the system manages Python. Each version is written once, and ffprobe is checked.
- Craft consultation has one name, and SKILL.md stays within 5000 estimated tokens while linking the documents conversational prompt work reads.
- Every deadline belongs to the operator.

## 2026.09.23.2

- The route read writes the reading record with every hash filled, so the author adds only quotations and reasons. `--model` reads only the prompt-writing guide sections for that model's family.
- Build formal inputs from the reading and only the choices a package builder cannot derive, and name the builder the task needs.
- An offering names where a service takes the image size, and a dispatch keeps the service's answer once.
- Record writes work on file systems without hard links. The shared helpers and the request, scope and reservation modules read as ordinary Python.
- The dependency check prints the install command for the Python running it: pip, or uv in an environment that has no pip.
- CI runs every test suite on both platforms, reports every failure in one run, installs the pinned dependencies with uv, and keeps the reports of a failed package build.

## 2026.09.23.1

- Consult the active craft library during direction and repair, bind authored applications to production sources, and carry questions into unassessed reviews.
- Include the synthetic cast admission example in the release archive, linked from Cast Admission and Persona Depth.
- Admit a person to the cast on the author's decision: an agent-proposed named character is a candidate in the design ledger until confirmed, a confirmation covers only its stated scope, an unnamed recurring participant keeps a stable identity, and every person uses the one Persona form at the depth their use needs. [Cast Admission and Persona Depth](references/runtime/cast-and-persona-depth.md) owns these rules, with a synthetic example under `examples/cast-admission/`.
- Develop a compressed claim into mechanisms before writing: opportunity, formation, first instance, repetition, current maintenance, recognition and presentation are examined as separate roles, and the surroundings keep purposes of their own.
- Save authoring before it is reused: a one-off answer stays in the conversation, a draft that will be revised gets its studio first, a narrative series may live inside the studio, and checkpoints are written at recoverable boundaries. Session entry reports the studio and its open task whether or not a pack runtime exists, reports a damaged studio in one line, and prints runnable commands. Studio and work-ledger commands take `--studio` before or after the command.
- Keep character work in a studio: the sheet, every generated image beside the exact request that produced it, the accepted image per slot, a gallery that every recording command rewrites, and the open task a session resumes from. Studio records are replaced whole under the project lock. Each acceptance is kept with its time and the image it replaced, so an earlier image can be accepted again. The gallery shows the prompt and negative as sent, or that none was sent. Character ids name one directory on every system.
- Work with any image service as data plus one transport module: a service record, an offering on each model record whose `request_keys` name the `model`, `prompt` and `negative prompt` keys, and a transport written against the contract in the dispatcher's module docstring. A transport returns images as URLs or as inline base64. Runware is the included transport.
- Check a Generation Package against the service's observed parameter schema before anything is sent. The dispatcher preview shows the model, service, output count, whether the negative is sent and the cost, then the exact request; the trace and the submission intent go to files on request. A bound package names its run, and the studio is the production root.
- Keep every returned image, including images beside a refusal or a count that differs from the approval, and download them only over https from the hosts the transport declares. `recover-recording` downloads what a run lacks from the saved answer and never sends again.
- Read a service credential from its environment variable or from that variable in an MCP server's `env` block, and send it only to the host the transport pins.
- Bind every production side effect to an explicit grant: prepared immutable runs pinned to the installed implementation by digest, intent and authorization steps for handoff, external claims, revision and adoption, and recovery without resubmission.
- Release a reservation until its send step is recorded, so a failed upload returns its budget, and refuse automatic resubmission after an uncertain send.
- Read a route's documents and active guides through one snapshot, with paged replay and source-bound application records. SKILL.md, which the host loads when the skill activates, names every route and feature.
- Record each catalog and vocabulary lookup with `--record lookups.json --element NAME`; the author marks each element adopted or composed with `prompt_retrieval.py`.
- Build a Generation Package from the prepared production run: the route reading comes from the run, the request check from the observed schema the active pack's offering names, and `--continuity SUBJECT=DECISION` states visual continuity. The feature walkthrough ends in a dispatch preview.
- Build formal inputs from explicit choices, accepted identities, reference bindings, and current evidence instead of copying hashes by hand.
- Keep undecided visual exploration in single-subject candidates until the author supplies the decisions required for adoption or shared scenes.
- Seal the final request and its transformation trace, then bind each execution to its validation mode and explicit authority assessment.
- Preserve original schema sources, record attributed reference schemas, and attach completed trial evidence to exact observed request profiles.
- Draft variations from recorded candidates and resume from retained evidence, preserving valid sources and delegation without reusing execution tokens.
- Settle the pack runtime with one command: `pack_cli.py ready` creates the state on first use, keeps every choice, including packs the author disabled, prints the packs retrieval uses, and exits 1 only for a decision the author has not made. A pack the catalog cannot use is left out and named in one `warning:` line with its fix, and disabling or removing a pack clears the provider choices it owned.
- Keep personal packs beside the pack state (`~/.character-prompt-builder/packs`), where `install` puts them and Skill updates leave them. `pack_cli.py init` creates, registers and enables a pack in one command, and `ready --only` makes a pack state of exactly the named packs.

## 2026.09.20.1

Initial release.

- Turn a short character idea, a detailed production brief or an approved recurring-character state into an image-generation package: prompts, scoped negative prompts and canonical reference material, written in the dialect of the target model from the bundled vocabulary and writing guide.
- Keep character work in a studio: the sheet, every generated image beside the exact request that produced it, the accepted image per slot, a gallery that every recording command rewrites, and the open task a session resumes from. The dispatcher checks a Generation Package against the service's observed parameter schema before anything is sent.
- Bind every production side effect to an explicit grant: prepared immutable runs, intent and authorization steps for handoff, external claims, revision and adoption, and recovery without resubmission.
- Reuse existing material without promoting it to canon: preserved source documents with evidence-bound extraction proposals, scene-specific Persona material verified against complete sources, and story moments resolved into production evidence.
- Inspect outcomes without a parallel ledger: read-only run reviews, evidence studies with blind review cards, explicitly configured agent trials, repair analysis over recorded reviews, pinned still-image edits and exact reference delivery.
- Read complete material by default with operator-owned budgets instead of invented ceilings. The product identity is CalVer (`YYYY.MM.DD.N`, UTC), checked by the release contract in CI and release validation.
