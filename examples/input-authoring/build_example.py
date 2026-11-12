#!/usr/bin/env python3
"""Create complete authored image inputs in a Studio with no previous run.

The fixture's model, authority and reference are explicitly synthetic. This
example stops at preparation and sends no request to any provider.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))

import execution_contract as c
import pack_manager as packs
import production_case_fixtures as fixtures
import production_fixtures

BRIEF = ('Prepare one image of a blue service robot lifting a yellow toolbox onto a workbench. '
         'Use the supplied image only for the blue color of the robot. '
         'Keep text overlays out of this illustration. Stop at the inspectable request.')
PROMPT = ('A blue service robot lifts a small yellow toolbox onto a workbench. '
          'The robot and the toolbox are the subjects of the illustration. '
          'Use the supplied image for the blue color of the robot only; '
          'retain the described blue robot and yellow toolbox. No text is displayed.')
ACTOR = production_fixtures.ACTOR


def initialize(destination: Path) -> dict:
    """A new Studio and local model fixture; no task, choices or run history."""
    import studio
    from catalog_retrieval import runtime
    from transport_synthetic import _png
    if destination.exists():
        raise FileExistsError('select an absent example directory: ' + str(destination))
    destination.mkdir(parents=True)
    root = studio.init(destination / 'studio', 'input-authoring-example', 'Synthetic first input')
    pack = fixtures.create_pack(destination / 'runtime/pack')
    settings = packs.default_settings(extra_roots=[pack], state_file=destination / 'runtime/state.json',
        cache_dir=destination / 'runtime/cache', managed_root=destination / 'runtime/managed')
    initial = packs.load_state(packs.DEFAULT_PACK_STATE_PATH)
    packs.save_state(settings.state_file, {'pack_roots': [],
        'enabled_packs': [*initial['enabled_packs'], fixtures.PACK_ID], 'disabled_packs': [],
        'pack_order': [fixtures.PACK_ID, *initial['enabled_packs']]})
    runtime.configure_pack_runtime(settings)
    fixtures.write(root / 'owner-direction.txt', BRIEF + '\n\nSynthetic interface exercise; '
                   'the colored reference exercises a color-use contract, not provider behavior.\n')
    c.atomic(root / 'reference.png', _png(32, 32, b'\x20\x50\x90'))
    return {'root': root, 'pack': pack, 'settings': settings, 'model': fixtures.MODEL_ID}


def build(destination: Path) -> dict:
    import work_ledger
    import production_inputs
    import production_input_guide
    import production_spec
    import production_store
    import production_workflow as workflow
    from reading_fixtures import fixture_reading
    from request_validation_fixtures import fixture_validation

    case = initialize(destination)
    root = case['root']
    work = work_ledger.begin(root, BRIEF, ['Author the requested input.', 'Prepare the inspectable request.'])
    before = production_store.runs(root)
    if before:
        raise ValueError('The first-input example must start without a prepared run.')
    draft = production_inputs.draft_inputs(root, None, 'work/input', route='generation',
        artifact='image', execution='dispatcher', features=['reference-delivery', 'production-spec'],
        model=case['model'], service='synthetic')
    choices = draft['choices']
    authored = choices['authoring']
    task = authored['task']
    task['sources'] = [{'id': 'owner-direction', 'path': 'owner-direction.txt', 'role': 'design',
        'disposition': 'applied', 'locator': 'whole', 'reason': 'The actual synthetic commission.'}]
    task['direction'] = {'purpose': BRIEF, 'intended_effect': 'Make the robot action legible in the requested scene.',
        'basis': ['owner-direction'], 'decisions': [], 'action_slice': None,
        'limitations': ['Synthetic protocol exercise; no live model or artistic result is asserted.']}
    task['criteria'] = [{'id': 'commission', 'strength': 'hard', 'evidence': 'image',
        'text': 'Show the blue service robot lifting the yellow toolbox onto the workbench.'},
        {'id': 'reference-scope', 'strength': 'hard', 'evidence': 'image',
         'text': 'Apply the supplied reference only to the blue color of the robot.'},
        {'id': 'no-text', 'strength': 'hard', 'evidence': 'image', 'text': 'The illustration contains no text overlay.'}]
    task['authority'] = 'authority.json'
    fixtures.write(root / 'authority-basis.txt', 'Synthetic fixture author permits preparation of the declared '
                   'local input. This is not user consent or permission to contact a real provider.\n')
    authority = {'task_id': work['task_id'], 'issuer': 'SYNTHETIC EXAMPLE AUTHOR',
        'evidence': {'path': 'authority-basis.txt', 'locator': 'whole'},
        'grants': [{'id': 'example-direction', 'actor': ACTOR, 'mode': 'direct',
            'operations': ['direction', 'edit'], 'targets': ['purpose', 'delivery'],
            'protected_criteria': [], 'expires_at': None, 'request_scope': None,
            'submission_validation_modes': []}],
        'stop_conditions': [{'id': 'local-only', 'text': 'Stop before submission; this example prepares inputs only.'}]}
    fixtures.write(root / 'authority.json', authority)
    fixtures.write(root / authored['delivery']['file'], PROMPT)
    authored['delivery']['translation_notes'] = None
    specification = production_spec.draft(model=case['model'], brief=BRIEF,
        subject='robot', kind='robot', render_intent={'artifact_type': 'render-intent',
            'execution_mode': 'reference-guided'})
    specification['subjects'][0]['identity'] = ['A blue service robot; no recurring character is adopted.']
    # The selected target in choices owns this value at compilation.
    specification.pop('target_model')
    documents = {
        'production_spec': specification,
        'plot': {'artifact_type': 'prompt-plot',
            'story': [{'id': 'lift', 'beat': 'The robot lifts its toolbox onto the workbench.', 'visibility': 'visible'}],
            'derived': [{'kind': 'shows', 'statement': 'the blue robot and yellow toolbox', 'from': ['lift']},
                {'kind': 'must_preserve', 'statement': 'the declared reference influence and lack of text overlays', 'from': ['lift']},
                {'kind': 'free', 'statement': 'Rendering treatment remains unspecified.'}],
            'approved': {'by': 'SYNTHETIC EXAMPLE AUTHOR', 'at': '2000-01-01T00:00:00Z'}},
        'retrieval_record': {'artifact_type': 'prompt-retrieval-record', 'elements': []},
        'creative_intent': {'image_promise': 'The requested robot action is the subject; the reference affects only its blue color.'},
        'negative': 'text overlays',
        'negative_provenance': {'activated_sources': [], 'diagnostic_sources_retained': [],
            'semantic_exclusions_user_supplied': ['text overlays']},
    }
    for name, value in documents.items():
        suffix = '.txt' if isinstance(value, str) else '.json'
        selected = 'work/input/' + name + suffix
        fixtures.write(root / selected, value)
        authored['documents'][name] = {'file': selected}
    authored['generation'].update(count=1, seed=None, continuity={'robot': 'one-off'})
    authored['references']['additional_references'] = [{'role': 'scene',
        'source': {'kind': 'supplied-file', 'reference_id': 'color-source', 'resolved_path': 'reference.png'},
        'subject_uses': [{'subject_id': 'robot', 'use': 'local-color', 'priority': 1}]}]
    choices['target'].update(execution_mode='reference-guided', parameters={'width': 32, 'height': 32, 'steps': 20})
    evidence = fixture_validation(root, case['model'], reference_mode='authored-rendition', service='synthetic')
    choices['validation'] = {'mode': 'target-schema', 'contract': evidence['contract']['path'],
        'evidence': evidence['evidence']['path'], 'execution_policy': evidence['execution_policy']['path']}
    reading = fixture_reading(route='generation', features=task['features'], studio=root,
        ledger=root / 'work/reads.jsonl', model=case['model'], service='synthetic', execution='dispatcher')
    choices['reading']['reading_key'] = reading['reading_key']
    fixtures.write(root / draft['choices_file'], choices)
    guide = production_input_guide.explain(root, draft['choices_file'])
    fixtures.write(destination / 'input-guide.json', guide)
    result = workflow.prepare(root, choices=draft['choices_file'])
    if not result.get('ok') or not result.get('run'):
        raise ValueError(json.dumps(result, ensure_ascii=False))
    run = result['run']
    loaded = workflow.read_run(root, run)
    packet = loaded.artifacts.get('package.json', {})
    if len(packet.get('prepared_reference_set', {}).get('selected_references', [])) != 1:
        raise ValueError('The example must compile exactly one supplied reference.')
    if len(production_store.runs(root)) != 1 or loaded.rows:
        # Preparation records may be in the journal; none may authorize or send.
        forbidden = {'dispatch-claim', 'external-claim', 'authorization', 'candidate'}
        if len(production_store.runs(root)) != 1 or any(row['event'] in forbidden for row in loaded.rows):
            raise ValueError('The first-input example must only prepare one run.')
    metadata = {'synthetic': True, 'prior_runs': len(before), 'prepared_runs': 1,
        'reference_count': 1, 'provider_calls': 0, 'source_file_ownership': True,
        'choices': draft['choices_file'], 'run': run,
        'selected_documents': sorted(authored['documents']),
        'authority': task['authority'], 'owner_direction': 'owner-direction.txt',
        'request_evidence': choices['validation'],
        'status_argv': [sys.executable, str(ROOT / 'scripts/production_workflow.py'),
                        'status', '--root', str(root), '--run', run]}
    fixtures.write(destination / 'report.json', metadata)
    return {**metadata, 'root': str(root), 'directory': str(destination)}


def _sample_files(root: Path) -> dict[str, bytes]:
    """The complete editable source set, without the Studio's generated history."""
    names = {'work/input/choices.json', 'owner-direction.txt', 'authority.json',
             'authority-basis.txt', 'reference.png'}
    choices = c.load(root / 'work/input/choices.json')
    names.add(choices['authoring']['delivery']['file'])
    names.update(row['file'] for row in choices['authoring']['documents'].values())
    names.update(path.relative_to(root).as_posix() for path in (root / 'synthetic-validation').rglob('*')
                 if path.is_file())
    return {name: c.read(c.local(root, name)) for name in sorted(names)}


