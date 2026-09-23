# Character Prompt Builder

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

Character Prompt Builder turns a character idea, an existing design or a scene brief into a visual direction and the files that produce and review it. It can stop at a prompt, build a reusable character sheet, assemble reference images, or send an approved image request and keep every result beside the exact input that produced it.

It is an Agent Skill: instructions the agent follows, plus local Python tools the agent runs. The author and the agent decide what an image is for and judge what comes back. The tools search the bundled production knowledge, check inputs, keep files and hashes, rebuild a character's state at any point in the story from recorded events, and track what was approved. Authoring and the offline examples below run without an API key.

The same workflow serves people, ordinary animals, anthropomorphic subjects, creatures, machines and scenes with no cast at all. A single image and a long-running project follow the same principles, and a short request stays short.

## Who this project is for

Use it when the job is more than finding a pleasing string of tags. You need to decide what an image should communicate, keep the subject you designed, let a reference influence only the parts it should, or continue from a result without losing the decisions behind it. An author with a one-line idea, an artist developing a reusable design and a production team revisiting one subject across scenes all follow the same path.

A typical brief fixes the subject's build and recognizable details and leaves lighting and composition open. The first job is to explore coherent directions around those fixed points. Once one is chosen, the skill writes the prompt, orders the references and sets the model parameters that express it. The returned image is evidence to inspect: it can be accepted, repaired or set aside, and it becomes part of the character's definition only when the author says so.

## Core production chain

```text
brief, existing design or approved story state
  -> fixed details and open visual decisions
  -> options while meaningful decisions stay open
  -> one selected direction
  -> full reading of the production records it uses
  -> the character's current state and profile, when continuity matters
  -> prompt and negative prompt
  -> checked generation package with ordered references
  -> approved request and every returned image
  -> review, local repair, selection, and write-back
```

**Settle the intent first.** The author supplies or decides the purpose, the fixed conditions and the acceptable freedom. The agent turns them into a complete image description: what the viewer should recognize, what carries the composition, how the subject is built, how the finish serves the purpose. When a sparse brief leaves several directions open, the agent compares complete alternatives instead of piling incompatible details into one prompt. A prompt-only request can stop here.

**Read what makes the direction possible.** Catalog search finds production records; the agent then reads the selected records in full, including their constraints and the conditions they apply under. For a recurring character, the character profile, the design, the author's aims and the current story state say what stays fixed and what may vary.

**Turn the direction into exact inputs.** The agent decides how each requirement appears in text and references. The scripts check the declared model and service parameters, keep the attachment order and permitted influence of every reference, and bind the package to its actual files. Sending a request is a separate step that needs a prepared run and an explicit approval.

**Inspect and continue deliberately.** Every returned image is kept with the input that produced it. The review compares the actual image with the stated intent, separates what was observed from why it might have happened, and targets a repair at the part that needs changing. Selecting an image for delivery, using it as a reference and making a detail a permanent part of the character are three separate decisions. A new session resumes from the saved project and its records.

## Installation

Use Python 3.11 or later. Authoring, catalog access and the text examples use only the standard library. Image conversion, visual-evidence extraction and image editing need the optional visual dependencies.

For a host that installs a skill directory, copy the complete extracted product folder to the host's skill location. For a plugin-capable host, use the package's plugin root with its host metadata. [SKILL.md](SKILL.md) is the agent's entry point; the scripts, schemas, resources and templates beside it are part of the product. A text-only chat can discuss a design but cannot run the tools.

Run the following from the extracted product folder with the interpreter the host will use:

<!-- readme-example: core-check -->
```sh
python scripts/check_dependencies.py --profile core
```
<!-- end-readme-example -->

This checks the environment and installs nothing. For image work, install and check the visual profile:

```sh
python -m pip install -r requirements-visual.txt
python scripts/check_dependencies.py --profile visual
```

CairoSVG needs the native Cairo runtime as well as its Python package, and character-sheet text rendering needs an installed font. [DEPENDENCIES.md](DEPENDENCIES.md) explains each dependency and the native-library notes. The [core](requirements-core.txt), [visual](requirements-visual.txt) and [combined](requirements.txt) requirement files define the supported profiles; the [tested requirements](requirements-tested.txt) pin the release-validation environment.

