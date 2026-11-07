"""Chronological gallery projection for generated, imported and locally derived artwork.

A missing old file is a diagnostic on its entry, not a reason to hide new work.
Only records are enumerated; filesystem modification times and guessed filenames
never determine chronology or acceptance.
"""
from __future__ import annotations
from pathlib import Path, PurePosixPath
from typing import Any
from html.parser import HTMLParser
from urllib.parse import quote
import copy
import json
import os
import re

import execution_contract as c
from studio_activity import chronological, timestamp


def utc_day(value: str | None) -> str:
    """Date filters use the same absolute UTC time basis as chronology."""
    from datetime import datetime, timezone
    try:
        parsed = datetime.fromisoformat((value or '').replace('Z', '+00:00'))
        return parsed.astimezone(timezone.utc).date().isoformat() if parsed.tzinfo is not None else ''
    except (ValueError, TypeError, OverflowError):
        return ''


def build_index(root: Path, *, read=None) -> dict:
    import studio
    import sheet_inventory
    document = read.document if read else studio.manifest(root)
    entries, diagnostics = [], []
    for info in document.get('characters') or []:
        if not isinstance(info, dict):
            continue
        character = str(info.get('id'))
        home = studio.character_dir(root, character)
        if not home.is_dir():
            diagnostics.append({'character': character, 'message': 'character directory is missing'})
            continue
        try:
            rows = read.iterations(character) if read else studio.read_iterations(home)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            diagnostics.append({'character': character, 'message': str(exc)})
            rows = []
        by_iteration = {}
        for row in rows:
            errors = []
            def read_link(key):
                item = row.get(key)
                if not item:
                    return None
                try:
                    return c.load(c.local(root, item['path']))
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    errors.append({'file': item.get('path'), 'message': str(exc)})
                    return None
            sent, package = read_link('request'), read_link('package')
            service = row.get('service') or {}
            payload = package.get('generation_payload') or {} if isinstance(package, dict) else {}
            model = service.get('model') or (payload.get('model') or package.get('upscaler_model') if isinstance(package, dict) else None)
            entry = {'entry_id': character + '/' + str(row.get('iteration_id')),
                     'character': character, 'iteration_id': row.get('iteration_id'), 'kind': 'generation',
                     'model_record': model, 'dialect': service.get('dialect'), 'at': row.get('at'),
                     'time_basis': 'output-received-or-imported', 'slot': row.get('slot'), 'status': row.get('status'),
                     'production': row.get('production'), 'evaluation': row.get('evaluation'), 'disposition': row.get('disposition'),
                     'selection_basis': row.get('selection_basis'), 'owner_acceptance': row.get('owner_acceptance'),
                     'unassessed_criteria': row.get('unassessed_criteria'), 'production_diagnostic': row.get('production_diagnostic'),
                     'selection_diagnostics': row.get('selection_diagnostics') or [], 'acceptances': row.get('acceptances') or [],
                     'superseded_by': row.get('superseded_by'), 'service': row.get('service'), 'seed': row.get('seed'),
                     **studio.sent_text(sent, row.get('request_layout')),
                     'result': (row.get('result') or {}).get('path'), 'result_sha256': (row.get('result') or {}).get('sha256'),
                     'package': (row.get('package') or {}).get('path'),
                     'request': (row.get('request') or {}).get('path'), 'response': (row.get('response') or {}).get('path'),
                     'note': row.get('note'), 'reason': row.get('reason'),
                     'decision_kind': row.get('decision_kind') if row.get('production') else ('rejection' if row.get('status') == 'rejected' else None),
                     'diagnostics': errors, 'sheet_state': None, 'artifact_id': None}
            _availability(root, entry)
            entries.append(entry); by_iteration[row.get('iteration_id')] = entry
        sidecar = home / 'sheet/sheet-data.json'
        if not sidecar.is_file():
            continue
        try:
            artwork = sheet_inventory.entries(sidecar, state=read.sheet(character) if read else None)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            diagnostics.append({'character': character, 'file': str(sidecar.relative_to(root)), 'message': str(exc)})
            continue
        for item in artwork:
            origin = item['origin']
            generated = by_iteration.get(origin.get('iteration_id')) if origin.get('character') == character else None
            if generated is not None and generated['slot'] == item['slot']:
                generated.update(sheet_state=item['state'], artifact_id=item['artifact_id'])
                # Sheet selection is the current artwork for this panel, even
                # when its source iteration's acceptance axis is independent.
                continue
            art = item['artifact']
            result = (sidecar.parent / art['image']['path']).relative_to(root).as_posix()
            entry = {'entry_id': character + '/' + item['slot'] + '/' + item['artifact_id'],
                     'character': character, 'iteration_id': 'art-' + item['artifact_id'][:16],
                     'artifact_id': item['artifact_id'], 'kind': item.get('kind', art['provenance']['kind']),
                     'at': item['recorded_at'], 'time_basis': 'artifact-published', 'slot': item['slot'],
                     'status': {'current':'accepted', 'candidate':'candidate', 'history':'superseded'}[item['state']],
                     'sheet_state': item['state'], 'production': origin if origin.get('kind') == 'production' else None,
                     'evaluation': None, 'disposition': None, 'selection_basis': None, 'owner_acceptance': None,
                     'unassessed_criteria': [], 'selection_diagnostics': [],
                     'acceptances': [], 'superseded_by': None, 'service': None, 'model_record': (item.get('recipe') or {}).get('model'),
                     'dialect': None, 'seed': None, 'request_recorded': False, 'prompt_fields_known': False,
                     'settings': item.get('recipe') or {}, 'media': {}, 'result': result,
                     'result_sha256': art['image']['sha256'], 'package': None, 'note': 'Exact source artwork and edit recipe are kept in provenance.',
                     'reason': None, 'decision_kind': None, 'diagnostics': [{'message': text} for text in item['diagnostics']],
                     'provenance': (sidecar.parent / art['provenance']['path']).relative_to(root).as_posix()}
            _availability(root, entry)
            entries.append(entry)
    # Natural sequence breaks ties without making it-10 appear older than it-2.
    def key(entry):
        number = re.search(r'(\d+)$', entry.get('iteration_id') or '')
        return chronological(entry.get('at')), int(number.group(1)) if number else 0, entry['entry_id']
    entries.sort(key=key, reverse=True)
    payload = {'studio_id': document.get('studio_id'), 'title': document.get('title'),
               'order': 'recorded_at_desc', 'entries': entries, 'diagnostics': diagnostics}
    return {**payload, 'revision': c.content_id(payload), 'generated_at': timestamp()}


