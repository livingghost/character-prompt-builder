#!/usr/bin/env python3
"""Focused contract tests for the pack release gate."""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock


sys.dont_write_bytecode = True

import style_family_audit
from audit_preset_quality import (
    Record,
    check_aesthetic_core,
    check_archetype,
    check_correction,
    check_distinctive_detail,
    check_domain_realization,
    check_positive_text_quality,
    check_recipes,
    check_scene,
    check_style_family,
)
from pack_manager import initialize_pack, validate_pack, write_lock
from pack_release_gate import (
    _corpus_suite,
    _style_suite,
    authored_metrics,
    run_release_gate,
    validate_release_contract,
)


ROOT = Path(__file__).resolve().parents[1]
MINIMAL_PACK = ROOT / "examples" / "pack-authoring" / "minimal-pack"
DEFAULT_PACK = ROOT / "packs" / "commons"


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _manifest(pack: Path) -> dict[str, Any]:
    return json.loads((pack / "pack.json").read_text(encoding="utf-8"))


def _bind(pack: Path, name: str, relative: str) -> None:
    manifest = _manifest(pack)
    manifest["content"]["resource_globs"] = ["resources/**/*"]
    manifest["content"]["resource_bindings"][name] = relative
    _write_json(pack / "pack.json", manifest)


def _state(path: Path, pack: Path, *, extra_root: Path | None = None) -> None:
    manifest = _manifest(pack)
    roots = [str(pack.resolve())]
    if extra_root is not None:
        roots.append(str(extra_root.resolve()))
    _write_json(
        path,
        {
            "pack_roots": roots,
            "enabled_packs": [manifest["pack_id"]],
        },
    )


def _runtime_paths(root: Path, label: str) -> tuple[Path, Path, Path]:
    runtime = root / f"runtime-{label}"
    managed = runtime / "managed"
    managed.mkdir(parents=True)
    return runtime / "state.json", runtime / "cache", managed


def _copy_pack(root: Path, label: str) -> Path:
    target = root / label
    shutil.copytree(MINIMAL_PACK, target)
    write_lock(target)
    return target


_AUTHORED_CLAUSES = (
    "establishes a deliberate visual hierarchy with stable relationships and a clearly readable focal order",
    "keeps the governing proportions observable while controlled variations change secondary presentation choices",
    "coordinates shape rhythm value grouping and material response so the intended construction remains legible",
    "preserves identity-bearing decisions independently from camera lighting environment wardrobe and transient performance",
    "states how artists should translate the design without replacing its defining structure with generic shorthand",
    "uses explicit local comparisons and visible landmarks so review can distinguish compliance from a nearby interpretation",
    "maintains coherent emphasis across the complete image while allowing declared adaptation axes to remain genuinely flexible",
    "connects silhouette interior structure surface treatment and detail priority into one reproducible production direction",
    "defines observable success conditions that remain useful when the subject domain or scene context changes",
    "retains the authored promise through final rendering by protecting the strongest relationships before decorative detail",
)


def _authored_text(topic: str, minimum_words: int) -> str:
    sentences: list[str] = []
    for clause in _AUTHORED_CLAUSES:
        sentences.append(f"{topic.capitalize()} {clause}.")
        if len(" ".join(sentences).split()) >= minimum_words:
            break
    text = " ".join(sentences)
    if len(text.split()) < minimum_words:
        raise AssertionError(
            f"synthetic authored text for {topic!r} cannot reach {minimum_words} words"
        )
    return text


def _curated_record(kind: str, record_id: str, **values: Any) -> Record:
    payload = {
        "id": record_id,
        "curation_status": "curated",
        "record_role": "authored-production-direction",
        **values,
    }
    return Record(
        kind=kind,
        category=str(payload.get("category") or ""),
        record=payload,
        source=f"synthetic:{record_id}",
    )


def _aesthetic_core_fixture() -> Record:
    authored_fields = (
        "aesthetic_promise",
        "appeal_center",
        "silhouette_and_proportion_strategy",
        "performance_and_expression_strategy",
        "viewer_relationship_strategy",
        "composition_and_focal_strategy",
        "shape_and_rhythm_strategy",
        "surface_and_tactility_strategy",
        "color_and_light_strategy",
        "finish_and_detail_hierarchy",
        "domain_neutrality",
    )
    values = {
        field: _authored_text(field.replace("_", " "), 24)
        for field in authored_fields
    }
    return _curated_record(
        "aesthetic-core",
        "synthetic-aesthetic-core",
        label="Synthetic coherent presence",
        domains=["shared"],
        compatible_medium_families=["illustration"],
        integration_prompt=_authored_text("aesthetic integration", 105),
        variation_axes=[
            "focal intimacy",
            "shape tension",
            "value compression",
            "finish density",
        ],
        best_for=["character portraits", "ensemble key art", "narrative studies"],
        avoid_for=["pure technical diagrams", "unreviewed style imitation"],
        tags=["coherent-presence", "shared-direction"],
        **values,
    )


def _style_system(name: str) -> dict[str, str]:
    return {
        "primary": _authored_text(f"{name} primary structure", 16),
        "secondary": _authored_text(f"{name} secondary structure", 16),
        "control": _authored_text(f"{name} production control", 16),
    }


