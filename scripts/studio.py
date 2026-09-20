#!/usr/bin/env python3
"""A studio: where one body of character work lives, with its trail.

A studio holds characters, each with its sheet, every image ever generated for
it, and which of those images are accepted for which slot. Every generation is
an iteration: the exact request that was sent, what came back, the file, and the
package it was built from, so that an image can be regenerated later with the
same settings and a quality that drifted can be traced to what changed. An
accepted image is superseded, never overwritten, when the owner changes their
mind, so the history of a slot is readable end to end.

The studio also carries the open task and the trail of tasks (see
work_ledger.py), so a session that lost its context reads where the work stands
and continues.

    python scripts/studio.py init --out DIR --studio-id ID --title "..."
    python scripts/studio.py status [--studio DIR]
    python scripts/studio.py character add <id> [--profile general|humanoid|anthro|<path>]
    python scripts/studio.py iterate --character <id> --slot <slot> --result <file>
        [--package <file>] [--package-companion <dir>] [--request <file>] [--response <file>] [--note "..."]
    python scripts/studio.py accept --character <id> --iteration <it-id>
    python scripts/studio.py reject --character <id> --iteration <it-id> --reason "..."
    python scripts/studio.py recipe --character <id> --slot <slot>
    python scripts/studio.py gallery [--out <file.html>]
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import work_ledger  # noqa: E402

MANIFEST = "studio.json"
LOCK = "studio.lock"
STUDIO_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]+$")
CHARACTER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SLOT = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
ITERATION_ID = re.compile(r"^it-([0-9]+)$")
DIRECTORIES = ("characters", "packages", "runs", "prompts", "work")
CHARACTER_DIRECTORIES = ("sheet", "iterations", "accepted")
STATUSES = ("candidate", "accepted", "rejected", "superseded")
# Keys of a sent request that name this run and not the recipe: a fresh run gets its own.
RUN_ONLY_KEYS = ("seed", "taskUUID", "uploadEndpoint", "ttl", "includeCost")

README = {
    "characters": "One directory per character: sheet/ (the Character Sheet), iterations/ (every generated image with the exact request and response), accepted/ (the image accepted for each slot), iterations.jsonl (the record of each iteration and its status).\n",
    "packages": "Generation Packages built for images of this studio, referenced by iterations.\n",
    "runs": "What was sent to a service and what came back, when a run is recorded outside an iteration.\n",
    "prompts": "Reviewed prompt artifacts and prompt-only work that belongs to no single iteration.\n",
    "work": "The open task (current.json) and the trail of tasks (ledger.jsonl). A session reads current.json first.\n",
}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def studio_root(start: Path) -> Path | None:
    """The studio a directory belongs to: the nearest ancestor holding the manifest."""
    for candidate in (start, *start.parents):
        if (candidate / MANIFEST).is_file():
            return candidate
    return None


def require_studio(start: Path) -> Path:
    found = studio_root(start.resolve())
    if found is None:
        raise ValueError(f"{start} is not in a studio; {ROOT / 'scripts' / 'studio.py'} init creates one")
    return found


@contextlib.contextmanager
def recording_lock(root: Path, timeout: float = 60.0) -> Iterator[None]:
    """Hold the studio while something is recorded, so two recorders never interleave.

    A studio is a directory, and the commands that record read the whole record,
    copy files into it, and write it back; two of them at once lose one another's
    rows. The lock is a file the first recorder creates exclusively: the others
    wait for it to go. A recorder killed mid-write leaves the file behind, and the
    message names the file to delete.
    """
    path = root / LOCK
    deadline = time.monotonic() + timeout
    while True:
        try:
            handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise ValueError(f"another recorder holds {path}; delete this file if nothing is recording") from None
            time.sleep(0.05)
            continue
        break
    os.close(handle)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


# The manifest and the layout.

def init(out: Path, studio_id: str, title: str) -> Path:
    if not STUDIO_ID.fullmatch(studio_id):
        raise ValueError("studio id must be at least two characters of letters, digits, dot, underscore or dash")
    if not title.strip():
        raise ValueError("a studio needs a title")
    out = out.resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"{out} exists and is not empty")
    for name in DIRECTORIES:
        (out / name).mkdir(parents=True, exist_ok=True)
        (out / name / "README.md").write_text(README[name], encoding="utf-8", newline="\n")
    write_json(out / MANIFEST, {
        "studio_id": studio_id,
        "title": title.strip(),
        "created_at": now(),
        "characters": [],
    })
    write_gallery(out)
    return out


def manifest(root: Path) -> dict[str, Any]:
    value = read_json(root / MANIFEST)
    if not isinstance(value, dict):
        raise ValueError(f"{root / MANIFEST}: not an object")
    return value


def character_dir(root: Path, character: str) -> Path:
    if not CHARACTER_ID.fullmatch(character):
        raise ValueError("character id must be one or more characters of letters, digits, dot, underscore or dash")
    return root / "characters" / character


def add_character(root: Path, character: str, profile: str) -> Path:
    home = character_dir(root, character)
    if home.exists():
        raise ValueError(f"character {character!r} already exists")
    for name in CHARACTER_DIRECTORIES:
        (home / name).mkdir(parents=True)
    (home / "iterations.jsonl").write_text("", encoding="utf-8")
    from character_sheet import initialize_sidecar

    initialize_sidecar(home / "sheet", profile=profile)
    document = manifest(root)
    document.setdefault("characters", []).append({"id": character, "added_at": now()})
    write_json(root / MANIFEST, document)
    write_gallery(root)
    return home


# Iterations: one record per generated image.

def read_iterations(home: Path) -> list[dict[str, Any]]:
    path = home / "iterations.jsonl"
    if not path.is_file():
        return []
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{number}: not an object")
            rows.append(value)
    return rows


def write_iterations(home: Path, rows: list[dict[str, Any]]) -> None:
    path = home / "iterations.jsonl"
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8", newline="\n")


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


def validate_recording_target(root: Path, character: str, slot: str, *, writable: bool = False) -> Path:
    """Refuse local destination errors before a dispatcher uploads or sends.

    Writability is probed only on a send. A dry run reads the destination without
    writing files. Recording repeats the check under its lock; a later disk or
    permission failure is recoverable from the dispatcher's durable run journal.
    """
    root = root.resolve()
    if require_studio(root) != root:
        raise ValueError(f"{root} is not a studio root")
    home = character_dir(root, character)
    characters = manifest(root).get("characters", [])
    if not home.is_dir() or not any(isinstance(row, dict) and row.get("id") == character for row in characters):
        raise ValueError(f"character {character!r} is not in this studio")
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
            package_companion: Path | None = None) -> dict[str, Any]:
    with recording_lock(root):
        return _record_iteration(root, character, slot, result, package=package, request=request,
                                 response=response, note=note, service=service,
                                 package_companion=package_companion)


def _record_iteration(root: Path, character: str, slot: str, result: Path, *, package: Path | None,
                      request: Path | None, response: Path | None, note: str | None,
                      service: dict[str, Any] | None = None,
                      package_companion: Path | None = None) -> dict[str, Any]:
    home = validate_recording_target(root, character, slot)
    rows = read_iterations(home)
    iteration_id = next_iteration_id(home, rows)
    row: dict[str, Any] = {
        "iteration_id": iteration_id,
        "at": now(),
        "character": character,
        "slot": slot,
        "status": "candidate",
        "supersedes": None,
        "result": _keep(root, home, iteration_id, result, "result"),
        "package": _keep(root, home, iteration_id, package, "package"),
        "request": _keep(root, home, iteration_id, request, "request"),
        "response": _keep(root, home, iteration_id, response, "response"),
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
            if row["seed"] is None:
                row["seed"] = sent.get("seed")
            if row["service"] is None and sent.get("model"):
                row["service"] = {"id": None, "model_identifier": sent.get("model"), "observed_at": None, "schema_snapshot": None}
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
    home = character_dir(root, character)
    rows = read_iterations(home)
    row = _find(rows, iteration_id)
    if row.get("status") == "accepted":
        raise ValueError(f"{iteration_id} is already accepted")
    if row.get("status") == "rejected":
        raise ValueError(f"{iteration_id} was rejected; record a new iteration instead")
    if not row.get("result"):
        raise ValueError(f"{iteration_id} has no result file to accept")
    for other in rows:
        if other.get("slot") == row["slot"] and other.get("status") == "accepted":
            other["status"] = "superseded"
            other["superseded_by"] = iteration_id
            # The copy under accepted/ belongs to the slot, not to the row: it is
            # about to be replaced or removed, so it is no longer this row's image.
            # The iteration keeps its own copy under iterations/.
            other["accepted_path"] = None
            row["supersedes"] = other["iteration_id"]
    row["status"] = "accepted"
    row["accepted_at"] = now()
    source = root / row["result"]["path"]
    target = home / "accepted" / f"{row['slot']}{source.suffix}"
    # Only the copies of this slot: with slots 'base' and 'base.front' side by
    # side, 'base.front.png' has the stem 'base.front' and is not 'base' output.
    for stale in (home / "accepted").glob(f"{row['slot']}.*"):
        if stale.is_file() and stale.stem == row["slot"]:
            stale.unlink()
    shutil.copyfile(source, target)
    row["accepted_path"] = target.relative_to(root).as_posix()
    write_iterations(home, rows)
    write_gallery(root)
    return row


def reject(root: Path, character: str, iteration_id: str, reason: str) -> dict[str, Any]:
    with recording_lock(root):
        return _record_reject(root, character, iteration_id, reason)


def _record_reject(root: Path, character: str, iteration_id: str, reason: str) -> dict[str, Any]:
    home = character_dir(root, character)
    rows = read_iterations(home)
    row = _find(rows, iteration_id)
    if row.get("status") == "accepted":
        raise ValueError(f"{iteration_id} is accepted; accept another iteration for the slot to supersede it")
    if not reason.strip():
        raise ValueError("rejecting an iteration needs the reason")
    row["status"] = "rejected"
    row["rejected_at"] = now()
    row["reason"] = reason.strip()
    write_iterations(home, rows)
    write_gallery(root)
    return row


def recipe(root: Path, character: str, slot: str) -> dict[str, Any]:
    """What to send to get an image like the accepted one for a slot: the request minus what names a run."""
    home = character_dir(root, character)
    rows = read_iterations(home)
    accepted = next((row for row in rows if row.get("slot") == slot and row.get("status") == "accepted"), None)
    if accepted is None:
        raise ValueError(f"no accepted iteration for slot {slot!r} of {character!r}")
    if not accepted.get("request"):
        raise ValueError(f"{accepted['iteration_id']} recorded no request, so its settings cannot be read back")
    sent = read_json(root / accepted["request"]["path"])
    settings = {key: value for key, value in sent.items() if key not in RUN_ONLY_KEYS} if isinstance(sent, dict) else sent
    return {
        "character": character,
        "slot": slot,
        "iteration_id": accepted["iteration_id"],
        "service": accepted.get("service"),
        "seed": accepted.get("seed"),
        "package": accepted.get("package"),
        "settings": settings,
        "note": "send these settings again for the same look; a different seed gives a variation, the same seed a reproduction where the service allows it",
    }


# Every generated image, in order, with what produced it.

# Request keys that are not settings of the image: the model and text are shown
# on their own, media are shown by role, and the envelope names the run.
NOT_A_SETTING = ("model", "positivePrompt", "negativePrompt", "inputs", "taskType", "taskUUID", "deliveryMethod")


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
            prompt = negative = None
            settings: dict[str, Any] = {}
            media: dict[str, Any] = {}
            if isinstance(sent, dict):
                prompt = sent.get("positivePrompt")
                negative = sent.get("negativePrompt")
                settings = {key: value for key, value in sent.items() if key not in NOT_A_SETTING}
                media = sent.get("inputs") if isinstance(sent.get("inputs"), dict) else {}
            if prompt is None and isinstance(payload, dict):
                prompt = payload.get("prompt")
                negative = payload.get("negative_prompt") or None
                if not settings and isinstance(payload.get("parameters"), dict):
                    settings = dict(payload["parameters"])
            service_row = row.get("service") or {}
            model_record = service_row.get("model")
            dialect = service_row.get("dialect")
            if model_record is None and isinstance(package, dict):
                model_record = (payload or {}).get("model") or package.get("upscaler_model")
            entries.append({
                "character": character,
                "iteration_id": row.get("iteration_id"),
                "model_record": model_record,
                "dialect": dialect,
                "at": row.get("at"),
                "slot": row.get("slot"),
                "status": row.get("status"),
                "supersedes": row.get("supersedes"),
                "service": row.get("service"),
                "seed": row.get("seed"),
                "prompt": prompt,
                "negative_prompt": negative,
                "settings": settings,
                "media": media,
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
        rows.append(f"""
