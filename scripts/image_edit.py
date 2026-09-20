#!/usr/bin/env python3
"""Execute pinned still-image operations through the production run's edit grants.

The selected direction stays unchanged. Repairs of direction or criteria use
production_workflow.revise instead. Outputs are new candidates, never approvals.
"""
from __future__ import annotations

import argparse
import io
import json
import math
from pathlib import Path
from typing import Any

import execution_contract as c
import production_plan as direction
import production_workflow as w



def dimensions(width: Any, height: Any) -> tuple[int, int]:
    if type(width) is not int or type(height) is not int or min(width, height) < 1:
        raise ValueError('built-in editor dimensions must be positive integers')
    return width, height


def finite(value: Any, label: str) -> float:
    if type(value) not in {int, float} or not math.isfinite(value):
        raise ValueError(label + ' must be a finite number')
    return float(value)


def _image(raw: bytes):
    from PIL import Image
    try:
        with Image.open(io.BytesIO(raw)) as image:
            dimensions(*image.size)
            if getattr(image, 'n_frames', 1) != 1:
                raise ValueError('the editor requires one still image, not a timed sequence')
            image.verify()
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            return image.convert('RGBA')
    except (OSError, SyntaxError) as exc:
        raise ValueError('source must decode as an actual still image') from exc


def _rotation_size(width: int, height: int, degrees: float, expand: bool) -> tuple[int, int]:
    """Match the default-center rotation canvas before allocating it."""
    if not expand:
        return width, height
    angle = degrees % 360
    if angle in {0, 180}:
        return width, height
    if angle in {90, 270}:
        return height, width
    angle = -math.radians(angle)
    a, b, d, e = round(math.cos(angle), 15), round(math.sin(angle), 15), round(-math.sin(angle), 15), round(math.cos(angle), 15)
    cx, cy = width / 2, height / 2
    c0, f0 = cx - a * cx - b * cy, cy - d * cx - e * cy
    points = [(a * x + b * y + c0, d * x + e * y + f0)
              for x, y in ((0, 0), (width, 0), (width, height), (0, height))]
    return math.ceil(max(x for x, _ in points)) - math.floor(min(x for x, _ in points)), math.ceil(max(y for _, y in points)) - math.floor(min(y for _, y in points))


