#!/usr/bin/env python3
"""Verify declared Character Prompt Builder dependency profiles."""
from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import sysconfig
import tomllib
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "requirements-core.txt"
VISUAL = ROOT / "requirements-visual.txt"
SUPPORTED = ROOT / "requirements.txt"
TESTED = ROOT / "requirements-tested.txt"
PYPROJECT = ROOT / "pyproject.toml"

REQUIREMENT_RE = re.compile(
    r"^([A-Za-z0-9_.-]+)(?:(==|>=)([0-9]+(?:\.[0-9]+)*)(?:,<([0-9]+(?:\.[0-9]+)*))?)$"
)
IMPORT_NAMES = {
    "CairoSVG": "cairosvg",
    "numpy": "numpy",
    "Pillow": "PIL",
    "rasterio": "rasterio",
    "opencv-python-headless": "cv2",
    "scikit-image": "skimage",
}
PROFILE_PATHS = {
    "core": CORE,
    "visual": VISUAL,
    "full": SUPPORTED,
    "tested": TESTED,
}
PROFILE_EXPECTED = {
    "core": frozenset(),
    "visual": frozenset(IMPORT_NAMES),
    "full": frozenset(IMPORT_NAMES),
    "tested": frozenset(IMPORT_NAMES),
}

PROFILE_CHECK_COMMANDS = {
    "core": "python scripts/check_dependencies.py --profile core",
    "visual": "python scripts/check_dependencies.py --profile visual",
    "full": "python scripts/check_dependencies.py --profile full",
    "tested": "python scripts/check_dependencies.py --tested",
}
INSTALLABLE_PROFILES = frozenset({"visual", "full", "tested"})


def externally_managed() -> bool:
    """Whether the system owns the running Python's packages (PEP 668), so pip refuses to install into it."""
    if sys.prefix != sys.base_prefix:
        return False
    return (Path(sysconfig.get_path("stdlib")) / "EXTERNALLY-MANAGED").is_file()


def install_command(profile: str) -> tuple[str | None, str | None]:
    """The command that installs a profile into the Python running this check, or the reason there is none.

    pip installs where this Python has it. A virtual environment that uv creates has no pip,
    so uv installs into it.
    """
    if profile not in INSTALLABLE_PROFILES:
        return None, None
    if externally_managed():
        return None, ("the system manages this Python's packages (PEP 668); create a virtual environment "
                      "with python -m venv DIR or uv venv DIR, then run this check with that environment's Python")
    requirements = str(PROFILE_PATHS[profile])
    if importlib.util.find_spec("pip") is not None:
        command = [sys.executable, "-m", "pip", "install", "-r", requirements]
    elif shutil.which("uv") is not None:
        command = ["uv", "pip", "install", "--python", sys.executable, "-r", requirements]
    else:
        return None, ("this Python has no pip and uv is not on the executable search path; "
                      "install pip for it, or use a virtual environment")
    return (subprocess.list2cmdline(command) if os.name == "nt" else shlex.join(command)), None


def version_tuple(value: str) -> tuple[int, ...]:
    match = re.match(r"^[0-9]+(?:\.[0-9]+)*", value)
    if not match:
        raise ValueError(f"unsupported nonnumeric dependency version: {value!r}")
    return tuple(int(part) for part in match.group(0).split("."))