### First commands

Once the core check passes, settle the content-pack state and ask the catalog for options around a real brief. These commands read local resources only and generate nothing.

```sh
python scripts/pack_cli.py ready
python scripts/catalog_cli.py recommend "a retired lighthouse keeper at dawn, portrait, overcast light" --directions 2
python scripts/catalog_cli.py inspect RECORD_ID
```

`recommend` returns options in `direction_cards`. The first option from that brief with only the bundled commons pack enabled, trimmed:

```json
{
  "title": "Quiet window portrait",
  "preserves": ["lighting: overcast light"],
  "adds": ["restrained interior context", "lateral window illumination", "face-led visual hierarchy", "..."],
  "adjustable": ["gaze target", "room character", "crop tightness", "wardrobe"],
  "preset_ids": {"style_family": "style-family-clear-portrait", "scene": "scene-quiet-window-portrait",
                 "camera": "camera-close-eye-level", "lighting": "lighting-overcast-ambient"},
  "open_axes_after_card": ["identity", "role", "wardrobe", "pose", "performance", "environment", "mood"]
}
```

`inspect` prints one full record with its constraints. A first request to the installed skill can then be:

> Develop an image prompt from this design. Preserve the attached identity details. Show alternatives only for decisions I have left open, state what you assumed, and do not send anything to a generation service.

## Authoring

Everything before a run: deciding what the image is for, developing the world and its subjects, reading production knowledge, and preparing reusable character and scene material.

### Creative development and the author's aims

The author's aims are their own record, kept apart from world facts and from a character's psychology. The [design form](templates/narrative/design/design-template.md) holds what the portrayal aims at, what a viewer should recognize, what may vary and the deliberate departures, each with its scope. The [character profile form](templates/narrative/personas/persona-template.md) ties a character's identity and its voice and body rules to those aims. Constancy can be the aim, and so can ambiguity. [Authorial Intent](references/runtime/authorial-intent.md) defines the records; [Authoring commands](references/narrative-authoring.md) create the full forms and audit the links between them.

[World-Coherent Creative Development](references/runtime/narrative-development.md) connects world rules, themes, agents, events, information and expression, starting from the author's actual idea and iterating across the dependencies it touches. The narrative initializer creates the structure and leaves the cast and the plot to the author; world-only work, a changing focus, unpeopled observation and a scene with no dramatic turn are all ordinary cases. Fill the forms with what the idea needs.

### Create a prompt from a brief

The agent works in three moves:

1. Decide what the image is for and what is fixed.
2. Retrieve and read the production records that apply. A search match is a lead; the decision rests on the full record behind it.
3. Choose one coherent direction and return the prompt with its negative prompt and the choices still open.

For a recurring subject, supply the current character profile, design and state, and say which kind of request it is: a local variation, a redesign, a new condition in the story or an exploratory draft. A new camera angle leaves anatomy alone, and a new outfit leaves stable identity alone.

### Find and inspect production knowledge

Production knowledge comes in layers: appeal, finish, anatomy or construction, rendering mechanics, scene elements, modules and corrections. Combine layers only where their assumptions agree; a correction written for one model family belongs to that family. The [Preset System Contract](references/preset-system-contract.md) explains the layers.

```sh
python scripts/catalog_cli.py recommend "YOUR_BRIEF" --directions 4
python scripts/catalog_cli.py inspire "YOUR_BRIEF" --categories composition,camera,lighting,emotion-nuance
python scripts/catalog_cli.py inspect RECORD_ID
```

The preparation record keeps the complete inspected record, the reason for using it and any deliberate new expression. [Sparse-Brief Discovery](references/runtime/sparse-discovery.md) describes how to compare complete alternatives; [Prompt Vocabulary](references/runtime/prompt-vocabulary.md) describes model-scoped wording.

### Model-specific prompt construction

