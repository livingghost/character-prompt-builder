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
    python scripts/studio.py accept --studio DIR --character <id> --iteration <it-id>
    python scripts/studio.py reject --studio DIR --character <id> --iteration <it-id> --reason "..."
    python scripts/studio.py recipe --studio DIR --character <id> --slot <slot> [--iteration <it-id>]
    python scripts/studio.py gallery --studio DIR [--out <file.html>]

`--studio` names any directory in the studio, before or after the command, and
defaults to the working directory.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import json
import os
import re
import shlex
import shutil
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import execution_contract  # noqa: E402
import work_ledger  # noqa: E402
# A record is replaced whole: a reader sees the old record or the new one, never a torn one.
from execution_contract import atomic_write_json as write_json, now, sha256_file  # noqa: E402

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
STATUSES = ("candidate", "accepted", "rejected", "superseded")
INIT_COMMAND = 'init --out <dir> --studio-id <id> --title "<title>"'

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
    return f"python {shlex.quote(str(ROOT / 'scripts' / 'studio.py'))} {INIT_COMMAND}"


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
def recording_lock(root: Path) -> Iterator[None]:
    """Hold the project lock that every studio writer, the dispatcher and adoption share."""
    with execution_contract.lock(root):
        yield


# The manifest and the layout.

def _entries(directory: Path) -> list[Path]:
    return [path for path in directory.iterdir() if path.name != execution_contract.LOCK_FILE]


def init(out: Path, studio_id: str, title: str) -> Path:
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
            "created_at": now(),
            "characters": [],
        })
        write_gallery(out)
    return out


def manifest(root: Path) -> dict[str, Any]:
    path = root / MANIFEST
    try:
        value = read_json(path)
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


def listed_characters(root: Path) -> list[str]:
    return [str(entry.get("id")) for entry in manifest(root).get("characters") or [] if isinstance(entry, dict)]


def character_home(root: Path, character: str) -> Path:
    """The directory of a character the manifest lists; a mistyped id is refused by name."""
    home = character_dir(root, character)
    if character not in listed_characters(root) or not home.is_dir():
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

def read_iterations(home: Path) -> list[dict[str, Any]]:
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


def write_iterations(home: Path, rows: list[dict[str, Any]]) -> None:
    raw = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode("utf-8")
    execution_contract.atomic(home / "iterations.jsonl", raw, replace=True)


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
    source = source.resolve()
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


def validate_recording_target(root: Path, character: str, slot: str, *, writable: bool = False) -> Path:
    """Refuse local destination errors before a dispatcher uploads or sends.

    Writability is probed only on a send. A dry run reads the destination without
    writing files. Recording repeats the check under its lock; a later disk or
    permission failure is recoverable from the dispatcher's durable run journal.
    """
    root = root.resolve()
    if require_studio(root) != root:
        raise ValueError(f"{root} is not a studio root")
    home = character_home(root, character)
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
    read_iterations(home)
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


def iterate(root: Path, character: str, slot: str, result: Path, *, package: Path | None, request: Path | None,
            response: Path | None, note: str | None, service: dict[str, Any] | None = None,
            package_companion: Path | None = None, layout: dict[str, Any] | None = None,
            answer: Path | None = None) -> dict[str, Any]:
    with recording_lock(root):
        return _record_iteration(root, character, slot, result, package=package, request=request,
                                 response=response, note=note, service=service,
                                 package_companion=package_companion, layout=layout, answer=answer)


