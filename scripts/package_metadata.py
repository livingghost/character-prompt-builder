#!/usr/bin/env python3
"""Load canonical package metadata from package-manifest.toml."""
from __future__ import annotations

import json
import os
import re
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
CALVER_RE = re.compile(
    r"^([0-9]{4})\.(0[1-9]|1[0-2])\.(0[1-9]|[12][0-9]|3[01])\.([1-9][0-9]*)$"
)
GENERATED_RELEASE_ARTIFACT_NAMES = frozenset(
    {
        "MANIFEST.json",
        "validation-report.json",
        "preset-authoring-audit.json",
        "style-family-audit.json",
        "sparse-discovery-report.json",
    }
)
DEVELOPMENT_ARTIFACT_SUFFIXES = frozenset(
    {".pyc", ".pyo", ".bak", ".orig", ".tmp"}
)
VCS_DIR_NAMES = frozenset({".git", ".hg", ".svn"})
CORE_EVALUATION_INCLUDES: frozenset[str] = frozenset()
# The declared retrieval contract for the bundled commons pack. It is core
# configuration, not an evaluation corpus, so it ships inside the whole-directory
# ``config`` include beside the pack state the suite runs against.
CORE_RELEASE_REGRESSION_CONTRACT = "config/default-release.json"
CORE_EXAMPLE_INCLUDES = frozenset(
    {"examples/render-contract", "examples/pack-authoring", "examples/feature-walkthrough", "examples/state-aware-pilot", "examples/declared-structures",
     "examples/authorial-intent", "examples/world-realization", "examples/production-execution", "examples/protocol-exchange", "examples/story-context", "examples/reusable-authoring",
     "examples/cast-admission", "examples/resume-recording", "examples/input-assembly", "examples/craft-consultation", "examples/model-evidence", "examples/candidate-recipe"}
)
CORE_PACK_INCLUDES = frozenset({"packs/commons"})
PACK_GITIGNORE_RULES = (
    "/packs/*",
    "!/packs/commons/",
    "!/packs/commons/**",
)
@dataclass(frozen=True)
class PackageMetadata:
    name: str
    version: str
    pyproject_version: str
    version_scheme: str
    release_timezone: str
    license_id: str
    description: str
    python_requirement: str
    core_requirements_file: str
    visual_requirements_file: str
    requirements_file: str
    tested_requirements_file: str
    pyproject_file: str
    release_output: str
    release_include: tuple[str, ...]
    release_exclude_names: tuple[str, ...]
    release_pack_dirs: tuple[str, ...]
    default_pack_ids: tuple[str, ...]
    default_resource_providers: tuple[tuple[str, str], ...]

    @property
    def resource_providers(self) -> dict[str, str]:
        return dict(self.default_resource_providers)

    @property
    def release_artifact_name(self) -> str:
        return PurePosixPath(self.release_output).name


def calver_key(value: object, *, field: str = "CalVer") -> tuple[int, int, int, int]:
    """Parse one canonical UTC Gregorian ``YYYY.MM.DD.N`` release value."""

    if not isinstance(value, str):
        raise ValueError(
            f"{field} must use canonical UTC Gregorian CalVer YYYY.MM.DD.N: {value!r}"
        )
    match = CALVER_RE.fullmatch(value)
    if not match:
        raise ValueError(
            f"{field} must use canonical UTC Gregorian CalVer YYYY.MM.DD.N "
            f"with N starting at 1: {value!r}"
        )
    year, month, day, revision = (int(part) for part in match.groups())
    try:
        date(year, month, day)
    except ValueError as exc:
        raise ValueError(f"{field} contains an invalid Gregorian date: {value!r}") from exc
    return year, month, day, revision


def pep440_version_for_calver(value: object, *, field: str = "CalVer") -> str:
    """Return the one normalized PEP 440 spelling of a core CalVer release."""

    return ".".join(str(part) for part in calver_key(value, field=field))


def _yaml_printable_code_point(code_point: int) -> bool:
    return (
        code_point in {0x09, 0x0A, 0x0D, 0x85}
        or 0x20 <= code_point <= 0x7E
        or 0xA0 <= code_point <= 0xD7FF
        or 0xE000 <= code_point <= 0xFFFD
        or 0x10000 <= code_point <= 0x10FFFF
    )


