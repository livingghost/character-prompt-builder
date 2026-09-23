#!/usr/bin/env python3
"""Generate a split, direct-open catalog for validated content packs.

The catalog keeps index.html small, stores complete records in separate pages,
and writes an explicit canonical-record-to-asset map. SVG previews refer only
to resources declared by validated packs and resolved beneath their roots.
The generator does not normalize, rank, rewrite, merge, or summarize records.
"""
from __future__ import annotations

import argparse
import hashlib
import gc
import html
import json
import mimetypes
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote

from pack_manager import (
    DiscoveredPack,
    PackError,
    PackRecord,
    PackSettings,
    PackValidation,
    load_state,
    resolve_enabled,
    validate_pack,
)
from pack_cache import load_runtime_catalog


_CATALOG_THUMBNAIL_CACHE: dict[tuple[str, str], dict[str, ResourceView]] = {}


@dataclass(frozen=True)
class InspectedPack:
    """One validated pack and its complete authored record set."""

    root: Path
    manifest: dict[str, Any]
    validation: PackValidation

    @property
    def pack_id(self) -> str:
        return str(self.manifest["pack_id"])

    @property
    def name(self) -> str:
        return str(self.manifest["name"])

    @property
    def release(self) -> str:
        return str(self.manifest["release"])


@dataclass(frozen=True)
class RecordView:
    """A record together with its unambiguous source pack."""

    pack: InspectedPack
    source: PackRecord

    @property
    def record(self) -> dict[str, Any]:
        return self.source.record

    @property
    def record_id(self) -> str:
        return str(self.record["id"])


@dataclass(frozen=True)
class ResourceView:
    """Display metadata for one pack-relative asset resource."""

    relative_path: str
    absolute_path: Path
    media_types: tuple[str, ...]
    roles: tuple[str, ...]
    primary: bool

    @property
    def previewable(self) -> bool:
        return any(value.startswith("image/") for value in self.media_types)


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _record_anchor(view: RecordView) -> str:
    return "record-" + view.pack.pack_id + "-" + view.record_id


def _json(value: Any) -> str:
    """Serialize without sorting so authored object order remains visible."""

    return json.dumps(value, ensure_ascii=False, indent=2)


def _unique(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            output.append(normalized)
    return output


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        output: list[str] = []
        for nested in value.values():
            output.extend(_strings(nested))
        return output
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        output = []
        for nested in value:
            output.extend(_strings(nested))
        return output
    return []


def _walk_named_fields(
    value: Any,
    predicate,
    *,
    path: str = "record",
) -> list[tuple[str, Any]]:
    matches: list[tuple[str, Any]] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key)
            nested_path = f"{path}.{key_text}"
            if predicate(key_text):
                matches.append((nested_path, nested))
            matches.extend(_walk_named_fields(nested, predicate, path=nested_path))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, nested in enumerate(value):
            matches.extend(_walk_named_fields(nested, predicate, path=f"{path}[{index}]"))
    return matches


def _is_grouping_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return (
        normalized in {
            "family",
            "family_id",
            "discovery_group",
            "group",
            "group_id",
            "variant",
            "variant_id",
            "variant_group",
            "species_group",
        }
        or normalized.endswith("_family")
        or normalized.endswith("_family_id")
        or normalized.endswith("_variant")
        or normalized.endswith("_variant_id")
    )


def _grouping_fields(record: Mapping[str, Any]) -> list[tuple[str, Any]]:
    return _walk_named_fields(record, _is_grouping_key)


def _grouping_values(record: Mapping[str, Any]) -> list[str]:
    return _unique(
        text
        for _, value in _grouping_fields(record)
        for text in _strings(value)
    )


def _category_domain_values(view: RecordView) -> list[str]:
    record = view.record
    categories: list[str] = []
    if view.source.category:
        categories.append(f"category:{view.source.category}")
    if record.get("category"):
        categories.append(f"category:{record['category']}")
    domains: list[str] = []
    if record.get("domain"):
        domains.append(str(record["domain"]))
    domains.extend(_strings(record.get("domains")))
    search_profile = record.get("search_profile")
    if isinstance(search_profile, Mapping):
        anchor = search_profile.get("anchor_signature")
        if isinstance(anchor, Mapping):
            domains.extend(_strings(anchor.get("domain")))
    categories.extend(f"domain:{value}" for value in _unique(domains))
    return _unique(categories)


