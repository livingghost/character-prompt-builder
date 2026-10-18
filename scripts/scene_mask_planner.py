#!/usr/bin/env python3
"""Build and verify source-bound edit masks for the production dispatcher.

The agent supplies named regions and reviews their meaning. This module checks
pixels, provenance and coverage, and stages the exact mask as request media.
"""
from __future__ import annotations

import argparse
import copy
import io
import json
import math
from pathlib import Path
import shutil
import tempfile
from typing import Any, Callable

import execution_contract as c

FORMAT = 'cpb-scene-mask-plan'
BUNDLE = 'cpb-scene-mask-bundle'
BINDING = 'cpb-scene-mask-binding'
FEATURE = 'scene-mask-planning'


def _image(raw: bytes, *, mask: bool = False, size: tuple | None = None):
    from PIL import Image
    try:
        with Image.open(io.BytesIO(raw)) as opened:
            if getattr(opened, 'n_frames', 1) != 1:
                raise ValueError('A scene mask input must be one still image.')
            opened.load()
            if opened.getexif().get(274, 1) != 1:
                raise ValueError('Normalize orientation before annotating a scene mask.')
            if size is not None and opened.size != size:
                raise ValueError('Region dimensions differ from the annotated source.')
            if mask and opened.mode not in {'1', 'L'}:
                raise ValueError('Use grayscale masks; RGB and alpha masks have ambiguous polarity.')
            image = opened.convert('L' if mask else 'RGB')
    except (OSError, SyntaxError) as exc:
        raise ValueError('Input is not a decodable still image.') from exc
    return image


def _png(image) -> bytes:
    output = io.BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()


def _count(mask) -> int:
    return sum(mask.histogram()[1:])


