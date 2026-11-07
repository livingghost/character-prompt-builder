#!/usr/bin/env python3
"""A studio: where one body of character work lives, with its trail.

A studio holds characters, each with its sheet, every image ever generated for
it, and which of those images are accepted for which slot. Every generation is
an iteration: the exact request that was sent, what came back, the file, and the
package it was built from, so that an image can be regenerated later with the
same settings and a quality that drifted can be traced to what changed. An
accepted image is superseded, never overwritten, when the owner changes their
mind, and every acceptance is kept with its time, so the history of a slot is
readable end to end.

The studio also carries the open task and the trail of tasks (see
work_ledger.py), so a session that lost its context reads where the work stands
and continues.

    python scripts/studio.py init --out DIR --studio-id ID --title "..."
    python scripts/studio.py status --studio DIR
    python scripts/studio.py character add <id> --studio DIR [--profile general|humanoid|anthro|<path>]
    python scripts/studio.py iterate --studio DIR --character <id> --slot <slot> --result <file>
        [--package <file>] [--package-companion <dir>] [--request <file>] [--response <file>] [--note "..."]
    python scripts/studio.py attach-package --studio DIR --character <id> --iteration <it-id>
        --package <file> [--package-companion <dir>] --evidence <file> --actor "..." --reason "..."
    python scripts/studio.py accept --studio DIR --character <id> --iteration <it-id>
    python scripts/studio.py reject --studio DIR --character <id> --iteration <it-id> --reason "..." --actor "..."
    python scripts/studio.py recipe --studio DIR --character <id> --slot <slot> [--iteration <it-id>]
    python scripts/studio.py gallery --studio DIR [--out <file.html>]
    python scripts/studio.py credentials prepare SERVICE --studio DIR
        [--environment NAME | --stored]
    python scripts/studio.py credentials set SERVICE --studio DIR [--stdin | --from-env NAME]
    python scripts/studio.py credentials status [SERVICE] --studio DIR
    python scripts/studio.py credentials remove SERVICE --studio DIR

`--studio` names any directory in the studio, before or after the command, and
defaults to the working directory.
"""
from __future__ import annotations
import operation_context as _operation_context

import argparse
import contextlib
import copy
import json
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Callable

from cli_invocation import python_argv, shown
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import execution_contract  # noqa: E402
import work_ledger  # noqa: E402
from private_state import assert_public_path, assert_public_tree
# A record is replaced whole: a reader sees the old record or the new one, never a torn one.
from studio_activity import timestamp as now, mutation
import runtime_snapshot
from execution_contract import atomic_write_json as write_json, sha256_file  # noqa: E402
from owned_json import freeze, mutable

MANIFEST = "studio.json"
STUDIO_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]+$")
# A character id is a directory name on every system, so it cannot end in a
# dot: Windows drops a trailing dot and would put the character somewhere else.
CHARACTER_ID = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9_-])?$")
# Windows reserves these device names in any case and with any extension.
RESERVED_NAMES = re.compile(r"^(?:con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\..*)?$", re.IGNORECASE)
SLOT = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
ITERATION_ID = re.compile(r"^it-([0-9]+)$")
DIRECTORIES = ("characters", "packages", "runs", "prompts", "work")
CHARACTER_DIRECTORIES = ("sheet", "iterations", "accepted")
# The status an imported iteration stores.
STATUSES = ("candidate", "accepted", "rejected", "superseded")
# The status a Production candidate shows: its place on the adoption axis, or
# `unavailable` when its formal record cannot be read. Its evaluation and
# disposition come from the run's records and are shown beside it.
PRODUCTION_STATUSES = ("candidate", "accepted", "superseded", "unavailable")
# Fields read from the run's records for a Production candidate; they are never stored.
PRODUCTION_PROJECTION = ("evaluation", "disposition", "unassessed_criteria", "selection_diagnostics", "review_ref",
                         "decision_kind", "reason", "selection_basis", "owner_acceptance", "production_diagnostic")
INIT_ARGUMENTS = ("init", "--out", "<dir>", "--studio-id", "<id>", "--title", "<title>")

