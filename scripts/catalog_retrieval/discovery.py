"""Sparse-brief discovery: lanes, scene compatibility, and recommend."""
from __future__ import annotations

import json
import re
from typing import Any, Mapping, Sequence

from search_discovery import (
    PERMANENT_IDENTITY_FACETS,
    QueryAnalysis,
    SearchIndex,
    analyze_query,
    color_families_in_text,
    extract_record_facets,
)

from catalog_retrieval.core import (
    _domain_compatible,
    _normalized_domains,
    _species_anchor_requests_specific_variant,
    _species_family_value,
    canonical_domain,
    load_json,
    normalize,
    token_set,
)
from catalog_retrieval.queries import ensure_supported_query
from catalog_retrieval.retrieval import (
    _domain_realization_candidates,
    compact_record,
    search_entries,
)
from catalog_retrieval.runtime import Entry, load_search_index, named_resource_path

def load_discovery_lanes() -> list[dict[str, Any]]:
    path = named_resource_path("discovery-lanes")
    assert path is not None
    data = load_json(path)
    return [dict(row) for row in data.get("lanes", []) if isinstance(row, dict)]


def _entry_lookup(entries: Sequence[Entry]) -> dict[str, Entry]:
    return {str(entry.record.get("id") or ""): entry for entry in entries}


def _species_family(term: str) -> str | None:
    return _species_family_value(term)


def _scene_compatible_with_anchors(entry: Entry, analysis: QueryAnalysis) -> bool:
    adaptable = normalize(" ".join(str(value) for value in entry.record.get("adaptable_fields") or []))
    text = normalize(json.dumps({
        "label": entry.record.get("label"),
        "tags": entry.record.get("tags"),
        "defaults": entry.record.get("defaults"),
        "promise": entry.record.get("image_promise"),
        "must_preserve": entry.record.get("must_preserve"),
    }, ensure_ascii=False))

    species = analysis.anchors.get("species") or []
    if species and "species" not in adaptable:
        if not any(normalize(value) in text for value in species):
            generic_species = any(
                phrase in text for phrase in (
                    "anthropomorphic animal", "anthropomorphic character",
                    "canine or feline", "species appropriate", "subject species",
                )
            )
            wanted_families = {_species_family(value) for value in species} - {None}
            family_match = bool(wanted_families and any(family in text for family in wanted_families))
            explicit_species = (
                "wolf", "dog", "fox", "tiger", "lion", "cat", "shark", "bear",
                "stag", "deer", "dragon", "alligator", "crocodile", "horse",
                "rabbit", "hare", "orca", "bird",
            )
            if not generic_species and not family_match and any(
                re.search(rf"\b{word}\b", text) for word in explicit_species
            ):
                return False

    # A scene may fix a subject palette even when the species is compatible.
    # Do not import a black, red, or gray identity scene into an explicit blue
    # coat brief unless the scene declares that coat/palette/markings adapt.
    wanted_coat = analysis.anchors.get("coat_palette") or []
    palette_is_adaptable = any(
        cue in adaptable for cue in ("coat", "palette", "color", "fur", "marking")
    )
    if wanted_coat and not palette_is_adaptable:
        scene_facets = extract_record_facets(entry.kind, entry.category, entry.record)
        candidate_colors: set[str] = set()
        for value in scene_facets.get("coat_palette", []):
            candidate_colors.update(color_families_in_text(value))
        wanted_colors: set[str] = set()
        for value in wanted_coat:
            wanted_colors.update(color_families_in_text(value))
        if wanted_colors and candidate_colors and not (wanted_colors & candidate_colors):
            return False

    # Scene presets are allowed to fill open axes, not replace explicit role,
    # clothing, accessory, environment, pose, gesture, or performance choices.
    # Accept a scene when it already contains the requested wording or clearly
    # declares the relevant field adaptable; otherwise let retrieval find a
    # less prescriptive scene or return no scene at all.
    adaptable_by_facet = {
        "role": ("role", "occupation", "profession", "job", "activity"),
        "wardrobe": ("wardrobe", "outfit", "clothing", "garment", "uniform", "costume"),
        "accessory": ("accessory", "equipment", "headwear", "jewelry", "prop"),
        "environment": ("environment", "setting", "background", "location", "room", "architecture"),
        "pose": ("pose", "action", "stance", "body geometry"),
        "gesture": ("gesture", "hand", "arm", "contact"),
        "performance": ("expression", "gaze", "emotion", "performance", "head turn"),
    }
    for facet, adaptable_cues in adaptable_by_facet.items():
        values = analysis.anchors.get(facet) or []
        if not values:
            continue
        if any(normalize(value) in text for value in values):
            continue
        if any(cue in adaptable for cue in adaptable_cues):
            continue
        return False
    return True