def _strings(value: Any, label: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        raise ValueError(label + ' must be an explicit list.')
    for item in value:
        c.text(item, label)
    if len(set(value)) != len(value):
        raise ValueError(label + ' has duplicate identifiers.')
    return value


def _reader(root: Path, captured: dict | None = None, read: Callable | None = None):
    seen = {} if captured is None else captured
    def read_ref(ref: dict) -> bytes:
        c.exact(ref, {'path', 'sha256'}, 'scene mask input reference')
        c.sha(ref['sha256'])
        c.local(root, ref['path'])
        if ref['path'] not in seen:
            from production_store import stable_bytes
            seen[ref['path']] = read(ref['path']) if read else stable_bytes(root, ref['path'])
        data = seen[ref['path']]
        if c.digest(data) != ref['sha256']:
            raise ValueError('Scene mask source changed: ' + ref['path'])
        return data
    return read_ref, seen


def compile_plan(root: Path, plan: dict, *, read: Callable | None = None) -> dict:
    """Check explicit regions; geometry success is not an artistic approval."""
    from PIL import Image, ImageChops, ImageFilter
    c.exact(plan, {'format', 'source', 'regions', 'selected', 'required', 'feather', 'unresolved'}, 'scene mask plan')
    if plan['format'] != FORMAT:
        raise ValueError('Unknown scene mask plan format.')
    read_ref, captured = _reader(root, read=read)
    source = _image(read_ref(plan['source']))
    size = source.size
    radius = plan['feather']
    if type(radius) not in {int, float} or not math.isfinite(radius) or radius < 0:
        raise ValueError('Mask feather must be a finite nonnegative number.')
    if not isinstance(plan['regions'], list) or not plan['regions']:
        raise ValueError('Declare named regions before mask assembly.')
    regions = {}
    protected = Image.new('L', size)
    for row in plan['regions']:
        c.exact(row, {'id', 'role', 'image', 'provenance'}, 'scene mask region')
        identifier = c.text(row['id'], 'region id')
        if identifier in regions:
            raise ValueError('Duplicate region: ' + identifier)
        if row['role'] not in {'garment', 'extension', 'protect'}:
            raise ValueError('Unknown region role: ' + identifier)
        c.text(row['provenance'], 'region extraction/annotation provenance')
        mask = _image(read_ref(row['image']), mask=True, size=size)
        hist = mask.histogram()
        if sum(hist[1:255]):
            raise ValueError('Region annotations must use binary black/white pixels: ' + identifier)
        if not hist[255]:
            raise ValueError('Empty region: ' + identifier)
        regions[identifier] = (row, mask)
        if row['role'] == 'protect':
            protected = ImageChops.lighter(protected, mask)
    if not _count(protected):
        raise ValueError('Explicit protected regions are required.')
    selected = _strings(plan['selected'], 'selected regions', nonempty=True)
    required = _strings(plan['required'], 'required regions', nonempty=True)
    unresolved = _strings(plan['unresolved'], 'unresolved region decisions')
    for identifier in set(selected + required):
        if identifier not in regions or regions[identifier][0]['role'] == 'protect':
            raise ValueError('An edit/required region is absent or protected: ' + identifier)
    union = Image.new('L', size)
    for identifier in selected:
        union = ImageChops.lighter(union, regions[identifier][1])
    overlap = _count(ImageChops.multiply(union, protected))
    hard = ImageChops.subtract(union, protected)
    findings = []
    if overlap:
        findings.append({'code': 'PROTECTED_OVERLAP', 'pixels': overlap})
    coverage = []
    for identifier in required:
        wanted = regions[identifier][1]
        missing = _count(ImageChops.subtract(wanted, hard))
        coverage.append({'region': identifier, 'pixels': _count(wanted), 'missing_pixels': missing})
        if missing:
            findings.append({'code': 'REQUIRED_REGION_MISSING', 'region': identifier, 'pixels': missing})
    if unresolved:
        findings.append({'code': 'UNRESOLVED_REGIONS', 'items': unresolved})
    if not _count(hard):
        findings.append({'code': 'EMPTY_EDIT_MASK'})
    # Feather inward, then enforce support again. Never re-binarize a feathered
    # mask at >0, which would expand the edit into a protected face or hand.
    soft = hard.filter(ImageFilter.GaussianBlur(radius)) if radius else hard.copy()
    soft = ImageChops.multiply(soft, hard)
    soft = ImageChops.subtract(soft, protected)
    for identifier in required:
        missing = _count(ImageChops.subtract(regions[identifier][1], soft.point(lambda x: 255 if x else 0)))
        if missing:
            findings.append({'code': 'FEATHER_ERASED_REGION', 'region': identifier, 'pixels': missing})
    report = {'format': 'cpb-scene-mask-report', 'source_sha256': plan['source']['sha256'],
              'dimensions': list(size), 'definition_sha256': c.content_id(plan),
              'geometry_valid': not findings, 'findings': findings, 'coverage': coverage,
              'editable_pixels': _count(soft), 'protected_overlap_pixels': _count(ImageChops.multiply(soft, protected)),
              'semantic_review_required': True, 'segmentation_correctness_inferred': False}
    return {'plan': copy.deepcopy(plan), 'source': source, 'mask': soft, 'protection': protected,
            'mask_bytes': _png(soft), 'report': report, 'inputs': captured}


def _publish(root: Path, out: str, files: dict[str, bytes]) -> Path:
    target = c.local(root, out, exists=False)
    if target.exists() or target == root.resolve():
        raise FileExistsError('Use a new mask output directory; existing work is preserved.')
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.scene-mask-', dir=target.parent))
    try:
        for name, raw in files.items():
            c.atomic(c.local(stage, name, exists=False), raw)
        c.publish_directory(stage, target)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return target


def build(root: Path, plan_path: str, out: str) -> dict:
    from PIL import Image
    from production_store import stable_bytes
    raw = stable_bytes(root, plan_path)
    data = compile_plan(root, c.decode(raw))
    report = data['report']
    source = data['source'].convert('RGBA')
    tint = Image.new('RGBA', source.size, (220, 55, 170, 0))
    tint.putalpha(data['mask'].point(lambda x: round(x * .40)))
    source.alpha_composite(tint)
    mask_ref = {'path': out + '/mask.png', 'sha256': c.digest(data['mask_bytes'])}
    bundle = {'format': BUNDLE, 'definition': data['plan'], 'definition_sha256': c.content_id(data['plan']), 'mask': mask_ref}
    review = {'format': 'cpb-scene-mask-review', 'bundle_sha256': c.content_id(bundle),
              'reviewer': '', 'verdict': None, 'observations': [], 'unresolved': []}
    files = {'report.json': c.encoded(report), 'overlay.png': _png(source),
             'review-template.json': c.encoded(review)}
    if report['geometry_valid']:
        files.update({'mask.png': data['mask_bytes'], 'bundle.json': c.encoded(bundle)})
    # Recheck exactly the bytes just used before publishing a complete directory.
    for path, data_raw in {plan_path: raw, **data['inputs']}.items():
        if stable_bytes(root, path) != data_raw:
            raise ValueError('Mask input changed during assembly: ' + path)
    _publish(root, out, files)
    return report


def validate_binding(root: Path, binding: dict, *, read: Callable | None = None) -> dict:
    c.exact(binding, {'format', 'bundle', 'review', 'guidance'}, 'scene mask binding')
    if binding['format'] != BINDING:
        raise ValueError('Unknown mask binding format.')
    read_ref, captured = _reader(root, read=read)
    bundle = c.decode(read_ref(binding['bundle']))
    c.exact(bundle, {'format', 'definition', 'definition_sha256', 'mask'}, 'mask bundle')
    if bundle['format'] != BUNDLE or bundle['definition_sha256'] != c.content_id(bundle['definition']):
        raise ValueError('Mask bundle definition hash mismatch.')
    def cached(path):
        if path not in captured:
            from production_store import stable_bytes
            captured[path] = read(path) if read else stable_bytes(root, path)
        return captured[path]
    result = compile_plan(root, bundle['definition'], read=cached)
    captured.update(result['inputs'])
    if not result['report']['geometry_valid']:
        raise ValueError('Mask geometry is invalid: ' + json.dumps(result['report']['findings']))
    raw_mask = read_ref(bundle['mask'])
    decoded = _image(raw_mask, mask=True, size=result['source'].size)
    if decoded.tobytes() != result['mask'].tobytes():
        raise ValueError('Saved mask does not equal its declared region assembly.')
    review = c.decode(read_ref(binding['review']))
    c.exact(review, {'format', 'bundle_sha256', 'reviewer', 'verdict', 'observations', 'unresolved'}, 'mask review')
    if review['format'] != 'cpb-scene-mask-review' or review['bundle_sha256'] != c.content_id(bundle):
        raise ValueError('Mask review refers to another mask bundle.')
    c.text(review['reviewer'], 'mask reviewer')
    if review['verdict'] != 'ready' or _strings(review['unresolved'], 'unresolved mask review'):
        raise ValueError('Complete the mask review before generation.')
    ids = {row['id'] for row in bundle['definition']['regions']
           if row['id'] in bundle['definition']['selected'] or row['role'] == 'protect'}
    seen = set()
    if not isinstance(review['observations'], list):
        raise ValueError('Mask observations must be a list.')
    for row in review['observations']:
        c.exact(row, {'region', 'observation'}, 'mask observation')
        if row['region'] not in ids or row['region'] in seen:
            raise ValueError('Unknown or repeated mask review region.')
        c.text(row['observation'], 'mask observation')
        seen.add(row['region'])
    if seen != ids:
        raise ValueError('Review every selected and protected region before generation.')
    guidance = binding['guidance']
    if guidance is not None:
        _image(read_ref(guidance))
    result.update({'binding': copy.deepcopy(binding), 'bundle': bundle, 'review': review,
                   'inputs': captured, 'raw_mask': raw_mask})
    return result


def bind(root: Path, *, bundle_path: str, review_path: str, guidance_path: str | None, out: str) -> dict:
    from production_store import stable_bytes
    def ref(path):
        return {'path': path, 'sha256': c.digest(stable_bytes(root, path))}
    binding = {'format': BINDING, 'bundle': ref(bundle_path), 'review': ref(review_path),
               'guidance': ref(guidance_path) if guidance_path else None}
    validate_binding(root, binding)
    c.atomic(c.local(root, out, exists=False), c.encoded(binding))
    return binding


def check_task(root: Path, task: dict, binding: dict, *, read: Callable) -> dict:
    if FEATURE not in task['features']:
        raise ValueError('A scene mask binding requires feature ' + FEATURE)
    if task['artifact'] != 'image' or task['execution'] != 'dispatcher':
        raise ValueError('Scene mask binding requires dispatched still-image generation.')
    result = validate_binding(root, binding, read=read)
    source = result['bundle']['definition']['source']
    if not any(row['path'] == source['path'] and row['disposition'] == 'applied' for row in task['sources']):
        raise ValueError('Declare the mask source as an applied production source.')
    return result


def stage_media(verified: dict, checked: dict, offering: dict, directory: Path) -> None:
    """Use source media for composition and add a mask plus optional guidance."""
    forwarding = verified['host_forwarding']
    if forwarding['reference_media_role'] != 'seed-image':
        raise ValueError('This mask workflow needs image-to-image with one explicit seed-image transport.')
    primary = forwarding['selected_references']
    expected = checked['bundle']['definition']['source']['sha256']
    if len(primary) != 1 or c.digest(c.read(Path(primary[0]['resolved_path']))) != expected:
        raise ValueError('The dispatched source image differs from the annotated scene.')
    source_size = tuple(checked['report']['dimensions'])
    parameters = forwarding['parameters']
    if 'width' in parameters and 'height' in parameters and (parameters['width'], parameters['height']) != source_size:
        raise ValueError('Source and dispatch dimensions must match; resize before annotating.')
    # Native mask media belongs in the same immutable carrier companion.
    # The execution journal retains that complete directory before any upload.
    companion = Path(primary[0]['resolved_path']).relative_to(directory).parts[0]
    if not companion.endswith('.references'):
        raise ValueError('Source carrier is not inside its sealed reference companion.')
    media = []
    pairs = [('mask image', checked['bundle']['mask'])]
    if checked['binding']['guidance']:
        pairs.append(('reference images', checked['binding']['guidance']))
    for role, ref in pairs:
        keys = offering.get('request_keys', {}).get(role)
        if not isinstance(keys, list) or not keys:
            raise ValueError('The selected offering has no native ' + role + ' field.')
        from request_contract import path_parts
        field = path_parts(keys[0])
        raw = checked['inputs'][ref['path']]
        suffix = Path(ref['path']).suffix.lower()
        target = directory / companion / 'scene-mask-media' / (ref['sha256'] + suffix)
        if target.exists():
            if c.read(target) != raw:
                raise ValueError('Native media staging collision.')
        else:
            c.atomic(target, raw)
        media.append({'resolved_path': str(target), 'role': role,
                      'field': field, 'many': role == 'reference images'})
    forwarding['technical_media'] = media


def write_media(verified: dict, writer, layout: dict, offering: dict, media_ids: dict) -> None:
    """Both built-in transports use this one ordered supplementary media writer."""
    from request_contract import MANAGEMENT_VALUE
    offset = len(layout['media'])
    for index, row in enumerate(verified['host_forwarding'].get('technical_media', []), offset):
        value = media_ids.get(row['resolved_path'], MANAGEMENT_VALUE)
        field = row['field']
        writer.write(field, [value] if row['many'] else value,
                     source_kind='reference-binding', source_refs=[{'kind': 'scene-mask', 'role': row['role']}],
                     transform_id='verified-scene-mask-media')
        location = field + [0] if row['many'] else field
        layout['media'].append({'index': index, 'field': location})
        layout['fields'].append({'id': f'media:{index + 1}', 'field': location, 'kind': 'media'})


def compare(root: Path, binding_path: str, candidate_path: str, out: str) -> dict:
    from PIL import ImageChops
    checked = validate_binding(root, c.load(c.local(root, binding_path)))
    candidate_raw = __import__('production_store').stable_bytes(root, candidate_path)
    candidate = _image(candidate_raw, size=checked['source'].size)
    difference = ImageChops.difference(checked['source'], candidate)
    channels = difference.split()
    maximum = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
    from PIL import ImageOps
    outside = ImageOps.invert(checked['mask'].point(lambda x: 255 if x else 0))
    selected = ImageChops.multiply(maximum, outside)
    report = {'format': 'cpb-scene-mask-comparison', 'candidate_sha256': c.digest(candidate_raw),
              'source_sha256': checked['bundle']['definition']['source']['sha256'],
              'changed_pixels_outside_mask': _count(selected),
              'max_channel_delta_outside_mask': max((i for i, n in enumerate(selected.histogram()) if n), default=0),
              'quality_verdict': 'not-assessed', 'note': 'Pixel difference is evidence, not garment or identity acceptance.'}
    _publish(root, out, {'comparison.json': c.encoded(report), 'outside-difference.png': _png(selected)})
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('build', 'refine', 'bind', 'compare'):
        item = sub.add_parser(command)
        item.add_argument('--root', type=Path, required=True)
        item.add_argument('--out', required=True)
        if command in ('build', 'refine'):
            item.add_argument('--plan', required=True)
        elif command == 'bind':
            item.add_argument('--bundle', required=True)
            item.add_argument('--review', required=True)
            item.add_argument('--guidance')
        else:
            item.add_argument('--binding', required=True)
            item.add_argument('--candidate', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'refine':
            from scene_mask_refinement import refine
            result = refine(args.root, args.plan, args.out)
        elif args.command == 'build':
            result = build(args.root, args.plan, args.out)
        elif args.command == 'bind':
            result = bind(args.root, bundle_path=args.bundle, review_path=args.review, guidance_path=args.guidance, out=args.out)
        else:
            result = compare(args.root, args.binding, args.candidate, args.out)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result.get('geometry_valid') is False else 0


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
