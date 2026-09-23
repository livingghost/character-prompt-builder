#!/usr/bin/env python3
"""Maintain the derived searchable catalog cache for enabled content packs."""
from __future__ import annotations

import json
import mimetypes
import os
import sqlite3
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from execution_contract import lock
from pack_manager import (
    DiscoveredPack,
    PackError,
    PackRecord,
    PackSettings,
    PackValidation,
    active_snapshot,
    canonical_json,
    default_settings,
    load_effective_state,
    pack_cli_command,
    required_dependency_cycles,
    resolve_enabled_lenient,
    sha256_bytes,
    sha256_file,
    validate_pack,
)
from search_discovery import (
    FACET_BY_CATEGORY,
    KIND_PRIMARY_FACET,
    build_search_profile,
    normalize,
)
from resource_policy import (
    validate_discovery_lane_targets,
    validate_species_scaffold_targets,
)

ROOT = Path(__file__).resolve().parents[1]
CACHE_FILENAME = "catalog.sqlite3"


@dataclass(frozen=True)
class RuntimePackEntry:
    kind: str
    category: str | None
    record: dict[str, Any]
    source_pack: str
    source_root: Path
    source_file: str


@dataclass(frozen=True)
class RuntimePackResource:
    name: str
    path: Path
    media_type: str
    source_pack: str


@dataclass(frozen=True)
class RuntimePackCatalog:
    fingerprint: str
    active_pack_count: int
    entries: tuple[RuntimePackEntry, ...]
    phrases: dict[str, list[dict[str, Any]]]
    profiles: dict[str, dict[str, Any]]
    resources: dict[str, RuntimePackResource]
    assets_by_canonical_record: dict[str, tuple[RuntimePackEntry, ...]]
    diagnostics: tuple[dict[str, Any], ...]
    # One line per pack the catalog left out, naming the reason and the fix.
    warnings: tuple[str, ...] = ()


def _builder_fingerprint() -> str:
    paths = (
        Path(__file__).resolve(),
        Path(__file__).with_name("pack_manager.py").resolve(),
        Path(__file__).with_name("resource_policy.py").resolve(),
        Path(__file__).with_name("search_discovery.py").resolve(),
        Path(__file__).with_name("state_protocol.py").resolve(),
        ROOT / "schemas" / "pack.schema.json",
        ROOT / "schemas" / "pack-lock.schema.json",
        ROOT / "schemas" / "pack-record-file.schema.json",
        ROOT / "schemas" / "pack-state.schema.json",
    )
    payload = [
        {"path": path.name, "sha256": sha256_file(path)}
        for path in paths
    ]
    return sha256_bytes(canonical_json(payload).encode("utf-8"))


CACHE_STEM, _, CACHE_SUFFIX = CACHE_FILENAME.rpartition(".")


def cache_path(settings: PackSettings, fingerprint: str) -> Path:
    """Where the cache built from `fingerprint` lives.

    The name states what the file was built from, so a build writes a name that
    does not exist yet rather than replacing the name readers hold open. Windows
    refuses to rename onto an open file, which is what let a reader fail
    somebody else's rebuild. A published file is never rewritten, because its
    content is settled by its name, so a reader needs no lock and a build waits
    for no reader.
    """

    return settings.cache_dir / f"{CACHE_STEM}-{fingerprint}.{CACHE_SUFFIX}"


def _existing_caches(settings: PackSettings) -> list[Path]:
    """Every cache file present, newest first.

    A modification time orders files here and settles nothing about content: it
    answers which cache arrived later, which is a fact about the directory. One
    discarded between being listed and being asked is left out rather than
    raised, because the answer to "is it there" became no while we were looking.
    """

    try:
        found = list(settings.cache_dir.glob(f"{CACHE_STEM}-*.{CACHE_SUFFIX}"))
    except OSError:
        return []
    rows: list[tuple[int, Path]] = []
    for path in found:
        try:
            rows.append((path.stat().st_mtime_ns, path))
        except OSError:
            continue
    rows.sort(key=lambda row: row[0], reverse=True)
    return [path for _, path in rows]


def _discard_superseded(settings: PackSettings, keep: Path) -> None:
    """Remove the caches this one superseded, and only those.

    A cache that arrived after the one being kept was built from inputs this
    caller has not seen, and is another process's current answer rather than an
    obsolete one. Removing it would delete a live cache and start a rebuild that
    the other process would then delete in turn. Only what predates `keep` is
    this caller's to discard.

    A reader that already opened one is unharmed: POSIX keeps its handle valid
    after the unlink, and Windows refuses the unlink outright. A refusal is
    skipped rather than reported, because nothing addresses that file any more
    and the next caller removes it once the reader has finished.
    """

    try:
        boundary = keep.stat().st_mtime_ns
    except OSError:
        return
    for candidate in _existing_caches(settings):
        if candidate == keep:
            continue
        try:
            if candidate.stat().st_mtime_ns >= boundary:
                continue
            candidate.unlink()
        except OSError:
            continue


def _connect_readonly(path: Path) -> sqlite3.Connection:
    """Open an existing cache without the power to create one.

    A plain connect to a missing path creates an empty database, which would
    read as a catalog with nothing in it. Read-only raises instead, so a cache
    discarded between finding it and opening it is an error and not silence.
    """

    return sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)