README = {
    "characters": "One directory per character: sheet/ (the Character Sheet), iterations/ (every generated image with the exact request and response), accepted/ (the image accepted for each slot), iterations.jsonl (the record of each iteration and its status).\n",
    "packages": "Generation Packages built for images of this studio, referenced by iterations.\n",
    "runs": "What was sent to a service and what came back, when a run is recorded outside an iteration.\n",
    "prompts": "Reviewed prompt artifacts and prompt-only work that belongs to no single iteration.\n",
    "work": "The open task (current.json) and the trail of tasks (ledger.jsonl). A session reads current.json first.\n",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def init_command() -> str:
    """The command that creates a studio, with every argument it requires."""
    return shown(python_argv(ROOT / "scripts" / "studio.py", *INIT_ARGUMENTS))


def studio_root(start: Path) -> Path | None:
    """The studio a directory belongs to: the nearest ancestor holding the manifest."""
    for candidate in (start, *start.parents):
        if (candidate / MANIFEST).is_file():
            return candidate
    return None


def require_studio(start: Path) -> Path:
    start = start.resolve()
    if not start.exists():
        raise ValueError(f"the directory {start} does not exist")
    found = studio_root(start)
    if found is None:
        raise ValueError(f"{start} is not in a studio; create one with: {init_command()}")
    return found


@contextlib.contextmanager
def recording_lock(root: Path, *, character: str | None = None) -> Iterator[None]:
    """Serialize only the manifest or one character's journal/file replacement.

    Readers and generated displays do not acquire this lock. A character's
    iterations, adoption journal and accepted image form one mutable owner.
    """
    owner = character_dir(root, character) if character is not None else root
    with execution_contract.lock(owner):
        yield


# The manifest and the layout.

def _entries(directory: Path) -> list[Path]:
    return [path for path in directory.iterdir() if path.name != execution_contract.LOCK_FILE]


def init(out: Path, studio_id: str, title: str, *, default_render_profile: str = "profile-clear-2d-illustration",
         default_creative_latitude: str = "directed", default_interaction_mode: str = "balanced",
         default_style_family: str | None = None) -> Path:
    if not STUDIO_ID.fullmatch(studio_id):
        raise ValueError("studio id must be at least two characters of letters, digits, dot, underscore or dash")
    if not title.strip():
        raise ValueError("a studio needs a title")
    out = out.resolve()
    if out.exists() and not out.is_dir():
        raise ValueError(f"{out} is a file, not a directory")
    parent = next((path for path in out.parents if path.exists()), None)
    if parent is not None and not parent.is_dir():
        raise ValueError(f"{parent} is a file, so {out} cannot be created")
    if out.exists() and _entries(out):
        raise ValueError(f"{out} exists and is not empty")
    with recording_lock(out):
        if _entries(out):
            raise ValueError(f"{out} exists and is not empty")
        for name in DIRECTORIES:
            (out / name).mkdir(parents=True, exist_ok=True)
            execution_contract.atomic(out / name / "README.md", README[name].encode("utf-8"), replace=True)
        write_json(out / MANIFEST, {
            "studio_id": studio_id,
            "title": title.strip(),
            # What a request that leaves medium, latitude, interaction or style open starts from.
            "default_render_profile": default_render_profile,
            "default_creative_latitude": default_creative_latitude,
            "default_interaction_mode": default_interaction_mode,
            "default_style_family": default_style_family,
            "created_at": now(),
            "characters": [],
        })
    import studio_activity as activity
    activity.changed(out / MANIFEST, 'studio-created', revision=execution_contract.content_id(manifest(out)))
    return out


def manifest(root: Path, *, read_bytes: Callable[[str], bytes] | None = None) -> dict[str, Any]:
    path = root / MANIFEST
    try:
        value = read_json(path) if read_bytes is None else json.loads(read_bytes(MANIFEST).decode('utf-8'))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not JSON ({exc.msg}, line {exc.lineno})") from None
    if not isinstance(value, dict):
        raise ValueError(f"{path}: not an object")
    return value


def valid_character_id(character: Any) -> bool:
    return isinstance(character, str) and bool(CHARACTER_ID.fullmatch(character)) and not RESERVED_NAMES.match(character)


def character_dir(root: Path, character: str) -> Path:
    if not valid_character_id(character):
        raise ValueError(
            "character id must be letters, digits, dot, underscore or dash, "
            "starting with a letter or digit, not ending with a dot, and not a Windows device name such as con or nul"
        )
    return root / "characters" / character


def listed_characters(root: Path, *, read_bytes: Callable[[str], bytes] | None = None) -> list[str]:
    return [str(entry.get("id")) for entry in manifest(root, read_bytes=read_bytes).get("characters") or [] if isinstance(entry, dict)]


def character_home(root: Path, character: str, *, read_bytes: Callable[[str], bytes] | None = None) -> Path:
    """The directory of a character the manifest lists; a mistyped id is refused by name."""
    home = character_dir(root, character)
    if character not in listed_characters(root, read_bytes=read_bytes) or not home.is_dir():
        raise ValueError(f"character {character!r} is not in this studio")
    return home


def add_character(root: Path, character: str, profile: str) -> Path:
    home = character_dir(root, character)
    with recording_lock(root):
        characters = root / "characters"
        on_disk = [path.name for path in characters.iterdir() if path.is_dir()] if characters.is_dir() else []
        for existing in (*listed_characters(root), *on_disk):
            if existing == character:
                raise ValueError(f"character {character!r} already exists")
            if existing.casefold() == character.casefold():
                raise ValueError(
                    f"character {character!r} differs only by case from {existing!r}; "
                    "Windows and macOS keep both in one directory"
                )
        if home.exists():
            raise ValueError(f"character {character!r} already exists")
        try:
            for name in CHARACTER_DIRECTORIES:
                (home / name).mkdir(parents=True)
            execution_contract.atomic(home / "iterations.jsonl", b"", replace=True)
            from character_sheet import initialize_sidecar

            initialize_sidecar(home / "sheet", profile=profile)
            document = manifest(root)
            document.setdefault("characters", []).append({"id": character, "added_at": now()})
            write_json(root / MANIFEST, document)
        except BaseException:
            # The manifest is written last, so a character it does not list is
            # removed whole and the id stays free to add again.
            shutil.rmtree(home, ignore_errors=True)
            raise
    write_gallery(root)
    return home


# Iterations: one record per generated image.

class StudioRead:
    """One operation's deserialized Studio inputs and derived read models.

    Callers pass this value explicitly. A mutation uses a new read model after
    committing; this object never serves data across public operations.
    """

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.reload()

    def reload(self) -> None:
        """Discard the previous read boundary before an owner publishes a view."""
        self.document = {}
        self.characters = []
        self._raw: dict[str, list[dict]] = {}
        self._adoption_rows: dict[str, list[dict]] = {}
        self._iterations: dict[str, list[dict]] = {}
        self._sheets: dict[str, dict] = {}
        self._runs: dict[str, tuple | BaseException] = {}
        self._references: dict[str, dict | BaseException] = {}
        self._journals: dict[tuple[str, str], dict] = {}
        self._packages: dict[tuple[str, str], tuple[Path, dict]] = {}
        self._verified_packages: set[tuple[str, str]] = set()
        self._current_references: dict[tuple[str, str], tuple[dict, dict]] = {}
        self.artifacts: dict = {}
        self.document = freeze(manifest(self.root))
        self.characters = freeze([str(entry.get('id')) for entry in self.document.get('characters') or []
                                  if isinstance(entry, dict)])

    def require_root(self, root: Path) -> None:
        if self.root != root.resolve():
            raise ValueError('Studio read belongs to another root')

    def home(self, character: str) -> Path:
        home = character_dir(self.root, character)
        if character not in self.characters or not home.is_dir():
            raise ValueError(f"character {character!r} is not in this studio")
        return home

    def raw_iterations(self, character: str) -> list[dict]:
        if character not in self._raw:
            self._raw[character] = freeze(read_iteration_records(self.home(character)))
        return self._raw[character]

    def iterations(self, character: str) -> list[dict]:
        if character not in self._iterations:
            self._iterations[character] = freeze(project_iterations(
                self.home(character), self.raw_iterations(character), read=self))
        return self._iterations[character]

    def adoption_rows(self, character: str) -> list[dict]:
        """Read the stored adoption axis without projecting unrelated Production runs."""
        if character not in self._adoption_rows:
            rows = copy.deepcopy(self.raw_iterations(character))
            for row in rows:
                if row.get('production') is not None:
                    adoption = row.get('adoption_status', 'none')
                    row['status'] = adoption if adoption in {'accepted', 'superseded'} else 'candidate'
            self._adoption_rows[character] = freeze(rows)
        return self._adoption_rows[character]

    def sheet(self, character: str) -> dict:
        if character not in self._sheets:
            from sheet_artifacts import _read
            self._sheets[character] = freeze(_read(self.home(character) / 'sheet/sheet-data.json'))
        return self._sheets[character]

    def run(self, run: str):
        if run not in self._runs:
            from production_workflow import read_run
            try:
                self._runs[run] = read_run(self.root, run)
            except (ValueError, OSError, KeyError, TypeError) as exc:
                self._runs[run] = exc
        result = self._runs[run]
        if isinstance(result, BaseException):
            raise result
        return result

    def journal(self, character: str, iteration: str) -> dict:
        key = character, iteration
        if key not in self._journals:
            from adoption_workflow import _journal_path
            self._journals[key] = freeze(read_json(_journal_path(self.home(character), iteration)))
        return self._journals[key]

    def _package(self, reference: dict, *, verify: bool = False) -> tuple[Path, dict]:
        """Read exact package bytes once and retain their recorded-content validation.

        Internal validators share this owned value without copying the complete
        input graph. Verification belongs to this read boundary and package
        directory, whose companion files are part of the proof.
        """
        key = reference['path'], reference['sha256']
        if key not in self._packages:
            from character_sheet import resolve_sheet_relative
            path = resolve_sheet_relative(reference['path'], root=self.root, field='studio file')
            raw = execution_contract.read(path)
            if execution_contract.digest(raw) != reference['sha256']:
                raise ValueError('studio file hash changed: ' + reference['path'])
            self._packages[key] = path, freeze(execution_contract.decode(raw))
        path, document = self._packages[key]
        if verify and key not in self._verified_packages:
            from verify_generation_payload import verify_content
            verify_content(document, package_root=path.parent)
            self._verified_packages.add(key)
        return path, document

    def package(self, reference: dict, *, verify: bool = False) -> tuple[Path, dict]:
        """Return a caller-owned package without exposing the retained read model."""
        path, document = self._package(reference, verify=verify)
        return path, mutable(document)

    def current_reference_view(self, character: str, slot: str) -> tuple[dict, dict]:
        """Share the exact immutable acceptance and proof with domain readers."""
        key = character, slot
        if key not in self._current_references:
            from studio_reference import _load_current
            self._current_references[key] = freeze(_load_current(self.root, character, slot, read=self))
        return self._current_references[key]

    def current_reference(self, character: str, slot: str) -> tuple[dict, dict]:
        """Export an independently editable source and proof for an API caller."""
        source, proof = self.current_reference_view(character, slot)
        return mutable(source), mutable(proof)

    def reference_index(self, character: str) -> dict:
        if character not in self._references:
            from adoption_workflow import _reference_index
            try:
                self._references[character] = freeze(_reference_index(self.root, character, read=self))
            except (ValueError, OSError, KeyError, TypeError, RuntimeError) as exc:
                self._references[character] = exc
        result = self._references[character]
        if isinstance(result, BaseException):
            raise result
        return result


def read_iteration_records(home: Path) -> list[dict[str, Any]]:
    """Read the stored iteration journal without loading any Production runs."""
    path = home / "iterations.jsonl"
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ValueError(f"{path} is not UTF-8 text") from None
    rows = []
    for number, line in enumerate(text.splitlines(), 1):
        if line.strip():
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}: line {number} is not JSON ({exc.msg})") from None
            if not isinstance(value, dict):
                raise ValueError(f"{path}: line {number} is not an object")
            rows.append(value)
    return rows


def read_iterations(home: Path, *, project: bool = True) -> list[dict[str, Any]]:
    """Read stored rows and, when requested, their Production display projection."""
    rows = read_iteration_records(home)
    return project_iterations(home, rows) if project else rows


def project_iterations(home: Path, rows: list[dict[str, Any]], *, read: StudioRead | None = None) -> list[dict[str, Any]]:
    """Build the shared Studio view from stored adoption and formal Production decisions.

    A Production candidate keeps its status on the adoption axis. Its evaluation,
    disposition, unassessed criteria and the reason of its latest decision come
    from the run, with `decision_kind` naming whether that reason belongs to a
    selection or a disposition.
    """
    rows = copy.deepcopy(rows)
    root = home.parent.parent
    # Each run is read and verified once; a run that cannot be read marks only its own rows.
    runs: dict[str, tuple | BaseException] = {}
    for row in rows:
        origin = row.get("production")
        if origin is None:
            continue
        adoption = row.get("adoption_status", "none")
        row["status"] = adoption if adoption in {"accepted", "superseded"} else "candidate"
        try:
            from production_workflow import candidate_state, read_run
            if origin["run"] not in runs:
                try:
                    runs[origin["run"]] = read.run(origin["run"]) if read else read_run(root, origin["run"])
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    runs[origin["run"]] = exc
            loaded = runs[origin["run"]]
            if isinstance(loaded, BaseException):
                raise loaded
            projected = candidate_state(root, origin["run"], origin["candidate"], loaded=loaded)
            if projected["candidate_sha256"] != row["result"]["sha256"]:
                raise ValueError("Studio result differs from its Production candidate")
            row.update({key: projected[key] for key in ("evaluation", "disposition", "unassessed_criteria", "selection_diagnostics")})
            row["review_ref"] = projected["review"]
            decision = projected["decision_detail"]
            row["decision_kind"] = None if decision is None else (
                "selection" if projected["disposition"] == "selected" else "disposition")
            row["reason"] = decision.get("reason") if decision else None
            row["selection_basis"] = projected.get("selection_basis")
            row["owner_acceptance"] = (decision.get("owner_acceptance")
                                       if decision and projected["disposition"] == "selected" else None)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            # A broken candidate is visible, not reinterpreted as an imported image.
            from production_diagnostics import from_exception
            row["production_diagnostic"] = from_exception(exc, phase="studio-projection")
            if row["status"] == "candidate":
                row["status"] = "unavailable"
    return rows


