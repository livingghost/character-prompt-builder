#!/usr/bin/env python3
"""Maintain the browser view of one explicitly selected enabled-pack runtime."""
from __future__ import annotations

import hashlib
import html
import json
import os
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

import catalog_html
import execution_contract as c
from execution_contract import atomic
from production_diagnostics import ProductionError
from pack_cache import RuntimePackCatalog
from pack_manager import PackError, canonical_json, sha256_file
from runtime_paths import PackSettings


TITLE = "Enabled Pack Catalog"


def context_identity(settings: PackSettings) -> str:
    """Keep runtimes sharing a cache separate while their active content changes."""
    def normalized(path: Path) -> str:
        return os.path.normcase(str(path.expanduser().resolve()))

    context = {
        "state_file": normalized(settings.state_file),
        "roots": sorted({normalized(path) for path in settings.roots}),
        "managed_root": normalized(settings.managed_root),
    }
    return hashlib.sha256(canonical_json(context).encode("utf-8")).hexdigest()


def output_directory(settings: PackSettings, source_fingerprint: str) -> Path:
    """Locate one complete generation of the selected runtime's browser view."""
    return Path(_generation(settings, source_fingerprint)["output_directory"])


def _generation(settings: PackSettings, source_fingerprint: str) -> dict[str, Any]:
    renderer = {
        path.name: sha256_file(path)
        for path in (Path(__file__).resolve(), Path(catalog_html.__file__).resolve())
    }
    generation = {
        "context": context_identity(settings),
        "source_fingerprint": source_fingerprint,
        "renderer_fingerprint": hashlib.sha256(canonical_json(renderer).encode("utf-8")).hexdigest(),
        "title": TITLE,
        "resource_mode": "relative-to-source-pack",
        "status": "ready",
    }
    identity = hashlib.sha256(canonical_json(generation).encode("utf-8")).hexdigest()
    output = settings.cache_dir.resolve() / "browser-catalog" / generation["context"] / identity
    return {**generation, "generation": identity, "output_directory": str(output)}