def _validate_frontmatter_characters(value: str, *, field: str) -> None:
    for index, character in enumerate(value):
        code_point = ord(character)
        if character == "\n":
            continue
        if code_point in {0x85, 0x2028, 0x2029}:
            raise ValueError(
                f"{field} contains a raw YAML line-break code point at character "
                f"{index + 1}: U+{code_point:04X}"
            )
        if code_point < 0x20 or code_point == 0x7F:
            raise ValueError(
                f"{field} contains an ASCII control at character {index + 1}"
            )
        if not _yaml_printable_code_point(code_point):
            raise ValueError(
                f"{field} contains a non-printable YAML code point at character "
                f"{index + 1}: U+{code_point:04X}"
            )


def _validate_decoded_frontmatter_scalar(value: str, *, field: str) -> None:
    for index, character in enumerate(value):
        code_point = ord(character)
        if code_point < 0x20 or code_point == 0x7F:
            raise ValueError(
                f"{field} decodes to an ASCII control at character {index + 1}"
            )
        if not _yaml_printable_code_point(code_point):
            raise ValueError(
                f"{field} decodes to a non-printable YAML code point at character "
                f"{index + 1}: U+{code_point:04X}"
            )


def _frontmatter_scalar(raw_value: str, *, field: str) -> str:
    if not raw_value.startswith(" "):
        raise ValueError(
            f"{field} must use a colon followed by at least one ASCII space"
        )
    value = raw_value.strip(" ")
    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{field} is not a valid quoted string") from exc
        if not isinstance(parsed, str):
            raise ValueError(f"{field} must be a string")
        _validate_decoded_frontmatter_scalar(parsed, field=field)
        if not parsed.strip(" "):
            raise ValueError(f"{field} must be a non-empty string")
        return parsed
    if not value or value.endswith('"'):
        raise ValueError(f"{field} must be a non-empty YAML scalar")
    if not re.match(r"[A-Za-z]", value):
        raise ValueError(
            f"{field} must be an unambiguous string scalar; quote the value with double quotes"
        )
    if re.fullmatch(
        r"(?:null|~|true|false|yes|no|on|off|[-+]?(?:\d+(?:\.\d*)?|\.\d+))",
        value,
        re.IGNORECASE,
    ):
        raise ValueError(
            f"{field} must be a string scalar; quote the value with double quotes"
        )
    if re.search(r":\s|\s#", value):
        raise ValueError(
            f"{field} contains YAML syntax; quote the value with double quotes"
        )
    if value.endswith(":") or re.search(r"[\x00-\x1f\x7f]", value):
        raise ValueError(
            f"{field} contains invalid plain-scalar syntax; quote the value with double quotes"
        )
    return value


def validate_skill_frontmatter_contract(
    path: Path, *, expected_name: str
) -> dict[str, str]:
    """Require the lean Skill trigger contract without product release metadata."""

    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            source = stream.read()
    except OSError as exc:
        raise ValueError(f"SKILL.md is unreadable: {path}") from exc
    source = source.replace("\r\n", "\n")
    lines = source.split("\n")
    if not lines or lines[0] != "---":
        raise ValueError("SKILL.md must begin with YAML front matter")
    try:
        closing = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("SKILL.md YAML front matter is not closed") from exc
    _validate_frontmatter_characters(
        "\n".join(lines[: closing + 1]), field="SKILL.md front matter"
    )

    fields: dict[str, str] = {}
    for line_number, line in enumerate(lines[1:closing], start=2):
        if not line.strip():
            continue
        if line != line.lstrip():
            raise ValueError(
                f"SKILL.md front matter must contain only top-level scalars; "
                f"found indentation at line {line_number}"
            )
        key, separator, raw_value = line.partition(":")
        if not separator or not key or key in fields:
            raise ValueError(
                f"SKILL.md front-matter entry is malformed or duplicated at line "
                f"{line_number}"
            )
        fields[key] = _frontmatter_scalar(
            raw_value, field=f"SKILL.md {key}"
        )

    required_fields = {"name", "description"}
    if set(fields) != required_fields:
        raise ValueError(
            "SKILL.md front matter must contain exactly name and description: "
            f"got {sorted(fields)}"
        )
    if fields["name"] != expected_name:
        raise ValueError(
            "SKILL.md name differs from package-manifest.toml package.name: "
            f"expected {expected_name!r}, got {fields['name']!r}"
        )
    if not fields["description"]:
        raise ValueError("SKILL.md description must not be empty")
    if len(fields["description"]) > 1024:
        raise ValueError("SKILL.md description must be at most 1024 characters")
    if "<" in fields["description"] or ">" in fields["description"]:
        raise ValueError("SKILL.md description must not contain angle brackets")
    return fields