def _style_family_fixture() -> Record:
    overlay_fields = (
        "identity_and_form",
        "surface_translation",
        "performance_translation",
        "detail_priority",
        "integration",
    )
    overlays = {
        domain: {
            field: _authored_text(
                f"{domain} {field.replace('_', ' ')}",
                10,
            )
            for field in overlay_fields
        }
        for domain in (
            "human",
            "anthropomorphic-animal",
            "animal",
            "creature",
            "hybrid",
            "robot",
        )
    }
    return _curated_record(
        "style-family",
        "synthetic-style-family",
        label="Synthetic structured illustration family",
        domains=["shared"],
        medium_family="illustration",
        base_render_profile_id="synthetic-render-profile",
        compatible_render_profile_ids=["synthetic-render-profile"],
        style_promise=_authored_text("style promise", 24),
        visual_signature=_authored_text("visual signature", 24),
        line_system=_style_system("line"),
        form_system=_style_system("form"),
        value_and_shadow_system=_style_system("value and shadow"),
        highlight_system=_style_system("highlight"),
        color_system=_style_system("color"),
        surface_system=_style_system("surface"),
        background_system=_style_system("background"),
        detail_hierarchy=_authored_text("detail hierarchy", 24),
        touch_policy=_authored_text("touch policy", 24),
        style_reference_guidance=_authored_text("style reference guidance", 24),
        domain_overlays=overlays,
        integration_prompt=_authored_text("style family integration", 120),
        negative_policy=_authored_text("scoped style exclusions", 24),
        negative_terms=["unstructured detail", "accidental material noise"],
        variation_axes=[
            "line density",
            "shadow compression",
            "color restraint",
            "background abstraction",
        ],
        best_for=["character sheets", "narrative portraits", "ensemble art"],
        avoid_for=["unreviewed photorealism", "pure wireframe diagrams"],
        tags=["structured-illustration", "cross-domain"],
    )


def _domain_realization_fixture() -> Record:
    authored_fields = (
        "realization_promise",
        "identity_and_silhouette",
        "performance_channels",
        "anatomy_and_weight",
        "surface_and_materials",
        "viewer_relationship",
        "motion_and_environment",
    )
    values = {
        field: _authored_text(field.replace("_", " "), 24)
        for field in authored_fields
    }
    translation_rules = {
        field: _authored_text(f"translation rule {field.replace('_', ' ')}", 14)
        for field in (
            "appeal_center",
            "shape_and_rhythm",
            "performance",
            "surface",
            "color_and_light",
            "detail_hierarchy",
        )
    }
    return _curated_record(
        "domain-realization",
        "synthetic-domain-realization",
        label="Synthetic human domain realization",
        domains=["human"],
        subject_domain="human",
        realization_level="foundation",
        base_realization=True,
        translation_rules=translation_rules,
        integration_prompt=_authored_text("domain realization integration", 105),
        extension_points=["age", "build", "grooming"],
        best_for=["portraits", "full figures", "character interactions"],
        avoid_for=["ordinary animal anatomy", "mechanical chassis studies"],
        tags=["human", "foundation-realization"],
        **values,
    )


def _distinctive_detail_fixture() -> Record:
    return _curated_record(
        "module",
        "synthetic-distinctive-detail",
        category="distinctive-detail",
        label="Small left brow interruption",
        visual_function=_authored_text("distinctive detail function", 12),
        prompt=_authored_text("distinctive detail construction", 30),
        invariants=[
            "the interruption stays above the left pupil",
            "its width remains subordinate to the brow arc",
            "its shallow relief follows the surrounding plane",
        ],
        misreadings_to_avoid=[
            "a deep vertical scar",
            "a centered forehead mark",
            "a painted cosmetic stripe",
        ],
        applies_to="permanent facial identity",
        tags=["brow-landmark", "identity-detail"],
        domains=["human"],
        feature_type="shallow healed interruption",
        target_region="left lateral brow",
        laterality="left",
        landmark_relation=_authored_text("landmark relation", 8),
        count_or_distribution="one isolated interruption",
        relative_size=_authored_text("relative size against the brow arc", 7),
        shape_and_path="short tapered diagonal path",
        orientation="slightly descending toward the temple",
        color_and_value="one restrained step lighter than the adjacent brow",
        depth_and_relief="shallow relief without a recessed wound channel",
        edge_and_texture="soft healed edges with uninterrupted surrounding texture",
        surface_interaction=_authored_text("surface interaction", 9),
        age_or_condition="fully healed and stable",
        visibility_and_occlusion=_authored_text("visibility and occlusion", 9),
        identity_priority="signature",
        adaptation_limits=[
            "retain the left-side landmark relationship",
            "do not enlarge it into a dominant injury",
        ],
    )


def _scene_fixture() -> Record:
    staging = {
        field: _authored_text(f"scene staging {field.replace('_', ' ')}", 16)
        for field in (
            "body_geometry",
            "action_geometry",
            "gaze_and_expression",
            "prop_or_contact_geometry",
            "focal_hierarchy",
            "depth_order",
        )
    }
    defaults = {
        "subject": "one clearly identified recurring character",
        "body": "balanced full upper-body construction",
        "pose": "stable three-quarter working pose",
        "expression": "focused calm attention",
        "composition": "single readable focal triangle",
        "camera": "eye-level medium portrait",
        "lighting": "soft directional studio light",
        "environment": "quiet adaptable workspace",
        "mood": "concentrated and assured",
        "constraints": ["preserve identity", "retain contact geometry"],
    }
    return _curated_record(
        "scene",
        "synthetic-scene",
        label="Synthetic careful handoff",
        image_promise=_authored_text("scene image promise", 20),
        staging=staging,
        defaults=defaults,
        must_preserve=[
            "the receiving hand remains below the offered object",
            "the gaze follows the exchange rather than the viewer",
            "the object remains the secondary focal point",
            "the two body silhouettes remain separately readable",
        ],
        adaptable_fields=["wardrobe", "workspace", "time of day", "object design"],
        failure_modes=[
            "hands merge around the object",
            "both subjects stare at the viewer",
            "the object blocks the primary face",
            "depth ordering reverses the intended exchange",
        ],
        aspect_ratio="4:5",
        domain="human",
    )


