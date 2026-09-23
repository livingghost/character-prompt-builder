#!/usr/bin/env python3
"""Static structural checks for the standalone Character Sheet HTML editor."""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "templates" / "character-sheet.template.html"
BLANK_DATA_PATH = ROOT / "templates" / "character-sheet-data.blank.json"
EXPECTED_TABLES = {
    "axes",
    "views",
    "evidence",
    "formreg",
    "invariants",
    "bodylang",
    "partstates",
    "motion",
    "actions",
    "gestures",
    "marks",
    "overrides",
    "colors",
    "parts",
    "items",
    "expressions",
    "outfits",
}
FORM_TAGS = {"input", "textarea", "select"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class EditorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[dict[str, Any]] = []
        self.contenteditable = 0
        self.row_seq = 0
        self.fields: list[tuple[str, str]] = []
        self.tables: set[str] = set()
        self.add_buttons: list[str] = []
        self.row_templates: list[str] = []
        self.cells: list[dict[str, Any]] = []
        self.current_cell: dict[str, Any] | None = None
        self.template_cells: list[dict[str, Any]] = []
        self.current_template_cell: dict[str, Any] | None = None
        self.slot_ids: list[str] = []
        self.slot_controls: dict[str, dict[str, int]] = {}

    def context(self, key: str, default: Any = None) -> Any:
        for item in reversed(self.stack):
            if item.get(key) is not None:
                return item[key]
        return default

    def _start(self, tag: str, attrs_list: list[tuple[str, str | None]], *, push: bool) -> None:
        attrs = {key: (value if value is not None else "") for key, value in attrs_list}
        if "contenteditable" in attrs:
            self.contenteditable += 1
        row_id = self.context("row")
        if tag == "tr" and push:
            self.row_seq += 1
            row_id = self.row_seq
        table_id = self.context("table_id")
        template_depth = int(self.context("template_depth", 0))
        # Row templates are siblings of their table element, so the owning
        # table id travels through the template tag itself.
        if attrs.get("data-row-template"):
            template_table: str | None = attrs["data-row-template"]
        else:
            template_table = self.context("template_table")
        slot_id = self.context("slot_id")
        if tag == "template":
            template_depth += 1
            if attrs.get("data-row-template"):
                self.row_templates.append(attrs["data-row-template"])
        if tag == "table" and attrs.get("data-export-table") is not None:
            table_id = attrs.get("id", "")
            if table_id:
                self.tables.add(table_id)
        classes = set(attrs.get("class", "").split())
        if tag == "div" and "slot" in classes and attrs.get("data-slot-id"):
            slot_id = attrs["data-slot-id"]
            self.slot_ids.append(slot_id)
            self.slot_controls.setdefault(slot_id, {"image": 0, "package": 0, "policy": 0})
        if attrs.get("data-field-id"):
            self.fields.append((attrs["data-field-id"], tag))
        if tag == "button" and attrs.get("data-add-row"):
            self.add_buttons.append(attrs["data-add-row"])
        if tag == "td" and attrs.get("data-column-id") and template_depth == 0 and table_id:
            self.current_cell = {
                "table": table_id,
                "column": attrs["data-column-id"],
                "row": row_id,
                "controls": 0,
            }
        if tag == "td" and attrs.get("data-column-id") and template_depth > 0 and template_table:
            self.current_template_cell = {
                "table": template_table,
                "column": attrs["data-column-id"],
                "row": row_id,
                "controls": 0,
            }
        if self.current_cell is not None and tag in FORM_TAGS:
            self.current_cell["controls"] += 1
        if self.current_template_cell is not None and tag in FORM_TAGS:
            self.current_template_cell["controls"] += 1
        if slot_id and tag in FORM_TAGS:
            path_kind = attrs.get("data-slot-path")
            if path_kind in {"image", "package"}:
                self.slot_controls[slot_id][path_kind] += 1
            if attrs.get("data-fill-policy") is not None:
                self.slot_controls[slot_id]["policy"] += 1
        if push:
            self.stack.append(
                {
                    "tag": tag,
                    "table_id": table_id,
                    "row": row_id,
                    "template_depth": template_depth,
                    "template_table": template_table,
                    "slot_id": slot_id,
                }
            )

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, push=tag not in VOID_TAGS)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, push=False)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self.current_cell is not None:
            self.cells.append(self.current_cell)
            self.current_cell = None
        if tag == "td" and self.current_template_cell is not None:
            self.template_cells.append(self.current_template_cell)
            self.current_template_cell = None
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                del self.stack[index:]
                break


def declared_table_columns(html: str) -> dict[str, list[str]]:
    """Extract the editor's TABLE_COLUMNS declaration from its inline script."""
    match = re.search(r"const TABLE_COLUMNS=\{(.*?)\};", html, re.S)
    if not match:
        return {}
    declared: dict[str, list[str]] = {}
    for name, body in re.findall(r"(\w+):\[(.*?)\]", match.group(1), re.S):
        declared[name] = re.findall(r"'([A-Za-z0-9_]+)'", body)
    return declared


