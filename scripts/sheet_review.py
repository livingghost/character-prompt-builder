"""Reproducible sheet comparison evidence; no artistic verdict is computed."""
from __future__ import annotations
import copy
import io
import math
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Sequence

import execution_contract as c
import sheet_artifacts as fills


def _rectangle(value: Any, width: int, height: int, *, label: str) -> list[int]:
    if value is None:
        return [0, 0, width, height]
    if not isinstance(value, list) or len(value) != 4 or any(type(v) is not int for v in value):
        raise ValueError(label + ' must be integer x,y,width,height')
    x, y, w, h = value
    if x < 0 or y < 0 or min(w, h) < 1 or x + w > width or y + h > height:
        raise ValueError(label + ' is outside the image')
    return list(value)


def _crop(image, rectangle):
    x, y, width, height = rectangle
    return image.crop((x, y, x + width, y + height))


def measure(image, region: dict, rectangle: list[int] | None = None) -> dict:
    """Exact RGB-to-HSV values; hue median is unwrapped at the selected hue start.

    H uses degrees, S and V use [0,1]. A hue interval may cross zero. Transparent
    pixels never count; all thresholds and the minimum population are reported.
    An empty or undersized selected population is not a zero difference.
    """
    import numpy as np
    c.exact(region, {'id', 'hue', 'saturation', 'value', 'minimum_pixels', 'rois'}, 'HSV region')
    c.text(region['id'], 'HSV region ID')
    bounds = {}
    for channel, maximum in [('hue',360),('saturation',1),('value',1)]:
        pair = region[channel]
        if not isinstance(pair, list) or len(pair) != 2 or any(type(v) not in (int,float) or not math.isfinite(v) or not 0 <= v <= maximum for v in pair):
            raise ValueError(channel + ' range is invalid')
        if channel != 'hue' and pair[0] > pair[1]:
            raise ValueError(channel + ' range is reversed')
        if channel == 'hue' and pair[0] == pair[1]:
            raise ValueError('hue range must cover a nonempty interval; use [0,360] for the whole circle')
        bounds[channel] = pair
    if type(region['minimum_pixels']) is not int or region['minimum_pixels'] < 1 or not isinstance(region['rois'], dict):
        raise ValueError('minimum_pixels must be positive and rois must map labels to rectangles')
    roi = _rectangle(rectangle, image.width, image.height, label='measurement ROI')
    rgba = np.asarray(_crop(image.convert('RGBA'),roi), dtype=np.float32) / 255.0
    rgb, alpha = rgba[...,:3], rgba[...,3]
    maximum, minimum = rgb.max(axis=-1), rgb.min(axis=-1)
    delta = maximum - minimum
    saturation = np.divide(delta, maximum, out=np.zeros_like(delta), where=maximum>0)
    hue = np.zeros_like(delta)
    nonzero = delta>0
    for channel, offset in ((0,0),(1,2),(2,4)):
        selected = nonzero & (rgb[...,channel] == maximum)
        numerator = rgb[...,(channel+1)%3] - rgb[...,(channel+2)%3]
        value = np.divide(numerator, delta, out=np.zeros_like(delta), where=nonzero) + offset
        hue[selected] = (value[selected] * 60) % 360
    lo, hi = bounds['hue']
    hue_selected = ((hue >= lo) & (hue <= hi)) if lo < hi else ((hue >= lo) | (hue <= hi))
    sl, sh = bounds['saturation']; vl, vh = bounds['value']
    visible = alpha > 0
    mask = visible & hue_selected & (saturation >= sl) & (saturation <= sh) & (maximum >= vl) & (maximum <= vh)
    count, population = int(mask.sum()), int(visible.sum())
    sufficient = count >= region['minimum_pixels']
    median = None
    if sufficient:
        median = {'h': float(np.median((hue[mask] - lo) % 360) + lo) % 360,
                  's': float(np.median(saturation[mask])), 'v': float(np.median(maximum[mask]))}
    return {'roi': roi, 'roi_pixel_count': roi[2]*roi[3], 'visible_pixel_count': population,
            'selected_pixel_count': count, 'selected_fraction': count/population if population else 0.0,
            'state': 'measured' if sufficient else 'insufficient-pixels', 'median': median}