def _compile(root: Path, run: str, filename: str, *, allow_output: bool = False) -> dict:
    """Read/validate all inputs without executing edits or reserving permission."""
    directory, prepared, _, rows = w.assert_current(root, run)
    w.find(rows, 'handoff')
    if prepared['task']['artifact'] != 'image':
        raise ValueError('image editing requires an image deliverable')
    raw = c.read(c.local(root, filename))
    value = c.decode(raw)
    w.schema_check(value, 'image-edit')
    c.exact(value, {'input_sha256', 'source', 'operations', 'output', 'targets', 'repair', 'reason', 'limitations'}, 'image edit')
    if value['input_sha256'] != prepared['input_sha256']:
        raise ValueError('image edit belongs to another prepared input')
    c.text(value['reason'], 'image edit reason')
    direction.strings(value['limitations'], 'image edit limitations')
    targets = direction.strings(value['targets'], 'image edit targets', nonempty=True)
    allowed = {'delivery'} | {'decision:' + d['id'] for d in prepared['task']['direction']['decisions']}
    if set(targets) - allowed:
        raise ValueError('pixel edits target delivery or declared decisions, not changes to the production contract')
    applied_paths = {s['path'] for s in prepared['task']['sources'] if s['disposition'] == 'applied'}
    pinned = {d['path']: d['sha256'] for d in prepared['dependencies'] if d['space'] == 'project' and d['path'] in applied_paths}
    candidate_sources: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        if row['event'] == 'candidate':
            for item in row['data']['files']:
                pinned[item['path']] = item['sha256']
                candidate_sources.setdefault((item['path'], item['sha256']), []).append(row)
    used: dict[str, bytes] = {}
    def source(spec: Any) -> tuple[int, int]:
        c.exact(spec, {'path', 'sha256'}, 'image source')
        c.sha(spec['sha256'])
        if pinned.get(spec['path']) != spec['sha256']:
            raise ValueError('image sources must be pinned project inputs or captured candidates')
        data = c.read(c.local(root, spec['path']))
        if c.digest(data) != spec['sha256']:
            raise ValueError('image source changed')
        used[spec['path']] = data
        with _image(data) as image:
            return image.size
    width, height = source(value['source'])
    operations = value['operations']
    if not isinstance(operations, list) or not operations:
        raise ValueError('built-in editor requires a nonempty operation list')
    from PIL import ImageColor
    for op in operations:
        if not isinstance(op, dict):
            raise ValueError('image operation must be an object')
        kind = op.get('operation')
        if kind == 'crop':
            c.exact(op, {'operation', 'box'}, 'crop')
            box = op['box']
            if not isinstance(box, list) or len(box) != 4 or any(type(x) is not int for x in box):
                raise ValueError('crop needs four integer pixel boundaries')
            left, top, right, bottom = box
            if not 0 <= left < right <= width or not 0 <= top < bottom <= height:
                raise ValueError('crop exceeds the current canvas')
            width, height = right - left, bottom - top
        elif kind == 'resize':
            c.exact(op, {'operation', 'width', 'height'}, 'resize')
            width, height = dimensions(op['width'], op['height'])
        elif kind == 'rotate':
            c.exact(op, {'operation', 'degrees', 'expand', 'fill'}, 'rotate')
            angle = finite(op['degrees'], 'rotation')
            if type(op['expand']) is not bool:
                raise ValueError('rotation expand must be boolean')
            c.text(op['fill'], 'rotation fill')
            ImageColor.getcolor(op['fill'], 'RGBA')
            width, height = dimensions(*_rotation_size(width, height, angle, op['expand']))
        elif kind == 'composite':
            c.exact(op, {'operation', 'source', 'x', 'y', 'opacity'}, 'composite')
            if type(op['x']) is not int or type(op['y']) is not int:
                raise ValueError('composite position uses integer pixels')
            if not 0 <= finite(op['opacity'], 'opacity') <= 1:
                raise ValueError('opacity must be within [0,1]')
            source(op['source'])
        else:
            raise ValueError('unsupported built-in image operation')
    output = c.local(root, value['output'], exists=False)
    if (output.suffix.lower() != '.png' or (value['output'] in pinned and not allow_output) or value['output'] == filename
            or any(part.startswith('.') for part in Path(value['output']).parts)
            or Path(value['output']).parts[0] == 'production'):
        raise ValueError('output must be a new PNG outside inputs and internal record directories')
    if output.exists() and not allow_output:
        raise ValueError('output already exists; inputs and previous outputs are never overwritten')
    repair_binding = None
    repair = value['repair']
    primary = candidate_sources.get((value['source']['path'], value['source']['sha256']), [])
    if repair is not None:
        c.exact(repair, {'candidate', 'repair'}, 'review repair')
        candidate = w.find(rows, 'candidate', repair['candidate'])
        if candidate not in primary:
            raise ValueError('repair must concern the primary source candidate')
        reviewed = w.latest_review(rows, candidate['sha256'])
        matches = [r for r in reviewed['data']['review']['repairs'] if r['id'] == repair['repair']]
        if len(matches) != 1 or set(targets) - set(matches[0]['targets']):
            raise ValueError('edit exceeds the latest reviewed repair targets')
        repair_binding = {**repair, 'review': reviewed['sha256']}
    elif any(r['event'] == 'review' and r['data']['candidate'] in {x['sha256'] for x in primary} for r in rows):
        raise ValueError('an already reviewed source candidate needs an explicit latest review repair')
    intent = {'operation': 'edit', 'targets': sorted(targets),
              'payload': {'tool': 'image-edit', 'plan_path': filename, 'plan_sha256': c.digest(raw),
                          'output': value['output'], 'repair': repair_binding,
                          'sources': [{'path': p, 'sha256': c.digest(b)} for p, b in sorted(used.items())]}}
    return {'intent': intent, 'plan': value, 'raw': raw, 'sources': used, 'size': (width, height)}


def edit_intent(root: Path, run: str, filename: str) -> dict:
    with c.lock(root):
        return _compile(root, run, filename)['intent']


def _render(compiled: dict) -> bytes:
    from PIL import Image
    value = compiled['plan']
    result = _image(compiled['sources'][value['source']['path']])
    for op in value['operations']:
        kind = op['operation']
        if kind == 'crop':
            result = result.crop(op['box'])
        elif kind == 'resize':
            result = result.resize((op['width'], op['height']), Image.Resampling.LANCZOS)
        elif kind == 'rotate':
            result = result.rotate(op['degrees'], resample=Image.Resampling.BICUBIC,
                                   expand=op['expand'], fillcolor=op['fill'])
        elif kind == 'composite':
            with _image(compiled['sources'][op['source']['path']]) as overlay:
                overlay.putalpha(overlay.getchannel('A').point(lambda n: round(n * op['opacity'])))
                result.alpha_composite(overlay, (op['x'], op['y']))
        dimensions(*result.size)
    if result.size != compiled['size']:
        raise ValueError('rendered canvas differs from the validated plan')
    stream = io.BytesIO()
    result.save(stream, format='PNG')
    return stream.getvalue()