The selected model record defines the target grammar and the service's parameter schema. Its prompt family decides which building blocks exist, in what order and with what vocabulary. The generation package carries the prompt, the scoped negative instructions, the production specification, the model settings and the ordered references, and records how the target receives each of them. It is verified again before sending, so a later edit cannot reuse an earlier approval.

The prompt in the bundled [state-aware pilot](examples/state-aware-pilot/README.md) shows the level of specificity a package carries:

```text
Create a polished cinematic 2D soft-cel office portrait of a tall broad-shouldered
blue-gray anthropomorphic wolf in a left three-quarter medium close view. Preserve
the long canine muzzle, thick charcoal brows, electric-cyan eyes, pale muzzle and
chest, paired charcoal cheek wedges, one small cyan stud on the subject-left upper
ear rim, and one healed triangular notch on the outer upper subject-left ear tip. ...

negative: photorealistic rendering, 3D render, swapped left and right details,
missing ear stud, intact left ear tip, extra pendant on the wolf, fused desk and
hand, unreadable facial markings
```

[Prompt Composition](references/runtime/prompt-composition.md), the [Prompt Writing Guide](references/runtime/prompt-writing-guide.md) and [Image Generation](references/runtime/image-generation.md) describe the steps.

### Identity, morphology and visible performance

Four inputs stay separate: stable identity, species or structural properties, individual morphology, and the state visible in one depiction. A camera change or an occlusion hides a feature without removing it. A temporary outfit, pose or expression becomes a permanent rule only when the author decides it does.

Construction covers clothing fit, layered garments, growth, fixed marks and distinguishing details, described with spatial language and the conditions that apply. See [Garment Geometry](references/garment-geometry-specification.md), [Growth Geometry](references/growth-geometry-specification.md) and [Distinctive Details](references/distinctive-detail-specification.md). Performance is expressed through gaze, posture, contact, timing, voice, ears, tails or machine signals, according to the subject's design; [Performance Language](references/performance-language-specification.md) connects the chosen expression to the character.

### Build and maintain a character sheet

The order matters: author the structured sheet data, prepare the layout, obtain any generated panel images, then record acceptance after review. Until acceptance, a panel image is only a draft. The sheet is authoring data as well as a renderable layout; generated panels can be cropped and composed into place. Accepting an image for one panel, selecting a production candidate and adopting a permanent identity detail are three decisions with three scopes. A reference board exposes the aspects the requested production needs, sized to the subject rather than to a fixed number of views. [Character Sheet Discipline](references/runtime/character-sheet-discipline.md) gives the panel, mask and board workflow.

### Prepare reusable scene material from a character profile

Even an uneventful exchange can depend on definitions spread across the whole character profile (the Persona the tools read). During scene preparation the agent reads the complete applicable originals, selects the exact passages the scene needs, and records their conditions, dependencies and application. The result is a document that later writing, repair and resumption reuse within its reviewed scope, instead of guessing the needed sections again.

Try the file workflow in an empty sibling directory. The example's few lines of subject definition demonstrate the data flow, not a real profile:

<!-- readme-example: authoring-material -->
```sh
python scripts/create_authoring_example.py --root ../cpb-authoring-demo
python scripts/scene_persona.py verify --root ../cpb-authoring-demo --plan scene-plan.json --bundle scene-material --require-ready
python scripts/source_material.py verify --root ../cpb-authoring-demo --bundle source-material
```
<!-- end-readme-example -->

The generated `scene-material/persona.md` carries the definitions themselves, each tied to its source, lines and whole-file hash:

```text
## Applicable definition text
### attention
Source: model, lines 1-2; complete source SHA-256: 1cf481eb...
Reason for inclusion: The controlling definition governs expression.

> Attend to the recipient before choosing a response.

### expression
Source: model, lines 3-4; complete source SHA-256: 1cf481eb...
Dependencies: attention

> A pause is an available response, not automatically distress.

## Application in this scene
### response (option)
A pause may be chosen after attending to the recipient; no exact line or motive is prescribed.
```

For real work, author a plan against the [plan schema](schemas/authoring/scene-persona-plan.schema.json) and run `inspect`, `build` and `verify` with your own paths:

```sh
python scripts/scene_persona.py inspect --root PROJECT --plan scene-plan.json
python scripts/scene_persona.py build --root PROJECT --plan scene-plan.json --out scene-material
python scripts/scene_persona.py verify --root PROJECT --plan scene-plan.json --bundle scene-material --require-ready
```

In a production task, add `scene-persona` to `features` and list the material:

```json
"scene_materials": [
  {"plan": "scene-plan.json", "bundle": "scene-material"}
]
```

Preparation verifies the files and carries the text into the exact input handed to the generator. Author-only information stays out of the image prompt. Changing any complete source, quoted or not, invalidates reuse, and a new participant, topic or portrayal aim can call for fresh preparation even when no file changed. When a gap appears, go back to the originals. [Scene Persona Material](references/runtime/scene-persona.md) covers replacement and accepted external snapshots.

### Resolve the story state and ground it in the world

The state resolver rebuilds the state at any point in the story from declared events and processes, keeping stable identity, temporary state, what is visible and the observed output apart. [World Realization](references/runtime/world-realization.md) connects pinned sources, resolved events, the author's aims and what each reader may know, and can inspect, build, verify and report source-change impact without a model or a cast. [State-aware authoring](references/runtime/state-aware-series.md) covers the path; the [unpeopled worked example](examples/world-realization/README.md) is runnable.

[Portrayal Principles](references/portrayal-principles.md) provides eight patterns for recognizable persistence, contrast, contextual expression, gradual change, disclosure, rupture and ambiguity. They are patterns to instantiate under the project's intent, not character types.

### Bring in existing manuscripts and notes

For an existing manuscript or notes, author a source plan naming the documents and the spans to analyze. Ingestion preserves the original bytes and records each span's completion status. Extraction proposals quote actual passages and mark each as a source statement, speech, observation, inference or unknown, so the author reviews them before anything updates the narrative or its state. A partial passage stays partial, and disagreement between a speaker, an observer and an inference stays visible. [Source Material](references/runtime/source-material.md) specifies the plans and commands.

## Production

Turning an approved direction into an exact, approved request: the task record, the dispatcher, Studio review, local editing and reference delivery.

### Prepare and record a run

Any task that saves a file is recorded as a task and prepared as a run. The task record names its purpose, source decisions, intended expression, output kind, review criteria and what the author has approved for it. Preparation freezes those inputs into a run; handing the input to the generator, sending, review, selection and making a result permanent follow as distinct steps, each leaving a record.

```text
brief and complete applicable sources
  -> authored direction and scene material
  -> prepared run and the exact input for the generator
  -> approved hand-off and, when needed, approved sending
  -> returned images and located observations
  -> reviewed selection, optionally made permanent, completion
```

See the lifecycle without a service call by running the constructed text-production example into a new directory:

<!-- readme-example: production-lifecycle -->
```sh
python examples/production-execution/run_example.py --out ../cpb-production-demo
```
<!-- end-readme-example -->

The run leaves a chain of hash-linked records, one per event:

```text
authorization -> handoff -> candidate -> review -> authorization -> selection -> completion
```

Each record names the previous one, the input it applies to and the approvals it relies on:

```json
{
  "event": "handoff",
  "sequence": 2,
  "previous": "1207092ad513911af14c14331d5e26633e89ccfd85eb798046b6c1a0be6d45ce",
  "input_sha256": "b9ccb0b4a6538670677b823d7c5c50b153f19e953efeac58cdcc8e9d259eb8ae",
  "data": {
    "recipient": "synthetic fixture",
    "method": "manual",
    "authorizations": ["1207092ad513911af14c14331d5e26633e89ccfd85eb798046b6c1a0be6d45ce"]
  }
}
```

The example's approvals are labeled synthetic fixtures. Real work uses your own approvals. [Production Execution](references/runtime/production-execution.md) gives the task, authorization and review commands.

### Send an approved image generation

A live generation needs a configured service, a model record that describes that service's fields, credentials outside the project files, and a package bound to a prepared run. The included transport is for Runware. Another service is a service record, an offering on each model record it exposes, and one transport module, `transport_<service>.py` beside the other scripts, written against the contract in the dispatcher's module docstring; a service without a transport uses an explicitly recorded external hand-off. A dry run shows the exact request and saves what to approve:

```sh
python scripts/dispatch.py generation-package.json --studio PROJECT --character SUBJECT_ID --slot SLOT_ID --intent-out intent.json
```

Approve `intent.json` with the real output count and cost bound, using `draft-authorization` and `authorize` from [Production Execution](references/runtime/production-execution.md). `authorize` prints the approval record; its `sha256` is `RECEIPT_SHA` below, and the live send carries it:

<!-- readme-send: generation -->
```sh
python scripts/dispatch.py generation-package.json --studio PROJECT --character SUBJECT_ID --slot SLOT_ID --production-authorization RECEIPT_SHA --send
```
<!-- end-readme-send -->

### Upscale an approved source

An upscale is its own prepared and approved task binding the source image, the upscaler, the factor and the settings, with its own approval:

<!-- readme-send: upscale -->
```sh
python scripts/dispatch.py --upscale --model UPSCALER_ID --source SOURCE_IMAGE --scale 2 --request-validation-file VALIDATION_JSON --studio PROJECT --character SUBJECT_ID --slot SLOT_ID --production-authorization RECEIPT_SHA --send
```
<!-- end-readme-send -->

Use a factor the selected record supports. A changed input, reference order, count or setting needs a new approval.

### Review Studio results and recover an interrupted run

Studio keeps each returned image beside its request, and the gallery shows them all. Selecting one delivers it; making it part of the character's permanent identity is a separate decision. After an interruption, the recorded request and output show whether a result arrived but was not indexed or whether the remote result is still unknown, and recovery works from that evidence instead of a second paid request. The [Studio Runtime](references/runtime/studio.md) explains slots, iterations, selected images, recipes, the gallery and resumption from an open task.

### Edit an existing image

[Image Editing](references/runtime/image-editing.md) performs crop, resize, rotation and composition as new reviewed images under the run's existing approval and repair history. The source image remains the evidence for the edit; the edited file is inspected for the intended framing and for protected content before it is selected.

### Control reference-image influence

A reference can constrain identity, morphology, clothing, pose, palette or another declared aspect while leaving the rest free. The reference contract records the allowed influence and the exclusions, and delivery records the real attachment order or board placement, so the saved request describes what the target actually received. A hidden limb is still a limb, and an expression in a reference stays a moment rather than a trait. A reference can also carry derived visual evidence: which source was inspected, what was measured and what the measurement can show. See the [reference runtime](references/runtime/reference-prompt-artifacts.md) and [Derived Visual Evidence](references/derived-visual-evidence.md).

## Review and evidence

### Review actual results

A production review records what was seen, where, how it was interpreted and what remains uncertain. A failed hard criterion blocks selection, and a changed image or task gets its own review. The HTML review export puts the recorded inputs, the exact input the generator received, every returned image, the observations and the selection reasons on one page. [Evidence Review](references/runtime/evidence-review.md) explains the export and the optional study built on it.

### Investigate repeated failures

A repair names the observed problem, the proposed change and the requirements that stay fixed. When failures repeat, [Repair Analysis](references/runtime/repair-analysis.md) groups them across runs by the criterion's actual definition and writes a readable report: whether the source run is current, its review record, the cited observations with their locations, and the reviewer's reason. A cause hypothesis carries its evidence, alternatives, protected requirements, scope and acceptance checks, and stays a proposal until a review confirms it.

### Evaluate an explicitly selected agent

The optional [Agent Evaluation](references/runtime/agent-evaluation.md) runner executes a host command you select and keeps the prompt, inputs, logs, timing and outputs. Three results are judged separately: whether the process ran, whether the evidence is complete, and how good the expression is. A missing output or a truncated log makes the trial incomplete whatever the exit code, and expressive quality waits for a human review. The runner gives each trial a fresh directory, not a sandbox: run trusted commands and account for their permissions and costs.

### Exchange public artifacts

Optional exchange uses public artifact schemas, content hashes and declared semantics, so another tool can accept a snapshot without reading this product's private directories. Export the constructed scene material from the example above:

<!-- readme-example: public-exchange -->
```sh
python scripts/protocol_exchange.py export --root ../cpb-authoring-demo --artifact scene-material/material.json --out public-exchange
python scripts/protocol_exchange.py verify --root ../cpb-authoring-demo --bundle public-exchange
```
<!-- end-readme-example -->

A receiver validates the snapshot and accepts it explicitly. Incoming paths are provenance labels.

## Project data

### Content packs

Persistent pack selection lives in user-level state:

```sh
python scripts/pack_cli.py ready
python scripts/pack_cli.py list
```

Use explicit `--state-file`, `--cache-dir` and `--managed-root` locations to isolate a project or a test, and enable an additional pack by its discovered UUID. A missing model or vocabulary record usually means the pack is disabled or its provider unresolved; `ready` names both. [Content Packs](PACKS.md) explains activation and resource providers; the core ships the minimal [commons pack](packs/commons/).

### Complete material and explicit budgets

A project is valid however long its sources are. Originals are kept in full, scene documents contain the definition text itself, and evaluation logs are retained whole. Where you set an explicit budget and the material exceeds it, the tool reports the conflict and stops; where a real limit such as memory, storage or a service quota is hit, it reports that limit. [Resource handling](references/resource-handling.md) lists the operator options and separates content limits from format rules and working buffers.

### Project files

Keep projects and generated outputs outside the installed skill folder. Pack activation and personal packs live under `~/.character-prompt-builder/` and survive skill updates. This command creates a personal pack and enables it:

```sh
python scripts/pack_cli.py init ~/.character-prompt-builder/packs/NAME --name "NAME"
```

## Troubleshooting

**Scene material no longer verifies.** A source changed. Return to the complete originals and the scene's intended scope, review the changed definitions and rebuild the material.

**Sending is refused.** Check the prepared run, the exact approval, the service configuration and the credentials. The operation, input, output count and cost must fit the approval; `--send` alone approves nothing. An unknown remote result needs investigation before a new submission.

**Catalog resources are missing.** Check discovered packs, enabled UUIDs and which pack supplies the missing resource. A folder on disk is active only once its pack is enabled.

**Visual preflight fails.** Install and check the named dependencies with the interpreter that runs the tools. Cairo and fonts may need native installation. Authoring keeps working while visual inspection waits.

## Validation

The README smoke test runs the offline examples above in temporary directories, checks the local links and checks the live command signatures without contacting a service. The repository diagnostic covers structure, files, hashes, recorded state, authority, packaging and the executable workflows, and needs the release dependencies.

```sh
python scripts/readme_smoke_test.py
python scripts/validate.py .
```

The [state-aware pilot](examples/state-aware-pilot/README.md) exercises recorded state, projection, a production specification and exact reference preparation as a deterministic structural example. [CONTRIBUTING.md](CONTRIBUTING.md) has the development and release procedures.

## Scope and limitations

The tools preserve declared inputs and evidence. Whether a source was understood, whether an omitted condition matters and whether an image succeeds artistically are judged by people, on the actual result. A verified request improves the odds of recognizable identity, correct anatomy and legible detail in the generated pixels without guaranteeing them. The [Blind Image Evaluation Protocol](references/blind-image-evaluation-protocol.md) describes a separate image-quality study.

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md) explains how to prepare a development checkout, run the checks and build a release. A contribution states the intended behavior, updates the documentation for it and adds a test that fails on the defect it addresses. Gates stay as they are, project data and credentials stay out of the product, and pack contributions follow the ownership and validation rules in [Content Packs](PACKS.md).

## Release management

Releases use the CalVer scheme `YYYY.MM.DD.N` in UTC. [package-manifest.toml](package-manifest.toml) owns the release identity, and the generated host and Python distribution metadata are checked against it. [CHANGELOG.md](CHANGELOG.md) records each release under its version heading. Release commands and tag checks are in [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Character Prompt Builder is free software under the GNU GPLv3. The full text is in [LICENSE](LICENSE).

## Support

If this project is useful, you can support its development.

- GitHub Sponsors https://github.com/sponsors/livingghost
