# Changelog

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
- Build a Generation Package from the prepared production run: the route reading comes from the run, the request check from the observed schema the active pack's offering names, and `--continuity SUBJECT=DECISION` states visual continuity. The feature walkthrough ends in an offline dispatch preview.
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