<section class="iteration {_escape(entry.get('status'))}">
  <div class="image">{image}</div>
  <div class="facts">
    <h2>{_escape(entry.get('character'))} / {_escape(entry.get('slot'))} / {_escape(entry.get('iteration_id'))} <span class="status">{_escape(entry.get('status'))}</span></h2>
    <p class="when">{_escape(entry.get('at'))}{(' supersedes ' + _escape(entry['supersedes'])) if entry.get('supersedes') else ''}</p>
    <p><b>record</b> {_escape(entry.get('model_record'))}{(' <b>family</b> ' + _escape(entry.get('dialect'))) if entry.get('dialect') else ''}</p>
    <p><b>model</b> {_escape(service.get('model_identifier'))} <b>service</b> {_escape(service.get('id'))} <b>observed</b> {_escape(service.get('observed_at'))} <b>seed</b> {_escape(entry.get('seed'))}</p>
    <p><b>prompt</b></p><pre>{_escape(entry.get('prompt'))}</pre>
    {('<p><b>negative</b></p><pre>' + _escape(entry.get('negative_prompt')) + '</pre>') if entry.get('negative_prompt') else ''}
    <table>{settings}{media}</table>
    {('<p class="note">' + _escape(entry.get('note')) + '</p>') if entry.get('note') else ''}
    {('<p class="note">rejected: ' + _escape(entry.get('reason')) + '</p>') if entry.get('reason') else ''}
    <p class="hash">{_escape(entry.get('result_sha256'))}</p>
  </div>
