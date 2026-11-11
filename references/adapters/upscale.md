# Upscale Adapter

## Purpose and controls

Use a model record with `operation_kind=upscale`. Upscaling has an explicit input-image contract and produces an Upscale Package; it is not a text-to-image prompt transport.

Restorative upscalers prioritize existing geometry and palette but need not preserve every pixel. Generative and creative upscalers can reinterpret detail and require a separate identity audit before canonical use. Use only the selected record's scale factors, declared settings and supported guidance. Provider descriptions are not measurements of the output.

## Prepare the exact input

Start through the common editable inputs. Select a real local image, the requested
factor and the actual purpose. An absolute image outside the Studio is copied
without changing its bytes; a selected Studio image keeps its existing path.
The purpose initializes unanswered direction and independent criteria. Existing
criteria and authority remain in place. When no work task is open, this explicit
purpose opens one once the draft is produced; an existing task continues with
its identity. A refused command opens no work.

```sh
python scripts/production_workflow.py draft-inputs --root STUDIO --route upscale --source-image /absolute/path/input.png --scale 4 --purpose "Enlarge this image four times for the requested delivery." --model MODEL_ID --service SERVICE_ID --out-dir work/upscale
```

Follow its actual `next_actions`: read the selected contract and model guidance,
fill unanswered choices, then prepare the same choices file. A plain enlargement
needs no new subject, medium, framing, prompt or set of creative alternatives.
An operation-only render intent is sufficient when the model owns rendering.
Respect actual source preservation requirements and the selected model's
supported controls. Never infer an API factor enum from a model's native scale.

Inspect candidates with `render_contract.py models --operation upscale`; each
candidate exposes its evidence readiness and its inspection command. This view
does not validate an unsent request. Missing provider evidence has to be acquired
or covered by an applicable explicit validation strategy before preparation.

`prepare --choices work/upscale/choices.json` builds the exact input. The lower
level declaration writer below is also available for an already authored task;
it grants no execution authority.

```sh
python scripts/production_binding.py --root STUDIO --source images/input.png --model MODEL_ID --scale 2 --settings-file settings.json --render-intent render-intent.json --request-validation-file validation.json --out upscale-input.json
```

The Production task uses route `upscale`, artifact `image`, execution `dispatcher`, and an authored-rendition delivery whose `path` is `upscale-input.json`. Declare `upscale.service`, `upscale.cost`, and the same `recording` contract as any other image task. The source image and validation evidence are captured; the original image is never uploaded directly after preparation. A sheet slot requires an explicit single-subject map and `sheet_panel=true`. Do not add a text-to-image `generation` block to an upscale task.

```sh
python scripts/production_workflow.py prepare --root STUDIO --task upscale-task.json
python scripts/production_workflow.py draft-execution --root STUDIO --run RUN_ID --out execution-decisions.json
python scripts/production_workflow.py execute --root STUDIO --run RUN_ID --decisions-file execution-decisions.json
python scripts/production_workflow.py resume --root STUDIO --run RUN_ID
```

Fill the decision file from actual approval or an applicable delegation after inspecting the prepared request. Execution uses the common authority transaction, execution claim, upload and send boundary. One upscale requests one output. Partial acquisition remains visible and can be resumed from the retained answer; an unknown remote outcome is not an instruction to resend.

The draft response shows required operations and targets, eligible grants, current
authority and its update action. The named file holds editable decisions only.
Use that same file after resuming; its location is registered even when it is
outside the standard decisions directory. The unapproved request-scope template
describes the prepared request but supplies no approval or delegation itself.

For a model change, reopen with `draft-inputs --from-run RUN_ID --model MODEL_ID`
and the selected service. Follow the returned `retarget` action and supply the
actual reason. The new run preserves its parent, source image and applicable
criteria. Reopening edited choices recomputes the action from the current target.

`repeat` prepares another run for the same input. `variant` accepts the compiler-declared `upscale-input` field as a file reference to an explicitly revised declaration, or a complete `recording` contract. It checks source content, rendering intent, scale, settings, validation evidence and affected dependencies again. It inherits no receipt, claim, review or adoption.

`dispatch.py --upscale` previews the upscale run of the studio's open task and sends nothing. It takes the same declaration fields and `--settings-file`, and refuses any that differ from the prepared declaration. `execute` sends the run; the preview is no alternate authority or recovery mechanism.

## Results, review and external work

The stored Upscale Package binds source and output paths, media hashes, dimensions, selected model record, factor, settings and audit. Verify actual files from disk. A returned image remains a candidate, not selected character canon. Compare generative and creative results with the Character Census; require explicit review and separate adoption for permanent changes.

For an upscaler with no transport, perform the separately authorized external operation and use `build_upscale_package.py` and `verify_upscale_package.py` on its real source/output files. Record external provenance with Studio rather than inventing a dispatcher run.

The executable local example is in [Generation examples](../../examples/generation/README.md); the common lifecycle is in [Production execution](../runtime/production-execution.md).
