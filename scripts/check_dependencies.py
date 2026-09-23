#!/usr/bin/env python3
"""Check a Character Prompt Builder dependency profile and print the commands that install it.

The check describes the Python running it, or the virtual environment that --venv names.
--install runs the printed commands once the user confirms them, then checks again with
the Python that received the packages.
"""
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
    "resvg-py": "resvg_py",
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

PROFILE_ARGUMENTS = {
    "core": ("--profile", "core"),
    "visual": ("--profile", "visual"),
    "full": ("--profile", "full"),
    "tested": ("--tested",),
}
PROFILE_CHECK_COMMANDS = {
    profile: " ".join(("python", "scripts/check_dependencies.py", *arguments))
    for profile, arguments in PROFILE_ARGUMENTS.items()
}
INSTALLABLE_PROFILES = frozenset({"visual", "full", "tested"})
# Each profile that reports ffprobe, and whether it requires it.
FFPROBE_REQUIRED = {"visual": False, "full": False, "tested": True}
FFPROBE_ENABLES = "measured audio and video streams in temporal production evidence"
REPORT_FIELDS = ("ok", "python", "profile", "definition", "dependencies", "errors")
HAS_PIP = "import importlib.util, sys; sys.exit(importlib.util.find_spec('pip') is None)"


def shown(command: Sequence[str]) -> str:
    """One command as this platform's shell reads it."""
    return subprocess.list2cmdline(list(command)) if os.name == "nt" else shlex.join(command)


def externally_managed() -> bool:
    """Whether the system owns the running Python's packages (PEP 668), so pip refuses to install into it."""
    if sys.prefix != sys.base_prefix:
        return False
    return (Path(sysconfig.get_path("stdlib")) / "EXTERNALLY-MANAGED").is_file()


def environment_python(venv: Path) -> Path:
    """The interpreter inside the virtual environment at venv."""
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def is_environment(venv: Path) -> bool:
    return (venv / "pyvenv.cfg").is_file()


def runs_pip(python: str) -> bool:
    """Whether the interpreter at python can import pip."""
    try:
        return subprocess.run([python, "-c", HAS_PIP], capture_output=True, check=False).returncode == 0
    except OSError:
        return False


def install_plan(profile: str, venv: Path | None = None) -> tuple[list[list[str]], str | None]:
    """The commands that install a profile, in order, or the reason there are none.

    The target is the Python running this check, or the virtual environment at venv, which
    the first command creates when it is absent. pip installs where the target has it, and uv
    installs into an environment without pip.
    """
    if profile not in INSTALLABLE_PROFILES:
        return [], None
    create: list[list[str]] = []
    if venv is None:
        if externally_managed():
            return [], ("the system manages this Python's packages (PEP 668); pass --venv DIR to create "
                        "a virtual environment at DIR and install into it")
        python = sys.executable
        has_pip = importlib.util.find_spec("pip") is not None
    else:
        python = str(environment_python(venv))
        if is_environment(venv):
            has_pip = runs_pip(python)
        elif venv.exists() and (not venv.is_dir() or any(venv.iterdir())):
            return [], f"{venv} holds no virtual environment and is not an empty directory"
        elif importlib.util.find_spec("venv") is not None and importlib.util.find_spec("ensurepip") is not None:
            create = [[sys.executable, "-m", "venv", str(venv)]]
            has_pip = True
        elif shutil.which("uv") is not None:
            create = [["uv", "venv", "--python", sys.executable, str(venv)]]
            has_pip = False
        else:
            return [], ("this Python cannot create a virtual environment with pip, and uv is not on the "
                        "executable search path; install uv, or run this check with another Python")
    requirements = str(PROFILE_PATHS[profile])
    if has_pip:
        install = [python, "-m", "pip", "install", "-r", requirements]
    elif shutil.which("uv") is not None:
        install = ["uv", "pip", "install", "--python", python, "-r", requirements]
    else:
        return [], (f"{python} has no pip and uv is not on the executable search path; install pip or uv"
                    + (", or pass --venv DIR" if venv is None else ""))
    return [*create, install], None


def install_command(profile: str, venv: Path | None = None) -> tuple[str | None, str | None]:
    """The command that installs a profile's packages, or the reason there is none."""
    commands, note = install_plan(profile, venv)
    return (shown(commands[-1]) if commands else None), note


def ffmpeg_install_command(platform: str | None = None) -> tuple[list[str] | None, str | None]:
    """The first package manager on the executable search path that installs FFmpeg, or why there is none.

    A Linux package manager runs through sudo unless the check already runs as root.
    """
    platform = platform or sys.platform
    if platform == "win32":
        candidates = [["winget", "install", "--exact", "--id", "Gyan.FFmpeg"], ["choco", "install", "ffmpeg", "-y"]]
    elif platform == "darwin":
        candidates = [["brew", "install", "ffmpeg"]]
    else:
        candidates = [
            ["apt-get", "install", "-y", "ffmpeg"],
            ["dnf", "install", "-y", "ffmpeg-free"],
            ["pacman", "-S", "--noconfirm", "ffmpeg"],
            ["apk", "add", "ffmpeg"],
        ]
    for command in candidates:
        if shutil.which(command[0]) is None:
            continue
        if platform not in {"win32", "darwin"} and getattr(os, "geteuid", lambda: 0)() != 0 and shutil.which("sudo"):
            return ["sudo", *command], None
        return command, None
    return None, "no known package manager is on the executable search path; install FFmpeg so ffprobe is on it"


