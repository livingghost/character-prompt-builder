# Dependencies

Character Prompt Builder supports a standard-library Core runtime and an optional Visual profile. Python 3.11 or newer is required. Select dependencies from the operation being performed; do not install the largest profile by default.

## Profiles

| Profile | Definition | Direct third-party packages | Use |
| --- | --- | --- | --- |
| Core | [`requirements-core.txt`](requirements-core.txt) | none | prompt composition, pack catalog and cache, record inspection, asset discovery, reference-use planning, prompt-artifact and SVG-bundle delivery, state contracts, metadata and structural validation, stored-corpus hashes and SVG safety |
| Visual | [`requirements-visual.txt`](requirements-visual.txt) | CairoSVG, NumPy, Pillow, rasterio, OpenCV, scikit-image | source-image extraction, vectorization, SVG-to-model rasterization, single-board construction, and perceptual fidelity computation |
| Unified | [`requirements.txt`](requirements.txt) | same direct set as Visual | one development environment with every distributed runtime feature |
| Tested | [`requirements-tested.txt`](requirements-tested.txt) | exact pins | complete core validation and publication |

[`pyproject.toml`](pyproject.toml) declares no mandatory third-party Core dependency and exposes matching `visual` and `all` extras. Extras describe runtime capabilities; they do not replace the exact Tested publication profile.

## Transport-triggered preflight

Choose the operation and reference transport first:

| Operation | Required profile |
| --- | --- |
| prompt only without references | Core |
| `prompt-artifacts` with existing SVG or raster sources | Core |
| `svg-bundle` | Core |
| SVG-to-PNG model transport | Visual |
| raster extraction or fidelity recomputation | Visual |
| `single-board` construction | Visual |
| full release validation and packaging | Tested |

Run the check immediately after the transport is known and before plan execution:

```bash
python scripts/check_dependencies.py --profile core
python scripts/check_dependencies.py --profile visual
```

Run only the applicable command. If Visual fails and the task authorizes environment mutation, run the `install_command` the check printed, then check again. It installs into the Python that ran the check: through pip where that Python has pip, and through `uv pip install --python` in an environment uv created, which has no pip.

If environment mutation is not authorized, report the exact missing package and installation command, then stop. Never omit a selected reference, send raw SVG to a raster-only model, substitute another artifact, drop to text-only, or change transport silently.

The skill does not install Visual dependencies merely because it was activated. Prompt-artifacts and svg-bundle remain Core operations.

## Visual dependencies

| Distribution | Import | Purpose |
| --- | --- | --- |
| `CairoSVG` | `cairosvg` | rasterize safe managed SVGs for model transports and validation |
| `numpy` | `numpy` | native-dimension arrays, color quantization, and fidelity tests |
| `Pillow` | `PIL` | decode images, inspect dimensions, and convert RGBA data |
| `rasterio` | `rasterio` | connected color-area contours through `rasterio.features.shapes` |
| `opencv-python-headless` | `cv2` | filtering, whole-frame profiles, masks, edges, and audit projections |
| `scikit-image` | `skimage` | SSIM and CIEDE2000 measurements |

## Native library notes

CairoSVG requires a working Cairo runtime loadable by `cairocffi`. Some Python distributions and operating systems supply it. If the checker reports that Cairo cannot load, install the platform Cairo runtime before retrying.

Prefer a binary wheel for rasterio. Building it from source requires a compatible GDAL development environment and is outside the normal installation path.

On Windows, activate a virtual environment with `.venv\Scripts\activate`. On POSIX shells, use `. .venv/bin/activate`.

## Verification and changes

`scripts/check_dependencies.py` validates the selected definition, matching `pyproject.toml` declaration, installed versions, imports, and minimal functional operations. It emits JSON and exits nonzero when the environment is incomplete or inconsistent.

`scripts/validate_reference_corpus.py` validates an existing pack corpus under Core without reconstructing unavailable source rasters. It checks pack closure, corpus manifest, asset links, content hashes, SVG safety, bundle structure, and stored metric consistency. Source extraction, metric recomputation, and SVG rasterization require Visual.

For exact publication commands and smoke gates, follow [Release Validation](references/release/validation.md). A third-party import change updates the relevant requirement profile, unified and tested definitions, `pyproject.toml`, this document, and the checker in one change. List transitive packages only when project code imports them directly.
