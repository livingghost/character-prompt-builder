# Upscale Adapter

## Purpose and controls

Use a model record with `operation_kind=upscale`. Upscaling has an explicit input-image contract and produces an Upscale Package; it is not a text-to-image prompt transport.

Restorative upscalers prioritize existing geometry and palette but need not preserve every pixel. Generative and creative upscalers can reinterpret detail and require a separate identity audit before canonical use. Use only the selected record's scale factors, declared settings and supported guidance. Provider descriptions are not measurements of the output.

## Prepare the exact input

Copy the source image into the studio. Read the selected model, service guidance, execution profile and validation evidence. `production_binding.py` writes the explicit input declaration from real source bytes, rendering intent and request validation; it grants no execution authority.

```sh
python scripts/production_binding.py --root STUDIO --source images/input.png --model MODEL_ID --scale 2 --settings-file settings.json --render-intent render-intent.json --request-validation-file validation.json --out upscale-input.json
```

The Production task uses route `upscale`, artifact `image`, execution `dispatcher`, and an authored-rendition delivery whose `path` is `upscale-input.json`. Declare `upscale.service`, `upscale.cost`, and the same `recording` contract as any other image task. The source image and validation evidence are captured; the original image is never uploaded directly after preparation. A sheet slot requires an explicit single-subject map and `sheet_panel=true`. Do not add a text-to-image `generation` block to an upscale task.

```sh
python scripts/production_workflow.py prepare --root STUDIO --task upscale-task.json
python scripts/production_workflow.py draft-execution --root STUDIO --run RUN_ID --grant GRANT_ID --out execution-decisions.json
python scripts/production_workflow.py execute --root STUDIO --run RUN_ID --decisions-file execution-decisions.json
python scripts/production_workflow.py resume --root STUDIO --run RUN_ID
```

Fill the decision file from actual approval or an applicable delegation after inspecting the prepared request. Execution uses the common authority transaction, execution claim, upload and send boundary. One upscale requests one output. Partial acquisition remains visible and can be resumed from the retained answer; an unknown remote outcome is not an instruction to resend.

`repeat` prepares another run for the same input. `variant` accepts the compiler-declared `upscale-input` field as a file reference to an explicitly revised declaration, or a complete `recording` contract. It checks source content, rendering intent, scale, settings, validation evidence and affected dependencies again. It inherits no receipt, claim, review or adoption.

`dispatch.py --upscale` previews the upscale run of the studio's open task and sends nothing. It takes the same declaration fields and `--settings-file`, and refuses any that differ from the prepared declaration. `execute` sends the run; the preview is no alternate authority or recovery mechanism.

## Results, review and external work

The stored Upscale Package binds source and output paths, media hashes, dimensions, selected model record, factor, settings and audit. Verify actual files from disk. A returned image remains a candidate, not selected character canon. Compare generative and creative results with the Character Census; require explicit review and separate adoption for permanent changes.

For an upscaler with no transport, perform the separately authorized external operation and use `build_upscale_package.py` and `verify_upscale_package.py` on its real source/output files. Record external provenance with Studio rather than inventing a dispatcher run.

The executable local example is in [Generation examples](../../examples/generation/README.md); the common lifecycle is in [Production execution](../runtime/production-execution.md).