def ffprobe_report(required: bool) -> dict[str, Any]:
    """Whether ffprobe from FFmpeg runs here, and the command that installs it when it does not."""
    path = shutil.which("ffprobe")
    version = None
    if path is not None:
        try:
            completed = subprocess.run(
                [path, "-version"], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False
            )
            if completed.returncode == 0:
                version = next(iter(completed.stdout.splitlines()), "").strip() or None
        except OSError:
            pass
    report: dict[str, Any] = {
        "required": required,
        "enables": FFPROBE_ENABLES,
        "path": path,
        "runs": version is not None,
        "version": version,
    }
    if version is None:
        command, note = ffmpeg_install_command()
        report["install_command"] = shown(command) if command else None
        if note:
            report["install_note"] = note
    return report


def with_ffprobe(report: dict[str, Any], profile: str) -> dict[str, Any]:
    """Add the ffprobe report for a profile; a profile that requires ffprobe fails where it does not run."""
    ffprobe = ffprobe_report(FFPROBE_REQUIRED[profile])
    if not ffprobe["required"] or ffprobe["runs"]:
        return {**report, "ffprobe": ffprobe}
    return {
        **report,
        "ok": False,
        "errors": [
            *(report.get("errors") or []),
            f"ffprobe from FFmpeg does not run; the {profile} profile needs it for {FFPROBE_ENABLES}",
        ],
        "ffprobe": ffprobe,
    }


def version_tuple(value: str) -> tuple[int, ...]:
    match = re.match(r"^[0-9]+(?:\.[0-9]+)*", value)
    if not match:
        raise ValueError(f"unsupported nonnumeric dependency version: {value!r}")
    return tuple(int(part) for part in match.group(0).split("."))