def _record_iteration(root: Path, character: str, slot: str, result: Path, *, package: Path | None,
                      request: Path | None, response: Path | None, note: str | None,
                      service: dict[str, Any] | None = None,
                      package_companion: Path | None = None,
                      layout: dict[str, Any] | None = None,
                      answer: Path | None = None) -> dict[str, Any]:
    home = validate_recording_target(root, character, slot)
    _check_inputs({"result": result, "package": package, "request": request, "response": response,
                   "answer": answer}, package_companion)
    if layout is not None:
        check_request_layout(layout, read_json(Path(request)) if request is not None else None)
    rows = read_iterations(home)
    iteration_id = next_iteration_id(home, rows)
    kept_answer = _keep_answer(root, home, rows, iteration_id, answer, response) if answer is not None else None
    row: dict[str, Any] = {
        "iteration_id": iteration_id,
        "at": now(),
        "character": character,
        "slot": slot,
        "status": "candidate",
        "acceptances": [],
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
    write_gallery(root)
    return row


def _find(rows: list[dict[str, Any]], iteration_id: str) -> dict[str, Any]:
    found = next((row for row in rows if row.get("iteration_id") == iteration_id), None)
    if found is None:
        raise ValueError(f"no iteration {iteration_id!r}")
    return found


def accept(root: Path, character: str, iteration_id: str) -> dict[str, Any]:
    with recording_lock(root):
        return _record_accept(root, character, iteration_id)


def _record_accept(root: Path, character: str, iteration_id: str) -> dict[str, Any]:
    home = character_home(root, character)
    rows = read_iterations(home)
    row = _find(rows, iteration_id)
    if row.get("status") == "accepted":
        raise ValueError(f"{iteration_id} is already accepted")
    if row.get("status") == "rejected":
        raise ValueError(f"{iteration_id} was rejected; record a new iteration instead")
    if not row.get("result"):
        raise ValueError(f"{iteration_id} has no result file to accept")
    source = root / row["result"]["path"]
    if not source.is_file():
        raise ValueError(f"the result file of {iteration_id} is missing: {row['result']['path']}")
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
    row["acceptances"] = [*(row.get("acceptances") or []), {"at": now(), "supersedes": replaced}]
    target = home / "accepted" / f"{row['slot']}{source.suffix}"
    # The new copy is in place before a stale one is removed, so the slot is
    # never without an accepted image.
    execution_contract.atomic(target, source.read_bytes(), replace=True)
    # Only the copies of this slot: with slots 'base' and 'base.front' side by
    # side, 'base.front.png' has the stem 'base.front' and is not 'base' output.
    for stale in (home / "accepted").glob(f"{row['slot']}.*"):
        if stale.is_file() and stale.stem == row["slot"] and stale != target:
            stale.unlink()
    row["accepted_path"] = target.relative_to(root).as_posix()
    write_iterations(home, rows)
    write_gallery(root)
    return row


def reject(root: Path, character: str, iteration_id: str, reason: str) -> dict[str, Any]:
    with recording_lock(root):
        return _record_reject(root, character, iteration_id, reason)


def _record_reject(root: Path, character: str, iteration_id: str, reason: str) -> dict[str, Any]:
    home = character_home(root, character)
    rows = read_iterations(home)
    row = _find(rows, iteration_id)
    if row.get("status") == "accepted":
        raise ValueError(f"{iteration_id} is accepted; accept another iteration for the slot to supersede it")
    if not reason.strip():
        raise ValueError("rejecting an iteration needs the reason")
    row["status"] = "rejected"
    row.pop("superseded_by", None)
    row["rejected_at"] = now()
    row["reason"] = reason.strip()
    write_iterations(home, rows)
    write_gallery(root)
    return row


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
    if row.get("status") not in STATUSES:
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


def gallery_index(root: Path) -> dict[str, Any]:
    """Every iteration of every character, oldest first, with prompt, model, settings, seed, and result."""
    document = manifest(root)
    entries: list[dict[str, Any]] = []
    for character in [item.get("id") for item in document.get("characters") or [] if isinstance(item, dict)]:
        home = root / "characters" / str(character)
        if not home.is_dir():
            continue
        for row in read_iterations(home):
            sent = read_json(root / row["request"]["path"]) if row.get("request") else None
            package = read_json(root / row["package"]["path"]) if row.get("package") else None
            payload = (package or {}).get("generation_payload") if isinstance(package, dict) else None
            service_row = row.get("service") or {}
            model_record = service_row.get("model")
            if model_record is None and isinstance(package, dict):
                model_record = (payload or {}).get("model") or package.get("upscaler_model")
            entries.append({
                "character": character,
                "iteration_id": row.get("iteration_id"),
                "model_record": model_record,
                "dialect": service_row.get("dialect"),
                "at": row.get("at"),
                "slot": row.get("slot"),
                "status": row.get("status"),
                "acceptances": row.get("acceptances") or [],
                "superseded_by": row.get("superseded_by"),
                "service": row.get("service"),
                "seed": row.get("seed"),
                **sent_text(sent, row.get("request_layout")),
                "result": (row.get("result") or {}).get("path"),
                "result_sha256": (row.get("result") or {}).get("sha256"),
                "package": (row.get("package") or {}).get("path"),
                "note": row.get("note"),
                "reason": row.get("reason"),
            })
    entries.sort(key=lambda entry: (str(entry.get("at") or ""), str(entry.get("iteration_id") or "")))
    return {"studio_id": document.get("studio_id"), "title": document.get("title"), "generated_at": now(), "entries": entries}


def _escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _fact(label: str, value: Any, missing: str | None = "not recorded") -> str:
    """One labelled fact; an unknown value says so, or is left out when `missing` is None."""
    if value is None or value == "":
        return "" if missing is None else f"<b>{label}</b> {missing}"
    return f"<b>{label}</b> {_escape(value)}"


def _text_block(entry: dict[str, Any]) -> str:
    if not entry.get("request_recorded"):
        return "<p><b>request</b> not recorded</p>"
    if not entry.get("prompt_fields_known"):
        return "<p><b>request</b> every field as sent is listed below; the record does not say which field held the prompt</p>"
    parts = []
    for label, key in (("prompt", "prompt"), ("negative", "negative_prompt")):
        if entry.get(key) is None:
            parts.append(f"<p><b>{label}</b> none sent</p>")
        else:
            parts.append(f"<p><b>{label}</b></p><pre>{_escape(entry[key])}</pre>")
    return "\n    ".join(parts)


def _history(entry: dict[str, Any]) -> str:
    parts = [f"generated {_escape(entry.get('at'))}"]
    for acceptance in entry.get("acceptances") or []:
        replaced = acceptance.get("supersedes") if isinstance(acceptance, dict) else None
        parts.append(f"accepted {_escape((acceptance or {}).get('at'))}" + (f" in place of {_escape(replaced)}" if replaced else ""))
    if entry.get("superseded_by"):
        parts.append(f"superseded by {_escape(entry['superseded_by'])}")
    return "; ".join(parts)


def render_gallery(index: dict[str, Any]) -> str:
    """One page, no scripts, images by relative path from the studio root."""
    rows = []
    for entry in index["entries"]:
        settings = "".join(
            f"<tr><th>{_escape(key)}</th><td>{_escape(json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value)}</td></tr>"
            for key, value in sorted((entry.get("settings") or {}).items())
        )
        media = "".join(
            f"<tr><th>{_escape(key)}</th><td>{_escape(json.dumps(value, ensure_ascii=False))}</td></tr>"
            for key, value in sorted((entry.get("media") or {}).items())
        )
        service = entry.get("service") or {}
        image = (f'<a href="{_escape(entry["result"])}"><img src="{_escape(entry["result"])}" alt="{_escape(entry["iteration_id"])}"></a>'
                 if entry.get("result") else "<div class=\"none\">no result file</div>")
        origin = " ".join(fact for fact in (
            _fact("model", service.get("model_identifier")),
            _fact("service", service.get("id"), None),
            _fact("observed", service.get("observed_at"), None),
        ) if fact)
        record = " ".join(fact for fact in (
            _fact("model record", entry.get("model_record")),
            _fact("family", entry.get("dialect"), None),
            _fact("seed", entry.get("seed")),
        ) if fact)
        rows.append(f"""
<section class="iteration {_escape(entry.get('status'))}">
  <div class="image">{image}</div>
  <div class="facts">
    <h2>{_escape(entry.get('character'))} / {_escape(entry.get('slot'))} / {_escape(entry.get('iteration_id'))} <span class="status">{_escape(entry.get('status'))}</span></h2>
    <p class="when">{_history(entry)}</p>
    <p>{origin}</p>
    <p>{record}</p>
    {_text_block(entry)}
    <table>{settings}{media}</table>
    {('<p class="note">' + _escape(entry.get('note')) + '</p>') if entry.get('note') else ''}
    {('<p class="note">rejected: ' + _escape(entry.get('reason')) + '</p>') if entry.get('reason') else ''}
    <p class="hash">{_escape(entry.get('result_sha256'))}</p>
  </div>
</section>""")
    count = len(index["entries"])
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>{_escape(index.get('title'))}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 1.5rem; color: #222; background: #fafafa; }}
h1 {{ font-size: 1.4rem; }} h2 {{ font-size: 1rem; margin: 0 0 .25rem; }}
.iteration {{ display: grid; grid-template-columns: 320px 1fr; gap: 1rem; padding: 1rem; margin: 0 0 1rem; background: #fff; border: 1px solid #ddd; }}
.iteration.accepted {{ border-color: #2a7; }} .iteration.rejected {{ opacity: .6; }} .iteration.superseded {{ border-style: dashed; }}
.image img {{ max-width: 320px; max-height: 320px; display: block; }} .none {{ color: #999; }}
.status {{ font-weight: normal; color: #666; }} .when, .hash {{ color: #777; font-size: .85rem; }}
pre {{ white-space: pre-wrap; background: #f4f4f4; padding: .5rem; margin: 0 0 .5rem; }}
table {{ border-collapse: collapse; font-size: .9rem; }} th {{ text-align: left; padding: .1rem .6rem .1rem 0; color: #555; }} td {{ padding: .1rem 0; }}
.note {{ font-style: italic; }}
</style></head>
<body><h1>{_escape(index.get('title'))} ({_escape(index.get('studio_id'))}): {count} {'image' if count == 1 else 'images'}, generated {_escape(index.get('generated_at'))}</h1>
{''.join(rows)}
</body></html>
"""


def gallery_stale(root: Path) -> str | None:
    """Why the gallery on disk is not the one the records would produce, or None."""
    json_path = root / "gallery.json"
    if not json_path.is_file() or not (root / "gallery.html").is_file():
        return "gallery.json or gallery.html is missing"
    try:
        held = read_json(json_path)
    except (ValueError, json.JSONDecodeError) as exc:
        return f"gallery.json: {exc}"
    try:
        expected = gallery_index(root)["entries"]
    except (ValueError, OSError) as exc:
        return f"the records cannot be read into a gallery: {exc}"
    if not isinstance(held, dict) or held.get("entries") != expected:
        return "gallery.json does not list what the iteration records hold"
    return None


def write_gallery(root: Path, out: Path | None = None) -> tuple[Path, Path]:
    """Write gallery.json and gallery.html in the studio root, or the HTML where asked with its JSON beside it.

    Every command that records something calls this, so the gallery is current
    without anyone asking for it; the command exists for a record edited by hand.
    """
    with recording_lock(root):
        index = gallery_index(root)
        html_path = (out or (root / "gallery.html")).resolve()
        json_path = html_path.with_suffix(".json")
        write_json(json_path, index)
        execution_contract.atomic(html_path, render_gallery(index).encode("utf-8"), replace=True)
    return html_path, json_path


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
    "accept-candidate": "adoption stopped before accepting the image; repeat the adoption command",
    "bind-sheet": "adoption stopped before binding the sheet; repeat the adoption command",
    "register-pack": "adoption stopped before registering the pack; repeat the adoption command",
    "activate-pack": "adoption stopped before enabling the pack; repeat the adoption command",
}


def _count(number: int, word: str) -> str:
    return f"{number} {word if number == 1 else word + 's'}"


def status(root: Path) -> str:
    document = manifest(root)
    lines = [f"studio {document.get('studio_id')}: {document.get('title')} ({root})", work_ledger.show(root)]
    for entry in document.get("characters") or []:
        character = entry.get("id")
        home = root / "characters" / str(character)
        rows = read_iterations(home) if home.is_dir() else []
        accepted = {row["slot"]: row for row in rows if row.get("status") == "accepted"}
        candidates = [row for row in rows if row.get("status") == "candidate"]
        lines.append(f"character {character}: {_count(len(rows), 'generated image')}, "
                     f"{_count(len(accepted), 'slot')} accepted, {_count(len(candidates), 'candidate')} waiting")
        for slot, row in sorted(accepted.items()):
            seed = row.get("seed")
            model = (row.get("service") or {}).get("model_identifier")
            lines.append(f"  accepted {slot}: {row['iteration_id']}, seed {'not recorded' if seed is None else seed}"
                         + (f", model {model}" if model else ""))
        for row in candidates[-5:]:
            lines.append(f"  candidate {row['iteration_id']} for {row.get('slot')}: {row.get('note') or 'no note'}")
        from adoption_workflow import reference_index
        try:
            reference_state = reference_index(root, str(character))
            for item in reference_state["bindings"]:
                state = REFERENCE_STATES.get(item["status"], item["status"])
                step = item["next_action"]
                lines.append(f"  {item['slot']} as a reference: {state}"
                             + (f"; {REFERENCE_NEXT.get(step, 'next: ' + str(step))}" if step else ""))
            lines.extend("  reference problem: " + error for error in reference_state["errors"])
        except (ValueError, OSError, RuntimeError) as exc:
            lines.append(f"  reference problem: {exc}")
    return "\n".join(lines)


def _explain(exc: BaseException) -> str:
    """One sentence for a refusal or a file the system could not use."""
    if isinstance(exc, FileNotFoundError) and exc.filename:
        return f"{exc.filename} does not exist"
    if isinstance(exc, OSError) and exc.filename:
        return f"{exc.filename} cannot be used: {exc.strerror or exc}"
    return str(exc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--studio", type=Path, default=None, help="A directory in the studio (default: the working directory)")
    # The studio may also be named after the command, as the documentation writes it.
    after = argparse.ArgumentParser(add_help=False)
    after.add_argument("--studio", type=Path, default=argparse.SUPPRESS,
                       help="A directory in the studio (default: the working directory)")
    commands = parser.add_subparsers(dest="command", required=True)
    init_parser = commands.add_parser("init", help="create a studio")
    init_parser.add_argument("--out", type=Path, required=True)
    init_parser.add_argument("--studio-id", required=True)
    init_parser.add_argument("--title", required=True)
    commands.add_parser("status", help="the open task, and every character's slots and candidates", parents=[after])
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
    accept_parser = commands.add_parser("accept", help="accept an iteration for its slot; the previous one is superseded", parents=[after])
    accept_parser.add_argument("--character", required=True)
    accept_parser.add_argument("--iteration", required=True)
    reject_parser = commands.add_parser("reject", help="mark an iteration rejected, with the reason", parents=[after])
    reject_parser.add_argument("--character", required=True)
    reject_parser.add_argument("--iteration", required=True)
    reject_parser.add_argument("--reason", required=True)
    recipe_parser = commands.add_parser("recipe", help="read the saved request of the accepted image or an explicitly selected candidate", parents=[after])
    recipe_parser.add_argument("--character", required=True)
    recipe_parser.add_argument("--slot", required=True)
    recipe_parser.add_argument("--iteration", help="read this recorded iteration without accepting it")
    gallery_parser = commands.add_parser("gallery", help="write gallery.html and gallery.json: every image in order with prompt, model, settings, and seed", parents=[after])
    gallery_parser.add_argument("--out", type=Path, help="Where to write the HTML (default: <studio>/gallery.html); the JSON goes beside it")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            root = init(args.out, args.studio_id, args.title)
            print(status(root))
            return 0
        root = require_studio(args.studio or Path.cwd())
        if args.command == "status":
            print(status(root))
        elif args.command == "character":
            home = add_character(root, args.character, args.profile)
            print(f"added {args.character} at {home}")
        elif args.command == "iterate":
            row = iterate(root, args.character, args.slot, args.result, package=args.package, request=args.request,
                          response=args.response, note=args.note, package_companion=args.package_companion)
            print(json.dumps(row, ensure_ascii=False, indent=2))
        elif args.command == "accept":
            print(json.dumps(accept(root, args.character, args.iteration), ensure_ascii=False, indent=2))
        elif args.command == "reject":
            print(json.dumps(reject(root, args.character, args.iteration, args.reason), ensure_ascii=False, indent=2))
        elif args.command == "recipe":
            print(json.dumps(recipe(root, args.character, args.slot, iteration=args.iteration), ensure_ascii=False, indent=2))
        elif args.command == "gallery":
            html_path, json_path = write_gallery(root, args.out)
            print(f"wrote {html_path} and {json_path}")
    except (ValueError, OSError) as exc:
        print(f"error: {_explain(exc)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
