#!/usr/bin/env python3
from __future__ import annotations
import operation_context as _operation_context

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# Static lexical size only. This neither measures host tokens nor establishes
# whether selecting fewer files preserves the task's meaning.
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*")


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


def measure(scenario: dict, *, root: Path = ROOT) -> dict:
    """Measure the complete section bodies selected for this scenario."""
    from execution_routes import resolve
    from knowledge_documents import DocumentReader
    acquired = {}

    def read_source(path):
        if path not in acquired:
            acquired[path] = (root / path).read_bytes()
        return acquired[path]

    reader = DocumentReader(read_source)
    resolved = resolve(scenario['route'], scenario.get('features', []),
        execution=scenario['execution'], operation=scenario.get('operation'),
        authoring_scope=scenario.get('authoring_scope'), root=root, read_source=read_source,
        document_reader=reader)
    parts = []
    for document in resolved['reads']:
        source = reader.acquire(document['document_id'])
        selected = b''.join(source.section(row['section_id']).raw for row in document['sections'])
        complete_size = sum(section.size for section in source.sections)
        parts.append({'document_id': document['document_id'], 'missing': False,
            'words': count_words(selected.decode('utf-8')), 'selected_bytes': len(selected),
            'source_bytes': complete_size, 'sections': document['sections'],
            'selection_scope': 'complete-source' if len(document['sections']) == len(source.sections) else 'selected-sections'})
    return {'operation': resolved['operation'], 'execution': resolved['execution'],
        'authoring_scope': resolved.get('authoring_scope'),
        'words': sum(row['words'] for row in parts),
        'selected_bytes': sum(row['selected_bytes'] for row in parts),
        'source_bytes': sum(row['source_bytes'] for row in parts), 'files': parts}


def main() -> int:
    parser = _operation_context.ArgumentParser()
    parser.add_argument("--routes", type=Path, default=ROOT / "config/runtime-read-routes.json")
    parser.add_argument('--root', type=Path, help='Studio root for measuring actual editable --choices.')
    parser.add_argument('--choices', help='Studio-relative choices file; derive its current stage and actual amendment scope.')
    args = parser.parse_args()
    if (args.root is None) != (args.choices is None):
        parser.error('--root and --choices must be supplied together')
    if args.choices is not None:
        from production_reading_scope import from_choices
        scope, task = from_choices(args.root, args.choices)
        routes = {'current-editable-work': {'route': task['route'], 'execution': task['execution'],
            'features': task.get('features', []), 'authoring_scope': scope}}
    else:
        routes = json.loads(args.routes.read_text(encoding="utf-8"))
    report = {"ok": True, "measurement": "static-lexical-words-not-host-tokens",
        "coverage": "Selected document source bytes only; model cards, pack resources and response metadata are excluded.",
        "routes": {}}
    for name, scenario in routes.items():
        report['routes'][name] = measure(scenario)
    report['errors'] = []
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