def validate_pyproject_release_identity(
    data: Mapping[str, Any], *, package_name: str, package_version: str
) -> str:
    """Validate and return the exact normalized PEP 440 project version."""

    project = data.get("project")
    if not isinstance(project, Mapping):
        raise ValueError("pyproject.toml [project] must be a table")
    if project.get("name") != package_name:
        raise ValueError(
            "pyproject.toml project.name differs from package-manifest.toml: "
            f"expected {package_name!r}, got {project.get('name')!r}"
        )
    expected_version = pep440_version_for_calver(
        package_version, field="package version"
    )
    observed_version = project.get("version")
    if observed_version != expected_version:
        raise ValueError(
            "pyproject.toml project.version must be the normalized PEP 440 "
            "representation of the package release: "
            f"expected {expected_version!r}, got {observed_version!r}"
        )
    return expected_version


def validate_core_release_includes(include: Sequence[str]) -> None:
    """Enforce the exact core-owned pack, evaluation, and example boundary."""

    observed = set(include)
    scoped_contracts = (
        ("evaluation", "evals", CORE_EVALUATION_INCLUDES),
        ("example", "examples", CORE_EXAMPLE_INCLUDES),
        ("pack", "packs", CORE_PACK_INCLUDES),
    )
    for label, root_name, expected in scoped_contracts:
        actual = {
            value
            for value in observed
            if PurePosixPath(value).parts
            and PurePosixPath(value).parts[0] == root_name
        }
        if actual != expected:
            raise ValueError(
                f"core release {label} includes must be exactly {sorted(expected)}, "
                f"got {sorted(actual)}"
            )


def validate_pack_gitignore_contract(text: str) -> None:
    """Require Git to track only the bundled default pack under ``packs/``."""

    def is_pack_rule(line: str) -> bool:
        pattern = line.strip().lstrip("!").lstrip("/")
        return pattern == "packs" or pattern.startswith("packs/")

    observed = tuple(
        line.strip()
        for line in text.splitlines()
        if line.strip()
        and not line.lstrip().startswith("#")
        and is_pack_rule(line)
    )
    if observed != PACK_GITIGNORE_RULES:
        raise ValueError(
            f"pack .gitignore rules must be exactly {list(PACK_GITIGNORE_RULES)}, "
            f"got {list(observed)}"
        )


def _safe_release_relative(value: str, *, label: str) -> PurePosixPath:
    if not value or "\\" in value:
        raise ValueError(f"{label} must be a normalized POSIX relative path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{label} must be a normalized POSIX relative path: {value!r}")
    return path


def _parts_within(parts: tuple[str, ...], parent: tuple[str, ...]) -> bool:
    return len(parts) >= len(parent) and parts[: len(parent)] == parent


def release_path_is_excluded(
    relative: Path | PurePosixPath,
    *,
    exclude_names: Iterable[str] = (),
) -> bool:
    """Return whether a declared release path is a development artifact.

    Content selection is owned by ``release.include``. This predicate only
    removes generated or editor/VCS artifacts inside those explicit inputs.
    """

    parts = tuple(relative.parts)
    if not parts:
        return False
    excluded_names = frozenset(exclude_names)
    if any(part in excluded_names or part in VCS_DIR_NAMES for part in parts):
        return True
    name = parts[-1]
    suffix = PurePosixPath(name).suffix.lower()
    return (
        name in GENERATED_RELEASE_ARTIFACT_NAMES
        or suffix in DEVELOPMENT_ARTIFACT_SUFFIXES
        or name.endswith("~")
    )


