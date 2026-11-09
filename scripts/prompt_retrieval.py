#!/usr/bin/env python3
"""Initialize, resolve and settle a prompt retrieval record (`schemas/prompt-retrieval-record.schema.json`).

Catalog and vocabulary commands given `--record` append actual investigations.
Each element names a construction question. Model-bound tag wording separately
requires real dictionary searches and resolved vocabulary choices in this record.
Descriptive input can retain an empty construction record when no inquiry is needed."""
from __future__ import annotations
import operation_context as _operation_context

import argparse
import hashlib
import re
import json
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "prompt-retrieval-record.schema.json"

ARTIFACT_TYPE = "prompt-retrieval-record"
OUTCOMES = ("adopted", "composed", "unused")


MARK_HINT = ("mark it with --adopted ID (repeat for each selected record), "
             "--composed TEXT and --reason TEXT, or --unused REASON")


def _string_list(value: Any, label: str, field: str, errors: list[str], *, required: bool) -> list[str]:
    if value is None:
        if required:
            errors.append(f"{label}: {field} is required")
        return []
    if not isinstance(value, list):
        errors.append(f"{label}: {field} must be an array")
        return []
    if required and not value:
        errors.append(f"{label}: {field} must not be empty")
    items: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{label}: {field}[{index}] must be a non-empty string")
            continue
        items.append(item)
    return items


def validate_prompt_retrieval_record(value: Any) -> dict[str, Any]:
    """Check completed investigations and count their actual outcomes."""

    errors: list[str] = []
    adopted = 0
    composed = 0
    unused = 0
    element_names: list[str] = []

    if not isinstance(value, dict):
        return {"ok": False, "errors": ["record root must be an object"],
                "elements": 0, "adopted": 0, "composed": 0, "unused": 0}
    if value.get("artifact_type") != ARTIFACT_TYPE:
        errors.append(f"artifact_type must be {ARTIFACT_TYPE!r}, got {value.get('artifact_type')!r}")
    unknown = sorted(set(value) - {"artifact_type", "elements", "pack_state", "settled", "context", "vocabulary"})
    if unknown:
        errors.append(f"record has unknown keys: {unknown}")
    if "settled" in value and not isinstance(value["settled"], bool):
        errors.append("settled must be a boolean")
    context = value.get("context")
    if context is not None:
        if not isinstance(context, dict) or set(context) != {"prompt_sha256", "plot_content_sha256"}:
            errors.append("context must bind prompt_sha256 and plot_content_sha256")
        else:
            for key, digest in context.items():
                if key == 'plot_content_sha256' and digest is None:
                    continue
                if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                    errors.append(f"context.{key} must be a SHA-256 digest")
    if value.get("settled") is True and context is None:
        errors.append("a settled retrieval record requires its context")
    pack_state = value.get("pack_state")
    if pack_state is not None and (not isinstance(pack_state, str) or not pack_state.strip()):
        errors.append("pack_state must be a non-empty string when present")
    if "vocabulary" in value:
        from state_protocol import validate_against_schema
        vocabulary_schema = json.loads((ROOT / 'schemas/prompt-vocabulary-selection.schema.json').read_text(encoding='utf-8'))
        errors.extend('vocabulary: ' + error for error in validate_against_schema(value['vocabulary'], vocabulary_schema))

    entries = value.get("elements")
    if not isinstance(entries, list):
        errors.append("elements must be an array")
        entries = []

    for index, entry in enumerate(entries):
        name = entry.get("element") if isinstance(entry, dict) else None
        named = isinstance(name, str) and bool(name.strip())
        label = f"element {name!r}" if named else f"elements[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{label} must be an object")
            continue
        unknown = sorted(set(entry) - {
            "element", "queries", "inspected_records", "outcome",
            "adopted_records", "composed_wording", "reason",
        })
        if unknown:
            errors.append(f"{label} has unknown keys: {unknown}")

        if not named:
            errors.append(f"{label}: element must be a non-empty string")
        else:
            if name in element_names:
                errors.append(f"elements[{index}] repeats {name!r}")
            element_names.append(name)

        queries = _string_list(entry.get("queries"), label, "queries", errors, required=False)
        inspected = _string_list(entry.get("inspected_records"), label, "inspected_records", errors, required=False)
        for field in ("queries", "inspected_records"):
            if field in entry and entry[field] is None:
                errors.append(f"{label}: {field} must be an array")
        if not queries and not inspected:
            errors.append(f"{label}: an investigation requires a query or an inspected record")

        outcome = entry.get("outcome")
        if outcome is None:
            errors.append(f"{label} has no outcome; {MARK_HINT}")
            continue
        if outcome not in OUTCOMES:
            errors.append(f"{label}: outcome must be one of {OUTCOMES!r}, got {outcome!r}")
            continue
        if outcome == "adopted":
            adopted += 1
            records = _string_list(entry.get("adopted_records"), label, "adopted_records", errors, required=True)
            if len(set(records)) != len(records):
                errors.append(f"{label}: adopted_records repeats a record")
            missing = [record for record in records if record not in inspected]
            if missing:
                errors.append(f"{label}: adopted records were not inspected: {missing}")
            for absent in ("composed_wording", "reason"):
                if absent in entry:
                    errors.append(f"{label}: {absent} does not belong to an adopted outcome")
        elif outcome == "composed":
            composed += 1
            for required_key in ("composed_wording", "reason"):
                item = entry.get(required_key)
                if not isinstance(item, str) or not item.strip():
                    errors.append(f"{label}: {required_key} is required when outcome is 'composed'")
            if "adopted_records" in entry:
                errors.append(f"{label}: adopted_records does not belong to a composed outcome")
        else:
            unused += 1
            if not isinstance(entry.get("reason"), str) or not entry["reason"].strip():
                errors.append(f"{label}: reason is required when outcome is 'unused'")
            for absent in ("adopted_records", "composed_wording"):
                if absent in entry:
                    errors.append(f"{label}: {absent} does not belong to an unused outcome")

    return {
        "ok": not errors,
        "errors": errors,
        "elements": len(entries),
        "adopted": adopted,
        "composed": composed,
        "unused": unused,
    }