def _scene_matches_lane(entry: Entry, lane: Mapping[str, Any]) -> bool:
    required = [normalize(value) for value in lane.get("scene_required_terms") or [] if normalize(value)]
    if not required:
        return True
    text = normalize(json.dumps({
        "label": entry.record.get("label"),
        "tags": entry.record.get("tags"),
        "promise": entry.record.get("image_promise"),
        "defaults": entry.record.get("defaults"),
        "staging": entry.record.get("staging"),
    }, ensure_ascii=False))
    matches = sum(1 for term in required if term in text)
    return matches >= max(1, int(lane.get("scene_required_min_matches", 1)))


def _anchor_lines(
    analysis: QueryAnalysis,
    facets: set[str] | frozenset[str] | None = None,
) -> list[str]:
    labels = {
        "domain": "domain",
        "species": "species",
        "body_build": "body build",
        "coat_palette": "coat color",
        "eye_feature": "eyes",
        "head_hair": "head hair",
        "hair_style": "hair style",
        "hair_texture": "hair texture",
        "hair_color": "hair color",
        "facial_hair": "facial hair",
        "mane": "mane",
        "ruff": "ruff",
        "head_fur_placement": "head fur placement",
        "head_feature": "head feature",
        "skin_tone": "skin tone",
        "age": "age appearance",
        "presentation": "presentation",
        "role": "role",
        "wardrobe": "wardrobe",
        "accessory": "accessory",
        "gesture": "gesture",
        "pose": "pose or action",
        "performance": "expression or gaze",
        "camera": "camera",
        "composition": "composition",
        "lighting": "lighting",
        "environment": "environment",
        "mood": "mood",
        "style": "style",
    }
    output: list[str] = []
    for facet, values in analysis.anchors.items():
        if not values or (facets is not None and facet not in facets):
            continue
        output.append(f"{labels.get(facet, facet.replace('_', ' '))}: {', '.join(values)}")
    return output


def _permanent_identity_anchor_lines(analysis: QueryAnalysis) -> list[str]:
    """Render only identity facets that may transfer to another scene."""
    return _anchor_lines(analysis, PERMANENT_IDENTITY_FACETS)


def _select_lane_scene(
    entries: Sequence[Entry],
    lane: Mapping[str, Any],
    analysis: QueryAnalysis,
    domain: str | None,
    search_index: SearchIndex,
    used_ids: set[str],
) -> dict[str, Any] | None:
    lookup = _entry_lookup(entries)
    for record_id in lane.get("preferred_scene_ids") or []:
        rid = str(record_id or "")
        entry = lookup.get(rid)
        if not rid or rid in used_ids or entry is None or entry.kind != "scene":
            continue
        if domain and not _domain_compatible(domain, _normalized_domains(entry.record)):
            continue
        if not _scene_compatible_with_anchors(entry, analysis) or not _scene_matches_lane(entry, lane):
            continue
        used_ids.add(rid)
        return compact_record(
            entry,
            "lane-default",
            [],
            [{
                "query_term": lane.get("label"),
                "facet": "scene",
                "source": "discovery-lane-preferred",
            }],
        )

    scene_anchor_facets = (
        "species", "body_build", "proportion", "coat_palette", "age",
        "head_hair", "hair_style", "hair_texture", "hair_color",
        "facial_hair", "mane", "ruff", "head_fur_placement", "head_feature",
        "presentation", "role", "wardrobe", "accessory", "environment",
        "pose", "gesture", "performance",
    )
    anchor_parts: list[str] = []
    for facet in scene_anchor_facets:
        for value in analysis.anchors.get(facet) or []:
            if value not in anchor_parts:
                anchor_parts.append(value)
    probe = " ".join(anchor_parts + [str(lane.get("scene_query") or "")]).strip()
    hits = search_entries(
        entries,
        probe,
        kinds={"scene"},
        categories=set(),
        domain=domain,
        limit=12,
        diverse=True,
        tier="curated",
        group_variants=True,
        search_index=search_index,
    )
    lookup = _entry_lookup(entries)
    for hit in hits:
        rid = str(hit.get("id") or "")
        entry = lookup.get(rid)
        if rid in used_ids or entry is None:
            continue
        if _scene_compatible_with_anchors(entry, analysis) and _scene_matches_lane(entry, lane):
            used_ids.add(rid)
            return hit
    return None