def iter_release_files(
    root: Path,
    include: Sequence[str],
    *,
    exclude_names: Iterable[str] = (),
    excluded_subtrees: Sequence[str] = (),
) -> tuple[Path, ...]:
    """Inventory regular files reachable only through explicit includes.

    Symbolic links are rejected instead of followed. The returned tuple is
    unique and sorted by canonical release-relative POSIX path so packaging,
    metadata generation, and validation operate on the same inventory.
    """

    root = root.resolve()
    subtree_parts = tuple(
        _safe_release_relative(value, label="excluded release subtree").parts
        for value in excluded_subtrees
    )

    def excluded(relative: Path) -> bool:
        parts = tuple(relative.parts)
        return any(_parts_within(parts, parent) for parent in subtree_parts) or release_path_is_excluded(
            relative, exclude_names=exclude_names
        )

    inventory: dict[str, Path] = {}
    for entry_name in include:
        entry_relative = _safe_release_relative(entry_name, label="release include")
        entry = root.joinpath(*entry_relative.parts)
        if not entry.exists() and not entry.is_symlink():
            raise FileNotFoundError(f"missing required release entry: {entry}")
        if entry.is_symlink():
            raise ValueError(f"symbolic links are forbidden in release inputs: {entry}")
        if excluded(Path(*entry_relative.parts)):
            continue
        if entry.is_file():
            inventory[entry_relative.as_posix()] = entry
            continue
        if not entry.is_dir():
            raise ValueError(f"unsupported release entry: {entry}")

        for current_name, directory_names, file_names in os.walk(entry, topdown=True, followlinks=False):
            current = Path(current_name)
            retained_directories: list[str] = []
            for directory_name in sorted(directory_names):
                child = current / directory_name
                relative = child.relative_to(root)
                if excluded(relative):
                    continue
                if child.is_symlink():
                    raise ValueError(f"symbolic links are forbidden in release inputs: {child}")
                retained_directories.append(directory_name)
            directory_names[:] = retained_directories
            for file_name in sorted(file_names):
                child = current / file_name
                relative = child.relative_to(root)
                if excluded(relative):
                    continue
                if child.is_symlink():
                    raise ValueError(f"symbolic links are forbidden in release inputs: {child}")
                if not child.is_file():
                    raise ValueError(f"unsupported release entry: {child}")
                inventory[relative.as_posix()] = child
    return tuple(inventory[name] for name in sorted(inventory))


def verify_release_includes_present(root: Path, include_paths: Sequence[PurePosixPath]) -> None:
    """Every declared release include exists in this tree.

    Presence is a property of a release tree, not of the declaration, so this is
    asked by the callers that are about a release. Asking it while the metadata
    module was imported made every command a completeness check, and an archive
    that drops an export-ignored file could not run `--help`.
    """

    for path in include_paths:
        target = root.joinpath(*path.parts)
        if not (target.exists() or target.is_symlink()):
            raise ValueError(f"release include is missing: {path.as_posix()!r}")


