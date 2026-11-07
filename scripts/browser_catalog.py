#!/usr/bin/env python3
"""Maintain the browser view of one explicitly selected enabled-pack runtime."""
from __future__ import annotations

import hashlib
import html
import json
import os
from pathlib import Path, PurePosixPath
from typing import Any

import catalog_html
from execution_contract import atomic, lock
from pack_cache import RuntimePackCatalog
from pack_manager import PackError, PackSettings, canonical_json, sha256_file


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


def output_directory(settings: PackSettings) -> Path:
    return settings.cache_dir.resolve() / "browser-catalog" / context_identity(settings)


def _generation(settings: PackSettings, source_fingerprint: str) -> dict[str, Any]:
    renderer = {
        path.name: sha256_file(path)
        for path in (Path(__file__).resolve(), Path(catalog_html.__file__).resolve())
    }
    return {
        "context": context_identity(settings),
        "source_fingerprint": source_fingerprint,
        "renderer_fingerprint": hashlib.sha256(canonical_json(renderer).encode("utf-8")).hexdigest(),
        "output_directory": str(output_directory(settings)),
        "title": TITLE,
        "resource_mode": "relative-to-source-pack",
        "status": "ready",
    }


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
    output = output_directory(settings)
    generation = _generation(settings, source_fingerprint)
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
    atomic(output / "index.html", document.encode("utf-8"), replace=True)
    manifest = {
        "format": "character-prompt-builder-catalog-unavailable",
        "runtime_projection": {**generation, "status": "unavailable"},
        "error": message,
    }
    atomic(output / "catalog-manifest.json", (json.dumps(manifest, indent=2) + "\n").encode("utf-8"), replace=True)


def maintain_catalog(settings: PackSettings, runtime: RuntimePackCatalog) -> dict[str, Any]:
    """Reuse or publish a complete display view without changing pack authority.

    Callers supply their resolved runtime. No discovery, state reload, temporary
    search cache or image-operation hook belongs to this derived display owner.
    """
    if not settings.state_file.is_file():
        return unselected_catalog(settings)
    output = output_directory(settings)
    result: dict[str, Any] = {
        "ok": False, "fresh": False, "rebuilt": False,
        "index": str(output / "index.html"),
        "context": context_identity(settings),
        "source_fingerprint": runtime.fingerprint,
    }
    try:
        # Keep the lock outside the directory the exporter atomically replaces.
        # A different explicit runtime uses a different lock and output.
        for root in runtime.pack_roots.values():
            source = root.resolve()
            if output == source or output in source.parents or source in output.parents:
                raise PackError("Browser catalog output overlaps an active source pack")
        generation = _generation(settings, runtime.fingerprint)
        if _current(output, generation) is not None:
            return {
                **result, "ok": True, "fresh": True,
                "pack_count": runtime.active_pack_count,
                "record_count": len(runtime.entries),
            }
        with lock(output.parent / ".locks" / result["context"]):
            try:
                # Another writer may have completed this generation while we waited.
                existing = _current(output, generation)
                if existing is None:
                    views = catalog_html.load_runtime_views(runtime)
                    notices = ["This catalog shows the resolved active records of the selected enabled-pack runtime."]
                    notices.extend(runtime.warnings)
                    if not runtime.active_pack_count:
                        notices.append("No active pack is available in this runtime.")
                    catalog_html.write_catalog_directory(
                        views, output, title=TITLE, overwrite=True,
                        runtime_projection=generation, notices=notices,
                    )
                    result["rebuilt"] = True
                return {
                    **result, "ok": True, "fresh": True,
                    "pack_count": runtime.active_pack_count,
                    "record_count": len(runtime.entries),
                }
            except Exception as exc:
                # A derived display failure must not undo a successful pack
                # operation or become another readiness decision.
                result["error"] = str(exc)[:1000]
                try:
                    _unavailable(output, generation, result["error"])
                except (OSError, ValueError) as publication_error:
                    result["display_error"] = str(publication_error)[:500]
                return result
    except Exception as exc:
        return {**result, "error": str(exc)[:1000]}
