#!/usr/bin/env python3
"""Export a read-only, byte-bound view of a production run.

Usage: python scripts/artifact_review.py --project WORK --run ID --out reviews/NAME
The report is derived from existing receipts. It never submits, selects or adopts.
"""
from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

import execution_contract as c
import production_workflow as workflow

ROOT = Path(__file__).resolve().parents[1]
from io_budget import optional_count


def workspace(root: Path) -> Path:
    """Resolve a workspace without letting reporting write into the installed skill."""
    root = root.absolute()
    # local() also rejects symbolic-link ancestors and noncanonical paths.
    c.local(root, 'reviews', exists=False)
    installation = next((p for p in (ROOT, *ROOT.parents)
                         if (p / 'package-manifest.toml').is_file()), ROOT)
    if root.resolve().is_relative_to(installation.resolve()):
        raise ValueError('use a project workspace outside the installed bundle')
    if not root.is_dir():
        raise ValueError('project workspace does not exist')
    return root


def attachment(raw: bytes) -> tuple[str, str]:
    """Choose an inert delivery extension; never publish arbitrary active HTML/SVG."""
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):
        return '.png', 'image'
    if raw.startswith(b'\xff\xd8\xff'):
        return '.jpg', 'image'
    if raw[:4] == b'RIFF' and raw[8:12] == b'WEBP':
        return '.webp', 'image'
    if raw[:4] == b'RIFF' and raw[8:12] == b'WAVE':
        return '.wav', 'audio'
    if len(raw) > 12 and raw[4:8] == b'ftyp':
        return '.mp4', 'video'
    try:
        raw.decode('utf-8')
    except UnicodeDecodeError:
        return '.bin', 'binary'
    return '.txt', 'text'


def _object_file(directory: Path, item: dict, files: dict[str, bytes], preview_chars: int | None = None) -> dict:
    optional_count(preview_chars, 'preview characters')
    raw = c.object_read(directory, item['sha256'])
    if item.get('size', len(raw)) != len(raw):
        raise ValueError('recorded file size does not match its saved bytes')
    suffix, kind = attachment(raw)
    text = raw.decode('utf-8') if kind == 'text' else None
    relative = 'files/' + item['sha256'] + suffix
    files[relative] = raw
    return {'path': item['path'], 'sha256': item['sha256'], 'size': len(raw),
            'download': relative, 'kind': kind,
            'preview': text[:preview_chars] if text is not None else None,
            'preview_truncated': text is not None and preview_chars is not None and len(text) > preview_chars}