def load_package_metadata(
    root: Path = ROOT,
    *,
    require_release_files: bool = True,
) -> PackageMetadata:
    manifest_path = root / "package-manifest.toml"
    with manifest_path.open("rb") as stream:
        data: dict[str, Any] = tomllib.load(stream)

    package = data.get("package") or {}
    dependencies = data.get("dependencies") or {}
    release = data.get("release") or {}

    name = str(package.get("name") or "")
    version = str(package.get("version") or "")
    version_scheme = str(package.get("version_scheme") or "")
    release_timezone = str(package.get("release_timezone") or "")
    license_id = str(package.get("license") or "")
    description = str(package.get("description") or "")
    python_requirement = str(dependencies.get("python") or "")
    core_requirements_file = str(dependencies.get("core_requirements") or "")
    visual_requirements_file = str(dependencies.get("visual_requirements") or "")
    requirements_file = str(dependencies.get("requirements") or "")
    tested_requirements_file = str(dependencies.get("tested_requirements") or "")
    pyproject_file = str(dependencies.get("pyproject") or "")
    release_output = str(release.get("output") or "")
    release_include = tuple(str(value) for value in release.get("include") or [])
    release_exclude_names = tuple(str(value) for value in release.get("exclude_names") or [])

    if name != "character-prompt-builder":
        raise ValueError(f"unexpected package name: {name!r}")
    calver_key(version, field="package version")
    if version_scheme != "YYYY.MM.DD.N":
        raise ValueError(f"unexpected version scheme: {version_scheme!r}")
    if release_timezone != "UTC":
        raise ValueError(f"release timezone must be UTC: {release_timezone!r}")
    if license_id != "GPL-3.0-only":
        raise ValueError(f"unexpected license identifier: {license_id!r}")
    if python_requirement != ">=3.11":
        raise ValueError(f"unexpected Python requirement: {python_requirement!r}")
    for field_name, value in (
        ("core_requirements", core_requirements_file),
        ("visual_requirements", visual_requirements_file),
        ("requirements", requirements_file),
        ("tested_requirements", tested_requirements_file),
        ("pyproject", pyproject_file),
    ):
        if not value or not (root / value).is_file():
            raise ValueError(f"dependency definition {field_name} is missing: {value!r}")

    pyproject_path = root / pyproject_file
    try:
        with pyproject_path.open("rb") as stream:
            pyproject_data = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"pyproject.toml is unreadable: {pyproject_path}") from exc
    pyproject_version = validate_pyproject_release_identity(
        pyproject_data,
        package_name=name,
        package_version=version,
    )
    validate_skill_frontmatter_contract(root / "SKILL.md", expected_name=name)

    expected_output = f"dist/{name}-{version}.zip"
    if release_output != expected_output:
        raise ValueError(f"release output must be {expected_output!r}, got {release_output!r}")
    if not release_include:
        raise ValueError("release include list must not be empty")
    if len(set(release_include)) != len(release_include):
        raise ValueError("release include entries must be unique")
    validate_core_release_includes(release_include)
    include_paths = tuple(
        _safe_release_relative(value, label="release include")
        for value in release_include
    )
    if require_release_files:
        verify_release_includes_present(root, include_paths)
    for index, path in enumerate(include_paths):
        for other in include_paths[index + 1 :]:
            if _parts_within(path.parts, other.parts) or _parts_within(other.parts, path.parts):
                raise ValueError(
                    "release include entries must not overlap: "
                    f"{path.as_posix()!r}, {other.as_posix()!r}"
                )
    if len(set(release_exclude_names)) != len(release_exclude_names):
        raise ValueError("release exclude_names entries must be unique")
    for value in release_exclude_names:
        if not value or PurePosixPath(value).name != value or "\\" in value:
            raise ValueError(f"release exclude_names must contain plain names: {value!r}")
    included_pack_dirs: dict[str, Path] = {}
    for value in release_include:
        parts = PurePosixPath(value).parts
        if not parts or parts[0] != "packs":
            continue
        if len(parts) != 2:
            raise ValueError(f"release pack include must be packs/<directory>: {value!r}")
        pack_root = root / value
        if not pack_root.is_dir() or not (pack_root / "pack.json").is_file():
            raise ValueError(f"release pack include is not a pack directory: {value!r}")
        included_pack_dirs[value] = pack_root

    default_state_path = root / "config" / "default-pack-state.json"
    try:
        default_state = json.loads(default_state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"default pack state is unreadable: {default_state_path}") from exc
    default_pack_ids = tuple(str(value) for value in default_state.get("enabled_packs") or [])
    if not default_pack_ids or len(set(default_pack_ids)) != len(default_pack_ids):
        raise ValueError("default-pack-state enabled_packs must contain unique default pack IDs")
    raw_resource_providers = default_state.get("resource_providers") or {}
    if not isinstance(raw_resource_providers, Mapping):
        raise ValueError("default-pack-state resource_providers must be an object")
    default_resource_providers = tuple(
        sorted((str(name), str(pack_id)) for name, pack_id in raw_resource_providers.items())
    )
    included_pack_ids: list[str] = []
    for value, pack_root in included_pack_dirs.items():
        try:
            pack_manifest = json.loads((pack_root / "pack.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"included default pack manifest is unreadable: {value!r}") from exc
        included_pack_ids.append(str(pack_manifest.get("pack_id") or ""))
    if sorted(default_pack_ids) != sorted(included_pack_ids):
        raise ValueError(
            "default-pack-state enabled_packs must exactly match individually included release packs"
        )
    unknown_providers = sorted(
        {pack_id for _, pack_id in default_resource_providers} - set(default_pack_ids)
    )
    if unknown_providers:
        raise ValueError(
            "default-pack-state resource providers must reference included default packs: "
            + ", ".join(unknown_providers)
        )

    return PackageMetadata(
        name=name,
        version=version,
        pyproject_version=pyproject_version,
        version_scheme=version_scheme,
        release_timezone=release_timezone,
        license_id=license_id,
        description=description,
        python_requirement=python_requirement,
        core_requirements_file=core_requirements_file,
        visual_requirements_file=visual_requirements_file,
        requirements_file=requirements_file,
        tested_requirements_file=tested_requirements_file,
        pyproject_file=pyproject_file,
        release_output=release_output,
        release_include=release_include,
        release_exclude_names=release_exclude_names,
        release_pack_dirs=tuple(sorted(included_pack_dirs)),
        default_pack_ids=default_pack_ids,
        default_resource_providers=default_resource_providers,
    )


_METADATA = load_package_metadata(require_release_files=False)
PACKAGE_NAME = _METADATA.name
PACKAGE_VERSION = _METADATA.version
VERSION_SCHEME = _METADATA.version_scheme
RELEASE_TIMEZONE = _METADATA.release_timezone
LICENSE_ID = _METADATA.license_id
PACKAGE_DESCRIPTION = _METADATA.description


def session_hook(root_variable: str) -> dict[str, Any]:
    """The session hook, written against one host's plugin-root variable."""

    script = f'"${{{root_variable}}}/scripts/session_entry_points.py"'
    return {
        "hooks": {
            "SessionStart": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"python3 {script} || python {script}",
                            "timeout": 20,
                        }
                    ]
                }
            ]
        }
    }