def load_requirements(path: Path, *, allow_empty: bool = False) -> list[dict[str, str | None]]:
    rows: list[dict[str, str | None]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = REQUIREMENT_RE.fullmatch(line)
        if not match:
            raise ValueError(f"{path.name}:{line_number}: unsupported dependency expression {line!r}")
        name, operator, lower, upper = match.groups()
        if operator == "==" and upper is not None:
            raise ValueError(f"{path.name}:{line_number}: exact pin cannot have an upper bound")
        rows.append({"distribution": name, "operator": operator, "lower": lower, "upper": upper})
    if not rows and not allow_empty:
        raise ValueError(f"{path.name}: no dependencies declared")
    names = [str(row["distribution"]).casefold() for row in rows]
    if len(names) != len(set(names)):
        raise ValueError(f"{path.name}: duplicate dependency declaration")
    return rows


def satisfies(installed: str, row: dict[str, str | None]) -> bool:
    current = version_tuple(installed)
    lower = version_tuple(str(row["lower"]))
    if row["operator"] == "==":
        return current == lower
    if current < lower:
        return False
    upper_raw = row.get("upper")
    return upper_raw is None or current < version_tuple(str(upper_raw))


def normalized_expression(row: dict[str, str | None]) -> str:
    name = str(row["distribution"])
    if row["operator"] == "==":
        return f"{name}=={row['lower']}"
    value = f"{name}>={row['lower']}"
    if row.get("upper"):
        value += f",<{row['upper']}"
    return value


def _pyproject_lists() -> tuple[list[str], dict[str, list[str]]]:
    with PYPROJECT.open("rb") as stream:
        data = tomllib.load(stream)
    project = data.get("project") or {}
    base = [str(value) for value in project.get("dependencies") or []]
    optional = {
        str(name): [str(value) for value in values or []]
        for name, values in (project.get("optional-dependencies") or {}).items()
    }
    return base, optional


def _definition_for(path: Path) -> str:
    resolved = path.resolve()
    for name, candidate in PROFILE_PATHS.items():
        if candidate.resolve() == resolved:
            return name
    return "custom"


def functional_checks(modules: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    try:
        np = modules["numpy"]
        image_module = importlib.import_module("PIL.Image")
        pixels = np.zeros((2, 2, 4), dtype=np.uint8)
        pixels[:, :, 3] = 255
        image = image_module.fromarray(pixels, "RGBA")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        if not buffer.getvalue().startswith(b"\x89PNG"):
            errors.append("Pillow and NumPy PNG smoke check returned invalid data")
    except Exception as exc:
        errors.append(f"Pillow and NumPy functional check failed: {exc}")

    try:
        rendered = modules["CairoSVG"].svg2png(
            bytestring=(
                b'<svg xmlns="http://www.w3.org/2000/svg" width="2" height="2">'
                b'<path d="M0 0H2V2H0Z" fill="#000"/></svg>'
            )
        )
        if not rendered.startswith(b"\x89PNG"):
            errors.append("CairoSVG smoke check returned invalid PNG data")
    except Exception as exc:
        errors.append(f"CairoSVG functional check failed: {exc}")

    try:
        np = modules["numpy"]
        features = importlib.import_module("rasterio.features")
        labels = np.array([[1, 1], [0, 0]], dtype=np.int16)
        if not list(features.shapes(labels, connectivity=4)):
            errors.append("Rasterio connected-region smoke check returned no shapes")
    except Exception as exc:
        errors.append(f"Rasterio functional check failed: {exc}")

    try:
        cv2 = modules["opencv-python-headless"]
        np = modules["numpy"]
        sample = np.zeros((4, 4, 3), dtype=np.uint8)
        if cv2.cvtColor(sample, cv2.COLOR_RGB2GRAY).shape != (4, 4):
            errors.append("OpenCV color conversion smoke check returned an unexpected shape")
    except Exception as exc:
        errors.append(f"OpenCV functional check failed: {exc}")

    try:
        metrics = importlib.import_module("skimage.metrics")
        np = modules["numpy"]
        sample = np.zeros((8, 8), dtype=np.uint8)
        if float(metrics.structural_similarity(sample, sample, data_range=255)) != 1.0:
            errors.append("scikit-image SSIM smoke check did not return 1.0 for identical arrays")
    except Exception as exc:
        errors.append(f"scikit-image functional check failed: {exc}")
    return errors


def check(requirements_path: Path = CORE) -> dict[str, Any]:
    requirements_path = Path(requirements_path)
    profile = _definition_for(requirements_path)
    errors: list[str] = []
    modules: dict[str, Any] = {}
    results: list[dict[str, Any]] = []
    if sys.version_info < (3, 11):
        errors.append("Python 3.11 or newer is required")

    try:
        requirements = load_requirements(requirements_path, allow_empty=(profile == "core"))
    except Exception as exc:
        return {
            "ok": False,
            "python": sys.version.split()[0],
            "profile": profile,
            "definition": requirements_path.name,
            "dependencies": [],
            "errors": [str(exc)],
        }

    declared = frozenset(str(row["distribution"]) for row in requirements)
    expected = PROFILE_EXPECTED.get(profile)
    if expected is not None and declared != expected:
        errors.append(
            f"{requirements_path.name} must declare exactly: "
            + (", ".join(sorted(expected)) if expected else "no third-party packages")
        )

    try:
        base, optional = _pyproject_lists()
        if base:
            errors.append("pyproject.toml project.dependencies must be empty for the Core profile")
        visual_rows = load_requirements(VISUAL)
        visual_expected = sorted((normalized_expression(row) for row in visual_rows), key=str.casefold)
        if sorted(optional.get("visual", []), key=str.casefold) != visual_expected:
            errors.append("pyproject.toml optional-dependencies.visual must match requirements-visual.txt")
        if sorted(optional.get("all", []), key=str.casefold) != visual_expected:
            errors.append("pyproject.toml optional-dependencies.all must match requirements-visual.txt")
        full_rows = load_requirements(SUPPORTED)
        if sorted((normalized_expression(row) for row in full_rows), key=str.casefold) != visual_expected:
            errors.append("requirements.txt must match requirements-visual.txt")
    except Exception as exc:
        errors.append(f"cannot validate dependency definitions: {exc}")

    for row in requirements:
        distribution = str(row["distribution"])
        import_name = IMPORT_NAMES.get(distribution)
        result: dict[str, Any] = {
            "distribution": distribution,
            "constraint": (
                f"=={row['lower']}" if row["operator"] == "=="
                else f">={row['lower']}" + (f",<{row['upper']}" if row.get("upper") else "")
            ),
            "installed": None,
            "import_name": import_name,
            "import_ok": False,
            "constraint_ok": False,
        }
        try:
            installed = importlib.metadata.version(distribution)
            result["installed"] = installed
            result["constraint_ok"] = satisfies(installed, row)
            if not result["constraint_ok"]:
                errors.append(f"{distribution} {installed} does not satisfy {result['constraint']}")
        except importlib.metadata.PackageNotFoundError:
            errors.append(f"{distribution} is not installed")
        if import_name:
            try:
                modules[distribution] = importlib.import_module(import_name)
                result["import_ok"] = True
            except Exception as exc:
                errors.append(f"cannot import {import_name} for {distribution}: {exc}")
        results.append(result)

    if declared == frozenset(IMPORT_NAMES) and all(name in modules for name in IMPORT_NAMES):
        errors.extend(functional_checks(modules))

    return {
        "ok": not errors,
        "python": sys.version.split()[0],
        "profile": profile,
        "definition": requirements_path.name,
        "dependencies": results,
        "errors": errors,
    }


def check_profile(profile: str) -> dict[str, Any]:
    """Return an actionable dependency report for one declared profile."""

    if profile not in PROFILE_PATHS:
        raise ValueError(f"unknown dependency profile: {profile!r}")
    report = check(PROFILE_PATHS[profile])
    dependencies = report.get("dependencies") or []
    missing = sorted(
        str(row.get("distribution"))
        for row in dependencies
        if isinstance(row, dict) and row.get("installed") is None
    )
    incompatible = sorted(
        str(row.get("distribution"))
        for row in dependencies
        if isinstance(row, dict)
        and row.get("installed") is not None
        and row.get("constraint_ok") is not True
    )
    command, note = install_command(profile)
    return {
        **report,
        "check_command": PROFILE_CHECK_COMMANDS[profile],
        "install_command": command,
        **({"install_note": note} if note else {}),
        "missing_packages": missing,
        "incompatible_packages": incompatible,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("core", "visual", "full"),
        default="core",
        help="dependency surface to verify; Core is standard-library only",
    )
    parser.add_argument(
        "--tested",
        action="store_true",
        help="verify the exact full release-validation pins",
    )
    args = parser.parse_args(argv)
    profile = "tested" if args.tested else args.profile
    report = check_profile(profile)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