</section>""")
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
<body><h1>{_escape(index.get('title'))} ({_escape(index.get('studio_id'))}): {len(index['entries'])} iterations, generated {_escape(index.get('generated_at'))}</h1>
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
    if not isinstance(held, dict) or held.get("entries") != gallery_index(root)["entries"]:
        return "gallery.json does not list what the iteration records hold"
    return None


def write_gallery(root: Path, out: Path | None = None) -> tuple[Path, Path]:
    """Write gallery.json and gallery.html in the studio root, or the HTML where asked with its JSON beside it.

    Every command that records something calls this, so the gallery is current
    without anyone asking for it; the command exists for a record edited by hand.
    """
    index = gallery_index(root)
    html_path = (out or (root / "gallery.html")).resolve()
    json_path = html_path.with_suffix(".json")
    write_json(json_path, index)
    html_path.write_text(render_gallery(index), encoding="utf-8", newline="\n")
    return html_path, json_path


# What a session reads first.

def status(root: Path) -> str:
    document = manifest(root)
    lines = [f"studio {document.get('studio_id')}: {document.get('title')} ({root})", work_ledger.show(root)]
    for entry in document.get("characters") or []:
        character = entry.get("id")
        home = root / "characters" / str(character)
        rows = read_iterations(home) if home.is_dir() else []
        accepted = {row["slot"]: row for row in rows if row.get("status") == "accepted"}
        candidates = [row for row in rows if row.get("status") == "candidate"]
        lines.append(f"character {character}: {len(rows)} iterations, {len(accepted)} slots accepted, {len(candidates)} candidates waiting")
        for slot, row in sorted(accepted.items()):
            lines.append(f"  accepted {slot}: {row['iteration_id']} seed {row.get('seed')} ({(row.get('service') or {}).get('model_identifier')})")
        for row in candidates[-5:]:
            lines.append(f"  candidate {row['iteration_id']} for {row.get('slot')}: {row.get('note') or 'no note'}")
        from adoption_workflow import reference_index
        try:
            reference_state = reference_index(root, str(character))
            for item in reference_state["bindings"]:
                lines.append(f"  reference {item['slot']}: {item['status']}; next={item['next_action'] or 'complete'}")
            lines.extend("  reference error: " + error for error in reference_state["errors"])
        except (ValueError, OSError, RuntimeError) as exc:
            lines.append(f"  reference error: {exc}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--studio", type=Path, default=None, help="A directory in the studio (default: the working directory)")
    commands = parser.add_subparsers(dest="command", required=True)
    init_parser = commands.add_parser("init", help="create a studio")
    init_parser.add_argument("--out", type=Path, required=True)
    init_parser.add_argument("--studio-id", required=True)
    init_parser.add_argument("--title", required=True)
    commands.add_parser("status", help="the open task, and every character's slots and candidates")
    character_parser = commands.add_parser("character", help="characters")
    character_commands = character_parser.add_subparsers(dest="character_command", required=True)
    add_parser = character_commands.add_parser("add", help="add a character with a blank sheet")
    add_parser.add_argument("character")
    add_parser.add_argument("--profile", default="")
    iterate_parser = commands.add_parser("iterate", help="record one generated image with what produced it")
    iterate_parser.add_argument("--character", required=True)
    iterate_parser.add_argument("--slot", required=True)
    iterate_parser.add_argument("--result", type=Path, required=True)
    iterate_parser.add_argument("--package", type=Path)
    iterate_parser.add_argument("--package-companion", type=Path, help="the saved package companion directory, kept under its exact name")
    iterate_parser.add_argument("--request", type=Path, help="the request as sent, JSON")
    iterate_parser.add_argument("--response", type=Path, help="what the service answered, JSON")
    iterate_parser.add_argument("--note")
    accept_parser = commands.add_parser("accept", help="accept an iteration for its slot; the previous one is superseded")
    accept_parser.add_argument("--character", required=True)
    accept_parser.add_argument("--iteration", required=True)
    reject_parser = commands.add_parser("reject", help="mark an iteration rejected, with the reason")
    reject_parser.add_argument("--character", required=True)
    reject_parser.add_argument("--iteration", required=True)
    reject_parser.add_argument("--reason", required=True)
    recipe_parser = commands.add_parser("recipe", help="the settings that produced the accepted image of a slot")
    recipe_parser.add_argument("--character", required=True)
    recipe_parser.add_argument("--slot", required=True)
    gallery_parser = commands.add_parser("gallery", help="write gallery.html and gallery.json: every image in order with prompt, model, settings, and seed")
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
            print(json.dumps(recipe(root, args.character, args.slot), ensure_ascii=False, indent=2))
        elif args.command == "gallery":
            html_path, json_path = write_gallery(root, args.out)
            print(f"wrote {html_path} and {json_path}")
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
