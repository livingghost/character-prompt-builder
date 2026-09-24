#!/usr/bin/env python3
"""Validate Character Prompt Builder structure without claiming artistic quality."""
from __future__ import annotations

import argparse
import narrative_corpus
import refusal_coverage
from collections import Counter
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import sys
import subprocess
import tempfile
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

sys.dont_write_bytecode = True

from catalog_cli import (
    VALID_DOMAINS,
    VALID_TIERS,
    catalog_stats,
    configure_pack_runtime,
    load_entries,
    load_pack_catalog,
    named_resource_path,
    record_tier,
)
import catalog_cli as catalog_cli_module
from pack_manager import PackSettings, validate_pack
from execution_contract import sha256_file
from validate_state_protocol import validate as validate_state_protocol
from validate_reference_corpus import validate as validate_reference_corpus
from check_dependencies import TESTED as TESTED_REQUIREMENTS, check as check_dependencies
from shot_request import validate_request as validate_shot_request
from build_generation_payload import (
    TRANSPORT_MODES,
    infer_negative_transport,
)
from prepare_generation_references import resolve_model_record
from search_discovery import catalog_query_from_mapping
from resource_policy import validate_known_resource
from state_protocol import unsupported_schema_keywords, validate_against_schema
from package import resolve_archive_path
from package_metadata import (
    host_manifests,
    LICENSE_ID, PACKAGE_NAME, PACKAGE_VERSION,
    GENERATED_RELEASE_ARTIFACT_NAMES, iter_release_files, load_package_metadata,
    pep440_version_for_calver,
    validate_skill_frontmatter_contract,
    validate_pack_gitignore_contract,
)
from reference_plan_cli_contract import plan_cli_example
from runtime_read_footprint import count_words as _skill_word_count
from io_budget import environment_seconds

ROOT_REQUIRED = (
    'SKILL.md',
    'README.md',
    'CHANGELOG.md',
    'CONTRIBUTING.md',
    'LICENSE',
    'package-manifest.toml',
    'pyproject.toml',
    'requirements-core.txt',
    'requirements-visual.txt',
    'requirements.txt',
    'requirements-tested.txt',
    'DEPENDENCIES.md',
    'PACKS.md',
    'VISUAL-CORPUS.md',
    'agents/openai.yaml',
    'scripts/package_metadata.py',
    'scripts/check_dependencies.py',
    'scripts/validate_prompt_semantics.py',
    'scripts/prompt_artifact_smoke_test.py',
    'scripts/prompt_plot_smoke_test.py',
    'scripts/narrative.py',
    'scripts/scene_plot.py',
    'scripts/narrative_contract_smoke_test.py',
    'scripts/scene_plot_contract_smoke_test.py',
    'references/narrative-protocol.md',
    'scripts/prompt_vocabulary_smoke_test.py',
    'scripts/search_prompt_vocabulary.py',
    'scripts/prompt_writing_guide.py',
    'scripts/prompt_writing_guide_smoke_test.py',
    'scripts/package_security_smoke_test.py',
    'scripts/release_file_operations_smoke_test.py',
    'scripts/default_release_smoke_test.py',
    'scripts/default_only_example_resolution_smoke_test.py',
    'scripts/catalog_cli.py',
    'scripts/catalog_cli_runtime_smoke_test.py',
    'scripts/catalog_html.py',
    'scripts/catalog_html_smoke_test.py',
    'scripts/validate_catalog_site.py',
    'scripts/package_full.py',
    'scripts/pack_manager.py',
    'scripts/resource_policy.py',
    'scripts/pack_cache.py',
    'scripts/pack_cli.py',
    'scripts/pack_smoke_test.py',
    'scripts/pack_runtime_cli.py',
    'scripts/pack_release_gate.py',
    'scripts/pack_release_gate_smoke_test.py',
    'scripts/build_generation_payload.py',
    'scripts/prepare_generation_references.py',
    'scripts/reference_active_validation.py',
    'scripts/reference_contract.py',
    'scripts/reference_plan_cli_contract.py',
    'scripts/build_reference_use_plan.py',
    'scripts/validate_reference_use_plan.py',
    'scripts/reference_runtime.py',
    'scripts/reference_runtime_smoke_test.py',
    'scripts/reference_runtime_cli_contract_test.py',
    'scripts/fresh_session_runtime_smoke_test.py',
    'scripts/generation_payload_smoke_test.py',
    'scripts/model_contract.py',
    'scripts/model_contract_smoke_test.py',
    'scripts/render_contract.py',
    'scripts/render_contract_lib.py',
    'scripts/render_contract_smoke_test.py',
    'schemas/render-intent.schema.json',
    'schemas/render-contract.schema.json',
    'schemas/model-execution-profile.schema.json',
    'config/render-presets.json',
    'references/runtime/render-contract.md',
    'scripts/nondefault_pack_isolation_smoke_test.py',
    'scripts/upscale_package.py',
    'scripts/build_upscale_package.py',
    'scripts/verify_upscale_package.py',
    'scripts/upscale_package_smoke_test.py',
    'scripts/character_sheet.py',
    'scripts/render_character_sheet.py',
    'scripts/harvest_sheet_render.py',
    'scripts/character_sheet_smoke_test.py',
    'scripts/session_entry_smoke_test.py',
    'scripts/pack_release_identity_smoke_test.py',
    'scripts/bundled_pack_gate_smoke_test.py',
    'scripts/build_state_generation_package.py',
    'scripts/state_generation_smoke_test.py',
    'scripts/feature_workflow_smoke_test.py',
    'scripts/adoption_workflow.py',
    'scripts/production_resume.py',
    'scripts/production_resume_smoke_test.py',
    'scripts/production_inputs.py',
    'scripts/craft_consultation.py',
    'scripts/craft_consultation_smoke_test.py',
    'references/runtime/craft-consultation.md',
    'examples/craft-consultation/README.md',
    'examples/craft-consultation/build_example.py',
    'examples/craft-consultation/report.json',
    'scripts/production_input_adapters.py',
    'scripts/production_inputs_smoke_test.py',
    'scripts/production_input_model_smoke_test.py',
    'scripts/dispatch_preview_smoke_test.py',
    'scripts/schema_observation_smoke_test.py',
    'scripts/production_variation_smoke_test.py',
    'scripts/runtime_evidence.py',
    'scripts/execution_policy.py',
    'scripts/request_validation.py',
    'scripts/request_scope.py',
    'scripts/request_renderer.py',
    'scripts/model_observation.py',
    'scripts/schema_observation.py',
    'scripts/production_variation_adapter.py',
    'scripts/production_variation.py',
    'scripts/production_request.py',
    'schemas/authoring/production-input-draft.schema.json',
    'scripts/studio_recipe_smoke_test.py',
    'scripts/revision_contract.py',
    'config/pack-initialization.json',
    'scripts/verify_generation_payload.py',
    'scripts/production_spec.py',
    'scripts/state_protocol.py',
    'scripts/build_scene_context.py',
    'scripts/build_visual_state_projection.py',
    'scripts/build_asset_render_spec.py',
    'scripts/build_reference_bundle.py',
    'scripts/build_candidate_manifest.py',
    'scripts/select_state_references.py',
    'scripts/shot_request.py',
    'scripts/shot_request_smoke_test.py',
    'scripts/validate_state_protocol.py',
    'scripts/integration_contract.py',
    'scripts/validate_integration.py',
    'scripts/build_interchange_envelope.py',
    'scripts/visual_evidence.py',
    'scripts/canonicalize_svg.py',
    'scripts/extract_visual_evidence.py',
    'scripts/validate_visual_evidence.py',
    'scripts/visual_evidence_smoke_test.py',
    'scripts/native_vector_visual_evidence.py',
    'scripts/compact_perceptual_visual_evidence.py',
    'scripts/validate_reference_corpus.py',
    'schemas/frame-character.schema.json',
    'schemas/part-measurement.schema.json',
    'schemas/accessory-geometry.schema.json',
    'schemas/visual-authority.schema.json',
    'schemas/semantic-region-map.schema.json',
    'schemas/visual-evidence-bundle.schema.json',
    'schemas/vectorization-result.schema.json',
    'schemas/audit-extraction-set.schema.json',
    'schemas/runtime-attachment-build.schema.json',
    'schemas/reference-corpus-manifest.schema.json',
    'schemas/reference-visual-authority.schema.json',
    'schemas/reference-semantic-region-map.schema.json',
    'schemas/pack.schema.json',
    'schemas/pack-lock.schema.json',
    'schemas/pack-record-file.schema.json',
    'schemas/pack-state.schema.json',
    'schemas/prompt-vocabulary.schema.json',
    'schemas/prompt-writing-guide.schema.json',
    'schemas/prepared-generation-reference.schema.json',
    'schemas/upscale-package.schema.json',
    'schemas/character-sheet-data.schema.json',
    'schemas/character-sheet-render-profile.schema.json',
    'schemas/reference-use-plan.schema.json',
    'schemas/surface-lighting-plan.schema.json',
    'schemas/prepared-reference-set.schema.json',
    'templates/reference-use-plan.json',
    'templates/surface-lighting-plan.json',
    'templates/prepared-reference-set.json',
    'templates/upscale-package-template.json',
    'templates/character-sheet.template.html',
    'templates/character-sheet-layout.humanoid.json',
    'templates/character-sheet-layout.anthro.json',
    'templates/reference-visual-authority.template.json',
    'templates/reference-semantic-region-map.template.json',
    'templates/vectorization-result.template.json',
    'schemas/morphology-feature.schema.json',
    'schemas/morphology-feature-instance.schema.json',
    'schemas/species-morphology-profile.schema.json',
    'schemas/individual-morphology-contract.schema.json',
    'schemas/resolved-morphology.schema.json',
    'templates/state/species-morphology-profile.template.json',
    'templates/state/individual-morphology-contract.template.json',
    'templates/frame-character-template.json',
    'templates/part-measurement-template.json',
    'templates/accessory-geometry-template.json',
    'templates/state/visual-authority.template.json',
    'templates/state/semantic-region-map.template.json',
    'templates/state/visual-evidence-bundle.template.json',
    'references/runtime/prompt-composition.md',
    'references/runtime/prompt-vocabulary.md',
    'references/runtime/prompt-writing-guide.md',
    'references/runtime/sparse-discovery.md',
    'references/runtime/reference-prompt-artifacts.md',
    'references/runtime/image-generation.md',
    'references/runtime/state-aware-series.md',
    'references/runtime/pack-state-quickstart.md',
    'references/maintenance/presets.md',
    'references/maintenance/packs.md',
    'references/maintenance/search-discovery.md',
    'references/release/validation.md',
    'references/morphology-and-species-contracts.md',
    'references/derived-visual-evidence.md',
    'references/reference-corpus-ingestion.md',
    'references/pack-format-specification.md',
    'references/catalog-cache-lifecycle.md',
    'config/default-pack-state.json',
    'config/integration-capabilities.json',
    'schemas/integration-interface.schema.json',
    'schemas/integration-capability-manifest.schema.json',
    'schemas/interchange-envelope.schema.json',
    'templates/handoff/interchange-envelope.template.json',
    'scripts/search_regression.py',
    'scripts/search_discovery.py',
    'scripts/search_discovery_smoke_test.py',
    'scripts/documentation_contract_smoke_test.py',
    'scripts/sparse_discovery_eval.py',
    'scripts/style_family_audit.py',
    'scripts/validate.py',
    'scripts/audit_preset_quality.py',
    'scripts/preset_maintenance.py',
    'scripts/preset_maintenance_smoke_test.py',
    'scripts/eval_runtime_smoke_test.py',
    'scripts/rebuild_metadata.py',
    'scripts/package.py',
    'scripts/tier_strategy_eval.py',
    'config/default-release.json',
    'templates/art-direction-template.md',
    'templates/catalog-query-template.json',
    'templates/output-template.md',
    'templates/production-spec-template.json',
    'templates/distinctive-detail-template.json',
    'templates/performance-language-template.json',
    'templates/camera-framing-contract-template.json',
    'templates/garment-geometry-template.json',
    'templates/growth-geometry-template.json',
    'templates/terminal-growth-contract-template.json',
    'templates/generation-package-template.json',
    'schemas/production-spec.schema.json',
    'schemas/catalog-query.schema.json',
    'schemas/distinctive-detail.schema.json',
    'schemas/distinctive-detail-observation.schema.json',
    'templates/distinctive-detail-observation-template.json',
    'schemas/performance-language.schema.json',
    'schemas/camera-framing-contract.schema.json',
    'schemas/garment-geometry.schema.json',
    'schemas/growth-geometry.schema.json',
    'schemas/terminal-growth-contract.schema.json',
    'schemas/character-identity-contract.schema.json',
    'schemas/state-event.schema.json',
    'schemas/state-process.schema.json',
    'schemas/state-snapshot.schema.json',
    'schemas/scene-context-snapshot.schema.json',
    'schemas/visual-state-projection.schema.json',
    'schemas/state-lineage.schema.json',
    'schemas/reference-bundle-plan.schema.json',
    'schemas/candidate-manifest.schema.json',
    'schemas/adoption-receipt.schema.json',
    'schemas/viewpoint/shot-request.schema.json',
    'templates/state/character-identity-contract.template.json',
    'templates/state/state-event.template.json',
    'templates/state/state-snapshot.template.json',
    'templates/state/scene-context-snapshot.template.json',
    'templates/state/visual-state-projection.template.json',
    'templates/state/state-lineage.template.json',
    'templates/handoff/shot-request.template.json',
    'references/creative-core.md',
    'references/aesthetic-language.md',
    'references/production-specification.md',
    'references/camera-framing-contract.md',
    'references/garment-geometry-specification.md',
    'references/growth-geometry-specification.md',
    'references/performance-language-specification.md',
    'references/distinctive-detail-specification.md',
    'references/reference-corpus-visual-technique-observation.md',
    'references/preset-system-contract.md',
    'references/preset-authoring-standard.md',
    'references/prompt-composition-geometry.md',
    'references/prompt-knowledge-boundary.md',
    'references/species-architecture.md',
    'references/style-family-taxonomy-audit.md',
    'references/preset-workflow.md',
    'references/evaluation-rubric.md',
    'references/state-protocol.md',
    'references/character-identity-contract.md',
    'references/state-event-ledger.md',
    'references/state-aware-prompt-workflow.md',
    'references/reference-bundle-workflow.md',
    'references/state-writeback-routing.md',
    'references/video-model-identity-evaluation-battery.md',
    'references/state-protocol-schema-index.md',
    'examples/state-aware-pilot/README.md',
    'examples/state-aware-pilot/build_example.py',
    'examples/state-aware-pilot/generated/generation-package.json',
    'examples/state-aware-pilot/generated/state-lineage.json',
    'examples/state-aware-pilot/generated/reference-selection.json',
    'examples/state-aware-pilot/generated/prepared-reference-set.json',
)