def write_iterations(home: Path, rows: list[dict[str, Any]]) -> None:
    stored = []
    for row in rows:
        item = copy.deepcopy(row)
        if item.get("production") is not None:
            status = item.pop("status", None)
            item["adoption_status"] = status if status in {"accepted", "superseded"} else item.get("adoption_status", "none")
            for key in (*PRODUCTION_PROJECTION, "rejected_at"):
                item.pop(key, None)
        stored.append(item)
    raw = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in stored).encode("utf-8")
    execution_contract.atomic(home / "iterations.jsonl", raw, replace=True)
    runtime_snapshot.invalidate_studio(home.parent.parent)


def next_iteration_id(home: Path, rows: list[dict[str, Any]]) -> str:
    """One past the highest id the character ever used, counting directories left by rows since removed."""
    used = {str(row.get("iteration_id") or "") for row in rows}
    iterations = home / "iterations"
    if iterations.is_dir():
        used.update(path.name for path in iterations.iterdir() if path.is_dir())
    numbers = [int(match.group(1)) for name in used if (match := ITERATION_ID.match(name))]
    return f"it-{(max(numbers) + 1) if numbers else 1:04d}"


def _keep(root: Path, home: Path, iteration_id: str, source: Path | None, name: str) -> dict[str, Any] | None:
    """Copy a file into the iteration's directory and record its hash; None when there is none."""
    if source is None:
        return None
    assert_public_path(source)
    source = source.resolve()
    assert_public_path(source)
    if not source.is_file():
        raise ValueError(f"{source} is not a file")
    target = home / "iterations" / iteration_id / f"{name}{source.suffix.lower()}"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return {"path": target.relative_to(root).as_posix(), "sha256": sha256_file(target)}


def _keep_answer(root: Path, home: Path, rows: list[dict[str, Any]], iteration_id: str, answer: Path,
                 response: Path | None) -> dict[str, Any]:
    """Keep the service's whole answer once; each image of one answer names the same copy.

    The response of the image names the answer by its SHA-256, so the two are
    refused when they do not belong together.
    """
    digest = sha256_file(answer.resolve())
    named = read_json(Path(response)) if response is not None else None
    if not isinstance(named, dict) or named.get("answer_sha256") != digest:
        raise ValueError(f"the response does not name the answer {answer} by its sha256")
    for row in rows:
        kept = row.get("answer")
        if isinstance(kept, dict) and kept.get("sha256") == digest and (root / str(kept.get("path"))).is_file() \
                and sha256_file(root / kept["path"]) == digest:
            return dict(kept)
    return _keep(root, home, iteration_id, answer, "answer")


def _keep_companion(home: Path, iteration_id: str, companion: Path) -> Path:
    """Copy a package's .references companion into the iteration under its own name.

    The name is kept because the carriers inside the package are signed as
    `<companion>/<file>`: renamed, the package that the iteration holds would no
    longer resolve beside it.
    """
    assert_public_tree(companion)
    companion = companion.resolve()
    if not companion.is_dir():
        raise ValueError(f"{companion} is not a directory")
    target = home / "iterations" / iteration_id / companion.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(companion, target, dirs_exist_ok=True)
    return target


def check_request_layout(layout: Any, request: Any) -> None:
    """Refuse a request layout that does not describe the recorded request.

    The layout is the one the service's transport wrote with the request: which
    field holds the model, the prompt, the negative, the seed, each media item
    and the run's own identifiers. It is checked with the transport contract's
    own rule, against the request exactly as it was sent.
    """
    import request_contract

    if not isinstance(request, dict):
        raise ValueError("a request layout needs the recorded request it describes")
    try:
        target = {"model_identifier": _field(request, layout["model"]), "operation": _field(request, layout["operation"])}
        request_contract.validate_layout(request, layout, [{}] * len(layout["media"]), target)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"the request layout does not describe the recorded request: {exc}") from None


def _field(value: Any, path: Any) -> Any:
    """The value at a layout path, or None where the request has nothing there."""
    import request_contract

    if not path:
        return None
    try:
        return request_contract.get(value, path)
    except ValueError:
        return None


def _check_inputs(files: dict[str, Path | None], package_companion: Path | None) -> None:
    """Name a missing or unreadable input before anything is copied into the studio."""
    for name, source in files.items():
        if source is None:
            continue
        path = Path(source).resolve()
        if not path.exists():
            raise ValueError(f"the {name} file {path} does not exist")
        if not path.is_file():
            raise ValueError(f"the {name} path {path} is not a file")
        if name != "result":
            try:
                read_json(path)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ValueError(f"the {name} file {path} is not JSON: {exc}") from None
    if files.get("package") is not None and package_companion is not None:
        companion = Path(package_companion).resolve()
        if not companion.is_dir():
            raise ValueError(f"the package companion {companion} is not a directory")


def validate_recording_target(root: Path, character: str, slot: str, *, writable: bool = False,
                              read: StudioRead | None = None) -> Path:
    """Refuse local destination errors before a dispatcher uploads or sends.

    Writability is probed only on a send. A dry run reads the destination without
    writing files. Recording repeats the check under its lock; a later disk or
    permission failure is recoverable from the dispatcher's durable run journal.
    """
    root = root.resolve()
    if require_studio(root) != root:
        raise ValueError(f"{root} is not a studio root")
    home = read.home(character) if read else character_home(root, character)
    if not isinstance(slot, str) or not SLOT.fullmatch(slot):
        raise ValueError("slot must be lower-case letters, digits, dot, underscore or dash, such as base.front")
    directories = (root, root / "runs", root / "packages", home, home / "iterations", home / "accepted")
    for directory in directories:
        if not directory.is_dir() or not directory.resolve().is_relative_to(root):
            raise ValueError(f"recording destination is not a directory inside this studio: {directory}")
    for path in (home / "iterations.jsonl", root / "gallery.html", root / "gallery.json"):
        if path.exists() and (not path.is_file() or path.is_symlink()):
            raise ValueError(f"recording destination is not a regular file: {path}")
    if not (home / "iterations.jsonl").is_file():
        raise ValueError(f"character {character!r} has no iterations.jsonl")
    # Destination validation checks the stored journal's syntax. Production
    # projection is a separate caller-owned concern and its result is not used here.
    if read is not None:
        read.raw_iterations(character)
    else:
        read_iteration_records(home)
    if writable:
        for directory in directories:
            # An actual create is more reliable than os.access with ACLs.
            descriptor, name = tempfile.mkstemp(prefix=".cpb-write-probe-", dir=directory)
            os.close(descriptor)
            Path(name).unlink()
        for path in (home / "iterations.jsonl", root / "gallery.html", root / "gallery.json"):
            if path.exists():
                with path.open("ab"):
                    pass
    return home


@mutation
def iterate(root: Path, character: str, slot: str, result: Path, *, package: Path | None, request: Path | None,
            response: Path | None, note: str | None, service: dict[str, Any] | None = None,
            package_companion: Path | None = None, layout: dict[str, Any] | None = None,
            answer: Path | None = None) -> dict[str, Any]:
    with recording_lock(root, character=character):
        return _record_iteration(root, character, slot, result, package=package, request=request,
                                 response=response, note=note, service=service,
                                 package_companion=package_companion, layout=layout, answer=answer)