def load_prompt_retrieval_record(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    report = validate_prompt_retrieval_record(value)
    if not report["ok"]:
        raise ValueError(
            f"prompt retrieval record is invalid: {path}: " + "; ".join(report["errors"])
        )
    return report


def initialize_record(path: Path) -> dict[str, Any]:
    """Create an empty investigation record without replacing existing work."""
    from execution_contract import atomic
    value = {"artifact_type": ARTIFACT_TYPE, "elements": []}
    raw = (json.dumps(value, indent=2) + "\n").encode("utf-8")
    try:
        atomic(path, raw)
    except FileExistsError as exc:
        raise ValueError(f"retrieval record already exists and is kept: {path}") from exc
    return value


def retrieval_context(prompt: str, plot: dict[str, Any] | None) -> dict[str, str | None]:
    from prompt_plot import content_sha256
    return {
        "prompt_sha256": hashlib.sha256(prompt.strip().encode("utf-8")).hexdigest(),
        "plot_content_sha256": content_sha256(plot) if plot is not None else None,
    }


def settle_retrieval_record(value: Any, *, prompt: str, plot: dict[str, Any] | None = None) -> dict[str, Any]:
    """Explicit authoring operation; never called implicitly by generation."""
    report = validate_prompt_retrieval_record(value)
    if not report["ok"]:
        raise ValueError("invalid retrieval record: " + "; ".join(report["errors"]))
    from prompt_plot import validate_prompt_plot
    if plot is not None:
        plot_report = validate_prompt_plot(plot)
        if not plot_report["ok"]:
            raise ValueError("invalid retrieval plot: " + "; ".join(plot_report["errors"]))
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("retrieval needs a non-empty authored prompt")
    result = json.loads(json.dumps(value))
    result["settled"] = True
    result["context"] = retrieval_context(prompt, plot)
    return result


def _draft(path: Path, pack_state: str | None) -> dict[str, Any]:
    value = (json.loads(path.read_text(encoding="utf-8")) if path.exists()
             else {"artifact_type": ARTIFACT_TYPE, "elements": []})
    if not isinstance(value, dict) or value.get("artifact_type") != ARTIFACT_TYPE or not isinstance(value.get("elements"), list):
        raise ValueError(f"not a prompt retrieval record: {path}")
    if value.get("settled"):
        raise ValueError(f"{path} is settled; record new lookups in a new file")
    if pack_state is not None and value.setdefault("pack_state", pack_state) != pack_state:
        raise ValueError(f"the pack runtime changed since {path} began; repeat retrieval into a new record")
    return value


def check_recordable(path: Path, pack_state: str | None) -> None:
    """Refuse before a lookup runs when its result could not be recorded."""
    _draft(path, pack_state)


def record_lookups(path: Path, lookups: Sequence[tuple[str, Sequence[str], Sequence[str]]], *,
                   pack_state: str | None = None) -> dict[str, Any]:
    """Append actual lookup evidence and reopen each investigated question's outcome."""
    value = _draft(path, pack_state)
    for element, queries, inspected in lookups:
        if not isinstance(element, str) or not element.strip():
            raise ValueError("a recorded lookup needs a non-empty element name")
        entry = next((item for item in value["elements"] if item.get("element") == element), None)
        if entry is None:
            entry = {"element": element, "queries": [], "inspected_records": []}
            value["elements"].append(entry)
        for field in ("outcome", "adopted_records", "composed_wording", "reason"):
            entry.pop(field, None)
        for field, items in (("queries", queries), ("inspected_records", inspected)):
            for item in items:
                if item not in entry.setdefault(field, []):
                    entry[field].append(item)
    from pack_manager import atomic_write_json
    atomic_write_json(path, value)
    return value


def begin_lookups(path: Path, elements: Sequence[str], *, pack_state: str | None = None) -> dict[str, Any]:
    """Keep requested questions incomplete if their lookup cannot finish."""
    return record_lookups(path, [(element, (), ()) for element in elements], pack_state=pack_state)


def record_lookup(path: Path, element: str, *, queries: Sequence[str] = (),
                  inspected: Sequence[str] = (), pack_state: str | None = None) -> dict[str, Any]:
    """Append the queries and inspected records one lookup actually ran."""
    return record_lookups(path, [(element, queries, inspected)], pack_state=pack_state)


def mark_outcome(value: Any, element: str, *, adopted: str | Sequence[str] = (),
                 composed: str | None = None, reason: str | None = None,
                 unused: str | None = None) -> dict[str, Any]:
    """Record selected knowledge, authored wording or an unused investigation.

    A mark states the element's whole decision, so it replaces an earlier mark."""
    if not isinstance(value, dict) or value.get("settled"):
        raise ValueError("mark outcomes on an unsettled retrieval record")
    entry = next((item for item in value.get("elements", []) if item.get("element") == element), None)
    if entry is None:
        raise ValueError(f"no recorded lookup for element {element!r}")
    records = list(dict.fromkeys([adopted] if isinstance(adopted, str) else adopted))
    if records and composed is None and reason is None and unused is None:
        missing = [record for record in records if record not in entry.get("inspected_records", [])]
        if missing:
            raise ValueError(f"not inspected for element {element!r}: {missing}; "
                             "search or inspect with --record first")
        entry.pop("composed_wording", None)
        entry.pop("reason", None)
        entry.update(outcome="adopted", adopted_records=records)
    elif not records and composed and reason and unused is None:
        entry.pop("adopted_records", None)
        entry.update(outcome="composed", composed_wording=composed, reason=reason)
    elif not records and composed is None and reason is None and isinstance(unused, str) and unused.strip():
        entry.pop("adopted_records", None)
        entry.pop("composed_wording", None)
        entry.update(outcome="unused", reason=unused)
    else:
        raise ValueError(MARK_HINT)
    return value


def require_settled_retrieval(value: Any, *, prompt: str, plot: dict[str, Any] | None = None) -> dict[str, Any]:
    """Check an authored record's binding, including immutable past artifacts.

    This checks construction provenance, not eligibility for a new model request.
    """
    report = validate_prompt_retrieval_record(value)
    if not report["ok"]:
        raise ValueError("generation requires a valid retrieval record: " + "; ".join(report["errors"]))
    if value.get("settled") is not True:
        raise ValueError("generation requires a settled retrieval record")
    if value.get("context") != retrieval_context(prompt, plot):
        raise ValueError("retrieval record belongs to a different prompt or plot; repeat affected retrieval and settle explicitly")
    return report


def require_generation_retrieval(value: Any, *, prompt: str, plot: dict[str, Any] | None = None,
                                 model_record: dict, negative: str = '',
                                 syntax: str = 'literal') -> dict[str, Any]:
    if value is None:
        from model_prompt_input import resolve_prompt_input
        if resolve_prompt_input(model_record)['mode'] == 'tag-based':
            raise ValueError('tag-based input requires dictionary search and vocabulary selection for the current prompt')
        return {'ok': True, 'vocabulary_searched': False}
    report = require_settled_retrieval(value, prompt=prompt, plot=plot)
    from prompt_vocabulary_selection import require_for_model
    selection = require_for_model(value, prompt=prompt, negative=negative,
                                  model_record=model_record, syntax=syntax)
    report['vocabulary_searched'] = selection is not None
    return report


def resolve_selected_model(model: str | None, model_file: Path | None) -> dict | None:
    """Resolve an authoring target; a supplied record is not an execution override."""
    if model and model_file:
        raise ValueError('select --model or --model-file, not both')
    if model:
        from prepare_generation_references import resolve_model_record
        _, record = resolve_model_record(model)
    elif model_file:
        record = json.loads(model_file.read_text(encoding='utf-8'))
    else:
        return None
    from model_prompt_input import resolve_prompt_input
    resolve_prompt_input(record)
    if not isinstance(record.get('id'), str) or not record['id'].strip():
        raise ValueError('a selected model record requires its exact id')
    return record


def main(argv: Sequence[str] | None = None) -> int:
    parser = _operation_context.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    parser.add_argument("--init", action="store_true", help="Create an empty record; refuse an existing path")
    parser.add_argument("--settle", action="store_true", help="Explicitly settle decisions for the supplied authored prompt and plot")
    parser.add_argument("--search-vocabulary", action="store_true", help="Search existing wording for every term of a selected tag-based model rendition")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--model", help="The selected catalog model")
    target.add_argument("--model-file", type=Path, help="An acquired external target record with id, prompt_input and its applicable prompt_dialect")
    parser.add_argument("--negative-file", type=Path)
    parser.add_argument("--weighting", choices=['literal', 'sdEmbeds', 'compel'], default='literal')
    parser.add_argument("--retain-wording", action='append', default=[], help="A searched phrase or entry id to retain after comparison; repeat when the same reason applies")
    parser.add_argument("--query", action='append', default=[], help="Additional conceptual or synonym query for --retain-wording")
    parser.add_argument("--prompt-file", type=Path)
    parser.add_argument("--plot-file", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--element", help="Mark this investigated question's outcome in the record, in place")
    parser.add_argument("--adopted", metavar="ID", action="append", default=[],
                        help="An inspected record whose knowledge or wording the prompt uses; repeat for each selected record")
    parser.add_argument("--composed", metavar="TEXT", help="Authored wording that resolves the question, including adaptations of inspected knowledge")
    parser.add_argument("--reason", help="Why the authored wording resolves this question")
    parser.add_argument("--unused", metavar="REASON", help="Record why this investigation is not used in the final prompt")
    from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime
    add_pack_runtime_arguments(parser)
    args = parser.parse_args(argv)
    from catalog_cli import configure_pack_runtime
    runtime = resolve_pack_runtime(parser, args)
    configure_pack_runtime(runtime.settings)
    try:
        if args.init:
            if (args.settle or args.element is not None or args.adopted
                    or any(item is not None for item in
                           (args.prompt_file, args.plot_file, args.out, args.composed, args.reason, args.unused,
                            args.model, args.model_file, args.negative_file)) or args.search_vocabulary or args.query or args.retain_wording):
                raise ValueError("--init creates an empty record; mark and settle in separate commands")
            value = initialize_record(args.record)
            report = {**validate_prompt_retrieval_record(value), "created": str(args.record)}
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        value = json.loads(args.record.read_text(encoding="utf-8"))
        if args.search_vocabulary or args.retain_wording:
            if (not (args.model or args.model_file) or not args.prompt_file or args.settle
                    or args.element or args.adopted or args.composed or args.unused or args.plot_file):
                raise ValueError('vocabulary search requires a selected model and --prompt-file, separately from construction marking or settlement')
            if value.get('settled'):
                raise ValueError('search vocabulary on a draft record; settled inputs are immutable')
            from prompt_vocabulary_selection import search_selection, resolve_authored
            model = resolve_selected_model(args.model, args.model_file)
            previous = value.get('vocabulary')
            if args.retain_wording:
                if not isinstance(previous, dict):
                    raise ValueError('run --search-vocabulary before --retain-wording')
                for term in args.retain_wording:
                    previous = resolve_authored(previous, term, args.reason, queries=args.query)
            elif args.query or args.reason:
                raise ValueError('--query and --reason belong to --retain-wording')
            value['vocabulary'] = search_selection(prompt=args.prompt_file.read_text(encoding='utf-8'),
                negative=args.negative_file.read_text(encoding='utf-8') if args.negative_file else '',
                model_record=model, syntax=args.weighting, previous=previous)
            from pack_manager import atomic_write_json
            atomic_write_json(args.out or args.record, value)
            print(json.dumps({'ok': True, 'vocabulary': value['vocabulary']}, ensure_ascii=False, indent=2))
            return 0
        if args.query:
            raise ValueError('--query requires --retain-wording')
        if args.element is not None:
            if args.settle or any((args.prompt_file, args.plot_file, args.out)):
                raise ValueError("mark outcomes before settling, in a separate command")
            mark_outcome(value, args.element, adopted=args.adopted, composed=args.composed,
                         reason=args.reason, unused=args.unused)
            from pack_manager import atomic_write_json
            atomic_write_json(args.record, value)
            entry = next(item for item in value["elements"] if item.get("element") == args.element)
            marked = {key: entry[key] for key in ("element", "outcome", "adopted_records", "composed_wording", "reason")
                      if key in entry}
            remaining = validate_prompt_retrieval_record(value)["errors"]
            print(json.dumps({"ok": True, "marked": marked, "remaining": remaining},
                             ensure_ascii=False, indent=2))
            return 0
        if args.adopted or args.composed is not None or args.reason is not None or args.unused is not None:
            raise ValueError("--adopted, --composed, --reason and --unused require --element")
        if args.settle:
            if not args.prompt_file or not args.out:
                raise ValueError("--settle requires --prompt-file and --out; include --plot-file when a plot is selected")
            if value.get('vocabulary') is not None and not (args.model or args.model_file):
                raise ValueError('settling model-bound vocabulary requires --model or --model-file')
            if args.model or args.model_file:
                from prompt_vocabulary_selection import require_for_model
                model = resolve_selected_model(args.model, args.model_file)
                require_for_model(value, prompt=args.prompt_file.read_text(encoding='utf-8'),
                    negative=args.negative_file.read_text(encoding='utf-8') if args.negative_file else '',
                    model_record=model, syntax=args.weighting)
            value = settle_retrieval_record(value, prompt=args.prompt_file.read_text(encoding="utf-8"),
                                            plot=json.loads(args.plot_file.read_text(encoding="utf-8")) if args.plot_file else None)
            from pack_manager import atomic_write_json
            atomic_write_json(args.out, value)
        elif any((args.prompt_file, args.plot_file, args.out)):
            raise ValueError("binding arguments require --settle")
        report = validate_prompt_retrieval_record(value)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {"ok": False, "errors": [str(exc)], "elements": 0,
                  "adopted": 0, "composed": 0, "unused": 0}
        if hasattr(exc, 'vocabulary_search'):
            report['vocabulary_search'] = exc.vocabulary_search
    finally:
        configure_pack_runtime(None)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