def _lane_score(
    lane: Mapping[str, Any],
    query: str,
    *,
    anchor_terms: Sequence[str] = (),
    situation_terms: Sequence[str] = (),
) -> tuple[int, int]:
    lane_text = " ".join(str(value) for value in (lane.get("label"), lane.get("summary"), lane.get("scene_query"), lane.get("adds"), lane.get("adjustable")))
    lane_tokens = token_set(lane_text)
    weighted = (
        len(token_set(query) & lane_tokens) * 2
        + len(token_set(" ".join(anchor_terms)) & lane_tokens) * 3
        + len(token_set(" ".join(situation_terms)) & lane_tokens)
    )
    return weighted, int(lane.get("priority", 0))


def _explicit_component_hit(
    entries: Sequence[Entry],
    analysis: QueryAnalysis,
    facet: str,
    *,
    kinds: set[str],
    categories: set[str],
    domain: str | None,
    search_index: SearchIndex,
    tier: str = "any",
) -> dict[str, Any] | None:
    values = analysis.anchors.get(facet) or []
    if not values:
        return None
    hits = search_entries(
        entries,
        " ".join(values),
        kinds=kinds,
        categories=categories,
        domain=domain,
        limit=1,
        diverse=False,
        tier=tier,
        group_variants=True,
        search_index=search_index,
    )
    return hits[0] if hits else None