def _resolve(item: dict, *, anchor: bool, documents: dict | None = None, verified: dict | None = None) -> tuple[dict, Any]:
    from PIL import Image
    c.exact(item, {'sheet', 'slot', 'artifact_id', 'label', 'head'}, 'review artwork')
    c.text(item['label'], 'review label')
    sidecar = Path(item['sheet']).resolve(strict=True)
    documents = {} if documents is None else documents
    if sidecar not in documents:
        documents[sidecar] = fills._read(sidecar)
    state = documents[sidecar]
    slot = state['slots'].get(item['slot'])
    if slot is None:
        raise ValueError('review names an unknown sheet slot')
    current = fills.current_artifact(slot)
    if anchor:
        artifact = current
        if artifact is None or (item['artifact_id'] is not None and item['artifact_id'] != artifact['artifact_id']):
            raise ValueError('review anchor must be the stated currently accepted artwork')
    else:
        choices = [*slot['candidates'], *[entry['artifact'] for entry in slot['history']], *([current] if current else [])]
        artifact = next((entry for entry in choices if entry['artifact_id'] == item['artifact_id']),None)
        if artifact is None: raise ValueError('review artwork is not recorded in the stated slot')
    if anchor:
        fills.verify_acceptance(slot['current'], sidecar.parent, item['slot'], cache=verified)
    else:
        fills.verify_artifact(artifact, sidecar.parent, cache=verified)
    raw = c.read(fills._file(sidecar.parent,artifact['image']['path'],artifact['image']['sha256']))
    with Image.open(io.BytesIO(raw)) as source:
        image = source.convert('RGBA')
    if item['head'] is not None:
        _rectangle(item['head'],image.width,image.height,label='head crop')
    return {**item,'sheet':str(sidecar),'artifact':copy.deepcopy(artifact)}, image


def _label(draw, xy: tuple[int,int], text: str, max_width: int) -> None:
    """Use the repository's bundled/system font coverage, retaining full labels in JSON."""
    from PIL import ImageFont
    from character_sheet_render.textmetrics import segment_text_by_font
    x,y = xy
    try:
        runs = segment_text_by_font('regular',text)
        for path, run in runs:
            font = ImageFont.truetype(str(path),16)
            width = draw.textlength(run,font=font)
            if x+width>xy[0]+max_width:
                # Labels are identifiers, not evidence. The JSON preserves the full text.
                draw.text((x,y),'…',font=font,fill='#111111'); break
            draw.text((x,y),run,font=font,fill='#111111'); x+=width
    except (ValueError,OSError,ImportError):
        draw.text((x,y),text[:70],fill='#111111')


