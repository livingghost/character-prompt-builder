"""Chronological gallery projection for generated, imported and locally derived artwork.

A missing old file is a diagnostic on its entry, not a reason to hide new work.
Only records are enumerated; filesystem modification times and guessed filenames
never determine chronology or acceptance.
"""
from __future__ import annotations
from pathlib import Path
import copy
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


def build_index(root: Path) -> dict:
    import studio
    import sheet_inventory
    document = studio.manifest(root)
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
            rows = studio.read_iterations(home)
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
                     'unassessed_criteria': row.get('unassessed_criteria'), 'production_diagnostic': row.get('production_diagnostic'),
                     'selection_diagnostics': row.get('selection_diagnostics') or [], 'acceptances': row.get('acceptances') or [],
                     'superseded_by': row.get('superseded_by'), 'service': row.get('service'), 'seed': row.get('seed'),
                     **studio.sent_text(sent, row.get('request_layout')),
                     'result': (row.get('result') or {}).get('path'), 'result_sha256': (row.get('result') or {}).get('sha256'),
                     'package': (row.get('package') or {}).get('path'), 'note': row.get('note'), 'reason': row.get('reason'),
                     'decision_kind': row.get('decision_kind') if row.get('production') else ('rejection' if row.get('status') == 'rejected' else None),
                     'diagnostics': errors, 'sheet_state': None, 'artifact_id': None}
            _availability(root, entry)
            entries.append(entry); by_iteration[row.get('iteration_id')] = entry
        sidecar = home / 'sheet/sheet-data.json'
        if not sidecar.is_file():
            continue
        try:
            artwork = sheet_inventory.entries(sidecar)
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
                     'evaluation': None, 'disposition': None, 'unassessed_criteria': [], 'selection_diagnostics': [],
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


CONTROLS = '''<nav class="gallery-controls" aria-label="Gallery filters">
<label>Order <select id="gallery-order"><option value="newest">Newest recorded first</option><option value="oldest">Oldest recorded first</option></select></label>
<label>Character / slot / prompt <input id="gallery-query" type="search" placeholder="Filter this gallery"></label>
<label>State <select id="gallery-state"><option value="">All</option><option value="accepted">Current accepted</option><option value="candidate">Candidates</option><option value="not_selected">Not selected</option><option value="superseded">History</option><option value="unavailable">Unavailable</option></select></label>
<label>From <input id="gallery-from" type="date"></label><label>To <input id="gallery-to" type="date"></label>
<label><input id="gallery-auto" type="checkbox" checked> Refresh every 30 seconds</label>
<button id="gallery-prev" type="button">Previous</button><span id="gallery-count" aria-live="polite"></span><button id="gallery-next" type="button">Next</button>
</nav>'''

SCRIPT = r'''<script>
(() => {
  const root=document.getElementById('gallery-entries');
  const all=[...root.querySelectorAll('section.iteration')];
  const ids=['gallery-order','gallery-query','gallery-state','gallery-from','gallery-to','gallery-auto'];
  const storage='cpb-gallery:'+document.body.dataset.studio;
  let page=0;const pageSize=40;
  try{const saved=JSON.parse(sessionStorage.getItem(storage)||'null');if(saved){page=saved.page||0;for(const id of ids){const el=document.getElementById(id);if(id==='gallery-auto')el.checked=saved[id]!==false;else if(saved[id]!==undefined)el.value=saved[id]}}}catch(e){}
  function remember(){try{const saved={page};for(const id of ids){const el=document.getElementById(id);saved[id]=id==='gallery-auto'?el.checked:el.value}sessionStorage.setItem(storage,JSON.stringify(saved))}catch(e){}}
  function render(){
    const query=document.getElementById('gallery-query').value.toLowerCase();const state=document.getElementById('gallery-state').value;
    const from=document.getElementById('gallery-from').value, to=document.getElementById('gallery-to').value;
    let rows=all.filter(el=>(!query||el.textContent.toLowerCase().includes(query))&&(!state||el.dataset.state===state||el.dataset.disposition===state||el.dataset.availability===state)&&(!from||el.dataset.day>=from)&&(!to||el.dataset.day<=to));
    if(document.getElementById('gallery-order').value==='oldest')rows.reverse();
    const pages=Math.max(1,Math.ceil(rows.length/pageSize));page=Math.max(0,Math.min(page,pages-1));
    for(const el of all)el.hidden=true;
    for(const el of rows.slice(page*pageSize,(page+1)*pageSize)){el.hidden=false;root.appendChild(el)}
    document.getElementById('gallery-count').textContent=rows.length+' results / page '+(page+1)+' of '+pages;
    document.getElementById('gallery-prev').disabled=page===0;document.getElementById('gallery-next').disabled=page+1>=pages;
    remember();
  }
  for(const id of ids)document.getElementById(id).addEventListener('input',()=>{page=0;render()});
  document.getElementById('gallery-prev').onclick=()=>{page--;render()};document.getElementById('gallery-next').onclick=()=>{page++;render()};
  render();
  // Reload the self-contained HTML even under file://; no local JSON fetch or
  // disabled browser security is required. Filters and page survive refresh.
  setInterval(()=>{if(document.getElementById('gallery-auto').checked&&!document.hidden){remember();location.reload()}},30000);
})();
</script>'''