def _availability(root: Path, entry: dict) -> None:
    try:
        if not entry['result']:
            raise ValueError('no result was recorded')
        c.local(root, entry['result'])
        entry['availability'] = 'present'
    except (ValueError, OSError, TypeError) as exc:
        entry['availability'] = 'unavailable'
        entry['diagnostics'].append({'message': str(exc)})
    # Presence is a display hint, not a replacement for hash verification before use.
    if entry['diagnostics'] or entry.get('production_diagnostic'):
        entry['availability'] = 'unavailable'


def _escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _fact(label: str, value: Any, missing: str | None = "not recorded") -> str:
    if value is None or value == "":
        return "" if missing is None else f"<b>{label}</b> {missing}"
    return f"<b>{label}</b> {_escape(value)}"


def _recorded_href(value: str | None) -> str:
    """A recorded local path cannot turn into an executable or remote URL."""
    if not isinstance(value, str) or not value or '\\' in value:
        return ''
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts:
        return ''
    return './' + quote(value, safe='/')


def _relative_href(path: Path, root: Path) -> str:
    """Projection paths may be outside the Studio for an explicit snapshot."""
    return quote(os.path.relpath(path, root).replace(os.sep, '/'), safe='/')


def _text_block(entry: dict) -> str:
    if not entry.get("request_recorded"):
        return "<p><b>request</b> not recorded</p>"
    if not entry.get("prompt_fields_known"):
        return "<p><b>request</b> every field as sent is listed below; the record does not say which field held the prompt</p>"
    parts = []
    for label, key in (("prompt", "prompt"), ("negative", "negative_prompt")):
        if entry.get(key) is None:
            parts.append(f"<p><b>{label}</b> none sent</p>")
        else:
            parts.append(f"<p><b>{label}</b></p><pre>{_escape(entry[key])}</pre>")
    return "\n".join(parts)


