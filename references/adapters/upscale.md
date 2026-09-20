# Upscale Adapter

## Purpose

Use this adapter only for model records with `operation_kind=upscale`. Upscaling is a derived image operation, not a Generation Package prompt transport. It uses the dedicated Upscale Package contract.

## Upscaler classes

- **Restorative** upscalers minimize semantic reinterpretation and prioritize source geometry, palette relationships, and existing edge structure. They may still infer high-frequency detail and do not guarantee pixel identity.
- **Generative** upscalers reconstruct missing detail and may alter texture or local form.
- **Creative** upscalers intentionally permit broader reinterpretation guided by settings or an optional prompt.

Use only scale factors and settings declared by the active record. Do not invent a provider setting or assume that a setting shared by another model is accepted. A guidance prompt is valid only when `supports_guidance_prompt=true`. Negative transport does not apply to an Upscale Package.

## Committed operation

Build an Upscale Package containing the exact source and output paths, media types, SHA-256 values, dimensions, resolved upscaler identity, record hash, scale factor, settings, optional guidance prompt, and post-upscale identity audit. Generative and creative classes require that audit before the package becomes ready. A changed source, output, model record, factor, setting, or audit changes the package hash.

When the upscaler record carries an offering, the dispatcher performs the upscale and builds the package in the studio in one step, as [Image Generation Runtime](../runtime/image-generation.md) describes:

```bash
python scripts/dispatch.py --upscale --model <upscaler-id> --source <image> --scale <factor> --settings '{...}' --studio <dir> --character <id> --slot <slot> --production-root <dir> --production-run <run> --production-authorization <receipt> --send
```

For an upscaler with no offering, or an upscale performed on a host with no transport, build and verify the package with the dedicated entrypoints rather than a Generation Package command, then record the result with `scripts/studio.py iterate`:

```bash
python scripts/build_upscale_package.py --help
python scripts/verify_upscale_package.py --help
```

Use each command's declared arguments for the selected source image, output image, model record, factor, settings, and audit. Verification must read the committed package and files from disk; do not reconstruct their values from chat.

For canonical characters, compare the result against the Character Census after any generative or creative upscale. Reject shape drift, marking drift, altered silhouette, unintended material changes, or invented accessories.


For artifact capture and review, use [Production Execution](../runtime/production-execution.md).
Native upscale submission requires a prepared `upscale` route, `artifact: "image"`,
`execution: "dispatcher"` and a dispatcher handoff. Copy the source inside the project,
list it among the task sources, and write the exact input declaration:

```sh
python scripts/production_binding.py --root PROJECT --source images/input.png --model RESOLVED_MODEL --scale FACTOR --settings '{}' --out upscale-request.json
```

Use `upscale-request.json` as the task delivery. It fixes source hash, model, scale,
settings and guidance. A bound dry run shows the exact submission intent. Authorize
that intent with the selected grant and quoted cost, then provide the receipt to
`dispatch.py`. The dispatcher reserves one output before upload and records the
acquired result and generated Upscale Package before Studio recording. An unknown
remote result is not retried. `recover-recording` can restore fully acquired results
without a network call. Authored material and output selection remain separate.