def load_requirements(path: Path, *, allow_empty: bool = False) -> list[dict[str, str | None]]:
    """Read a requirement file, following each `-r FILE` line to the file it names."""
    rows: list[dict[str, str | None]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        included = re.fullmatch(r"-r\s+(\S+)", line)
        if included:
            rows.extend(load_requirements(path.parent / included.group(1), allow_empty=True))
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


def constraint(row: dict[str, str | None]) -> str:
    if row["operator"] == "==":
        return f"=={row['lower']}"
    return f">={row['lower']}" + (f",<{row['upper']}" if row.get("upper") else "")


def _pyproject_dependencies() -> list[str]:
    with PYPROJECT.open("rb") as stream:
        data = tomllib.load(stream)
    return [str(value) for value in (data.get("project") or {}).get("dependencies") or []]


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
        rendered = modules["resvg-py"].svg_to_bytes(
            svg_string=(
                '<svg xmlns="http://www.w3.org/2000/svg" width="2" height="2">'
                '<path d="M0 0H2V2H0Z" fill="#000"/></svg>'
            ),
            skip_system_fonts=True,
        )
        if not rendered.startswith(b"\x89PNG"):
            errors.append("resvg-py smoke check returned invalid PNG data")
    except Exception as exc:
        errors.append(f"resvg-py functional check failed: {exc}")

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
        if _pyproject_dependencies():
            errors.append("pyproject.toml project.dependencies must be empty for the Core profile")
        if profile == "tested":
            ranges = {str(row["distribution"]).casefold(): row for row in load_requirements(VISUAL)}
            for row in requirements:
                supported = ranges.get(str(row["distribution"]).casefold())
                if row["operator"] != "==":
                    errors.append(f"{requirements_path.name} must pin {row['distribution']} to one version with ==")
                elif supported is not None and not satisfies(str(row["lower"]), supported):
                    errors.append(
                        f"{row['distribution']}=={row['lower']} is outside the range {VISUAL.name} declares, "
                        f"{constraint(supported)}"
                    )
    except Exception as exc:
        errors.append(f"cannot validate dependency definitions: {exc}")

    for row in requirements:
        distribution = str(row["distribution"])
        import_name = IMPORT_NAMES.get(distribution)
        result: dict[str, Any] = {
            "distribution": distribution,
            "constraint": constraint(row),
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


def _failed_report(profile: str, error: str) -> dict[str, Any]:
    return {
        "ok": False,
        "python": None,
        "profile": profile,
        "definition": PROFILE_PATHS[profile].name,
        "dependencies": [],
        "errors": [error],
    }


def check_in(python: str, profile: str) -> dict[str, Any]:
    """Run this check in a new process of the interpreter at python and return its report."""
    command = [python, str(Path(__file__).resolve()), *PROFILE_ARGUMENTS[profile]]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=False)
    except OSError as exc:
        return _failed_report(profile, f"{shown(command)} could not start: {exc}")
    try:
        report = json.loads(completed.stdout)
        result = {field: report[field] for field in REPORT_FIELDS}
        if "ffprobe" in report:
            result["ffprobe"] = report["ffprobe"]
        return result
    except (ValueError, KeyError, TypeError):
        detail = completed.stderr.strip().splitlines()
        return _failed_report(
            profile,
            f"{shown(command)} exited with status {completed.returncode} and printed no report"
            + (f": {detail[-1]}" if detail else ""),
        )


def check_profile(
    profile: str,
    venv: Path | None = None,
    *,
    fresh: bool = False,
    plan: tuple[list[list[str]], str | None] | None = None,
) -> dict[str, Any]:
    """Return an actionable dependency report for one declared profile.

    The report describes the Python running this check, or the one in the virtual
    environment at venv. fresh checks the running Python in a new process, which sees
    packages installed after this process imported its modules.
    """

    if profile not in PROFILE_PATHS:
        raise ValueError(f"unknown dependency profile: {profile!r}")
    python = sys.executable if venv is None else str(environment_python(venv))
    if venv is None and not fresh:
        report = check(PROFILE_PATHS[profile])
    elif venv is not None and not is_environment(venv):
        report = _failed_report(profile, f"{venv} holds no virtual environment")
    else:
        report = check_in(python, profile)
    if "ffprobe" not in report and profile in FFPROBE_REQUIRED:
        report = with_ffprobe(report, profile)
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
    commands, note = install_plan(profile, venv) if plan is None else plan
    return {
        **report,
        "executable": python,
        "check_command": PROFILE_CHECK_COMMANDS[profile] + ("" if venv is None else f" --venv {shown([str(venv)])}"),
        **({"venv_command": shown(commands[0])} if len(commands) > 1 else {}),
        "install_command": shown(commands[-1]) if commands else None,
        **({"install_note": note} if note else {}),
        "missing_packages": missing,
        "incompatible_packages": incompatible,
    }


def pending_commands(report: dict[str, Any], plan: tuple[list[list[str]], str | None]) -> list[list[str]]:
    """The commands --install runs for a report.

    The package commands run when a package is missing, out of range or fails to import.
    The FFmpeg command runs when the profile requires ffprobe and it does not run.
    """
    rows = report.get("dependencies") or []
    commands: list[list[str]] = []
    if not rows or any(row.get("import_ok") is not True or row.get("constraint_ok") is not True for row in rows):
        commands.extend(plan[0])
    ffprobe = report.get("ffprobe")
    if ffprobe and ffprobe["required"] and not ffprobe["runs"]:
        command, _note = ffmpeg_install_command()
        if command:
            commands.append(command)
    return commands


def confirmation(commands: Sequence[Sequence[str]], *, yes: bool) -> str | None:
    """Return None once the user has confirmed the commands, or why --install runs nothing.

    --yes records a confirmation the user gave elsewhere. Without it, a terminal asks.
    """
    no_terminal = ("--install ran nothing: there is no terminal to confirm at; "
                   "pass --yes once the user has confirmed the printed commands")
    if yes:
        return None
    if sys.stdin is None or not sys.stdin.isatty():
        return no_terminal
    sys.stderr.write("".join(f"  {shown(command)}\n" for command in commands) + "Run these commands? [y/N] ")
    sys.stderr.flush()
    answer = sys.stdin.readline()
    if not answer:
        return no_terminal
    if answer.strip().casefold() in {"y", "yes"}:
        return None
    return "--install ran nothing: the user did not confirm the commands"


def run_commands(commands: Sequence[Sequence[str]]) -> tuple[list[str], str | None]:
    """Run the commands in order with their output on standard error, stopping at the first failure.

    Return the commands that ran and the failure, if any.
    """
    ran: list[str] = []
    for command in commands:
        ran.append(shown(command))
        sys.stderr.flush()
        try:
            status = subprocess.run(list(command), stdout=sys.stderr, check=False).returncode
        except OSError as exc:
            return ran, f"{shown(command)} could not start: {exc}"
        if status:
            return ran, f"{shown(command)} exited with status {status}"
    return ran, None


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
    parser.add_argument(
        "--venv",
        metavar="DIR",
        help="check the virtual environment at DIR; the printed commands create it when absent and install into it",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="run the printed commands once the user confirms them, then check again",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="the user has already confirmed the printed commands; --install then runs without asking",
    )
    args = parser.parse_args(argv)
    profile = "tested" if args.tested else args.profile
    if args.yes and not args.install:
        parser.error("--yes confirms --install; pass both")
    if (args.install or args.venv) and profile not in INSTALLABLE_PROFILES:
        parser.error("the core profile installs nothing")
    venv = Path(os.path.abspath(args.venv)) if args.venv else None
    plan = install_plan(profile, venv)
    report = check_profile(profile, venv, plan=plan)
    commands = pending_commands(report, plan) if args.install else []
    refusal = confirmation(commands, yes=args.yes) if commands else None
    if refusal:
        report["errors"].append(refusal)
    elif commands:
        ran, failure = run_commands(commands)
        report = {**check_profile(profile, venv, fresh=True), "install_ran": ran}
        if failure:
            report["ok"] = False
            report["errors"].append(failure)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
