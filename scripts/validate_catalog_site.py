#!/usr/bin/env python3
"""Validate one generated split catalog, including all pack and SVG links."""
from __future__ import annotations

import argparse
import json
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import unquote, urlparse


class Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []
        self.images: list[str] = []
        self.scripts: list[str] = []
        self.stylesheets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        href = values.get("href")
        if href:
            self.hrefs.append(href)
        if tag == "img" and values.get("src"):
            self.images.append(values["src"])
        if tag == "script" and values.get("src"):
            self.scripts.append(values["src"])
        if tag == "link" and values.get("rel") == "stylesheet" and href:
            self.stylesheets.append(href)


def load_index(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    prefix = "window.CPB_CATALOG_INDEX="
    if not text.startswith(prefix) or not text.rstrip().endswith(";"):
        raise ValueError("catalog-index.js does not contain the canonical assignment")
    value = json.loads(text[len(prefix) :].rstrip()[:-1])
    if not isinstance(value, dict):
        raise ValueError("catalog index must be an object")
    return value


def resolve_local(page: Path, value: str) -> Path | None:
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        return None
    if not parsed.path:
        return page
    return (page.parent / unquote(parsed.path)).resolve()


def _absolute_workspace_link(value: str) -> bool:
    """Report whether one emitted link points outside the published catalog."""

    decoded = unquote(value)
    return decoded.startswith("file:") or "/mnt/data" in decoded


def search_thumbnail_region_ok(catalog_css: str, catalog_js: str) -> bool:
    copy_append = catalog_js.find("card.appendChild(copy);")
    thumbnail_append = catalog_js.find("card.appendChild(imageLink);")
    return (
        ".result-card.has-thumbnail{grid-template-columns:minmax(0,1fr) minmax(112px,160px)}"
        in catalog_css
        and ".result-copy{" in catalog_css
        and ".result-thumbnail{" in catalog_css
        and copy_append >= 0
        and thumbnail_append >= 0
        and copy_append < thumbnail_append
    )


def run(catalog: Path) -> dict[str, Any]:
    catalog = catalog.expanduser().resolve()
    errors: list[str] = []
    checks = 0
    required = (
        "index.html",
        "search.html",
        "catalog-manifest.json",
        "assets/catalog.css",
        "assets/catalog.js",
        "data/catalog-index.js",
        "data/record-asset-map.json",
        "visual-evidence/index.html",
        "linked-presets/index.html",
        "browse/kinds.html",
    )
    for relative in required:
        if not (catalog / relative).is_file():
            errors.append(f"missing catalog file: {relative}")
    checks += len(required)
    if errors:
        return {"ok": False, "checks": checks, "errors": errors}

    manifest = json.loads((catalog / "catalog-manifest.json").read_text(encoding="utf-8"))
    index = load_index(catalog / "data" / "catalog-index.js")
    asset_map = json.loads((catalog / "data" / "record-asset-map.json").read_text(encoding="utf-8"))
    records = index.get("records") or []
    packs = index.get("packs") or []
    if manifest.get("record_count") != len(records):
        errors.append("catalog manifest record_count differs from compact index")
    if manifest.get("pack_count") != len(packs):
        errors.append("catalog manifest pack_count differs from compact index")
    if manifest.get("unresolved_asset_links"):
        errors.append("catalog manifest contains unresolved asset links")
    if asset_map.get("unresolved"):
        errors.append("record-asset map contains unresolved asset links")
    checks += 4

    index_by_key = {f"{row.get('pack_id')}:{row.get('id')}": row for row in records}
    record_map = asset_map.get("records") or {}
    asset_reverse = asset_map.get("assets") or {}
    map_summary = asset_map.get("summary") or {}
    if map_summary.get("canonical_records_with_assets") != len(record_map):
        errors.append("record-asset map summary canonical count is stale")
    if map_summary.get("asset_records_with_canonical_links") != len(asset_reverse):
        errors.append("record-asset map summary asset count is stale")
    if map_summary.get("canonical_asset_link_count") != sum(
        len((value or {}).get("assets") or []) for value in record_map.values()
    ):
        errors.append("record-asset map summary link count is stale")
    if map_summary.get("unresolved_link_count") != len(asset_map.get("unresolved") or []):
        errors.append("record-asset map summary unresolved count is stale")
    checks += 4
    if len(record_map) != manifest.get("canonical_records_with_assets"):
        errors.append("record-asset map size differs from manifest canonical count")
    if len(asset_reverse) != manifest.get("asset_record_count"):
        errors.append("asset reverse-map size differs from manifest asset count")
    checks += 2

    broken_index_paths: list[str] = []
    absolute_index_links: list[str] = []
    count_mismatches: list[str] = []
    for key, row in index_by_key.items():
        page = catalog / str(row.get("page") or "")
        if not page.is_file():
            broken_index_paths.append(f"{key}: page={row.get('page')}")
        thumbnail = row.get("thumbnail")
        if thumbnail:
            if _absolute_workspace_link(str(thumbnail)):
                absolute_index_links.append(f"{key}: thumbnail={thumbnail}")
            else:
                target = resolve_local(catalog / "search.html", str(thumbnail))
                if target is None or not target.is_file():
                    broken_index_paths.append(f"{key}: thumbnail={thumbnail}")
        if row.get("is_asset"):
            observed = len((asset_reverse.get(key) or {}).get("linked_records") or [])
            if int(row.get("linked_preset_count") or 0) != observed:
                count_mismatches.append(f"{key}: linked_preset_count")
        else:
            observed = len((record_map.get(key) or {}).get("assets") or [])
            if int(row.get("linked_asset_count") or 0) != observed:
                count_mismatches.append(f"{key}: linked_asset_count")
    if broken_index_paths:
        errors.append("broken index paths: " + "; ".join(broken_index_paths))
    if absolute_index_links:
        errors.append(
            "absolute workspace paths leaked into the compact index: "
            + "; ".join(absolute_index_links)
        )
    if count_mismatches:
        errors.append("link count mismatches: " + "; ".join(count_mismatches))
    checks += len(index_by_key) * 2

    html_files = sorted(catalog.rglob("*.html"))
    broken_links: list[str] = []
    absolute_leaks: list[str] = []
    unlinked_message_count = 0
    image_count = 0
    for page in html_files:
        text = page.read_text(encoding="utf-8")
        unlinked_message_count += text.count(
            "No Visual Evidence is linked to this record."
        )
        parsed = Links()
        parsed.feed(text)
        image_count += len(parsed.images)
        for value in [*parsed.hrefs, *parsed.images, *parsed.scripts, *parsed.stylesheets]:
            if _absolute_workspace_link(value):
                absolute_leaks.append(
                    f"{page.relative_to(catalog).as_posix()} -> {value}"
                )
                continue
            if value.startswith(("#", "mailto:", "https:", "http:")):
                continue
            target = resolve_local(page, value)
            if target is None or not target.is_file():
                broken_links.append(
                    f"{page.relative_to(catalog).as_posix()} -> {value}"
                )
    if broken_links:
        errors.append("broken HTML links: " + "; ".join(broken_links))
    if absolute_leaks:
        errors.append("absolute workspace paths leaked into HTML: " + "; ".join(absolute_leaks))
    checks += len(html_files) + image_count

    home = (catalog / "index.html").read_text(encoding="utf-8")
    search = (catalog / "search.html").read_text(encoding="utf-8")
    catalog_css = (catalog / "assets" / "catalog.css").read_text(encoding="utf-8")
    catalog_js = (catalog / "assets" / "catalog.js").read_text(encoding="utf-8")
    if "<script" in home:
        errors.append("direct-open catalog home must not load the compact search index")
    if "visual-evidence/index.html" not in home or "linked-presets/index.html" not in home:
        errors.append("catalog home lacks visual-first browse entry points")
    linked_count = sum(
        1 for row in records if not row.get("is_asset") and int(row.get("linked_asset_count") or 0) > 0
    )
    if f"Presets with linked Visual Evidence ({linked_count})" not in search:
        errors.append("search evidence filter does not publish the actual linked preset count")
    if linked_count != manifest.get("canonical_records_with_assets"):
        errors.append("linked preset count differs from catalog manifest")
    unlinked_count = sum(
        1
        for row in records
        if not row.get("is_asset") and int(row.get("linked_asset_count") or 0) == 0
    )
    if unlinked_message_count != unlinked_count:
        errors.append(
            "unlinked record message count differs from the actual unlinked preset count: "
            f"expected {unlinked_count}, got {unlinked_message_count}"
        )
    if not (
        "Browse Visual Evidence" in home
        and "Browse presets with Visual Evidence" in home
        and "Visual Evidence records" in search
    ):
        errors.append("catalog entry points do not use the Visual Evidence product name")
    if not search_thumbnail_region_ok(catalog_css, catalog_js):
        errors.append("search thumbnails are not isolated in the dedicated trailing card region")
    checks += 7

    return {
        "ok": not errors,
        "checks": checks,
        "catalog": str(catalog),
        "pack_count": len(packs),
        "record_count": len(records),
        "asset_record_count": len(asset_reverse),
        "linked_preset_count": linked_count,
        "html_file_count": len(html_files),
        "image_reference_count": image_count,
        "errors": errors,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    args = parser.parse_args(argv)
    report = run(args.catalog)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