def _record_iteration(root: Path, character: str, slot: str, result: Path, *, package: Path | None,
                      request: Path | None, response: Path | None, note: str | None,
                      service: dict[str, Any] | None = None,
                      package_companion: Path | None = None,
                      layout: dict[str, Any] | None = None,
                      answer: Path | None = None) -> dict[str, Any]:
    # The kept copies are recorded relative to the resolved studio root, the
    # root the destination check reads, so a root given through a directory
    # junction records the same studio-relative paths.
    root = root.resolve()
    home = validate_recording_target(root, character, slot)
    _check_inputs({"result": result, "package": package, "request": request, "response": response,
                   "answer": answer}, package_companion)
    if layout is not None:
        check_request_layout(layout, read_json(Path(request)) if request is not None else None)
    rows = read_iterations(home)
    origin = None
    document = read_json(package) if package is not None else None
    binding = document.get("production_binding") if isinstance(document, dict) else None
    if binding is not None:
        from production_workflow import read_run
        _, prepared, _, events = read_run(root, binding["run"])
        if prepared["input_sha256"] != binding["input_sha256"]:
            raise ValueError("Studio package does not belong to the named Production input")
        digest = sha256_file(result)
        response_value = read_json(response) if response is not None else {}
        index = response_value.get("index")
        matches = [e for e in events if e["event"] == "candidate" and e["data"]["files"][0]["sha256"] == digest
                   and (index is None or e["data"].get("output_index") == index)]
        if len(matches) != 1:
            raise ValueError("Register the exact result as a Production candidate before projecting it in Studio")
        origin = {"run": binding["run"], "candidate": matches[0]["sha256"]}
        existing = [row for row in rows if row.get("production") == origin]
        if existing:
            return existing[0]
    iteration_id = next_iteration_id(home, rows)
    kept_answer = _keep_answer(root, home, rows, iteration_id, answer, response) if answer is not None else None
    row: dict[str, Any] = {
        "iteration_id": iteration_id,
        "at": now(),
        "character": character,
        "slot": slot,
        "status": "candidate",
        "acceptances": [],
        **({"production": origin, "adoption_status": "none"} if origin else {"provenance": "external-import"}),
        "result": _keep(root, home, iteration_id, result, "result"),
        "package": _keep(root, home, iteration_id, package, "package"),
        "request": _keep(root, home, iteration_id, request, "request"),
        "request_layout": copy.deepcopy(layout),
        "response": _keep(root, home, iteration_id, response, "response"),
        **({"answer": kept_answer} if kept_answer is not None else {}),
        "service": None,
        "seed": None,
        "note": note.strip() if note else None,
    }
    if row["package"] and package_companion is not None:
        # The carriers the package names live beside it; without them the copy
        # the iteration keeps cannot be read back as a package.
        _keep_companion(home, iteration_id, package_companion)
    if row["package"]:
        document = read_json(root / row["package"]["path"])
        payload = document.get("generation_payload") if isinstance(document, dict) else None
        if isinstance(payload, dict):
            row["service"] = payload.get("service")
            row["package"]["generation_input_sha256"] = document.get("generation_input_sha256")
    # The seed of this image is the one the service answered with. The request's
    # seed is what was asked for, and one request that returns several images
    # answers with a different seed for each; the request is the fallback for a
    # service that answers with none, and for an iteration recorded by hand.
    if row["response"]:
        answer = read_json(root / row["response"]["path"])
        if isinstance(answer, dict):
            row["seed"] = answer.get("seed")
    if row["request"]:
        sent = read_json(root / row["request"]["path"])
        if isinstance(sent, dict):
            # The layout names the fields; a request recorded by hand has none,
            # and its top-level model and seed are read as written.
            asked_seed = _field(sent, layout.get("seed")) if layout else sent.get("seed")
            model = _field(sent, layout.get("model")) if layout else sent.get("model")
            if row["seed"] is None:
                row["seed"] = asked_seed
            if row["service"] is None and model:
                row["service"] = {"id": None, "model_identifier": model, "observed_at": None, "schema_snapshot": None}
    if service is not None:
        row["service"] = dict(service)
    rows.append(row)
    write_iterations(home, rows)
    import studio_activity as activity
    projection = activity.changed(home / 'iterations.jsonl', 'iteration-recorded', subject=character+'/'+iteration_id,
                     revision=execution_contract.content_id(row),
                     details={'character':character, 'slot':slot, 'iteration_id':iteration_id,
                              'received_at':row['at'], 'run':(origin or {}).get('run'), 'result':row['result']['path']})
    result = _find(read_iterations(home), iteration_id)
    return result if projection.get('ok') else {**result, 'projection_warning': projection}


def _find(rows: list[dict[str, Any]], iteration_id: str) -> dict[str, Any]:
    found = next((row for row in rows if row.get("iteration_id") == iteration_id), None)
    if found is None:
        raise ValueError(f"no iteration {iteration_id!r}")
    return found


def _package_source_candidates(root: Path, row: dict[str, Any], package: dict[str, Any],
                               recorded: list[str] | None = None, *, read: StudioRead | None = None) -> list[str] | None:
    """Check a local Production source without transferring the import's ownership.

    A package records input. Its binding neither selects an image nor grants a
    run permission. A retained local candidate corroborates the declared source;
    the separately retained attribution evidence remains the author's judgment.
    """
    binding = package.get('production_binding')
    if binding is None:
        if recorded is not None:
            raise ValueError('package attachment names Production candidates without a binding')
        return None
    import production_store
    if not any(run['run_id'] == binding['run'] for run in production_store.runs(root)):
        if recorded is not None:
            raise ValueError('package attachment lost its recorded local Production source')
        return None
    from production_workflow import read_run
    _, prepared, consumer, events = read.run(binding['run']) if read else read_run(root, binding['run'])
    if prepared['input_sha256'] != binding['input_sha256'] or execution_contract.content_id(consumer) != binding['consumer_sha256']:
        raise ValueError('attached package differs from its named Production input')
    candidates = sorted(event['sha256'] for event in events if event['event'] == 'candidate'
                        and event['data']['files'][0]['sha256'] == row['result']['sha256'])
    if not candidates:
        raise ValueError('attached package has no matching image candidate in its named Production run; '
                         'inspect the original package and image evidence before attaching it')
    if recorded is not None and (not recorded or not set(recorded).issubset(candidates)):
        raise ValueError('package attachment differs from its retained Production candidate evidence')
    return candidates


def _attachment_reference(root: Path, reference: Any, *, fields: set[str] | None = None) -> Path:
    execution_contract.exact(reference, fields or {'path', 'sha256'}, 'package attachment file')
    execution_contract.sha(reference['sha256'])
    path = execution_contract.local(root, reference['path'])
    if not path.is_file() or sha256_file(path) != reference['sha256']:
        raise ValueError('package attachment file no longer matches its recorded sha256: ' + reference['path'])
    return path


def validate_package_attachment(root: Path, row: dict[str, Any], *, read: StudioRead | None = None) -> dict[str, Any] | None:
    """Read retained attribution evidence; no attachment is needed for an initial package.

    This checks the historical package content and retained evidence, not live
    execution readiness or whether the author's attribution is semantically true.
    """
    root = root.resolve()
    reference = row.get('package_attachment')
    if reference is None:
        return None
    if row.get('production') is not None or row.get('provenance') != 'external-import':
        raise ValueError('package attachment must retain the iteration\'s external-import ownership')
    expected = f"characters/{row['character']}/iterations/{row['iteration_id']}/package-attachment/record.json"
    record_path = _attachment_reference(root, reference)
    if reference['path'] != expected:
        raise ValueError('package attachment belongs to another iteration')
    receipt = execution_contract.load(record_path)
    execution_contract.exact(receipt, {'artifact_type', 'recorded_at', 'actor', 'reason', 'character',
        'iteration_id', 'image_sha256', 'package', 'evidence', 'source', 'companion_files',
        'production_candidates'}, 'package attachment')
    if receipt['artifact_type'] != 'studio-package-attachment' or any(
            receipt[key] != row[key] for key in ('character', 'iteration_id')) \
            or receipt['image_sha256'] != row['result']['sha256']:
        raise ValueError('package attachment does not name this iteration and exact image')
    from studio_activity import chronological
    if not isinstance(receipt['recorded_at'], str) or chronological(receipt['recorded_at']) == float('-inf'):
        raise ValueError('package attachment needs its actual recorded_at time')
    for key in ('actor', 'reason'):
        execution_contract.text(receipt[key], 'package attachment ' + key)
    execution_contract.exact(receipt['source'], {'package', 'evidence', 'companion'}, 'package attachment source')
    for key in ('package', 'evidence'):
        execution_contract.text(receipt['source'][key], 'package attachment source ' + key)
    if receipt['source']['companion'] is not None:
        execution_contract.text(receipt['source']['companion'], 'package attachment source companion')
    base = record_path.parent
    package_path = _attachment_reference(base, receipt['package'],
        fields={'path', 'sha256', 'generation_input_sha256'})
    if receipt['package']['path'] != 'package.json':
        raise ValueError('package attachment must retain package.json')
    expected_package = {**receipt['package'], 'path': package_path.relative_to(root).as_posix()}
    if row.get('package') != expected_package:
        raise ValueError('iteration package differs from its attachment receipt')
    _attachment_reference(root, row['result'])
    evidence_path = _attachment_reference(base, receipt['evidence'])
    if not evidence_path.stat().st_size or evidence_path.stem != 'evidence' or evidence_path.parent != base:
        raise ValueError('package attachment needs its separate retained attribution evidence')
    files = receipt['companion_files']
    if not isinstance(files, list):
        raise ValueError('package attachment companion_files must be a list')
    seen = {'package.json', 'record.json', receipt['evidence']['path']}
    for item in files:
        _attachment_reference(base, item)
        if item['path'] in seen:
            raise ValueError('package attachment contains duplicate file paths')
        seen.add(item['path'])
    assert_public_tree(base)
    if any(path.is_symlink() for path in base.rglob('*')) or {
            path.relative_to(base).as_posix() for path in base.rglob('*') if path.is_file()} != seen:
        raise ValueError('package attachment files differ from its retained manifest')
    if read is None:
        document = execution_contract.load(package_path)
        from verify_generation_payload import verify_content
        verify_content(document, package_root=base)
    else:
        _, document = read._package(row['package'], verify=True)
    if document['generation_input_sha256'] != receipt['package']['generation_input_sha256']:
        raise ValueError('package attachment generation input differs from its package')
    candidates = receipt['production_candidates']
    if candidates is not None:
        if not isinstance(candidates, list):
            raise ValueError('package attachment production_candidates must be unique sorted identifiers')
        for candidate in candidates:
            execution_contract.sha(candidate)
        if candidates != sorted(set(candidates)):
            raise ValueError('package attachment production_candidates must be unique sorted identifiers')
    _package_source_candidates(root, row, document, candidates, read=read)
    return receipt