def _montage(anchor, candidates, *, heads: bool, cell: int):
    from PIL import Image, ImageOps, ImageDraw
    gutter, title = 16, 36
    canvas = Image.new('RGB',(2*cell+3*gutter,len(candidates)*(cell+title+gutter)+gutter),'#ffffff')
    draw = ImageDraw.Draw(canvas)
    for index, candidate in enumerate(candidates):
        top = gutter + index*(cell+title+gutter)
        for column, (item,image) in enumerate((anchor,candidate)):
            left = gutter + column*(cell+gutter)
            _label(draw,(left,top),('Anchor: ' if column==0 else 'Candidate: ')+item['label'],cell)
            if heads and item['head'] is None:
                _label(draw,(left,top+title),'Head crop not supplied; no anatomy inferred.',cell)
                continue
            selected = _crop(image,item['head']) if heads else image
            reduced = ImageOps.contain(selected,(cell,cell),Image.Resampling.LANCZOS)
            background = Image.new('RGBA',(cell,cell),'#ffffff')
            background.alpha_composite(reduced,((cell-reduced.width)//2,(cell-reduced.height)//2))
            canvas.paste(background.convert('RGB'),(left,top+title))
    return canvas


def build_review(anchor: dict, candidates: Sequence[dict], regions: Sequence[dict], *, out_dir: Path,
                 cell_size: int = 500, pairs_per_page: int = 6) -> dict:
    """Verify each selected artifact once and decode only one page of images at a time."""
    if not candidates:
        raise ValueError('review requires at least one candidate')
    if type(cell_size) is not int or not 100 <= cell_size <= 2000 or type(pairs_per_page) is not int or not 1<=pairs_per_page<=12:
        raise ValueError('invalid review cell size or page length')
    labels = [item['label'] for item in [anchor, *candidates]]
    if len(set(labels)) != len(labels):
        raise ValueError('review labels must be unique, including the anchor')
    ids = [item['id'] for item in regions]
    if len(set(ids)) != len(ids):
        raise ValueError('HSV region IDs must be unique')
    for region in regions:
        unknown = set(region['rois']) - set(labels)
        if unknown:
            raise ValueError('measurement ROI names an unknown artwork label: ' + ', '.join(sorted(unknown)))
    out_dir = out_dir.absolute()
    if out_dir.exists() or out_dir.is_symlink():
        raise ValueError('review output must be a new directory')
    if any(parent.is_symlink() for parent in out_dir.parents):
        raise ValueError('review output must not traverse a symbolic link')
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    documents, verified = {}, {}
    resolved_anchor = _resolve(anchor, anchor=True, documents=documents, verified=verified)
    report = {'artifact_type':'sheet-review-evidence', 'anchor':resolved_anchor[0],
              'candidates':[], 'regions':copy.deepcopy(list(regions)),
              'method':{'rgb':'8-bit decoded RGB; alpha=0 excluded', 'hue':'degrees, median unwrapped at interval start',
                        'saturation_value':'[0,1]', 'delta_hue':'signed shortest difference in [-180,180)',
                        'cell_size':cell_size, 'pairs_per_page':pairs_per_page},
              'measurements':[], 'montages':{'full':[], 'head':[]},
              'limitations':['Pixel statistics do not assess shape, markings, anatomy, laterality or identity.',
                             'Insufficient selected pixels are missing evidence, not a small difference.',
                             'Head crops and measurement regions are supplied by the author; no segmentation is inferred.'],
              'decision':'author-required'}
    staging = Path(tempfile.mkdtemp(prefix='.sheet-review-', dir=out_dir.parent))
    try:
        for region in regions:
            baseline = measure(resolved_anchor[1], region, region['rois'].get(resolved_anchor[0]['label']))
            report['measurements'].append({'region':region['id'], 'anchor':baseline, 'candidates':[]})
        for start in range(0, len(candidates), pairs_per_page):
            page = []
            try:
                for item in candidates[start:start + pairs_per_page]:
                    page.append(_resolve(item, anchor=False, documents=documents, verified=verified))
                report['candidates'].extend(item for item, _ in page)
                for region, comparison in zip(regions, report['measurements']):
                    baseline = comparison['anchor']
                    for item, image in page:
                        measured = measure(image, region, region['rois'].get(item['label']))
                        delta = None
                        if baseline['median'] is not None and measured['median'] is not None:
                            left, right = baseline['median'], measured['median']
                            delta = {'h':(right['h']-left['h']+180)%360-180, 's':right['s']-left['s'], 'v':right['v']-left['v']}
                        comparison['candidates'].append({'label':item['label'], 'artifact_id':item['artifact']['artifact_id'],
                                                        **measured, 'delta_from_anchor':delta})
                for kind in ('full', 'head'):
                    image = _montage(resolved_anchor, page, heads=kind=='head', cell=cell_size)
                    try:
                        raw = io.BytesIO(); image.save(raw, format='PNG')
                        name = f'{kind}-{start//pairs_per_page+1:03d}.png'
                        c.atomic(staging / name, raw.getvalue())
                        report['montages'][kind].append({'path':name, 'sha256':c.sha256_file(staging/name),
                                                        'width':image.width, 'height':image.height})
                    finally:
                        image.close()
            finally:
                for _, image in page:
                    image.close()
        c.atomic(staging / 'review.json', c.encoded(report))
        c.publish_directory(staging, out_dir)
    finally:
        resolved_anchor[1].close()
        if staging.exists():
            shutil.rmtree(staging)
    import studio_activity as activity
    report['projection'] = activity.changed(Path(anchor['sheet']), 'sheet-review-created',
        subject=str(out_dir), revision=c.sha256_file(out_dir/'review.json'),
        details={'candidates':len(candidates), 'pages':len(report['montages']['full']), 'decision':'author-required'})
    return report