def _fetchall(connection: sqlite3.Connection, query: str) -> list[tuple[Any, ...]]:
    cursor = connection.execute(query)
    try:
        return cursor.fetchall()
    finally:
        cursor.close()


def _read_meta(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    connection: sqlite3.Connection | None = None
    try:
        connection = _connect_readonly(path)
        rows = _fetchall(connection, "SELECT key, value FROM meta")
    except sqlite3.Error:
        return {}
    finally:
        if connection is not None:
            connection.close()
    return {str(key): str(value) for key, value in rows}


def _cached_active_pack_count(path: Path) -> int:
    """How many packs the built cache actually holds, as the cache recorded it."""

    return int(_read_meta(path).get("active_pack_count") or 0)


def _expected_fingerprint(snapshot: Mapping[str, Any]) -> str:
    return sha256_bytes(
        canonical_json(
            {
                "builder": _builder_fingerprint(),
                "snapshot": snapshot,
            }
        ).encode("utf-8")
    )


def _cache_lock(settings: PackSettings):
    """The lock a build takes. Readers never take it.

    The operating system holds it and releases it when the holder exits, however
    it exits, so a live builder is waited for and a dead one never blocks.
    """

    return lock(settings.cache_dir)


def _required_pack_ids(pack: DiscoveredPack) -> frozenset[str]:
    """The packs this one needs present. A dependency names a pack, not a version."""

    return frozenset(
        str(row.get("pack_id"))
        for row in pack.manifest.get("dependencies") or []
        if isinstance(row, Mapping) and row.get("pack_id")
    )


def _replacement_sources(pack: DiscoveredPack) -> dict[str, set[str]]:
    output: dict[str, set[str]] = {}
    for row in pack.manifest.get("replaces") or []:
        if not isinstance(row, Mapping):
            continue
        record_id = str(row.get("record_id") or "")
        source = str(row.get("from_pack") or "")
        if record_id and source:
            output.setdefault(record_id, set()).add(source)
    return output


def _remove_broken_dependencies(
    packs: list[tuple[DiscoveredPack, list[PackRecord]]],
    diagnostics: list[dict[str, Any]],
) -> list[tuple[DiscoveredPack, list[PackRecord]]]:
    active = {pack.pack_id: (pack, records) for pack, records in packs}
    cycles = required_dependency_cycles({pack_id: row[0] for pack_id, row in active.items()})
    for cycle in cycles:
        cycle_set = set(cycle)
        diagnostics.append(
            {
                "severity": "error",
                "code": "required-dependency-cycle",
                "pack_ids": list(cycle),
                "message": (
                    "Packs were excluded because required dependencies form a cycle: "
                    + " -> ".join((*cycle, cycle[0]))
                ),
            }
        )
        for pack_id in cycle_set:
            active.pop(pack_id, None)
    changed = True
    while changed:
        changed = False
        for pack_id, (pack, _) in list(active.items()):
            for dependency_id in sorted(_required_pack_ids(pack)):
                dependency = active.get(dependency_id)
                if dependency is None:
                    diagnostics.append(
                        {
                            "severity": "error",
                            "code": "missing-active-dependency",
                            "pack_id": pack_id,
                            "root": str(pack.root),
                            "requires": dependency_id,
                            "message": (
                                f"Pack {pack_id} was excluded because required pack "
                                f"{dependency_id} is unavailable."
                            ),
                        }
                    )
                    active.pop(pack_id, None)
                    changed = True
                    break
    return [active[pack.pack_id] for pack, _ in packs if pack.pack_id in active]


def _resolve_records(
    packs: Sequence[tuple[DiscoveredPack, list[PackRecord]]],
    diagnostics: list[dict[str, Any]],
) -> list[tuple[DiscoveredPack, PackRecord]]:
    candidates: dict[str, dict[str, tuple[DiscoveredPack, PackRecord]]] = {}
    replacement_maps = {pack.pack_id: _replacement_sources(pack) for pack, _ in packs}
    for pack, records in packs:
        for record in records:
            record_id = str(record.record.get("id") or "")
            candidates.setdefault(record_id, {})[pack.pack_id] = (pack, record)

    selected: dict[str, tuple[DiscoveredPack, PackRecord]] = {}
    for record_id, rows in sorted(candidates.items()):
        if len(rows) == 1:
            selected[record_id] = next(iter(rows.values()))
            continue
        pack_ids = set(rows)
        winners: list[str] = []
        for candidate_id in sorted(pack_ids):
            other_ids = pack_ids - {candidate_id}
            replaced_ids = replacement_maps[candidate_id].get(record_id, set())
            if not other_ids.issubset(replaced_ids):
                continue
            if any(
                candidate_id in replacement_maps[other_id].get(record_id, set())
                for other_id in other_ids
            ):
                continue
            winners.append(candidate_id)
        if len(winners) == 1:
            selected[record_id] = rows[winners[0]]
            continue
        ordered_ids = sorted(pack_ids)
        diagnostics.append(
            {
                "severity": "error",
                "code": "record-id-conflict",
                "record_id": record_id,
                "pack_ids": ordered_ids,
                "message": (
                    f"Record ID {record_id!r} was excluded because packs {ordered_ids} "
                    "do not declare one global, unambiguous replacement winner."
                ),
            }
        )
    return [selected[key] for key in sorted(selected)]


def _remove_broken_record_references(
    records: Sequence[tuple[DiscoveredPack, PackRecord]],
    diagnostics: list[dict[str, Any]],
) -> list[tuple[DiscoveredPack, PackRecord]]:
    """Exclude assets whose declared canonical records are not active."""
    available_ids = {
        str(record.record.get("id") or "")
        for _, record in records
        if record.kind != "asset"
    }
    resolved: list[tuple[DiscoveredPack, PackRecord]] = []
    for pack, record in records:
        raw_references = record.record.get("canonical_record_ids")
        if record.kind != "asset" or raw_references is None:
            resolved.append((pack, record))
            continue
        references = [str(value) for value in raw_references]
        missing = sorted(set(references) - available_ids)
        if not missing:
            resolved.append((pack, record))
            continue
        record_id = str(record.record.get("id") or "")
        diagnostics.append(
            {
                "severity": "error",
                "code": "missing-canonical-record",
                "pack_id": pack.pack_id,
                "record_id": record_id,
                "missing_record_ids": missing,
                "message": (
                    f"Asset record {record_id!r} was excluded because its canonical "
                    f"records are not active: {missing}."
                ),
            }
        )
    return resolved


def _resolve_resources(
    packs: Sequence[tuple[DiscoveredPack, list[PackRecord]]],
    reports: Mapping[str, Any],
    providers: Mapping[str, str],
    diagnostics: list[dict[str, Any]],
) -> list[tuple[DiscoveredPack, str, str]]:
    candidates: dict[str, dict[str, tuple[DiscoveredPack, str]]] = {}
    active_ids = {pack.pack_id for pack, _ in packs}
    for pack, _ in packs:
        report = reports.get(pack.pack_id)
        bindings = getattr(report, "resource_bindings", {})
        for name, relative in sorted(bindings.items()):
            candidates.setdefault(name, {})[pack.pack_id] = (pack, relative)

    selected: list[tuple[DiscoveredPack, str, str]] = []
    all_names = sorted(set(candidates) | set(providers))
    for name in all_names:
        provider_id = providers.get(name)
        available = candidates.get(name, {})
        if provider_id is None:
            diagnostics.append(
                {
                    "severity": "warning",
                    "code": "resource-provider-unselected",
                    "resource": name,
                    "candidate_packs": sorted(available),
                    "message": (
                        f"Named resource {name!r} was excluded because no provider "
                        "pack is selected in state."
                    ),
                }
            )
            continue
        selected_row = available.get(provider_id)
        if selected_row is None:
            diagnostics.append(
                {
                    "severity": "error",
                    "code": "resource-provider-unavailable",
                    "resource": name,
                    "provider_pack": provider_id,
                    "provider_active": provider_id in active_ids,
                    "available_providers": sorted(available),
                    "message": (
                        f"Named resource {name!r} was excluded because selected provider "
                        f"{provider_id} is not an active pack that supplies it."
                    ),
                }
            )
            continue
        pack, relative = selected_row
        selected.append((pack, name, relative))
    return selected


def _apply_contextual_resource_contracts(
    resources: Sequence[tuple[DiscoveredPack, str, str]],
    records: Sequence[tuple[DiscoveredPack, PackRecord]],
    diagnostics: list[dict[str, Any]],
) -> list[tuple[DiscoveredPack, str, str]]:
    """Reject selected known resources whose references miss active records."""
    canonical_ids = {
        str(record.record.get("id") or "")
        for _, record in records
        if record.record.get("id")
    }
    species_ids = {
        str(record.record.get("id") or "")
        for _, record in records
        if record.kind == "module"
        and record.category == "species"
        and record.record.get("id")
    }
    accepted: list[tuple[DiscoveredPack, str, str]] = []
    for pack, name, relative in resources:
        if name not in {"discovery-lanes", "species-scaffold-map"}:
            accepted.append((pack, name, relative))
            continue
        path = pack.root / relative
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            errors = (
                validate_discovery_lane_targets(value, canonical_ids)
                if name == "discovery-lanes"
                else validate_species_scaffold_targets(value, species_ids)
            )
        except (OSError, json.JSONDecodeError) as exc:
            errors = [str(exc)]
        if errors:
            diagnostics.append(
                {
                    "severity": "error",
                    "code": "known-resource-contract",
                    "resource": name,
                    "provider_pack": pack.pack_id,
                    "path": str(path.resolve()),
                    "errors": errors,
                    "message": (
                        f"Named resource {name!r} was excluded because its active-record "
                        "references do not satisfy the core semantic contract."
                    ),
                }
            )
            continue
        accepted.append((pack, name, relative))
    return accepted


def _resolve_runtime_pack_inputs(
    settings: PackSettings,
) -> tuple[
    list[DiscoveredPack],
    list[tuple[DiscoveredPack, list[PackRecord]]],
    dict[str, dict[str, Any]],
    dict[str, PackValidation],
    list[dict[str, Any]],
]:
    """Validate enabled packs and apply the runtime dependency-closure policy once."""
    selected, discovery_issues = resolve_enabled_lenient(settings)
    diagnostics: list[dict[str, Any]] = [issue.to_dict() for issue in discovery_issues]
    valid_packs: list[tuple[DiscoveredPack, list[PackRecord]]] = []
    pack_reports: dict[str, dict[str, Any]] = {}
    pack_validations: dict[str, PackValidation] = {}
    for pack in selected:
        report = validate_pack(pack.root)
        pack_reports[pack.pack_id] = report.to_dict()
        pack_validations[pack.pack_id] = report
        if report.valid:
            valid_packs.append((pack, report.records))
        else:
            diagnostics.append(
                {
                    "severity": "error",
                    "code": "invalid-enabled-pack",
                    "pack_id": pack.pack_id,
                    "root": str(pack.root),
                    "message": f"Pack {pack.pack_id} was excluded because validation failed.",
                    "details": report.to_dict()["errors"],
                }
            )
    valid_packs = _remove_broken_dependencies(valid_packs, diagnostics)
    return selected, valid_packs, pack_reports, pack_validations, diagnostics


# A validation problem in a few words, and what repairs it.
_PACK_REPAIRS: dict[str, tuple[str, str]] = {
    "lock-extra-files": ("files not in pack.lock.json", "remove the extra files"),
    "lock-missing-files": ("files in pack.lock.json are missing", "restore the missing files"),
    "lock-file-mismatch": ("files differ from pack.lock.json", "restore the locked files"),
    "lock-content-hash": ("files differ from pack.lock.json", "restore the locked files"),
}
_REPORTED_WARNINGS: set[str] = set()


def _short(message: Any) -> str:
    text = " ".join(str(message or "").split())
    return text if len(text) <= 100 else text[:97] + "..."


def pack_warnings(
    diagnostics: Sequence[Mapping[str, Any]],
    settings: PackSettings,
) -> dict[str, str]:
    """One line for each pack the catalog left out: the pack, the reason and the fix.

    Lines are keyed by the pack ID where there is one. Provider selections that
    point at a left-out pack belong to that pack's line; selections that point at
    a pack nobody uses get one line per such pack.
    """

    command = pack_cli_command(settings)
    lines: dict[str, str] = {}

    def disable(pack_id: str) -> str:
        if pack_id in settings.protected_pack_ids:
            return " (it is a bundled pack and stays enabled)"
        return f" or disable it: {command} disable {pack_id}"

    for row in diagnostics:
        code = str(row.get("code") or "")
        pack_id = str(row.get("pack_id") or "")
        folder = Path(str(row.get("root") or pack_id)).name
        label = pack_id if folder == pack_id else folder
        if code == "invalid-enabled-pack":
            details = [item for item in row.get("details") or [] if isinstance(item, Mapping)]
            first = details[0] if details else {}
            first_code = str(first.get("code") or "invalid")
            reason, repair = _PACK_REPAIRS.get(
                first_code,
                (_short(first.get("message")), f"fix it ({command} validate {row.get('root')} names every problem)"),
            )
            lines.setdefault(
                pack_id,
                f"pack {label} is invalid ({first_code}: {reason}); {repair}{disable(pack_id)}",
            )
        elif code == "missing-active-dependency":
            lines.setdefault(
                pack_id,
                f"pack {label} is unusable (it requires pack {row.get('requires')}, which is not in use); "
                f"enable that pack{disable(pack_id)}",
            )
        elif code == "enabled-pack-unavailable":
            lines.setdefault(
                pack_id,
                f"pack {pack_id} is enabled but not found; restore it{disable(pack_id)}",
            )
        elif code == "required-dependency-cycle":
            members = [str(value) for value in row.get("pack_ids") or []]
            lines.setdefault(
                ",".join(members),
                f"packs {', '.join(members)} are unusable (their required dependencies form a cycle); "
                f"disable one of them: {command} disable <pack-id>",
            )
        elif code == "duplicate-pack-id":
            lines.setdefault(
                pack_id,
                f"pack {pack_id} is in more than one pack root, so no copy is used; "
                f"keep one copy ({command} list shows the roots)",
            )
        elif code in {"manifest", "manifest-type", "schema"} and row.get("path"):
            where = Path(str(row["path"])).parent
            reason = _short(str(row.get("message") or "").replace(str(row["path"]), "pack.json"))
            lines.setdefault(
                str(where),
                f"pack at {where} has an invalid pack.json ({code}: {reason}); "
                "fix pack.json or move the directory out of the pack roots",
            )
    covered = {member for key in lines for member in key.split(",")}
    unused: dict[str, list[str]] = {}
    for row in diagnostics:
        if row.get("code") != "resource-provider-unavailable":
            continue
        provider = str(row.get("provider_pack") or "")
        name = str(row.get("resource") or "")
        if provider in covered:
            continue
        if row.get("provider_active"):
            lines[f"{provider}:{name}"] = (
                f"resource {name} points at pack {provider}, which does not provide it; "
                f"clear it: {command} provider-clear {name}"
            )
        else:
            unused.setdefault(provider, []).append(name)
    for provider, names in unused.items():
        shown = ", ".join(names[:3]) + (f" and {len(names) - 3} more" if len(names) > 3 else "")
        lines[provider] = (
            f"{len(names)} resource provider selection(s) ({shown}) point at pack {provider}, "
            f"which is not in use; clear them: {command} disable {provider}"
        )
    return lines


def _print_warnings(lines: Sequence[str]) -> None:
    """Print each warning to standard error once per process."""
    for line in lines:
        if line not in _REPORTED_WARNINGS:
            _REPORTED_WARNINGS.add(line)
            print(f"warning: {line}", file=sys.stderr, flush=True)


def resource_warning(catalog: RuntimePackCatalog, name: str) -> str | None:
    """Why the selected provider of `name` is not in the catalog, or None when nothing failed."""

    for row in catalog.diagnostics:
        if row.get("code") == "resource-provider-unavailable" and row.get("resource") == name:
            provider = str(row.get("provider_pack") or "")
            return next((line for line in catalog.warnings if provider in line), str(row.get("message")))
    return None


def runtime_resource_provider_status(settings: PackSettings) -> dict[str, Any]:
    """List provider intent and eligibility under the exact runtime pack policy."""
    state = load_effective_state(settings)
    _, active_packs, _, validations, diagnostics = _resolve_runtime_pack_inputs(settings)
    providers = state["resource_providers"]
    resolved_resources = _resolve_resources(
        active_packs,
        validations,
        providers,
        diagnostics,
    )
    resolved_records = _remove_broken_record_references(
        _resolve_records(active_packs, diagnostics),
        diagnostics,
    )
    resolved_resources = _apply_contextual_resource_contracts(
        resolved_resources,
        resolved_records,
        diagnostics,
    )
    candidates: dict[str, list[str]] = {}
    for pack, _ in active_packs:
        report = validations[pack.pack_id]
        for name in report.resource_bindings:
            candidates.setdefault(name, []).append(pack.pack_id)
    resolved_names = {name for _, name, _ in resolved_resources}
    names = sorted(set(candidates) | set(providers))
    _print_warnings(list(pack_warnings(diagnostics, settings).values()))
    return {
        "ok": True,
        "resource_providers": [
            {
                "name": name,
                "selected_pack": providers.get(name),
                "candidate_packs": sorted(candidates.get(name, [])),
                "resolved": name in resolved_names,
            }
            for name in names
        ],
        "diagnostics": diagnostics,
    }


def _primary_facet(kind: str, category: str | None) -> str:
    return FACET_BY_CATEGORY.get(str(category or "")) or KIND_PRIMARY_FACET.get(kind) or "subject"


def _record_aliases(record: Mapping[str, Any]) -> list[str]:
    output: list[str] = []
    values: list[Any] = [record.get("label")]
    values.extend(record.get("tags") or [])
    search_profile = record.get("search_profile")
    if isinstance(search_profile, Mapping):
        values.extend(search_profile.get("aliases") or [])
    for value in values:
        normalized = normalize(value)
        if normalized and normalized not in output:
            output.append(normalized)
    return output


def _runtime_profile_is_complete(profile: Mapping[str, Any]) -> bool:
    aliases = {
        normalize(value)
        for value in profile.get("aliases") or []
        if normalize(value)
    }
    return (
        len(aliases) >= 3
        and bool(str(profile.get("outcome_summary") or "").strip())
        and bool(str(profile.get("discovery_group") or "").strip())
        and isinstance(profile.get("facets"), Mapping)
        and bool(profile.get("facets"))
        and isinstance(profile.get("anchor_signature"), Mapping)
    )


def _phrase_rows(
    pack: DiscoveredPack,
    record: PackRecord,
) -> tuple[list[tuple[str, str, str, float, str]], dict[str, Any] | None]:
    value = record.record
    record_id = str(value["id"])
    facet = _primary_facet(record.kind, record.category)
    explicit_rows: list[tuple[str, str, str, float, str]] = []
    explicit_positions: dict[tuple[str, str, str], int] = {}
    explicit_keys: set[tuple[str, str]] = set()
    generated_rows: list[tuple[str, str, str, float, str]] = []
    generated_keys: set[tuple[str, str]] = set()

    def add_explicit(
        raw: Any,
        weight: float,
        source: str,
        row_facet: str | None = None,
    ) -> None:
        phrase = normalize(raw)
        resolved_facet = str(row_facet or facet)
        if phrase:
            semantic_key = (phrase, resolved_facet, source)
            existing_position = explicit_positions.get(semantic_key)
            row = (phrase, record_id, resolved_facet, weight, source)
            if existing_position is None:
                explicit_positions[semantic_key] = len(explicit_rows)
                explicit_rows.append(row)
            elif weight > explicit_rows[existing_position][3]:
                # Canonical normalization can make two authored spellings
                # equivalent (for example, "muscled" and "muscular"). Keep
                # the authoring record intact while emitting one runtime
                # contribution at the strongest authored weight.
                explicit_rows[existing_position] = row
            explicit_keys.add((phrase, resolved_facet))

    def add_generated(raw: Any, weight: float, source: str) -> None:
        phrase = normalize(raw)
        key = (phrase, facet)
        if not phrase or key in explicit_keys or key in generated_keys:
            return
        generated_keys.add(key)
        generated_rows.append((phrase, record_id, facet, weight, source))

    for term in value.get("search_terms") or []:
        if not isinstance(term, Mapping):
            continue
        add_explicit(
            term.get("phrase"),
            float(term.get("weight", 1.0)),
            str(term.get("source") or "pack-search-term"),
            str(term.get("facet") or facet),
        )
    label = value.get("label")
    if label:
        add_generated(label, 1.0, "pack-label")
    for tag in value.get("tags") or []:
        add_generated(tag, 0.9, "pack-tag")
    search_profile = value.get("search_profile")
    if isinstance(search_profile, Mapping):
        for alias in search_profile.get("aliases") or []:
            add_generated(alias, 1.05, "pack-author-alias")
    aliases = _record_aliases(value)
    profile = None
    if isinstance(search_profile, Mapping) and _runtime_profile_is_complete(search_profile):
        profile = dict(search_profile)
        profile.setdefault("kind", record.kind)
        profile.setdefault("category", record.category)
        profile.setdefault("tier", value.get("curation_status") or "vocabulary")
    elif isinstance(search_profile, Mapping) or value.get("curation_status") == "curated":
        profile = build_search_profile(record.kind, record.category, value, aliases)
    if profile is not None:
        profile["source_pack"] = pack.pack_id
    return [*explicit_rows, *generated_rows], profile


def _create_database(
    path: Path,
    settings: PackSettings,
    snapshot: Mapping[str, Any],
    fingerprint: str,
) -> None:
    (
        selected,
        valid_packs,
        pack_reports,
        pack_validations,
        diagnostics,
    ) = _resolve_runtime_pack_inputs(settings)
    resolved_records = _resolve_records(valid_packs, diagnostics)
    resolved_records = _remove_broken_record_references(resolved_records, diagnostics)
    resolved_resources = _resolve_resources(
        valid_packs,
        pack_validations,
        snapshot.get("resource_providers") or {},
        diagnostics,
    )
    resolved_resources = _apply_contextual_resource_contracts(
        resolved_resources,
        resolved_records,
        diagnostics,
    )

    # This database is written once into a new file and read whole. Every query
    # the loader issues returns an entire table in a stated order, so the index
    # each one needs is the one that produces that order and carries the columns
    # it selects. The primary keys do that for packs, records, profiles and
    # resources. phrases is read ordered by four columns and selects five, so
    # phrases_read states all four in order and carries the fifth: the loader
    # scans it as a covering index and sorts nothing. An index on `phrase` alone
    # cannot do either, and no query filters by phrase.
    #
    # Nothing is deleted or updated after the build, so the file has no free
    # pages to reclaim and VACUUM would rewrite it for no gain. A rollback
    # journal rather than WAL, because the build publishes by renaming one file
    # and WAL keeps its content in sidecars that a rename leaves behind. All the
    # inserts are one transaction, so FULL costs one flush and buys a published
    # file that survives a crash.
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.executescript(
            """
            CREATE TABLE meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE packs (
                pack_id TEXT PRIMARY KEY,
                root TEXT NOT NULL,
                manifest_json TEXT NOT NULL,
                validation_json TEXT NOT NULL
            );
            CREATE TABLE records (
                record_id TEXT PRIMARY KEY,
                pack_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                category TEXT,
                source_file TEXT NOT NULL,
                record_json TEXT NOT NULL
            );
            CREATE TABLE phrases (
                phrase TEXT NOT NULL,
                record_id TEXT NOT NULL,
                facet TEXT NOT NULL,
                weight REAL NOT NULL,
                source TEXT NOT NULL,
                row_order INTEGER NOT NULL,
                PRIMARY KEY (record_id, row_order)
            );
            CREATE INDEX phrases_read ON phrases (
                phrase, weight DESC, record_id, row_order, facet, source
            );
            CREATE TABLE profiles (
                record_id TEXT PRIMARY KEY,
                profile_json TEXT NOT NULL
            );
            CREATE TABLE resources (
                name TEXT PRIMARY KEY,
                pack_id TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                absolute_path TEXT NOT NULL,
                media_type TEXT NOT NULL
            );
            """
        )
        active_ids = {pack.pack_id for pack, _ in valid_packs}
        meta = {
            "builder_fingerprint": _builder_fingerprint(),
            "source_fingerprint": str(snapshot.get("fingerprint") or ""),
            "cache_fingerprint": fingerprint,
            "snapshot_json": canonical_json(snapshot),
            "diagnostics_json": canonical_json(diagnostics),
            "active_pack_count": str(len(active_ids)),
        }
        connection.executemany(
            "INSERT INTO meta(key, value) VALUES (?, ?)",
            sorted(meta.items()),
        )
        for pack in selected:
            report = pack_reports.get(pack.pack_id, {})
            connection.execute(
                "INSERT INTO packs(pack_id, root, manifest_json, validation_json) "
                "VALUES (?, ?, ?, ?)",
                (
                    pack.pack_id,
                    str(pack.root),
                    canonical_json(pack.manifest),
                    canonical_json({**report, "active": pack.pack_id in active_ids}),
                ),
            )
        for pack, name, relative in resolved_resources:
            absolute = (pack.root / relative).resolve()
            media_type = mimetypes.guess_type(relative)[0] or "application/octet-stream"
            connection.execute(
                "INSERT INTO resources(name, pack_id, relative_path, "
                "absolute_path, media_type) VALUES (?, ?, ?, ?, ?)",
                (name, pack.pack_id, relative, str(absolute), media_type),
            )
        for pack, record in resolved_records:
            record_id = str(record.record["id"])
            connection.execute(
                "INSERT INTO records(record_id, pack_id, kind, category, "
                "source_file, record_json) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    record_id,
                    pack.pack_id,
                    record.kind,
                    record.category,
                    record.source_file,
                    canonical_json(record.record),
                ),
            )
            phrase_rows, profile = _phrase_rows(pack, record)
            connection.executemany(
                "INSERT INTO phrases(phrase, record_id, facet, weight, source, row_order) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [(*row, index) for index, row in enumerate(phrase_rows)],
            )
            if profile is not None:
                connection.execute(
                    "INSERT INTO profiles(record_id, profile_json) VALUES (?, ?)",
                    (record_id, canonical_json(profile)),
                )
        connection.commit()
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise PackError(f"Pack cache integrity check failed: {integrity}")
    finally:
        connection.close()