def _publish(root: Path, run: str, claim: dict) -> dict:
    directory, prepared, _, rows = w.assert_current(root, run)
    ready = [r for r in rows if r['event'] == 'image-edit-output' and r['data']['claim'] == claim['sha256']]
    if len(ready) != 1:
        raise ValueError('edit has no retained output; inspect its claim before explicitly authorizing new work')
    result = ready[0]
    item = result['data']['output']
    output = c.local(root, item['path'], exists=False)
    data = c.object_read(directory, item['sha256'])
    if output.exists():
        if c.read(output) != data:
            raise ValueError('retained edit output conflicts with an existing file')
    else:
        c.atomic(output, data)
    recorded = w.file_record(root, directory, item['path'])
    handoff = w.find(rows, 'handoff')
    return w.append_record(directory, prepared, rows, 'candidate',
                           {'handoff': handoff['sha256'], 'files': [recorded],
                            'media': w.media.inspect(data, 'image'), 'note': claim['data']['reason'],
                            'image_edit': result['sha256'], 'limitations': claim['data']['limitations']})


def execute(root: Path, run: str, filename: str, authorization: str) -> dict:
    with c.lock(root):
        directory, prepared, _, rows = w.assert_current(root, run)
        prior = [r for r in rows if r['event'] == 'image-edit-claim' and authorization in r['data']['authorizations']]
        if prior:
            # Retry means record the exact retained output, never spend or render again.
            claim = prior[-1]
            if claim['data']['intent']['payload']['plan_path'] != filename:
                raise ValueError('edit authorization already belongs to another plan')
            w._permission(root, prepared, rows, authorization, **claim['data']['intent'])
            if _compile(root, run, filename, allow_output=True)['intent'] != claim['data']['intent']:
                raise ValueError('edit review or plan changed; cannot recover under an obsolete permission')
            return _publish(root, run, claim)
        w.require_mutable(rows)
        compiled = _compile(root, run, filename)
        intent = compiled['intent']
        w._permission(root, prepared, rows, authorization, **intent)
        if any(authorization in r['data'].get('authorizations', []) for r in rows if r['event'] != 'authorization'):
            raise ValueError('edit authorization has already been consumed')
        files = [w.file_record(root, directory, filename)]
        if c.object_read(directory, files[0]['sha256']) != compiled['raw']:
            raise ValueError('edit plan changed during validation')
        evidence = [w.file_record(root, directory, p) for p in compiled['sources']]
        if any(c.object_read(directory, f['sha256']) != compiled['sources'][f['path']] for f in evidence):
            raise ValueError('source changed during validation')
        claim = w.append_record(directory, prepared, rows, 'image-edit-claim',
                                {'intent': intent, 'authorizations': [authorization], 'files': files,
                                 'evidence': evidence, 'reason': compiled['plan']['reason'],
                                 'limitations': compiled['plan']['limitations']})
    # A failed computation leaves the reservation/claim. It never creates a new permission.
    raw = _render(compiled)
    with c.lock(root):
        directory, prepared, _, rows = w.assert_current(root, run)
        w._permission(root, prepared, rows, authorization, **intent)
        if _compile(root, run, filename)['intent'] != intent:
            raise ValueError('edit plan or review changed during execution')
        digest = c.object_store(directory, raw)
        output = {'path': compiled['plan']['output'], 'sha256': digest, 'size': len(raw)}
        w.append_record(directory, prepared, rows, 'image-edit-output',
                        {'claim': claim['sha256'], 'output': output})
        return _publish(root, run, claim)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('intent', 'execute'):
        sub = commands.add_parser(name)
        sub.add_argument('--root', required=True, type=Path)
        sub.add_argument('--run', required=True)
        sub.add_argument('--plan', required=True)
        if name == 'execute':
            sub.add_argument('--authorization', required=True)
    args = parser.parse_args()
    try:
        result = edit_intent(args.root.absolute(), args.run, args.plan) if args.command == 'intent' else execute(args.root.absolute(), args.run, args.plan, args.authorization)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, UnicodeError, KeyError, ImportError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