def _history(entry: dict) -> str:
    parts = [f"received / published {_escape(entry.get('at'))}"]
    for acceptance in entry.get("acceptances") or []:
        replaced = acceptance.get("supersedes") if isinstance(acceptance, dict) else None
        parts.append(f"accepted {_escape((acceptance or {}).get('at'))}" + (f" in place of {_escape(replaced)}" if replaced else ""))
    if entry.get("superseded_by"):
        parts.append(f"superseded by {_escape(entry['superseded_by'])}")
    return "; ".join(parts)


DECISION_LABELS = {"selection": "selection reason", "disposition": "disposition reason", "rejection": "rejection reason"}


def render_entry(entry: dict) -> str:
    """One complete detail, including its recorded values and original evidence links."""
    settings = "".join(
        f"<tr><th>{_escape(key)}</th><td>{_escape(json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value)}</td></tr>"
        for key, value in sorted((entry.get("settings") or {}).items()))
    media = "".join(
        f"<tr><th>{_escape(key)}</th><td>{_escape(json.dumps(value, ensure_ascii=False))}</td></tr>"
        for key, value in sorted((entry.get("media") or {}).items()))
    service = entry.get("service") or {}
    result = _recorded_href(entry.get('result'))
    image = (f'<a href="{_escape(result)}"><img loading="lazy" decoding="async" src="{_escape(result)}" alt="{_escape(entry.get("iteration_id"))}"></a>'
             if result else '<div class="none">no local result file</div>')
    origin = " ".join(fact for fact in (
        _fact("model", service.get("model_identifier")),
        _fact("service", service.get("id"), None),
        _fact("parameter schema dated", service.get("observed_at"), None),
    ) if fact)
    record = " ".join(fact for fact in (
        _fact("model record", entry.get("model_record")),
        _fact("family", entry.get("dialect"), None),
        _fact("seed", entry.get("seed")),
    ) if fact)
    judged = " ".join(fact for fact in (
        _fact("evaluation", entry.get("evaluation"), None),
        _fact("disposition", entry.get("disposition"), None),
        _fact("selection basis", entry.get("selection_basis"), None),
        _fact("unassessed", ", ".join(entry.get("unassessed_criteria") or []), None),
    ) if fact)
    diagnostics = "".join(
        f'<p class="diagnostic">{_escape(item.get("code"))}: {_escape(item.get("message"))}</p>'
        for item in [entry.get("production_diagnostic"), *(entry.get("selection_diagnostics") or []), *(entry.get("diagnostics") or [])] if item)
    reason = (f'<p class="note">{_escape(DECISION_LABELS.get(entry.get("decision_kind"), "reason"))}: '
              f'{_escape(entry.get("reason"))}</p>') if entry.get("reason") else ""
    allowance = entry.get('owner_acceptance')
    allowance_detail = ('<details><summary>Owner allowance for this selection</summary>'
                        '<p>The recorded review remains unchanged.</p><pre>'
                        + _escape(json.dumps(allowance, ensure_ascii=False, indent=2))
                        + '</pre></details>') if allowance else ''
    links = []
    for label, key in (('Recorded request', 'request'), ('Recorded response', 'response'),
                       ('Generation package', 'package'), ('Artifact provenance', 'provenance')):
        href = _recorded_href(entry.get(key))
        if href:
            links.append(f'<a href="{_escape(href)}">{label}</a>')
    return f"""
<section class="iteration {_escape(entry.get('status'))}" data-state="{_escape(entry.get('status'))}" data-disposition="{_escape(entry.get('disposition'))}" data-availability="{_escape(entry.get('availability'))}" data-day="{_escape(utc_day(entry.get('at')))}" data-entry="{_escape(entry.get('entry_id'))}">
  <div class="image">{image}</div>
  <div class="facts">
    <h2>{_escape(entry.get('character'))} / {_escape(entry.get('slot'))} / {_escape(entry.get('iteration_id'))} <span class="status">{_escape(entry.get('status'))}</span></h2>
    <p class="when">{_history(entry)}</p>
    <p>{origin}</p><p>{record}</p>
    {('<p>' + judged + '</p>') if judged else ''}
    {diagnostics}
    {_text_block(entry)}
    <table>{settings}{media}</table>
    {('<p class="note">' + _escape(entry.get('note')) + '</p>') if entry.get('note') else ''}
    {reason}
    {allowance_detail}
    <p class="hash">{_escape(entry.get('result_sha256'))}</p>
    <nav class="evidence">{' | '.join(links)}</nav>
  </div>
</section>"""