def build(root: Path, run: str, *, preview_chars: int | None = None) -> tuple[dict, dict[str, bytes]]:
    """Read pinned inputs and every candidate, not just the chosen result."""
    optional_count(preview_chars, "preview characters")
    root = workspace(root)
    directory, prepared, consumer, rows = workflow.load_run(root, run)
    files: dict[str, bytes] = {}
    changes: list[dict] = []
    for dep in prepared['dependencies']:
        try:
            if workflow.current_sha256(root, dep) != dep['sha256']:
                changes.append({'space': dep['space'], 'path': dep['path'], 'reason': 'content changed'})
        except (OSError, ValueError):
            changes.append({'space': dep['space'], 'path': dep['path'], 'reason': 'missing or unreadable'})
    for row in rows:
        for item in row['data'].get('files', []) + row['data'].get('evidence', []):
            # Validate every pinned object even if it is not displayed.
            raw = c.object_read(directory, item['sha256'])
            if len(raw) != item['size']:
                raise ValueError('receipt file size mismatch')
            try:
                current = c.read(c.local(root, item['path']))
                if current != raw:
                    changes.append({'space': 'artifact', 'path': item['path'], 'reason': 'content changed'})
            except (OSError, ValueError):
                changes.append({'space': 'artifact', 'path': item['path'], 'reason': 'missing or unreadable'})
    sources = []
    dependencies = {(d['space'], d['path']): d for d in prepared['dependencies']}
    for source in prepared['task']['sources']:
        dep = dependencies.get(('project', source['path']))
        if dep is None:
            raise ValueError('declared source has no pinned project dependency')
        sources.append({**source, 'file': _object_file(directory, dep, files, preview_chars)})
    candidates = []
    for row in rows:
        if row['event'] != 'candidate':
            continue
        reviews = [r for r in rows if r['event'] == 'review'
                   and r['data']['candidate'] == row['sha256']]
        candidates.append({'id': row['sha256'], 'note': row['data'].get('note', ''),
                           'limitations': row['data'].get('limitations', []),
                           'media': row['data'].get('media'),
                           'files': [_object_file(directory, f, files, preview_chars) for f in row['data']['files']],
                           'reviews': [{'receipt': r['sha256'], 'review': r['data']['review'],
                                        'evidence': [_object_file(directory, f, files, preview_chars)
                                                     for f in r['data'].get('evidence', [])]}
                                       for r in reviews]})
    selections = [{'receipt': row['sha256'], **row['data']['selection']}
                  for row in rows if row['event'] == 'selection']
    report = {'preview_characters': preview_chars, 'run': run, 'input_sha256': prepared['input_sha256'],
              'receipt_head': rows[-1]['sha256'] if rows else None,
              'current': not changes, 'changed_dependencies': changes,
              'task_id': prepared['task']['task_id'], 'task_path': prepared['task_path'],
              'direction': prepared['task']['direction'],
              'criteria': prepared['task']['criteria'], 'sources': sources,
              'consumer': consumer, 'candidates': candidates, 'selections': selections,
              'completion_recorded': any(r['event'] == 'completion' for r in rows),
              'timeline': [{'sequence': r['sequence'], 'event': r['event'], 'receipt': r['sha256']}
                           for r in rows],
              'limits': ['A receipt proves recorded bytes, not human consent or artistic quality.',
                         'This is a read-only snapshot; selecting or adopting uses the production workflow.',
                         'Previews display the saved bytes. Current workspace changes are listed separately.',
                         'Preview format detection is not a media-quality assessment.']}
    return report, files