def _profile_for_recipe() -> Record:
    grammar_fields = (
        "medium_family",
        "visual_intent",
        "linework",
        "shape_language",
        "value_structure",
        "color_logic",
        "surface_policy",
        "lighting_response",
        "background_policy",
        "detail_hierarchy",
    )
    values = {
        field: (
            "illustration"
            if field == "medium_family"
            else _authored_text(f"profile {field.replace('_', ' ')}", 12)
        )
        for field in grammar_fields
    }
    return _curated_record(
        "profile",
        "synthetic-render-profile",
        label="Synthetic render profile",
        **values,
    )


def _recipe_fixture(scene: Record, profile: Record) -> Record:
    grammar_fields = (
        "medium_family",
        "visual_intent",
        "linework",
        "shape_language",
        "value_structure",
        "color_logic",
        "surface_policy",
        "lighting_response",
        "background_policy",
        "detail_hierarchy",
    )
    staging = copy.deepcopy(scene.record["staging"])
    prompt_template = " ".join(staging.values())
    prompt_template += " " + _authored_text("finished recipe assembly", 120)
    prompt_template += " " + _authored_text("finished recipe continuity review", 60)
    return _curated_record(
        "recipe",
        "synthetic-recipe",
        label="Synthetic careful handoff recipe",
        base_scene_id=scene.record["id"],
        render_profile_id=profile.record["id"],
        image_promise=_authored_text("finished recipe image promise", 24),
        scene_blueprint={
            "staging": staging,
            "must_preserve": copy.deepcopy(scene.record["must_preserve"]),
        },
        rendering_grammar={field: profile.record.get(field) for field in grammar_fields},
        prompt_template=prompt_template,
        adaptation_rules=[
            "change setting without changing the exchange geometry",
            "change wardrobe without hiding the receiving hand",
            "change object design while retaining its focal role",
            "change lighting while preserving gaze direction",
        ],
        must_preserve=copy.deepcopy(scene.record["must_preserve"]),
        negative_terms=["merged hands", "viewer-facing gaze"],
        input_slots=["subject one", "subject two", "exchange object"],
    )


def _archetype_policy_fixture() -> dict[str, Any]:
    return {
        "curated_archetype_scope": "recurring-character-identity",
        "creation_basis_values": ["curated-design"],
        "required_identity_axes": [
            "subject_domain",
            "morphology",
            "proportions",
            "surface_palette_markings",
            "distinctive_details",
        ],
        "creation_gate": {"minimum_stable_axes": 5},
    }


def _archetype_fixture() -> Record:
    return _curated_record(
        "archetype",
        "synthetic-archetype",
        label="Synthetic recurring cartographer",
        archetype_scope="recurring-character-identity",
        creation_basis="curated-design",
        evidence_scope=_authored_text("reusable identity evidence", 14),
        identity_axes={
            "subject_domain": "human",
            "morphology": "compact upright adult build",
            "proportions": "long forearms and narrow shoulders",
            "surface_palette_markings": "warm umber complexion with one pale brow mark",
            "distinctive_details": "small left brow interruption and squared ear cuff",
        },
        identity_invariants=[
            "retain the compact build",
            "retain the long forearm proportion",
            "retain the left brow landmark",
            "retain the squared ear cuff geometry",
        ],
        variable_fields=["wardrobe", "pose", "expression", "environment"],
        identity_construction=_authored_text("identity construction", 24),
        character_lock=_authored_text("permanent character identity lock", 45),
        defaults={
            "morphology": "compact upright adult human build",
            "grooming": "short practical side-part",
        },
        constraints=["keep permanent traits independent from scene presentation"],
        do_not_lock=["pose", "gaze", "wardrobe", "weather"],
        domain="human",
    )


def _correction_fixture() -> Record:
    return _curated_record(
        "correction",
        "synthetic-correction",
        label="Restore readable object handoff",
        trigger="the exchange object merges with both hands",
        diagnosis="contact planes and depth order have collapsed into one silhouette",
        positive_correction=_authored_text("positive handoff repair", 32),
        inspection_points=[
            "receiving palm remains below the object",
            "offering fingers remain separately visible",
            "object contour remains continuous between the hands",
        ],
        avoidance_terms=["merged hands", "floating exchange object"],
        tags=["contact-geometry", "handoff-repair"],
    )


def _style_boundary(nearest_family: str, *, status: str = "retained") -> dict[str, Any]:
    return {
        "status": status,
        "evidence_basis": [
            "front character sheet",
            "three-quarter interaction study",
            "wide environment key art",
        ],
        "recurring_axes": sorted(style_family_audit.RECURRING_AXES),
        "excluded_scene_attributes": ["camera angle", "weather state"],
        "nearest_family": nearest_family,
        "boundary": "Structured line and grouped values separate this family from softer painterly work.",
        "review_notes": "Three distinct compositions preserve the same authored systems across materially different scene demands.",
    }


def _deferred_candidate(candidate_id: str) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "label": "Synthetic one-scene candidate",
        "decision": "deferred-not-canonical",
        "available_evidence": ["one beach portrait"],
        "evidence_gap": "Only one scene exists, so recurrence across materially different compositions is not demonstrated.",
        "reconsideration_condition": "Reconsider after three materially different scenes repeat the same finish.",
    }


def _style_family_record(record_id: str, nearest_family: str) -> dict[str, Any]:
    """A schema-complete vocabulary style family for an on-disk synthetic pack."""
    label = record_id.replace("-", " ")
    return {
        "id": record_id,
        "label": label,
        "curation_status": "vocabulary",
        "medium_family": "illustration",
        "style_promise": "Structured contours and grouped values.",
        "integration_prompt": "Use structured contours, grouped values and restrained highlights.",
        "base_render_profile_id": "synthetic-render-profile",
        "domains": ["shared"],
        "search_terms": [{"phrase": label, "facet": "style", "weight": 1.0, "source": "author"}],
        "tags": ["structured-illustration"],
        **_style_boundary(nearest_family),
    }