def _comparable(name: str, raw: bytes):
    if not name.endswith('.json'):
        return raw
    value = c.decode(raw)
    if name.endswith('/choices.json'):
        value['authoring']['task']['task_id'] = '<current-task>'
        value['authoring']['task']['production_id'] = '<current-production>'
        value['reading']['reading_key'] = '<current-complete-reading>'
    elif name == 'authority.json':
        value['task_id'] = '<current-task>'
    return value


def filled_inputs(root: Path, *, refresh: bool = False) -> None:
    """Check or rebuild the example-owned complete files; reject unknown files."""
    destination = EXAMPLE / 'filled'
    files = _sample_files(root)
    listing = destination / 'source-files.json'
    if refresh:
        known = set(c.load(listing)) if listing.is_file() else set()
        actual = {path.relative_to(destination).as_posix() for path in destination.rglob('*')
                  if path.is_file()} if destination.exists() else set()
        unknown = actual - known - {'source-files.json'}
        if unknown:
            raise ValueError('Unowned files in generated example: ' + ', '.join(sorted(unknown)))
        for name in known:
            c.local(destination, name, exists=False).unlink(missing_ok=True)
        for name, raw in files.items():
            fixtures.write(destination / name, raw.decode('utf-8')) if name.endswith(('.json', '.txt')) else c.atomic(destination / name, raw, replace=True)
        fixtures.write(listing, sorted(files))
    if not listing.is_file() or c.load(listing) != sorted(files):
        raise ValueError('Filled source inventory differs; rebuild with --refresh-filled.')
    for name, raw in files.items():
        saved = c.read(c.local(destination, name))
        if _comparable(name, saved) != _comparable(name, raw):
            raise ValueError('Filled authored source differs: ' + name + '; rebuild with --refresh-filled.')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, help='New directory holding the complete Studio, inputs and local fixture runtime.')
    parser.add_argument('--check', action='store_true', help='Run the no-history preparation in an isolated temporary directory.')
    parser.add_argument('--refresh-filled', action='store_true', help='Rebuild this example\'s checked-in filled source set after a contract change.')
    args = parser.parse_args()
    if args.check or args.refresh_filled:
        if args.out is not None:
            parser.error('use --check/--refresh-filled or --out')
        with tempfile.TemporaryDirectory(prefix='input-authoring-check-') as temporary:
            with production_fixtures.scratch_home(Path(temporary) / 'home'):
                result = build(Path(temporary) / 'example')
                filled_inputs(Path(result['root']), refresh=args.refresh_filled)
        print(json.dumps({key: result[key] for key in ('synthetic', 'prior_runs', 'prepared_runs',
              'reference_count', 'provider_calls', 'source_file_ownership', 'selected_documents')}, indent=2))
    else:
        if args.out is None:
            parser.error('select --out NEW_DIRECTORY or --check')
        destination = args.out.resolve()
        with production_fixtures.scratch_home(destination.parent / (destination.name + '-home')):
            print(json.dumps(build(destination), indent=2))
    return 0


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