def main() -> int:
    html = HTML_PATH.read_text(encoding="utf-8")
    parser = EditorParser()
    parser.feed(html)
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: Any = None) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    field_ids = [field_id for field_id, _ in parser.fields]
    check("contenteditable is not used", parser.contenteditable == 0, parser.contenteditable)
    check("all field IDs are attached to real form controls", all(tag in FORM_TAGS for _, tag in parser.fields), parser.fields)
    check("field IDs are unique", len(field_ids) == len(set(field_ids)), field_ids)
    check(
        "the layout profile declaration field is exposed",
        "field.sheet_layout_profile" in field_ids,
        "field.sheet_layout_profile",
    )
    check("the expected data tables exist", parser.tables == EXPECTED_TABLES, sorted(parser.tables))
    check("each table has exactly one Add button", sorted(parser.add_buttons) == sorted(EXPECTED_TABLES), parser.add_buttons)
    check("each table has exactly one hidden row template", sorted(parser.row_templates) == sorted(EXPECTED_TABLES), parser.row_templates)
    check("every visible data cell contains exactly one form control", all(cell["controls"] == 1 for cell in parser.cells), [cell for cell in parser.cells if cell["controls"] != 1])
    check("every row-template data cell contains exactly one form control", all(cell["controls"] == 1 for cell in parser.template_cells), [cell for cell in parser.template_cells if cell["controls"] != 1])
    # The export loop and the structure audit both derive their columns from
    # TABLE_COLUMNS, so a declared column without a matching cell in either
    # the visible body or the hidden row template silently disables export.
    declared = declared_table_columns(html)
    check("the editor declares TABLE_COLUMNS", sorted(declared) == sorted(EXPECTED_TABLES), sorted(declared))
    blank = json.loads(BLANK_DATA_PATH.read_text(encoding="utf-8"))
    blank_rows_match = all(
        isinstance(blank.get("tables", {}).get(table_id), list)
        and len(blank["tables"][table_id]) == 1
        and set(blank["tables"][table_id][0].get("values", {})) == set(columns)
        and all(value == "" for value in blank["tables"][table_id][0]["values"].values())
        for table_id, columns in declared.items()
    )
    check(
        "the blank sidecar exposes the current editor contract without seeded meaning",
        blank.get("sheet_status") == "draft"
        and set(blank.get("fields", {})) == set(field_ids)
        and all(value == "" for value in blank["fields"].values())
        and set(blank.get("tables", {})) == EXPECTED_TABLES
        and blank_rows_match
        and blank.get("slots") == {},
    )

    # Per-row comparison, not per-table aggregation: an aggregate set can
    # mask one row missing a column that another row carries, and a table
    # whose cells were all dropped would vanish from an aggregate map
    # entirely. Every declared table must appear with at least one visible
    # row and one template row, and every row must carry exactly the
    # declared columns.

    def rows_by_table(cells: list[dict[str, Any]]) -> dict[str, dict[Any, set[str]]]:
        grouped: dict[str, dict[Any, set[str]]] = {}
        for cell in cells:
            grouped.setdefault(cell["table"], {}).setdefault(cell["row"], set()).add(cell["column"])
        return grouped

    def row_mismatches(grouped: dict[str, dict[Any, set[str]]]) -> dict[str, Any]:
        detail: dict[str, Any] = {}
        for table, columns in declared.items():
            rows = grouped.get(table, {})
            if not rows:
                detail[table] = "no data rows found"
                continue
            for row_key, row_columns in sorted(rows.items(), key=lambda item: str(item[0])):
                if sorted(row_columns) != sorted(columns):
                    detail[f"{table}#row{row_key}"] = sorted(row_columns)
        return detail

    visible_rows = rows_by_table(parser.cells)
    template_rows = rows_by_table(parser.template_cells)
    check("every visible table row exposes exactly its declared columns", not row_mismatches(visible_rows), row_mismatches(visible_rows))
    check("every row template exposes exactly its declared columns", not row_mismatches(template_rows), row_mismatches(template_rows))
    check("all slot IDs are unique", len(parser.slot_ids) == len(set(parser.slot_ids)), parser.slot_ids)
    check(
        "blank source predeclares no fixed panel slots or panel-count contract",
        not parser.slot_ids and "SHARED_SLOT_DEFINITIONS" not in html,
        parser.slot_ids,
    )
    malformed_slots = {
        slot_id: counts
        for slot_id, counts in parser.slot_controls.items()
        if counts != {"image": 1, "package": 1, "policy": 1}
    }
    check("every slot has one image path, package path, and policy control", not malformed_slots, malformed_slots)
    check(
        "slot controls are created from declared visual rows or imported resolved entries",
        "function ensureSlotEditor" in html
        and "function syncDeclaredPanelSlotEditors" in html
        and "profile-only artifact section starts empty" in html
        and "for(const [slotId,raw] of Object.entries(data.slots))" in html,
    )
    check(
        "imported unknown slots become editable instead of opaque passthrough",
        "const slot=ensureSlotEditor(slotId);" in html
        and "normalizeSlotPanelCode" in html
        and "Importing sheet data adds any further slots" in html,
    )
    check(
        "non-object slot values remain opaque during import and export",
        html.index("if(!raw||typeof raw!=='object'||Array.isArray(raw))")
        < html.index("const slot=ensureSlotEditor(slotId);")
        and "Object.prototype.hasOwnProperty.call(passthrough.slots,slotId)" in html,
    )
    check(
        "untouched auto artifact editors do not create empty slot records",
        "!state.imagePath&&!state.packagePath&&state.fillPolicy==='auto'&&!Object.keys(extras).length"
        in html
        and "delete slots[slotId];continue" in html,
    )
    check(
        "reset removes every imported dynamic slot editor",
        "slot.dataset.dynamicSlotEditor='true'" in html
        and "querySelectorAll('.slot[data-dynamic-slot-editor=\"true\"]'))slot.remove()" in html
        and "sharedSlotEditor" not in html,
    )
    check(
        "expression and body-language tables do not auto-seed fixed row totals",
        "function ensureStarterRows" not in html
        and "no fixed total or upper count" in html
        and "there is no required total or maximum" in html,
    )
    check(
        "linked form sheets expose semantic id and reverse-spine fields",
        {"field.form_id", "field.form_spine_path"} <= set(field_ids),
    )
    check(
        "visual identity axes are arbitrary rows rather than fixed humanoid fields",
        declared.get("axes") == ["axis", "choices_expression", "binding"]
        and not any(field_id.startswith("core.axis_") for field_id in field_ids)
        and "there is no fixed category list or row total" in html,
    )
    seeded_part_names = re.findall(
        r'<table data-export-table="" id="parts".*?</table>', html, re.S
    )
    seeded_part_values = (
        [
            value
            for value in re.findall(
                r'data-column-id="part"[^>]*value="([^"]*)"', seeded_part_names[0]
            )
            if value.strip()
        ]
        if seeded_part_names
        else ["missing parts table"]
    )
    check(
        "blank editor does not seed anatomy or component names",
        seeded_part_values == [],
        seeded_part_values,
    )
    check(
        "color targets are author-declared and examples are explicitly non-exhaustive",
        "Region / component / material / signal" in html
        and "none is assumed or treated as a complete list" in html
        and "Zone (skin, hair or fur, eyes, markings, plating, accessory)" not in html,
    )
    check(
        "communicated-state channels are generic rather than fixed anatomy columns",
        declared.get("expressions")
        == [
            "state",
            "overall_read",
            "channel_states",
            "fixed_identity_cues",
            "notes",
            "binding",
        ]
        and not any(
            token in html
            for token in (
                'data-column-id="gaze"',
                'data-column-id="mouth"',
                'data-column-id="brows"',
                'data-column-id="ears"',
                'data-column-id="tail"',
            )
        ),
    )
    check(
        "blank character data contains no non-empty input defaults",
        not re.findall(r'<input\b[^>]*\bvalue="[^"]+"', html, re.I)
        and "data-default=" not in html,
    )
    check(
        "creative guidance is not encoded as one-line or one-to-two field limits",
        "one or two, no more" not in html
        and "Personality axis (one line)" not in html
        and {
            "field.personality_and_motivational_structure",
            "field.design_themes_and_organizing_principles",
        }
        <= set(field_ids),
    )
    check(
        "all table add buttons use concise non-counting labels",
        len(re.findall(r'<button class="add" data-add-row="[^"]+" type="button">Add row</button>', html))
        == len(EXPECTED_TABLES)
        and "Add one " not in html
        and "Each activation adds exactly one" not in html,
    )
    check(
        "every fixed visual table exposes continuity and visibility controls",
        declared.get("marks")[-3:-1] == ["continuity_rule", "visibility_rule"]
        and declared.get("parts")[-3:-1] == ["continuity_rule", "visibility_rule"]
        and declared.get("items")[-3:-1] == ["continuity_rule", "visibility_rule"]
        and declared.get("outfits")[-3:-1] == ["continuity_rule", "visibility_rule"]
        and "visibility_rule" in declared.get("colors", []),
    )
    check(
        "all visual declaration rows retain live image artifact frames without fixed counts",
        all(
            f'id="{host}"' in html
            for host in (
                "viewPanelEditors",
                "outfitPanelEditors",
                "bodylangPanelEditors",
                "markPanelEditors",
                "partPanelEditors",
                "itemPanelEditors",
                "expressionPanelEditors",
                "evidencePanelEditors",
            )
        )
        and "function syncDeclaredPanelSlotEditors" in html
        and "view.base." in html
        and "view.outfit." in html
        and "'row.'+spec.tableId+'.'+row.dataset.rowId" in html
        and "syncDeclaredPanelSlotEditors();" in html,
    )
    check(
        "additional evidence views reference any declared subject row rather than one item kind",
        declared.get("evidence")
        == [
            "subject_table",
            "subject_row_id",
            "view_id",
            "orientation_configuration",
            "specification",
            "must_prove",
        ]
        and "This is not item-specific" in html
        and "has no fixed direction set" in html,
    )

    report = {"ok": all(row["passed"] for row in checks), "checks": len(checks), "results": checks}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