@mutation
def attach_package(root: Path, character: str, iteration_id: str, *, package: Path,
                   evidence: Path, actor: str, reason: str,
                   package_companion: Path | None = None) -> dict[str, Any]:
    """Attribute an existing original package to one imported image, without re-importing it.

    The immutable receipt says who made this later attribution, when, why and
    from which retained evidence. It is not proof of generation or a new image
    decision. A complete publication survives a failed ledger save for retry.
    """
    with recording_lock(root, character=character):
        root = require_studio(root).resolve()
        home = character_home(root, character)
        rows = read_iterations(home, project=False)
        row = _find(rows, iteration_id)
        validate_recording_target(root, character, row['slot'])
        if row.get('production') is not None or row.get('provenance') != 'external-import':
            raise ValueError('attach-package records attribution for external-import iterations; '
                             'recover a Production candidate\'s package from its retained run evidence')
        if not ITERATION_ID.fullmatch(iteration_id):
            raise ValueError('invalid iteration id')
        actor = execution_contract.text(actor, 'package attachment actor').strip()
        reason = execution_contract.text(reason, 'package attachment reason').strip()
        _attachment_reference(root, row['result'])
        if row.get('package') is not None and row.get('package_attachment') is None:
            raise ValueError('this iteration already records a package; attach-package cannot replace it')
        package, evidence = Path(package).absolute(), Path(evidence).absolute()
        assert_public_path(package); assert_public_path(evidence)
        raw_package, raw_evidence = execution_contract.read(package), execution_contract.read(evidence)
        if not raw_evidence or package.resolve() == evidence.resolve():
            raise ValueError('attach-package needs separate nonempty evidence relating the package to the image')
        document = execution_contract.decode(raw_package)
        if not isinstance(document, dict) or not isinstance(document.get('prepared_reference_set'), dict):
            raise ValueError('attach-package needs the original complete Generation Package')
        destination = execution_contract.local(root,
            f'characters/{character}/iterations/{iteration_id}/package-attachment', exists=False)
        source_companion = Path(package_companion).absolute() if package_companion is not None else None
        from build_generation_payload import validate_generation_package_carrier_paths
        # The original companion may be supplied from a separate saved location;
        # its exact name remains the package's signed relative reference root.
        with tempfile.TemporaryDirectory(prefix='.package-attachment-', dir=destination.parent) as temporary:
            staging = Path(temporary)
            execution_contract.atomic(staging / 'package.json', raw_package)
            evidence_name = 'evidence' + evidence.suffix.lower()
            execution_contract.atomic(staging / evidence_name, raw_evidence)
            if source_companion is None:
                name = validate_generation_package_carrier_paths(document['prepared_reference_set'], package_root=package.parent)
                source_companion = package.parent / name if name is not None else None
            companion_files = []
            if source_companion is not None:
                assert_public_tree(source_companion)
                if source_companion.is_symlink() or not source_companion.is_dir() or not source_companion.name.endswith('.references'):
                    raise ValueError('package companion must be its original named .references directory')
                for path in sorted(source_companion.rglob('*')):
                    if path.is_symlink():
                        raise ValueError('package companion must contain no symbolic links')
                    if path.is_file():
                        relative = source_companion.name + '/' + path.relative_to(source_companion).as_posix()
                        raw = execution_contract.read(path)
                        execution_contract.atomic(execution_contract.local(staging, relative, exists=False), raw)
                        companion_files.append({'path': relative, 'sha256': execution_contract.digest(raw)})
            from verify_generation_payload import verify_content
            verify_content(document, package_root=staging)
            candidates = _package_source_candidates(root, row, document)
            receipt = {'artifact_type': 'studio-package-attachment', 'recorded_at': now(),
                'actor': actor, 'reason': reason, 'character': character, 'iteration_id': iteration_id,
                'image_sha256': row['result']['sha256'],
                'package': {'path': 'package.json', 'sha256': execution_contract.digest(raw_package),
                            'generation_input_sha256': document['generation_input_sha256']},
                'evidence': {'path': evidence_name, 'sha256': execution_contract.digest(raw_evidence)},
                'source': {'package': str(package), 'evidence': str(evidence),
                           'companion': str(source_companion) if source_companion is not None else None},
                'companion_files': companion_files, 'production_candidates': candidates}
            proposed = copy.deepcopy(row)
            proposed['package'] = {**receipt['package'], 'path': (destination / 'package.json').relative_to(root).as_posix()}
            if destination.exists():
                # This is either the same committed attachment, or its complete
                # publication left by an interrupted iterations.jsonl write.
                saved_path = execution_contract.local(destination, 'record.json')
                proposed['package_attachment'] = {'path': saved_path.relative_to(root).as_posix(),
                                                  'sha256': sha256_file(saved_path)}
                if row.get('package_attachment') is not None:
                    validate_package_attachment(root, row)
                saved = validate_package_attachment(root, proposed)
                # Later candidates can corroborate the same source. The first
                # attachment keeps the exact witnesses it recorded at that time.
                receipt['production_candidates'] = saved['production_candidates']
                if {key: value for key, value in saved.items() if key != 'recorded_at'} != {
                        key: value for key, value in receipt.items() if key != 'recorded_at'}:
                    raise ValueError('package attachment already records different source bytes or attribution; '
                                     'retain the existing record and inspect the original evidence')
            else:
                if row.get('package_attachment') is not None:
                    raise ValueError('the recorded package attachment is missing; restore its retained evidence')
                receipt_raw = execution_contract.encoded(receipt)
                execution_contract.atomic(staging / 'record.json', receipt_raw)
                proposed['package_attachment'] = {'path': (destination / 'record.json').relative_to(root).as_posix(),
                                                  'sha256': execution_contract.digest(receipt_raw)}
                execution_contract.publish_directory(staging, destination)
            if row != proposed:
                rows[rows.index(row)] = proposed
                write_iterations(home, rows)
        import studio_activity as activity
        projection = activity.changed(home / 'iterations.jsonl', 'iteration-package-attached',
            subject=character + '/' + iteration_id, revision=proposed['package_attachment']['sha256'],
            details={'character': character, 'iteration_id': iteration_id, 'package': proposed['package']['path'],
                     'attachment': proposed['package_attachment']['path']})
        result = _find(read_iterations(home), iteration_id)
        return result if projection.get('ok') else {**result, 'projection_warning': projection}


@mutation
def accept(root: Path, character: str, iteration_id: str, *, production_selection: str | None = None) -> dict[str, Any]:
    """Accept an explicitly chosen iteration, or recover one exact Production effect."""
    with recording_lock(root, character=character):
        return _record_accept(root, character, iteration_id, production_selection=production_selection)


def acceptance_state(root: Path, character: str, slot: str) -> dict[str, Any] | None:
    """Identify the recorded current acceptance, independently of an interrupted file copy.

    The receipt guards a replacement. Its retained image and the accepted copy
    are verified when the effect is applied or confirmed. Reading the ledger
    here permits recovery after the copy succeeded but its ledger save did not.
    """
    rows = read_iterations(character_home(root, character), project=False)
    accepted = [row for row in rows if row.get('slot') == slot
                and (row.get('adoption_status') if row.get('production') is not None else row.get('status')) == 'accepted']
    if len(accepted) > 1:
        raise ValueError('the Studio records more than one current acceptance for this slot')
    if not accepted:
        return None
    row = accepted[0]
    if not row.get('result') or not row.get('acceptances'):
        raise ValueError('the accepted iteration has no retained image or acceptance receipt')
    return {'iteration_id': row['iteration_id'], 'image_sha256': row['result']['sha256'],
            'acceptance_sha256': execution_contract.content_id(row['acceptances'][-1])}


def verify_accepted_file(root: Path, row: dict[str, Any]) -> None:
    """Verify that this accepted copy and retained image still have their recorded bytes."""
    result = row.get('result')
    if not result or not row.get('accepted_path'):
        raise ValueError('the accepted iteration has no retained image or accepted path')
    for relative in (result['path'], row['accepted_path']):
        actual = sha256_file(execution_contract.local(root, relative))
        if actual != result['sha256']:
            raise ValueError('the accepted image differs from its recorded bytes: ' + relative)


