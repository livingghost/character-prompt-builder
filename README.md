# Character Prompt Builder

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

Character Prompt Builder turns a character idea, an existing design or a scene brief into a visual direction and the files that produce it. It can stop at a prompt, build a reusable character sheet, or send an approved image request. Every returned image is kept beside the exact request that produced it.

It is an Agent Skill: instructions an agent follows, plus local Python tools the agent runs. The author and the agent decide what an image is for and judge what comes back. The tools search the bundled production knowledge, check inputs, keep files with their hashes and record each approval. Authoring and the examples below run without an API key.

## Who this project is for

Use it when the job is more than finding a pleasing string of tags:

- an author with a one-line idea who wants coherent alternatives before any image exists;
- an artist developing a design that must stay recognizable from image to image;
- a production team revisiting one subject across scenes, sessions and models.

The subject can be a person, an animal, an anthropomorphic character, a creature, a machine or a scene with no cast. A short request stays short, and a long project follows the same path with more records.

## Core production chain

Saved production records the inputs and decisions needed by later steps.

1. **Settle the purpose and scope.** Identify what the artifact must communicate and which requirements stay fixed. See [Production direction](references/runtime/production-direction.md).
2. **Discover and choose the expression.** Consult relevant knowledge before resolving open presentation choices. The agent chooses within delegated scope, using a scene, ordered views, graphic hierarchy or another suitable construction. Read each selected record in full. See [Knowledge discovery](references/runtime/sparse-discovery.md) and the [Preset System Contract](references/preset-system-contract.md).
3. **Resolve the subject.** For a recurring character, its character profile, design and current story state say what stays fixed and what may vary. See [State-Aware Series](references/runtime/state-aware-series.md).
4. **Choose the finish and the model controls.** Record the rendering intent, read the selected model's guidance and resolve each control it requires. See [Rendering choices and execution controls](references/runtime/render-contract.md).
5. **Write the prompt and seal the request.** The prompt, the scoped negative, the settings and the ordered references are checked and bound to their files. See [Image Generation](references/runtime/image-generation.md).
6. **Prepare, authorize and send.** Preparation shows the complete request and its cost; sending uses the author's recorded authorization for that scope. See [Production Execution](references/runtime/production-execution.md).
7. **Review and continue.** Every returned image is kept and compared with the stated intent before anything is selected. See the [Studio Runtime](references/runtime/studio.md).

A request for a prompt alone ends once the prompt is written. Selecting an image, using it as a reference and making a detail permanent are three separate decisions, each the author's. The tools check that a request matches its declared inputs, and people judge whether the image succeeds.

## Installation

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) to run the skill in its declared Python environment. Prompt work, image processing and validation use the same dependencies. [The Python selection](.python-version) chooses Python 3.12 by default; [the project declaration](pyproject.toml) supports Python 3.12 or later and owns the direct package pins.

Copy the complete extracted product folder to the host's skill location, or install the package's plugin root on a plugin-capable host. [SKILL.md](SKILL.md) is the agent's entry point, and the scripts, schemas and resources beside it are part of the product. A text-only chat can discuss a design but cannot run the tools.

The [package manifest](package-manifest.toml) identifies the installed release and declares its bundled contents.

From the extracted product folder, synchronize the committed [lockfile](uv.lock), then check the complete environment:

```sh
uv sync --locked
```

Execute each `python` command on this page through `uv run --locked`. The environment check's script invocation is:

<!-- readme-example: environment-check -->
```sh
python scripts/check_dependencies.py
```
<!-- end-readme-example -->

Its complete uv invocation is:

```sh
uv run --locked python scripts/check_dependencies.py
```

The host's session hook uses this same uv environment. An agent working from a Studio directory selects the skill with `uv run --locked --project /absolute/path/to/character-prompt-builder` and passes the script's absolute path; its working directory stays in the Studio. Child tools inherit that environment's Python.

