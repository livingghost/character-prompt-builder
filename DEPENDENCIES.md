# Dependencies

Character Prompt Builder uses one Python environment for the agent's runtime commands, image processing, repository checks and publication. Python 3.12 is the default selected by [`.python-version`](.python-version); [`pyproject.toml`](pyproject.toml) declares Python 3.12 or newer and the direct package versions.

## Dependency ownership

| File | Responsibility |
| --- | --- |
| [`pyproject.toml`](pyproject.toml) | supported Python minimum and exact versions of packages imported by project code |
| [`.python-version`](.python-version) | default interpreter selection for uv |
| [`uv.lock`](uv.lock) | uv's generated resolution of the complete package dependency graph, including exact versions and distribution hashes |
| [`requirements.txt`](requirements.txt) | uv's generated pip export of the same lock, including transitive packages and hashes |

Edit the project declarations when dependency policy changes. Generate the lock and its requirements export through uv. The export is an installation artifact; its package and hash entries are generated from the lock. [Release Validation](references/release/validation.md#publication-and-metadata) defines the update and verification sequence before release metadata is rebuilt.

## uv project environment

Install [uv](https://docs.astral.sh/uv/getting-started/installation/). From the directory holding `SKILL.md`, synchronize the environment and check it:

```bash
uv sync --locked
uv run --locked python scripts/check_dependencies.py
```

The host's session hook uses the same project environment. uv reads the default interpreter selection, installs the locked packages and runs the requested command. `--locked` reports stale project metadata instead of rewriting the lock during execution. Every runtime operation uses this environment.

When the agent is working in a Studio directory, retain that working directory and select the skill by its absolute installed path:

```bash
uv run --locked --project /absolute/path/to/character-prompt-builder python /absolute/path/to/character-prompt-builder/scripts/check_dependencies.py
```

Use that same project and absolute script paths for subsequent commands. `--project` selects the environment while keeping the current Studio directory. Child tools use the parent's `sys.executable`, so they retain the selected Python and packages. Commands documented with `python` assume this interpreter; an agent enters through `uv run --locked --project ...`, or uses the already selected interpreter for a child command.

By default uv creates `.venv` in the project. Set `UV_PROJECT_ENVIRONMENT` to an absolute directory to keep the environment elsewhere, and retain that setting for each `uv sync` and `uv run`. uv's environment and cache are local installation state. The complete skill files stay together beside `SKILL.md`.

Tools that install requirements files can use the generated `requirements.txt` with `python -m pip install -r requirements.txt`. It describes the same resolved packages. A Python whose packages the system manages needs a virtual environment; the dependency check reports that condition and supports `--venv DIR`.

## Environment check and installation

Run `python scripts/check_dependencies.py` with the selected environment's interpreter. It verifies Python, every declared direct version, imports, minimal functional operations, ffprobe and representative CJK font coverage. The report emits JSON and exits nonzero when the environment is incomplete or inconsistent. Before rendering CJK labels, add repeated `--sheet-text TEXT` arguments containing the actual labels.

Without `--install` the check installs nothing. With `--install` it prints the missing installation commands, runs them once the user confirms, and checks again with the Python that received the packages:

- At a terminal, the check asks before it runs anything.
- Without a terminal, it runs only with `--yes`. An agent passes `--yes` when the requested environment changes are already covered by the user's instruction or existing authorization. It asks for confirmation when the required change needs additional authority.
- Python package commands install the generated requirements into the Python that ran the check, through pip, or through `uv pip install --python` where that Python has no pip.
- A Python whose packages the system manages (PEP 668) gets nothing unless `--venv DIR` is given. The commands create a virtual environment at DIR when it is absent, with `python -m venv`, or with `uv venv` where that Python cannot. Run later tools with that environment's Python.

When an installation needs additional authority, report the missing prerequisite and the exact installation command that needs approval. Existing authorization continues to apply to the work it covers. Continue the affected operation once its environment check succeeds, preserving the selected sources, artifact and transport while resolving prerequisites.

## Packages and system prerequisites

| Distribution | Import | Purpose |
| --- | --- | --- |
| `resvg-py` | `resvg_py` | rasterize safe SVGs and character sheets to PNG for model transports and validation |
| `numpy` | `numpy` | native-dimension arrays, color quantization, and fidelity tests |
| `Pillow` | `PIL` | decode images, inspect dimensions, and convert RGBA data |
| `rasterio` | `rasterio` | connected color-area contours through `rasterio.features.shapes` |
| `opencv-python-headless` | `cv2` | filtering, whole-frame profiles, masks, edges, and audit projections |
| `scikit-image` | `skimage` | SSIM and CIEDE2000 measurements |
| FFmpeg, a system package | `ffprobe` on the executable search path | measured audio and video streams in temporal production evidence |

uv installs Python packages. FFmpeg and fonts are system prerequisites verified by the same environment check. Where ffprobe does not run, the check prints the FFmpeg install command of the first package manager it finds: winget or choco on Windows, brew on macOS, and apt-get, dnf, pacman or apk on Linux. `--install` runs that command after confirmation.

## Native library notes

The resvg-py wheel contains its renderer, so SVG rasterization needs no system library.

Character-sheet text uses the installed system fonts. Latin text takes the first installed family in the sheet's font list, and the render stops and prints that list when none is installed. Chinese, Japanese and Korean text needs an installed font that covers it; the render names any character no installed font prints.

The environment check verifies representative Chinese, Japanese and Korean text at both regular and bold weights, and also checks supplied `--sheet-text` labels. Its `sheet_fonts` report names the checked text, resolved files, missing characters and unavailable weights. It checks the selected Python environment, including when `--venv` is supplied. Coverage of those labels establishes nothing about characters that were not checked.

Font installation is a system-font operation. `--install` installs the declared Python packages and required FFmpeg, while the report explains any font requirement that remains. Install fonts covering the reported characters at both weights, then repeat the check; the renderer still checks each actual glyph during production.

Prefer a binary wheel for rasterio. Building it from source requires a compatible GDAL development environment and is outside the normal installation path.

On Windows, activate a project environment with `.venv\Scripts\activate`. On POSIX shells, use `. .venv/bin/activate`. The `uv run` entrypoint selects the environment directly.

## Verification and changes

`scripts/validate_reference_corpus.py` validates an existing pack corpus without reconstructing unavailable source rasters. It checks pack closure, corpus manifest, asset links, content hashes, SVG safety, bundle structure, and stored metric consistency. Source extraction, metric recomputation and SVG rasterization use the installed image-processing packages when those operations are requested.

Corpus validation uses the active catalog's resolved dependency roots, including packs stored in separate directories. The CLI accepts the complete pack-runtime selectors used by catalog commands. A positional pack without runtime selectors can still validate a standalone tree whose dependencies are siblings. The pack release gate passes its exact catalog to the corpus validator and preserves each detailed corpus error in its report.

For exact publication commands and smoke gates, follow [Release Validation](references/release/validation.md). A third-party import change updates `project.dependencies`, this document and the checker's import names in one change. Regenerate `uv.lock` and `requirements.txt`, verify the environment, then rebuild the release inventory. Keep transitive package choices in the generated lock and export.