# Read volume is measured, not used as proof of relevance or a hard optimization gate.

# The Agent Skills specification recommends a body under 500 lines and under
# 5000 tokens, and both are refused here. No local tokenizer exists, so the token
# figure is estimated as characters divided by four.
SKILL_MAX_LINES = 500
SKILL_MAX_ESTIMATED_TOKENS = 5000
SKILL_CHARACTERS_PER_TOKEN = 4


def carried_implementation_hashes(document: str) -> dict[str, str]:
    """The hashes the narrative contract publishes for the files that answer it."""

    found: dict[str, str] = {}
    for line in document.split(chr(10)):
        parts = line.split()
        if len(parts) == 2 and parts[0].startswith("scripts/") and len(parts[1]) == 64:
            found[parts[0]] = parts[1]
    return found


def run_preset_quality_audit(root: Path, errors: list[str]) -> None:
    """The authoring conformance of what this project ships, on its own content.

    Listing this among the required files checked that the file exists, which is
    not what it is for. It reads the pack state, so it runs against a state made
    here rather than the one the person running it happens to have enabled: the
    question is whether the shipped content conforms, and a pack somebody
    installed is not shipped content.
    """

    script = root / "scripts/audit_preset_quality.py"
    if not script.is_file():
        return
    with tempfile.TemporaryDirectory(prefix="preset-audit-") as temporary:
        area = Path(temporary)
        # This gate audits core release content, not the user's newly all-on packs.
        shutil.copyfile(root / "config/default-pack-state.json", area / "pack-state.json")
        done = subprocess.run(
            [sys.executable, str(script), str(root),
             "--state-file", str(area / "pack-state.json"),
             "--cache-dir", str(area / "cache"),
             "--managed-root", str(area / "managed")],
            cwd=root, text=True, encoding="utf-8", check=False,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
    if done.returncode == 0:
        return
    detail = done.stdout.strip().splitlines()[-6:]
    errors.append("audit_preset_quality.py refused the shipped catalog: "
                  + " ".join(line.strip() for line in detail)[:600])


def check_model_record_keys(root, errors) -> None:
    """The keys a model record may carry, as the schema and the contract both state them.

    The schema is what a pack is checked against and the contract is what refuses
    an unknown key, so the two name the same set or one of them is wrong.
    """

    import model_contract as _model_contract

    schema = json.loads((root / "schemas/pack-record-file.schema.json").read_text(encoding="utf-8"))
    definitions = schema["$defs"]
    declared = set(definitions["common"]["properties"])
    for part in definitions["model"]["allOf"]:
        declared.update(part.get("properties") or {})
    if declared != set(_model_contract.MODEL_RECORD_KEYS):
        only_schema = sorted(declared - set(_model_contract.MODEL_RECORD_KEYS))
        only_contract = sorted(set(_model_contract.MODEL_RECORD_KEYS) - declared)
        errors.append(
            "model record keys differ between schemas/pack-record-file.schema.json and "
            f"model_contract.MODEL_RECORD_KEYS: only the schema has {only_schema}, only the contract has {only_contract}"
        )


def check_declared_enumerations(root, errors) -> None:
    """Check closed operational vocabularies and explicitly open authored fields."""

    import sys as _sys

    _sys.path.insert(0, str(root / "scripts"))
    import narrative as _narrative
    import scene_plot as _scene_plot

    documents = "".join(
        path.read_text(encoding="utf-8")
        for path in sorted((root / "references").rglob("*.md"))
    ) + (root / "SKILL.md").read_text(encoding="utf-8")
    declared = {
        "arc status": list(_narrative.ARC_STATUS),
        "chapter status": list(_narrative.CHAPTER_STATUS),
        "promise status": list(_narrative.PROMISE_STATUS),
        "question status": list(_narrative.QUESTION_STATUS),
        "prohibition kind": list(_narrative.PROHIBITION_KINDS),
        "medium": sorted(_narrative.MEDIA),
        "focalization": list(_scene_plot.FOCALIZATIONS),
        "interior or exterior": list(_scene_plot.INTERIOR_EXTERIOR),
        "passage mode": list(_scene_plot.PASSAGE_MODES),
        "realization kind": sorted(_scene_plot.REALIZATIONS),
        "scene statement kind": list(_scene_plot.SCENE_KINDS),
        "beat visibility": list(_scene_plot.VISIBILITIES),
    }
    narrative_document = (root / "references/narrative-protocol.md").read_text(encoding="utf-8")
    for field in ("arcs[].type", "relationships[].bond_type", "delivery_role",
                  "relationship_delta[].channel", "scene_function", "structure.profile"):
        if f"| `{field}` | nonempty authored text |" not in narrative_document:
            errors.append(f"the narrative contract must declare {field} as open authored text")

    # As a word. A substring match answered `main` with `domain`, `both` with
    # `bother` and `scene` with `scenes`, so a list could be absent from every
    # document and reported as present by the prose around it.
    def named(value: str) -> bool:
        return re.search(rf"(?<![A-Za-z0-9_-]){re.escape(value)}(?![A-Za-z0-9_-])",
                         documents) is not None

    for label, values in sorted(declared.items()):
        absent = [value for value in values if not named(value)]
        if absent:
            errors.append(
                f"every {label} the carried reader accepts has to be named in a routed "
                f"document, and these are in none: {absent}"
            )


def check_carried_implementation(root, contract_relative, errors) -> None:
    """The reader that answers the contract, against the hash the contract publishes.

    An installation reads only itself, so nothing here can compare this copy of
    the reader with a copy anywhere else. What it can do is check that the reader
    and the document stating its rules were changed together, which is what keeps
    an edit to one from drifting away from the other in silence.
    """

    contract = root / contract_relative
    if not contract.is_file():
        errors.append(f"the narrative contract is missing: {contract_relative}")
        return
    published = carried_implementation_hashes(contract.read_text(encoding="utf-8"))
    if not published:
        errors.append(f"{contract_relative} publishes no implementation hashes")
        return
    for relative, expected in sorted(published.items()):
        path = root / relative
        if not path.is_file():
            errors.append(f"{contract_relative} publishes a hash for {relative}, which is absent")
            continue
        found = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        if found != expected:
            errors.append(
                f"{relative} does not match the hash the narrative contract publishes: "
                f"{found[:12]} against {expected[:12]}; the reader and the document that publishes "
                "its hash travel together, and an edit to one has to travel with the other"
            )
FRESH_SESSION_RUNTIME_DOCUMENTS = (
    "references/runtime/prompt-composition.md",
    "references/runtime/sparse-discovery.md",
    "references/runtime/reference-prompt-artifacts.md",
    "references/runtime/pack-state-quickstart.md",
)
# SKILL.md routes each of these by a link or by naming a route or feature that delivers it.
SKILL_ROUTED_DOCUMENTS = (
    "references/runtime/narrative-development.md",
    "references/runtime/cast-and-persona-depth.md",
    "references/runtime/prompt-composition.md",
    "references/runtime/sparse-discovery.md",
    "references/runtime/prompt-writing-guide.md",
    "references/runtime/reference-prompt-artifacts.md",
    "references/runtime/image-generation.md",
    "references/runtime/state-aware-series.md",
    "references/runtime/studio.md",
    "references/runtime/pack-state-quickstart.md",
    "references/maintenance/presets.md",
    "references/maintenance/packs.md",
    "references/maintenance/search-discovery.md",
    "references/release/validation.md",
)
# Prompt work in conversation reads these without a route read, so SKILL.md links each one.
SKILL_DIRECT_LINKS = (
    "references/runtime/prompt-only-core.md",
    "references/runtime/prompt-composition.md",
    "references/runtime/sparse-discovery.md",
    "references/runtime/prompt-vocabulary.md",
    "references/runtime/prompt-writing-guide.md",
    "references/runtime/subject-domain-quick-reference.md",
    "references/runtime/craft-consultation.md",
)
ADAPTER_DIRECTORY = "references/adapters"

PUBLISHED_BLOCK = re.compile(
    "```text" + chr(10) + "(?:scripts/\\S+[ \\t]+[0-9a-f]{64}" + chr(10) + ")+```" + chr(10))


def contract_digest(document: str) -> str:
    """The contract over everything except the block that publishes reader hashes.

    The reader carries this document's hash and this document carries the
    reader's, which cannot both be computed unless one of them is taken over
    less than the whole. The protocol already cuts that way: `content_sha256`
    is taken with the `approved` block removed, because an approval cannot be
    part of what it approves. A published hash cannot be part of what it
    publishes either.
    """

    stripped = PUBLISHED_BLOCK.sub("", document.replace(chr(13) + chr(10), chr(10)))
    return hashlib.sha256(stripped.encode("utf-8")).hexdigest()


def check_contract_document(root, contract_relative, errors) -> None:
    """The contract document, against the hash the reader that answers it carries.

    Two copies of this contract are meant to be the same document. Nothing here
    can see the other copy, but both copies carry a reader whose hash this
    document publishes, and that reader names the hash of this document, so a
    copy edited on one side stops matching its own reader and is refused where
    it was edited rather than diverging in silence.
    """

    contract = root / contract_relative
    reader = root / "scripts" / "narrative.py"
    if not contract.is_file() or not reader.is_file():
        return
    text = reader.read_text(encoding="utf-8")
    match = re.search(r"(?m)^CONTRACT_SHA256 = \"([0-9a-f]{64})\"$", text)
    if not match:
        errors.append("scripts/narrative.py publishes no CONTRACT_SHA256 for the contract it answers")
        return
    found = contract_digest(contract.read_text(encoding="utf-8"))
    if found != match.group(1):
        errors.append(
            f"{contract_relative} does not match the hash its reader carries: "
            f"{found[:12]} against {match.group(1)[:12]}; the contract and the reader that "
            "answers it travel together, and an edit to one has to travel with the other"
        )


def _adapter_documents(root: Path) -> tuple[str, ...]:
    """Return every adapter document that exists, newest routing authority first."""

    directory = root / ADAPTER_DIRECTORY
    if not directory.is_dir():
        return ()
    return tuple(sorted(f"{ADAPTER_DIRECTORY}/{path.name}" for path in directory.glob("*.md")))


def _route_deliveries(root: Path) -> dict[str, tuple[str, ...]]:
    """Return, for each route and feature name, the documents a route read prints for it."""

    path = root / "config/execution-routes.json"
    if not path.is_file():
        return {}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    features = manifest.get("features", {})
    deliveries: dict[str, set[str]] = {}
    for name, feature in features.items():
        deliveries.setdefault(name, set()).update(feature.get("reads", ()))
    for name, route in manifest.get("routes", {}).items():
        reads = deliveries.setdefault(name, set())
        reads.update(manifest.get("always_read", ()), route.get("reads", ()))
        for feature in route.get("features", ()):
            reads.update(features.get(feature, {}).get("reads", ()))
    return {name: tuple(sorted(reads)) for name, reads in deliveries.items()}


def _named_route_documents(root: Path, skill: str) -> set[str]:
    """Return what a route read delivers for each route or feature SKILL.md names."""

    return {
        read
        for name, reads in _route_deliveries(root).items()
        if f"`{name}`" in skill
        for read in reads
    }


def _skill_routed_documents(root: Path, skill: str) -> set[str]:
    """Return what SKILL.md links and what a route read delivers for each route or feature it names."""

    return set(_markdown_link_targets(skill)) | _named_route_documents(root, skill)


def _skill_target_adapters(skill: str, root: Path) -> tuple[str, ...]:
    """Return the adapters SKILL.md offers as the one selectable target adapter."""

    selection = [line for line in skill.splitlines() if "exactly one of" in line]
    if not selection:
        return ()
    deliveries = _route_deliveries(root)
    targets = {
        target
        for line in selection
        for target in (
            *_markdown_link_targets(line),
            *(read for name in re.findall(r"`([^`]+)`", line) for read in deliveries.get(name, ())),
        )
        if target.startswith(f"{ADAPTER_DIRECTORY}/")
    }
    return tuple(sorted(targets))


SKILL_REQUIRED_ROUTER_PHRASES = (
    "# Character Prompt Builder",
    "## Core contract",
    "## Choose a runtime path",
    "## Common runtime sequence",
    "## Identity and scene-state authority",
    "## Catalog and pack runtime",
    "## Visual Reference Activation Gate",
    "## Output contract",
    "## Maintenance and release",
    "user anchors",
    "creative space",
    "Keep judgment and automation separate.",
    "A script is usable only when routed documentation exposes activation, input, output, help or example, failures, and a regression test.",
    "Inspect every selected canonical record in full.",
    "resolve the optional `prompt-writing-guide`",
    "Inspect complete records and asset details together with `inspect-many` (or `inspect` plus `asset-lookup`).",
    "A category name proposes; only the author's declaration decides.",
    "Species, domain, and material supply no default.",
    "growth, grooming, hair, fur, feathers, quills, bristles, spun fiber, molded strands, nails, claws, talons, hooves, digit plates",
    "Scene-specific character state is an open class",
    "Do not start several catalog CLI processes in parallel.",
    "A file path or hash is not delivery.",
    "Treat every selected SVG as bounded evidence, not as the whole requested image.",
)
SKILL_FORBIDDEN_DEEP_RUNTIME_TOKENS = (
    "scripts/pack_release_gate.py",
    "scripts/build_state_generation_package.py",
    "python -m pip install",
)
AUTHORITATIVE_DOCUMENT_MARKERS = {
    "references/runtime/narrative-development.md": (
        "# World-Coherent Creative Development",
        "## Activation and ownership",
        "## 2. Develop the relevant dependencies, in either direction",
        "## 3. Make alternatives along the requested axis",
        "## 4. Test coherence at the interfaces",
        "## 6. Connect to the existing narrative and production contracts",
        "## Checks and limits",
        "not a questionnaire",
        "Neither can establish",
    ),
    "references/runtime/cast-and-persona-depth.md": (
        "# Cast Admission and Persona Depth",
        "## Four separate questions",
        "## Admission: the author decides who joins the cast",
        "## One Persona structure, depth by use",
        "## After an appearance",
        "joins the active cast only after the author confirms that candidate",
        "One line proves no habitual voice",
    ),
    "references/runtime/prompt-composition.md": (
        "# Prompt Composition Runtime",
        "## Image intent and anchor integrity",
        "## Whole-image art direction",
        "## Construction order",
        "## Representation grammar",
        "## Catalog retrieval and inspection",
        "## Prompt assembly and review",
        "## Negative output",
        "Search is discovery, not authority.",
        "When the user specifies anime, produce anime. When the user specifies photorealism, produce photorealism.",
        "nose thickness and placement, ear construction",
        "load both [Morphology and Species Contracts]",
        "Before atomic retrieval, always run one `search --kind archetype`",
        "Run full `asset-lookup` for each record",
        "The bundled commons pack selects `profile-clear-2d-illustration`",
        "Read `query_token_count`, `axis_coverage`, and any `retrieval_note`",
    ),
    "references/runtime/sparse-discovery.md": (
        "# Sparse-Brief Discovery Runtime",
        "## Activation",
        "## Anchor extraction",
        "## Translation boundary",
        "## Direction cards",
        "## Catalog workflow",
        "## Runtime failure rules",
        "Recommendation output is not an adopted record.",
        "`fixed_component_overrides` is populated when",
        "Read `query_token_count`, `axis_coverage`, and any `retrieval_note`",
    ),
    "references/runtime/prompt-writing-guide.md": (
        "# Prompt Writing Guide Runtime",
        "## Activation",
        "## Resolve the active guide",
        "## Application sequence",
        "## Weighting and prompt pressure",
        "## Controlled comparison",
        "## Failure policy",
        "When a selected provider exists, read the complete resolved JSON",
        "The Skill-using agent decides which rules are relevant.",
    ),
    "references/runtime/reference-prompt-artifacts.md": (
        "# Prompt Artifact Reference Runtime",
        "## Activation gate",
        "## Record-scoped authority",
        "## Technical artifact roles",
        "## Prompt-facing transports",
        "## Surface and Lighting Plan",
        "## Commands",
        "## Validation and failure policy",
        "A path or hash in prose is not file delivery.",
        "Full `asset-lookup` and review are mandatory for every selected record",
    ),
    "references/runtime/image-generation.md": (
        "# Image Generation Runtime",
        "## Activation and dependency preflight",
        "## Model-facing reference transport",
        "## Generation Package",
        "## Verification and host forwarding",
        "## Failure policy",
        "Do not reconstruct from chat.",
        "The model-record catalog is the single extensibility boundary.",
        "commits all three renditions independently",
        "are the complete forwarding contract",
    ),
    "references/runtime/state-aware-series.md": (
        "# State-Aware Series Runtime",
        "Do not reconstruct current state from chat memory.",
    ),
    "references/runtime/pack-state-quickstart.md": (
        "# Pack State Runtime Quickstart",
        "`pack-state.json` is the complete activation authority.",
        "python scripts/pack_cli.py resource negative-policy",
    ),
    "references/growth-geometry-specification.md": (
        "# Growth Geometry Specification",
        "A fixed menu of body regions is not the common model.",
        'Use `representation: "declared-structures"` and a map of author-owned IDs.',
        "## Authoring",
        "## Detailed geometry",
        "## Terminal structures",
        "## Resolved authority in state-aware packages",
        "Missing data is not an instruction to invent anatomy.",
    ),
    "references/visual-reference-activation-and-transport.md": (
        "# Visual reference activation and transport",
        "## Semantic reading",
        "## Role map",
        "## Reference-to-prompt synthesis",
        "preserve authorized evidence, replace conflicting source content, add target content, and omit contamination",
        "## Review",
    ),
    "references/state-event-ledger.md": (
        "# State Event Ledger and Deterministic Snapshot Resolution",
        "Evaluate every precondition against the unchanged input state before applying any change",
    ),
    "references/reference-bundle-workflow.md": (
        "# Reference Bundle Workflow",
        "must record the resulting registry version and any supersession relationship",
    ),
    "references/preset-workflow.md": (
        "# Preset Workflow",
        "`query_token_count`, and a conditional `retrieval_note`",
        "python scripts/catalog_cli.py inspect profile-clear-2d-illustration",
        "python scripts/catalog_cli.py inspect domain-realization-anthropomorphic-animal-baseline",
        "python scripts/catalog_cli.py inspect style-family-clear-portrait",
    ),
    "references/adapters/gpt-image.md": (
        "# GPT Image Adapter",
        "Transport a safe selected SVG as a deterministic PNG derived from that same SVG.",
    ),
    "references/adapters/midjourney-niji.md": (
        "# Midjourney and Niji Adapter",
        "Transmit only the verified native negative subset through `--no`.",
    ),
    "references/adapters/flux.md": (
        "# FLUX Adapter",
        "Do not assume negative conditioning exists in the active workflow.",
    ),
    "references/adapters/sdxl-comfyui.md": (
        "# SDXL and ComfyUI Adapter",
        "Send the complete verified negative prompt through separate conditioning.",
    ),
    "references/adapters/novelai.md": (
        "# NovelAI Adapter",
        "Send the verified negative prompt to undesired content.",
    ),
    "references/adapters/unlisted-interface.md": (
        "# Unlisted Image Interface Adapter",
        "There is no explicit media override.",
    ),
    "references/maintenance/presets.md": (
        "# Preset Maintenance",
        "Never deduplicate as size optimization, cache construction, export, copying, or packaging.",
    ),
    "references/maintenance/packs.md": (
        "# Pack Maintenance",
        "A storage location is not a pack taxonomy.",
    ),
    "references/maintenance/search-discovery.md": (
        "# Search Discovery Maintenance",
        "Facets are discovery projections, not production authority.",
    ),
    "references/release/validation.md": (
        "# Release Validation",
        "Release validation is an exact-profile gate, not an artistic-quality claim.",
        "Publication checks the installed source, local public contract, declared resources",
        "and executable fixtures.",
    ),
}


def iter_jsonl(path: Path) -> Iterable[tuple[int, Any]]:
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if raw.strip():
            yield line_number, json.loads(raw)






def strip_fenced_blocks(text: str) -> str:
    lines: list[str] = []
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            lines.append("")
            continue
        lines.append("" if fenced else line)
    return "\n".join(lines)


def _markdown_heading_slug(heading: str) -> str:
    heading = re.sub(r"[*_`~]", "", heading.strip().lower())
    return re.sub(r"\s", "-", re.sub(r"[^\w\s-]", "", heading))


def markdown_anchor_slugs(document: Path) -> set[str]:
    """Return the slug set an external fragment link can target in a document."""

    slugs: set[str] = set()
    seen: dict[str, int] = {}
    for line in document.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        base = _markdown_heading_slug(match.group(1))
        if not base:
            continue
        uses = seen.get(base, 0)
        seen[base] = uses + 1
        slugs.add(f"{base}-{uses}" if uses else base)
    return slugs


def validate_local_markdown_links(root: Path, document: Path, errors: list[str]) -> int:
    text = strip_fenced_blocks(document.read_text(encoding="utf-8"))
    count = 0
    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
        target = target.strip()
        if not target or target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        path_part = target.split("#", 1)[0]
        if not path_part:
            continue
        count += 1
        resolved = (document.parent / path_part).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            errors.append(f"local link escapes package root in {document.name}: {target}")
            continue
        if not resolved.exists():
            errors.append(f"broken local link in {document.name}: {target}")
            continue
        fragment = target.split("#", 1)[1] if "#" in target else ""
        if fragment and resolved.suffix == ".md" and fragment not in markdown_anchor_slugs(resolved):
            errors.append(f"broken local anchor link in {document.name}: {target}")
    return count


def _fresh_session_consumed_cli_word_counts() -> dict[str, int]:
    """Measure the exact help/example outputs consumed by the baseline route."""

    batch_help = io.StringIO()
    original_program = sys.argv[0]
    try:
        sys.argv[0] = "catalog_cli.py"
        with contextlib.redirect_stdout(batch_help):
            try:
                catalog_cli_module.main(["batch", "--help"])
            except SystemExit as exc:
                if exc.code not in (None, 0):
                    raise RuntimeError(
                        f"catalog batch --help failed with exit {exc.code}"
                    ) from exc
    finally:
        sys.argv[0] = original_program
    example_text = json.dumps(
        plan_cli_example(),
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    )
    return {
        "catalog batch --help": _skill_word_count(batch_help.getvalue()),
        "reference_runtime example plan": _skill_word_count(example_text),
    }


def _markdown_link_targets(text: str) -> tuple[str, ...]:
    targets: list[str] = []
    for raw in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
        target = raw.strip().strip("<>").split("#", 1)[0]
        if target:
            targets.append(target.replace("\\", "/"))
    return tuple(targets)


def _reachable_reference_documents(root: Path, skill: str) -> set[str]:
    """Return Markdown references reached by links from SKILL.md and from the documents
    a route read delivers for each route or feature SKILL.md names."""

    resolved_root = root.resolve()
    delivered = sorted(
        relative for relative in _named_route_documents(root, skill) if (root / relative).is_file()
    )
    pending = ["SKILL.md", *delivered]
    visited: set[str] = set()
    reached_references = {relative for relative in delivered if relative.startswith("references/")}
    while pending:
        relative = pending.pop()
        if relative in visited:
            continue
        visited.add(relative)
        path = root / relative
        if not path.is_file():
            continue
        for target in _markdown_link_targets(path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("mailto:"):
                continue
            candidate = (path.parent / target).resolve()
            if not candidate.is_relative_to(resolved_root) or candidate.suffix.lower() != ".md":
                continue
            if not candidate.is_file():
                continue
            candidate_relative = candidate.relative_to(resolved_root).as_posix()
            if candidate_relative.startswith("references/"):
                reached_references.add(candidate_relative)
            if candidate_relative not in visited:
                pending.append(candidate_relative)
    return reached_references


def check_skill_documentation_contract(root: Path, errors: list[str]) -> dict[str, Any]:
    """Validate the lean skill router and its authoritative routed documents."""
    observed: dict[str, Any] = {}

    skill_path = root / "SKILL.md"
    if not skill_path.is_file():
        errors.append("missing SKILL.md for documentation contract validation")
        return observed

    skill = skill_path.read_text(encoding="utf-8")
    try:
        skill_frontmatter = validate_skill_frontmatter_contract(
            skill_path,
            expected_name=PACKAGE_NAME,
        )
    except ValueError as exc:
        errors.append(f"SKILL.md frontmatter contract failed: {exc}")
        fields: list[str] = []
    else:
        fields = list(skill_frontmatter)
    observed["SKILL frontmatter fields"] = fields

    word_count = _skill_word_count(skill)
    observed["SKILL words"] = word_count

    line_count = len(skill.splitlines())
    observed["SKILL lines"] = line_count
    if line_count > SKILL_MAX_LINES:
        errors.append(
            f"SKILL.md exceeds the {SKILL_MAX_LINES}-line limit the specification "
            f"recommends: observed {line_count}"
        )
    estimated_tokens = -(-len(skill) // SKILL_CHARACTERS_PER_TOKEN)
    observed["SKILL estimated tokens"] = estimated_tokens
    if estimated_tokens > SKILL_MAX_ESTIMATED_TOKENS:
        errors.append(
            f"SKILL.md exceeds the {SKILL_MAX_ESTIMATED_TOKENS}-token limit the specification "
            f"recommends: estimated {estimated_tokens} from {len(skill)} characters"
        )

    for phrase in SKILL_REQUIRED_ROUTER_PHRASES:
        if phrase not in skill:
            errors.append(f"SKILL.md is missing lean-router invariant: {phrase}")
    for token in SKILL_FORBIDDEN_DEEP_RUNTIME_TOKENS:
        if token in skill:
            errors.append(
                "SKILL.md must route to specialist instructions instead of embedding deep "
                f"runtime or maintenance commands: {token}"
            )
    routed_documents = _skill_routed_documents(root, skill)
    unrouted = [relative for relative in SKILL_ROUTED_DOCUMENTS if relative not in routed_documents]
    observed["SKILL routed documents"] = len(SKILL_ROUTED_DOCUMENTS) - len(unrouted)
    for relative in unrouted:
        errors.append(f"SKILL.md does not route the required document: {relative}")
    link_targets = _markdown_link_targets(skill)
    for relative in SKILL_DIRECT_LINKS:
        if relative not in link_targets:
            errors.append(f"SKILL.md does not link the conversational prompt document: {relative}")

    all_reference_documents = {
        path.relative_to(root).as_posix()
        for path in (root / "references").rglob("*.md")
        if path.is_file()
    }
    reachable_reference_documents = _reachable_reference_documents(root, skill)
    unreachable_reference_documents = sorted(
        all_reference_documents - reachable_reference_documents
    )
    observed["reachable reference documents"] = len(reachable_reference_documents)
    observed["total reference documents"] = len(all_reference_documents)
    observed["unreachable reference documents"] = unreachable_reference_documents
    for relative in unreachable_reference_documents:
        errors.append(
            "reference document is reached by no SKILL.md link or named route or feature: "
            + relative
        )

    reachable_runtime_text = skill + "\n" + "\n".join(
        (root / relative).read_text(encoding="utf-8")
        for relative in sorted(reachable_reference_documents)
    )
    documented_entrypoints: list[str] = []
    undocumented_entrypoints: list[str] = []
    scripts_root = root / "scripts"
    if scripts_root.is_dir():
        for script_path in sorted(scripts_root.glob("*.py")):
            script_text = script_path.read_text(encoding="utf-8")
            if not re.search(
                r"if\s+__name__\s*==\s*['\"]__main__['\"]\s*:",
                script_text,
            ):
                continue
            if script_path.name in reachable_runtime_text:
                documented_entrypoints.append(script_path.name)
            else:
                undocumented_entrypoints.append(script_path.name)
    observed["documented script entrypoints"] = len(documented_entrypoints)
    observed["undocumented script entrypoints"] = undocumented_entrypoints
    for script_name in undocumented_entrypoints:
        errors.append(
            "script entrypoint is unreachable from routed Skill documentation: "
            + script_name
        )

    document_word_count = 0
    authoritative_texts: dict[str, str] = {}
    for relative, markers in AUTHORITATIVE_DOCUMENT_MARKERS.items():
        path = root / relative
        if not path.is_file():
            errors.append(f"missing authoritative routed document: {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        authoritative_texts[relative] = text
        document_word_count += _skill_word_count(text)
        for marker in markers:
            if marker not in text:
                errors.append(
                    f"authoritative routed document {relative} is missing contract marker: "
                    f"{marker}"
                )
    for owner, markers in AUTHORITATIVE_DOCUMENT_MARKERS.items():
        heading = markers[0]
        for relative, text in authoritative_texts.items():
            if relative != owner and heading in text:
                errors.append(
                    f"authoritative routed document {relative} contains authority heading "
                    f"owned by {owner}: {heading}"
                )
    observed["authoritative routed-document words"] = document_word_count

    fresh_session_words = word_count
    fresh_session_complete = True
    for relative in FRESH_SESSION_RUNTIME_DOCUMENTS:
        path = root / relative
        if not path.is_file():
            fresh_session_complete = False
            continue
        fresh_session_words += _skill_word_count(path.read_text(encoding="utf-8"))
    try:
        consumed_cli_words = _fresh_session_consumed_cli_word_counts()
    except Exception as exc:
        fresh_session_complete = False
        consumed_cli_words = {}
        errors.append(f"cannot render fresh-session CLI context: {exc}")
    else:
        fresh_session_words += sum(consumed_cli_words.values())
    observed["fresh-session consumed CLI words"] = consumed_cli_words
    observed["fresh-session sparse prompt-artifacts words"] = (
        fresh_session_words if fresh_session_complete else None
    )

    adapters = _adapter_documents(root)
    target_adapters = _skill_target_adapters(skill, root)
    observed["adapter documents"] = len(adapters)
    observed["SKILL target adapters"] = len(target_adapters)
    for relative in adapters:
        if relative not in routed_documents:
            errors.append(f"SKILL.md does not route the adapter document: {relative}")
    for relative in target_adapters:
        if relative not in adapters:
            errors.append(
                f"SKILL.md offers a target adapter that does not exist: {relative}"
            )

    image_generation_path = root / "references/runtime/image-generation.md"
    if image_generation_path.is_file() and target_adapters:
        image_generation_links = _markdown_link_targets(
            image_generation_path.read_text(encoding="utf-8")
        )
        for relative in target_adapters:
            adapter_from_runtime = "../adapters/" + Path(relative).name
            if adapter_from_runtime not in image_generation_links:
                errors.append(
                    "image-generation runtime is missing target-adapter link: "
                    f"{adapter_from_runtime}"
                )

    prompt_runtime_path = root / "references/runtime/prompt-composition.md"
    if prompt_runtime_path.is_file():
        prompt_runtime = prompt_runtime_path.read_text(encoding="utf-8")
        for forbidden in (
            "scripts/build_state_generation_package.py",
            "scripts/pack_release_gate.py",
        ):
            if forbidden in prompt_runtime:
                errors.append(
                    "prompt-composition runtime must not embed state or release maintenance "
                    f"commands: {forbidden}"
                )

    adapter_headings = {
        relative: markers[0]
        for relative, markers in AUTHORITATIVE_DOCUMENT_MARKERS.items()
        if relative.startswith("references/adapters/")
    }
    for relative, own_heading in adapter_headings.items():
        path = root / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for other_relative, other_heading in adapter_headings.items():
            if other_relative != relative and other_heading in text:
                errors.append(
                    f"model adapter {relative} contains another adapter heading: {other_heading}"
                )
        if text.count(own_heading) != 1:
            errors.append(
                f"model adapter {relative} must contain exactly one own-model heading: "
                f"{own_heading}"
            )

    return observed


def check_documentation(root: Path, errors: list[str]) -> dict[str, Any]:
    observed: dict[str, Any] = {}
    readme_path = root / "README.md"
    contributing_path = root / "CONTRIBUTING.md"
    license_path = root / "LICENSE"

    readme = readme_path.read_text(encoding="utf-8")
    observed["README heading"] = next(
        (line.strip() for line in readme.splitlines() if line.startswith("# ")), None
    )
    if observed["README heading"] != "# Character Prompt Builder":
        errors.append("README heading must be '# Character Prompt Builder' without release-version prose")
    # README explains how a user operates the product, including release names.
    # Authoritative metadata and contributor procedure are validated separately;
    # their existence does not prohibit explaining them here. Keep the links to
    # those authorities instead of enforcing a smaller, link-only README.
    for required_target in ("CONTRIBUTING.md", "LICENSE", "package-manifest.toml", "requirements-core.txt", "requirements-visual.txt", "requirements.txt", "requirements-tested.txt"):
        if f"]({required_target})" not in readme:
            errors.append(f"README must link to {required_target}")

    non_code = strip_fenced_blocks(readme)
    path_pattern = re.compile(
        r"(?:references|scripts|packs|schemas|templates|config|examples|agents)/[A-Za-z0-9_./-]+"
        r"|\b(?:CONTRIBUTING\.md|package-manifest\.toml|SKILL\.md|LICENSE)\b"
    )
    for line_number, line in enumerate(non_code.splitlines(), start=1):
        for match in path_pattern.finditer(line):
            raw = match.group(0).rstrip(".,;:")
            if f"]({raw})" not in line and f"]({raw.rstrip('/')}/)" not in line:
                errors.append(
                    f"README local path must be a Markdown link at line {line_number}: {raw}"
                )

    observed["README local links"] = validate_local_markdown_links(root, readme_path, errors)
    observed["CONTRIBUTING local links"] = validate_local_markdown_links(
        root, contributing_path, errors
    )

    contributing = contributing_path.read_text(encoding="utf-8")
    for marker in (
        "UTC CalVer",
        "package-manifest.toml",
        "Preset Authoring Standard",
        "references/release/validation.md",
        "GNU General Public License version 3 only",
        "Core internal artifacts do not carry independent counters",
        "Content packs have independent UTC CalVer releases",
        "immutable semantic identifiers",
        "$schema",
    ):
        if marker not in contributing:
            errors.append(f"CONTRIBUTING.md is missing required governance marker: {marker}")

    license_text = license_path.read_text(encoding="utf-8")
    observed["license bytes"] = len(license_text.encode("utf-8"))
    if "GNU GENERAL PUBLIC LICENSE" not in license_text:
        errors.append("LICENSE must contain the GNU General Public License text")
    if "Version 3, 29 June 2007" not in license_text:
        errors.append("LICENSE must contain GNU GPL version 3")
    if "END OF TERMS AND CONDITIONS" not in license_text:
        errors.append("LICENSE is missing the end of the GPL terms")
    if "How to Apply These Terms to Your New Programs" in license_text:
        errors.append("LICENSE must omit the optional application appendix so no author placeholder is present")
    if "<name of author>" in license_text or "Copyright (C) 2026" in license_text:
        errors.append("LICENSE must not name a project copyright holder")

    search_maintenance_path = root / "references/maintenance/search-discovery.md"
    if search_maintenance_path.is_file():
        search_maintenance = search_maintenance_path.read_text(encoding="utf-8")
        for marker in (
            "expression",
            "emotion",
            "pose",
            "activity",
            "situation",
            "theme",
            "content_intensity",
            "erotic",
            "sexual",
            "## Coverage changes and evaluation ownership",
        ):
            if marker not in search_maintenance:
                errors.append(
                    "search-discovery maintenance reference is missing required marker: "
                    f"{marker}"
                )

    knowledge_boundary = (root / "references/prompt-knowledge-boundary.md").read_text(encoding="utf-8")
    for marker in (
        "Prompt-only work stops before execution",
        "Do not silently remove",
        "Preservation is not invention",
        "Searchability is part of fidelity",
        "erotic",
        "sexual",
        "nudity",
        "fetish",
        "Execution boundary",
        "Non-diegetic source artifacts",
        "censor mask",
        "Do not create a canonical field saying that censoring, concealment, or an overlay occurred",
        "does not prove the exact hidden geometry",
    ):
        if marker not in knowledge_boundary:
            errors.append(f"prompt-knowledge boundary reference is missing required marker: {marker}")

    return observed


def newest_changelog_release(text: str) -> str | None:
    """Return the topmost CHANGELOG heading, the newest release, which must equal the package version."""

    match = re.search(r"^##\s+([^\s:]+)", text, re.M)
    return match.group(1) if match else None


def check_version_consistency(root: Path, errors: list[str]) -> dict[str, Any]:
    """Validate product-release identity without versioning internal artifacts."""
    observed: dict[str, Any] = {}

    try:
        metadata = load_package_metadata(root)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"package-manifest.toml is invalid: {exc}")
        return observed

    observed["package manifest"] = metadata.version
    observed["pyproject project.version"] = metadata.pyproject_version
    observed["version scheme"] = metadata.version_scheme
    observed["release timezone"] = metadata.release_timezone
    observed["license"] = metadata.license_id

    try:
        changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"CHANGELOG.md is missing or unreadable: {exc}")
        observed["CHANGELOG latest"] = None
    else:
        from release_contract import validate_changelog
        observed["CHANGELOG latest"] = newest_changelog_release(changelog)
        errors.extend(validate_changelog(changelog, metadata.version, style="plain"))

    try:
        manifest = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))
        observed["MANIFEST"] = manifest.get("version")
        if manifest.get("version") != metadata.version:
            errors.append("MANIFEST.json product release differs from package-manifest.toml")
    except (OSError, json.JSONDecodeError) as exc:
        observed["MANIFEST"] = None
        errors.append(f"MANIFEST.json is missing or unreadable: {exc}")

    # The host manifests are generated from this same metadata. Comparing the
    # documents rather than a field or two means a host reads exactly what the
    # package says, and a stale file is a mismatch instead of a version nobody
    # thought to check.
    for relative, expected in host_manifests().items():
        path = root / relative
        try:
            actual = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{relative} is missing or invalid: {exc}")
            continue
        if actual != expected:
            errors.append(
                f"{relative} differs from the package metadata; run scripts/rebuild_metadata.py"
            )
    observed["host manifests"] = len(host_manifests())

    # The two repository guides are one document under the two names a host looks
    # for, rendered from one template. A hand edit to either is overwritten by the
    # next build, so it is reported here instead of disappearing silently.
    template_path = root / "hosts" / "shared" / "repository-guide.md.template"
    try:
        rendered = template_path.read_text(encoding="utf-8").format(
            name=metadata.name, version=metadata.version, description=metadata.description
        )
    except (OSError, KeyError, IndexError) as exc:
        errors.append(f"hosts/shared/repository-guide.md.template is missing or invalid: {exc}")
    else:
        for relative in ("AGENTS.md", "CLAUDE.md"):
            path = root / relative
            if not path.is_file():
                errors.append(f"{relative} is missing; run scripts/rebuild_metadata.py")
            elif path.read_text(encoding="utf-8") != rendered:
                errors.append(
                    f"{relative} differs from the repository guide template; "
                    "run scripts/rebuild_metadata.py"
                )

    return observed


