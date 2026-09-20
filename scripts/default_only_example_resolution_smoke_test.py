#!/usr/bin/env python3
"""Prove runnable core examples resolve canonical selections from packs/commons alone."""
from __future__ import annotations

import copy
import importlib.util
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from pack_manager import validate_pack
from state_protocol import artifact_hash, validate_artifact


ROOT = Path(__file__).resolve().parents[1]
ZERO_SHA256 = "0" * 64
EXPECTED_PILOT_SELECTION = (
    "style-family-clear-portrait",
    "domain-realization-anthropomorphic-animal-baseline",
    "profile-clear-2d-illustration",
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _add(
    references: dict[str, set[str]],
    value: Any,
    source: str,
) -> None:
    if isinstance(value, str) and value:
        references[value].add(source)


def _collect_catalog_selections(
    value: Any,
    source: str,
    references: dict[str, set[str]],
) -> None:
    """Collect only fields whose contract explicitly identifies catalog records."""

    if isinstance(value, list):
        for item in value:
            _collect_catalog_selections(item, source, references)
        return
    if not isinstance(value, dict):
        return
    for key, item in value.items():
        if key in {"selected_preset_ids", "canonical_record_ids", "canonical_record_refs"}:
            if isinstance(item, list):
                for record_id in item:
                    _add(references, record_id, f"{source}:{key}")
            continue
        if key == "style_family_id":
            _add(references, item, f"{source}:{key}")
            continue
        if key in {"visual_language", "creative_intent"} and isinstance(item, dict):
            for scalar_key in ("aesthetic_core", "style_family", "render_profile"):
                _add(
                    references,
                    item.get(scalar_key),
                    f"{source}:{key}.{scalar_key}",
                )
            realizations = item.get("domain_realizations")
            if isinstance(realizations, dict):
                for domain, record_id in realizations.items():
                    _add(
                        references,
                        record_id,
                        f"{source}:{key}.domain_realizations.{domain}",
                    )
            touches = item.get("aesthetic_touches")
            if isinstance(touches, list):
                for record_id in touches:
                    _add(
                        references,
                        record_id,
                        f"{source}:{key}.aesthetic_touches",
                    )
        _collect_catalog_selections(item, source, references)


def _load_builder_ids(root: Path) -> tuple[str, ...]:
    builder_path = root / "examples" / "state-aware-pilot" / "build_example.py"
    spec = importlib.util.spec_from_file_location("cpb_state_aware_pilot_builder", builder_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"could not load pilot builder: {builder_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    value = getattr(module, "DEFAULT_ONLY_CANONICAL_RECORD_IDS", None)
    if not isinstance(value, tuple) or not value:
        raise ValueError("pilot builder omitted DEFAULT_ONLY_CANONICAL_RECORD_IDS")
    if any(not isinstance(item, str) or not item for item in value):
        raise ValueError("pilot builder default-only record IDs must be non-empty strings")
    return value


def evaluate(root: Path = ROOT) -> dict[str, Any]:
    root = Path(root).resolve()
    errors: list[str] = []
    references: dict[str, set[str]] = defaultdict(set)

    default_pack = root / "packs" / "commons"
    validation = validate_pack(default_pack, require_lock=True)
    if not validation.valid:
        errors.extend(
            f"default pack: {issue.message}"
            for issue in validation.issues
            if issue.severity == "error"
        )
    default_record_ids = {
        str(record.record.get("id"))
        for record in validation.records
        if record.record.get("id")
    }
    default_records = {
        str(record.record.get("id")): record
        for record in validation.records
        if record.record.get("id")
    }

    for relative in ("render-spec-request.json",):
        path = root / "examples" / "state-aware-pilot" / relative
        _collect_catalog_selections(
            _load_json(path),
            path.relative_to(root).as_posix(),
            references,
        )
    generated = root / "examples" / "state-aware-pilot" / "generated"
    for path in sorted(generated.rglob("*.json")):
        _collect_catalog_selections(
            _load_json(path),
            path.relative_to(root).as_posix(),
            references,
        )
    for path in sorted((root / "templates" / "state").glob("*.json")):
        data = _load_json(path)
        refs = data.get("canonical_record_refs") if isinstance(data, dict) else None
        if isinstance(refs, list):
            for record_id in refs:
                _add(
                    references,
                    record_id,
                    f"{path.relative_to(root).as_posix()}:canonical_record_refs",
                )

    try:
        builder_ids = _load_builder_ids(root)
    except Exception as exc:  # noqa: BLE001
        builder_ids = ()
        errors.append(str(exc))
    for record_id in builder_ids:
        _add(
            references,
            record_id,
            "examples/state-aware-pilot/build_example.py:DEFAULT_ONLY_CANONICAL_RECORD_IDS",
        )

    missing = sorted(set(references) - default_record_ids)
    if missing:
        errors.append(
            "runnable core example selections are absent from packs/commons: "
            + ", ".join(missing)
        )

    field_role_contract = {
        "style-family-clear-portrait": (
            "style-family",
            "concrete-style-family",
            None,
        ),
        "domain-realization-anthropomorphic-animal-baseline": (
            "domain-realization",
            None,
            "anthropomorphic-animal",
        ),
        "profile-clear-2d-illustration": ("profile", None, None),
    }
    observed_role_contract: dict[str, dict[str, Any]] = {}
    for record_id, (expected_kind, expected_category, expected_domain) in (
        field_role_contract.items()
    ):
        record = default_records.get(record_id)
        if record is None:
            continue
        observed_role_contract[record_id] = {
            "kind": record.kind,
            "category": record.category,
            "subject_domain": record.record.get("subject_domain"),
        }
        if record.kind != expected_kind:
            errors.append(
                f"{record_id} has kind {record.kind!r}, expected {expected_kind!r}"
            )
        if expected_category is not None and record.category != expected_category:
            errors.append(
                f"{record_id} has category {record.category!r}, "
                f"expected {expected_category!r}"
            )
        if (
            expected_domain is not None
            and record.record.get("subject_domain") != expected_domain
        ):
            errors.append(
                f"{record_id} has subject_domain "
                f"{record.record.get('subject_domain')!r}, expected {expected_domain!r}"
            )

    expected_field_kind = {
        "style_family_id": "style-family",
        ".style_family": "style-family",
        ".render_profile": "profile",
        ".domain_realizations.": "domain-realization",
    }
    for record_id, sources in references.items():
        record = default_records.get(record_id)
        if record is None:
            continue
        for source in sources:
            for marker, expected_kind in expected_field_kind.items():
                if marker in source and record.kind != expected_kind:
                    errors.append(
                        f"{source} contains {record_id!r} of kind {record.kind!r}; "
                        f"the field requires {expected_kind!r}"
                    )

    request = _load_json(
        root / "examples" / "state-aware-pilot" / "render-spec-request.json"
    )
    production = _load_json(
        root
        / "examples"
        / "state-aware-pilot"
        / "generated"
        / "production-specification.json"
    )
    intent = _load_json(
        root
        / "examples"
        / "state-aware-pilot"
        / "generated"
        / "creative-intent.json"
    )
    visual_language = production.get("visual_language") or {}
    if builder_ids != EXPECTED_PILOT_SELECTION:
        errors.append(
            "pilot builder default-only selection differs from its typed role contract: "
            f"{list(builder_ids)}"
        )
    if request.get("selected_preset_ids") != list(EXPECTED_PILOT_SELECTION):
        errors.append("pilot render request selection differs from the builder role contract")
    if production.get("selected_preset_ids") != list(EXPECTED_PILOT_SELECTION):
        errors.append("pilot production selection differs from the builder role contract")
    if visual_language.get("aesthetic_core", "missing") is not None:
        errors.append("pilot must represent an unselected optional aesthetic core as null")
    if visual_language.get("aesthetic_touches") != []:
        errors.append("pilot must not place non-touch modules in aesthetic_touches")
    if visual_language.get("style_family") != EXPECTED_PILOT_SELECTION[0]:
        errors.append("pilot style_family is not the selected style-family record")
    if visual_language.get("domain_realizations") != {
        "anthropomorphic-animal": EXPECTED_PILOT_SELECTION[1]
    }:
        errors.append("pilot domain_realizations does not contain the typed domain record")
    if visual_language.get("render_profile") != EXPECTED_PILOT_SELECTION[2]:
        errors.append("pilot render_profile is not the selected profile record")
    if intent.get("aesthetic_core", "missing") is not None:
        errors.append("pilot creative intent must represent no aesthetic core as null")

    neutral_template_contract: dict[str, dict[str, Any]] = {}
    neutral_templates: dict[str, dict[str, Any]] = {}
    for name, self_hash_field in (
        ("semantic-region-map.template.json", "semantic_region_map_sha256"),
        ("visual-authority.template.json", "visual_authority_sha256"),
        ("visual-evidence-bundle.template.json", "visual_evidence_bundle_sha256"),
    ):
        value = _load_json(root / "templates" / "state" / name)
        neutral_templates[name] = value
        validation_report = validate_artifact(value, allow_placeholder_hashes=True)
        neutral_template_contract[name] = {
            "canonical_record_refs": value.get("canonical_record_refs"),
            "source_sha256": value.get("source_sha256"),
            "self_sha256": value.get(self_hash_field),
            "validation_ok": validation_report.get("ok"),
        }
        if not validation_report.get("ok"):
            errors.append(
                f"neutral core template is structurally invalid: {name}: "
                + "; ".join(str(item) for item in validation_report.get("errors", []))
            )
        if value.get("canonical_record_refs") != []:
            errors.append(f"neutral core template must start with no record binding: {name}")
        if value.get("source_sha256") != ZERO_SHA256:
            errors.append(f"neutral core template contains an authoritative source hash: {name}")
        self_hash = value.get(self_hash_field)
        if self_hash == ZERO_SHA256 or self_hash != artifact_hash(value):
            errors.append(
                f"neutral core template self hash is not formally sealed: {name}"
            )
        notes = value.get("notes")
        if not isinstance(notes, list) or "no authority" not in " ".join(
            str(item).lower() for item in notes
        ):
            errors.append(f"neutral core template omits its no-authority warning: {name}")

    visual_authority = neutral_templates["visual-authority.template.json"]
    if visual_authority.get("mode") != "text-only":
        errors.append("neutral visual-authority template must use text-only mode")
    if visual_authority.get("archival_vector") is not None:
        errors.append("text-only visual-authority template must not assert an archival vector")
    invalid_source_derived = copy.deepcopy(visual_authority)
    invalid_source_derived["mode"] = "source-derived"
    invalid_source_report = validate_artifact(
        invalid_source_derived,
        allow_placeholder_hashes=True,
    )
    if invalid_source_report.get("ok") or not any(
        "requires archival_vector" in str(item)
        for item in invalid_source_report.get("errors", [])
    ):
        errors.append(
            "visual-authority validation did not reject source-derived mode without "
            "an archival vector"
        )

    evidence_bundle = neutral_templates["visual-evidence-bundle.template.json"]
    expected_authority_ref = {
        "id": visual_authority.get("authority_id"),
        "sha256": visual_authority.get("visual_authority_sha256"),
    }
    if evidence_bundle.get("visual_authority_ref") != expected_authority_ref:
        errors.append(
            "neutral visual-evidence bundle does not link to the sealed neutral "
            "visual-authority artifact"
        )
    for index, artifact in enumerate(evidence_bundle.get("artifacts", [])):
        if not isinstance(artifact, dict) or artifact.get("sha256") != ZERO_SHA256:
            errors.append(
                "neutral visual-evidence bundle contains a non-placeholder derivative "
                f"hash at artifacts[{index}]"
            )

    return {
        "ok": not errors,
        "default_pack": default_pack.relative_to(root).as_posix(),
        "default_record_count": len(default_record_ids),
        "resolved_record_ids": sorted(references),
        "reference_sources": {
            record_id: sorted(sources) for record_id, sources in sorted(references.items())
        },
        "missing_record_ids": missing,
        "field_role_contract": observed_role_contract,
        "neutral_template_contract": neutral_template_contract,
        "errors": errors,
    }


def main() -> int:
    report = evaluate(ROOT)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