def _safe_resource_path(pack: InspectedPack, relative: str) -> Path:
    """Resolve a declared POSIX-relative resource without leaving the pack."""

    pure = PurePosixPath(relative)
    if (
        not relative
        or pure.is_absolute()
        or "\\" in relative
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise PackError(
            f"Unsafe resource path in validated pack {pack.pack_id}: {relative!r}"
        )
    if relative not in set(pack.validation.resource_files):
        raise PackError(
            f"Asset resource is not selected by the validated pack: {relative!r}"
        )
    resolved = pack.root.joinpath(*pure.parts).resolve()
    try:
        resolved.relative_to(pack.root)
    except ValueError as exc:
        raise PackError(
            f"Asset resource resolves outside pack {pack.pack_id}: {relative!r}"
        ) from exc
    if not resolved.is_file():
        raise PackError(f"Validated asset resource is unavailable: {relative!r}")
    return resolved


def _asset_resources(view: RecordView) -> list[ResourceView]:
    record = view.record
    raw_refs = record.get("resource_refs") or []
    if not isinstance(raw_refs, list):
        raise PackError(
            f"Asset record {view.record_id!r} resource_refs must be an array"
        )
    refs = _unique(str(value) for value in raw_refs)
    primary = str(record.get("primary_resource") or "")

    artifact_roles: dict[str, list[str]] = {}
    artifact_media: dict[str, list[str]] = {}
    artifacts = record.get("artifacts") or []
    if isinstance(artifacts, Sequence) and not isinstance(
        artifacts, (str, bytes, bytearray)
    ):
        for artifact in artifacts:
            if not isinstance(artifact, Mapping):
                continue
            relative = str(artifact.get("path") or "")
            if not relative:
                continue
            role = str(artifact.get("role") or "")
            media_type = str(artifact.get("media_type") or "")
            if role:
                artifact_roles.setdefault(relative, []).append(role)
            if media_type:
                artifact_media.setdefault(relative, []).append(media_type)

    output: list[ResourceView] = []
    for relative in refs:
        absolute = _safe_resource_path(view.pack, relative)
        roles = list(artifact_roles.get(relative, []))
        if relative == primary:
            roles.insert(0, "primary-resource")
        if not roles:
            roles.append("resource-reference")
        media_types = artifact_media.get(relative, [])
        if not media_types:
            media_types = [
                mimetypes.guess_type(relative)[0] or "application/octet-stream"
            ]
        output.append(
            ResourceView(
                relative_path=relative,
                absolute_path=absolute,
                media_types=tuple(_unique(media_types)),
                roles=tuple(_unique(roles)),
                primary=relative == primary,
            )
        )
    return output


def _preview_resources(resources: Sequence[ResourceView]) -> list[ResourceView]:
    """Select primary and explicitly preview-oriented image resources."""

    primary_images = [item for item in resources if item.primary and item.previewable]
    designated = [
        item
        for item in resources
        if item.previewable
        and any(
            token in role.lower()
            for role in item.roles
            for token in ("thumbnail", "preview")
        )
    ]
    if not primary_images and not designated:
        designated = [item for item in resources if item.previewable][:1]
    seen: set[str] = set()
    output: list[ResourceView] = []
    for item in [*primary_images, *designated]:
        if item.relative_path not in seen:
            seen.add(item.relative_path)
            output.append(item)
    return output


def _load_validated_pack(root: Path, *, require_lock: bool) -> InspectedPack:
    report = validate_pack(root, require_lock=require_lock)
    if not report.valid:
        errors = [issue.message for issue in report.issues if issue.severity == "error"]
        raise PackError(
            f"Pack validation failed for {root.resolve()}: " + "; ".join(errors)
        )
    if report.manifest is None:
        raise PackError(f"Validated pack has no manifest: {root.resolve()}")
    return InspectedPack(report.root, dict(report.manifest), report)


def load_pack_directories(
    roots: Sequence[Path],
    *,
    require_lock: bool = False,
) -> list[InspectedPack]:
    """Load explicitly named pack directories and no implicit pack roots."""

    if not roots:
        raise PackError("At least one explicit pack directory is required.")
    packs = [_load_validated_pack(Path(root), require_lock=require_lock) for root in roots]
    return _deduplicate_packs(packs)


def discover_pack_tree(
    root: Path,
    *,
    require_lock: bool = False,
) -> list[InspectedPack]:
    """Discover every validated pack beneath an explicit pack tree.

    Discovery is deterministic and does not consult platform-default roots or
    ambient state. A future pack becomes part of the generated catalog as soon
    as it is present beneath the supplied tree and validates successfully.
    """

    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise PackError(f"Explicit pack tree does not exist: {root}")
    candidates = sorted(
        {path.parent for path in root.rglob("pack.json")},
        key=lambda value: value.relative_to(root).as_posix(),
    )
    if not candidates:
        raise PackError(f"Explicit pack tree contains no pack.json files: {root}")
    packs = [
        _load_validated_pack(candidate, require_lock=require_lock)
        for candidate in candidates
    ]
    return _deduplicate_packs(packs)


def _deduplicate_packs(packs: Sequence[InspectedPack]) -> list[InspectedPack]:
    ids: dict[str, Path] = {}
    roots: set[str] = set()
    output: list[InspectedPack] = []
    for pack in packs:
        normalized_root = os.path.normcase(str(pack.root))
        if normalized_root in roots:
            continue
        roots.add(normalized_root)
        previous = ids.get(pack.pack_id)
        if previous is not None and previous != pack.root:
            raise PackError(
                f"Pack ID {pack.pack_id!r} appears at both {previous} and {pack.root}."
            )
        ids[pack.pack_id] = pack.root
        output.append(pack)
    return output


def _active_pack_views(
    settings: PackSettings,
    selected: Sequence[DiscoveredPack],
    *,
    require_lock: bool,
) -> list[InspectedPack]:
    """Restrict enabled-pack views to the runtime's resolved active records.

    The runtime cache is built under an ephemeral directory. This preserves the
    exact replacement/conflict/dependency result without reading or writing a
    platform-default cache and without leaving an inspection cache beside the
    explicit state file.
    """

    inspected = _deduplicate_packs(
        [
            _load_validated_pack(item.root, require_lock=require_lock)
            for item in selected
        ]
    )
    with tempfile.TemporaryDirectory(prefix="cpb-catalog-html-cache-") as temp:
        temporary_root = Path(temp).resolve()
        runtime_settings = PackSettings(
            roots=settings.roots,
            state_file=settings.state_file,
            cache_dir=temporary_root / "cache",
            managed_root=temporary_root / "managed",
            quarantine_root=temporary_root / "quarantine",
            default_enabled_packs=settings.default_enabled_packs,
            default_resource_providers=settings.default_resource_providers,
        )
        runtime = load_runtime_catalog(runtime_settings)
        # sqlite3 may retain completed cursor objects until cyclic collection;
        # collect before Windows removes the ephemeral database directory.
        gc.collect()

    authored: dict[tuple[str, str], PackRecord] = {}
    inspected_by_id = {pack.pack_id: pack for pack in inspected}
    for pack in inspected:
        for source in pack.validation.records:
            key = (pack.pack_id, str(source.record.get("id") or ""))
            authored[key] = source

    active_by_pack: dict[str, list[PackRecord]] = {pack.pack_id: [] for pack in inspected}
    seen_record_ids: set[str] = set()
    for entry in runtime.entries:
        record_id = str(entry.record.get("id") or "")
        if not record_id:
            raise PackError("Resolved runtime catalog contains a record without an ID.")
        if record_id in seen_record_ids:
            raise PackError(
                f"Resolved runtime catalog contains duplicate active record ID: {record_id}"
            )
        seen_record_ids.add(record_id)
        key = (entry.source_pack, record_id)
        source = authored.get(key)
        if source is None:
            raise PackError(
                "Resolved runtime record has no matching validated authored record: "
                f"{entry.source_pack}/{record_id}"
            )
        if inspected_by_id.get(entry.source_pack) is None:
            raise PackError(
                "Resolved runtime record names a pack that was not inspected: "
                f"{entry.source_pack}/{record_id}"
            )
        if (
            source.kind != entry.kind
            or source.category != entry.category
            or source.record != entry.record
        ):
            raise PackError(
                "Resolved runtime record differs from its validated authored record: "
                f"{entry.source_pack}/{record_id}"
            )
        active_by_pack[entry.source_pack].append(source)

    output: list[InspectedPack] = []
    for pack in inspected:
        validation = pack.validation
        active_validation = PackValidation(
            root=validation.root,
            manifest=validation.manifest,
            records=active_by_pack.get(pack.pack_id, []),
            resource_files=list(validation.resource_files),
            resource_bindings=dict(validation.resource_bindings),
            issues=list(validation.issues),
            lock_present=validation.lock_present,
        )
        output.append(
            InspectedPack(pack.root, pack.manifest, active_validation)
        )
    return output


def _explicit_settings(
    state_file: Path,
    roots: Sequence[Path],
    *,
    default_enabled_packs: Sequence[str] = (),
    default_resource_providers: Mapping[str, str] | None = None,
) -> PackSettings:
    """Construct read-only settings without invoking platform defaults."""

    state_file = state_file.resolve()
    base = state_file.parent.resolve()
    return PackSettings(
        roots=tuple(Path(value).expanduser().resolve() for value in roots),
        state_file=state_file,
        cache_dir=base / ".catalog-html-unused-cache",
        managed_root=base / ".catalog-html-unused-managed",
        quarantine_root=base / ".catalog-html-unused-quarantine",
        default_enabled_packs=tuple(str(value) for value in default_enabled_packs),
        default_resource_providers=tuple(
            sorted(
                (str(name), str(pack_id))
                for name, pack_id in (default_resource_providers or {}).items()
            )
        ),
    )


def load_explicit_state(
    state_file: Path,
    roots: Sequence[Path] = (),
    *,
    require_lock: bool = False,
) -> list[InspectedPack]:
    """Load enabled packs from an explicitly named state file and roots."""

    state_file = state_file.resolve()
    if not state_file.is_file():
        raise PackError(f"Explicit state file does not exist: {state_file}")
    state = load_state(state_file)
    if not state.get("enabled_packs"):
        raise PackError(f"Explicit state enables no packs: {state_file}")
    if not roots and not state.get("pack_roots"):
        raise PackError(
            "Explicit state inspection requires pack_roots in state or at least one --pack-root."
        )
    settings = _explicit_settings(state_file, roots)
    selected = resolve_enabled(settings, state)
    return _active_pack_views(settings, selected, require_lock=require_lock)


def _resolve_settings_path(base: Path, value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise PackError(f"Explicit settings field {field!r} must be a non-empty path string.")
    path = Path(value).expanduser()
    return (base / path).resolve() if not path.is_absolute() else path.resolve()


def load_explicit_settings(
    settings_file: Path,
    *,
    require_lock: bool = False,
) -> list[InspectedPack]:
    """Load enabled packs from a fully explicit inspector settings document.

    The JSON object requires ``state_file`` and may provide ``roots``,
    ``default_enabled_packs``, and ``default_resource_providers``. Relative
    paths are based on the settings file. Runtime cache and platform-default
    paths are intentionally not consulted. A missing state file is permitted
    only when the explicit defaults select at least one pack.
    """

    settings_file = settings_file.resolve()
    try:
        raw = json.loads(settings_file.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PackError(f"Explicit settings file does not exist: {settings_file}") from exc
    except json.JSONDecodeError as exc:
        raise PackError(f"Invalid explicit settings JSON in {settings_file}: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise PackError(f"Explicit settings must contain a JSON object: {settings_file}")
    unexpected = sorted(
        set(raw)
        - {
            "state_file",
            "roots",
            "default_enabled_packs",
            "default_resource_providers",
        }
    )
    if unexpected:
        raise PackError(f"Unexpected explicit settings fields: {unexpected}")
    base = settings_file.parent
    state_file = _resolve_settings_path(base, raw.get("state_file"), "state_file")
    roots_value = raw.get("roots") or []
    if not isinstance(roots_value, list):
        raise PackError("Explicit settings field 'roots' must be an array of paths.")
    roots = [_resolve_settings_path(base, value, "roots") for value in roots_value]
    defaults = raw.get("default_enabled_packs") or []
    if not isinstance(defaults, list) or any(not isinstance(value, str) for value in defaults):
        raise PackError("Explicit settings field 'default_enabled_packs' must be an array of IDs.")
    provider_defaults = raw.get("default_resource_providers") or {}
    if not isinstance(provider_defaults, Mapping) or any(
        not isinstance(name, str) or not isinstance(pack_id, str)
        for name, pack_id in provider_defaults.items()
    ):
        raise PackError(
            "Explicit settings field 'default_resource_providers' must map resource names to pack IDs."
        )
    state = load_state(
        state_file,
        default_enabled_packs=defaults,
        default_resource_providers=provider_defaults,
    )
    if not state.get("enabled_packs"):
        raise PackError(f"Explicit settings resolve to no enabled packs: {settings_file}")
    if not roots and not state.get("pack_roots"):
        raise PackError("Explicit settings and state provide no pack roots.")
    settings = _explicit_settings(
        state_file,
        roots,
        default_enabled_packs=defaults,
        default_resource_providers=provider_defaults,
    )
    selected: list[DiscoveredPack] = resolve_enabled(settings, state)
    return _active_pack_views(settings, selected, require_lock=require_lock)



def _field_list(title: str, values: Sequence[tuple[str, Any]]) -> str:
    if not values:
        return ""
    rows = []
    for path, value in values:
        rows.append(
            "<dt>" + _escape(path) + "</dt><dd><pre class=\"field-json\">"
            + _escape(_json(value))
            + "</pre></dd>"
        )
    return (
        '<section class="field-section"><h4>'
        + _escape(title)
        + "</h4><dl>"
        + "".join(rows)
        + "</dl></section>"
    )


def _safe_filename(value: str, *, fallback: str = "item") -> str:
    """Return a deterministic filesystem-safe component without losing identity."""

    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-.")
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:10]
    if not normalized:
        normalized = fallback
    normalized = normalized[:96]
    if normalized != str(value):
        normalized = f"{normalized}-{digest}"
    return normalized


def _pack_page_relative(pack: InspectedPack) -> Path:
    return Path("packs") / f"{_safe_filename(pack.pack_id, fallback='pack')}.html"


def _record_page_relative(view: RecordView) -> Path:
    return (
        Path("records")
        / _safe_filename(view.pack.pack_id, fallback="pack")
        / f"{_safe_filename(view.record_id, fallback='record')}.html"
    )


def _url_quote_path(value: str) -> str:
    return quote(value.replace(os.sep, "/"), safe="/._-~")


def _relative_href(target: Path, *, from_directory: Path) -> str:
    """Build a local-file-safe relative URL, falling back to a file URI across drives."""

    target = target.resolve()
    from_directory = from_directory.resolve()
    try:
        relative = os.path.relpath(target, start=from_directory)
    except ValueError:
        return target.as_uri()
    return _url_quote_path(relative)


def _copy_resource(
    asset: RecordView,
    resource: ResourceView,
    output_root: Path,
    copied: set[Path],
) -> Path:
    destination = (
        output_root
        / "media"
        / _safe_filename(asset.pack.pack_id, fallback="pack")
        / Path(*PurePosixPath(resource.relative_path).parts)
    )
    if destination not in copied:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(resource.absolute_path, destination, follow_symlinks=False)
        copied.add(destination)
    return destination


def _resource_href(
    asset: RecordView,
    resource: ResourceView,
    *,
    page_path: Path,
    output_root: Path,
    copy_assets: bool,
    copied: set[Path],
) -> str:
    target = (
        _copy_resource(asset, resource, output_root, copied)
        if copy_assets
        else resource.absolute_path
    )
    return _relative_href(target, from_directory=page_path.parent)


def _resource_table(
    asset: RecordView,
    resources: Sequence[ResourceView],
    *,
    page_path: Path,
    output_root: Path,
    copy_assets: bool,
    copied: set[Path],
) -> str:
    if not resources:
        return '<p class="muted">No resource references.</p>'
    rows = []
    for resource in resources:
        href = _resource_href(
            asset,
            resource,
            page_path=page_path,
            output_root=output_root,
            copy_assets=copy_assets,
            copied=copied,
        )
        rows.append(
            "<tr><td>"
            + ("yes" if resource.primary else "")
            + '</td><td><a class="resource-link" href="'
            + _escape(href)
            + '" rel="noreferrer">'
            + _escape(resource.relative_path)
            + "</a></td><td>"
            + _escape(", ".join(resource.roles))
            + "</td><td>"
            + _escape(", ".join(resource.media_types))
            + "</td></tr>"
        )
    return (
        '<div class="table-scroll"><table class="resources"><thead><tr>'
        "<th>Primary</th><th>Pack-relative resource</th><th>Role(s)</th>"
        "<th>Media type(s)</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def _previews(
    asset: RecordView,
    resources: Sequence[ResourceView],
    *,
    label: str,
    page_path: Path,
    output_root: Path,
    copy_assets: bool,
    copied: set[Path],
) -> str:
    """Render one lightweight display thumbnail linked to the primary asset.

    A pack may provide a catalog-only WebP sidecar so browsing never requires
    decoding a multi-megabyte archival SVG. The sidecar has no prompt authority;
    the click target and resource table continue to expose the authored SVG.
    """

    display_resource = _primary_preview_resource(asset)
    if display_resource is None:
        return ""
    target_resource = next(
        (item for item in resources if item.primary and item.previewable),
        display_resource,
    )
    display_href = _resource_href(
        asset,
        display_resource,
        page_path=page_path,
        output_root=output_root,
        copy_assets=copy_assets,
        copied=copied,
    )
    target_href = _resource_href(
        asset,
        target_resource,
        page_path=page_path,
        output_root=output_root,
        copy_assets=copy_assets,
        copied=copied,
    )
    caption = (
        "Catalog thumbnail (display-only; open the linked primary resource)"
        if "catalog-thumbnail" in display_resource.roles
        else ", ".join(display_resource.roles)
    )
    return (
        '<div class="previews"><figure><a href="'
        + _escape(target_href)
        + '" rel="noreferrer"><img loading="lazy" decoding="async" '
        'referrerpolicy="no-referrer" src="'
        + _escape(display_href)
        + '" alt="'
        + _escape(f"{label}: {display_resource.relative_path}")
        + '"></a><figcaption>'
        + _escape(caption)
        + '<br><span>'
        + _escape(display_resource.relative_path)
        + '</span></figcaption></figure></div>'
    )

def _canonical_link_specs(asset: RecordView) -> list[tuple[str | None, str]]:
    """Return authored canonical targets, preferring optional pack-qualified refs."""

    specs: list[tuple[str | None, str]] = []
    raw_refs = asset.record.get("canonical_record_refs") or []
    if raw_refs and not isinstance(raw_refs, list):
        raise PackError(
            f"Asset record {asset.record_id!r} canonical_record_refs must be an array"
        )
    for value in raw_refs:
        if isinstance(value, Mapping):
            record_id = str(value.get("record_id") or "").strip()
            pack_id = str(value.get("pack_id") or "").strip() or None
        elif isinstance(value, str) and value.strip():
            text = value.strip()
            if ":" in text:
                pack_id, record_id = (part.strip() for part in text.split(":", 1))
                pack_id = pack_id or None
            else:
                pack_id, record_id = None, text
        else:
            raise PackError(
                f"Asset record {asset.record_id!r} has an invalid canonical_record_ref: {value!r}"
            )
        if not record_id:
            raise PackError(
                f"Asset record {asset.record_id!r} has an empty canonical record reference"
            )
        specs.append((pack_id, record_id))
    specs.extend(
        (None, record_id)
        for record_id in _unique(_strings(asset.record.get("canonical_record_ids")))
    )
    output: list[tuple[str | None, str]] = []
    seen: set[tuple[str | None, str]] = set()
    for spec in specs:
        if spec not in seen:
            seen.add(spec)
            output.append(spec)
    return output


def _build_catalog_links(
    records: Sequence[RecordView],
) -> tuple[
    dict[str, list[RecordView]],
    dict[tuple[str, str], list[RecordView]],
    dict[tuple[str, str], list[RecordView]],
    list[dict[str, str]],
]:
    """Resolve authored asset-to-canonical links for every selected pack.

    Unqualified ``canonical_record_ids`` prefer a same-pack record and may fall
    back to a globally unique record. Future packs with duplicate IDs can use
    ``canonical_record_refs`` with explicit ``pack_id`` and ``record_id``.
    """

    records_by_id: dict[str, list[RecordView]] = {}
    records_by_key: dict[tuple[str, str], RecordView] = {}
    for view in records:
        records_by_id.setdefault(view.record_id, []).append(view)
        records_by_key[(view.pack.pack_id, view.record_id)] = view

    assets_by_record: dict[tuple[str, str], list[RecordView]] = {}
    records_by_asset: dict[tuple[str, str], list[RecordView]] = {}
    unresolved: list[dict[str, str]] = []
    assets = [view for view in records if view.source.kind == "asset"]
    for asset in assets:
        asset_key = (asset.pack.pack_id, asset.record_id)
        for requested_pack_id, canonical_id in _canonical_link_specs(asset):
            if requested_pack_id:
                target = records_by_key.get((requested_pack_id, canonical_id))
                targets = (
                    [target]
                    if target is not None and target.source.kind != "asset"
                    else []
                )
            else:
                candidates = [
                    target
                    for target in records_by_id.get(canonical_id, ())
                    if target.source.kind != "asset"
                ]
                same_pack = [
                    target
                    for target in candidates
                    if target.pack.pack_id == asset.pack.pack_id
                ]
                if same_pack:
                    targets = same_pack
                elif len(candidates) == 1:
                    targets = candidates
                else:
                    targets = []
            if not targets:
                unresolved.append(
                    {
                        "asset_pack_id": asset.pack.pack_id,
                        "asset_id": asset.record_id,
                        "canonical_pack_id": requested_pack_id or "",
                        "canonical_record_id": canonical_id,
                    }
                )
                continue
            for target in targets:
                key = (target.pack.pack_id, target.record_id)
                if asset not in assets_by_record.setdefault(key, []):
                    assets_by_record[key].append(asset)
                if target not in records_by_asset.setdefault(asset_key, []):
                    records_by_asset[asset_key].append(target)

    for linked in assets_by_record.values():
        linked.sort(key=lambda value: (value.pack.name, value.record_id))
    for linked in records_by_asset.values():
        linked.sort(key=lambda value: (value.pack.name, value.record_id))
    return records_by_id, assets_by_record, records_by_asset, unresolved

def _page_href(
    target: RecordView,
    *,
    page_path: Path,
    page_map: Mapping[tuple[str, str], Path],
    output_root: Path,
) -> str:
    target_path = output_root / page_map[(target.pack.pack_id, target.record_id)]
    return _relative_href(target_path, from_directory=page_path.parent)


def _canonical_navigation(
    asset: RecordView,
    records_by_id: Mapping[str, Sequence[RecordView]],
    *,
    page_path: Path,
    page_map: Mapping[tuple[str, str], Path],
    output_root: Path,
) -> str:
    """Render authored canonical targets, including pack-qualified future refs."""

    items: list[str] = []
    for requested_pack_id, canonical_id in _canonical_link_specs(asset):
        targets = [
            target
            for target in records_by_id.get(canonical_id, ())
            if target.source.kind != "asset"
        ]
        if requested_pack_id:
            targets = [
                target for target in targets
                if target.pack.pack_id == requested_pack_id
            ]
        else:
            same_pack = [
                target for target in targets
                if target.pack.pack_id == asset.pack.pack_id
            ]
            if same_pack:
                targets = same_pack
            elif len(targets) != 1:
                targets = []
        display_id = (
            f"{requested_pack_id}:{canonical_id}"
            if requested_pack_id
            else canonical_id
        )
        if not targets:
            items.append("<code>" + _escape(display_id) + "</code>")
            continue
        for target in targets:
            items.append(
                '<a href="'
                + _escape(
                    _page_href(
                        target,
                        page_path=page_path,
                        page_map=page_map,
                        output_root=output_root,
                    )
                )
                + '"><code>'
                + _escape(display_id)
                + "</code> | "
                + _escape(target.pack.name)
                + "</a>"
            )
    return ", ".join(items) if items else '<span class="muted">none</span>'

def _asset_panel(
    asset: RecordView,
    *,
    compact: bool,
    records_by_id: Mapping[str, Sequence[RecordView]],
    page_path: Path,
    page_map: Mapping[tuple[str, str], Path],
    output_root: Path,
    copy_assets: bool,
    copied: set[Path],
) -> str:
    resources = _asset_resources(asset)
    label = str(asset.record.get("label") or asset.record_id)
    asset_href = _page_href(
        asset,
        page_path=page_path,
        page_map=page_map,
        output_root=output_root,
    )
    return (
        '<article class="asset-panel"><header><h4><a href="'
        + _escape(asset_href)
        + '">'
        + _escape(label)
        + '</a></h4><code>'
        + _escape(asset.record_id)
        + "</code></header><p><strong>Pack:</strong> "
        + _escape(asset.pack.name)
        + " <code>"
        + _escape(asset.pack.pack_id)
        + "</code></p><p><strong>Canonical record IDs:</strong> "
        + _canonical_navigation(
            asset,
            records_by_id,
            page_path=page_path,
            page_map=page_map,
            output_root=output_root,
        )
        + "</p><p><strong>primary_resource:</strong> <code>"
        + _escape(str(asset.record.get("primary_resource") or ""))
        + "</code></p>"
        + _previews(
            asset,
            resources,
            label=label,
            page_path=page_path,
            output_root=output_root,
            copy_assets=copy_assets,
            copied=copied,
        )
        + _resource_table(
            asset,
            resources,
            page_path=page_path,
            output_root=output_root,
            copy_assets=copy_assets,
            copied=copied,
        )
        + "</article>"
    )


def _catalog_thumbnail_resources(pack: InspectedPack) -> dict[str, ResourceView]:
    """Load a pack-owned display-thumbnail map without granting prompt authority."""

    binding = str(pack.validation.resource_bindings.get("catalog-thumbnails") or "")
    if not binding:
        return {}
    cache_key = (str(pack.root), binding)
    cached = _CATALOG_THUMBNAIL_CACHE.get(cache_key)
    if cached is not None:
        return cached
    manifest_path = _safe_resource_path(pack, binding)
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackError(f"Invalid catalog thumbnail manifest: {manifest_path}: {exc}") from exc
    if not isinstance(document, Mapping) or document.get("format") != "character-prompt-builder-catalog-thumbnails":
        raise PackError(f"Unexpected catalog thumbnail manifest format: {manifest_path}")
    raw_assets = document.get("assets")
    if not isinstance(raw_assets, Mapping):
        raise PackError(f"Catalog thumbnail manifest assets must be an object: {manifest_path}")
    output: dict[str, ResourceView] = {}
    for asset_id, raw in raw_assets.items():
        if not isinstance(asset_id, str) or not isinstance(raw, Mapping):
            raise PackError(f"Invalid catalog thumbnail entry in {manifest_path}")
        relative = str(raw.get("path") or "")
        media_type = str(raw.get("media_type") or mimetypes.guess_type(relative)[0] or "application/octet-stream")
        expected_sha = str(raw.get("sha256") or "")
        absolute = _safe_resource_path(pack, relative)
        if expected_sha and hashlib.sha256(absolute.read_bytes()).hexdigest() != expected_sha:
            raise PackError(f"Catalog thumbnail hash mismatch for {asset_id}: {relative}")
        if not media_type.startswith("image/"):
            raise PackError(f"Catalog thumbnail is not an image for {asset_id}: {relative}")
        output[asset_id] = ResourceView(
            relative_path=relative,
            absolute_path=absolute,
            media_types=(media_type,),
            roles=("catalog-thumbnail",),
            primary=False,
        )
    _CATALOG_THUMBNAIL_CACHE[cache_key] = output
    return output


def _primary_preview_resource(asset: RecordView) -> ResourceView | None:
    sidecar = _catalog_thumbnail_resources(asset.pack).get(asset.record_id)
    if sidecar is not None:
        return sidecar
    resources = _asset_resources(asset)
    selected = _preview_resources(resources)
    return selected[0] if selected else None


def _thumbnail_href(
    asset: RecordView,
    *,
    page_path: Path,
    output_root: Path,
    copy_assets: bool,
    copied: set[Path],
) -> str | None:
    resource = _primary_preview_resource(asset)
    if resource is None:
        return None
    return _resource_href(
        asset,
        resource,
        page_path=page_path,
        output_root=output_root,
        copy_assets=copy_assets,
        copied=copied,
    )


def _record_link_list(
    records: Sequence[RecordView],
    *,
    page_path: Path,
    page_map: Mapping[tuple[str, str], Path],
    output_root: Path,
    limit: int = 12,
) -> str:
    if not records:
        return '<span class="muted">No linked presets.</span>'
    links = []
    for target in records[:limit]:
        label = str(target.record.get("label") or target.record_id)
        links.append(
            '<li><a href="'
            + _escape(
                _page_href(
                    target,
                    page_path=page_path,
                    page_map=page_map,
                    output_root=output_root,
                )
            )
            + '">'
            + _escape(label)
            + '</a><br><code>'
            + _escape(target.record_id)
            + '</code> <span class="muted">| '
            + _escape(target.pack.name)
            + '</span></li>'
        )
    suffix = (
        '<li class="muted">+' + str(len(records) - limit) + ' additional linked presets</li>'
        if len(records) > limit
        else ''
    )
    return '<ul class="linked-record-list">' + ''.join(links) + suffix + '</ul>'


def _svg_resource_link_list(
    asset: RecordView,
    *,
    page_path: Path,
    output_root: Path,
    copy_assets: bool,
    copied: set[Path],
) -> str:
    """List every SVG artifact for visual-first browsing."""

    resources = {item.relative_path: item for item in _asset_resources(asset)}
    rows: list[str] = []
    for artifact in _svg_artifacts(asset):
        path = str(artifact.get("path") or "")
        resource = resources.get(path)
        if resource is None:
            continue
        href = _resource_href(
            asset,
            resource,
            page_path=page_path,
            output_root=output_root,
            copy_assets=copy_assets,
            copied=copied,
        )
        role = str(artifact.get("role") or artifact.get("artifact_id") or "Evidence artifact")
        rows.append(
            '<li><a href="'
            + _escape(href)
            + '" rel="noreferrer">'
            + _escape(role)
            + '</a></li>'
        )
    if not rows:
        return '<span class="muted">No evidence artifacts.</span>'
    return '<ul class="artifact-link-list">' + ''.join(rows) + '</ul>'


def _pagination_links(
    *,
    page_number: int,
    page_count: int,
    page_path: Path,
    page_paths: Sequence[Path],
    output_root: Path,
) -> str:
    items: list[str] = []
    if page_number > 1:
        items.append(
            '<a href="'
            + _escape(
                _relative_href(
                    output_root / page_paths[page_number - 2],
                    from_directory=page_path.parent,
                )
            )
            + '">Previous</a>'
        )
    items.append(f'<span>Page {page_number} of {page_count}</span>')
    if page_number < page_count:
        items.append(
            '<a href="'
            + _escape(
                _relative_href(
                    output_root / page_paths[page_number],
                    from_directory=page_path.parent,
                )
            )
            + '">Next</a>'
        )
    return '<nav class="static-pagination">' + ''.join(items) + '</nav>'


def _visual_evidence_gallery_pages(
    assets: Sequence[RecordView],
    records_by_asset: Mapping[tuple[str, str], Sequence[RecordView]],
    *,
    page_map: Mapping[tuple[str, str], Path],
    output_root: Path,
    copy_assets: bool,
    copied: set[Path],
    page_size: int = 24,
) -> list[Path]:
    ordered = sorted(
        assets,
        key=lambda value: (
            str(value.record.get("label") or value.record_id).casefold(),
            value.pack.name.casefold(),
            value.record_id,
        ),
    )
    page_count = max(1, (len(ordered) + page_size - 1) // page_size)
    page_paths = [
        Path("visual-evidence") / ("index.html" if index == 0 else f"page-{index + 1:03d}.html")
        for index in range(page_count)
    ]
    for index, relative in enumerate(page_paths):
        page_path = output_root / relative
        page_path.parent.mkdir(parents=True, exist_ok=True)
        cards: list[str] = []
        for asset in ordered[index * page_size : (index + 1) * page_size]:
            asset_key = (asset.pack.pack_id, asset.record_id)
            linked_records = list(records_by_asset.get(asset_key, ()))
            asset_href = _page_href(
                asset,
                page_path=page_path,
                page_map=page_map,
                output_root=output_root,
            )
            thumbnail = _thumbnail_href(
                asset,
                page_path=page_path,
                output_root=output_root,
                copy_assets=copy_assets,
                copied=copied,
            )
            label = str(asset.record.get("label") or asset.record_id)
            image = (
                '<a class="gallery-image" href="' + _escape(asset_href) + '"><img loading="lazy" decoding="async" src="'
                + _escape(thumbnail)
                + '" alt="' + _escape(label) + '"></a>'
                if thumbnail
                else '<div class="gallery-placeholder">No preview thumbnail available</div>'
            )
            cards.append(
                '<article class="gallery-card">'
                + image
                + '<div class="gallery-copy"><p class="eyebrow">Visual Evidence | '
                + _escape(asset.pack.name)
                + '</p><h2><a href="'
                + _escape(asset_href)
                + '">'
                + _escape(label)
                + '</a></h2><code>'
                + _escape(asset.record_id)
                + '</code><p>'
                + _escape(str(asset.record.get("description") or ""))
                + '</p><h3>Evidence artifacts</h3>'
                + _svg_resource_link_list(
                    asset,
                    page_path=page_path,
                    output_root=output_root,
                    copy_assets=copy_assets,
                    copied=copied,
                )
                + '<h3>Linked presets ('
                + str(len(linked_records))
                + ')</h3>'
                + _record_link_list(
                    linked_records,
                    page_path=page_path,
                    page_map=page_map,
                    output_root=output_root,
                )
                + '</div></article>'
            )
        home_href = _relative_href(output_root / "index.html", from_directory=page_path.parent)
        search_href = _relative_href(output_root / "search.html", from_directory=page_path.parent)
        body = (
            '<header class="page"><nav class="top-links"><a href="'
            + _escape(home_href)
            + '">Catalog home</a><a href="'
            + _escape(search_href)
            + '">Search records</a></nav><h1>Visual Evidence gallery</h1>'
            + '<p class="summary">Browse Visual Evidence by preview thumbnail, then open the Visual Evidence record or a linked preset. '
            + str(len(assets))
            + ' Visual Evidence records are split into pages of at most '
            + str(page_size)
            + ' thumbnails.</p></header><main class="gallery-page">'
            + _pagination_links(
                page_number=index + 1,
                page_count=page_count,
                page_path=page_path,
                page_paths=page_paths,
                output_root=output_root,
            )
            + '<section class="gallery-grid">'
            + ''.join(cards)
            + '</section>'
            + _pagination_links(
                page_number=index + 1,
                page_count=page_count,
                page_path=page_path,
                page_paths=page_paths,
                output_root=output_root,
            )
            + '</main>'
        )
        css_href = _relative_href(output_root / "assets" / "catalog.css", from_directory=page_path.parent)
        page_path.write_text(
            _html_shell("Visual Evidence gallery", css_href=css_href, body=body),
            encoding="utf-8",
            newline="\n",
        )
    return page_paths


def _linked_preset_gallery_pages(
    records: Sequence[RecordView],
    assets_by_record: Mapping[tuple[str, str], Sequence[RecordView]],
    *,
    page_map: Mapping[tuple[str, str], Path],
    output_root: Path,
    copy_assets: bool,
    copied: set[Path],
    page_size: int = 24,
) -> list[Path]:
    linked_records = [
        view
        for view in records
        if view.source.kind != "asset"
        and assets_by_record.get((view.pack.pack_id, view.record_id))
    ]
    linked_records.sort(
        key=lambda value: (
            str(value.record.get("label") or value.record_id).casefold(),
            value.pack.name.casefold(),
            value.record_id,
        )
    )
    page_count = max(1, (len(linked_records) + page_size - 1) // page_size)
    page_paths = [
        Path("linked-presets") / ("index.html" if index == 0 else f"page-{index + 1:03d}.html")
        for index in range(page_count)
    ]
    for index, relative in enumerate(page_paths):
        page_path = output_root / relative
        page_path.parent.mkdir(parents=True, exist_ok=True)
        cards: list[str] = []
        for view in linked_records[index * page_size : (index + 1) * page_size]:
            linked_assets = list(assets_by_record[(view.pack.pack_id, view.record_id)])
            primary_asset = linked_assets[0]
            thumbnail = _thumbnail_href(
                primary_asset,
                page_path=page_path,
                output_root=output_root,
                copy_assets=copy_assets,
                copied=copied,
            )
            record_href = _page_href(
                view,
                page_path=page_path,
                page_map=page_map,
                output_root=output_root,
            )
            label = str(view.record.get("label") or view.record_id)
            image = (
                '<a class="gallery-image" href="' + _escape(record_href) + '"><img loading="lazy" decoding="async" src="'
                + _escape(thumbnail)
                + '" alt="' + _escape(label) + '"></a>'
                if thumbnail
                else '<div class="gallery-placeholder">No preview thumbnail available</div>'
            )
            cards.append(
                '<article class="gallery-card">'
                + image
                + '<div class="gallery-copy"><p class="eyebrow">'
                + _escape(view.source.kind)
                + ' | '
                + _escape(view.pack.name)
                + '</p><h2><a href="'
                + _escape(record_href)
                + '">'
                + _escape(label)
                + '</a></h2><code>'
                + _escape(view.record_id)
                + '</code><p><strong>Linked Visual Evidence:</strong> '
                + str(len(linked_assets))
                + '</p></div></article>'
            )
        home_href = _relative_href(output_root / "index.html", from_directory=page_path.parent)
        visual_href = _relative_href(output_root / "visual-evidence" / "index.html", from_directory=page_path.parent)
        body = (
            '<header class="page"><nav class="top-links"><a href="'
            + _escape(home_href)
            + '">Catalog home</a><a href="'
            + _escape(visual_href)
            + '">Visual Evidence gallery</a></nav><h1>Presets with linked Visual Evidence</h1>'
            + '<p class="summary">Browse canonical presets by a preview thumbnail from their linked Visual Evidence. '
            + str(len(linked_records))
            + ' presets are split into pages of at most '
            + str(page_size)
            + ' thumbnails.</p></header><main class="gallery-page">'
            + _pagination_links(
                page_number=index + 1,
                page_count=page_count,
                page_path=page_path,
                page_paths=page_paths,
                output_root=output_root,
            )
            + '<section class="gallery-grid">'
            + ''.join(cards)
            + '</section>'
            + _pagination_links(
                page_number=index + 1,
                page_count=page_count,
                page_path=page_path,
                page_paths=page_paths,
                output_root=output_root,
            )
            + '</main>'
        )
        css_href = _relative_href(output_root / "assets" / "catalog.css", from_directory=page_path.parent)
        page_path.write_text(
            _html_shell("Presets with linked Visual Evidence", css_href=css_href, body=body),
            encoding="utf-8",
            newline="\n",
        )
    return page_paths


_CATALOG_CSS = """
:root{color-scheme:light dark;--bg:#11151b;--panel:#1a2029;--panel2:#222a35;--text:#edf2f7;--muted:#a9b4c2;--line:#3a4655;--accent:#77c7ff;--accent2:#b7e3ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,sans-serif}a{color:var(--accent);overflow-wrap:anywhere}code,pre{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}code{overflow-wrap:anywhere}.page{padding:1.5rem max(1rem,4vw) 1rem}.page h1{margin:0 0 .4rem;font-size:clamp(1.5rem,4vw,2.7rem)}.muted,.summary{color:var(--muted)}
.top-links{display:flex;flex-wrap:wrap;gap:1rem}.home-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:1rem;padding:1rem max(1rem,4vw) 2rem}.home-card{display:block;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:1.15rem;text-decoration:none;color:var(--text)}.home-card:hover{border-color:var(--accent)}.home-card h2{margin:.1rem 0 .35rem;color:var(--accent2)}.home-card p{margin:.25rem 0;color:var(--muted)}.home-count{font-size:1.8rem;font-weight:750;color:var(--text)}
.toolbar{position:sticky;top:0;z-index:5;display:grid;grid-template-columns:minmax(220px,2fr) repeat(3,minmax(150px,1fr));gap:.7rem;padding:1rem max(1rem,4vw);background:#151b23f5;border-block:1px solid var(--line);backdrop-filter:blur(8px)}.toolbar label{display:grid;gap:.25rem;color:var(--muted);font-size:.8rem}.toolbar input,.toolbar select{width:100%;padding:.58rem;border:1px solid var(--line);border-radius:7px;background:var(--panel2);color:var(--text)}
.content,.record-page,.pack-page,.gallery-page{display:grid;gap:1rem;padding:1rem max(1rem,4vw) 2rem}.results{display:grid;gap:.7rem}.result-card,.pack-card,.record-card,.asset-panel,.panel,.gallery-card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:1rem;min-width:0}.result-card{display:grid;grid-template-columns:minmax(0,1fr);gap:.75rem;align-items:start}.result-card.has-thumbnail{grid-template-columns:minmax(0,1fr) minmax(112px,160px)}.result-copy{display:grid;gap:.45rem;min-width:0}.result-thumbnail{display:grid;place-items:center;width:100%;min-height:112px;background:#fff;border-radius:8px;overflow:hidden;text-decoration:none}.result-thumb{display:block;width:100%;height:136px;object-fit:contain}.result-card h2,.record-card h2,.pack-card h2,.asset-panel h4,.gallery-card h2{margin:.2rem 0}.eyebrow{margin:0;color:var(--accent);font-size:.78rem;font-weight:700;letter-spacing:.05em;text-transform:uppercase}.badges{display:flex;flex-wrap:wrap;gap:.4rem}.badge{padding:.2rem .5rem;border-radius:999px;background:var(--panel2);color:var(--muted);font-size:.78rem}
.pagination,.static-pagination{display:flex;align-items:center;justify-content:space-between;gap:1rem}.pagination button{padding:.45rem .8rem;border:1px solid var(--line);border-radius:7px;background:var(--panel2);color:var(--text);cursor:pointer}.pagination button:disabled{opacity:.45;cursor:not-allowed}.static-pagination{padding:.7rem 0}.static-pagination a{padding:.45rem .8rem;border:1px solid var(--line);border-radius:7px;background:var(--panel2);text-decoration:none}
.record-header,.asset-panel header{display:flex;align-items:flex-start;justify-content:space-between;gap:1rem}.record-meta{padding:.75rem;background:var(--panel2);border-radius:8px}dl{display:grid;grid-template-columns:minmax(8rem,max-content) 1fr;gap:.35rem 1rem}dt{color:var(--muted);font-weight:650}dd{margin:0;min-width:0;overflow-wrap:anywhere}.field-section,.linked-assets{margin-top:1rem}.field-json{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}details{margin-top:.8rem}summary{cursor:pointer;color:var(--accent)}.raw-json{max-height:70vh;overflow:auto;padding:1rem;background:#0b0f14;border-radius:8px;white-space:pre-wrap;overflow-wrap:anywhere}.asset-panel{margin-top:.75rem;background:var(--panel2)}.table-scroll{overflow:auto}table{width:100%;border-collapse:collapse}th,td{padding:.45rem;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
.previews{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,320px));gap:.8rem;margin:.8rem 0}figure{margin:0}figure img{width:100%;height:260px;object-fit:contain;background:#fff;border-radius:8px}figcaption{color:var(--muted);font-size:.8rem;overflow-wrap:anywhere}.notice{padding:.7rem 1rem;border-left:4px solid var(--accent);background:var(--panel2)}
.gallery-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:1rem}.gallery-card{display:grid;grid-template-rows:auto 1fr;padding:0;overflow:hidden}.gallery-image{display:block;background:#fff}.gallery-image img{display:block;width:100%;height:300px;object-fit:contain}.gallery-placeholder{height:300px;display:grid;place-items:center;background:var(--panel2);color:var(--muted)}.gallery-copy{padding:1rem}.gallery-copy h3{margin:.8rem 0 .2rem;font-size:1rem}.linked-record-list,.artifact-link-list{margin:.35rem 0 0;padding-left:1.2rem}.linked-record-list li,.artifact-link-list li{margin:.3rem 0}.kind-grid,.pack-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:.8rem}.browse-card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:1rem}.browse-card h2{margin:.1rem 0}.browse-card p{margin:.3rem 0;color:var(--muted)}[hidden]{display:none!important}
@media(max-width:850px){.toolbar{grid-template-columns:1fr 1fr}.toolbar label:first-child{grid-column:1/-1}.result-card.has-thumbnail{grid-template-columns:minmax(0,1fr) 104px}.result-thumbnail{min-height:104px}.result-thumb{height:104px}.gallery-image img,.gallery-placeholder{height:240px}}
@media(max-width:620px){.toolbar{grid-template-columns:1fr}.toolbar label:first-child{grid-column:auto}.result-card.has-thumbnail{grid-template-columns:minmax(0,1fr)}.result-thumbnail{width:min(100%,160px);min-height:100px}.result-thumb{height:100px}}
@media(prefers-color-scheme:light){:root{--bg:#f2f5f8;--panel:#fff;--panel2:#eef2f6;--text:#17202a;--muted:#566574;--line:#ccd5de;--accent:#0069a8;--accent2:#00527f}.toolbar{background:#f7f9fbf5}.raw-json{background:#f4f6f8}}
""".strip() + "\n"


_CATALOG_JS = r"""
(() => {
  const catalog = window.CPB_CATALOG_INDEX || {records: [], packs: []};
  const records = catalog.records || [];
  const pageSize = 60;
  let page = 0;
  const q = document.querySelector('#filter-query');
  const pack = document.querySelector('#filter-pack');
  const kind = document.querySelector('#filter-kind');
  const assets = document.querySelector('#filter-assets');
  const results = document.querySelector('#results');
  const count = document.querySelector('#result-count');
  const pageText = document.querySelector('#page-text');
  const prev = document.querySelector('#prev-page');
  const next = document.querySelector('#next-page');
  const addOption = (control, value, text) => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = text;
    control.appendChild(option);
  };
  for (const item of catalog.packs || []) addOption(pack, item.id, `${item.name} | ${item.id}`);
  for (const value of [...new Set(records.map(item => item.kind))].sort()) addOption(kind, value, value);

  const hashValues = () => new URLSearchParams(location.hash.replace(/^#/, ''));
  const applyHash = () => {
    const values = hashValues();
    if (values.has('q')) q.value = values.get('q') || '';
    if (values.has('pack') && [...pack.options].some(option => option.value === values.get('pack'))) pack.value = values.get('pack');
    if (values.has('kind') && [...kind.options].some(option => option.value === values.get('kind'))) kind.value = values.get('kind');
    if (values.has('assets') && [...assets.options].some(option => option.value === values.get('assets'))) assets.value = values.get('assets');
  };
  const syncHash = () => {
    const values = new URLSearchParams();
    if (q.value.trim()) values.set('q', q.value.trim());
    if (pack.value) values.set('pack', pack.value);
    if (kind.value) values.set('kind', kind.value);
    if (assets.value) values.set('assets', assets.value);
    const nextHash = values.toString();
    history.replaceState(null, '', nextHash ? `#${nextHash}` : location.pathname);
  };
  const filtered = () => {
    const needle = q.value.trim().toLocaleLowerCase();
    return records.filter(item => {
      const linkedCount = Number(item.linked_asset_count || 0);
      const assetMatch = !assets.value
        || (assets.value === 'with' && !item.is_asset && linkedCount > 0)
        || (assets.value === 'without' && !item.is_asset && linkedCount === 0)
        || (assets.value === 'evidence' && item.is_asset)
        || (assets.value === 'multiple' && !item.is_asset && linkedCount > 1);
      return (!pack.value || item.pack_id === pack.value)
        && (!kind.value || item.kind === kind.value)
        && assetMatch
        && (!needle || item.search.includes(needle));
    });
  };
  const render = () => {
    const selected = filtered();
    const pages = Math.max(1, Math.ceil(selected.length / pageSize));
    page = Math.max(0, Math.min(page, pages - 1));
    results.replaceChildren();
    for (const item of selected.slice(page * pageSize, (page + 1) * pageSize)) {
      const card = document.createElement('article');
      card.className = 'result-card';
      const copy = document.createElement('div');
      copy.className = 'result-copy';
      const eyebrow = document.createElement('p');
      eyebrow.className = 'eyebrow';
      eyebrow.textContent = `${item.kind} | ${item.pack_name}`;
      const title = document.createElement('h2');
      const link = document.createElement('a');
      link.href = item.page;
      link.textContent = item.label;
      title.appendChild(link);
      const id = document.createElement('code');
      id.textContent = item.id;
      const badges = document.createElement('div');
      badges.className = 'badges';
      for (const value of [...item.dimensions, ...item.groups].slice(0, 8)) {
        const badge = document.createElement('span');
        badge.className = 'badge';
        badge.textContent = value;
        badges.appendChild(badge);
      }
      const assetBadge = document.createElement('span');
      assetBadge.className = 'badge';
      assetBadge.textContent = item.is_asset
        ? `${item.linked_preset_count || 0} linked preset${item.linked_preset_count === 1 ? '' : 's'}`
        : `${item.linked_asset_count || 0} linked Visual Evidence record${item.linked_asset_count === 1 ? '' : 's'}`;
      badges.appendChild(assetBadge);
      copy.append(eyebrow, title, id, badges);
      card.appendChild(copy);
      if (item.thumbnail) {
        card.classList.add('has-thumbnail');
        const imageLink = document.createElement('a');
        imageLink.className = 'result-thumbnail';
        imageLink.href = item.page;
        imageLink.setAttribute('aria-label', `Open ${item.label}`);
        const image = document.createElement('img');
        image.className = 'result-thumb';
        image.loading = 'lazy';
        image.decoding = 'async';
        image.width = 160;
        image.height = 136;
        image.src = item.thumbnail;
        image.alt = `Preview for ${item.label}`;
        imageLink.appendChild(image);
        card.appendChild(imageLink);
      }
      results.appendChild(card);
    }
    if (!selected.length) {
      const empty = document.createElement('p');
      empty.className = 'notice';
      empty.textContent = 'No records match these filters.';
      results.appendChild(empty);
    }
    count.textContent = `${selected.length} of ${records.length} records match`;
    pageText.textContent = `Page ${page + 1} of ${pages}`;
    prev.disabled = page === 0;
    next.disabled = page + 1 >= pages;
  };
  const reset = () => { page = 0; syncHash(); render(); };
  q.addEventListener('input', reset);
  pack.addEventListener('change', reset);
  kind.addEventListener('change', reset);
  assets.addEventListener('change', reset);
  prev.addEventListener('click', () => { page -= 1; render(); window.scrollTo(0, 0); });
  next.addEventListener('click', () => { page += 1; render(); window.scrollTo(0, 0); });
  window.addEventListener('hashchange', () => { applyHash(); page = 0; render(); });
  applyHash();
  render();
})();
""".strip() + "\n"


def _html_shell(title: str, *, css_href: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' file: data:; style-src 'self' file:; script-src 'self' file:;">
  <title>{_escape(title)}</title>
  <link rel="stylesheet" href="{_escape(css_href)}">
</head>
<body>{body}</body>
</html>
"""



def _pack_summary_page(pack: InspectedPack, *, output_root: Path) -> str:
    page_relative = _pack_page_relative(pack)
    page_path = output_root / page_relative
    index_href = _relative_href(output_root / "index.html", from_directory=page_path.parent)
    search_target = output_root / "search.html"
    search_href = _relative_href(search_target, from_directory=page_path.parent) + "#pack=" + quote(pack.pack_id)
    visual_href = _relative_href(
        output_root / "visual-evidence" / "index.html",
        from_directory=page_path.parent,
    )
    warnings = [
        issue.to_dict()
        for issue in pack.validation.issues
        if issue.severity == "warning"
    ]
    kind_counts: dict[str, int] = {}
    for source in pack.validation.records:
        kind_counts[source.kind] = kind_counts.get(source.kind, 0) + 1
    kind_cards = "".join(
        '<article class="browse-card"><h2>'
        + _escape(kind)
        + '</h2><p>'
        + str(count)
        + ' records</p><a href="'
        + _escape(search_href + "&kind=" + quote(kind))
        + '">Browse this kind in this pack</a></article>'
        for kind, count in sorted(kind_counts.items())
    )
    body = (
        '<header class="page"><nav class="top-links"><a href="'
        + _escape(index_href)
        + '">Catalog home</a><a href="'
        + _escape(search_href)
        + '">Browse this pack</a><a href="'
        + _escape(visual_href)
        + '">Visual Evidence gallery</a></nav><h1>'
        + _escape(pack.name)
        + '</h1><p class="summary">Pack manifest, validation summary, and record-kind entry points.</p></header>'
        + '<main class="pack-page"><article class="pack-card"><dl><dt>UUID</dt><dd><code>'
        + _escape(pack.pack_id)
        + "</code></dd><dt>Release</dt><dd>"
        + _escape(pack.release)
        + "</dd><dt>Source pack</dt><dd><code>"
        + _escape((PurePosixPath("packs") / pack.root.name).as_posix())
        + "</code></dd><dt>Records</dt><dd>"
        + str(len(pack.validation.records))
        + "</dd></dl>"
        + (
            '<details><summary>Validation warnings ('
            + str(len(warnings))
            + ')</summary><pre class="raw-json">'
            + _escape(_json(warnings))
            + "</pre></details>"
            if warnings
            else ""
        )
        + '<section><h2>Browse record kinds</h2><div class="kind-grid">'
        + kind_cards
        + '</div></section><details><summary>Full pack manifest JSON</summary><pre class="raw-json">'
        + _escape(_json(pack.manifest))
        + "</pre></details></article></main>"
    )
    css_href = _relative_href(
        output_root / "assets" / "catalog.css",
        from_directory=page_path.parent,
    )
    return _html_shell(pack.name, css_href=css_href, body=body)

def _render_record_page(
    view: RecordView,
    linked_assets: Sequence[RecordView],
    records_by_id: Mapping[str, Sequence[RecordView]],
    *,
    page_map: Mapping[tuple[str, str], Path],
    output_root: Path,
    copy_assets: bool,
    copied: set[Path],
) -> str:
    record = view.record
    page_relative = page_map[(view.pack.pack_id, view.record_id)]
    page_path = output_root / page_relative
    label = str(record.get("label") or view.record_id)
    dimensions = _category_domain_values(view)
    groups = _grouping_fields(record)
    aliases = _walk_named_fields(record, lambda key: key.lower() in {"alias", "aliases"})
    outcomes = _walk_named_fields(record, lambda key: "outcome" in key.lower())
    facets = _walk_named_fields(record, lambda key: key.lower() == "facets")
    index_href = _relative_href(output_root / "index.html", from_directory=page_path.parent)
    search_href = _relative_href(output_root / "search.html", from_directory=page_path.parent)
    visual_href = _relative_href(
        output_root / "visual-evidence" / "index.html",
        from_directory=page_path.parent,
    )
    linked_presets_href = _relative_href(
        output_root / "linked-presets" / "index.html",
        from_directory=page_path.parent,
    )
    pack_href = _relative_href(
        output_root / _pack_page_relative(view.pack),
        from_directory=page_path.parent,
    )
    linked_html = ""
    if view.source.kind != "asset":
        if linked_assets:
            linked_html = (
                '<section class="linked-assets"><h3>Linked Visual Evidence ('
                + str(len(linked_assets))
                + ")</h3>"
                + "".join(
                    _asset_panel(
                        asset,
                        compact=True,
                        records_by_id=records_by_id,
                        page_path=page_path,
                        page_map=page_map,
                        output_root=output_root,
                        copy_assets=copy_assets,
                        copied=copied,
                    )
                    for asset in linked_assets
                )
                + "</section>"
            )
        else:
            linked_html = (
                '<section class="linked-assets no-linked-assets"><p class="muted">No Visual Evidence is linked to this record.</p></section>'
            )
    asset_html = (
        _asset_panel(
            view,
            compact=False,
            records_by_id=records_by_id,
            page_path=page_path,
            page_map=page_map,
            output_root=output_root,
            copy_assets=copy_assets,
            copied=copied,
        )
        if view.source.kind == "asset"
        else ""
    )
    body = (
        '<header class="page"><nav class="top-links"><a href="'
        + _escape(index_href)
        + '">Catalog home</a><a href="'
        + _escape(search_href)
        + '">Search</a><a href="'
        + _escape(visual_href)
        + '">Visual Evidence</a><a href="'
        + _escape(linked_presets_href)
        + '">Linked presets</a><a href="'
        + _escape(pack_href)
        + '">Pack manifest</a></nav><p class="eyebrow">'
        + _escape(view.source.kind)
        + " | "
        + _escape(view.pack.name)
        + "</p><h1>"
        + _escape(label)
        + "</h1><code>"
        + _escape(view.record_id)
        + "</code></header><main class=\"record-page\"><article class=\"record-card\">"
        + '<dl class="record-meta"><dt>Pack UUID</dt><dd><code>'
        + _escape(view.pack.pack_id)
        + "</code></dd><dt>Pack release</dt><dd>"
        + _escape(view.pack.release)
        + "</dd><dt>Source file</dt><dd><code>"
        + _escape(view.source.source_file)
        + "</code></dd><dt>Kind</dt><dd>"
        + _escape(view.source.kind)
        + "</dd><dt>Category / domain</dt><dd>"
        + (_escape(", ".join(dimensions)) if dimensions else '<span class="muted">none</span>')
        + "</dd></dl>"
        + _field_list("Family, group, and variant fields", groups)
        + _field_list("Aliases", aliases)
        + _field_list("Outcome fields", outcomes)
        + _field_list("Facets", facets)
        + linked_html
        + asset_html
        + '<details class="full-record" open><summary>Full canonical record JSON</summary>'
        + '<pre class="raw-json">'
        + _escape(_json(record))
        + "</pre></details></article></main>"
    )
    css_href = _relative_href(
        output_root / "assets" / "catalog.css",
        from_directory=page_path.parent,
    )
    return _html_shell(label, css_href=css_href, body=body)



def _record_index_entry(
    view: RecordView,
    linked_assets: Sequence[RecordView],
    linked_presets: Sequence[RecordView],
    *,
    page_map: Mapping[tuple[str, str], Path],
    output_root: Path,
    copy_assets: bool,
    copied: set[Path],
) -> dict[str, Any]:
    record = view.record
    label = str(record.get("label") or view.record_id)
    dimensions = _category_domain_values(view)
    groups = _grouping_values(record)
    evidence_text: list[str] = []
    if view.source.kind == "asset":
        evidence_text.extend(
            [
                str(record.get("description") or ""),
                *_strings(record.get("canonical_record_ids")),
            ]
        )
        preview_asset: RecordView | None = view
    else:
        for asset in linked_assets:
            evidence_text.extend(
                [
                    asset.record_id,
                    str(asset.record.get("label") or ""),
                    str(asset.record.get("description") or ""),
                ]
            )
        preview_asset = linked_assets[0] if linked_assets else None

    thumbnail = ""
    thumbnail_role = ""
    if preview_asset is not None:
        resource = _primary_preview_resource(preview_asset)
        if resource is not None:
            thumbnail = _resource_href(
                preview_asset,
                resource,
                page_path=output_root / "search.html",
                output_root=output_root,
                copy_assets=copy_assets,
                copied=copied,
            )
            thumbnail_role = ", ".join(resource.roles)

    searchable = _unique(
        [
            view.record_id,
            label,
            view.source.kind,
            view.pack.name,
            view.pack.pack_id,
            *dimensions,
            *groups,
            *_strings(record.get("aliases")),
            *_strings(record.get("tags")),
            *_strings(record.get("search_terms")),
            *evidence_text,
        ]
    )
    linked_count = len(linked_assets)
    return {
        "id": view.record_id,
        "label": label,
        "kind": view.source.kind,
        "is_asset_record": view.source.kind == "asset",
        "is_asset": view.source.kind == "asset",
        "pack_id": view.pack.pack_id,
        "pack_name": view.pack.name,
        "release": view.pack.release,
        "dimensions": dimensions,
        "groups": groups,
        "linked_asset_count": linked_count,
        "linked_preset_count": len(linked_presets),
        "asset_count": linked_count,
        "thumbnail": thumbnail,
        "thumbnail_role": thumbnail_role,
        "page": page_map[(view.pack.pack_id, view.record_id)].as_posix(),
        "search": " ".join(searchable).lower(),
    }

def _svg_artifacts(asset: RecordView) -> list[dict[str, Any]]:
    """Return the authored SVG artifact inventory for one asset record."""

    output: list[dict[str, Any]] = []
    for artifact in asset.record.get("artifacts") or []:
        if not isinstance(artifact, Mapping):
            continue
        media_type = str(artifact.get("media_type") or "")
        path = str(artifact.get("path") or "")
        if media_type == "image/svg+xml" or path.lower().endswith(".svg"):
            output.append(
                {
                    "artifact_id": artifact.get("artifact_id"),
                    "role": artifact.get("role"),
                    "path": path,
                    "media_type": media_type or "image/svg+xml",
                    "sha256": artifact.get("sha256"),
                }
            )
    return output


def _asset_map_document(
    records: Sequence[RecordView],
    assets_by_record: Mapping[tuple[str, str], Sequence[RecordView]],
    records_by_asset: Mapping[tuple[str, str], Sequence[RecordView]],
    page_map: Mapping[tuple[str, str], Path],
    unresolved: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    record_map: dict[str, Any] = {}
    asset_map: dict[str, Any] = {}
    by_key = {(view.pack.pack_id, view.record_id): view for view in records}
    for key, assets in sorted(assets_by_record.items()):
        record = by_key[key]
        linked = [
            {
                "asset_pack_id": asset.pack.pack_id,
                "asset_id": asset.record_id,
                "asset_label": asset.record.get("label"),
                "asset_page": page_map[(asset.pack.pack_id, asset.record_id)].as_posix(),
                "primary_resource": asset.record.get("primary_resource"),
                "svg_artifacts": _svg_artifacts(asset),
            }
            for asset in assets
        ]
        record_map[f"{record.pack.pack_id}:{record.record_id}"] = {
            "record_pack_id": record.pack.pack_id,
            "record_id": record.record_id,
            "record_label": record.record.get("label"),
            "record_page": page_map[key].as_posix(),
            "assets": linked,
        }
    for key, linked_records in sorted(records_by_asset.items()):
        asset = by_key[key]
        asset_map[f"{asset.pack.pack_id}:{asset.record_id}"] = {
            "asset_pack_id": asset.pack.pack_id,
            "asset_id": asset.record_id,
            "asset_label": asset.record.get("label"),
            "asset_page": page_map[key].as_posix(),
            "primary_resource": asset.record.get("primary_resource"),
            "svg_artifacts": _svg_artifacts(asset),
            "linked_records": [
                {
                    "record_pack_id": record.pack.pack_id,
                    "record_id": record.record_id,
                    "record_label": record.record.get("label"),
                    "record_page": page_map[(record.pack.pack_id, record.record_id)].as_posix(),
                }
                for record in linked_records
            ],
        }
    return {
        "format": "character-prompt-builder-catalog-asset-map",
        "summary": {
            "canonical_records_with_assets": len(record_map),
            "asset_records_with_canonical_links": len(asset_map),
            "canonical_asset_link_count": sum(
                len(value.get("assets") or []) for value in record_map.values()
            ),
            "svg_artifact_count": sum(
                len(value.get("svg_artifacts") or []) for value in asset_map.values()
            ),
            "unresolved_link_count": len(unresolved),
        },
        "records": record_map,
        "assets": asset_map,
        "unresolved": list(unresolved),
    }


def _home_html(
    title: str,
    *,
    packs: Sequence[InspectedPack],
    record_count: int,
    asset_count: int,
    linked_record_count: int,
    kind_counts: Mapping[str, int],
) -> str:
    pack_cards = "".join(
        '<a class="home-card" href="'
        + _escape(_pack_page_relative(pack).as_posix())
        + '"><span class="home-count">'
        + str(len(pack.validation.records))
        + '</span><h2>'
        + _escape(pack.name)
        + '</h2><p>Release '
        + _escape(pack.release)
        + '</p></a>'
        for pack in packs
    )
    leading_kinds = sorted(kind_counts.items(), key=lambda item: (-item[1], item[0]))[:8]
    kind_summary = ", ".join(f"{kind}: {count}" for kind, count in leading_kinds)
    body = (
        '<header class="page"><h1>'
        + _escape(title)
        + '</h1><p class="summary">A direct-open landing page. Choose a visual gallery, linked preset gallery, text search, pack, or record kind without knowing internal IDs first.</p>'
        + '<p class="muted">Validated packs: '
        + str(len(packs))
        + ' | Records: '
        + str(record_count)
        + ' | Visual Evidence records: '
        + str(asset_count)
        + ' | Presets with linked Visual Evidence: '
        + str(linked_record_count)
        + '</p></header><main><section class="home-grid">'
        + '<a class="home-card" href="visual-evidence/index.html"><span class="home-count">'
        + str(asset_count)
        + '</span><h2>Browse Visual Evidence</h2><p>Start with preview thumbnails, then open a Visual Evidence record or linked preset.</p></a>'
        + '<a class="home-card" href="linked-presets/index.html"><span class="home-count">'
        + str(linked_record_count)
        + '</span><h2>Browse presets with Visual Evidence</h2><p>Preset-first browsing with thumbnails from linked Visual Evidence.</p></a>'
        + '<a class="home-card" href="search.html"><span class="home-count">'
        + str(record_count)
        + '</span><h2>Search all records</h2><p>Search labels, tags, families, packs, linked Visual Evidence descriptions, and IDs.</p></a>'
        + '<a class="home-card" href="browse/kinds.html"><span class="home-count">'
        + str(len(kind_counts))
        + '</span><h2>Browse by record kind</h2><p>'
        + _escape(kind_summary)
        + '</p></a>'
        + '</section><section class="page"><h2>Browse by pack</h2><div class="pack-grid">'
        + pack_cards
        + '</div></section></main>'
    )
    return _html_shell(title, css_href="assets/catalog.css", body=body)


def _search_html(
    title: str,
    *,
    record_count: int,
    linked_record_count: int,
    asset_count: int,
    multiple_link_count: int,
) -> str:
    body = f"""
<header class="page">
  <nav class="top-links"><a href="index.html">Catalog home</a><a href="visual-evidence/index.html">Visual Evidence gallery</a><a href="linked-presets/index.html">Linked preset gallery</a></nav>
  <h1>{_escape(title)} search</h1>
  <p class="summary">Compact text search. Only the current page of at most 60 cards is rendered; linked records show preview thumbnails from their Visual Evidence.</p>
</header>
<section class="toolbar" aria-label="Catalog filters">
  <label>Search<input id="filter-query" type="search" placeholder="Description, label, tag, domain, family, or ID"></label>
  <label>Pack<select id="filter-pack"><option value="">All packs</option></select></label>
  <label>Kind<select id="filter-kind"><option value="">All kinds</option></select></label>
  <label>Visual Evidence<select id="filter-assets"><option value="">All records ({record_count})</option><option value="with">Presets with linked Visual Evidence ({linked_record_count})</option><option value="without">Presets without linked Visual Evidence ({record_count - linked_record_count - asset_count})</option><option value="evidence">Visual Evidence records ({asset_count})</option><option value="multiple">Presets with multiple Visual Evidence records ({multiple_link_count})</option></select></label>
</section>
<main class="content">
  <p id="result-count" aria-live="polite"></p>
  <section id="results" class="results"></section>
  <nav class="pagination"><button id="prev-page" type="button">Previous</button><span id="page-text"></span><button id="next-page" type="button">Next</button></nav>
  <noscript><p class="notice">JavaScript is required for text filtering. The Visual Evidence and linked preset galleries remain ordinary paginated HTML.</p></noscript>
</main>
<script src="data/catalog-index.js"></script>
<script src="assets/catalog.js"></script>
"""
    return _html_shell(title + " search", css_href="assets/catalog.css", body=body)


def _kind_index_html(
    kind_counts: Mapping[str, int],
    *,
    output_root: Path,
) -> str:
    page_path = output_root / "browse" / "kinds.html"
    home_href = _relative_href(output_root / "index.html", from_directory=page_path.parent)
    search_href = _relative_href(output_root / "search.html", from_directory=page_path.parent)
    cards = "".join(
        '<article class="browse-card"><h2>'
        + _escape(kind)
        + '</h2><p>'
        + str(count)
        + ' records</p><a href="'
        + _escape(search_href + "#kind=" + quote(kind))
        + '">Browse '
        + _escape(kind)
        + '</a></article>'
        for kind, count in sorted(kind_counts.items())
    )
    body = (
        '<header class="page"><nav class="top-links"><a href="'
        + _escape(home_href)
        + '">Catalog home</a><a href="'
        + _escape(search_href)
        + '">Search all records</a></nav><h1>Browse by record kind</h1></header>'
        + '<main class="content"><section class="kind-grid">'
        + cards
        + '</section></main>'
    )
    css_href = _relative_href(output_root / "assets" / "catalog.css", from_directory=page_path.parent)
    return _html_shell("Browse by record kind", css_href=css_href, body=body)


def write_catalog_directory(
    packs: Sequence[InspectedPack],
    output_directory: Path,
    *,
    title: str = "Character Prompt Builder Pack Catalog",
    overwrite: bool = False,
    copy_assets: bool = False,
) -> dict[str, Any]:
    """Write a direct-open landing page, search page, galleries, and record pages."""

    requested_output = output_directory.expanduser()
    if requested_output.is_symlink():
        raise PackError(f"Inspection output must not be a symbolic link: {requested_output}")
    output_directory = requested_output.resolve()
    for pack in packs:
        pack_root = pack.root.resolve()
        if (
            output_directory == pack_root
            or output_directory in pack_root.parents
            or pack_root in output_directory.parents
        ):
            raise PackError(
                "Inspection output must not overlap a source pack or its ancestors: "
                f"{output_directory}"
            )
    if output_directory.exists() and not overwrite:
        raise PackError(
            f"Output directory already exists; pass --overwrite to replace it: {output_directory}"
        )
    if output_directory.exists() and not output_directory.is_dir():
        raise PackError(f"Inspection output must be a directory: {output_directory}")
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}.tmp-",
            dir=str(output_directory.parent),
        )
    )
    try:
        records = [
            RecordView(pack, source)
            for pack in packs
            for source in pack.validation.records
        ]
        assets = [view for view in records if view.source.kind == "asset"]
        (
            records_by_id,
            assets_by_record,
            records_by_asset,
            unresolved,
        ) = _build_catalog_links(records)
        if unresolved:
            raise PackError(
                "Catalog contains unresolved canonical asset links: "
                + "; ".join(
                    f"{item['asset_id']} -> "
                    f"{item.get('canonical_pack_id') or '*'}:{item['canonical_record_id']}"
                    for item in unresolved
                )
            )
        page_map = {
            (view.pack.pack_id, view.record_id): _record_page_relative(view)
            for view in records
        }
        for directory in (
            "assets",
            "data",
            "packs",
            "records",
            "browse",
            "visual-evidence",
            "linked-presets",
        ):
            (temporary / directory).mkdir(parents=True, exist_ok=True)
        (temporary / "assets" / "catalog.css").write_text(
            _CATALOG_CSS,
            encoding="utf-8",
            newline="\n",
        )
        (temporary / "assets" / "catalog.js").write_text(
            _CATALOG_JS,
            encoding="utf-8",
            newline="\n",
        )
        copied: set[Path] = set()
        for pack in packs:
            page_relative = _pack_page_relative(pack)
            page_path = temporary / page_relative
            page_path.parent.mkdir(parents=True, exist_ok=True)
            page_path.write_text(
                _pack_summary_page(pack, output_root=temporary),
                encoding="utf-8",
                newline="\n",
            )

        index_records: list[dict[str, Any]] = []
        for view in records:
            key = (view.pack.pack_id, view.record_id)
            linked_assets = list(assets_by_record.get(key, ()))
            linked_presets = list(records_by_asset.get(key, ()))
            page_relative = page_map[key]
            page_path = temporary / page_relative
            page_path.parent.mkdir(parents=True, exist_ok=True)
            page_path.write_text(
                _render_record_page(
                    view,
                    linked_assets,
                    records_by_id,
                    page_map=page_map,
                    output_root=temporary,
                    copy_assets=copy_assets,
                    copied=copied,
                ),
                encoding="utf-8",
                newline="\n",
            )
            index_records.append(
                _record_index_entry(
                    view,
                    linked_assets,
                    linked_presets,
                    page_map=page_map,
                    output_root=temporary,
                    copy_assets=copy_assets,
                    copied=copied,
                )
            )

        visual_pages = _visual_evidence_gallery_pages(
            assets,
            records_by_asset,
            page_map=page_map,
            output_root=temporary,
            copy_assets=copy_assets,
            copied=copied,
        )
        linked_preset_pages = _linked_preset_gallery_pages(
            records,
            assets_by_record,
            page_map=page_map,
            output_root=temporary,
            copy_assets=copy_assets,
            copied=copied,
        )

        kind_counts: dict[str, int] = {}
        for view in records:
            kind_counts[view.source.kind] = kind_counts.get(view.source.kind, 0) + 1
        (temporary / "browse" / "kinds.html").write_text(
            _kind_index_html(kind_counts, output_root=temporary),
            encoding="utf-8",
            newline="\n",
        )

        index_payload = {
            "format": "character-prompt-builder-catalog-index",
            "packs": [
                {
                    "id": pack.pack_id,
                    "name": pack.name,
                    "release": pack.release,
                    "page": _pack_page_relative(pack).as_posix(),
                    "record_count": len(pack.validation.records),
                }
                for pack in packs
            ],
            "records": index_records,
        }
        (temporary / "data" / "catalog-index.js").write_text(
            "window.CPB_CATALOG_INDEX="
            + json.dumps(index_payload, ensure_ascii=False, separators=(",", ":"))
            + ";\n",
            encoding="utf-8",
            newline="\n",
        )
        asset_map = _asset_map_document(
            records,
            assets_by_record,
            records_by_asset,
            page_map,
            unresolved,
        )
        (temporary / "data" / "record-asset-map.json").write_text(
            json.dumps(asset_map, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

        linked_record_count = len(assets_by_record)
        multiple_link_count = sum(1 for value in assets_by_record.values() if len(value) > 1)
        manifest = {
            "format": "character-prompt-builder-split-catalog",
            "entry_point": "index.html",
            "search_entry_point": "search.html",
            "visual_evidence_entry_point": visual_pages[0].as_posix(),
            "linked_presets_entry_point": linked_preset_pages[0].as_posix(),
            "kind_entry_point": "browse/kinds.html",
            "pack_count": len(packs),
            "packs": [
                {
                    "pack_id": pack.pack_id,
                    "name": pack.name,
                    "release": pack.release,
                    "record_count": len(pack.validation.records),
                }
                for pack in packs
            ],
            "record_count": len(records),
            "record_kind_counts": dict(sorted(kind_counts.items())),
            "asset_record_count": len(assets),
            "canonical_records_with_assets": linked_record_count,
            "canonical_asset_link_count": sum(len(value) for value in assets_by_record.values()),
            "visual_gallery_page_count": len(visual_pages),
            "linked_preset_gallery_page_count": len(linked_preset_pages),
            "unresolved_asset_links": unresolved,
            "copied_resource_count": len(copied),
            "resource_mode": "copied" if copy_assets else "relative-to-source-pack",
            "pack_discovery": "all explicitly selected or discovered validated packs; no pack ID is hard-coded by the exporter",
        }
        (temporary / "catalog-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        (temporary / "index.html").write_text(
            _home_html(
                title,
                packs=packs,
                record_count=len(records),
                asset_count=len(assets),
                linked_record_count=linked_record_count,
                kind_counts=kind_counts,
            ),
            encoding="utf-8",
            newline="\n",
        )
        (temporary / "search.html").write_text(
            _search_html(
                title,
                record_count=len(records),
                linked_record_count=linked_record_count,
                asset_count=len(assets),
                multiple_link_count=multiple_link_count,
            ),
            encoding="utf-8",
            newline="\n",
        )
        if not output_directory.exists():
            os.replace(temporary, output_directory)
            temporary = None
        else:
            backup_parent = Path(
                tempfile.mkdtemp(
                    prefix=f".{output_directory.name}.previous-",
                    dir=str(output_directory.parent),
                )
            )
            backup = backup_parent / output_directory.name
            os.replace(output_directory, backup)
            try:
                os.replace(temporary, output_directory)
                temporary = None
            except BaseException:
                os.replace(backup, output_directory)
                raise
            else:
                shutil.rmtree(backup, ignore_errors=True)
            finally:
                try:
                    backup_parent.rmdir()
                except OSError:
                    pass
    finally:
        if temporary is not None and temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
    index_path = output_directory / "index.html"
    search_path = output_directory / "search.html"
    index_script = output_directory / "data" / "catalog-index.js"
    detail_pages = sum(1 for _ in (output_directory / "records").rglob("*.html"))
    return {
        "ok": True,
        "output_directory": str(output_directory),
        "index": str(index_path),
        "index_bytes": index_path.stat().st_size,
        "search": str(search_path),
        "search_bytes": search_path.stat().st_size,
        "index_script_bytes": index_script.stat().st_size,
        "pack_count": len(packs),
        "record_count": sum(len(pack.validation.records) for pack in packs),
        "asset_record_count": len(assets),
        "record_page_count": detail_pages,
        "canonical_records_with_assets": len(assets_by_record),
        "canonical_asset_link_count": sum(len(value) for value in assets_by_record.values()),
        "visual_gallery_page_count": len(visual_pages),
        "linked_preset_gallery_page_count": len(linked_preset_pages),
        "resource_mode": "copied" if copy_assets else "relative-to-source-pack",
    }

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a split catalog with a small direct-open index.html, "
            "separate record pages, an explicit record-to-asset map, and linked Visual Evidence previews."
        )
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--pack",
        action="append",
        type=Path,
        help="Explicit validated pack directory; repeat to inspect multiple packs.",
    )
    source.add_argument(
        "--pack-tree",
        type=Path,
        help=(
            "Explicit directory tree containing pack.json files. Every validated "
            "pack beneath the tree is included deterministically, so later packs "
            "are picked up without editing the exporter command."
        ),
    )
    source.add_argument(
        "--state",
        type=Path,
        help="Explicit pack-state JSON file; only enabled packs are inspected.",
    )
    source.add_argument(
        "--settings",
        type=Path,
        help=(
            "Explicit inspector-settings JSON with state_file, optional roots, and "
            "optional default pack/provider selections."
        ),
    )
    parser.add_argument(
        "--pack-root",
        action="append",
        type=Path,
        default=[],
        help="Explicit discovery root used with --state; repeat as needed.",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output directory containing index.html.",
    )
    parser.add_argument("--title", default="Character Prompt Builder Pack Catalog")
    parser.add_argument(
        "--released",
        action="store_true",
        help="Require and verify pack.lock.json for every inspected pack.",
    )
    parser.add_argument(
        "--copy-assets",
        action="store_true",
        help=(
            "Copy linked resources into the catalog for standalone portability. "
            "By default, record pages use relative links to validated pack resources."
        ),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output directory or launcher.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.pack:
            if args.pack_root:
                raise PackError("--pack-root is valid only with --state.")
            packs = load_pack_directories(args.pack, require_lock=args.released)
        elif args.pack_tree:
            if args.pack_root:
                raise PackError("--pack-root is valid only with --state.")
            packs = discover_pack_tree(args.pack_tree, require_lock=args.released)
        elif args.state:
            packs = load_explicit_state(
                args.state,
                args.pack_root,
                require_lock=args.released,
            )
        else:
            if args.pack_root:
                raise PackError("--pack-root is valid only with --state.")
            packs = load_explicit_settings(args.settings, require_lock=args.released)
        result = write_catalog_directory(
            packs,
            args.output,
            title=args.title,
            overwrite=args.overwrite,
            copy_assets=args.copy_assets,
        )
    except (OSError, PackError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