def _json(value: Any) -> str:
    return html.escape(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


def _file_view(item: dict) -> str:
    label = html.escape(item['path'])
    link = html.escape(item['download'], quote=True)
    if item['kind'] == 'image':
        preview = f'<img src="{link}" alt="{label}" loading="lazy">'
    elif item['kind'] in {'video', 'audio'}:
        tag = item['kind']
        preview = f'<{tag} controls preload="metadata" src="{link}"></{tag}>'
    elif item['kind'] == 'text':
        preview = '<pre>' + html.escape(item['preview']) + '</pre>'
        if item['preview_truncated']:
            preview += '<p>Preview truncated. The attachment retains the complete bytes.</p>'
    else:
        preview = '<p>No active preview for this file type.</p>'
    return (f'<div class="file"><h4>{label}</h4>{preview}<p><a download href="{link}">'
            f'Saved artifact</a> <code>{item["sha256"]}</code> ({item["size"]} bytes)</p></div>')


def render(report: dict) -> str:
    """Escape all authored data and provide no script or editable authority surface."""
    body = [f'<h1>Production review</h1><p>Task: {html.escape(report["task_id"])}<br>'
            f'Run: <code>{report["run"]}</code></p>']
    body.append('<p class="status">' + ('Inputs match this snapshot.' if report['current']
                 else 'STALE: workspace content differs. Saved evidence is shown, not silently replaced.') + '</p>')
    if report['changed_dependencies']:
        body.append('<h2>Changed dependencies</h2><pre>' + _json(report['changed_dependencies']) + '</pre>')
    body += ['<h2>Purpose and choices</h2><pre>' + _json(report['direction']) + '</pre>',
             '<h2>Evidence criteria</h2><pre>' + _json(report['criteria']) + '</pre>',
             '<h2>Source material</h2>']
    for source in report['sources']:
        body.append('<details><summary>' + html.escape(source['id'] + ' / ' + source['role'])
                    + '</summary><pre>' + _json({k: v for k, v in source.items() if k != 'file'})
                    + '</pre>' + _file_view(source['file']) + '</details>')
    body.append('<h2>Exact prepared consumer</h2><pre>' + _json(report['consumer']) + '</pre>')
    body.append('<h2>Actual candidates and observations</h2>')
    if not report['candidates']:
        body.append('<p>No candidate has been captured. Nothing here is a generated result.</p>')
    for candidate in report['candidates']:
        body.append('<section><h3>Candidate <code>' + candidate['id'] + '</code></h3><p>'
                    + html.escape(candidate['note']) + '</p>')
        body.extend(_file_view(f) for f in candidate['files'])
        body.append('<pre>' + _json({'limitations': candidate['limitations'], 'media': candidate['media']}) + '</pre>')
        if not candidate['reviews']:
            body.append('<p>Not reviewed.</p>')
        for review in candidate['reviews']:
            body.append('<details open><summary>Recorded review</summary><pre>' + _json(review['review']) + '</pre>')
            body.extend(_file_view(f) for f in review['evidence'])
            body.append('</details>')
        body.append('</section>')
    body += ['<h2>Recorded selection</h2><pre>' + _json(report['selections']) + '</pre>',
             '<p>Completion receipt: ' + ('present' if report['completion_recorded'] else 'not present') + '</p>',
             '<details><summary>Receipt timeline</summary><pre>' + _json(report['timeline']) + '</pre></details>',
             '<h2>Limits</h2><pre>' + _json(report['limits']) + '</pre>']
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; media-src 'self'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Production review</title><style>
body{font:16px/1.6 system-ui,sans-serif;max-width:1100px;margin:3rem auto;padding:0 1.4rem;color:#172632;background:#f5f7fa}
h1,h2,h3{line-height:1.25}h2{margin-top:2.8rem}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:.88rem;background:#fff;padding:1rem;border:1px solid #d8e0e6;border-radius:.5rem}
code{overflow-wrap:anywhere;font-size:.8em}section,details{padding:1rem;margin:1rem 0;background:white;border:1px solid #d8e0e6;border-radius:.7rem}summary{cursor:pointer;font-weight:600}img,video{max-width:100%;max-height:75vh}.status{padding:1rem;border-left:4px solid #395d77;background:#e5edf3}a{color:#194f76}.file{margin:1.4rem 0}
</style></head><body>''' + '\n'.join(body) + '</body></html>\n'


def publish(root: Path, out: str, files: dict[str, bytes], *, prefix: str = 'reviews') -> Path:
    """Publish a complete derived directory once; leave existing destinations alone."""
    root = workspace(root)
    if not out.startswith(prefix + '/'):
        raise ValueError(f'output must be below {prefix}/ in the project workspace')
    target = c.local(root, out, exists=False)
    if target.exists():
        raise ValueError('output already exists; choose a new derived-report directory')
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.pending-', dir=target.parent))
    try:
        for name, raw in sorted(files.items()):
            c.atomic(c.local(staging, name, exists=False), raw)
        c.publish_directory(staging, target)
        c.fsync_dir(target.parent)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return target


def export(root: Path, run: str, out: str, *, preview_chars: int | None = None) -> dict:
    root = workspace(root)
    with c.lock(root):
        report, files = build(root, run, preview_chars=preview_chars)
        files['review.json'] = c.encoded(report)
        files['index.html'] = render(report).encode('utf-8')
        inventory = {k: {'sha256': c.digest(v), 'size': len(v)} for k, v in files.items()}
        files['files.json'] = c.encoded(inventory)
        target = publish(root, out, files)
    return {'ok': True, 'run': run, 'current': report['current'],
            'candidates': len(report['candidates']), 'output': str(target),
            'html': str(target / 'index.html'), 'mutates_canon': False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--run', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--preview-chars', type=int, help='Optional display-only text limit; default shows complete text and attachments are always complete')
    args = parser.parse_args()
    try:
        result = export(args.project, args.run, args.out, preview_chars=args.preview_chars)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