def _record_accept(root: Path, character: str, iteration_id: str, *,
                   production_selection: str | None = None, read: StudioRead | None = None) -> dict[str, Any]:
    read = read or StudioRead(root)
    home = read.home(character)
    rows = copy.deepcopy(read.iterations(character))
    row = _find(rows, iteration_id)
    if row.get("production_diagnostic"):
        raise ValueError("The Production candidate cannot be verified; repair its evidence before adoption")
    selection = None
    if row.get("production") is not None:
        # The Studio accepts the candidate its run currently selects; a selected
        # candidate keeps its selection while the Studio holds it as accepted.
        import production_workflow as workflow
        origin = row["production"]
        _, prepared, _, records = read.run(origin['run'])
        selection = workflow.require_selected(prepared, records, origin["candidate"], run=origin["run"])
    if production_selection is not None:
        from production_diagnostics import ProductionError
        if selection is None or selection['sha256'] != production_selection:
            raise ProductionError('SLOT_ACCEPTANCE_MISMATCH', 'The slot effect differs from the candidate\'s current exact selection.',
                                  phase='acceptance', expected=production_selection,
                                  actual=selection['sha256'] if selection else None)
        saved = [entry for entry in row.get('acceptances', [])
                 if entry.get('production_selection') == selection['sha256']]
        if saved:
            from production_diagnostics import ProductionError
            expected = {'iteration_id': iteration_id, 'image_sha256': row['result']['sha256'],
                        'acceptance_sha256': execution_contract.content_id(saved[0])}
            if len(saved) != 1 or acceptance_state(root, character, row['slot']) != expected:
                raise ProductionError('SLOT_ACCEPTANCE_CONFLICT', 'A later acceptance replaced this operation.',
                    phase='acceptance', run=origin['run'],
                    required_action='Inspect the newer acceptance; retry does not restore an older slot decision.')
            verify_accepted_file(root, row)
            return row
        if selection['data']['selection']['scope'] == 'studio-slot':
            from production_acceptance import validate_slot
            from production_diagnostics import ProductionError
            validate_slot(root, origin['run'], origin['candidate'], selection['data']['selection']['slot'])
            current = acceptance_state(root, character, row['slot'])
            if 'slot_state' not in selection['data'] or current != selection['data']['slot_state']:
                raise ProductionError('SLOT_ACCEPTANCE_CONFLICT', 'The slot changed after this exact selection.',
                    phase='acceptance', run=origin['run'], expected=selection['data'].get('slot_state'), actual=current,
                    required_action='Inspect the current slot and record a new explicit selection if replacement is still intended.')
    if row.get("status") == "accepted":
        verify_accepted_file(root, row)
        if production_selection is None:
            return row
    if row.get("status") == "rejected":
        raise ValueError(f"{iteration_id} was rejected; record a new iteration instead")
    if not row.get("result"):
        raise ValueError(f"{iteration_id} has no result file to accept")
    source = execution_contract.local(root, row['result']['path'])
    image = execution_contract.read(source)
    if execution_contract.digest(image) != row['result']['sha256']:
        raise ValueError(f"the result file of {iteration_id} differs from its recorded bytes")
    replaced = None
    for other in rows:
        if other is not row and other.get("slot") == row["slot"] and other.get("status") == "accepted":
            other["status"] = "superseded"
            other["superseded_by"] = iteration_id
            # The copy under accepted/ belongs to the slot, not to the row: it is
            # about to be replaced or removed, so it is no longer this row's image.
            # The iteration keeps its own copy under iterations/.
            other["accepted_path"] = None
            replaced = other["iteration_id"]
    # An image accepted again is no longer superseded; each acceptance stays in
    # its list with what it replaced, so the slot's history is never rewritten.
    row["status"] = "accepted"
    row.pop("superseded_by", None)
    receipt = {"at": now(), "supersedes": replaced}
    if production_selection is not None:
        receipt['production_selection'] = production_selection
    row["acceptances"] = [*(row.get("acceptances") or []), receipt]
    target = home / "accepted" / f"{row['slot']}{source.suffix}"
    # The new copy is in place before a stale one is removed, so the slot is
    # never without an accepted image.
    execution_contract.atomic(target, image, replace=True)
    # Only the copies of this slot: with slots 'base' and 'base.front' side by
    # side, 'base.front.png' has the stem 'base.front' and is not 'base' output.
    for stale in (home / "accepted").glob(f"{row['slot']}.*"):
        if stale.is_file() and stale.stem == row["slot"] and stale != target:
            stale.unlink()
    row["accepted_path"] = target.relative_to(root).as_posix()
    write_iterations(home, rows)
    import studio_activity as activity
    projection = activity.changed(home / 'iterations.jsonl', 'iteration-'+row['status'], subject=character+'/'+iteration_id,
                     revision=execution_contract.content_id(row),
                     details={'character':character, 'slot':row['slot'], 'iteration_id':iteration_id,
                              'status':row['status']})
    return row if projection.get('ok') else {**row, 'projection_warning': projection}


@mutation
def reject(root: Path, character: str, iteration_id: str, reason: str, *, actor: str) -> dict[str, Any]:
    with recording_lock(root, character=character):
        return _record_reject(root, character, iteration_id, reason, actor=actor)


def _record_reject(root: Path, character: str, iteration_id: str, reason: str, *, actor: str) -> dict[str, Any]:
    home = character_home(root, character)
    rows = read_iterations(home)
    row = _find(rows, iteration_id)
    if not reason.strip() or not actor.strip():
        raise ValueError("rejecting an iteration requires the actual actor and reason")
    if row.get("production_diagnostic"):
        raise ValueError("The Production candidate cannot be verified; its disposition was not changed")
    if row.get("production") is not None:
        # The run records the decision and refuses it for the slot's accepted image;
        # it also rewrites the gallery, which is a rebuildable projection.
        import production_workflow as workflow
        origin = row["production"]
        decision = workflow.draft_disposition(root, origin["run"], origin["candidate"])
        decision.update(actor=actor, reason=reason, review=row.get("review_ref"))
        receipt = workflow.disposition_value(root, origin["run"], decision)
        result = _find(read_iterations(home), iteration_id)
        result["production_decision"] = receipt["sha256"]
        if "projection_warning" in receipt:
            result["projection_warning"] = receipt["projection_warning"]
        return result
    if row.get("status") == "accepted":
        raise ValueError(f"{iteration_id} is accepted; accept another iteration for the slot to supersede it")
    row["actor"] = actor
    row["status"] = "rejected"
    row.pop("superseded_by", None)
    row["rejected_at"] = now()
    row["reason"] = reason.strip()
    write_iterations(home, rows)
    import studio_activity as activity
    projection = activity.changed(home / 'iterations.jsonl', 'iteration-'+row['status'], subject=character+'/'+iteration_id,
                     revision=execution_contract.content_id(row),
                     details={'character':character, 'slot':row['slot'], 'iteration_id':iteration_id,
                              'status':row['status']})
    return row if projection.get('ok') else {**row, 'projection_warning': projection}


def recipe(root: Path, character: str, slot: str, *, iteration: str | None = None) -> dict[str, Any]:
    """Read one saved request and its evidence without selecting or accepting it."""
    evidence = execution_contract

    home = validate_recording_target(root, character, slot, writable=False)
    rows = read_iterations(home)
    if iteration is None:
        matches = [row for row in rows if row.get("slot") == slot and row.get("status") == "accepted"]
        if not matches:
            raise ValueError(f"no accepted iteration for slot {slot!r} of {character!r}")
    else:
        matches = [row for row in rows if row.get("iteration_id") == iteration]
        if not matches:
            raise ValueError(f"no iteration {iteration!r} for {character!r}")
    if len(matches) != 1:
        raise ValueError("recipe selector must identify exactly one recorded iteration")
    row = matches[0]
    if row.get("slot") != slot or row.get("character") != character:
        raise ValueError("recipe iteration does not match the selected character and slot")
    # The Studio keeps the request and its evidence itself, so a Production
    # candidate whose run cannot be read still has a readable recipe; the
    # diagnostic travels with it.
    diagnostic = row.get("production_diagnostic")
    if row.get("status") not in (PRODUCTION_STATUSES if row.get("production") is not None else STATUSES):
        raise ValueError("recipe iteration has an unknown recorded status")
    if not row.get("request"):
        raise ValueError(f"{row['iteration_id']} recorded no request, so its settings cannot be read back")

    witnessed = {}
    bodies = {}
    for name in ("request", "response", "answer", "result", "package"):
        item = row.get(name)
        if item is None:
            continue
        if not isinstance(item, dict) or not {"path", "sha256"} <= set(item):
            raise ValueError("recipe needs a recorded file reference: " + name)
        evidence.sha(item["sha256"])
        raw = evidence.read(evidence.local(root, item["path"]))
        if evidence.digest(raw) != item["sha256"]:
            raise ValueError("recipe evidence changed: " + item["path"])
        witnessed[name] = {"path": item["path"], "sha256": item["sha256"], "size": len(raw)}
        bodies[name] = raw
    sent = evidence.decode(bodies["request"])
    # The layout the transport recorded names the fields that belong to this one
    # run: its identifiers and its seed. A request recorded without one keeps them.
    layout = row.get("request_layout")
    settings = copy.deepcopy(sent)
    if isinstance(sent, dict) and isinstance(layout, dict):
        for path in [*(layout.get("management") or []), layout.get("seed")]:
            if path:
                _remove_field(settings, path)
    response = evidence.decode(bodies["response"]) if "response" in bodies else None
    seed = response.get("seed") if isinstance(response, dict) else None
    if seed is None and isinstance(sent, dict):
        seed = _field(sent, layout.get("seed")) if isinstance(layout, dict) else sent.get("seed")
    return {
        "character": character,
        "slot": slot,
        "iteration_id": row["iteration_id"],
        "source_status": row["status"],
        "production_diagnostic": diagnostic,
        "service": row.get("service"),
        "seed": seed,
        "package": row.get("package"),
        "request": sent,
        "settings": settings,
        "evidence": witnessed,
        "record_sha256": evidence.content_id(row),
        "note": "These settings describe the saved request. A variation uses fresh validation and authorization.",
    }


