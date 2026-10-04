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

Each step leaves a record, and the next step starts from it.

1. **Settle the intent.** Decide what the image is for and which details may not change, and compare complete alternatives while real choices stay open. See [Sparse-Brief Discovery](references/runtime/sparse-discovery.md).
2. **Read the production knowledge.** A catalog search finds production records, and the agent reads each selected record in full. See the [Preset System Contract](references/preset-system-contract.md).
3. **Resolve the subject.** For a recurring character, its character profile, design and current story state say what stays fixed and what may vary. See [State-Aware Series](references/runtime/state-aware-series.md).
4. **Choose the finish and the model controls.** Record the rendering intent, read the selected model's guidance and resolve each control it requires. See [Rendering choices and execution controls](references/runtime/render-contract.md).
5. **Write the prompt and seal the request.** The prompt, the scoped negative, the settings and the ordered references are checked and bound to their files. See [Image Generation](references/runtime/image-generation.md).
6. **Prepare, approve and send.** Preparation shows the complete request and its cost, and sending waits for a separate approval. See [Production Execution](references/runtime/production-execution.md).
7. **Review and continue.** Every returned image is kept and compared with the stated intent before anything is selected. See the [Studio Runtime](references/runtime/studio.md).

A request for a prompt alone ends once the prompt is written. Selecting an image, using it as a reference and making a detail permanent are three separate decisions, each the author's. The tools check that a request matches its declared inputs, and people judge whether the image succeeds.

## Installation

Use Python 3.11 or later. The core needs only the standard library. Image conversion, visual evidence and image editing need the optional visual dependencies.

Copy the complete extracted product folder to the host's skill location, or install the package's plugin root on a plugin-capable host. [SKILL.md](SKILL.md) is the agent's entry point, and the scripts, schemas and resources beside it are part of the product. A text-only chat can discuss a design but cannot run the tools.

Run the following from the extracted product folder with the interpreter the host will use:

<!-- readme-example: core-check -->
```sh
python scripts/check_dependencies.py --profile core
```
<!-- end-readme-example -->

For image work, run the same check with `--profile visual --install`. It prints the commands that install what is missing, runs them once you confirm and checks again.

[DEPENDENCIES.md](DEPENDENCIES.md) explains each dependency, Pythons managed by the system, virtual environments and fonts. The [core](requirements-core.txt), [visual](requirements-visual.txt) and [combined](requirements.txt) requirement files define the dependency profiles. The [tested requirements](requirements-tested.txt) pin the release-validation environment.

## First commands

Settle the content-pack state, then ask the catalog for options around a real brief. These commands read local resources only and generate nothing:

```sh
python scripts/pack_cli.py ready
python scripts/catalog_cli.py recommend "a retired lighthouse keeper at dawn, portrait, overcast light" --directions 2
python scripts/catalog_cli.py inspect RECORD_ID
```

`ready` prints the enabled packs and any decision it waits on. `recommend` returns complete alternative directions, each naming what it keeps, what it adds and what stays adjustable. `inspect` prints one full record with its constraints. A first request to the installed skill can then be:

> Develop an image prompt from this design. Preserve the attached identity details. Show alternatives only for decisions I have left open, state what you assumed, and do not send anything to a generation service.

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

After an interruption, `resume` recovers the same execution from saved evidence and never sends its request twice. `status --budget` names each run's next command and how much of each approved budget remains. The included transport is for Runware, and [Image Generation](references/runtime/image-generation.md) shows how another service is added. The [synthetic generation example](examples/generation/README.md) runs the whole path with a local transport that makes no network request.

## Where each topic is documented

[SKILL.md](SKILL.md) routes the agent to these documents, and a person can read them directly.

- Sparse briefs and alternative directions: [Sparse-Brief Discovery](references/runtime/sparse-discovery.md)
- Prompt wording for a target model: [Prompt Composition](references/runtime/prompt-composition.md) and [Prompt Vocabulary](references/runtime/prompt-vocabulary.md)
- Finish, model guidance and controls: [Rendering choices and execution controls](references/runtime/render-contract.md) and [Model request evidence](references/runtime/model-evidence.md)
- Worlds, character profiles and the author's aims: [World-Coherent Creative Development](references/runtime/narrative-development.md), [Authorial Intent](references/runtime/authorial-intent.md) and [Narrative Authoring](references/narrative-authoring.md)
- Identity, anatomy and expression: [Character Identity Contract](references/character-identity-contract.md), [Morphology and species contracts](references/morphology-and-species-contracts.md) and [Performance Language](references/performance-language-specification.md)
- Clothing, growth and fixed marks: [Garment Geometry](references/garment-geometry-specification.md), [Growth Geometry](references/growth-geometry-specification.md) and [Distinctive Details](references/distinctive-detail-specification.md)
- Character sheets: [Character Sheet Discipline](references/runtime/character-sheet-discipline.md)
- Scene material from a character profile: [Scene Persona Material](references/runtime/scene-persona.md)
- Story state and world facts: [State-Aware Series](references/runtime/state-aware-series.md) and [World Realization](references/runtime/world-realization.md)
- Existing manuscripts and notes: [Source Material](references/runtime/source-material.md)
- Reference images and their influence: [Prompt Artifact References](references/runtime/reference-prompt-artifacts.md) and [Derived Visual Evidence](references/derived-visual-evidence.md)
- Runs, approvals, budgets and command logs: [Production Execution](references/runtime/production-execution.md), [Production Permissions](references/runtime/production-permissions.md) and [Operation Logs](references/runtime/operation-logs.md)
- Character folders, galleries and resumption: [Studio Runtime](references/runtime/studio.md)
- Editing and upscaling an approved image: [Image Editing](references/runtime/image-editing.md) and [Upscale Adapter](references/adapters/upscale.md)
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

## Release management

Releases use the CalVer scheme `YYYY.MM.DD.N` in UTC. [package-manifest.toml](package-manifest.toml) owns the release identity, and the generated host and Python metadata are checked against it. [CHANGELOG.md](CHANGELOG.md) records each release under its version heading. Release commands are in [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Character Prompt Builder is free software under the GNU GPLv3. The full text is in [LICENSE](LICENSE).

## Support

If this project is useful, you can support its development.

- GitHub Sponsors https://github.com/sponsors/livingghost