class _SearchText(HTMLParser):
    """The complete detail's text, including collapsed values, without HTML markup."""
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def search_text(detail: str) -> str:
    parser = _SearchText()
    parser.feed(detail)
    parser.close()
    return ''.join(parser.parts)


def asset_dir(html_path: Path) -> Path:
    return html_path.with_suffix('.assets')


def entry_key(entry_id: str) -> str:
    return c.digest(entry_id.encode('utf-8'))


def detail_file(html_path: Path, entry_id: str) -> Path:
    return asset_dir(html_path) / 'entries' / (entry_key(entry_id) + '.html')


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def _script_json(value: Any) -> str:
    # These files are external scripts; escaping also makes accidental inline use inert.
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')


def _write_changed(path: Path, raw: bytes) -> dict:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError(f'gallery output is not a regular file: {path}')
    if not path.is_file() or c.read(path) != raw:
        c.atomic(path, raw, replace=True)
    return {'sha256': c.digest(raw), 'size': len(raw)}


def _matches(directory: Path, relative: str, expected: dict) -> bool:
    try:
        digest, size = c.file_digest(directory, relative)
        return digest == expected['sha256'] and size == expected['size']
    except (ValueError, OSError, KeyError, TypeError):
        return False


def _template(name: str) -> bytes:
    return (Path(__file__).resolve().parent.parent / 'templates' / name).read_bytes()


def _renderer_revision() -> str:
    return c.content_id({'owner': c.sha256_file(Path(__file__)),
                         'runtime': c.digest(_template('studio-gallery.js')),
                         'style': c.digest(_template('studio-gallery.css'))})


CONTROLS = """
<div class="gallery-controls">
<label>Order <select id="gallery-order"><option value="newest">Newest first</option><option value="oldest">Oldest first</option></select></label>
<label>Search all recorded details <input id="gallery-query" type="search" autocomplete="off"></label>
<label>State <select id="gallery-state"><option value="">All</option><option value="accepted">Accepted / current</option><option value="candidate">Candidate</option><option value="not_selected">Not selected</option><option value="superseded">History</option><option value="unavailable">Unavailable</option></select></label>
<label>From (UTC) <input id="gallery-from" type="date"></label>
<label>To (UTC) <input id="gallery-to" type="date"></label>
<label><input id="gallery-auto" type="checkbox" checked>Refresh while visible</label>
<button id="gallery-prev" type="button">Previous</button><span id="gallery-count"></span><button id="gallery-next" type="button">Next</button>
</div>
<p id="gallery-progress" role="status" aria-live="polite"></p>
"""


def _shell(index: dict, root: Path, html_path: Path) -> str:
    assets = asset_dir(html_path)
    prefix = _relative_href(assets, root)
    base = _relative_href(root, html_path.parent).rstrip('/') + '/'
    diagnostics = ('<a href="' + _escape(prefix + '/diagnostics.html') + '">Index diagnostics</a> | ') if index.get('diagnostics') else ''
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="cpb-gallery-revision" content="{_escape(index['revision'])}"><base href="{_escape(base)}"><title>{_escape(index.get('title'))}</title>
<link rel="stylesheet" href="{_escape(prefix)}/style.css">
<script defer src="{_escape(prefix)}/runtime.js"></script><script defer src="{_escape(prefix)}/index.js?revision={_escape(index['revision'])}"></script></head>
<body data-studio="{_escape(index.get('studio_id'))}" data-revision="{_escape(index['revision'])}">
<h1>{_escape(index.get('title'))} ({_escape(index.get('studio_id'))})</h1>
<p id="gallery-summary">Opening recorded artwork...</p>
<p>Newest received or published artwork first. Acceptance does not change its creation order. Display rebuilt at {_escape(index.get('generated_at'))}.</p>
<nav><a href="work/activity/timeline.md">Activity log</a> | <a href="work/activity/timeline.jsonl">Machine-readable log</a> | {diagnostics}<a href="{_escape(_relative_href(html_path.with_suffix('.json'), root))}">Complete gallery JSON</a></nav>
{CONTROLS}
<main id="gallery-entries" aria-live="polite"></main>
<noscript>This gallery uses local JavaScript files for paging and search. Every record remains in the complete gallery JSON and its linked source files.</noscript>
</body></html>
"""


def _detail_page(entry: dict, rendered: str, root: Path, html_path: Path) -> str:
    target = detail_file(html_path, entry['entry_id'])
    base = _relative_href(root, target.parent).rstrip('/') + '/'
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><base href="{_escape(base)}"><title>{_escape(entry['entry_id'])}</title><link rel="stylesheet" href="{_escape(_relative_href(asset_dir(html_path) / 'style.css', root))}"></head>
<body><nav><a href="{_escape(_relative_href(html_path, root))}">Back to gallery</a> | <a href="{_escape(_relative_href(html_path.with_suffix('.json'), root))}">Complete gallery JSON</a></nav>
{rendered}
</body></html>
"""


