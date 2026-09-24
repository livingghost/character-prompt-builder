#!/usr/bin/env python3
"""Bind one bounded production consumer to a Generation Package."""
from __future__ import annotations
from pathlib import Path
from typing import Any
import execution_contract as c


def create(root: Path | None, run: str | None, prompt: str) -> dict[str,Any] | None:
    if root is None and run is None:
        return None  # Explicit low-level packaging, not evidence of production completion.
    if root is None or run is None: raise ValueError('production root and run are both required')
    from production_workflow import assert_current
    _,prepared,consumer,_=assert_current(root.absolute(),run)
    if consumer['instructions'].strip()!=prompt.strip(): raise ValueError('composition prompt differs from the prepared delivery')
    result={'run':run,'input_sha256':prepared['input_sha256'],'consumer':consumer,
            'consumer_sha256':c.content_id(consumer),'composition_sha256':c.digest(prompt.strip().encode('utf-8'))}
    result['sha256']=c.content_id(result)
    return result


def validate(binding: Any, prompt: str) -> None:
    if binding is None: return
    c.exact(binding,{'run','input_sha256','consumer','consumer_sha256','composition_sha256','sha256'},'production binding')
    import uuid
    identifier=uuid.UUID(binding['run'])
    if identifier.version!=7 or str(identifier)!=binding['run']: raise ValueError('invalid production run identity')
    c.sha(binding['input_sha256'])
    obj=dict(binding); expected=obj.pop('sha256')
    if c.content_id(obj)!=expected or c.content_id(binding['consumer'])!=binding['consumer_sha256']:
        raise ValueError('production binding integrity mismatch')
    consumer=binding['consumer']
    c.exact(consumer,{'route','transport','instructions','criteria','direction','world_views','moment_views','authoring_materials'},'bounded consumer')
    if not isinstance(consumer['authoring_materials'], list):
        raise ValueError('authoring_materials must be an array')
    for material in consumer['authoring_materials']:
        if not isinstance(material, dict) or material.get('audience') != 'authoring':
            raise ValueError('scene material is author-only input')
        c.text(material.get('document'), 'scene material document')
        c.sha(material.get('content_sha256'))
    from production_plan import validate_consumer
    validate_consumer(consumer['direction'])
    if consumer['transport'] not in {'authored-rendition','bounded-context'}: raise ValueError('invalid production transport')
    if c.digest(prompt.strip().encode('utf-8'))!=binding['composition_sha256'] or consumer['instructions'].strip()!=prompt.strip():
        raise ValueError('production binding composition mismatch')


def effective(binding: Any, original: str, *, context_transport: str | None = None) -> str:
    """Render only the conversion explicitly chosen for this consumer."""
    if binding is None:
        return original
    consumer = binding['consumer']
    if consumer['transport'] == 'authored-rendition':
        return original
    if consumer['transport'] != 'bounded-context':
        raise ValueError('invalid production transport')
    if context_transport != 'prompt-prefix':
        raise ValueError('bounded context requires an explicit prompt-prefix execution policy')
    context = {'direction': consumer['direction'], 'criteria': consumer['criteria'],
               'world_views': consumer['world_views'], 'moment_views': consumer['moment_views']}
    return ('Production context (hard constraints and advisory choices are distinct):\n'
            + c.encoded(context).decode('utf-8') + '\n' + original)


def validate_live(root: Path | None, run: str | None, package: dict[str,Any]) -> None:
    binding=package['production_binding']
    if binding is None:
        if root is not None or run is not None: raise ValueError('package is not bound to production')
        return
    if root is None or run is None: raise ValueError('a bound package needs its production root and run')
    expected=create(root,run,package['composition_prompt'])
    if binding!=expected: raise ValueError('package belongs to a different or stale production input')


