"""Fit existing garment boundaries to source pixels within an explicit search band.

Called by scene_mask_planner.py refine. This is constrained GrabCut, not semantic
recognition or image generation. Extension and protection annotations stay fixed.
"""
from __future__ import annotations

import copy
from pathlib import Path
import threading
import tempfile

import execution_contract as c

_LOCK = threading.Lock()
FORMAT = 'cpb-scene-mask-refinement'


def _integer(value, name, *, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(name + ' must be an integer >= ' + str(minimum))
    return value


def fit_region(source, proposal, protection, *, inside, outside, iterations, seed,
               foreground=None, background=None):
    """Keep certain foreground/protection, fit only the explicitly uncertain band."""
    import cv2
    import numpy as np
    from PIL import Image

    inside = _integer(inside, 'inside', minimum=1)
    outside = _integer(outside, 'outside')
    iterations = _integer(iterations, 'iterations', minimum=1)
    seed = _integer(seed, 'seed')
    if seed > 2147483647:
        raise ValueError('seed must fit the OpenCV signed 32-bit seed field.')
    size = proposal.size
    if source.size != size or protection.size != size:
        raise ValueError('Source, proposal and protection dimensions differ.')
    binary = np.asarray(proposal) == 255
    locked = np.asarray(protection) > 0
    if np.any(binary & locked):
        raise ValueError('Resolve the proposed edit/protection overlap before refinement.')
    if not binary.any():
        raise ValueError('An empty proposal cannot supply foreground evidence.')
    # Explicit zero padding defines distances at the image edge.
    padded = np.pad(binary.astype(np.uint8), 1)
    inner = cv2.distanceTransform(padded, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)[1:-1, 1:-1]
    away = cv2.distanceTransform(1 - padded, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)[1:-1, 1:-1]
    certain = binary & (inner > inside)
    support = (binary | (away <= outside)) & ~locked
    excluded = ~support | locked

    for supplied, kind in ((foreground, 'foreground'), (background, 'background')):
        if supplied is not None and (supplied.size != size or supplied.mode != 'L'):
            raise ValueError(kind + ' points must be same-canvas grayscale masks.')
        if supplied is not None and sum(supplied.histogram()[1:255]):
            raise ValueError(kind + ' points must be binary.')
    if foreground is not None:
        fg = np.asarray(foreground) > 0
        if np.any(fg & ~support):
            raise ValueError('Foreground points leave the declared search band or enter protection.')
        certain |= fg
    if background is not None:
        excluded |= np.asarray(background) > 0
    if np.any(certain & excluded):
        raise ValueError('Certain foreground and background assignments conflict.')

    # Keep a certain seed in EACH component, including separated sleeve fragments.
    count, labels = cv2.connectedComponents(binary.astype(np.uint8), connectivity=8)
    seedless = [i for i in range(1, count) if not np.any(certain & (labels == i))]
    if seedless:
        raise ValueError('A proposed component has no certain foreground: ' + str(seedless) +
                         '. Add included points or reduce inside; do not discard that component.')
    if not excluded.any():
        raise ValueError('Declare certain background pixels for boundary refinement.')

    # Four classes are essential: passing only 0/1 makes the initial contour fixed.
    classes = np.full(binary.shape, cv2.GC_BGD, np.uint8)
    classes[support & ~binary] = cv2.GC_PR_BGD
    classes[binary & support] = cv2.GC_PR_FGD
    classes[certain] = cv2.GC_FGD
    classes[excluded] = cv2.GC_BGD
    initial = classes.copy()
    bg_model = np.zeros((1, 65), dtype=np.float64)
    fg_model = np.zeros((1, 65), dtype=np.float64)
    try:
        with _LOCK:
            # A fresh CLI process is the reproducible execution boundary.
            cv2.setRNGSeed(seed)
            cv2.grabCut(np.asarray(source.convert('RGB'))[:, :, ::-1].copy(), classes,
                        None, bg_model, fg_model, iterations, cv2.GC_INIT_WITH_MASK)
    except cv2.error as exc:
        raise ValueError('GrabCut could not fit the declared foreground/background samples: ' + str(exc)) from exc
    result = (classes == cv2.GC_FGD) | (classes == cv2.GC_PR_FGD)
    if np.any(result & excluded) or np.any(certain & ~result):
        raise ValueError('Boundary refinement violated a hard constraint.')
    mask = Image.fromarray((result.astype(np.uint8) * 255))
    report = {
        'proposal_pixels': int(binary.sum()), 'refined_pixels': int(result.sum()),
        'added_pixels': int((result & ~binary).sum()), 'removed_pixels': int((binary & ~result).sum()),
        'protected_overlap_pixels': int((result & locked).sum()),
        'certain_foreground_pixels': int(certain.sum()), 'proposal_components': count - 1,
        'seeded_components': count - 1, 'search_inside_px': inside, 'search_outside_px': outside,
        'iterations': iterations, 'seed': seed, 'opencv_version': cv2.__version__,
        'numpy_version': np.__version__, 'semantic_acceptance': 'unreviewed',
        'new_image_generated': False,
    }
    return mask, report, Image.fromarray(initial)


def refine(root: Path, specification_path: str, out: str):
    import cv2
    import numpy as np
    from PIL import Image, ImageChops
    import scene_mask_planner as m
    from production_store import stable_bytes

    output_target = c.local(root, out, exists=False)
    if output_target.exists() or output_target == root.resolve():
        raise FileExistsError('Use a new refinement directory; previous work is preserved.')
    raw = stable_bytes(root, specification_path)
    spec = c.decode(raw)
    c.exact(spec, {'format', 'plan', 'regions'}, 'mask refinement specification')
    if spec['format'] != FORMAT:
        raise ValueError('Unknown boundary refinement format.')
    read, captured = m._reader(root)
    plan_raw = read(spec['plan'])
    original = c.decode(plan_raw)
    checked = m.compile_plan(root, original)
    captured.update(checked['inputs'])
    if not checked['report']['geometry_valid']:
        raise ValueError('Fix the source plan geometry before refining boundaries.')
    if not isinstance(spec['regions'], list) or not spec['regions']:
        raise ValueError('Declare at least one garment region for refinement.')
    plan = copy.deepcopy(original)
    by_id = {row['id']: row for row in plan['regions']}
    seen, reports, files = set(), [], {}
    for index, row in enumerate(spec['regions']):
        c.exact(row, {'region', 'inside', 'outside', 'iterations', 'seed', 'foreground', 'background'},
                'boundary refinement region')
        identifier = c.text(row['region'], 'refinement region')
        if identifier in seen or identifier not in by_id:
            raise ValueError('Unknown or repeated refinement region: ' + identifier)
        seen.add(identifier)
        target = by_id[identifier]
        if target['role'] != 'garment':
            raise ValueError('Refine existing garments only; keep protection and new-garment extensions explicit.')
        proposal = m._image(read(target['image']), mask=True, size=checked['source'].size)
        samples = {name: m._image(read(row[name]), mask=True, size=proposal.size)
                   if row[name] is not None else None for name in ('foreground', 'background')}
        # A sleeve/front boundary is not an exterior edge of the edit. Preserve
        # union-interior pixels so independent region fits cannot open seam holes.
        inside = _integer(row['inside'], 'inside', minimum=1)
        union = (np.asarray(checked['mask']) > 0).astype(np.uint8)
        union_distance = cv2.distanceTransform(np.pad(union, 1), cv2.DIST_L2,
            cv2.DIST_MASK_PRECISE)[1:-1, 1:-1]
        seam_seeds = Image.fromarray(((np.asarray(proposal) > 0) &
            (union_distance > inside)).astype(np.uint8) * 255)
        samples['foreground'] = ImageChops.lighter(seam_seeds, samples['foreground'])             if samples['foreground'] is not None else seam_seeds
        result, detail, classes = fit_region(checked['source'], proposal, checked['protection'],
            inside=row['inside'], outside=row['outside'], iterations=row['iterations'], seed=row['seed'], **samples)
        detail['region'] = identifier
        detail['union_interior_preserved'] = True
        detail['input_mask_sha256'] = target['image']['sha256']
        relative = f'regions/region-{index:03d}.png'
        result_raw = m._png(result)
        files[relative] = result_raw
        files[f'classes/region-{index:03d}.png'] = m._png(classes)
        target['image'] = {'path': out + '/' + relative, 'sha256': c.digest(result_raw)}
        target['provenance'] = ('Source-pixel GrabCut boundary refinement; source ' + original['source']['sha256'] +
            '; specification ' + c.digest(raw) + '; initial region ' + detail['input_mask_sha256'] +
            '; OpenCV ' + cv2.__version__ + '; semantics require review.')
        detail['output_mask_sha256'] = target['image']['sha256']
        reports.append(detail)

    # Validate a complete isolated snapshot before publishing anything in Studio.
    with tempfile.TemporaryDirectory(prefix='cpb-refine-check-') as td:
        snapshot = Path(td)
        for name, content in captured.items():
            c.atomic(c.local(snapshot, name, exists=False), content)
        for name, content in files.items():
            c.atomic(c.local(snapshot, out + '/' + name, exists=False), content)
        final = m.compile_plan(snapshot, plan)
    if not final['report']['geometry_valid']:
        raise ValueError('Refined annotations do not assemble into valid geometry: ' + str(final['report']['findings']))
    before = checked['source'].convert('RGBA')
    tint = Image.new('RGBA', before.size, (220, 55, 170, 0))
    tint.putalpha(final['mask'].point(lambda x: round(x * .4)))
    before.alpha_composite(tint)
    delta = ImageChops.difference(checked['mask'], final['mask'])
    report = {'format': 'cpb-scene-mask-refinement-report', 'specification_sha256': c.digest(raw),
        'source_sha256': original['source']['sha256'], 'regions': reports,
        'geometry_valid': final['report']['geometry_valid'], 'semantic_review_required': True,
        'source_image_modified': False, 'automatic_subject_recognition': False,
        'inputs': [{'path': p, 'sha256': c.digest(data)} for p, data in sorted(captured.items())],
        'protected_overlap_pixels': final['report']['protected_overlap_pixels'],
        'changed_mask_pixels': m._count(delta), 'quality_verdict': 'not-assessed'}
    files.update({'refined-plan.json': c.encoded(plan), 'refinement-report.json': c.encoded(report),
                  'overlay.png': m._png(before), 'mask-difference.png': m._png(delta),
                  'specification.json': raw})
    for p, before_raw in {specification_path: raw, **captured}.items():
        if stable_bytes(root, p) != before_raw:
            raise ValueError('Refinement input changed during processing: ' + p)
    m._publish(root, out, files)
    return report
