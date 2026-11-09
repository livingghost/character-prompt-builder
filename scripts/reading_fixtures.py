"""Synthetic reading records for executable examples and tests only."""
from __future__ import annotations
import io
import os
import tempfile
from pathlib import Path
import execution_contract as c
import route_reading as r

_WORK = tempfile.TemporaryDirectory(prefix='synthetic-reading-')


def fixture_reading(*, execution: str, route: str = 'generation', features: list[str] | None = None,
                    studio: Path | None = None, ledger: Path | None = None,
                    dialect: str | None = None, operation: str | None = None,
                    model: str | None = None, service: str | None = None,
                    model_file: Path | None = None) -> dict:
    """Deliver complete source bytes for a labeled synthetic operation."""
    ledger = ledger or Path(os.environ.get('CPB_READS_LEDGER', str(Path(_WORK.name)/'reads.jsonl')))
    os.environ['CPB_READS_LEDGER'] = str(ledger.absolute())
    manifest, _ = r.capture(route, features, dialect=dialect, operation=operation, execution=execution, model=model,
                            service=service, model_file=model_file)
    key = c.content_id({'fixture': 'synthetic reading', 'manifest': manifest})[:32]
    issued = r.issue(route, features, ledger=ledger, stream=io.StringIO(), key=key,
                     at='2000-01-01T00:00:00Z', cwd='synthetic-fixture', dialect=dialect,
                     operation=operation, execution=execution, model=model, service=service, model_file=model_file)
    return r.build_record(issued, ledgers=[ledger])


def task_reading(root: Path, task: dict) -> dict:
    target = task.get('generation') or task.get('upscale') or (task.get('authored') or {}).get('target') or {}
    model = target.get('model')
    if model is None and target.get('production_spec'):
        model = c.load(root / target['production_spec']).get('target_model')
    if model is None and task.get('route') == 'upscale' and task.get('delivery'):
        source = root / task['delivery']['path']
        if source.is_file():
            model = c.load(source).get('model')
    record = fixture_reading(route=task['route'], features=task['features'], studio=root,
                             execution=task['execution'],
                             operation='author' if task['execution'] == 'authored' else 'prepare',
                             model=model, service=target.get('service') if model else None,
                             model_file=root / target['model_file'] if target.get('model_file') else None)
    path = 'work/fixture-reading-' + c.content_id(record) + '.json'
    target = root/path; target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(c.encoded(record))
    task['route_reading'] = path
    return task