def _publish(temporary: Path, output_path: Path) -> None:
    """Put the built database at the name that states what it was built from.

    That name did not exist when the build started, so this is a rename into
    free space and no reader can be holding it. A forced rebuild is the one
    caller that can find it occupied, and on Windows a rename onto an open file
    is refused; that is reported as what it is rather than as a bare permission
    error.
    """

    try:
        os.replace(temporary, output_path)
    except PermissionError as error:
        raise PackError(
            f"{output_path} could not be replaced because another program holds it open. "
            "Close whatever is reading the catalog cache and run the refresh again."
        ) from error


def _build(
    resolved_settings: PackSettings,
    snapshot: Mapping[str, Any],
    fingerprint: str,
    output_path: Path,
    *,
    force: bool = False,
) -> None:
    """Build the cache for `fingerprint` unless another process just did.

    The lock is what keeps two builds of the same inputs from doing the work
    twice, and the existence check inside it is what lets the second one find
    the first one's result. Readers take no part in either.

    A forced build is the one caller that finds the name occupied and must clear
    it. That happens here, under the lock, so a second forced build does not
    remove the file the first one is in the middle of replacing. Windows refuses
    to remove a file another program holds open, and that refusal is reported as
    what it is rather than as a bare permission error.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with _cache_lock(resolved_settings):
        if output_path.is_file():
            if not force:
                return
            try:
                output_path.unlink()
            except OSError as error:
                raise PackError(
                    f"{output_path} could not be rebuilt because another program holds it "
                    "open. Close whatever is reading the catalog cache and run the refresh "
                    "again."
                ) from error
        temporary = output_path.with_name(
            f".{output_path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}"
        )
        try:
            _create_database(temporary, resolved_settings, snapshot, fingerprint)
            _publish(temporary, output_path)
        finally:
            temporary.unlink(missing_ok=True)


def refresh_cache(
    settings: PackSettings | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    resolved_settings = settings or default_settings()
    # Inventory the active inputs once. The same snapshot names the cache and
    # goes into it, so the file a reader opens is the one these inputs produce.
    snapshot = active_snapshot(resolved_settings)
    fingerprint = _expected_fingerprint(snapshot)
    output_path = cache_path(resolved_settings, fingerprint)
    result = {
        "ok": True,
        "enabled": True,
        "fresh": True,
        "rebuilt": False,
        # What discovery was able to enable, and what the built cache kept. The
        # two differ by the packs validation excluded, which the diagnostics
        # name; active_pack_count is the catalog's own count, not discovery's.
        "available_enabled_pack_count": len(
            snapshot.get("available_enabled_packs") or []
        ),
        "active_pack_count": 0,
        "cache_path": str(output_path),
        "fingerprint": fingerprint,
    }
    if output_path.is_file() and not force:
        # Present means built, because the name is the fingerprint and the file
        # arrives under it whole. Nothing is opened and no lock is taken.
        result["active_pack_count"] = _cached_active_pack_count(output_path)
        _discard_superseded(resolved_settings, output_path)
        return result
    _build(resolved_settings, snapshot, fingerprint, output_path, force=force)
    result["active_pack_count"] = _cached_active_pack_count(output_path)
    # Which cache is current is settled on both paths, so the caches that are
    # not go on both. One a reader still holds survives the attempt and is
    # removed by whoever asks next.
    _discard_superseded(resolved_settings, output_path)
    result["rebuilt"] = True
    result["discovery_issues"] = snapshot.get("discovery_issues") or []
    return result


def cache_status(settings: PackSettings | None = None) -> dict[str, Any]:
    resolved_settings = settings or default_settings()
    state = load_effective_state(resolved_settings)
    snapshot = active_snapshot(resolved_settings)
    expected = _expected_fingerprint(snapshot)
    output_path = cache_path(resolved_settings, expected)
    # Freshness is whether the cache these inputs name is present. Nothing is
    # rebuilt and no lock is taken; the meta read only supplies what the cache
    # recorded about itself, and falls back to the newest one when the cache
    # these inputs name is not there to ask.
    present = _existing_caches(resolved_settings)
    fresh = output_path.is_file()
    meta = _read_meta(output_path if fresh else (present[0] if present else output_path))
    diagnostics: list[dict[str, Any]] = []
    raw_diagnostics = meta.get("diagnostics_json")
    if raw_diagnostics:
        try:
            value = json.loads(raw_diagnostics)
            if isinstance(value, list):
                diagnostics = [dict(item) for item in value if isinstance(item, Mapping)]
        except json.JSONDecodeError:
            diagnostics = []
    return {
        "ok": True,
        "enabled": True,
        "fresh": fresh,
        # The catalog's own count, read from the cache meta. When `fresh` is
        # false this comes from the newest cache present rather than from the
        # one these inputs name, exactly as `cached_fingerprint` and
        # `diagnostics` do; read it beside `fresh` before trusting it.
        "active_pack_count": int(meta.get("active_pack_count") or 0),
        "available_enabled_pack_count": len(
            snapshot.get("available_enabled_packs") or []
        ),
        "cache_exists": bool(present),
        "cache_path": str(output_path),
        "expected_fingerprint": expected,
        "cached_fingerprint": meta.get("cache_fingerprint"),
        "enabled_packs": state["enabled_packs"],
        "resource_providers": state["resource_providers"],
        "available_enabled_packs": snapshot.get("available_enabled_packs") or [],
        "discovery_issues": snapshot.get("discovery_issues") or [],
        "diagnostics": diagnostics,
    }


def load_runtime_catalog(
    settings: PackSettings | None = None,
    *,
    quiet: bool = False,
) -> RuntimePackCatalog:
    """Load the catalog of the enabled packs, and warn once about each pack left out.

    Each warning goes to standard error once per process; `quiet` leaves the
    printing to a caller that reports the same lines itself.
    """
    resolved_settings = settings or default_settings()
    # No lock is taken. A published cache is never rewritten, so once this holds
    # a handle nothing can disturb it, and holding it disturbs no build. The one
    # gap is between naming the file and opening it, where a build for other
    # inputs may discard it; a read-only open makes that an error rather than an
    # empty catalog, and the second attempt names the file from inputs read
    # after that discard, so it cannot be the one that was discarded.
    connection: sqlite3.Connection | None = None
    for final_attempt in (False, True):
        path = Path(refresh_cache(resolved_settings)["cache_path"])
        try:
            connection = _connect_readonly(path)
            break
        except sqlite3.Error:
            if final_attempt:
                raise PackError(
                    f"{path} went away while it was being opened, twice over. "
                    "Something outside this runtime is removing the catalog cache."
                ) from None
    if connection is None:  # pragma: no cover - the loop either breaks or raises
        raise PackError("the catalog cache could not be opened")
    try:
        meta = {
            str(key): str(value)
            for key, value in _fetchall(connection, "SELECT key, value FROM meta")
        }
        entries = tuple(
            RuntimePackEntry(
                kind=str(kind),
                category=str(category) if category is not None else None,
                record=json.loads(record_json),
                source_pack=str(pack_id),
                source_root=Path(str(pack_root)),
                source_file=str(source_file),
            )
            for (
                kind,
                category,
                record_json,
                pack_id,
                pack_root,
                source_file,
            ) in _fetchall(
                connection,
                "SELECT records.kind, records.category, records.record_json, "
                "records.pack_id, packs.root, records.source_file "
                "FROM records JOIN packs ON packs.pack_id = records.pack_id "
                "ORDER BY records.record_id",
            )
        )
        phrases: dict[str, list[dict[str, Any]]] = {}
        for phrase, record_id, facet, weight, source in _fetchall(
            connection,
            "SELECT phrase, record_id, facet, weight, source FROM phrases "
            "ORDER BY phrase, weight DESC, record_id, row_order",
        ):
            phrases.setdefault(str(phrase), []).append(
                {
                    "id": str(record_id),
                    "facet": str(facet),
                    "weight": float(weight),
                    "source": str(source),
                }
            )
        profiles = {
            str(record_id): json.loads(profile_json)
            for record_id, profile_json in _fetchall(
                connection,
                "SELECT record_id, profile_json FROM profiles ORDER BY record_id",
            )
        }
        resources = {
            str(name): RuntimePackResource(
                name=str(name),
                path=Path(str(absolute_path)),
                media_type=str(media_type),
                source_pack=str(pack_id),
            )
            for name, absolute_path, media_type, pack_id in _fetchall(
                connection,
                "SELECT name, absolute_path, media_type, pack_id "
                "FROM resources ORDER BY name",
            )
        }
    finally:
        connection.close()
    assets_by_canonical_record_lists: dict[str, list[RuntimePackEntry]] = {
        str(entry.record.get("id")): []
        for entry in entries
        if entry.kind != "asset" and entry.record.get("id")
    }
    for entry in entries:
        if entry.kind != "asset":
            continue
        for canonical_id in entry.record.get("canonical_record_ids") or []:
            key = str(canonical_id)
            if key in assets_by_canonical_record_lists:
                assets_by_canonical_record_lists[key].append(entry)
    assets_by_canonical_record = {
        record_id: tuple(
            sorted(
                linked,
                key=lambda entry: (
                    str(entry.record.get("id") or ""),
                    entry.source_pack,
                    entry.source_file,
                ),
            )
        )
        for record_id, linked in sorted(assets_by_canonical_record_lists.items())
    }
    diagnostics_value = json.loads(meta.get("diagnostics_json") or "[]")
    diagnostics = tuple(
        dict(item) for item in diagnostics_value if isinstance(item, Mapping)
    )
    warnings = tuple(pack_warnings(diagnostics, resolved_settings).values())
    if not quiet:
        _print_warnings(warnings)
    return RuntimePackCatalog(
        fingerprint=meta.get("cache_fingerprint", ""),
        active_pack_count=int(meta.get("active_pack_count") or 0),
        entries=entries,
        phrases=phrases,
        profiles=profiles,
        resources=resources,
        assets_by_canonical_record=assets_by_canonical_record,
        diagnostics=diagnostics,
        warnings=warnings,
    )