def _current(output: Path, generation: dict[str, Any]) -> dict[str, Any] | None:
    try:
        manifest = json.loads((output / "catalog-manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(manifest, dict) or manifest.get("runtime_projection") != generation:
        return None
    files = manifest.get("generated_files")
    if not isinstance(files, list) or "index.html" not in files or "catalog-manifest.json" not in files:
        return None
    for relative in files:
        if not isinstance(relative, str):
            return None
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or "\\" in relative:
            return None
        if not (output / relative).is_file():
            return None
    return manifest


def unselected_catalog(settings: PackSettings) -> dict[str, Any]:
    """A display does not select an enabled set on an author's behalf."""
    return {
        "ok": True, "fresh": False, "rebuilt": False, "status": "unselected",
        "context": context_identity(settings), "index": None,
        "reason": "No enabled-pack state has been selected; ready establishes the runtime.",
    }


def catalog_status(settings: PackSettings, source_fingerprint: str) -> dict[str, Any]:
    """Inspect a managed view using the source fingerprint already selected by its caller."""
    if not settings.state_file.is_file():
        return unselected_catalog(settings)
    generation = _generation(settings, source_fingerprint)
    output = Path(generation["output_directory"])
    manifest = _current(output, generation)
    return {
        "ok": True,
        "fresh": manifest is not None,
        "context": generation["context"],
        "source_fingerprint": source_fingerprint,
        "index": str(output / "index.html"),
        "pack_count": manifest.get("pack_count") if manifest else None,
        "record_count": manifest.get("record_count") if manifest else None,
    }


def _publish_generation(staging: Path, output: Path, generation: dict[str, Any]) -> None:
    """Publish a complete new generation or repair that exact generation's files.

    Different source/renderer generations never replace one another. A damaged
    existing generation is repaired under its actual catalog manifest, with
    that manifest published last. Completed competing publication is reused.
    """
    if not output.exists():
        try:
            c.publish_directory(staging, output)
            return
        except ProductionError as exc:
            if exc.diagnostic.code != 'OUTPUT_ALREADY_EXISTS':
                raise
    if output.is_symlink() or not output.is_dir():
        raise PackError("Browser generation output must be a regular directory")
    manifest_path = output / "catalog-manifest.json"
    raw_manifest = (staging / "catalog-manifest.json").read_bytes()
    if not manifest_path.exists():
        for retained in output.rglob("*"):
            if retained.is_symlink():
                raise PackError("Browser generation contains an unowned symbolic path")
            if retained.is_file():
                source = staging / retained.relative_to(output)
                if not source.is_file() or retained.read_bytes() != source.read_bytes():
                    raise PackError("Browser generation has files without its content inventory")
        # This is the completed staging generation's real content inventory,
        # not an empty claim or an extra coordination document.
        try:
            atomic(manifest_path, raw_manifest, durable=False)
        except FileExistsError:
            pass
    with c.file_lock(manifest_path):
        if _current(output, generation) is not None:
            return
        held = c.load(manifest_path)
        projection = held.get("runtime_projection") if isinstance(held, dict) else None
        if (not isinstance(projection, dict) or projection.get("status") not in {"ready", "unavailable"}
                or {**projection, "status": "ready"} != generation):
            raise PackError("Browser generation directory belongs to a different publication")
        for source in sorted(staging.rglob("*")):
            if not source.is_file() or source.name == "catalog-manifest.json":
                continue
            relative = source.relative_to(staging).as_posix()
            target = c.local(output, relative, exists=False)
            raw = source.read_bytes()
            if not target.is_file() or c.read(target) != raw:
                atomic(target, raw, replace=True, durable=False)
        atomic(manifest_path, raw_manifest, replace=True, durable=False)


def _unavailable(output: Path, generation: dict[str, Any], message: str) -> None:
    """Do not leave a formerly active catalog advertised as the current view."""
    document = (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Pack catalog unavailable</title><body><h1>Pack catalog unavailable</h1>'
        '<p>The browser view could not be updated for the current enabled packs.</p><p>'
        + html.escape(message)
        + '</p><p>The selected pack state is retained. The next pack readiness '
          'or maintenance operation retries this derived view.</p></body></html>\n'
    )
    manifest = {
        "format": "character-prompt-builder-catalog-unavailable",
        "runtime_projection": {**generation, "status": "unavailable"},
        "error": message,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.catalog-unavailable-', dir=output.parent))
    try:
        atomic(temporary / "index.html", document.encode("utf-8"), durable=False)
        atomic(temporary / "catalog-manifest.json", (json.dumps(manifest, indent=2) + "\n").encode("utf-8"), durable=False)
        _publish_generation(temporary, output, generation)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def maintain_catalog(settings: PackSettings, runtime: RuntimePackCatalog) -> dict[str, Any]:
    """Reuse or publish a complete display view without changing pack authority.

    Callers supply their resolved runtime. No discovery, state reload, temporary
    search cache or image-operation hook belongs to this derived display owner.
    """
    if not settings.state_file.is_file():
        return unselected_catalog(settings)
    generation = _generation(settings, runtime.fingerprint)
    output = Path(generation["output_directory"])
    result: dict[str, Any] = {
        "ok": False, "fresh": False, "rebuilt": False,
        "index": str(output / "index.html"),
        "context": context_identity(settings),
        "source_fingerprint": runtime.fingerprint,
    }
    try:
        # A display generation contains only this resolved runtime and renderer.
        for root in runtime.pack_roots.values():
            source = root.resolve()
            if output == source or output in source.parents or source in output.parents:
                raise PackError("Browser catalog output overlaps an active source pack")
        if _current(output, generation) is not None:
            return {
                **result, "ok": True, "fresh": True,
                "pack_count": runtime.active_pack_count,
                "record_count": len(runtime.entries),
            }
        try:
            views = catalog_html.load_runtime_views(runtime)
            notices = ["This catalog shows the resolved active records of the selected enabled-pack runtime."]
            notices.extend(runtime.warnings)
            if not runtime.active_pack_count:
                notices.append("No active pack is available in this runtime.")
            catalog_html.write_catalog_directory(
                views, output, title=TITLE, overwrite=True,
                runtime_projection=generation, notices=notices,
                publisher=lambda staging, target: _publish_generation(staging, target, generation),
            )
            return {
                **result, "ok": True, "fresh": True, "rebuilt": True,
                "pack_count": runtime.active_pack_count,
                "record_count": len(runtime.entries),
            }
        except Exception as exc:
            # Failure never replaces another source generation or a successful
            # competing publication of this generation.
            if _current(output, generation) is not None:
                return {**result, "ok": True, "fresh": True,
                        "pack_count": runtime.active_pack_count, "record_count": len(runtime.entries)}
            result["error"] = str(exc)[:1000]
            try:
                _unavailable(output, generation, result["error"])
            except (OSError, ValueError, ProductionError) as publication_error:
                result["display_error"] = str(publication_error)[:500]
            return result
    except Exception as exc:
        return {**result, "error": str(exc)[:1000]}
