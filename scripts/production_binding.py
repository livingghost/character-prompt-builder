#!/usr/bin/env python3
"""Bind one bounded production consumer to a Generation Package, and read the studio files a package CLI names.

The package CLIs resolve every studio file the same way: an absolute path is
taken as given, and a relative path is a '/'-separated path below the explicit
studio root. They refuse an existing output, and report a failure as
`{"ok": false, "diagnostics": [...]}` with the exit status its codes select in
production_diagnostics.
"""
from __future__ import annotations
import operation_context as _operation_context
import json
from pathlib import Path
from typing import Any
import execution_contract as c


def studio_file(root: Path | None, value: str | Path, *, option: str, root_option: str = '--root',
                 exists: bool = True) -> Path:
    """The file one CLI option names: an absolute path, or a '/'-separated path below the studio root.

    A backslash or a leading './' is refused with the root-relative form to
    write instead, so a relative path never depends on the working directory.
    """
    from production_diagnostics import ProductionError
    text = str(value)

    def refuse(code: str, message: str, action: str):
        raise ProductionError(code, message, phase='arguments', file=text, required_action=action, option=option)

    if Path(text).is_absolute():
        path = Path(text)
        if exists and not path.is_file():
            refuse('INPUT_UNREADABLE', f'{option} names no file: {text}', f'Check the path given to {option}.')
        return path
    suggestion = text.replace('\\', '/')
    while suggestion.startswith('./'):
        suggestion = suggestion[2:]
    if suggestion != text:
        refuse('INPUT_SCHEMA_INVALID', f'{option} is not a /-separated studio-relative path: {text}',
               f'Write {option} {suggestion}, relative to {root_option}, or give an absolute path.')
    if root is None:
        refuse('INPUT_SCHEMA_INVALID', f'{option} is relative and no studio root is given: {text}',
               f'Pass {root_option} STUDIO, or give {option} an absolute path.')
    try:
        path = c.local(Path(root), text, exists=False)
    except ValueError as exc:
        refuse('INPUT_SCHEMA_INVALID', f'{option}: {exc}: {text}',
               f'Write {option} as a /-separated path inside {root_option}, or give an absolute path.')
    if exists and not path.is_file():
        refuse('INPUT_UNREADABLE', f'{option} names no file below {root_option}: {text}',
               f'Check the path; {option} is read relative to {root_option}.')
    return path


def new_output(root: Path | None, value: str | Path, *, option: str, root_option: str = '--root') -> Path:
    """The new file an output option names; an existing file is kept and refused."""
    path = studio_file(root, value, option=option, root_option=root_option, exists=False)
    if path.exists() or path.is_symlink():
        _exists(str(value), option)
    return path


def _exists(value: str, option: str):
    from production_diagnostics import ProductionError
    raise ProductionError('OUTPUT_ALREADY_EXISTS', f'{option} names an existing file, which is kept: {value}',
                          phase='output', file=value, required_action=f'Choose a new {option}.', option=option)


def write_new(path: Path, raw: bytes, *, option: str, value: str) -> None:
    """Create one output whole; a file another writer created meanwhile is kept and refused."""
    try:
        c.atomic(path, raw)
    except FileExistsError:
        _exists(value, option)


def read_json_file(root: Path | None, value: str | None, *, option: str, root_option: str = '--root') -> Any:
    """One UTF-8 JSON input: a studio file, or '-' for standard input."""
    if value is None:
        return None
    if str(value) == '-':
        return c.read_json_input('-')
    return c.decode(c.read(studio_file(root, value, option=option, root_option=root_option)))


def single_stdin(values: dict[str, Any]) -> None:
    """Standard input feeds at most one option of a call."""
    readers = [option for option, value in values.items() if value is not None and str(value) == '-']
    if len(readers) > 1:
        from production_diagnostics import ProductionError
        raise ProductionError('INPUT_SCHEMA_INVALID', 'standard input is named by ' + ', '.join(readers),
                              phase='arguments', required_action='Read at most one option from -; give the others as files.')


def diagnostics_of(error: BaseException, *, phase: str) -> list[dict]:
    """The common diagnostics of one CLI failure, each reported once."""
    from production_diagnostics import Diagnostic, ProductionError, from_exception
    from render_contract_lib import ParameterErrors, problem_code
    if isinstance(error, ParameterErrors):
        rows = [Diagnostic(problem_code(item['status']), item['message'], phase=phase,
                           pointer='$.' + item['parameter'], details={'status': item['status']}).as_dict()
                for item in error.problems]
    elif isinstance(error, ProductionError):
        rows = [error.diagnostic.as_dict()]
    elif getattr(error, 'errors', None):
        rows = [Diagnostic('INPUT_CONSISTENCY_ERROR', message, phase=phase).as_dict()
                for message in dict.fromkeys(str(item) for item in error.errors)]
    else:
        rows = [from_exception(error, phase=phase)]
    seen = {row['message'] for row in rows}
    for note in getattr(error, '__notes__', ()):
        if str(note) and str(note) not in seen:
            seen.add(str(note))
            rows.append(Diagnostic('ARTIFACT_PUBLISH_FAILED', str(note), phase='publication',
                                   required_action='Inspect the named staging before building again.').as_dict())
    return rows


