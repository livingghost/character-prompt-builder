"""Render human and host documents from authoritative section records."""
from __future__ import annotations
import operation_context as _operation_context

from collections.abc import Mapping
import json
from pathlib import Path

import execution_contract as c
from knowledge_documents import (
    AcquiredDocument, DocumentReader, RECORD_DIRECTORY, markdown_path, record_id, record_path,
)


ROOT = Path(__file__).resolve().parents[1]


def render_document(document: AcquiredDocument) -> bytes:
    """Retain every body byte in the document's declared section order."""
    return b''.join(section.raw for section in document.sections)


def record_ids(root: Path) -> list[str]:
    """Enumerate canonical records beneath the installed knowledge directory."""
    directory = c.local(root, RECORD_DIRECTORY, exists=False)
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise ValueError('knowledge records require a directory')
    identifiers = []
    for path in sorted(directory.rglob('*')):
        if path.is_symlink() or path.is_junction():
            raise ValueError('symbolic links and junctions are forbidden in knowledge records')
        if path.is_file() and path.suffix == '.json':
            relative = RECORD_DIRECTORY + '/' + path.relative_to(directory).as_posix()
            identifier = record_id(relative)
            c.local(root, record_path(identifier))
            identifiers.append(identifier)
    return identifiers


def generated_documents(root: Path) -> tuple[dict[str, bytes], tuple[str, ...]]:
    """Derive all current presentations and previously owned obsolete paths.

    Only canonical records supply content. The previous release inventory
    supplies deletion ownership, and no inventory is needed for a first build.
    Acquiring every record and checking every path precedes any caller's writes.
    """
    reader = DocumentReader(lambda relative: c.local(root, relative).read_bytes())
    outputs = {markdown_path(identifier): render_document(reader.acquire(identifier))
               for identifier in record_ids(root)}
    for relative in outputs:
        c.local(root, relative, exists=False)
    obsolete = set()
    previous = c.local(root, 'MANIFEST.json', exists=False)
    if previous.is_file():
        inventory = c.decode(previous.read_bytes())
        if not isinstance(inventory, dict) or not isinstance(inventory.get('files'), list):
            raise ValueError('previous MANIFEST.json must contain a files array')
        for item in inventory['files']:
            if not isinstance(item, dict) or not isinstance(item.get('path'), str):
                raise ValueError('previous MANIFEST.json file entries must contain a path')
            path = item['path']
            if path.startswith(RECORD_DIRECTORY + '/'):
                rendered = markdown_path(record_id(path))
                target = c.local(root, rendered, exists=False)
                if rendered not in outputs and target.exists():
                    obsolete.add(rendered)
    return outputs, tuple(sorted(obsolete))


def routed_document_ids(manifest: dict) -> list[str]:
    """Read document identities from the route manifest's declaration owners.

    Route, feature and operation reads, operation execution reads and reading
    profile document maps own these selections. Examples and explanatory strings
    do not declare runtime knowledge.
    """
    identifiers: set[str] = set()

    def mapping(value, owner: str) -> Mapping:
        if not isinstance(value, Mapping):
            raise ValueError(owner + ' must be an object')
        return value

    def include(values, owner: str) -> None:
        if not isinstance(values, list):
            raise ValueError(owner + ' must be an array of knowledge document IDs')
        for identifier in values:
            record_path(identifier)
            identifiers.add(identifier)

    manifest = mapping(manifest, 'route manifest')
    for group in ('routes', 'features', 'operation_contexts'):
        for name, entry in mapping(manifest.get(group, {}), group).items():
            owner = group + '.' + name
            entry = mapping(entry, owner)
            include(entry.get('reads', []), owner + '.reads')
            if group == 'operation_contexts':
                for execution, values in mapping(entry.get('executions', {}), owner + '.executions').items():
                    include(values, owner + '.executions.' + execution)
    for name, profile in mapping(manifest.get('reading_scopes', {}), 'reading_scopes').items():
        owner = 'reading_scopes.' + name
        profile = mapping(profile, owner)
        for field in ('documents', 'deferred_documents'):
            values = mapping(profile.get(field, {}), owner + '.' + field)
            include(list(values), owner + '.' + field)
    return sorted(identifiers)


def main(argv: list[str] | None = None) -> int:
    """Render or check presentations without acquiring the installed runtime."""
    parser = _operation_context.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='Compare every generated document without changing files.')
    arguments = parser.parse_args(argv)
    outputs, obsolete = generated_documents(ROOT)
    if arguments.check:
        stale = sorted({relative for relative, raw in outputs.items()
                        if not (path := c.local(ROOT, relative, exists=False)).is_file()
                        or path.read_bytes() != raw} | set(obsolete))
        print(json.dumps({'ok': not stale, 'generated_documents': len(outputs), 'stale': stale}, indent=2))
        return 1 if stale else 0
    for relative, raw in outputs.items():
        c.atomic(c.local(ROOT, relative, exists=False), raw, replace=True)
    for relative in obsolete:
        c.local(ROOT, relative).unlink()
    print(json.dumps({'ok': True, 'generated_documents': len(outputs), 'removed': list(obsolete)}, indent=2))
    return 0


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
