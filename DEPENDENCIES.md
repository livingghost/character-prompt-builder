# Dependencies

Character Prompt Builder supports a standard-library Core runtime and an optional Visual profile. Python 3.11 or newer is required. Select dependencies from the operation being performed; do not install the largest profile by default.

## Profiles

| Profile | Definition | Direct third-party packages | Use |
| --- | --- | --- | --- |
| Core | [`requirements-core.txt`](requirements-core.txt) | none | prompt composition, pack catalog and cache, record inspection, asset discovery, reference-use planning, prompt-artifact and SVG-bundle delivery, state contracts, metadata and structural validation, stored-corpus hashes and SVG safety |
| Visual | [`requirements-visual.txt`](requirements-visual.txt) | resvg-py, NumPy, Pillow, rasterio, OpenCV, scikit-image | source-image extraction, vectorization, SVG-to-model rasterization, single-board construction, and perceptual fidelity computation |
| Unified | [`requirements.txt`](requirements.txt) | same direct set as Visual | one development environment with every distributed runtime feature |
| Tested | [`requirements-tested.txt`](requirements-tested.txt) | exact pins | complete core validation and publication |

Each supported version range is written once, in `requirements-visual.txt`. `requirements.txt` includes it, and the `visual` and `all` extras of [`pyproject.toml`](pyproject.toml) read it. Each exact pin is written once, in `requirements-tested.txt`, and the check requires it to lie inside that range.

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

Run only the applicable command. Without `--install` the check installs nothing. With `--install` it prints the commands that install what is missing, runs them once the user confirms, and checks again with the Python that received the packages:

- At a terminal, the check asks before it runs anything.
- Without a terminal, it runs only with `--yes`. An agent passes `--yes` after the user confirms the printed commands.
- The commands install into the Python that ran the check, through pip, or through `uv pip install --python` where that Python has no pip.
- A Python whose packages the system manages (PEP 668) gets nothing unless `--venv DIR` is given. The commands then create a virtual environment at DIR when it is absent, with `python -m venv`, or with `uv venv` where that Python cannot. Run the tools with that environment's Python.

If the user does not confirm, report the exact missing package and installation command, then stop. Never omit a selected reference, send raw SVG to a raster-only model, substitute another artifact, drop to text-only, or change transport silently.

The skill does not install Visual dependencies merely because it was activated. Prompt-artifacts and svg-bundle remain Core operations.

## Visual dependencies

| Distribution | Import | Purpose |
| --- | --- | --- |
| `resvg-py` | `resvg_py` | rasterize safe SVGs and character sheets to PNG for model transports and validation |
| `numpy` | `numpy` | native-dimension arrays, color quantization, and fidelity tests |
| `Pillow` | `PIL` | decode images, inspect dimensions, and convert RGBA data |
| `rasterio` | `rasterio` | connected color-area contours through `rasterio.features.shapes` |
| `opencv-python-headless` | `cv2` | filtering, whole-frame profiles, masks, edges, and audit projections |
| `scikit-image` | `skimage` | SSIM and CIEDE2000 measurements |
| FFmpeg, a system package | `ffprobe` on the executable search path | measured audio and video streams in temporal production evidence; the Tested profile requires it, and the Visual check reports it |

Where ffprobe does not run, the check prints the FFmpeg install command of the first package manager it finds: winget or choco on Windows, brew on macOS, and apt-get, dnf, pacman or apk on Linux. `--install` runs it for the Tested profile.

## Native library notes

The resvg-py wheel contains its renderer, so SVG rasterization needs no system library.

Character-sheet text uses the installed system fonts. Latin text takes the first installed family in the sheet's font list, and the render stops and prints that list when none is installed. Chinese, Japanese and Korean text needs an installed font that covers it; the render names any character no installed font prints.

Prefer a binary wheel for rasterio. Building it from source requires a compatible GDAL development environment and is outside the normal installation path.

On Windows, activate a virtual environment with `.venv\Scripts\activate`. On POSIX shells, use `. .venv/bin/activate`.

## Verification and changes

`scripts/check_dependencies.py` checks the selected definition, installed versions, imports, minimal functional operations and ffprobe. It emits JSON and exits nonzero when the environment is incomplete or inconsistent.

`scripts/validate_reference_corpus.py` validates an existing pack corpus under Core without reconstructing unavailable source rasters. It checks pack closure, corpus manifest, asset links, content hashes, SVG safety, bundle structure, and stored metric consistency. Source extraction, metric recomputation, and SVG rasterization require Visual.

For exact publication commands and smoke gates, follow [Release Validation](references/release/validation.md). A third-party import change updates `requirements-visual.txt`, `requirements-tested.txt`, this document and the checker's import names in one change. List transitive packages only when project code imports them directly.