def upscale_request(root: Path, source: Path, model: str, scale: float,
                    settings: dict, guidance: str | None, *, request_validation: dict, render_intent: dict) -> dict:
    """Describe exact local inputs before the submit authorization is issued."""
    import math
    if isinstance(scale, bool) or not isinstance(scale, (int, float)) or not math.isfinite(scale) or scale <= 0:
        raise ValueError('upscale factor must be positive and finite')
    c.text(model, 'upscale model')
    if not isinstance(settings, dict):
        raise ValueError('upscale settings must be an object')
    if guidance is not None:
        c.text(guidance, 'upscale guidance')
    from render_contract_lib import validate_intent
    validate_intent(render_intent, for_generation=bool(guidance), prompt=guidance)
    if render_intent['execution_mode'] != 'upscale':
        raise ValueError('upscale request needs an upscale rendering intent')
    root = root.absolute()
    source = source.absolute()
    try:
        relative = source.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError('copy the upscale source into the project before preparing the request') from exc
    source = c.local(root, relative)
    value = {'artifact_type': 'upscale-request',
             'source': {'path': relative, 'sha256': c.digest(c.read(source))},
             'model': model, 'scale_factor': float(scale), 'settings': settings,
             'guidance_prompt': guidance, 'render_intent': render_intent}
    import input_contracts
    reader, _ = input_contracts.capture_validation(request_validation, root=root)
    input_contracts.attach(value, request_validation, reader)
    c.encoded(value)  # Reject non-finite or unsupported JSON settings.
    return value


def validate_upscale_live(root: Path, run: str, request: dict) -> None:
    """The prepared delivery and source snapshot, not a chat description, authorize input."""
    c.exact(request, {'artifact_type', 'source', 'model', 'scale_factor', 'settings', 'guidance_prompt', 'render_intent',
                      'request_validation', 'request_validation_sha256', 'input_snapshots', 'input_snapshots_sha256'}, 'upscale request')
    if request['artifact_type'] != 'upscale-request':
        raise ValueError('expected an upscale-request declaration')
    c.exact(request['source'], {'path', 'sha256'}, 'upscale source')
    expected = upscale_request(root, c.local(root, request['source']['path']), request['model'],
                               request['scale_factor'], request['settings'], request['guidance_prompt'],
                               request_validation=request['request_validation'], render_intent=request['render_intent'])
    if request != expected:
        raise ValueError('upscale source differs from the prepared request')
    from production_workflow import assert_current
    _, prepared, consumer, _ = assert_current(root, run)
    if prepared['task']['route'] != 'upscale' or prepared['task']['execution'] != 'dispatcher' or prepared['task']['artifact'] != 'image':
        raise ValueError('upscale needs an image task on the upscale dispatcher route')
    if c.decode(consumer['instructions'].encode('utf-8')) != request:
        raise ValueError('upscale request differs from the prepared delivery')
    if not any(x['space'] == 'project' and x['path'] == request['source']['path']
               and x['sha256'] == request['source']['sha256'] for x in prepared['dependencies']):
        raise ValueError('upscale source must be pinned among the prepared task sources')


def main() -> int:
    import argparse
    import json
    parser = argparse.ArgumentParser(description='Write an exact upscale input declaration; no upload or submission.')
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--source', required=True, help='Project-relative source image')
    parser.add_argument('--model', required=True, help='Resolved model record identifier')
    parser.add_argument('--scale', required=True, type=float)
    parser.add_argument('--settings', default='{}')
    parser.add_argument('--guidance')
    parser.add_argument('--render-intent', required=True, type=Path, help='Explicit source finish and upscale intent')
    parser.add_argument('--request-validation-file', required=True, type=Path,
                        help='Explicit validation record, with evidence paths relative to the project.')
    parser.add_argument('--out', required=True, help='New project-relative declaration file')
    args = parser.parse_args()
    try:
        value = upscale_request(args.root, c.local(args.root, args.source), args.model, args.scale,
                                c.decode(args.settings.encode('utf-8')), args.guidance,
                                request_validation=c.load(args.request_validation_file), render_intent=c.load(args.render_intent))
        c.atomic(c.local(args.root, args.out, exists=False), c.encoded(value))
        print(json.dumps({'ok': True, 'request': args.out, 'content_sha256': c.content_id(value)}, indent=2))
        return 0
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))
    return 1


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