[DEPENDENCIES.md](DEPENDENCIES.md) explains every package, virtual environments, fonts and FFmpeg. The check reports missing prerequisites; `--install` prints the installation commands, asks for confirmation and checks again after running them. The generated [requirements file](requirements.txt) provides the same locked packages to pip-based tooling. [Release Validation](references/release/validation.md#core-release-environment) defines the publication checks in this environment.

## First commands

Settle the content-pack state, then ask the catalog for options around a real brief. These commands read local resources only and generate nothing:

```sh
python scripts/pack_cli.py ready
python scripts/catalog_cli.py recommend "whole object detail relationship" --limit 8
python scripts/catalog_cli.py inspect RECORD_ID
```

`ready` prints enabled packs and any unresolved activation decision. `recommend`
returns candidate knowledge with its functions and applicability, plus the
active catalog's scope and optional dictionary categories. The agent uses that
evidence to choose the construction. `inspect` prints one complete record.
A first request to the installed skill can then be:

> Develop an image prompt from this design. Preserve the attached identity details, choose a suitable presentation and briefly explain the choice. Do not send it to a generation service.

### Examples that run locally

These constructed examples need no API key. They write into new directories beside the product folder.

Prepare scene material from a short synthetic character profile, then verify it and its archived sources:

<!-- readme-example: authoring-material -->
```sh
python scripts/create_authoring_example.py --root ../cpb-authoring-demo
python scripts/scene_persona.py verify --root ../cpb-authoring-demo --plan scene-plan.json --bundle scene-material --require-ready
python scripts/source_material.py verify --root ../cpb-authoring-demo --bundle source-material
```
<!-- end-readme-example -->

Export that scene material as a public artifact and verify it as a receiving tool would:

<!-- readme-example: public-exchange -->
```sh
python scripts/protocol_exchange.py export --root ../cpb-authoring-demo --artifact scene-material/material.json --out public-exchange
python scripts/protocol_exchange.py verify --root ../cpb-authoring-demo --bundle public-exchange
```
<!-- end-readme-example -->

Run a synthetic text task from approval to completion, with one hash-linked record per event:

<!-- readme-example: production-lifecycle -->
```sh
python examples/production-execution/run_example.py --out ../cpb-production-demo
```
<!-- end-readme-example -->

## Send an approved generation

A live generation needs:

- a service record, and a model record with an offering on that service;
- the credential in the environment variable the service record names, never in studio files;
- a prepared run and an approval that covers it.

<!-- readme-send: generation -->
```sh
python scripts/production_workflow.py prepare --root STUDIO --task task.json
python scripts/production_workflow.py draft-execution --root STUDIO --run RUN --grant GRANT --out decisions.json
python scripts/production_workflow.py execute --root STUDIO --run RUN --decisions-file decisions.json
```
<!-- end-readme-send -->

- `prepare` publishes the run with its exact request preview and execution plan. `check` takes the same arguments, runs every check and creates no run.
- `draft-execution` writes the decision file, which you fill from the actual approval.
- `execute` sends only what that file covers and records every returned image.

After an interruption, `resume` recovers the same execution from saved evidence and never sends its request twice. `status` names each run's next command and its recorded submissions and images. The included transport is for Runware, and [Image Generation](references/runtime/image-generation.md) shows how another service is added. The [synthetic generation example](examples/generation/README.md) runs the whole path with a local transport that makes no network request.

## Where each topic is documented

[SKILL.md](SKILL.md) routes the agent to these documents, and a person can read them directly.

- Expressive choices and sparse briefs: [Production direction](references/runtime/production-direction.md) and [Knowledge discovery](references/runtime/sparse-discovery.md)
- Multiple views, graphic regions and shared identity: [Production Specification](references/production-specification.md)
- Prompt wording for a target model: [Prompt Composition](references/runtime/prompt-composition.md) and [Prompt Vocabulary](references/runtime/prompt-vocabulary.md)
- Finish, model guidance and controls: [Rendering choices and execution controls](references/runtime/render-contract.md) and [Model request evidence](references/runtime/model-evidence.md). Select an exact model and offering; observed interface constraints live in the active model record and its pinned schema, not in README examples.
- Worlds, character profiles and the author's aims: [World-Coherent Creative Development](references/runtime/narrative-development.md), [Authorial Intent](references/runtime/authorial-intent.md) and [Narrative Authoring](references/narrative-authoring.md)
- Identity, anatomy and expression: [Character Identity Contract](references/character-identity-contract.md), [Morphology and species contracts](references/morphology-and-species-contracts.md) and [Performance Language](references/performance-language-specification.md)
- Clothing, growth and fixed marks: [Garment Geometry](references/garment-geometry-specification.md), [Growth Geometry](references/growth-geometry-specification.md) and [Distinctive Details](references/distinctive-detail-specification.md)
- Character sheets: [Character Sheet Discipline](references/runtime/character-sheet-discipline.md)
- Scene material from a character profile: [Scene Persona Material](references/runtime/scene-persona.md)
- Story state and world facts: [State-Aware Series](references/runtime/state-aware-series.md) and [World Realization](references/runtime/world-realization.md)
- Existing manuscripts and notes: [Source Material](references/runtime/source-material.md)
- Reference images and their influence: [Prompt Artifact References](references/runtime/reference-prompt-artifacts.md) and [Derived Visual Evidence](references/derived-visual-evidence.md)
- Runs, approvals, execution records and command logs: [Production Execution](references/runtime/production-execution.md), [Production Permissions](references/runtime/production-permissions.md) and [Operation Logs](references/runtime/operation-logs.md)
- Character folders, galleries and resumption: [Studio Runtime](references/runtime/studio.md)
- Changing clothing, objects, backgrounds or other depicted content: [Semantic Instruction Editing](references/runtime/semantic-instruction-edit.md)
- Local pixel edits, masks and enlargement: [Image Editing](references/runtime/image-editing.md), [Scene masks](references/runtime/scene-mask-planning.md) and [Upscale Adapter](references/adapters/upscale.md)
- Reviewing results, repeated failures and agent trials: [Evidence Review](references/runtime/evidence-review.md), [Repair Analysis](references/runtime/repair-analysis.md) and [Agent Evaluation](references/runtime/agent-evaluation.md)
- Failures in the picture itself: [Troubleshooting](references/troubleshooting.md)
- Exchange with other tools: [Protocol Exchange](references/protocol-exchange.md)
- Long material and explicit budgets: [Resource handling](references/resource-handling.md)

## Packs and studios

The bundled [commons pack](packs/commons/) is the one pack the product ships. Pack selection and personal packs live in the configuration directory, so they survive skill updates. `CPB_HOME` names that directory; it is `~/.character-prompt-builder/` while `CPB_HOME` is unset. A pack found on disk is used only once it is enabled.

- [Pack State Runtime Quickstart](references/runtime/pack-state-quickstart.md) explains activation and isolated pack state.
- [Pack Maintenance](references/maintenance/packs.md) creates, validates and releases a personal pack.
- The [Pack Format Specification](references/pack-format-specification.md) defines a pack.

Keep studios and generated images outside the installed skill folder. `studio.py init` creates a studio, and the [Studio Runtime](references/runtime/studio.md) defines it and its layout.

## Validation

```sh
python scripts/run_checks.py
python scripts/validate.py .
python scripts/package.py
```

- `run_checks.py` runs every test suite once, in parallel, with `CPB_HOME` at one scratch configuration directory whose pack state enables the shipped packs alone. CI runs the same command.
- `validate.py` checks the structure, metadata, contracts and documentation of the tree, and runs no suite.
- `package.py` builds the release archive and checks the extracted copy.

The checks use synthetic fixtures and never contact a service. [Release Validation](references/release/validation.md) is the authority for publication.

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md) explains how to prepare a development checkout, run the checks and build a release. A contribution states the intended behavior, updates its documentation and adds a test that fails on the defect it addresses. Checks stay as they are, and studio data and credentials stay out of the product. Pack contributions follow [Pack Maintenance](references/maintenance/packs.md).

## License

Character Prompt Builder is free software under the GNU GPLv3. The full text is in [LICENSE](LICENSE).

## Support

If this project is useful, you can support its development.

- GitHub Sponsors https://github.com/sponsors/livingghost