def _canonical_manifest_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"not a normalized POSIX relative path: {value!r}")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"not a normalized POSIX relative path: {value!r}")
    return value


def verify_release_manifest(
    root: Path,
    metadata: Any,
    entries: list[Any],
    *,
    strict_release_tree: bool,
) -> dict[str, Any]:
    """Verify MANIFEST against the shared, explicit release inventory."""

    findings: list[str] = []
    inventory = iter_release_files(
        root,
        metadata.release_include,
        exclude_names=metadata.release_exclude_names,
    )
    expected_files = {
        path.relative_to(root).as_posix(): path
        for path in inventory
    }
    manifest_path = root / "MANIFEST.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "strict_release_tree": strict_release_tree,
            "expected_files": len(expected_files),
            "manifest_files": 0,
            "errors": [f"MANIFEST.json is unreadable: {exc}"],
        }
    if not isinstance(manifest, dict):
        return {
            "ok": False,
            "strict_release_tree": strict_release_tree,
            "expected_files": len(expected_files),
            "manifest_files": 0,
            "errors": ["MANIFEST.json must contain an object"],
        }

    expected_identity = {
        "package": metadata.name,
        "version": metadata.version,
        "version_scheme": metadata.version_scheme,
        "release_timezone": metadata.release_timezone,
        "license": metadata.license_id,
    }
    for field, expected in expected_identity.items():
        if manifest.get(field) != expected:
            findings.append(
                f"MANIFEST {field} mismatch: expected {expected!r}, got {manifest.get(field)!r}"
            )

    rows = manifest.get("files")
    if not isinstance(rows, list):
        rows = []
        findings.append("MANIFEST files must be an array")
    observed_rows: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            findings.append(f"MANIFEST files[{index}] must be an object")
            continue
        try:
            relative = _canonical_manifest_path(row.get("path"))
        except ValueError as exc:
            findings.append(f"MANIFEST files[{index}].path is invalid: {exc}")
            continue
        if relative in observed_rows:
            findings.append(f"MANIFEST contains duplicate path: {relative}")
            continue
        observed_rows[relative] = row

    expected_paths = set(expected_files)
    observed_paths = set(observed_rows)
    missing = sorted(expected_paths - observed_paths)
    unexpected = sorted(observed_paths - expected_paths)
    if missing:
        findings.append(f"MANIFEST is missing release files: {missing}")
    if unexpected:
        findings.append(f"MANIFEST contains files outside release inventory: {unexpected}")

    measured_bytes = 0
    for relative, path in expected_files.items():
        size = path.stat().st_size
        measured_bytes += size
        row = observed_rows.get(relative)
        if row is None:
            continue
        if row.get("bytes") != size:
            findings.append(
                f"MANIFEST byte count mismatch for {relative}: expected {size}, got {row.get('bytes')!r}"
            )
        digest = sha256_file(path)
        if row.get("sha256") != digest:
            findings.append(f"MANIFEST SHA-256 mismatch for {relative}")
    if manifest.get("file_count_excluding_manifest") != len(expected_files):
        findings.append(
            "MANIFEST file_count_excluding_manifest mismatch: "
            f"expected {len(expected_files)}, got {manifest.get('file_count_excluding_manifest')!r}"
        )
    if manifest.get("total_bytes_excluding_manifest") != measured_bytes:
        findings.append(
            "MANIFEST total_bytes_excluding_manifest mismatch: "
            f"expected {measured_bytes}, got {manifest.get('total_bytes_excluding_manifest')!r}"
        )

    pack_catalog = load_pack_catalog()
    counts = catalog_stats(entries)
    tier_counts = dict(sorted(Counter(record_tier(entry.record) for entry in entries).items()))
    expected_pack_catalog = {
        "default_state": "config/default-pack-state.json",
        "default_pack_count": len(metadata.default_pack_ids),
        "record_counts": counts,
        "tier_counts": tier_counts,
        "named_resources": sorted(pack_catalog.resources),
    }
    actual_pack_catalog = manifest.get("pack_catalog")
    if not isinstance(actual_pack_catalog, dict):
        findings.append("MANIFEST pack_catalog must be an object")
    else:
        if set(actual_pack_catalog) != set(expected_pack_catalog):
            findings.append(
                "MANIFEST pack_catalog fields mismatch: "
                f"expected {sorted(expected_pack_catalog)}, got {sorted(actual_pack_catalog)}"
            )
        for field, expected in expected_pack_catalog.items():
            if actual_pack_catalog.get(field) != expected:
                findings.append(f"MANIFEST pack_catalog.{field} does not match active default packs")

    if strict_release_tree:
        links = sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_symlink()
        )
        if links:
            findings.append(f"strict release tree contains symbolic links: {links}")
        actual_files = {
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file()
        }
        allowed_files = expected_paths | {"MANIFEST.json"}
        strict_missing = sorted(allowed_files - actual_files)
        strict_unexpected = sorted(actual_files - allowed_files)
        if strict_missing:
            findings.append(f"strict release tree is missing files: {strict_missing}")
        if strict_unexpected:
            findings.append(f"strict release tree contains undeclared files: {strict_unexpected}")

    return {
        "ok": not findings,
        "strict_release_tree": strict_release_tree,
        "expected_files": len(expected_files),
        "manifest_files": len(observed_rows),
        "total_bytes_excluding_manifest": measured_bytes,
        "errors": findings,
    }