def host_manifests() -> dict[str, Any]:
    """The manifests a plugin host reads, as documents rather than as files.

    A host takes the product name, version and licence from these. Written by
    hand they drift from the package the moment the package moves, because
    nothing reads both, so they are derived from the same metadata as everything
    else this file rebuilds.
    """

    author = {"name": PACKAGE_NAME}
    entry = {
        "name": PACKAGE_NAME,
        "description": PACKAGE_DESCRIPTION,
    }
    return {
        ".claude-plugin/plugin.json": {
            "name": PACKAGE_NAME,
            "version": PACKAGE_VERSION,
            "description": PACKAGE_DESCRIPTION,
            "author": author,
            "license": LICENSE_ID,
        },
        ".claude-plugin/marketplace.json": {
            "name": PACKAGE_NAME,
            "owner": author,
            "description": PACKAGE_DESCRIPTION,
            "plugins": [{**entry, "source": "."}],
        },
        ".codex-plugin/plugin.json": {
            "name": PACKAGE_NAME,
            "version": PACKAGE_VERSION,
            "description": PACKAGE_DESCRIPTION,
            "author": author,
            "license": LICENSE_ID,
            # This product keeps SKILL.md at the plugin root rather than under a
            # skills directory, so the path is the root itself. A manifest hook
            # path must start with "./"; a bare relative path is refused.
            "skills": "./",
            "hooks": "./hooks/codex.json",
        },
        # One definition, rendered once per host. Each host reads its own file
        # under its own canonical variable: Claude Code loads hooks/hooks.json
        # and sets CLAUDE_PLUGIN_ROOT, and Codex is pointed at its own file by
        # the manifest entry below, which replaces its default lookup, and reads
        # PLUGIN_ROOT. Codex also sets CLAUDE_PLUGIN_ROOT as a compatibility
        # alias, so one shared file would run on both, but naming a host by the
        # other one's variable is a dependency on that alias rather than on the
        # contract. Codex does not execute a plugin's hooks until the user
        # reviews and trusts them.
        "hooks/hooks.json": session_hook("CLAUDE_PLUGIN_ROOT"),
        "hooks/codex.json": session_hook("PLUGIN_ROOT"),
        ".agents/plugins/marketplace.json": {
            "name": PACKAGE_NAME,
            "plugins": [{
                **entry,
                "source": {"source": "local", "path": "./"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_USE"},
            }],
        },
    }
RELEASE_OUTPUT = _METADATA.release_output
RELEASE_INCLUDE = _METADATA.release_include
RELEASE_EXCLUDE_NAMES = _METADATA.release_exclude_names
DEFAULT_PACK_IDS = _METADATA.default_pack_ids
DEFAULT_RESOURCE_PROVIDERS = _METADATA.resource_providers
RELEASE_OUTPUT_DIR = PurePosixPath(_METADATA.release_output).parts[0]
NON_CONTENT_DIR_NAMES = frozenset({".git", RELEASE_OUTPUT_DIR})
RELEASE_PACK_DIR_NAMES = frozenset(
    PurePosixPath(value).parts[1]
    for value in RELEASE_INCLUDE
    if len(PurePosixPath(value).parts) == 2 and PurePosixPath(value).parts[0] == "packs"
)


def is_non_content_path(path: Path, root: Path = ROOT) -> bool:
    """Return whether a path is outside the compact core release boundary."""
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        relative = path
    if NON_CONTENT_DIR_NAMES.intersection(relative.parts):
        return True
    return (
        len(relative.parts) >= 2
        and relative.parts[0] == "packs"
        and relative.parts[1] not in RELEASE_PACK_DIR_NAMES
    )
