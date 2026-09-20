#!/usr/bin/env python3
"""Exercise split catalog generation, local SVG links, and direct-open index."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import shutil
import tempfile
from contextlib import redirect_stdout
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from unittest import mock
from urllib.parse import unquote, urlparse

from catalog_html import (
    RecordView,
    _record_page_relative,
    _safe_resource_path,
    discover_pack_tree,
    load_explicit_settings,
    load_explicit_state,
    load_pack_directories,
    main as catalog_html_main,
    write_catalog_directory,
)
from pack_manager import PackError, atomic_write_json
from validate_catalog_site import run as validate_site, search_thumbnail_region_ok

PACK_ID = "018f0000-0000-7000-8000-000000000001"
REPLACEMENT_PACK_ID = "018f0000-0000-7000-8000-000000000002"
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class Structure(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []
        self.images: list[str] = []
        self.scripts: list[str] = []
        self.stylesheets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if values.get("href"):
            self.hrefs.append(values["href"])
        if tag == "img" and values.get("src"):
            self.images.append(values["src"])
        if tag == "script" and values.get("src"):
            self.scripts.append(values["src"])
        if tag == "link" and values.get("rel") == "stylesheet" and values.get("href"):
            self.stylesheets.append(values["href"])


def fixture(pack: Path) -> None:
    atomic_write_json(
        pack / "pack.json",
        {
            "pack_id": PACK_ID,
            "name": "Catalog HTML Fixture",
            "description": "Temporary split-catalog fixture.",
            "release": "2026.08.15.1",
            "content": {
                "record_globs": ["records/**/*.json"],
                "resource_globs": ["resources/**/*"],
                "resource_bindings": {},
            },
            "capabilities": ["scene-records", "searchable-assets", "evidence-artifact-reference"],
            "dependencies": [],
            "optional_dependencies": [],
            "replaces": [],
            "license": "GPL-3.0-only",
        },
    )
    atomic_write_json(
        pack / "records" / "scene.json",
        {
            "kind": "scene",
            "records": [
                {
                    "id": "fixture-canonical-scene",
                    "label": "Fixture canonical scene",
                    "description": (
                        "Reference delivered as a local file:// URI under /mnt/data "
                        "by the requesting tool."
                    ),
                    "category": "portrait",
                    "domain": "anthropomorphic-animal",
                    "family": "fixture-family",
                    "variant": "night-variant",
                    "aliases": ["fixture alias", "</option><script>fixture-injection</script>"],
                    "outcome": "Never summarize this Ω outcome.",
                    "defaults": {"lighting": "cyan rim"},
                    "tags": ["fixture", "portrait"],
                    "search_terms": [
                        {
                            "phrase": "fixture canonical scene",
                            "facet": "scene",
                            "weight": 1.0,
                            "source": "label",
                        }
                    ],
                    "search_profile": {
                        "aliases": ["profile alias"],
                        "discovery_group": "fixture-discovery-group",
                        "facets": {"lighting": ["cyan rim"]},
                    },
                },
                {
                    "id": "fixture-unlinked-scene",
                    "label": "Fixture scene without Visual Evidence",
                    "category": "portrait",
                    "domain": "anthropomorphic-animal",
                    "family": "fixture-family",
                    "variant": "unlinked-variant",
                    "defaults": {"lighting": "soft daylight"},
                    "tags": ["fixture", "unlinked"],
                    "search_terms": [
                        {
                            "phrase": "fixture scene without visual evidence",
                            "facet": "scene",
                            "weight": 1.0,
                            "source": "label",
                        }
                    ],
                },
            ],
        },
    )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">'
        '<rect width="20" height="20" fill="#22bbdd"/></svg>\n'
    )
    svg_path = pack / "resources" / "fixture.svg"
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path.write_text(svg, encoding="utf-8", newline="\n")
    thumb_path = pack / "resources" / "thumbnail.png"
    thumb_path.write_bytes(PNG_1X1)
    authority_path = pack / "resources" / "authority.json"
    atomic_write_json(authority_path, {"authority": "fixture"})
    unicode_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        '<rect width="24" height="24" fill="#dd8822"/></svg>\n'
    )
    unicode_path = pack / "resources" / "fixture thumb 테스트.svg"
    unicode_path.write_text(unicode_svg, encoding="utf-8", newline="\n")
    svg_sha = hashlib.sha256(svg_path.read_bytes()).hexdigest()
    thumb_sha = hashlib.sha256(thumb_path.read_bytes()).hexdigest()
    authority_sha = hashlib.sha256(authority_path.read_bytes()).hexdigest()
    unicode_sha = hashlib.sha256(unicode_path.read_bytes()).hexdigest()
    atomic_write_json(
        pack / "records" / "assets.json",
        {
            "kind": "asset",
            "category": "visual-evidence",
            "records": [
                {
                    "id": "fixture-visual-evidence",
                    "label": "Fixture Visual Evidence record",
                    "category": "visual-evidence",
                    "asset_type": "evidence-artifact-reference",
                    "description": "Visual Evidence for the fixture canonical record.",
                    "source_ref_id": "fixture-visual-evidence-source",
                    "source_sha256": svg_sha,
                    "source_media_type": "image/svg+xml",
                    "source_dimensions": {"width": 20, "height": 20},
                    "disposition": "fixture-evidence",
                    "evidence_relation": "direct-fixture-reference",
                    "canonical_record_ids": ["fixture-canonical-scene"],
                    "primary_resource": "resources/fixture.svg",
                    "resource_refs": ["resources/fixture.svg"],
                    "tags": ["fixture", "Visual Evidence reference"],
                    "artifacts": [
                        {
                            "artifact_id": "fixture-vector",
                            "role": "faithful-archival-vector",
                            "path": "resources/fixture.svg",
                            "media_type": "image/svg+xml",
                            "sha256": svg_sha,
                        }
                    ],
                },
                {
                    "id": "fixture-thumbnail-asset",
                    "label": "Fixture thumbnail asset",
                    "category": "visual-evidence",
                    "asset_type": "thumbnail-reference",
                    "description": "Thumbnail evidence for the fixture canonical record.",
                    "source_ref_id": "fixture-thumbnail-source",
                    "source_sha256": thumb_sha,
                    "source_media_type": "image/png",
                    "source_dimensions": {"width": 1, "height": 1},
                    "disposition": "fixture-evidence",
                    "evidence_relation": "direct-fixture-reference",
                    "canonical_record_ids": ["fixture-canonical-scene"],
                    "canonical_record_refs": ["fixture-canonical-scene"],
                    "primary_resource": "resources/authority.json",
                    "resource_refs": ["resources/authority.json", "resources/thumbnail.png"],
                    "tags": ["fixture", "thumbnail"],
                    "artifacts": [
                        {
                            "artifact_id": "fixture-authority",
                            "role": "visual-authority",
                            "path": "resources/authority.json",
                            "media_type": "application/json",
                            "sha256": authority_sha,
                        },
                        {
                            "artifact_id": "fixture-thumbnail",
                            "role": "thumbnail",
                            "path": "resources/thumbnail.png",
                            "media_type": "image/png",
                            "sha256": thumb_sha,
                        },
                    ],
                },
                {
                    "id": "fixture-unicode-asset",
                    "label": "Fixture asset with an encoded resource name",
                    "category": "visual-evidence",
                    "asset_type": "evidence-artifact-reference",
                    "description": "Visual Evidence whose resource name needs URL encoding.",
                    "source_ref_id": "fixture-unicode-source",
                    "source_sha256": unicode_sha,
                    "source_media_type": "image/svg+xml",
                    "source_dimensions": {"width": 24, "height": 24},
                    "disposition": "fixture-evidence",
                    "evidence_relation": "direct-fixture-reference",
                    "canonical_record_ids": ["fixture-canonical-scene"],
                    "primary_resource": "resources/fixture thumb 테스트.svg",
                    "resource_refs": ["resources/fixture thumb 테스트.svg"],
                    "tags": ["fixture", "unicode"],
                    "artifacts": [
                        {
                            "artifact_id": "fixture-unicode-vector",
                            "role": "faithful-archival-vector",
                            "path": "resources/fixture thumb 테스트.svg",
                            "media_type": "image/svg+xml",
                            "sha256": unicode_sha,
                        }
                    ],
                },
            ],
        },
    )


def replacement_fixture(pack: Path) -> None:
    atomic_write_json(
        pack / "pack.json",
        {
            "pack_id": REPLACEMENT_PACK_ID,
            "name": "Catalog HTML Replacement Fixture",
            "release": "2026.08.15.1",
            "content": {
                "record_globs": ["records/**/*.json"],
                "resource_globs": [],
                "resource_bindings": {},
            },
            "capabilities": ["scene-records"],
            "dependencies": [],
            "optional_dependencies": [],
            "replaces": [{"record_id": "fixture-canonical-scene", "from_pack": PACK_ID}],
            "license": "GPL-3.0-only",
        },
    )
    atomic_write_json(
        pack / "records" / "scene.json",
        {
            "kind": "scene",
            "records": [
                {
                    "id": "fixture-canonical-scene",
                    "label": "Replacement fixture canonical scene",
                    "domain": "anthropomorphic-animal",
                    "defaults": {"lighting": "warm rim"},
                    "tags": ["fixture", "replacement"],
                    "search_terms": [
                        {
                            "phrase": "replacement fixture canonical scene",
                            "facet": "scene",
                            "weight": 1.0,
                            "source": "label",
                        }
                    ],
                }
            ],
        },
    )


def inventory(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def parse_index(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    prefix = "window.CPB_CATALOG_INDEX="
    return json.loads(text[len(prefix):].rstrip()[:-1])


def resolve_local(page: Path, href: str) -> Path:
    parsed = urlparse(href)
    if parsed.scheme:
        raise ValueError(f"expected relative link, got {href}")
    return (page.parent / unquote(parsed.path)).resolve()


def view_by_id(packs, record_id: str) -> RecordView:
    for pack in packs:
        for source in pack.validation.records:
            if source.record.get("id") == record_id:
                return RecordView(pack, source)
    raise KeyError(record_id)



def run() -> dict[str, Any]:
    checks = 0
    errors: list[str] = []
    try:
        with tempfile.TemporaryDirectory(prefix="cpb-catalog-html-") as temp:
            # resolve_local() resolves every link it reads back, so the fixture
            # root must be resolved too. A TEMP reaching the process through a
            # link or an 8.3 short name - the GitHub Windows runner exposes both
            # - would otherwise fail the portable-copy containment check.
            root = Path(temp).resolve()
            pack_parent = root / "packs"
            pack = pack_parent / "fixture"
            fixture(pack)
            before = inventory(pack)
            packs = load_pack_directories([pack])
            if [item.pack_id for item in packs] == [PACK_ID]:
                checks += 1
            else:
                errors.append("explicit pack loading failed")

            unsafe_ok = True
            for value in ("../escape.svg", "/absolute.svg", "resources\\escape.svg"):
                try:
                    _safe_resource_path(packs[0], value)
                except PackError:
                    continue
                unsafe_ok = False
            if unsafe_ok:
                checks += 1
            else:
                errors.append("unsafe pack resource path was accepted")

            outside = root / "outside.svg"
            outside.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>\n', encoding="utf-8")
            link = pack / "resources" / "escape.svg"
            try:
                link.symlink_to(outside)
                packs[0].validation.resource_files.append("resources/escape.svg")
                try:
                    _safe_resource_path(packs[0], "resources/escape.svg")
                except PackError:
                    checks += 1
                else:
                    errors.append("resource resolver followed an escaping symlink")
            finally:
                packs[0].validation.resource_files.remove("resources/escape.svg")
                link.unlink(missing_ok=True)
                outside.unlink(missing_ok=True)

            try:
                write_catalog_directory(packs, pack / "catalog")
            except PackError:
                checks += 1
            else:
                errors.append("catalog wrote inside a source pack")

            output = root / "catalog"
            report = write_catalog_directory(packs, output)
            if (
                report.get("record_count") == 5
                and report.get("asset_record_count") == 3
                and report.get("canonical_records_with_assets") == 1
                and report.get("canonical_asset_link_count") == 3
                and report.get("visual_gallery_page_count") == 1
                and report.get("linked_preset_gallery_page_count") == 1
            ):
                checks += 1
            else:
                errors.append(f"catalog report mismatch: {report}")

            index = output / "index.html"
            index_text = index.read_text(encoding="utf-8")
            index_structure = StructureWithFeed(index_text)
            if (
                index.stat().st_size < 100_000
                and not index_structure.scripts
                and "visual-evidence/index.html" in index_structure.hrefs
                and "linked-presets/index.html" in index_structure.hrefs
                and "search.html" in index_structure.hrefs
                and "Never summarize this Ω outcome." not in index_text
                and "Browse Visual Evidence" in index_text
                and "Browse presets with Visual Evidence" in index_text
            ):
                checks += 1
            else:
                errors.append("direct-open home is not a small static discovery page")

            search_page = output / "search.html"
            search_text = search_page.read_text(encoding="utf-8")
            search_structure = StructureWithFeed(search_text)
            catalog_css = (output / "assets" / "catalog.css").read_text(encoding="utf-8")
            catalog_js = (output / "assets" / "catalog.js").read_text(encoding="utf-8")
            if (
                search_structure.scripts == ["data/catalog-index.js", "assets/catalog.js"]
                and search_structure.stylesheets == ["assets/catalog.css"]
                and "Presets with linked Visual Evidence (1)" in search_text
                and "Presets without linked Visual Evidence (1)" in search_text
                and "Visual Evidence records (3)" in search_text
                and ".result-card.has-thumbnail{grid-template-columns:minmax(0,1fr) minmax(112px,160px)}" in catalog_css
                and ".result-copy{" in catalog_css
                and ".result-thumbnail{" in catalog_css
                and catalog_js.find("card.appendChild(copy);") < catalog_js.find("card.appendChild(imageLink);")
                and "image.width = 160;" in catalog_js
                and "image.height = 136;" in catalog_js
            ):
                checks += 1
            else:
                errors.append("search page or evidence filter counts are incorrect")

            if (
                search_thumbnail_region_ok(catalog_css, catalog_js)
                and not search_thumbnail_region_ok(
                    catalog_css,
                    catalog_js.replace("card.appendChild(copy);", ""),
                )
            ):
                checks += 1
            else:
                errors.append("thumbnail-region validation accepted a missing copy region")

            pack_page = output / "packs" / f"{PACK_ID}.html"
            pack_page_text = pack_page.read_text(encoding="utf-8")
            if (
                "Source pack" in pack_page_text
                and "packs/fixture" in pack_page_text
                and "Browse record kinds" in pack_page_text
                and str(pack.resolve()) not in pack_page_text
                and "/mnt/data" not in pack_page_text
            ):
                checks += 1
            else:
                errors.append("pack summary leaked a path or lacks browse entry points")

            index_data = parse_index(output / "data" / "catalog-index.js")
            scene_entry = next(item for item in index_data["records"] if item["id"] == "fixture-canonical-scene")
            asset_entries = [item for item in index_data["records"] if item["is_asset"]]
            if (
                len(index_data["records"]) == 5
                and scene_entry["linked_asset_count"] == 3
                and scene_entry["thumbnail"]
                and len(asset_entries) == 3
                and all(item["linked_preset_count"] == 1 for item in asset_entries)
            ):
                checks += 1
            else:
                errors.append("compact search index lost link counts or thumbnails")

            all_index_resources = [
                output / item["page"]
                for item in index_data["records"]
            ] + [
                resolve_local(output / "search.html", item["thumbnail"])
                for item in index_data["records"]
                if item.get("thumbnail")
            ]
            if all(path.is_file() for path in all_index_resources):
                checks += 1
            else:
                errors.append("compact search index contains broken page or thumbnail links")

            site_report = validate_site(output)
            if site_report.get("ok") is True and site_report.get("errors") == []:
                checks += 1
            else:
                errors.append(f"generated catalog failed site validation: {site_report.get('errors')}")

            html_leak = root / "leak-html"
            shutil.copytree(output, html_leak)
            leak_page = html_leak / scene_entry["page"]
            leak_page.write_text(
                leak_page.read_text(encoding="utf-8").replace(
                    "</main>",
                    '<img src="file:///C:/mnt/data/leak.svg" alt="x"></main>',
                    1,
                ),
                encoding="utf-8",
                newline="\n",
            )
            html_leak_report = validate_site(html_leak)

            home_leak = root / "leak-home"
            shutil.copytree(output, home_leak)
            home_leak_page = home_leak / "index.html"
            home_leak_page.write_text(
                home_leak_page.read_text(encoding="utf-8").replace(
                    "</main>",
                    '<a href="/mnt/data/pack/x.svg">x</a></main>',
                    1,
                ),
                encoding="utf-8",
                newline="\n",
            )
            home_leak_report = validate_site(home_leak)

            index_leak = root / "leak-index"
            shutil.copytree(output, index_leak)
            index_leak_js = index_leak / "data" / "catalog-index.js"
            index_leak_js.write_text(
                index_leak_js.read_text(encoding="utf-8").replace(
                    '"thumbnail":"',
                    '"thumbnail":"file:///C:/packs/x.svg","_old":"',
                    1,
                ),
                encoding="utf-8",
                newline="\n",
            )
            index_leak_report = validate_site(index_leak)

            if (
                html_leak_report.get("ok") is False
                and any(
                    "absolute workspace paths leaked into HTML" in item
                    for item in html_leak_report["errors"]
                )
                and home_leak_report.get("ok") is False
                and any(
                    "absolute workspace paths leaked into HTML" in item
                    for item in home_leak_report["errors"]
                )
                and index_leak_report.get("ok") is False
                and any(
                    "absolute workspace paths leaked into the compact index" in item
                    for item in index_leak_report["errors"]
                )
            ):
                checks += 1
            else:
                errors.append("absolute workspace link detection missed an emitted link")

            scene_view = view_by_id(packs, "fixture-canonical-scene")
            scene_page = output / _record_page_relative(scene_view)
            scene_text = scene_page.read_text(encoding="utf-8")
            required = (
                "Linked Visual Evidence (3)",
                "fixture-visual-evidence",
                "fixture-thumbnail-asset",
                "fixture-unicode-asset",
                "resources/fixture.svg",
                "resources/thumbnail.png",
                "Never summarize this Ω outcome.",
                "Visual Evidence",
            )
            unlinked_view = view_by_id(packs, "fixture-unlinked-scene")
            unlinked_page = output / _record_page_relative(unlinked_view)
            unlinked_text = unlinked_page.read_text(encoding="utf-8")
            if (
                all(value in scene_text for value in required)
                and unlinked_text.count("No Visual Evidence is linked to this record.") == 1
                and "failed lookup" not in unlinked_text
                and "validated asset declaration" not in unlinked_text
                and "Browse the presets" not in unlinked_text
            ):
                checks += 1
            else:
                errors.append("preset detail pages lost linked evidence or the direct unlinked-state message")

            scene_structure = StructureWithFeed(scene_text)
            resolved = [resolve_local(scene_page, value) for value in scene_structure.images]
            if resolved and all(path.is_file() for path in resolved) and not any("file:" in value for value in scene_structure.images):
                checks += 1
            else:
                errors.append("linked evidence previews are not resolvable relative files")

            asset_view = view_by_id(packs, "fixture-visual-evidence")
            asset_page = output / _record_page_relative(asset_view)
            asset_text = asset_page.read_text(encoding="utf-8")
            if "fixture-canonical-scene" in asset_text and any("fixture-canonical-scene.html" in href for href in StructureWithFeed(asset_text).hrefs):
                checks += 1
            else:
                errors.append("asset detail lacks navigation to its canonical preset")

            asset_map = json.loads((output / "data" / "record-asset-map.json").read_text(encoding="utf-8"))
            mapped = asset_map["records"][f"{PACK_ID}:fixture-canonical-scene"]
            reverse = asset_map["assets"][f"{PACK_ID}:fixture-visual-evidence"]
            roles = [artifact.get("role") for asset in mapped["assets"] for artifact in asset.get("svg_artifacts", [])]
            if (
                len(mapped["assets"]) == 3
                and "faithful-archival-vector" in roles
                and reverse["linked_records"][0]["record_id"] == "fixture-canonical-scene"
                and asset_map["summary"]["canonical_records_with_assets"] == 1
                and asset_map["summary"]["asset_records_with_canonical_links"] == 3
                and asset_map["summary"]["canonical_asset_link_count"] == 3
                and not asset_map["unresolved"]
            ):
                checks += 1
            else:
                errors.append("forward or reverse record-to-evidence map is incomplete")

            visual_page = output / "visual-evidence" / "index.html"
            visual_text = visual_page.read_text(encoding="utf-8")
            visual_structure = StructureWithFeed(visual_text)
            if (
                visual_text.count('<article class="gallery-card">') == 3
                and visual_structure.images
                and any("fixture-canonical-scene.html" in href for href in visual_structure.hrefs)
                and "faithful-archival-vector" in visual_text
                and "Visual Evidence gallery" in visual_text
                and "Evidence artifacts" in visual_text
                and "<h3>SVG artifacts</h3>" not in visual_text
                and all(resolve_local(visual_page, src).is_file() for src in visual_structure.images)
            ):
                checks += 1
            else:
                errors.append("visual evidence gallery lacks thumbnails or preset navigation")

            linked_page = output / "linked-presets" / "index.html"
            linked_text = linked_page.read_text(encoding="utf-8")
            linked_structure = StructureWithFeed(linked_text)
            if (
                linked_text.count('<article class="gallery-card">') == 1
                and "fixture-canonical-scene" in linked_text
                and "Presets with linked Visual Evidence" in linked_text
                and linked_structure.images
                and all(resolve_local(linked_page, src).is_file() for src in linked_structure.images)
            ):
                checks += 1
            else:
                errors.append("linked preset gallery lacks its preview thumbnail or preset link")

            if "<script>fixture-injection</script>" not in scene_text and "&lt;script&gt;fixture-injection&lt;/script&gt;" in scene_text:
                checks += 1
            else:
                errors.append("authored HTML-like text was not escaped")

            direct_dir = root / "direct-cli"
            captured = io.StringIO()
            with redirect_stdout(captured):
                exit_code = catalog_html_main(["--pack", str(pack), "--output", str(direct_dir)])
            if exit_code == 0 and (direct_dir / "index.html").is_file() and (direct_dir / "search.html").is_file():
                checks += 1
            else:
                errors.append("direct directory CLI failed")

            ancestor_marker = root / "preserve-source-tree.txt"
            ancestor_marker.write_text("preserve me\n", encoding="utf-8")
            try:
                write_catalog_directory(packs, root, overwrite=True)
            except PackError:
                if ancestor_marker.read_text(encoding="utf-8") == "preserve me\n":
                    checks += 1
                else:
                    errors.append("ancestor output rejection modified the source tree")
            else:
                errors.append("catalog accepted an ancestor of a source pack as output")

            replacement_pack = pack_parent / "replacement"
            replacement_fixture(replacement_pack)
            discovered = discover_pack_tree(pack_parent)
            if [item.pack_id for item in discovered] == [PACK_ID, REPLACEMENT_PACK_ID]:
                checks += 1
            else:
                errors.append("pack-tree discovery did not include every later pack deterministically")

            tree_output = root / "tree-cli"
            captured = io.StringIO()
            with redirect_stdout(captured):
                exit_code = catalog_html_main(["--pack-tree", str(pack_parent), "--output", str(tree_output)])
            tree_manifest = json.loads((tree_output / "catalog-manifest.json").read_text(encoding="utf-8")) if tree_output.is_dir() else {}
            if exit_code == 0 and tree_manifest.get("pack_count") == 2:
                checks += 1
            else:
                errors.append("--pack-tree CLI failed to follow newly added packs")

            state = root / "state.json"
            atomic_write_json(state, {"pack_roots": [str(pack_parent)], "enabled_packs": [PACK_ID], "resource_providers": {}})
            settings = root / "settings.json"
            atomic_write_json(settings, {"state_file": "state.json", "roots": ["packs"]})
            state_ok = [item.pack_id for item in load_explicit_state(state)] == [PACK_ID]
            settings_ok = [item.pack_id for item in load_explicit_settings(settings)] == [PACK_ID]
            replacement_state = root / "replacement-state.json"
            atomic_write_json(replacement_state, {"pack_roots": [str(pack_parent)], "enabled_packs": [PACK_ID, REPLACEMENT_PACK_ID], "resource_providers": {}})
            replacement_views = load_explicit_state(replacement_state)
            replacement_output = root / "replacement-catalog"
            replacement_report = write_catalog_directory(replacement_views, replacement_output)
            active = [item for item in parse_index(replacement_output / "data" / "catalog-index.js")["records"] if item["id"] == "fixture-canonical-scene"]
            if state_ok and settings_ok and len(active) == 1 and active[0]["pack_id"] == REPLACEMENT_PACK_ID and replacement_report.get("canonical_asset_link_count") == 3:
                checks += 1
            else:
                errors.append("state/settings/replacement resolution lost canonical asset links")

            portable = root / "portable"
            portable_report = write_catalog_directory(packs, portable, copy_assets=True)
            portable_scene = portable / _record_page_relative(scene_view)
            portable_structure = StructureWithFeed(portable_scene.read_text(encoding="utf-8"))
            portable_images = [resolve_local(portable_scene, value) for value in portable_structure.images]
            if portable_report.get("resource_mode") == "copied" and portable_images and all(path.is_file() and portable in path.parents for path in portable_images):
                checks += 1
            else:
                errors.append("portable mode failed to copy linked SVG resources")

            if inventory(pack) == before:
                checks += 1
            else:
                errors.append("catalog generation mutated the source pack")

            transaction_output = root / "transaction-catalog"
            transaction_output.mkdir()
            transaction_marker = transaction_output / "preserve.txt"
            transaction_marker.write_text("preserve me\n", encoding="utf-8")
            original_replace = os.replace
            failed_publication = False

            def fail_candidate_publication(source: object, destination: object) -> None:
                nonlocal failed_publication
                source_path = Path(source)
                destination_path = Path(destination)
                if (
                    not failed_publication
                    and destination_path.resolve() == transaction_output.resolve()
                    and source_path.name.startswith(".transaction-catalog.tmp-")
                ):
                    failed_publication = True
                    raise OSError("fixture publication failure")
                original_replace(source, destination)

            with mock.patch("catalog_html.os.replace", side_effect=fail_candidate_publication):
                try:
                    write_catalog_directory(packs, transaction_output, overwrite=True)
                except OSError:
                    if (
                        failed_publication
                        and transaction_marker.read_text(encoding="utf-8")
                        == "preserve me\n"
                    ):
                        checks += 1
                    else:
                        errors.append("failed catalog publication did not restore prior output")
                else:
                    errors.append("catalog publication failure fixture did not fail")

            def asset_ref_failure(name: str, ref: Any) -> str:
                """Build one fixture whose asset names another asset, and report the failure."""

                probe_pack = root / name / "packs" / "fixture"
                fixture(probe_pack)
                assets_file = probe_pack / "records" / "assets.json"
                document = json.loads(assets_file.read_text(encoding="utf-8"))
                for record in document["records"]:
                    if record["id"] == "fixture-visual-evidence":
                        record["canonical_record_refs"] = [ref]
                atomic_write_json(assets_file, document)
                try:
                    write_catalog_directory(
                        load_pack_directories([probe_pack]), root / name / "catalog"
                    )
                except PackError as exc:
                    return str(exc)
                return ""

            mapping_failure = asset_ref_failure(
                "asset-ref-mapping",
                {"pack_id": PACK_ID, "record_id": "fixture-thumbnail-asset"},
            )
            string_failure = asset_ref_failure(
                "asset-ref-string", f"{PACK_ID}:fixture-thumbnail-asset"
            )
            if all(
                "unresolved canonical asset links" in message
                and "fixture-thumbnail-asset" in message
                for message in (mapping_failure, string_failure)
            ):
                checks += 1
            else:
                errors.append(
                    "a pack-qualified canonical_record_ref resolved to an asset record: "
                    f"{mapping_failure!r} / {string_failure!r}"
                )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"unexpected exception: {exc}")
    return {"ok": not errors, "checks": checks, "errors": errors}



class StructureWithFeed(Structure):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.feed(text)


def main() -> int:
    report = run()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