def _dedupe_compact_records(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        record_id = str(row.get("id") or "")
        if record_id and record_id not in seen:
            seen.add(record_id)
            output.append(dict(row))
    return output


def _selected_situation_component(category: str, candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    if not candidates:
        return None
    first = dict(candidates[0])
    relevance = str(first.get("relevance") or "")
    if category == "mood-palette":
        return first if relevance in {"strong", "moderate"} else None
    return first if relevance == "strong" else None


def _compact_component_ids(groups: Mapping[str, Sequence[Mapping[str, Any]]]) -> list[str]:
    output: list[str] = []
    for rows in groups.values():
        for row in rows:
            record_id = str(row.get("id") or "")
            if record_id and record_id not in output:
                output.append(record_id)
    return output


def recommend(
    entries: Sequence[Entry],
    query: str,
    domain: str | None,
    directions: int = 4,
    *,
    analysis: QueryAnalysis | None = None,
    search_index: SearchIndex | None = None,
) -> dict[str, Any]:
    """Create diverse direction cards from a sparse descriptive brief.

    This is exploration, not prompt generation. Explicit anchors remain fixed;
    every card clearly identifies which visual choices the catalog proposes.
    """
    ensure_supported_query(query)
    search_index = search_index or load_search_index()
    analysis = analysis or analyze_query(query, search_index, domain)
    resolved_domain = canonical_domain(domain) if domain else (
        canonical_domain(analysis.domain) if analysis.domain else None
    )

    identity_candidates = search_entries(
        entries,
        query,
        kinds={"archetype"},
        categories=set(),
        domain=resolved_domain,
        limit=6,
        diverse=True,
        tier="any",
        group_variants=True,
        search_index=search_index,
        analysis=analysis,
    )
    identity_modules: dict[str, list[dict[str, Any]]] = {}
    identity_module_queries = {
        "species": ({"species"}, analysis.anchors.get("species") or []),
        "body_build": ({"body-build"}, analysis.anchors.get("body_build") or []),
        "proportion": ({"proportion"}, analysis.anchors.get("proportion") or []),
        "coat_palette": ({"coat-palette"}, analysis.anchors.get("coat_palette") or []),
        "eye_feature": ({"eye-feature"}, analysis.anchors.get("eye_feature") or []),
        "head_hair": ({"head-hair"}, analysis.anchors.get("head_hair") or []),
        "hair_style": ({"hair-style"}, analysis.anchors.get("hair_style") or []),
        "hair_texture": ({"hair-texture"}, analysis.anchors.get("hair_texture") or []),
        "hair_color": ({"hair-color"}, analysis.anchors.get("hair_color") or []),
        "facial_hair": ({"facial-hair"}, analysis.anchors.get("facial_hair") or []),
        "mane": ({"mane"}, analysis.anchors.get("mane") or []),
        "ruff": ({"ruff"}, analysis.anchors.get("ruff") or []),
        "head_fur_placement": ({"head-fur-placement"}, analysis.anchors.get("head_fur_placement") or []),
        "head_feature": ({"head-feature"}, analysis.anchors.get("head_feature") or []),
        "age": ({"age-appearance"}, analysis.anchors.get("age") or []),
        "presentation": ({"gender-presentation"}, analysis.anchors.get("presentation") or []),
        "wardrobe": ({"outfit", "fashion-aesthetic", "footwear"}, analysis.anchors.get("wardrobe") or []),
        "accessory": ({"accessory"}, analysis.anchors.get("accessory") or []),
    }
    for output_key, (categories, values) in identity_module_queries.items():
        if values:
            identity_modules[output_key] = search_entries(entries, " ".join(values), kinds={"module"}, categories=categories, domain=resolved_domain, limit=4, diverse=True, tier="any", group_variants=True, search_index=search_index)

    role_values = analysis.anchors.get("role") or []
    occupation_candidates = search_entries(entries, " ".join(role_values), kinds={"module"}, categories={"occupation"}, domain=resolved_domain, limit=4, diverse=True, tier="any", group_variants=True, search_index=search_index) if role_values else []

    normalized_probe = str(analysis.normalized_query or query)
    situation_candidates = {
        category: search_entries(entries, normalized_probe, kinds={"module"}, categories={category}, domain=resolved_domain, limit=4, diverse=True, tier="any", group_variants=True, search_index=search_index)
        for category in ("mood-palette", "pose-action", "expression", "body-language-cue")
    }
    selected_situation: dict[str, list[dict[str, Any]]] = {}
    situation_alternatives: dict[str, list[dict[str, Any]]] = {}
    for category, candidates in situation_candidates.items():
        selected = _selected_situation_component(category, candidates)
        if selected is not None:
            selected_situation[category] = [selected]
            situation_alternatives[category] = [dict(row) for row in candidates if str(row.get("id")) != str(selected.get("id"))]
        else:
            situation_alternatives[category] = [dict(row) for row in candidates]

    selected_identity_rows: list[dict[str, Any]] = []
    identity_alternatives: dict[str, list[dict[str, Any]]] = {}
    for identity_key, candidates in identity_modules.items():
        if identity_key == "species" and not _species_anchor_requests_specific_variant(analysis.anchors.get("species") or []):
            identity_alternatives[identity_key] = [dict(row) for row in candidates]
            continue
        if candidates:
            selected_identity_rows.append(dict(candidates[0]))
            identity_alternatives[identity_key] = [dict(row) for row in candidates[1:]]

    shared_groups = {
        "identity": _dedupe_compact_records(selected_identity_rows),
        "occupation": _dedupe_compact_records(occupation_candidates[:1]),
        "situation": _dedupe_compact_records([row for rows in selected_situation.values() for row in rows]),
    }
    shared_component_ids = _compact_component_ids(shared_groups)
    shared_requirements = {
        **shared_groups,
        "identity_alternatives": identity_alternatives,
        "occupation_alternatives": [dict(row) for row in occupation_candidates[1:]],
        "situation_alternatives": situation_alternatives,
        "inspection_queue": shared_component_ids,
    }

    domain_realizations = _domain_realization_candidates(entries, query, resolved_domain, 1, analysis=analysis, search_index=search_index) if resolved_domain else []
    domain_realization = domain_realizations[0] if domain_realizations else None
    explicit_style_hit = _explicit_component_hit(entries, analysis, "style", kinds={"style-family"}, categories=set(), domain=resolved_domain, search_index=search_index, tier="curated")
    explicit_camera_hit = _explicit_component_hit(entries, analysis, "camera", kinds={"module"}, categories={"camera"}, domain=resolved_domain, search_index=search_index)
    explicit_lighting_hit = _explicit_component_hit(entries, analysis, "lighting", kinds={"module"}, categories={"lighting"}, domain=resolved_domain, search_index=search_index)

    lanes = [lane for lane in load_discovery_lanes() if not resolved_domain or resolved_domain in set(lane.get("domains") or []) or "shared" in set(lane.get("domains") or [])]
    lane_query = str(analysis.normalized_query or query)
    anchor_terms = [value for values in analysis.anchors.values() for value in values]
    situation_terms: list[str] = []
    for row in shared_groups["situation"]:
        situation_terms.extend(str(value) for value in row.get("tags") or [])
        situation_terms.extend(str(row.get(key) or "") for key in ("label", "prompt", "visual_function"))
    lanes.sort(key=lambda lane: (-_lane_score(lane, lane_query, anchor_terms=anchor_terms, situation_terms=situation_terms)[0], -_lane_score(lane, lane_query, anchor_terms=anchor_terms, situation_terms=situation_terms)[1], str(lane.get("id"))))
    deduped_lanes: list[dict[str, Any]] = []
    seen_lane_families: set[str] = set()
    for lane in lanes:
        lane_family = str(lane.get("style_family_id") or "")
        if lane_family and lane_family in seen_lane_families:
            continue
        if lane_family:
            seen_lane_families.add(lane_family)
        deduped_lanes.append(lane)
        if len(deduped_lanes) >= max(1, directions):
            break
    lanes = deduped_lanes or lanes[:max(1, directions)]

    lookup = _entry_lookup(entries)
    used_scene_ids: set[str] = set()
    cards: list[dict[str, Any]] = []
    preserves = _anchor_lines(analysis)
    identity_preserves = _permanent_identity_anchor_lines(analysis)
    for lane in lanes:
        lane_style_id = str(lane.get("style_family_id") or "")
        style_id = str((explicit_style_hit or {}).get("id") or lane_style_id)
        style_entry = lookup.get(style_id)
        style_hit = explicit_style_hit
        if style_hit is None and style_entry is not None:
            style_hit = compact_record(
                style_entry,
                "lane-default",
                [],
                [{"query_term": lane.get("label"), "facet": "style", "source": "discovery-lane"}],
            )
        scene_hit = _select_lane_scene(entries, lane, analysis, resolved_domain, search_index, used_scene_ids)

        def lane_module_hit(record_id: Any, category: str, fallback_query: str) -> dict[str, Any] | None:
            preferred = lookup.get(str(record_id or ""))
            if preferred is not None and preferred.kind == "module" and preferred.category == category:
                return compact_record(
                    preferred,
                    "lane-default",
                    [],
                    [{
                        "query_term": lane.get("label"),
                        "facet": category,
                        "source": "discovery-lane",
                    }],
                )
            hits = search_entries(
                entries,
                fallback_query,
                kinds={"module"},
                categories={category},
                domain=resolved_domain,
                limit=1,
                diverse=False,
                tier="any",
                group_variants=True,
                search_index=search_index,
            )
            return hits[0] if hits else None

        camera_hit = explicit_camera_hit or lane_module_hit(
            lane.get("camera_id"), "camera",
            str(lane.get("camera_query") or lane.get("label") or "camera"),
        )
        lighting_hit = explicit_lighting_hit or lane_module_hit(
            lane.get("lighting_id"), "lighting",
            str(lane.get("lighting_query") or lane.get("label") or "lighting"),
        )

        selected_labels = []
        for hit in (scene_hit, style_hit, camera_hit, lighting_hit, domain_realization):
            if hit and hit.get("label"):
                selected_labels.append(str(hit["label"]))
        adds = list(lane.get("adds") or [])
        for label in selected_labels:
            if label not in adds:
                adds.append(label)

        what_you_get = str(lane.get("summary") or "").strip()
        if scene_hit and scene_hit.get("outcome_summary"):
            scene_summary = str(scene_hit["outcome_summary"]).strip()
            if scene_summary and scene_summary not in what_you_get:
                what_you_get += " Catalog staging option: " + scene_summary

        fixed_overrides: list[str] = []
        if explicit_style_hit:
            fixed_overrides.append(
                f"style fixed by brief: {explicit_style_hit.get('label')}"
            )
        if explicit_camera_hit:
            fixed_overrides.append(
                f"camera fixed by brief: {explicit_camera_hit.get('label')}"
            )
        if explicit_lighting_hit:
            fixed_overrides.append(
                f"lighting fixed by brief: {explicit_lighting_hit.get('label')}"
            )
        if fixed_overrides:
            what_you_get += " Explicit brief choices replace the lane defaults for: " + "; ".join(fixed_overrides) + "."

        preset_ids = {
            "style_family": style_id or None,
            "scene": scene_hit.get("id") if scene_hit else None,
            "camera": camera_hit.get("id") if camera_hit else None,
            "lighting": lighting_hit.get("id") if lighting_hit else None,
            "domain_realization": domain_realization.get("id") if domain_realization else None,
        }
        preset_ids = {key: value for key, value in preset_ids.items() if value}
        why_parts = [
            ("preserves normalized brief anchors: " + "; ".join(preserves) if preserves else "no normalized brief anchors were detected; lane defaults fill open visual axes"),
            f"uses the {lane.get('label')} lane to fill still-open visual axes",
        ]
        if scene_hit:
            why_parts.append("selects a scene compatible with the subject domain and explicit scene-facing anchors")
        if fixed_overrides:
            why_parts.append("uses explicit style, camera, or lighting matches instead of conflicting lane defaults")
        cards.append({
            "id": lane.get("id"),
            "title": lane.get("label"),
            "what_you_get": what_you_get,
            "why_it_fits": "; ".join(why_parts) + ".",
            "preserves": preserves,
            "permanent_identity_preserves": identity_preserves,
            "scene_specific_character_state": {
                "concept": "scene-specific character state",
                "classification": "open-class",
                "handling": (
                    "Rebuild every changeable character-state detail for the current "
                    "scene. Do not inherit such state from an identity reference."
                ),
            },
            "terms_without_alias": list(analysis.terms_without_alias),
            "adds": adds,
            "adjustable": list(lane.get("adjustable") or []),
            "fixed_component_overrides": fixed_overrides,
            "preset_ids": preset_ids,
            "shared_component_ids": shared_component_ids,
            "direction_specific_components": list(preset_ids.values()),
            "inspection_queue": list(dict.fromkeys([*shared_component_ids, *preset_ids.values()])),
            "open_axes_after_card": [
                axis for axis in analysis.open_axes
                if axis not in {"scene", "camera", "lighting", "style"}
            ],
        })

    return {
        "mode": "sparse-brief-discovery",
        "query_analysis": analysis.to_dict(),
        "identity_candidates": identity_candidates,
        "identity_modules": identity_modules,
        "shared_requirements": shared_requirements,
        "domain_realizations": domain_realizations,
        "direction_cards": cards,
        "terms_without_alias": list(analysis.terms_without_alias),
        "note": (
            "Preset names and IDs are not required input. Shared identity, occupation, and situation "
            "requirements are inspected once and carried into every direction card; cards vary only "
            "the open visual direction. Inspect every selected canonical record before prompt "
            "construction. Any terms_without_alias are retained for semantic review rather than silently dropped."
        ),
    }
