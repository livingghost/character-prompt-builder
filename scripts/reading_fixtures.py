"""Synthetic reading records for executable examples and tests only."""
from __future__ import annotations
import io
import os
import tempfile
from pathlib import Path
import execution_contract as c
import route_reading as r

_WORK = tempfile.TemporaryDirectory(prefix='synthetic-reading-')


def fixture_reading(*, route: str = 'generation', features: list[str] | None = None,
                    project: Path | None = None, ledger: Path | None = None) -> dict:
    """Read full fixture documents, then author a labeled synthetic application of the route's own documents."""
    ledger = ledger or Path(os.environ.get('CPB_READS_LEDGER', str(Path(_WORK.name)/'reads.jsonl')))
    os.environ['CPB_READS_LEDGER'] = str(ledger.absolute())
    manifest, bodies = r.capture(route, features)
    key = c.content_id({'fixture': 'synthetic reading', 'manifest': manifest})[:32]
    issued = r.issue(route, features, ledger=ledger, stream=io.StringIO(), key=key,
                     at='2000-01-01T00:00:00Z', cwd='synthetic-fixture')
    applied = set(c.load(r.ROOT/r.execution_routes.MANIFEST)['routes'][route]['reads'])
    applications = {'applied': [], 'resource_applied': []}
    for meta, raw in bodies:
        if meta['kind'] == 'document' and meta['path'] in applied:
            candidates = [block for block in r.prose_blocks(raw.decode('utf-8')) if len(block.split()) >= 12]
            if not candidates:
                raise ValueError('fixture needs a paragraph quotation in ' + meta['path'])
            applications['applied'].append({'path':meta['path'], 'quote':candidates[0],
                'why':'Exercise quotation integrity with synthetic input, not evidence of a real reading session.'})
        elif meta['kind'] == 'resource' and meta['resource'] == 'prompt-writing-guide':
            guide = c.decode(raw)
            candidates = [(i,j,rule) for i,section in enumerate(guide['sections']) if not section.get('dialects')
                          for j,rule in enumerate(section['rules']) if isinstance(rule,str) and rule.strip()]
            if not candidates:
                raise ValueError('synthetic model fixture needs a universal guide rule')
            i,j,rule=candidates[0]
            applications['resource_applied'].append({'resource':'prompt-writing-guide','pointer':f'/sections/{i}/rules/{j}',
                'quote':rule,'why':'Synthetic fixture exercises the complete decoded rule and its source pointer.'})
    return r.build_record(issued, applications, ledgers=[ledger])


def task_reading(root: Path, task: dict) -> dict:
    record = fixture_reading(route=task['route'], features=task['features'], project=root)
    path = 'work/fixture-reading-' + c.content_id(record) + '.json'
    target = root/path; target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(c.encoded(record))
    task['route_reading'] = path
    return task