def report_failure(error: BaseException, *, phase: str) -> int:
    """Print the failure in the common form and return the exit status its diagnostic codes select."""
    from production_diagnostics import result_exit
    rows = diagnostics_of(error, phase=phase)
    print(json.dumps({'ok': False, 'diagnostics': rows}, ensure_ascii=False, indent=2))
    return result_exit(rows)


def create(root: Path | None, run: str | None, prompt: str) -> dict[str,Any] | None:
    if root is None and run is None:return None
    if root is None or run is None:raise ValueError('production root and run are both required')
    from production_workflow import assert_current
    _,prepared,consumer,_=assert_current(c._root(root),run)
    return bind_consumer({'run':run,'input_sha256':prepared['input_sha256'],'consumer':consumer},prompt)



def bind_consumer(context: dict, prompt: str) -> dict:
    c.exact(context,{'run','input_sha256','consumer'},'compiled production context')
    consumer=context['consumer']
    if consumer['instructions']!=prompt:raise ValueError('composition differs from the canonical prepared prompt')
    result={**context,'consumer_sha256':c.content_id(consumer),'composition_sha256':c.digest(prompt.encode('utf-8'))}
    result['sha256']=c.content_id(result)
    validate(result,prompt)
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
    if c.digest(prompt.encode('utf-8'))!=binding['composition_sha256'] or consumer['instructions']!=prompt:
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
        raise ValueError('copy the upscale source into the studio before preparing the request') from exc
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


def validate_upscale_input(root: Path, request: dict) -> None:
    """Verify one explicit upscale declaration and its actual source bytes."""
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


def validate_upscale_live(root: Path, run: str, request: dict) -> None:
    """The prepared delivery and source snapshot authorize the exact input."""
    validate_upscale_input(root, request)
    from production_workflow import assert_current
    _, prepared, consumer, _ = assert_current(root, run)
    if prepared['task']['route'] != 'upscale' or prepared['task']['execution'] != 'dispatcher' or prepared['task']['artifact'] != 'image':
        raise ValueError('upscale needs an image task on the upscale dispatcher route')
    if c.decode(consumer['instructions'].encode('utf-8')) != request:
        raise ValueError('upscale request differs from the prepared delivery')
    if not any(x['space'] == 'studio' and x['path'] == request['source']['path']
               and x['sha256'] == request['source']['sha256'] for x in prepared['dependencies']):
        raise ValueError('upscale source must be pinned among the prepared task sources')


def json_object(root: Path, value: str | None, *, option: str, root_option: str = '--root') -> dict:
    """One JSON object input; an absent option is the empty object."""
    found = read_json_file(root, value, option=option, root_option=root_option)
    if found is None:
        return {}
    if not isinstance(found, dict):
        raise ValueError(f'{option}: expected a JSON object')
    return found


def main(argv: list[str] | None = None) -> int:
    parser = _operation_context.ArgumentParser(description='Write an exact upscale input declaration; no upload or submission.')
    parser.add_argument('--root', required=True, type=Path, help='The studio the declaration and every relative path belong to')
    parser.add_argument('--source', required=True, help='The source image, a /-separated path relative to --root')
    parser.add_argument('--model', required=True, help='Resolved model record identifier')
    parser.add_argument('--scale', required=True, type=float)
    parser.add_argument('--settings-file', help='UTF-8 JSON settings file relative to --root, or - for stdin')
    parser.add_argument('--guidance')
    parser.add_argument('--render-intent', required=True,
                        help='UTF-8 JSON file relative to --root with the explicit source finish and upscale intent, or - for stdin')
    parser.add_argument('--request-validation-file', required=True,
                        help='Validation record relative to --root, with evidence paths relative to the studio, or - for stdin')
    parser.add_argument('--out', required=True, help='New declaration file relative to --root; an existing file is kept')
    args = parser.parse_args(argv)
    try:
        single_stdin({'--settings-file': args.settings_file, '--render-intent': args.render_intent,
                      '--request-validation-file': args.request_validation_file})
        out = new_output(args.root, args.out, option='--out')
        value = upscale_request(args.root, studio_file(args.root, args.source, option='--source'), args.model, args.scale,
                                json_object(args.root, args.settings_file, option='--settings-file'), args.guidance,
                                request_validation=json_object(args.root, args.request_validation_file, option='--request-validation-file'),
                                render_intent=json_object(args.root, args.render_intent, option='--render-intent'))
        write_new(out, c.encoded(value), option='--out', value=args.out)
        print(json.dumps({'ok': True, 'request': args.out, 'content_sha256': c.content_id(value)}, indent=2))
        return 0
    except (OSError, ValueError, TypeError) as exc:
        return report_failure(exc, phase='upscale-declaration')


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