# Every generated image, in order, with what produced it.

def _remove_field(value: dict[str, Any], path: list[Any]) -> None:
    """Take one field out of a request copy, and the containers it leaves empty."""
    path = list(path)
    # A media position inside a list takes the list: every entry of it is media.
    while path and isinstance(path[-1], int):
        path.pop()
    if not path:
        return
    trail: list[tuple[dict[str, Any], Any]] = []
    node: Any = value
    for part in path[:-1]:
        if not isinstance(node, dict) or part not in node:
            return
        trail.append((node, part))
        node = node[part]
    if not isinstance(node, dict) or path[-1] not in node:
        return
    node.pop(path[-1])
    for parent, key in reversed(trail):
        if parent[key] != {}:
            break
        parent.pop(key)


def sent_text(sent: Any, layout: Any) -> dict[str, Any]:
    """What the recorded request carried, read through the layout the transport recorded with it.

    Without a layout nothing says which field held the prompt, so every field is
    listed as sent and no prompt is named.
    """
    if sent is None:
        return {"request_recorded": False, "prompt_fields_known": False,
                "prompt": None, "negative_prompt": None, "settings": {}, "media": {}}
    if not isinstance(sent, dict) or not isinstance(layout, dict):
        return {"request_recorded": True, "prompt_fields_known": False, "prompt": None, "negative_prompt": None,
                "settings": copy.deepcopy(sent) if isinstance(sent, dict) else {"request": sent}, "media": {}}
    media = {".".join(str(part) for part in item["field"]): _field(sent, item["field"])
             for item in layout.get("media") or [] if isinstance(item, dict) and item.get("field")}
    settings = copy.deepcopy(sent)
    for path in [layout.get("model"), layout.get("operation"), layout.get("primary_text"), layout.get("negative_text"),
                 *(layout.get("management") or []),
                 *(item.get("field") for item in layout.get("media") or [] if isinstance(item, dict))]:
        if path:
            _remove_field(settings, path)
    return {"request_recorded": True, "prompt_fields_known": True,
            "prompt": _field(sent, layout.get("primary_text")),
            "negative_prompt": _field(sent, layout.get("negative_text")),
            "settings": settings, "media": media}


def gallery_index(root: Path, *, read: StudioRead | None = None) -> dict[str, Any]:
    """All recorded artwork, newest first, including local sheet candidates and history."""
    from studio_gallery import build_index
    return build_index(root, read=read)


def gallery_stale(root: Path) -> str | None:
    """Why the complete gallery projection differs from recorded artwork, or None."""
    from studio_gallery import stale
    return stale(root)


def write_gallery(root: Path, out: Path | None = None, *, read: StudioRead | None = None) -> tuple[Path, Path]:
    """Refresh the complete inventory and offline browser view from recorded artwork.

    The gallery owner publishes only changed generated bytes. An explicit output
    has an independent companion directory and rebased links to this Studio.
    """
    from studio_gallery import publish
    import studio_activity as activity
    with activity.publication(activity.artwork_owner(root, out)) as admitted:
        if admitted:
            read = activity.publication_read(root, read)
        return publish(root, gallery_index(root, read=read), out)


# What a session reads first.

# How far a slot's image is along the adoption route, in words.
REFERENCE_STATES = {
    "candidate-accepted": "accepted, not bound to the sheet",
    "sheet-bound": "bound to the sheet",
    "catalog-registered": "bound to the sheet and registered in the catalog",
}
# What the adoption route does next for a slot, in words.
REFERENCE_NEXT = {
    "adopt-with-sheet-scope": "adopt it with adoption_workflow.py to use it as a reference",
    "record-generation-package": "use studio.py attach-package to record the original package and its attribution evidence",
    "adopt-production-candidate": "use production_workflow.py adoption-intent and adopt with separate adoption authorization",
    "record-adoption-result": "repeat production_workflow.py adopt with the same candidate, approval and authorization to record its result",
    "inspect-production-selection": "inspect the Production selection and review diagnostics before adoption",
    "repair-reference": "inspect the reference diagnostic and restore the required retained evidence",
    "accept-candidate": "adoption stopped before accepting the image; repeat the adoption command",
    "bind-sheet": "adoption stopped before binding the sheet; repeat the adoption command",
    "register-pack": "adoption stopped before registering the pack; repeat the adoption command",
    "activate-pack": "adoption stopped before enabling the pack; repeat the adoption command",
}


def _count(number: int, word: str) -> str:
    return f"{number} {word if number == 1 else word + 's'}"


@runtime_snapshot.operation
def status(root: Path) -> str:
    import studio_activity as activity
    read = StudioRead(root)
    projection = activity.refresh(root, read=read)
    document = read.document
    lines = [f"studio {document.get('studio_id')}: {document.get('title')} ({root})", work_ledger.show(root)]
    if not projection.get('ok'):
        lines.append("display/log refresh pending; committed work retained: " + projection['message'])
    for entry in document.get("characters") or []:
        character = entry.get("id")
        home = root / "characters" / str(character)
        rows = read.iterations(str(character)) if home.is_dir() else []
        accepted = {row["slot"]: row for row in rows if row.get("status") == "accepted"}
        # A Production candidate its run did not select is not waiting for a decision.
        candidates = [row for row in rows if row.get("status") == "candidate" and row.get("disposition") != "not_selected"]
        lines.append(f"character {character}: {_count(len(rows), 'generated image')}, "
                     f"{_count(len(accepted), 'slot')} accepted, {_count(len(candidates), 'candidate')} waiting")
        for slot, row in sorted(accepted.items()):
            seed = row.get("seed")
            model = (row.get("service") or {}).get("model_identifier")
            lines.append(f"  accepted {slot}: {row['iteration_id']}, seed {'not recorded' if seed is None else seed}"
                         + (f", model {model}" if model else ""))
        for row in candidates[-5:]:
            lines.append(f"  candidate {row['iteration_id']} for {row.get('slot')}: {row.get('note') or 'no note'}")
        try:
            reference_state = read.reference_index(str(character))
            for item in reference_state["bindings"]:
                state = REFERENCE_STATES.get(item["status"], item["status"])
                step = item["next_action"]
                readiness = item.get('adoption') or {}
                action = REFERENCE_NEXT.get(step, 'next: ' + str(step)) if step else None
                if readiness.get('owner') == 'production' and step in {
                        'accept-candidate', 'bind-sheet', 'register-pack', 'activate-pack'}:
                    action = 'adoption is pending; repeat production_workflow.py adopt for this exact run and candidate'
                lines.append(f"  {item['slot']} as a reference: {state}"
                             + (f"; {action}" if action else ""))
                for diagnostic in readiness.get('diagnostics', []):
                    lines.append('    ' + diagnostic.get('code', 'adoption') + ': ' + diagnostic.get('message', ''))
                    if diagnostic.get('required_action'):
                        lines.append('    ' + diagnostic['required_action'])
            lines.extend("  reference problem: " + error for error in reference_state["errors"])
        except (ValueError, OSError, RuntimeError) as exc:
            lines.append(f"  reference problem: {exc}")
    import story_timeline
    if story_timeline.configured(root):
        path = root / story_timeline.OUTPUT
        state = path.with_suffix('.status.json')
        try:
            projection = read_json(state) if state.is_file() else {}
            label = projection.get('status', 'not built')
            if projection.get('ledger_ok') is False:
                label += '; ledger diagnostics need review'
            lines.append('story timeline: ' + story_timeline.OUTPUT + ' (' + label + '); studio.py sync checks current inputs')
        except (ValueError, OSError, KeyError, TypeError):
            lines.append('story timeline: status unavailable; run studio.py sync')
    persona_changes = persona_change_line(root)
    if persona_changes:
        lines.append(persona_changes)
    return "\n".join(lines)


def persona_change_line(root: Path) -> str | None:
    """The scene materials of this studio that a persona change reaches, and the command that lists them."""
    import scene_persona
    root = root.resolve()
    try:
        scenes = scene_persona.impact(root, uses=False)["scenes"]
    except (ValueError, OSError, KeyError, TypeError, UnicodeError) as exc:
        return f"scene materials cannot be compared with their personas: {exc}"
    states = [row["status"] for row in scenes]
    reached = sum(state in ("stale", "review", "missing") for state in states)
    if not reached:
        return None
    detail = [f"{states.count('stale')} stale"] if "stale" in states else []
    detail += [f"{states.count('missing')} with a source gone"] if "missing" in states else []
    command = shown(python_argv(ROOT / "scripts" / "scene_persona.py", "impact", "--root", str(root)))
    return (f"persona changes reach {_count(reached, 'scene material')}"
            + (f" ({', '.join(detail)})" if detail else "") + f": {command}")