def _card(entry: dict, root: Path, html_path: Path) -> dict:
    """Only fields needed to browse, order and filter; full text stays in entry assets."""
    key = entry_key(entry['entry_id'])
    prefix = _relative_href(asset_dir(html_path) / 'entries' / key, root)
    service = entry.get('service') or {}
    return {
        'key': key, 'revision': c.content_id(entry), 'entry_id': entry['entry_id'],
        **{field: entry.get(field) for field in ('character', 'iteration_id', 'slot', 'at', 'status', 'disposition', 'availability', 'evaluation', 'selection_basis', 'seed')},
        'day': utc_day(entry.get('at')), 'model': service.get('model_identifier') or entry.get('model_record'),
        'result': _recorded_href(entry.get('result')), 'detail': prefix + '.html', 'search': prefix + '.search.js',
        'diagnostic_count': len(entry.get('diagnostics') or []) + len(entry.get('selection_diagnostics') or []) + bool(entry.get('production_diagnostic')),
    }


def publish(root: Path, index: dict, out: Path | None = None) -> tuple[Path, Path]:
    """Publish an offline view, replacing only changed generated bytes.

    Stable filenames belong to entries, not to their successive status revisions.
    Formal artwork and evidence are read-only. Each explicit output has its own
    assets, so another view's update never changes a saved snapshot.
    """
    root = c._root(root)
    html_path = Path(out or root / 'gallery.html').absolute().resolve()
    c._root(html_path.parent)
    json_path, assets = html_path.with_suffix('.json'), asset_dir(html_path)
    if json_path == html_path:
        raise ValueError('gallery HTML and JSON need distinct output paths')
    if assets.is_symlink() or (assets.exists() and not assets.is_dir()):
        raise ValueError(f'gallery assets are not a regular directory: {assets}')
    owner = {'kind': 'studio-gallery-projection', 'studio_id': index.get('studio_id'), 'view': html_path.name}
    owner_path = assets / 'owner.json'
    if owner_path.exists():
        if c.load(owner_path) != owner:
            raise ValueError(f'gallery assets belong to another output: {assets}')
    elif assets.exists() and any(assets.iterdir()):
        raise ValueError(f'gallery assets directory has no generated ownership record: {assets}')
    assets.mkdir(parents=True, exist_ok=True)
    _write_changed(owner_path, _json_bytes(owner))
    previous = {}
    manifest_path = assets / 'manifest.json'
    if manifest_path.is_file():
        try:
            previous = c.load(manifest_path)
            if (not isinstance(previous, dict) or not isinstance(previous.get('files'), dict)
                    or not isinstance(previous.get('entries'), dict)):
                previous = {}
        except (ValueError, OSError):
            previous = {}
    index = copy.deepcopy(index)
    if json_path.is_file():
        try:
            held = c.load(json_path)
            if isinstance(held, dict) and held.get('revision') == index['revision'] and held.get('generated_at'):
                index['generated_at'] = held['generated_at']
        except (ValueError, OSError):
            pass
    layout_revision = c.content_id({'renderer': _renderer_revision(), 'title': index.get('title'),
                                   'studio_id': index.get('studio_id'), 'view': _relative_href(html_path, root)})
    manifest = {'kind': owner['kind'], 'revision': index['revision'], 'layout_revision': layout_revision,
                'files': {}, 'entries': {}}
    def emit(relative: str, raw: bytes) -> None:
        path = c.local(assets, relative, exists=False)
        manifest['files'][relative] = _write_changed(path, raw)
    emit('runtime.js', _template('studio-gallery.js'))
    emit('style.css', _template('studio-gallery.css'))
    cards = []
    for entry in index['entries']:
        card = _card(entry, root, html_path)
        cards.append(card)
        key, revision = card['key'], card['revision']
        paths = [f'entries/{key}.html', f'entries/{key}.search.js']
        held_entry = (previous.get('entries') or {}).get(key) or {}
        held_files = previous.get('files') or {}
        reusable = (previous.get('layout_revision') == layout_revision and held_entry.get('revision') == revision
                    and all(isinstance(held_files.get(path), dict) and _matches(assets, path, held_files[path]) for path in paths))
        if reusable:
            for path in paths:
                manifest['files'][path] = held_files[path]
        else:
            rendered = render_entry(entry)
            emit(paths[0], _detail_page(entry, rendered, root, html_path).encode('utf-8'))
            emit(paths[1], ('CPBGallery.searchDocument(' + ','.join(_script_json(value) for value in
                             (key, revision, search_text(rendered))) + ');\n').encode('utf-8'))
        manifest['entries'][key] = {'entry_id': entry['entry_id'], 'revision': revision}
    emit('diagnostics.html', (f'<!DOCTYPE html><html lang="en"><meta charset="utf-8"><title>Gallery diagnostics</title>'
                              f'<pre>{_escape(json.dumps(index.get("diagnostics") or [], ensure_ascii=False, indent=2))}</pre></html>').encode('utf-8'))
    emit('index.js', ('CPBGallery.start(' + _script_json({'revision': index['revision'], 'cards': cards}) + ');\n').encode('utf-8'))
    _write_changed(json_path, _json_bytes(index))
    _write_changed(html_path, _shell(index, root, html_path).encode('utf-8'))
    _write_changed(manifest_path, _json_bytes(manifest))
    return html_path, json_path