def verify_release_line_endings(root: Path, metadata: Any) -> dict[str, Any]:
    """Verify the release inventory is LF-normalized.

    MANIFEST records working-tree bytes and digests, so a source file left with
    CRLF yields a manifest that only reproduces on the platform that wrote it.
    """

    findings: list[str] = []
    paths = sorted(
        iter_release_files(
            root,
            metadata.release_include,
            exclude_names=metadata.release_exclude_names,
        ),
        key=lambda value: value.relative_to(root).as_posix(),
    )
    for path in paths:
        data = path.read_bytes()
        carriage_returns = data.count(b"\r")
        if not carriage_returns:
            continue
        crlf = data.count(b"\r\n")
        findings.append(
            f"release file is not LF-normalized: {path.relative_to(root).as_posix()} "
            f"({crlf} CRLF, {carriage_returns - crlf} bare CR)"
        )
    return {
        "ok": not findings,
        "checked_files": len(paths),
        "errors": findings,
    }


def run_visual_evidence_smoke(root: Path) -> dict[str, Any]:
    """Run the production visual-operations gate and retain failure evidence."""

    process = subprocess.run(
        [sys.executable, "scripts/visual_evidence_smoke_test.py"],
        cwd=root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    errors: list[str] = []
    try:
        parsed = json.loads(process.stdout)
        if not isinstance(parsed, dict):
            raise ValueError("visual smoke output must be a JSON object")
        report: dict[str, Any] = parsed
    except (json.JSONDecodeError, ValueError) as exc:
        report = {"ok": False}
        errors.append(f"visual smoke returned invalid JSON: {exc}")
    if process.returncode != 0:
        errors.append(f"visual smoke exited with status {process.returncode}")
    if process.stderr.strip():
        report["stderr"] = process.stderr.strip()
    if errors:
        report["ok"] = False
        report["errors"] = [*report.get("errors", []), *errors]
    else:
        report.setdefault("errors", [])
    report["command_returncode"] = process.returncode
    return report



def run_reference_runtime_smoke(root: Path) -> dict[str, Any]:
    """Run automatic SVG activation and multi-reference transport regression."""

    process = subprocess.run(
        [sys.executable, "scripts/reference_runtime_smoke_test.py"],
        cwd=root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    errors: list[str] = []
    try:
        parsed = json.loads(process.stdout)
        if not isinstance(parsed, dict):
            raise ValueError("reference runtime smoke output must be a JSON object")
        report: dict[str, Any] = parsed
    except (json.JSONDecodeError, ValueError) as exc:
        report = {"ok": False}
        errors.append(f"reference runtime smoke returned invalid JSON: {exc}")
    if process.returncode != 0:
        errors.append(f"reference runtime smoke exited with status {process.returncode}")
    if process.stderr.strip():
        report["stderr"] = process.stderr.strip()
    if errors:
        report["ok"] = False
        report["errors"] = [*report.get("errors", []), *errors]
    else:
        report.setdefault("errors", [])
    report["command_returncode"] = process.returncode
    return report


def run_nondefault_pack_isolation_smoke(root: Path) -> dict[str, Any]:
    """Run the owner-pack isolation regression without reading owner pack content."""

    process = subprocess.run(
        [sys.executable, "scripts/nondefault_pack_isolation_smoke_test.py"],
        cwd=root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    errors: list[str] = []
    try:
        parsed = json.loads(process.stdout)
        if not isinstance(parsed, dict):
            raise ValueError("nondefault-pack isolation output must be a JSON object")
        report: dict[str, Any] = parsed
    except (json.JSONDecodeError, ValueError) as exc:
        report = {"ok": False}
        errors.append(f"nondefault-pack isolation returned invalid JSON: {exc}")
    if process.returncode != 0:
        errors.append(f"nondefault-pack isolation exited with status {process.returncode}")
    if process.stderr.strip():
        report["stderr"] = process.stderr.strip()
    if errors:
        report["ok"] = False
        report["errors"] = [*report.get("errors", []), *errors]
    else:
        report.setdefault("errors", [])
    report["command_returncode"] = process.returncode
    return report


def run_preset_maintenance_smoke(root: Path) -> dict[str, Any]:
    """Run duplicate-audit and transactional-removal regressions."""

    process = subprocess.run(
        [sys.executable, "scripts/preset_maintenance_smoke_test.py"],
        cwd=root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "ok": process.returncode == 0,
        "command_returncode": process.returncode,
        "stdout": process.stdout.strip(),
        "stderr": process.stderr.strip(),
        "errors": [] if process.returncode == 0 else [
            f"preset maintenance smoke exited with status {process.returncode}"
        ],
    }


def run_feature_workflow_smoke(root: Path) -> dict[str, Any]:
    process = subprocess.run([sys.executable, "scripts/feature_workflow_smoke_test.py"], cwd=root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True, encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    try:
        result = json.loads(process.stdout)
    except ValueError:
        result = {"ok": False, "errors": ["feature workflow returned invalid JSON"], "stdout": process.stdout}
    if process.returncode != 0 or process.stderr:
        result["ok"] = False
        result.setdefault("errors", []).append(f"feature workflow exited {process.returncode}: {process.stderr}")
    return result


def run_structure_neutrality_smoke(root: Path) -> dict[str, Any]:
    process = subprocess.run([sys.executable, "scripts/structure_neutrality_smoke_test.py"], cwd=root,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True, encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    try:
        result = json.loads(process.stdout)
    except ValueError:
        result = {"ok": False, "errors": ["structure neutrality returned invalid JSON"], "stdout": process.stdout}
    if process.returncode != 0 or process.stderr:
        result["ok"] = False
        result.setdefault("errors", []).append(f"structure neutrality exited {process.returncode}: {process.stderr}")
    return result


def non_english_characters(text: str) -> dict[int, str]:
    """Map each line number to the characters on it written in another script.

    A letter outside the Latin script, or a punctuation mark from the CJK and
    fullwidth blocks, marks text that is not English, whichever language it
    is. Accented Latin letters, symbols and typographic punctuation pass, so a
    name such as Zo\u00eb or a section sign is not an error.
    """

    found: dict[int, str] = {}
    for number, line in enumerate(text.splitlines(), 1):
        characters = ""
        for character in line:
            code_point = ord(character)
            if code_point < 0x80 or character in characters:
                continue
            foreign_letter = (
                unicodedata.category(character).startswith("L")
                and not unicodedata.name(character, "").startswith("LATIN")
            )
            cjk_punctuation = (
                0x3000 <= code_point <= 0x303F
                or 0xFE30 <= code_point <= 0xFE4F
                or 0xFF00 <= code_point <= 0xFFEF
            )
            if foreign_letter or cjk_punctuation:
                characters += character
        if characters:
            found[number] = characters
    return found


def check_english_content(root: Path) -> list[str]:
    """Report canonical instruction files that carry text in another language.

    Every routed Markdown document under ``references/`` is in scope, not only
    the top level, because a document a host reads is canonical wherever it
    sits. Inline code spans and fenced blocks are in scope too: an exact form
    in a character's language belongs in the persona form under ``templates/``,
    which this check leaves alone, and a quoted line in a reference is a
    leftover. The report names the first offending line and its characters.
    """

    errors: list[str] = []
    core_text_files = [
        root / "SKILL.md", root / "README.md", root / "CONTRIBUTING.md", root / "CHANGELOG.md",
        root / "agents" / "openai.yaml",
    ] + sorted((root / "references").rglob("*.md"), key=lambda value: value.as_posix())
    for path in core_text_files:
        if not path.is_file():
            continue
        found = non_english_characters(path.read_text(encoding="utf-8"))
        if found:
            number, characters = next(iter(found.items()))
            errors.append(
                "canonical instruction file is not English: "
                f"{path.relative_to(root).as_posix()}:{number} ({characters})"
            )
    return errors


REGRESSION_TIMEOUT_VARIABLE = "VALIDATE_REGRESSION_TIMEOUT_SECONDS"


def _captured_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value or ""


def run_standalone_regression(root: Path, name: str, *, output_format: str) -> dict:
    """Run a registered suite and retain its evidence without weakening its exit status.

    The suite runs to completion unless the operator sets
    VALIDATE_REGRESSION_TIMEOUT_SECONDS; validation chooses no deadline of its
    own. An exceeded deadline is reported in the result rather than ending
    validation without one.
    """
    budget = environment_seconds(REGRESSION_TIMEOUT_VARIABLE)
    try:
        proc = subprocess.run(
            [sys.executable, str(root / "scripts" / name)], cwd=root,
            capture_output=True, text=True, encoding="utf-8", timeout=budget,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False, "returncode": None, "tests": 0,
            "errors": [f"regression exceeded the explicit {budget}-second budget {REGRESSION_TIMEOUT_VARIABLE}"],
            "stdout": _captured_text(exc.stdout), "stderr": _captured_text(exc.stderr),
        }
    if output_format == "json":
        try:
            result = json.loads(proc.stdout)
        except json.JSONDecodeError:
            result = {"ok": False, "errors": ["regression did not emit JSON"]}
        if not isinstance(result, dict):
            result = {"ok": False, "errors": ["regression result must be an object"]}
        return {
            **result, "ok": proc.returncode == 0 and result.get("ok") is True,
            "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr,
        }
    if output_format == "unittest":
        observed = re.search(r"Ran (\d+) tests? in ", proc.stderr)
        count = int(observed.group(1)) if observed else 0
        return {
            "ok": proc.returncode == 0 and count > 0,
            "tests": count, "returncode": proc.returncode,
            "stdout": proc.stdout, "stderr": proc.stderr,
        }
    raise ValueError("unsupported regression output format")


def validate(
    root: Path,
    *,
    write_report: bool = False,
    package_structural_only: bool = False,
    state_file: Path | None = None,
    cache_dir: Path | None = None,
    managed_root: Path | None = None,
    strict_release_tree: bool = False,
) -> dict[str, Any]:
    metadata = load_package_metadata(root)
    explicit_runtime = (state_file, cache_dir, managed_root)
    if any(value is not None for value in explicit_runtime) and not all(
        value is not None for value in explicit_runtime
    ):
        raise ValueError("state_file, cache_dir, and managed_root must be supplied together")
    validation_runtime: tempfile.TemporaryDirectory[str] | None = None
    if state_file is None:
        validation_runtime = tempfile.TemporaryDirectory(prefix="cpb-validation-")
        validation_runtime_root = Path(validation_runtime.name)
        state_file = validation_runtime_root / "pack-state.json"
        cache_dir = validation_runtime_root / "cache"
        managed_root = validation_runtime_root / "managed"
    assert state_file is not None and cache_dir is not None and managed_root is not None
    workspace_pack_roots = sorted(
        (root / value for value in metadata.release_pack_dirs),
        key=lambda path: path.as_posix(),
    )
    workspace_pack_ids: list[str] = []
    workspace_pack_validation: list[dict[str, Any]] = []
    for pack_root in workspace_pack_roots:
        pack_report = validate_pack(pack_root, require_lock=True)
        workspace_pack_validation.append(
            {
                "path": pack_root.relative_to(root).as_posix(),
                "pack_id": pack_report.pack_id,
                "release": pack_report.release,
                "ok": pack_report.valid,
                "errors": [
                    issue.to_dict() for issue in pack_report.issues if issue.severity == "error"
                ],
                "warnings": [
                    issue.to_dict() for issue in pack_report.issues if issue.severity == "warning"
                ],
                "records": len(pack_report.records),
                "resources": len(pack_report.resource_files),
            }
        )
        if pack_report.pack_id:
            workspace_pack_ids.append(pack_report.pack_id)
    configure_pack_runtime(
        PackSettings(
            roots=tuple(path.resolve() for path in workspace_pack_roots),
            state_file=state_file.resolve(),
            cache_dir=cache_dir.resolve(),
            managed_root=managed_root.resolve(),
            quarantine_root=(managed_root.resolve() / ".quarantine").resolve(),
            default_enabled_packs=tuple(metadata.default_pack_ids),
            default_resource_providers=tuple(
                sorted(metadata.resource_providers.items())
            ),
        )
    )
    errors: list[str] = []
    warnings: list[str] = []
    for pack_report in workspace_pack_validation:
        if not pack_report["ok"]:
            errors.append(f"workspace pack validation failed: {pack_report['path']}")
    missing_default_pack_ids = [
        pack_id for pack_id in metadata.default_pack_ids
        if pack_id not in workspace_pack_ids
    ]
    if missing_default_pack_ids:
        errors.append(
            "validated release packs omit default-pack-state activations: "
            + ", ".join(missing_default_pack_ids)
        )
    if package_structural_only:
        dependency_report = {
            "ok": None,
            "profile": "tested",
            "definition": TESTED_REQUIREMENTS.name,
            "not_run": True,
            "reason": "the release packager runs the exact dependency gate before structural validation",
            "errors": [],
        }
        visual_evidence_smoke = {
            "ok": None,
            "not_run": True,
            "reason": "the release packager runs visual-evidence validation before structural validation",
            "errors": [],
        }
        reference_runtime_smoke = {
            "ok": None,
            "not_run": True,
            "reason": "the release packager runs reference-runtime validation before structural validation",
            "errors": [],
        }
    else:
        dependency_report = check_dependencies(root / TESTED_REQUIREMENTS.name)
        if not dependency_report.get("ok"):
            errors.append("exact tested Python dependency validation failed")
        visual_evidence_smoke = run_visual_evidence_smoke(root)
        if not visual_evidence_smoke.get("ok"):
            errors.append("production visual-evidence smoke validation failed")
        reference_runtime_smoke = run_reference_runtime_smoke(root)
        if not reference_runtime_smoke.get("ok"):
            errors.append("visual-reference activation and transport smoke validation failed")
    nondefault_pack_isolation_smoke = run_nondefault_pack_isolation_smoke(root)
    if not nondefault_pack_isolation_smoke.get("ok"):
        errors.append("nondefault-pack core-isolation smoke validation failed")
    preset_maintenance_smoke = run_preset_maintenance_smoke(root)
    if not preset_maintenance_smoke.get("ok"):
        errors.append("preset duplicate and removal maintenance smoke validation failed")
    structure_neutrality_smoke = run_structure_neutrality_smoke(root)
    if not structure_neutrality_smoke.get("ok"):
        errors.append("structure neutrality smoke validation failed")
    feature_workflow_smoke = run_feature_workflow_smoke(root)
    if not feature_workflow_smoke.get("ok"):
        errors.append("feature workflow smoke validation failed")
    try:
        release_files = list(
            iter_release_files(
                root,
                metadata.release_include,
                exclude_names=metadata.release_exclude_names,
            )
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"release inventory failed: {exc}")
        release_files = []
    manifest_path = root / "MANIFEST.json"
    files = release_files + ([manifest_path] if manifest_path.is_file() else [])

    generated_reports = [
        name for name in (
            "validation-report.json", "preset-authoring-audit.json",
            "sparse-discovery-report.json",
        )
        if (root / name).exists()
    ]
    if generated_reports:
        errors.append(
            "generated release reports must stay outside the distributable tree: "
            + ", ".join(generated_reports)
        )

    for path in files:
        if path.suffix.lower() in {".pyc", ".pyo", ".bak", ".orig", ".tmp"} or path.name.endswith("~"):
            errors.append(f"development artifact remains: {path.relative_to(root).as_posix()}")
        try:
            decoded = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            decoded = ""
        if "\u2014" in decoded:
            errors.append(f"Unicode em dash is forbidden in the distributable skill: {path.relative_to(root).as_posix()}")
        if "\u2013" in decoded:
            errors.append(f"Unicode en dash is forbidden in the distributable skill: {path.relative_to(root).as_posix()}")

    for relative in ROOT_REQUIRED:
        if not (root / relative).is_file():
            errors.append(f"missing required file: {relative}")

    run_preset_quality_audit(root, errors)

    gitignore_path = root / ".gitignore"
    if gitignore_path.is_file():
        try:
            validate_pack_gitignore_contract(
                gitignore_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            errors.append(f"default-only pack tracking contract is invalid: {exc}")

    documentation_observed = check_documentation(root, errors)
    documentation_observed.update(check_skill_documentation_contract(root, errors))
    # Routed artifact workflows are checked as dependency graphs, not name hits.
    try:
        from execution_routes import validate as validate_execution_routes
        execution_report = validate_execution_routes(root)
        documentation_observed["artifact-bearing execution routes"] = execution_report
        errors.extend("execution routes: " + error for error in execution_report["errors"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(f"execution route contract is invalid: {exc}")

    # A manifest entry proves a test exists, not that the release exercised it.
    # Run JSON-report suites and unittest suites under their actual result formats.
    regressions = {
        "release_management_smoke_test.py": "json",
        "readme_smoke_test.py": "json",
        "evidence_tools_smoke_test.py": "json",
        "reference_delivery_smoke_test.py": "json",
        "scene_material_smoke_test.py": "unittest",
        "agent_evaluation_smoke_test.py": "unittest",
        "resource_handling_smoke_test.py": "unittest",
        "reimplementation_smoke_test.py": "unittest",
        "craft_consultation_smoke_test.py": "unittest",
        "render_contract_smoke_test.py": "unittest",
    }
    for name, output_format in regressions.items():
        result = run_standalone_regression(root, name, output_format=output_format)
        documentation_observed[name] = result
        if result["ok"] is not True:
            errors.append(f"artifact evidence regression failed: {name}")

    link_documents: list[Path] = sorted(root.glob("*.md"))
    for link_tree in ("references", "examples", "agents", "tests"):
        link_root = root / link_tree
        if link_root.is_dir():
            link_documents.extend(sorted(link_root.rglob("*.md")))
    locally_checked = {"README.md", "CONTRIBUTING.md"}
    local_link_count = 0
    for link_document in link_documents:
        if link_document.parent == root and link_document.name in locally_checked:
            continue
        local_link_count += validate_local_markdown_links(root, link_document, errors)
    documentation_observed["repository local markdown links"] = local_link_count

    skill_files = [path for path in files if path.name == "SKILL.md"]
    if len(skill_files) != 1:
        errors.append(f"expected one SKILL.md, found {len(skill_files)}")

    output_template = root / "templates" / "output-template.md"
    if output_template.is_file():
        output_text = output_template.read_text(encoding="utf-8")
        required_output_headings = [
            "## Creative direction",
            "## Prompt",
            "## Negative prompt",
            "## Reference mode",
            "## Conditional delivered artifacts",
            "## Reference review",
        ]
        optional_trailing_headings = ["## Assumptions", "## Modifications"]
        observed_output_headings = re.findall(r"^## .+$", output_text, re.M)
        observed_optional_headings = observed_output_headings[
            len(required_output_headings) :
        ]
        if (
            observed_output_headings[: len(required_output_headings)]
            != required_output_headings
            or observed_optional_headings
            != [
                heading
                for heading in optional_trailing_headings
                if heading in observed_optional_headings
            ]
        ):
            errors.append(
                "output template headings or their order are invalid: "
                f"required {required_output_headings} with only optional trailing "
                f"{optional_trailing_headings}, got {observed_output_headings}"
            )
        required_reference_disclosures = (
            "Always deliver `final-prompt.txt`.",
            "Deliver `final-negative.txt` only when required.",
            "When one or more references are selected",
            "reference-use-plan.json",
            "reference-artifacts/<selected SVG files>",
            "surface-lighting-plan.json",
            "only when source lighting or material response",
            "prepared-reference-set.json",
            "reference-preamble.txt",
            "only for a target-specific or generation-ready package",
            "Do not create empty placeholder reference files.",
            "A path or checksum is not delivery.",
            "ordered semantic roles and precedence",
            "exact authority controls and exclusions",
            "source-state leakage result",
            "unnamed-averaging result",
            "source-lighting mode and material response",
        )
        missing_disclosures = [
            marker
            for marker in required_reference_disclosures
            if marker not in output_text
        ]
        if missing_disclosures:
            errors.append(
                "output template is missing prepared-reference disclosure contracts: "
                f"{missing_disclosures}"
            )

    expected_tiers = {"any", "curated", "vocabulary"}
    expected_domains = {
        "human", "anthropomorphic-animal", "animal", "creature",
        "hybrid", "robot", "shared",
    }
    if VALID_TIERS != expected_tiers:
        errors.append(
            f"tier vocabulary mismatch: expected {sorted(expected_tiers)}, got {sorted(VALID_TIERS)}"
        )
    if VALID_DOMAINS != expected_domains:
        errors.append(
            f"domain vocabulary mismatch: expected {sorted(expected_domains)}, got {sorted(VALID_DOMAINS)}"
        )

    # Parse every JSON and JSONL artifact. Internal formats are identified by
    # artifact_type and structure, not by independent version fields.
    parsed_json: dict[str, Any] = {}
    for path in (item for item in files if item.suffix.lower() == ".json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            rel = path.relative_to(root).as_posix()
            parsed_json[rel] = data
        except Exception as exc:  # noqa: BLE001
            errors.append(f"invalid JSON {path.relative_to(root).as_posix()}: {exc}")

    for path in (item for item in files if item.suffix.lower() == ".jsonl"):
        try:
            for line_number, data in iter_jsonl(path):
                rel = path.relative_to(root).as_posix()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"invalid JSONL {path.relative_to(root).as_posix()}: {exc}")

    for path in (item for item in files if item.suffix.lower() == ".py"):
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Python compile failed {path.relative_to(root).as_posix()}: {exc}")

    errors.extend(check_english_content(root))

    version_observed = check_version_consistency(root, errors)

    try:
        metadata = load_package_metadata(root)
        default_archive = resolve_archive_path(root, metadata.release_output, None)
        expected_archive = (root / metadata.release_output).resolve()
        if default_archive != expected_archive:
            errors.append(
                "package.py default output does not resolve to package-manifest.toml release.output"
            )
        output_parts = Path(metadata.release_output).parts
        if output_parts and output_parts[0] in metadata.release_include:
            errors.append(
                "manifest release.output is inside an allowlisted release input"
            )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"package output contract validation failed: {exc}")

    package_source = (root / "scripts" / "package.py").read_text(encoding="utf-8")
    if "path.stat().st_mode" in package_source or "stat.S_IMODE" in package_source:
        errors.append("deterministic packager must not copy host file permission bits")
    for marker in (
        "0o644",
        "0o755",
        "info.create_system = 3",
        "resolve_archive_path",
        # The raw archive digest still depends on the deflate implementation, so
        # a compression-independent content digest must remain available for
        # comparing builds made with different interpreters.
        "def archive_content_sha256",
        "content_sha256",
        # The reproducibility claim is only a claim until the packager builds the
        # archive twice and asks it to verify its own member CRCs, and reports both.
        "zip_crc_ok",
        "deterministic_rebuild",
    ):
        if marker not in package_source:
            errors.append(f"deterministic packager is missing cross-platform marker: {marker}")
    if re.search(r'add_argument\(\s*["\']--out["\'][^\n]*required\s*=\s*True', package_source):
        errors.append("package.py --out must be optional so manifest release.output is usable")

    # Lint every schema document statically. Instance-driven validation only
    # visits the branches an artifact happens to exercise, so an unimplemented
    # keyword parked in an unvisited branch would stay a silent no-op.
    schema_root = root / "schemas"
    for schema_path in sorted(schema_root.rglob("*.json"), key=lambda value: value.as_posix()):
        rel = schema_path.relative_to(root).as_posix()
        schema_document = parsed_json.get(rel)
        if not isinstance(schema_document, dict):
            errors.append(f"schema document is unreadable: {rel}")
            continue
        for finding in unsupported_schema_keywords(schema_document):
            errors.append(
                f"{rel}: schema keyword is authored but never enforced at {finding}"
            )

    query_schema = parsed_json.get("schemas/catalog-query.schema.json")
    if not isinstance(query_schema, dict):
        errors.append("catalog-query schema is unavailable for runtime validation")
    else:
        valid_query = {
            "anchors": {
                "species": "wolf",
                "body_build": ["muscular"],
            }
        }
        if validate_against_schema(valid_query, query_schema):
            errors.append("catalog-query schema rejects a valid anchors-only query")
        invalid_query_samples = (
            {},
            {"anchors": {}},
            {"canonical_query": "wolf", "unexpected": True},
            {"anchors": {"Bad-Key": "wolf"}},
            {"anchors": {"species": ["wolf", 3]}},
        )
        if any(not validate_against_schema(sample, query_schema) for sample in invalid_query_samples):
            errors.append(
                "catalog-query schema does not enforce anyOf, minProperties, propertyNames, oneOf, and additionalProperties"
            )
        try:
            catalog_query_from_mapping(valid_query)
        except ValueError as exc:
            errors.append(f"catalog query parser rejects a schema-valid query: {exc}")
        for sample in invalid_query_samples:
            try:
                catalog_query_from_mapping(sample)
            except ValueError:
                continue
            errors.append(f"catalog query parser accepted schema-invalid input: {sample}")

    try:
        model_catalog = {
            str(entry.record["id"]): dict(entry.record)
            for entry in load_pack_catalog().entries
            if entry.kind == "model" and entry.record.get("id")
        }
        if not model_catalog:
            errors.append("enabled default packs do not provide a model record")
        valid_transport_modes = TRANSPORT_MODES - {"auto"}
        for model_id, record in model_catalog.items():
            declared = str(record.get("negative_transport_mode") or "")
            if declared not in valid_transport_modes:
                errors.append(
                    f"enabled model record {model_id!r} has invalid negative_transport_mode {declared!r}"
                )
                continue
            try:
                inferred = infer_negative_transport(model_id)
            except ValueError as exc:
                errors.append(f"model transport resolution failed for {model_id!r}: {exc}")
                continue
            if inferred != declared:
                errors.append(
                    f"model transport mismatch for {model_id!r}: declared {declared!r}, resolved {inferred!r}"
                )
            aliases = record.get("aliases") or []
            if not isinstance(aliases, list):
                errors.append(
                    f"enabled model record {model_id!r} aliases must be an array"
                )
                continue
            names = [model_id, str(record.get("label") or "")]
            names.extend(str(value) for value in aliases)
            for name in names:
                if not name.strip():
                    continue
                try:
                    resolved_id, _resolved_record = resolve_model_record(name)
                except ValueError as exc:
                    errors.append(
                        f"model catalog name {name!r} does not resolve exactly: {exc}"
                    )
                    continue
                if resolved_id != model_id:
                    errors.append(
                        f"model catalog name {name!r} resolves to {resolved_id!r}, not {model_id!r}"
                    )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"model transport catalog validation failed: {exc}")

    try:
        entries = load_entries()
        counts = catalog_stats(entries)
        active_pack_ids = {entry.source_pack for entry in entries}
        if active_pack_ids != set(metadata.default_pack_ids):
            errors.append(
                "active validation catalog must contain exactly the configured default packs: "
                f"expected {sorted(metadata.default_pack_ids)}, got {sorted(active_pack_ids)}"
            )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"catalog load failed: {exc}")
        counts = {}
        entries = []

    ids: dict[str, str] = {}
    for entry in entries:
        record_id = str(entry.record.get("id") or "")
        if not record_id:
            errors.append(f"catalog record without id in {entry.kind}/{entry.category}")
            continue
        if record_id in ids:
            errors.append(f"duplicate catalog id {record_id}: {ids[record_id]} and {entry.kind}/{entry.category}")
        ids[record_id] = f"{entry.kind}/{entry.category}"

    species_ids = {
        str(entry.record.get("id") or "")
        for entry in entries
        if entry.kind == "module" and entry.category == "species"
    }
    scaffold_path = named_resource_path("species-scaffold-map", required=False)
    species_scaffold_report = {
        "ok": True,
        "declared": scaffold_path is not None,
        "species_records": len(species_ids),
        "mapped_records": 0,
        "fallback_records": 0,
        "errors": [],
    }
    if scaffold_path is not None:
        try:
            scaffold_data = json.loads(scaffold_path.read_text(encoding="utf-8"))
            mappings = scaffold_data.get("species_to_scaffold") or {}
            families = scaffold_data.get("families") or {}
            mapped_ids = set(map(str, mappings))
            scaffold_errors = validate_known_resource(
                "species-scaffold-map",
                scaffold_data,
            )
            missing = sorted(species_ids - mapped_ids)
            extra = sorted(mapped_ids - species_ids)
            if missing:
                scaffold_errors.append(f"missing species scaffold mappings: {missing}")
            if extra:
                scaffold_errors.append(f"unknown species scaffold mappings: {extra}")
            invalid_families = sorted(
                sid for sid, row in mappings.items()
                if not isinstance(row, dict) or row.get("scaffold_family") not in families
            )
            if invalid_families:
                scaffold_errors.append(f"invalid scaffold families: {invalid_families}")
            if scaffold_data.get("species_count") != len(species_ids):
                scaffold_errors.append("species scaffold species_count does not match the active catalog")
            species_scaffold_report = {
                "ok": not scaffold_errors,
                "declared": True,
                "species_records": len(species_ids),
                "mapped_records": len(mapped_ids),
                "fallback_records": sum(
                    1 for row in mappings.values()
                    if isinstance(row, dict)
                    and row.get("scaffold_family") == "direct-geometry-required"
                ),
                "errors": scaffold_errors,
            }
            if scaffold_errors:
                errors.append("species scaffold map validation failed")
        except Exception as exc:  # noqa: BLE001
            species_scaffold_report = {
                "ok": False,
                "declared": True,
                "species_records": len(species_ids),
                "mapped_records": 0,
                "fallback_records": 0,
                "errors": [str(exc)],
            }
            errors.append(f"species scaffold map validation failed: {exc}")

    scenes = [entry.record for entry in entries if entry.kind == "scene"]
    profiles = [entry.record for entry in entries if entry.kind == "profile"]
    style_families = [entry.record for entry in entries if entry.kind == "style-family"]
    recipes = [entry.record for entry in entries if entry.kind == "recipe"]
    scene_ids = {str(item.get("id")) for item in scenes}
    profile_ids = {str(item.get("id")) for item in profiles}
    style_family_ids = {str(item.get("id")) for item in style_families}
    for recipe in recipes:
        if str(recipe.get("base_scene_id")) not in scene_ids:
            errors.append(f"recipe references missing scene: {recipe.get('id')}")
        if str(recipe.get("render_profile_id")) not in profile_ids:
            errors.append(f"recipe references missing profile: {recipe.get('id')}")
    expected_style_domains = {"human", "anthropomorphic-animal", "animal", "creature", "hybrid", "robot"}
    for family in style_families:
        fid = str(family.get("id") or "")
        if str(family.get("base_render_profile_id") or "") not in profile_ids:
            errors.append(f"style family references missing base profile: {fid}")
        missing_profiles = sorted(
            str(value) for value in family.get("compatible_render_profile_ids", [])
            if str(value) not in profile_ids
        )
        if missing_profiles:
            errors.append(f"style family references missing compatible profiles: {fid}: {missing_profiles}")
        if set(family.get("domain_overlays", {})) != expected_style_domains:
            errors.append(f"style family domain overlays are incomplete: {fid}")

    try:
        manifest_verification = verify_release_manifest(
            root,
            metadata,
            entries,
            strict_release_tree=strict_release_tree,
        )
    except Exception as exc:  # noqa: BLE001
        manifest_verification = {
            "ok": False,
            "strict_release_tree": strict_release_tree,
            "errors": [str(exc)],
        }
    if not manifest_verification.get("ok"):
        errors.append("release MANIFEST verification failed")

    try:
        line_ending_verification = verify_release_line_endings(root, metadata)
    except Exception as exc:  # noqa: BLE001
        line_ending_verification = {"ok": False, "errors": [str(exc)]}
    if not line_ending_verification.get("ok"):
        errors.append("release line-ending normalization failed")

    defaults_path = named_resource_path("project-defaults")
    assert defaults_path is not None
    defaults = json.loads(defaults_path.read_text(encoding="utf-8"))
    for message in validate_known_resource("project-defaults", defaults):
        errors.append(f"selected project-defaults: {message}")
    if defaults.get("medium_policy", {}).get("single_medium_family_by_default") is not True:
        errors.append("single-medium policy is not enabled")
    if defaults.get("medium_policy", {}).get("hybrid_requires_explicit_request") is not True:
        errors.append("hybrid medium does not require an explicit request")

    negative_policy_path = named_resource_path("negative-policy")
    assert negative_policy_path is not None
    negative_policy = json.loads(negative_policy_path.read_text(encoding="utf-8"))
    for message in validate_known_resource("negative-policy", negative_policy):
        errors.append(f"selected negative-policy: {message}")
    if defaults.get("creative_policy", {}).get("art_direction_before_preset_search") is not True:
        errors.append("art direction is not configured before preset search")
    if defaults.get("creative_policy", {}).get("art_direction_contains_aesthetic_judgment") is not True:
        errors.append("art direction does not explicitly contain aesthetic judgment")
    expected_art_direction_fields = {
        "center_of_appeal", "viewer_or_environment_relationship",
        "composition_and_visual_hierarchy", "medium_family",
        "shape_and_rhythm", "surface_and_tactility",
        "color_and_light", "detail_hierarchy",
    }
    if set(defaults.get("art_direction_definition", {})) != expected_art_direction_fields:
        errors.append(
            "art-direction definition must cover the eight integrated visual decisions: "
            f"expected {sorted(expected_art_direction_fields)}, got "
            f"{sorted(defaults.get('art_direction_definition', {}))}"
        )
    if defaults.get("default_aesthetic_core") not in (None, ""):
        errors.append("project defaults must not force a universal aesthetic core")
    if defaults.get("default_style_family") not in (None, ""):
        errors.append("project defaults must not force a concrete style family")
    style_policy = defaults.get("style_family_policy", {})
    for key in (
        "style_family_is_optional_concrete_grammar",
        "selected_style_family_is_primary_visual_grammar",
        "linked_render_profile_supplies_medium_envelope_and_negative_boundary",
        "do_not_append_two_complete_grammars",
    ):
        if style_policy.get(key) is not True:
            errors.append(f"style-family policy is missing or disabled: {key}")
    expected_realization_domains = {
        "human", "anthropomorphic-animal", "animal",
        "creature", "hybrid", "robot",
    }
    realization_map = defaults.get("default_domain_realization_by_domain", {})
    if set(realization_map) != expected_realization_domains:
        errors.append(
            "default domain-realization map must cover the six subject domains: "
            f"expected {sorted(expected_realization_domains)}, got {sorted(realization_map)}"
        )
    default_profile_id = str(defaults.get("default_render_profile") or "")
    default_profile = next((item for item in profiles if item.get("id") == default_profile_id), None)
    if not default_profile:
        errors.append(f"default rendering profile does not exist: {default_profile_id}")
    elif default_profile.get("curation_status") != "curated" or not default_profile.get("medium_family"):
        errors.append(f"default rendering profile is not curated production knowledge: {default_profile_id}")

    payload_template = json.loads((root / "templates/generation-package-template.json").read_text(encoding="utf-8"))
    if payload_template.get("status") != "template":
        errors.append(
            "generation package skeleton status must be 'template'; only the builder may emit 'ready'"
        )
    creative_intent_template = payload_template.get("creative_intent", {})
    required_creative_intent_fields = {
        "image_promise", "chosen_direction", "medium_family",
        "purposeful_additions", "aesthetic_core", "style_family",
        "domain_realizations", "render_profile", "production_spec_sha256",
        "state_lineage_sha256", "selected_preset_ids",
    }
    if set(creative_intent_template) != required_creative_intent_fields:
        errors.append(
            "generation package creative_intent must use the current art-direction architecture: "
            f"expected {sorted(required_creative_intent_fields)}, got "
            f"{sorted(creative_intent_template)}"
        )
    if not isinstance(creative_intent_template.get("domain_realizations"), dict):
        errors.append("generation package domain_realizations must be an object keyed by subject domain")
    production_spec_template = json.loads((root / "templates/production-spec-template.json").read_text(encoding="utf-8"))
    distinctive_detail_template = json.loads((root / "templates/distinctive-detail-template.json").read_text(encoding="utf-8"))
    distinctive_detail_schema = json.loads((root / "schemas/distinctive-detail.schema.json").read_text(encoding="utf-8"))
    expected_detail_fields = {
        "id", "feature_type", "target_region", "laterality",
        "landmark_relation", "count_or_distribution", "relative_size",
        "shape_and_path", "orientation", "color_and_value", "depth_and_relief",
        "edge_and_texture", "surface_interaction", "age_or_condition",
        "visibility_and_occlusion", "identity_priority", "continuity_rules",
        "source_confidence",
    }
    if set(distinctive_detail_template) != expected_detail_fields:
        errors.append("distinctive-detail template fields are invalid")
    if set(distinctive_detail_schema.get("required", [])) != expected_detail_fields:
        errors.append("distinctive-detail schema required fields are invalid")

    performance_template = json.loads((root / "templates/performance-language-template.json").read_text(encoding="utf-8"))
    performance_schema = json.loads((root / "schemas/performance-language.schema.json").read_text(encoding="utf-8"))
    expected_performance_fields = {
        "felt_emotion", "displayed_emotion", "masked_or_conflicted_emotion",
        "intent", "viewer_or_partner_relationship", "intensity", "temporal_phase",
        "channel_cues", "interpretation_candidates", "selected_interpretation",
        "ambiguity_notes", "prompt_projection",
    }
    if set(performance_template) != expected_performance_fields:
        errors.append("performance-language template fields are invalid")
    if validate_against_schema(performance_template, performance_schema):
        errors.append("performance-language template does not validate against its schema")
    if not validate_against_schema("professional composure masking fear", performance_schema):
        errors.append("performance-language schema accepted a string instead of the current object contract")
    for invalid_performance in ({}, {"felt_emotion": []}, []):
        if not validate_against_schema(invalid_performance, performance_schema):
            errors.append(f"performance-language schema accepted invalid input: {invalid_performance!r}")

    performance_reference = (root / "references/performance-language-specification.md").read_text(encoding="utf-8")
    for marker in (
        "felt_emotion", "displayed_emotion", "masked_or_conflicted_emotion",
        "tongue display", "bilateral cheek blush", "tail flick", "whiskers",
        "optics", "manipulators", "ventilation", "alternate readings",
    ):
        if marker not in performance_reference:
            errors.append(f"performance-language specification is missing required marker: {marker}")

    search_source = (root / "scripts/search_discovery.py").read_text(encoding="utf-8")
    if '"body-language-cue": "performance"' not in search_source:
        errors.append("search discovery does not route body-language-cue records to performance")

    structural_contracts = [
        ("camera-framing", "templates/camera-framing-contract-template.json", "schemas/camera-framing-contract.schema.json"),
        ("garment-geometry", "templates/garment-geometry-template.json", "schemas/garment-geometry.schema.json"),
        ("terminal-growth", "templates/terminal-growth-contract-template.json", "schemas/terminal-growth-contract.schema.json"),
        ("growth-geometry", "templates/growth-geometry-template.json", "schemas/growth-geometry.schema.json"),
    ]
    for label, template_rel, schema_rel in structural_contracts:
        template_value = json.loads((root / template_rel).read_text(encoding="utf-8"))
        schema_value = json.loads((root / schema_rel).read_text(encoding="utf-8"))
        contract_errors = validate_against_schema(template_value, schema_value)
        if contract_errors:
            errors.append(f"{label} template fails schema validation: {contract_errors[:3]}")
        unsupported = unsupported_schema_keywords(schema_value)
        if unsupported:
            errors.append(f"{label} schema uses unsupported keywords: {unsupported}")

    required_spec_fields = {
        "source_brief", "target_model", "creative_latitude",
        "image_promise", "art_direction", "state_context", "subjects", "scene", "camera",
        "lighting", "visual_language", "constraints", "selected_preset_ids", "render_intent",
    }
    if set(production_spec_template) != required_spec_fields:
        errors.append(
            "production-spec template top-level fields are invalid: "
            f"expected {sorted(required_spec_fields)}, got {sorted(production_spec_template)}"
        )
    visual_language = production_spec_template.get("visual_language", {})
    expected_visual_language = {
        "aesthetic_core", "style_family", "domain_realizations",
        "render_profile", "aesthetic_touches",
    }
    if set(visual_language) != expected_visual_language:
        errors.append("production-spec visual_language fields are invalid")
    production_schema = json.loads((root / "schemas/production-spec.schema.json").read_text(encoding="utf-8"))
    subject_required = set(production_schema.get("properties", {}).get("subjects", {}).get("items", {}).get("required", []))
    subject_properties = production_schema.get("properties", {}).get("subjects", {}).get("items", {}).get("properties", {})
    if subject_properties.get("growth_geometry", {}).get("$ref") != "growth-geometry.schema.json":
        errors.append("production-spec subjects.growth_geometry must reference growth-geometry.schema.json")
    garment_items = subject_properties.get("garment_geometry", {}).get("items", {})
    if garment_items.get("$ref") != "garment-geometry.schema.json":
        errors.append("production-spec subjects.garment_geometry must reference garment-geometry.schema.json")
    if production_schema.get("properties", {}).get("camera", {}).get("$ref") != "camera-framing-contract.schema.json":
        errors.append("production-spec camera must reference camera-framing-contract.schema.json")

    if "distinctive_details" not in subject_required:
        errors.append("production-spec subjects must require distinctive_details")
    if "current_state" not in subject_required:
        errors.append("production-spec subjects must require current_state")
    performance_contract = production_schema.get("properties", {}).get("subjects", {}).get("items", {}).get("properties", {}).get("performance", {})
    if performance_contract.get("$ref") != "performance-language.schema.json":
        errors.append("production-spec subjects.performance must reference performance-language.schema.json")
    identity_schema = json.loads((root / "schemas/character-identity-contract.schema.json").read_text(encoding="utf-8"))
    stable_identity = identity_schema.get("properties", {}).get("stable_identity", {})
    if "growth_geometry" not in set(stable_identity.get("required", [])):
        errors.append("character identity stable_identity must require growth_geometry")
    if stable_identity.get("properties", {}).get("growth_geometry", {}).get("$ref") != "growth-geometry.schema.json":
        errors.append("character identity stable_identity.growth_geometry must reference growth-geometry.schema.json")

    projection_schema = json.loads((root / "schemas/visual-state-projection.schema.json").read_text(encoding="utf-8"))
    projection_performance = projection_schema.get("properties", {}).get("performance_language", {})
    if projection_performance.get("$ref") != "performance-language.schema.json":
        errors.append("visual-state-projection performance_language must reference performance-language.schema.json")
    state_context_required = set(production_schema.get("properties", {}).get("state_context", {}).get("required", []))
    if state_context_required != {"mode"}:
        errors.append("production-spec state_context required fields are invalid")
    if "production_spec" not in payload_template or "production_spec_sha256" not in payload_template:
        errors.append("generation package template is missing production-specification traceability")
    if "production_spec_sha256" not in payload_template.get("generation_contract", {}):
        errors.append("generation contract is missing production_spec_sha256")
    for field in (
        "state_lineage",
        "state_lineage_sha256",
        "prepared_reference_set",
        "prepared_reference_set_sha256",
        "generation_input_sha256",
    ):
        if field not in payload_template:
            errors.append(f"generation package template is missing {field}")
    for field in (
        "state_lineage_sha256",
        "prepared_reference_set_sha256",
        "generation_input_sha256",
    ):
        if field not in payload_template.get("generation_contract", {}):
            errors.append(f"generation contract is missing {field}")
    lineage_template = payload_template.get("state_lineage", {})
    if lineage_template.get("artifact_type") != "state-lineage":
        errors.append("generation package template must embed a state-lineage artifact")

    generation_payload_template = payload_template.get("generation_payload", {})
    transport = generation_payload_template.get("negative_transport", {})
    if transport.get("mode") not in {"separate-field", "integrated-critical", "native-subset", "retained-only"}:
        errors.append("generation package template has invalid negative transport mode")
    contract_template = payload_template.get("generation_contract", {})
    from verify_generation_payload import GENERATION_CONTRACT_FIELDS
    expected_generation_contract_fields = GENERATION_CONTRACT_FIELDS
    if set(contract_template) != expected_generation_contract_fields:
        errors.append(
            "generation package template generation_contract fields are invalid: "
            f"expected {sorted(expected_generation_contract_fields)}, "
            f"got {sorted(contract_template)}"
        )
    for field in (
        "forward_verified_prompt_transport",
        "forward_verified_negative_transport",
        "forward_ordered_reference_transports",
        "do_not_reconstruct_from_chat",
    ):
        if contract_template.get(field) is not True:
            errors.append(
                f"generation package template generation_contract.{field} must be true"
            )
    transports = generation_payload_template.get("transports")
    if not isinstance(transports, dict):
        errors.append("generation package template is missing transport structure")
    else:
        expected_transport_keys = {"separate", "integrated", "native_subset", "paste_instructions"}
        if set(transports) != expected_transport_keys:
            errors.append("generation package template transport fields are invalid")
        separate = transports.get("separate", {})
        integrated = transports.get("integrated", {})
        native = transports.get("native_subset", {})
        if separate.get("channel") != "prompt_plus_negative_fields":
            errors.append("generation package template separate transport channel is invalid")
        if integrated.get("channel") != "single_prompt_field":
            errors.append("generation package template integrated transport channel is invalid")
        if native.get("channel") != "prompt_plus_native_negative":
            errors.append("generation package template native-subset channel is invalid")
    provenance = generation_payload_template.get("negative_provenance")
    if not isinstance(provenance, dict):
        errors.append("generation package template is missing negative_provenance")
    else:
        for key in ("activated_sources", "diagnostic_sources_retained", "semantic_exclusions_user_supplied"):
            if not isinstance(provenance.get(key), list):
                errors.append(f"generation package template negative_provenance.{key} must be a list")
        if not isinstance(provenance.get("affirmative_translations"), dict):
            errors.append("generation package template negative_provenance.affirmative_translations must be an object")

    state_protocol = validate_state_protocol(root)
    if not state_protocol.get("ok"):
        errors.append("Shared State Protocol validation failed")

    protocol_sync = subprocess.run(
        [sys.executable, "scripts/validate_integration.py"],
        cwd=root, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True, encoding="utf-8", stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if protocol_sync.returncode != 0:
        errors.append("Local integration capability validation failed")

    # A pack that owns a reference corpus is validated through its active named
    # resources. Core releases without such a pack remain valid.
    reference_corpus = validate_reference_corpus(None, require_bundles=None)
    if not reference_corpus.get("ok"):
        errors.append("Reference corpus disposition and visual-evidence validation failed")

    handoff_errors: list[str] = []
    check_carried_implementation(root, "references/narrative-protocol.md", errors)
    check_contract_document(root, "references/narrative-protocol.md", errors)
    # Every refusal a carried reader can make is named by a case in the suite
    # that exercises it, so deleting the refusal turns that case red.
    refusal_coverage.check(root, [
        ("scripts/narrative.py",
         ["scripts/narrative_contract_smoke_test.py", "scripts/narrative_authoring_smoke_test.py"]),
        ("scripts/scene_plot.py", ["scripts/scene_plot_contract_smoke_test.py"]),
    ], errors)
    # The corpus the contract publishes is what those suites' case tables
    # assert, and the readers here reach every verdict in it.
    narrative_corpus.check(root, errors)
    check_declared_enumerations(root, errors)
    check_model_record_keys(root, errors)

    handoff_template_path = root / "templates/handoff/shot-request.template.json"
    try:
        handoff_template = json.loads(handoff_template_path.read_text(encoding="utf-8"))
        handoff_errors.extend(validate_shot_request(handoff_template, allow_placeholder_hash=True))
    except Exception as exc:  # noqa: BLE001
        handoff_errors.append(f"shot-request handoff validation failed: {exc}")
    shot_binding_regression = state_protocol.get("shot_binding_regression") or {
        "ok": False,
        "checks": 0,
        "checked_bindings": [],
        "errors": ["the state protocol report omitted the real shot binding regression"],
    }
    if not shot_binding_regression.get("ok"):
        handoff_errors.extend(
            str(message) for message in shot_binding_regression.get("errors", [])
        )
    if handoff_errors:
        errors.append("shot-request handoff validation failed")

    if not package_structural_only:
        from default_release_smoke_test import evaluate_default_release

        default_release_regression = evaluate_default_release(root)
        if not default_release_regression.get("ok"):
            errors.append("default-pack positive release regression failed")
    else:
        default_release_regression = {
            "ok": None,
            "total_cases": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "details": [],
            "errors": [],
            "not_run": True,
            "reason": "the release packager runs the default-pack regression as a separate gate",
        }

    measured = [
        path for path in files
        if path.name not in GENERATED_RELEASE_ARTIFACT_NAMES
    ]
    report = {
        "package": PACKAGE_NAME,


        "license": LICENSE_ID,
        "ok": not errors,
        "validation_scope": (
            "explicit release inventory, full MANIFEST integrity, LF-normalized release inventory, "
            "lean SKILL router and authoritative documentation routing, "
            "product-release identity, versionless internal artifacts, "
            "default-pack catalog integrity and activation isolation, direct canonical-ID integrity, Shared State Protocol schemas and lineage, "
            "shot-request handoff, pack-declared reference-corpus disposition and full declared-bundle validation, "
            "default-pack positive retrieval regression, exact payload transport, "
            + (
                "and package-delegated exact dependency and production visual gates; "
                if package_structural_only
                else "exact tested dependencies, and the production visual-evidence workflow; "
            )
            + "this report does "
            "not claim artistic-quality validation"
        ),
        "version_observed": version_observed,
        "documentation_observed": documentation_observed,
        "counts": counts,
        "dependencies": dependency_report,
        "visual_evidence_smoke": visual_evidence_smoke,
        "reference_runtime_smoke": reference_runtime_smoke,
        "nondefault_pack_isolation_smoke": nondefault_pack_isolation_smoke,
        "preset_maintenance_smoke": preset_maintenance_smoke,
        "feature_workflow_smoke": feature_workflow_smoke,
        "structure_neutrality_smoke": structure_neutrality_smoke,
        "release_manifest": manifest_verification,
        "release_line_endings": line_ending_verification,
        "species_scaffold_map": species_scaffold_report,
        "default_release_regression": default_release_regression,
        "state_protocol": {
            "ok": state_protocol.get("ok"),
            "artifact_schema_count": state_protocol.get("artifact_schema_count"),
            "state_template_count": state_protocol.get("state_template_count"),
            "auxiliary_contracts_validated": state_protocol.get(
                "auxiliary_contracts_validated", []
            ),
            "distinctive_detail_observation_contract": state_protocol.get(
                "distinctive_detail_observation_contract", {}
            ),
            "default_only_example_resolution": state_protocol.get(
                "default_only_example_resolution", {}
            ),
            "errors": state_protocol.get("errors", []),
            "warnings": state_protocol.get("warnings", []),
        },
        "shot_handoff": {
            "ok": not handoff_errors,
            "errors": handoff_errors,
        },
        "shot_binding_regression": shot_binding_regression,
        "reference_corpus": {
            "ok": reference_corpus.get("ok"),
            "errors": reference_corpus.get("errors", []),
            "warnings": reference_corpus.get("warnings", []),
            "stats": reference_corpus.get("stats", {}),
        },
        "default_packs": [
            row for row in workspace_pack_validation
            if row.get("pack_id") in set(metadata.default_pack_ids)
        ],
        "release_packs": workspace_pack_validation,
        "package_structural_only": package_structural_only,
        "files": len(files),
        "bytes_excluding_manifest_and_report": sum(path.stat().st_size for path in measured),
        "errors": errors,
        "warnings": warnings,
        "hashes": {
            path.relative_to(root).as_posix(): sha256_file(path)
            for path in (
                root / "SKILL.md",
                root / "README.md",
                root / "scripts" / "catalog_cli.py",
                root / "scripts" / "catalog_html.py",
                root / "scripts" / "catalog_html_smoke_test.py",
                root / "scripts" / "build_generation_payload.py",
                root / "scripts" / "verify_generation_payload.py",
                root / "config" / "default-pack-state.json",
                root / "schemas" / "pack.schema.json",
                root / "schemas" / "pack-record-file.schema.json",
                root / "scripts" / "pack_manager.py",
                root / "scripts" / "pack_cache.py",
                root / "schemas" / "catalog-query.schema.json",
                root / "templates" / "catalog-query-template.json",
                root / "schemas" / "viewpoint" / "shot-request.schema.json",
                root / "templates" / "handoff" / "shot-request.template.json",
                root / "scripts" / "shot_request.py",
                root / "scripts" / "shot_request_smoke_test.py",
            )
            if path.is_file()
        },
    }
    if write_report:
        (root / "validation-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    configure_pack_runtime(None)
    if validation_runtime is not None:
        validation_runtime.cleanup()
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--report-out", help="Optional external JSON report path")
    parser.add_argument("--state-file", type=Path, help="Explicit validation pack-state path")
    parser.add_argument("--cache-dir", type=Path, help="Explicit validation cache directory")
    parser.add_argument("--managed-root", type=Path, help="Explicit validation managed-pack directory")
    parser.add_argument(
        "--strict-release-tree",
        action="store_true",
        help="Require the complete tree to equal the declared release inventory plus MANIFEST.json.",
    )
    parser.add_argument(
        "--package-structural-only",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    runtime_values = (args.state_file, args.cache_dir, args.managed_root)
    if any(value is not None for value in runtime_values) and not all(
        value is not None for value in runtime_values
    ):
        parser.error("--state-file, --cache-dir, and --managed-root must be supplied together")
    report = validate(
        Path(args.root).resolve(),
        write_report=False,
        package_structural_only=args.package_structural_only,
        state_file=args.state_file,
        cache_dir=args.cache_dir,
        managed_root=args.managed_root,
        strict_release_tree=args.strict_release_tree,
    )
    if args.report_out:
        Path(args.report_out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