def _explain(exc: BaseException) -> str:
    """One sentence for a refusal or a file the system could not use."""
    if isinstance(exc, FileNotFoundError) and exc.filename:
        return f"{exc.filename} does not exist"
    if isinstance(exc, OSError) and exc.filename:
        return f"{exc.filename} cannot be used: {exc.strerror or exc}"
    return str(exc)


def main(argv: list[str] | None = None) -> int:
    parser = _operation_context.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--studio", type=Path, default=None, help="A directory in the studio (default: the working directory)")
    # The studio may also be named after the command, as the documentation writes it.
    after = _operation_context.ArgumentParser(add_help=False)
    after.add_argument("--studio", type=Path, default=argparse.SUPPRESS,
                       help="A directory in the studio (default: the working directory)")
    commands = parser.add_subparsers(dest="command", required=True)
    init_parser = commands.add_parser("init", help="create a studio")
    init_parser.add_argument("--out", type=Path, required=True)
    init_parser.add_argument("--studio-id", required=True)
    init_parser.add_argument("--title", required=True)
    init_parser.add_argument("--default-render-profile", default="profile-clear-2d-illustration",
                             help="the render profile a request with an open medium starts from")
    init_parser.add_argument("--default-creative-latitude", default="directed")
    init_parser.add_argument("--default-interaction-mode", default="balanced")
    init_parser.add_argument("--default-style-family", help="a style family every request starts from (default: none)")
    commands.add_parser("status", help="the open task, and every character's slots and candidates", parents=[after])
    auth_parser = commands.add_parser("credentials", help="manage one saved API key or environment source per service", parents=[after])
    auth_commands = auth_parser.add_subparsers(dest="auth_command", required=True)
    auth_prepare = auth_commands.add_parser("prepare", parents=[after],
        help="prepare the service's API-key entry or select its environment variable",
        description="Prepare one authentication entry for the service in credentials.json. Existing values and environment sources are retained by default. Give the owner the returned file path and JSON Pointer to fill the API-key string and save. Use --environment or --stored to explicitly change the service's source.")
    auth_prepare.add_argument("service", metavar="SERVICE", help="the service identifier selected by the model offering")
    auth_source = auth_prepare.add_mutually_exclusive_group()
    auth_source.add_argument("--environment", metavar="NAME", help="read this process environment variable whenever execution needs authentication")
    auth_source.add_argument("--stored", action="store_true", help="select the service's api_key string; retain its saved value or prepare an empty string")
    auth_set = auth_commands.add_parser("set", parents=[after],
        help="save or rotate a private value for a service; hidden terminal input is the default")
    auth_set.add_argument("service", metavar="SERVICE", help="the service identifier selected by the model offering")
    auth_input = auth_set.add_mutually_exclusive_group()
    auth_input.add_argument("--stdin", action="store_true", help="read the complete value from standard input without trimming whitespace")
    auth_input.add_argument("--from-env", metavar="NAME", help="import this environment variable's current value into private storage")
    auth_status = auth_commands.add_parser("status", parents=[after],
        help="show each service's authentication source and local availability")
    auth_status.add_argument("service", metavar="SERVICE", nargs="?")
    auth_remove = auth_commands.add_parser("remove", parents=[after],
        help="remove the service's saved key or environment reference from this Studio")
    auth_remove.add_argument("service", metavar="SERVICE")
    character_parser = commands.add_parser("character", help="characters")
    character_commands = character_parser.add_subparsers(dest="character_command", required=True)
    add_parser = character_commands.add_parser("add", help="add a character with a blank sheet", parents=[after])
    add_parser.add_argument("character")
    add_parser.add_argument("--profile", default="")
    iterate_parser = commands.add_parser("iterate", help="record one generated image with what produced it", parents=[after])
    iterate_parser.add_argument("--character", required=True)
    iterate_parser.add_argument("--slot", required=True)
    iterate_parser.add_argument("--result", type=Path, required=True)
    iterate_parser.add_argument("--package", type=Path)
    iterate_parser.add_argument("--package-companion", type=Path, help="the saved package companion directory, kept under its exact name")
    iterate_parser.add_argument("--request", type=Path, help="the request as sent, JSON")
    iterate_parser.add_argument("--response", type=Path, help="what the service answered, JSON")
    iterate_parser.add_argument("--note")
    attach_parser = commands.add_parser("attach-package", parents=[after],
        help="record an imported iteration's original Generation Package with later attribution evidence")
    attach_parser.add_argument("--character", required=True)
    attach_parser.add_argument("--iteration", required=True)
    attach_parser.add_argument("--package", type=Path, required=True)
    attach_parser.add_argument("--package-companion", type=Path,
        help="the original .references directory, discovered beside the package when omitted")
    attach_parser.add_argument("--evidence", type=Path, required=True,
        help="existing evidence relating this package to the exact imported image; retained with the attribution")
    attach_parser.add_argument("--actor", required=True, help="Actual person or agent making the attribution")
    attach_parser.add_argument("--reason", required=True, help="Why the evidence establishes this image's original input package")
    accept_parser = commands.add_parser("accept", help="accept an iteration for its slot; the previous one is superseded", parents=[after])
    accept_parser.add_argument("--character", required=True)
    accept_parser.add_argument("--iteration", required=True)
    reject_parser = commands.add_parser("reject", help="record that an iteration is not used, with the reason; a Production candidate's run records it as not selected", parents=[after])
    reject_parser.add_argument("--character", required=True)
    reject_parser.add_argument("--iteration", required=True)
    reject_parser.add_argument("--reason", required=True)
    reject_parser.add_argument("--actor", required=True, help="Actual person or agent making the non-selection decision")
    recipe_parser = commands.add_parser("recipe", help="read the saved request of the accepted image or an explicitly selected iteration", parents=[after])
    recipe_parser.add_argument("--character", required=True)
    recipe_parser.add_argument("--slot", required=True)
    recipe_parser.add_argument("--iteration", help="read this recorded iteration without accepting it")
    commands.add_parser("sync", help="rebuild the gallery and chronological activity log from their records", parents=[after])
    gallery_parser = commands.add_parser("gallery", help="write gallery.html and gallery.json: every image in order with prompt, model, settings, and seed", parents=[after])
    gallery_parser.add_argument("--out", type=Path, help="Where to write the HTML (default: <studio>/gallery.html); the JSON goes beside it")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            root = init(args.out, args.studio_id, args.title,
                        default_render_profile=args.default_render_profile,
                        default_creative_latitude=args.default_creative_latitude,
                        default_interaction_mode=args.default_interaction_mode,
                        default_style_family=args.default_style_family)
            print(status(root))
            return 0
        root = require_studio(args.studio or Path.cwd())
        if args.command == "status":
            print(status(root))
        elif args.command == "credentials":
            import service_auth
            if args.auth_command == "prepare":
                report = service_auth.prepare(root, args.service,
                    environment=args.environment, stored=args.stored)
            elif args.auth_command == "set":
                report = service_auth.set_from_input(root, args.service,
                    from_env=args.from_env, stdin=args.stdin)
            elif args.auth_command == "remove":
                report = service_auth.remove(root, args.service)
            else:
                report = service_auth.status(root, args.service)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["ok"] else 3
        elif args.command == "character":
            home = add_character(root, args.character, args.profile)
            print(f"added {args.character} at {home}")
        elif args.command == "iterate":
            row = iterate(root, args.character, args.slot, args.result, package=args.package, request=args.request,
                          response=args.response, note=args.note, package_companion=args.package_companion)
            print(json.dumps(row, ensure_ascii=False, indent=2))
        elif args.command == "attach-package":
            row = attach_package(root, args.character, args.iteration, package=args.package,
                package_companion=args.package_companion, evidence=args.evidence, actor=args.actor, reason=args.reason)
            print(json.dumps(row, ensure_ascii=False, indent=2))
        elif args.command == "accept":
            print(json.dumps(accept(root, args.character, args.iteration), ensure_ascii=False, indent=2))
        elif args.command == "reject":
            print(json.dumps(reject(root, args.character, args.iteration, args.reason, actor=args.actor), ensure_ascii=False, indent=2))
        elif args.command == "recipe":
            print(json.dumps(recipe(root, args.character, args.slot, iteration=args.iteration), ensure_ascii=False, indent=2))
        elif args.command == "sync":
            import studio_activity as activity
            report = activity.refresh(root)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report['ok'] else 1
        elif args.command == "gallery":
            html_path, json_path = write_gallery(root, args.out)
            print(f"wrote {html_path} and {json_path}")
    except (ValueError, OSError) as exc:
        if args.command == "credentials":
            from production_diagnostics import ProductionError, exit_code, from_exception
            diagnostic = _operation_context.safe_value(from_exception(exc, phase="credential-management"),
                secrets=_operation_context.current().secrets if _operation_context.current() else ())
            print(json.dumps({"ok": False, "diagnostics": [diagnostic]}, ensure_ascii=False, indent=2))
            print("error: " + diagnostic["message"], file=sys.stderr)
            return exit_code(diagnostic["code"]) if isinstance(exc, ProductionError) else 2
        print(f"error: {_explain(exc)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