def stale(root: Path) -> str | None:
    """Check the complete projection and its owned assets against recorded artwork."""
    json_path, html_path = root / 'gallery.json', root / 'gallery.html'
    if not json_path.is_file() or not html_path.is_file():
        return 'gallery.json or gallery.html is missing'
    try:
        held, expected = c.load(json_path), build_index(root)
        if (not isinstance(held, dict) or {key: value for key, value in held.items() if key != 'generated_at'}
                != {key: value for key, value in expected.items() if key != 'generated_at'}):
            return 'gallery.json does not list what the artwork records hold'
        marker = '<meta name="cpb-gallery-revision" content="' + expected['revision'] + '">'
        if marker not in c.read(html_path).decode('utf-8'):
            return 'gallery.html does not match the recorded gallery revision; run studio.py sync'
        assets = asset_dir(html_path)
        owner = {'kind': 'studio-gallery-projection', 'studio_id': expected.get('studio_id'), 'view': html_path.name}
        if c.load(c.local(assets, 'owner.json')) != owner:
            return 'gallery assets have an incorrect ownership record'
        manifest = c.load(c.local(assets, 'manifest.json'))
        if not isinstance(manifest, dict):
            return 'gallery assets manifest is not an object; run studio.py sync'
        layout_revision = c.content_id({'renderer': _renderer_revision(), 'title': expected.get('title'),
                                       'studio_id': expected.get('studio_id'), 'view': _relative_href(html_path, root)})
        keys = {entry_key(entry['entry_id']): {'entry_id': entry['entry_id'], 'revision': c.content_id(entry)} for entry in expected['entries']}
        if (manifest.get('revision') != expected['revision'] or manifest.get('layout_revision') != layout_revision
                or manifest.get('entries') != keys):
            return 'gallery assets do not match the recorded gallery revision; run studio.py sync'
        files = manifest.get('files') or {}
        required = {'runtime.js', 'style.css', 'index.js', 'diagnostics.html'}
        required.update(f'entries/{key}{suffix}' for key in keys for suffix in ('.html', '.search.js'))
        if set(files) != required or any(not _matches(assets, path, files[path]) for path in required):
            return 'gallery assets are missing or changed; run studio.py sync'
    except (ValueError, OSError, TypeError, KeyError) as exc:
        return f'gallery projection cannot be read: {exc}'
    return None