def run() -> dict[str, Any]:
    failures: list[str] = []
    passed = 0

    def check(condition: bool, message: str) -> None:
        nonlocal passed
        if condition:
            passed += 1
        else:
            failures.append(message)

    placeholder_errors: list[str] = []
    placeholder_findings = check_positive_text_quality(
        [
            Record(
                kind="module",
                category="composition",
                record={
                    "id": "placeholder-language-probe",
                    "curation_status": "curated",
                    "prompt": (
                        "Produce a nearby but different result with clear framing "
                        "and readable visual hierarchy."
                    ),
                },
                source="synthetic:placeholder-language-probe",
            )
        ],
        placeholder_errors,
    )
    check(
        any("nearby but different result" in item for item in placeholder_errors)
        and any(
            item.get("text") == "nearby but different result"
            for item in placeholder_findings
        ),
        "curated prompt-facing placeholder summary language must be rejected",
    )

    def exercise_quality_handler(
        label: str,
        handler: Any,
        valid_record: Record,
        mutate: Any,
        expected_error: str,
    ) -> None:
        valid_errors: list[str] = []
        valid_warnings: list[str] = []
        handler(valid_record, valid_errors, valid_warnings)
        check(
            not valid_errors,
            f"synthetic valid {label} must pass its rich quality handler: {valid_errors}",
        )

        invalid_record = copy.deepcopy(valid_record)
        mutate(invalid_record.record)
        invalid_errors: list[str] = []
        invalid_warnings: list[str] = []
        handler(invalid_record, invalid_errors, invalid_warnings)
        check(
            any(expected_error in item for item in invalid_errors),
            f"synthetic invalid {label} mutation must be rejected: {invalid_errors}",
        )

    aesthetic_core = _aesthetic_core_fixture()
    exercise_quality_handler(
        "aesthetic-core",
        check_aesthetic_core,
        aesthetic_core,
        lambda item: item.__setitem__("domains", ["human"]),
        "universal aesthetic core must use domains ['shared']",
    )

    style_family = _style_family_fixture()
    exercise_quality_handler(
        "style-family",
        check_style_family,
        style_family,
        lambda item: item["domain_overlays"].pop("robot"),
        "domain_overlays must cover exactly",
    )

    domain_realization = _domain_realization_fixture()
    exercise_quality_handler(
        "domain-realization",
        check_domain_realization,
        domain_realization,
        lambda item: item.__setitem__("domains", ["shared"]),
        "requires one exact non-shared subject domain",
    )

    distinctive_detail = _distinctive_detail_fixture()
    exercise_quality_handler(
        "distinctive-detail",
        check_distinctive_detail,
        distinctive_detail,
        lambda item: item.__setitem__("laterality", "upper-left"),
        "distinctive-detail laterality is invalid",
    )

    scene = _scene_fixture()
    exercise_quality_handler(
        "scene",
        check_scene,
        scene,
        lambda item: item["staging"].__setitem__("body_geometry", "brief"),
        "staging.body_geometry is under-authored",
    )

    archetype = _archetype_fixture()
    archetype_policy = _archetype_policy_fixture()
    exercise_quality_handler(
        "archetype",
        lambda record, errors, warnings: check_archetype(
            record,
            errors,
            warnings,
            archetype_policy,
        ),
        archetype,
        lambda item: item.__setitem__("archetype_scope", "scene-template"),
        "archetype_scope must be `recurring-character-identity`",
    )

    correction = _correction_fixture()
    exercise_quality_handler(
        "correction",
        check_correction,
        correction,
        lambda item: item.__setitem__("positive_correction", "restore contact"),
        "positive repair is under-authored",
    )

    profile = _profile_for_recipe()
    recipe = _recipe_fixture(scene, profile)
    recipe_records = [scene, profile, recipe]
    recipe_errors: list[str] = []
    recipe_warnings: list[str] = []
    check_recipes(recipe_records, recipe_errors, recipe_warnings)
    check(
        not recipe_errors,
        f"synthetic valid recipe must preserve its scene and profile snapshots: {recipe_errors}",
    )

    invalid_recipe = copy.deepcopy(recipe)
    invalid_recipe.record["scene_blueprint"]["staging"]["body_geometry"] = (
        "a different body arrangement"
    )
    invalid_recipe_errors: list[str] = []
    invalid_recipe_warnings: list[str] = []
    check_recipes(
        [scene, profile, invalid_recipe],
        invalid_recipe_errors,
        invalid_recipe_warnings,
    )
    check(
        any("staging snapshot does not preserve" in item for item in invalid_recipe_errors),
        "synthetic invalid recipe snapshot mutation must be rejected",
    )

    with tempfile.TemporaryDirectory(prefix="cpb-pack-release-gate-") as temporary:
        root = Path(temporary)

        own_family = {
            **copy.deepcopy(style_family.record),
            **_style_boundary("synthetic-painterly-family", status="new"),
            "deferred_candidates": [_deferred_candidate("synthetic-one-scene-candidate")],
        }
        other_family = {
            "id": "synthetic-painterly-family",
            "label": "Synthetic painterly family",
            **_style_boundary(own_family["id"]),
        }
        style_entries = [
            SimpleNamespace(kind="style-family", record=own_family, source_pack="synthetic-style-pack"),
            SimpleNamespace(kind="style-family", record=other_family, source_pack="synthetic-dependency-pack"),
        ]
        style_catalog = SimpleNamespace(entries=style_entries)

        def style_suite() -> dict[str, Any]:
            return _style_suite(
                {"expected_family_count": 1},
                style_catalog,
                "synthetic-style-pack",
                {"style_family_record_count": 1},
            )

        with mock.patch.object(style_family_audit, "load_entries", return_value=style_entries):
            style_report = style_family_audit.audit(root)
            check(
                style_report["ok"] is True
                and style_report["family_count"] == 2
                and style_report["revised_or_new_family_count"] == 1
                and style_report["retained_family_count"] == 1
                and style_report["deferred_candidate_count"] == 1,
                f"complete synthetic style families must pass the direct audit: {style_report}",
            )
            complete_suite = style_suite()
            check(
                complete_suite["ok"] is True
                and complete_suite["coverage_complete"] is True
                and complete_suite["actual_family_count"] == 1,
                f"the style suite counts the pack's own families: {complete_suite}",
            )

            own_family["recurring_axes"] = ["line"]
            check(
                any(
                    "at least six recurring visual axes" in item
                    for item in style_family_audit.audit(root)["errors"]
                ),
                "a family with collapsed recurring evidence is rejected by the direct audit",
            )
            collapsed_suite = style_suite()
            check(
                collapsed_suite["ok"] is False
                and any(
                    item.startswith("style audit:") and "six recurring" in item
                    for item in collapsed_suite["errors"]
                ),
                f"the style suite reports the audit's errors: {collapsed_suite['errors']}",
            )
            own_family["recurring_axes"] = sorted(style_family_audit.RECURRING_AXES)

            own_family["nearest_family"] = "synthetic-absent-family"
            check(
                any(
                    "is not another enabled style family" in item
                    for item in style_family_audit.audit(root)["errors"]
                ),
                "a nearest family outside the enabled families is rejected",
            )
            own_family["nearest_family"] = other_family["id"]

            own_family["deferred_candidates"] = [_deferred_candidate(other_family["id"])]
            check(
                any(
                    "is also a style family" in item
                    for item in style_family_audit.audit(root)["errors"]
                ),
                "a deferred candidate that is an enabled family is rejected",
            )

        base = _copy_pack(root, "base-pack")
        state, cache, managed = _runtime_paths(root, "base")
        _state(state, base)
        report = run_release_gate(
            base, state_file=state, cache_dir=cache, managed_root=managed
        )
        check(report["ok"] is True, "a generic locked pack without eval declarations must pass")
        check(report["suites"] == {}, "an undeclared suite must not appear as a skip")
        check(report["skipped"] == 0, "base-only gate must report zero skips")
        check(
            report["checks"]["runtime_cache"]["active_pack_count"] == 1,
            "exact runtime must contain one active pack",
        )
        check(
            report["checks"]["runtime_cache"]["error_diagnostic_count"] == 0,
            "exact runtime must have no error diagnostics",
        )

        ambient_state, ambient_cache, ambient_managed = _runtime_paths(root, "ambient")
        extra_root = root / "ambient-discovery-root"
        extra_root.mkdir()
        _state(ambient_state, base, extra_root=extra_root)
        ambient = run_release_gate(
            base,
            state_file=ambient_state,
            cache_dir=ambient_cache,
            managed_root=ambient_managed,
        )
        check(ambient["ok"] is False, "an ambient discovery root must be rejected")
        check(
            any("pack_roots" in item for item in ambient["errors"]),
            "ambient-root failure must identify the exact state boundary",
        )

        # A pack runs its gate with its required dependencies, and with nothing else.
        # The dependency holds one file and no records, so the two packs share no record ID.
        required = root / "required-pack"
        required_manifest = initialize_pack(required, name="Required pack", release="2026.08.24.1")
        (required / "notice.txt").write_text("required fixture\n", encoding="utf-8", newline="\n")
        required_manifest["content"]["resource_globs"] = ["*.txt"]
        _write_json(required / "pack.json", required_manifest)
        write_lock(required)
        dependent = _copy_pack(root, "dependent-pack")
        dependent_manifest = _manifest(dependent)
        dependent_manifest["dependencies"] = [{"pack_id": _manifest(required)["pack_id"]}]
        _write_json(dependent / "pack.json", dependent_manifest)
        write_lock(dependent)
        with_state, with_cache, with_managed = _runtime_paths(root, "with-dependency")
        _write_json(with_state, {
            "pack_roots": [str(dependent.resolve()), str(required.resolve())],
            "enabled_packs": [dependent_manifest["pack_id"], _manifest(required)["pack_id"]],
        })
        with_dependency = run_release_gate(dependent, state_file=with_state, cache_dir=with_cache, managed_root=with_managed)
        check(
            with_dependency["checks"].get("runtime_cache", {}).get("ok") is True
            and with_dependency["checks"]["runtime_cache"]["active_pack_count"] == 2,
            "a pack's gate runs with its required dependency enabled",
        )
        check(with_dependency["pack"].get("required_dependencies") == [_manifest(required)["pack_id"]],
              "the report names the required dependency")
        alone_state, alone_cache, alone_managed = _runtime_paths(root, "without-dependency")
        _state(alone_state, dependent)
        alone = run_release_gate(dependent, state_file=alone_state, cache_dir=alone_cache, managed_root=alone_managed)
        check(
            alone["ok"] is False and any("each required dependency" in item for item in alone["errors"]),
            "a state that leaves out a required dependency is refused",
        )

        # Style families merge across the enabled packs, so the dependent
        # pack's family names its nearest family in the dependency.
        source_root = root / "family-source-pack"
        source = initialize_pack(source_root, name="Family source pack", release="2026.10.04.1")
        _write_json(
            source_root / "records" / "style-families.json",
            {
                "kind": "style-family",
                "records": [
                    _style_family_record("synthetic-source-line-family", "synthetic-source-wash-family"),
                    _style_family_record("synthetic-source-wash-family", "synthetic-source-line-family"),
                ],
            },
        )
        write_lock(source_root)
        user_root = root / "family-user-pack"
        user = initialize_pack(user_root, name="Family user pack", release="2026.10.04.1")
        user["dependencies"] = [{"pack_id": source["pack_id"]}]
        _write_json(user_root / "pack.json", user)
        _bind(user_root, "release-evaluation-contract", "resources/evals/release-evaluation-contract.json")
        _write_json(
            user_root / "resources" / "evals" / "release-evaluation-contract.json",
            {"style_family": {"expected_family_count": 1}},
        )
        _write_json(
            user_root / "records" / "style-families.json",
            {
                "kind": "style-family",
                "records": [_style_family_record("synthetic-user-cel-family", "synthetic-source-line-family")],
            },
        )
        write_lock(user_root)
        family_state, family_cache, family_managed = _runtime_paths(root, "style-families")
        _write_json(family_state, {
            "pack_roots": [str(user_root.resolve()), str(source_root.resolve())],
            "enabled_packs": [user["pack_id"], source["pack_id"]],
        })
        merged = run_release_gate(
            user_root, state_file=family_state, cache_dir=family_cache, managed_root=family_managed
        )
        merged_suite = merged["suites"].get("style_family") or {}
        check(
            merged["ok"] is True
            and merged_suite.get("actual_family_count") == 1
            and merged_suite.get("retained_family_count") == 3,
            "one audit holds both packs' families and resolves a nearest family in the dependency: "
            f"{merged['errors']} {merged_suite}",
        )

        declared = _copy_pack(root, "declared-pack")
        _bind(
            declared,
            "catalog-search-regression",
            "resources/evals/search-regression.json",
        )
        _write_json(
            declared / "resources" / "evals" / "search-regression.json",
            {"purpose": "gate smoke", "case_count": 1, "cases": [{}]},
        )
        write_lock(declared)
        declared_state, declared_cache, declared_managed = _runtime_paths(root, "declared")
        _state(declared_state, declared)
        missing_contract = run_release_gate(
            declared,
            state_file=declared_state,
            cache_dir=declared_cache,
            managed_root=declared_managed,
        )
        check(
            missing_contract["ok"] is False,
            "declared evaluation resources must require a pack-owned contract",
        )
        check(
            any("has no pack-owned" in item for item in missing_contract["errors"]),
            "missing contract must be reported explicitly",
        )
        check(
            missing_contract["skipped"] == 0 and missing_contract["suites"] == {},
            "missing contract is a failure, not a skipped suite",
        )

        tier_pack = _copy_pack(root, "tier-pack")
        _bind(
            tier_pack,
            "tier-strategy-evaluation-cases",
            "resources/evals/tier-strategy-cases.jsonl",
        )
        _bind(
            tier_pack,
            "release-evaluation-contract",
            "resources/evals/release-evaluation-contract.json",
        )
        tier_case = {
            "id": "tier-gate-smoke",
            "brief": "one exact tier gate case",
            "domain": "human",
            "query": "soft window rim",
            "categories": ["lighting"],
            "per_category": 1,
            "profile_limit": 1,
            "core_limit": 1,
            "realization_limit": 1,
            "evaluation_focus": ["retrieval stability"],
        }
        tier_cases_path = tier_pack / "resources" / "evals" / "tier-strategy-cases.jsonl"
        tier_cases_path.parent.mkdir(parents=True, exist_ok=True)
        tier_cases_path.write_text(
            json.dumps(tier_case, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        _write_json(
            tier_pack / "resources" / "evals" / "release-evaluation-contract.json",
            {
                "tier_strategy": {
                    "cases_resource": "tier-strategy-evaluation-cases",
                    "baseline_resource": "tier-strategy-retrieval-baseline",
                    "expected_case_count": 1,
                }
            },
        )
        write_lock(tier_pack)
        tier_state, tier_cache, tier_managed = _runtime_paths(root, "tier")
        _state(tier_state, tier_pack)
        missing_baseline = run_release_gate(
            tier_pack,
            state_file=tier_state,
            cache_dir=tier_cache,
            managed_root=tier_managed,
        )
        check(missing_baseline["ok"] is False, "tier suite must require a frozen baseline")
        check(
            any("requires the pack-owned" in item for item in missing_baseline["errors"]),
            "missing tier baseline must be reported as a contract failure",
        )
        check(
            missing_baseline["executed_suite_count"] == 0
            and missing_baseline["skipped"] == 0,
            "missing tier baseline must fail before execution without becoming a skip",
        )

        preserved = _copy_pack(root, "preserved-pack")
        _bind(
            preserved,
            "release-evaluation-contract",
            "resources/evals/release-evaluation-contract.json",
        )
        preserved_record_path = preserved / "records" / "lighting.json"
        preserved_record_document = json.loads(
            preserved_record_path.read_text(encoding="utf-8")
        )
        preserved_record = preserved_record_document["records"][0]
        preserved_record["id"] = "lighting-soft-window-rim"
        preserved_record["search_profile"] = {
            "aliases": ["soft-rim-light", "rim", "soft rim light"]
        }
        _write_json(preserved_record_path, preserved_record_document)
        draft = validate_pack(preserved, require_lock=False, verify_lock=False)
        metrics = authored_metrics(draft)
        contract_path = (
            preserved / "resources" / "evals" / "release-evaluation-contract.json"
        )
        contract = {
            "preservation": {
                "expected_record_count": metrics["record_count"],
                "expected_record_content_sha256": metrics["record_content_sha256"],
                "expected_explicit_lexical_tuple_count": metrics[
                    "explicit_lexical_tuple_count"
                ],
                "expected_explicit_lexical_tuples_sha256": metrics[
                    "explicit_lexical_tuples_sha256"
                ],
                "expected_search_profile_alias_tuple_count": metrics[
                    "search_profile_alias_tuple_count"
                ],
                "expected_search_profile_alias_tuples_sha256": metrics[
                    "search_profile_alias_tuples_sha256"
                ],
                "expected_noncanonical_id_alias_count": 0,
            }
        }
        new_preservation_fields = {
            "expected_search_profile_alias_tuple_count",
            "expected_search_profile_alias_tuples_sha256",
            "expected_noncanonical_id_alias_count",
        }
        missing_field_failures: list[str] = []
        for field in sorted(new_preservation_fields):
            incomplete = json.loads(json.dumps(contract))
            incomplete["preservation"].pop(field)
            if not any(
                field in error for error in validate_release_contract(incomplete)
            ):
                missing_field_failures.append(field)
        check(
            not missing_field_failures,
            "preservation contract accepted missing alias fields: "
            + ", ".join(missing_field_failures),
        )
        invalid_field_values = {
            "expected_search_profile_alias_tuple_count": "2",
            "expected_search_profile_alias_tuples_sha256": "A" * 64,
            "expected_noncanonical_id_alias_count": "0",
        }
        type_failure_fields: list[str] = []
        for field, invalid_value in invalid_field_values.items():
            malformed = json.loads(json.dumps(contract))
            malformed["preservation"][field] = invalid_value
            if not any(field in error for error in validate_release_contract(malformed)):
                type_failure_fields.append(field)
        check(
            not type_failure_fields,
            "preservation contract accepted invalid alias-field types: "
            + ", ".join(type_failure_fields),
        )
        _write_json(contract_path, contract)
        write_lock(preserved)
        preserved_state, preserved_cache, preserved_managed = _runtime_paths(
            root, "preserved"
        )
        _state(preserved_state, preserved)
        preserved_report = run_release_gate(
            preserved,
            state_file=preserved_state,
            cache_dir=preserved_cache,
            managed_root=preserved_managed,
        )
        check(preserved_report["ok"] is True, "matching preservation invariants must pass")
        check(
            preserved_report["declared_suite_count"]
            == preserved_report["executed_suite_count"]
            == 1,
            "every declared preservation suite must execute",
        )
        check(
            preserved_report["suites"]["preservation"]["coverage_complete"] is True,
            "preservation coverage must be complete",
        )
        check(
            metrics["search_profile_alias_tuple_count"] == 3
            and metrics["noncanonical_id_alias_count"] == 0
            and preserved_report["suites"]["preservation"][
                "actual_noncanonical_id_alias_count"
            ]
            == 0,
            "ordinary one-word, spaced, and hyphenated human aliases must remain valid",
        )

        noncanonical_alias_pack = root / "noncanonical-alias-pack"
        shutil.copytree(preserved, noncanonical_alias_pack)
        noncanonical_record_path = noncanonical_alias_pack / "records" / "lighting.json"
        noncanonical_record_document = json.loads(
            noncanonical_record_path.read_text(encoding="utf-8")
        )
        noncanonical_record_document["records"][0]["search_profile"]["aliases"].append(
            "lighting-unregistered-soft-window-rim"
        )
        _write_json(noncanonical_record_path, noncanonical_record_document)
        noncanonical_draft = validate_pack(
            noncanonical_alias_pack,
            require_lock=False,
            verify_lock=False,
        )
        noncanonical_metrics = authored_metrics(noncanonical_draft)
        noncanonical_contract_path = (
            noncanonical_alias_pack
            / "resources"
            / "evals"
            / "release-evaluation-contract.json"
        )
        noncanonical_contract = json.loads(
            noncanonical_contract_path.read_text(encoding="utf-8")
        )
        noncanonical_preservation = noncanonical_contract["preservation"]
        noncanonical_preservation["expected_record_content_sha256"] = noncanonical_metrics[
            "record_content_sha256"
        ]
        noncanonical_preservation["expected_search_profile_alias_tuple_count"] = (
            noncanonical_metrics["search_profile_alias_tuple_count"]
        )
        noncanonical_preservation["expected_search_profile_alias_tuples_sha256"] = (
            noncanonical_metrics["search_profile_alias_tuples_sha256"]
        )
        noncanonical_preservation["expected_noncanonical_id_alias_count"] = 0
        _write_json(noncanonical_contract_path, noncanonical_contract)
        write_lock(noncanonical_alias_pack)
        noncanonical_state, noncanonical_cache, noncanonical_managed = _runtime_paths(
            root, "noncanonical-alias"
        )
        _state(noncanonical_state, noncanonical_alias_pack)
        noncanonical_report = run_release_gate(
            noncanonical_alias_pack,
            state_file=noncanonical_state,
            cache_dir=noncanonical_cache,
            managed_root=noncanonical_managed,
        )
        noncanonical_suite = noncanonical_report["suites"].get("preservation") or {}
        check(
            noncanonical_report["ok"] is False
            and noncanonical_metrics["noncanonical_id_alias_count"] == 1
            and noncanonical_suite.get("actual_noncanonical_id_alias_count") == 1,
            "same-namespace noncanonical profile alias must be counted and rejected",
        )
        check(
            any(
                "noncanonical" in error
                for error in noncanonical_suite.get("errors") or []
            ),
            "noncanonical profile-alias rejection must identify the invariant",
        )

        contract["preservation"]["expected_record_count"] = 0
        _write_json(contract_path, contract)
        write_lock(preserved)
        zero_report = run_release_gate(
            preserved,
            state_file=preserved_state,
            cache_dir=preserved_cache,
            managed_root=preserved_managed,
        )
        check(zero_report["ok"] is False, "zero expected suite coverage must be rejected")
        check(
            any("must be a positive integer" in item for item in zero_report["errors"]),
            "zero-coverage failure must identify its contract field",
        )

        contract["preservation"]["expected_record_count"] = metrics["record_count"]
        _write_json(contract_path, contract)
        write_lock(preserved)
        record_path = preserved / "records" / "lighting.json"
        record_path.write_text(
            record_path.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
            newline="\n",
        )
        tampered = run_release_gate(
            preserved,
            state_file=preserved_state,
            cache_dir=preserved_cache,
            managed_root=preserved_managed,
        )
        check(tampered["ok"] is False, "content changed after locking must fail")
        check(
            any("released pack:" in item for item in tampered["errors"]),
            "lock-content failure must be retained in JSON errors",
        )

        cwd_pack = root / "cwd-quality-pack"
        shutil.copytree(DEFAULT_PACK, cwd_pack)
        _bind(
            cwd_pack,
            "release-evaluation-contract",
            "resources/evals/release-evaluation-contract.json",
        )
        _write_json(
            cwd_pack / "resources" / "evals" / "release-evaluation-contract.json",
            {"quality": {"derive_expected_record_count_from_lock": True}},
        )
        write_lock(cwd_pack)
        project_state, project_cache, project_managed = _runtime_paths(
            root, "cwd-project"
        )
        foreign_state, foreign_cache, foreign_managed = _runtime_paths(
            root, "cwd-foreign"
        )
        _state(project_state, cwd_pack)
        _state(foreign_state, cwd_pack)
        foreign_cwd = root / "unrelated-working-directory"
        foreign_cwd.mkdir()
        gate_script = ROOT / "scripts" / "pack_release_gate.py"

        def run_cli(
            cwd: Path, state_file: Path, cache_dir: Path, managed_root: Path
        ) -> tuple[int, dict[str, Any], str]:
            process = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(gate_script),
                    str(cwd_pack),
                    "--state-file",
                    str(state_file),
                    "--cache-dir",
                    str(cache_dir),
                    "--managed-root",
                    str(managed_root),
                ],
                cwd=str(cwd),
                text=True,
                encoding="utf-8",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=120,
            )
            return process.returncode, json.loads(process.stdout), process.stderr

        project_exit, project_report, project_stderr = run_cli(
            ROOT, project_state, project_cache, project_managed
        )
        foreign_exit, foreign_report, foreign_stderr = run_cli(
            foreign_cwd, foreign_state, foreign_cache, foreign_managed
        )
        check(
            project_exit == foreign_exit == 0
            and project_report["ok"] is True
            and foreign_report["ok"] is True,
            "absolute gate invocation must pass from project and unrelated working directories",
        )
        check(
            project_report["suites"]["quality"]
            == foreign_report["suites"]["quality"],
            "quality suite results must be independent of the process working directory",
        )
        check(
            foreign_report["suites"]["quality"]["expected_count"] > 0
            and foreign_report["suites"]["quality"]["coverage_complete"] is True,
            "foreign-cwd smoke must execute nonzero complete quality coverage",
        )
        check(
            not project_stderr and not foreign_stderr,
            "cwd-independent CLI smoke must not emit hidden diagnostics",
        )

        corpus_manifest = root / "hostile-env-corpus-manifest.json"
        _write_json(corpus_manifest, {})
        corpus_pack_id = _manifest(base)["pack_id"]
        corpus_catalog = SimpleNamespace(
            resources={
                "reference-corpus-manifest": SimpleNamespace(
                    source_pack=corpus_pack_id,
                    sources=((corpus_pack_id, "hostile-env-corpus-manifest.json"),),
                    path=corpus_manifest,
                )
            }
        )
        captured_corpus_call: dict[str, Any] = {}
        import validate_reference_corpus

        original_validate = validate_reference_corpus.validate
        previous_hostile_env = os.environ.get("CPB_REFERENCE_CORPUS_JOBS")

        def fake_corpus_validate(
            root: Path | None = None,
            *,
            require_bundles: bool | None = None,
            workers: int | None = None,
        ) -> dict[str, Any]:
            captured_corpus_call.update(
                {
                    "root": root,
                    "require_bundles": require_bundles,
                    "workers": workers,
                }
            )
            return {
                "ok": True,
                "errors": [],
                "warnings": [],
                "stats": {
                    "validation_mode": "full",
                    "searchable_asset_count": 1,
                    "source_file_count": 1,
                    "evidence_bundle_count": 1,
                    "validated_bundle_count": 1,
                    "bundle_validation_workers": workers,
                },
            }

        try:
            os.environ["CPB_REFERENCE_CORPUS_JOBS"] = "hostile-not-an-integer"
            validate_reference_corpus.validate = fake_corpus_validate
            hostile_env_corpus = _corpus_suite(
                {
                    "manifest_resource": "reference-corpus-manifest",
                    "expected_searchable_asset_count": 1,
                    "expected_source_file_count": 1,
                    "expected_evidence_bundle_count": 1,
                },
                corpus_catalog,
                corpus_pack_id,
                {},
            )
        finally:
            validate_reference_corpus.validate = original_validate
            if previous_hostile_env is None:
                os.environ.pop("CPB_REFERENCE_CORPUS_JOBS", None)
            else:
                os.environ["CPB_REFERENCE_CORPUS_JOBS"] = previous_hostile_env

        check(
            hostile_env_corpus["ok"] is True
            and captured_corpus_call
            == {"root": None, "require_bundles": True, "workers": 1},
            "release corpus suite must commit workers=1 and ignore hostile ambient worker state",
        )

    return {
        "ok": not failures,
        "checks": passed + len(failures),
        "passed": passed,
        "failed": len(failures),
        "failures": failures,
    }


def main() -> int:
    report = run()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
