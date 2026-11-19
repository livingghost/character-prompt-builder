"""Explicitly synthetic retrieval data for smoke tests, never production defaults."""
from __future__ import annotations
import json
import tempfile
from pathlib import Path
from typing import Any, Callable
from prompt_retrieval import settle_retrieval_record


def fixture_retrieval(prompt: str, plot: dict[str, Any]) -> dict[str, Any]:
    return settle_retrieval_record({"artifact_type": "prompt-retrieval-record", "pack_state": "synthetic-test-fixture",
        "elements": [{"element": "synthetic fixture composition", "queries": ["synthetic fixture lookup"],
                      "inspected_records": [], "outcome": "composed", "composed_wording": prompt.strip(),
                      "reason": "Synthetic test data, not a claim that a production search was performed."}]},
        prompt=prompt, plot=plot)


def fixture_reference_prompt(prompt: str, prepared: dict | None) -> str:
    """Author generic scope directions for explicit transport-only test fixtures.

    Dedicated depiction tests write their own directions. This helper gives
    byte/transaction fixtures an operative use of each reference they selected;
    it is never imported by a production authoring command.
    """
    if (not prompt or '{{reference:' in prompt or not isinstance(prepared, dict)
            or not {'transport_mode', 'selected_references', 'single_board'} <= prepared.keys()):
        return prompt
    from reference_delivery import bindings
    rows = bindings(prepared['transport_mode'], prepared['selected_references'], prepared['single_board'])
    directions = []
    for row in rows:
        use = row['reference_id']
        direction = 'Image {{reference:' + use + ':attachment_number}}'
        if row['region_pixels'] is not None:
            direction += ', panel (x, y, width, height) {{reference:' + use + ':region}}'
        directions.append(direction + ', supplies {{reference:' + use + ':controls}}.')
    return prompt + ('\n' + '\n'.join(directions) if directions else '')


def fixture_resolved_prompt(prompt: str, prepared: dict | None) -> str:
    from model_rendition import resolve_reference_text
    from reference_delivery import bindings
    source = fixture_reference_prompt(prompt, prepared)
    rows = bindings(prepared['transport_mode'], prepared['selected_references'], prepared['single_board']) if (
        isinstance(prepared, dict) and {'transport_mode', 'selected_references', 'single_board'} <= prepared.keys()) else []
    return resolve_reference_text(source, rows)['text']


def fixture_external_delivery(folder: Path, prompt: str, features: list[str], *,
                              model: str | None = None) -> tuple[Path, str]:
    """Prepare input for an independent package-construction test, not automatic dispatch.

    These tests inspect reference/package bytes and never execute a service. The
    external text task holds the literal source template for package compilation;
    it makes no image-generation request or provider claim.
    Complete automatic execution is covered by production_case_fixtures instead.
    """
    import execution_contract as c
    import production_fixtures
    import production_operations as production_workflow
    import studio_workspace as studio
    import work_ledger
    root = studio.init(folder, 'synthetic-cli', 'Synthetic CLI fixture')
    started = work_ledger.begin(root, 'Synthetic package', ['prepare'])
    (root / 'fixture-delivery.txt').write_bytes(prompt.encode('utf-8'))
    features = [*features, 'generation-package']
    spec = {'task_id': started['task_id'], 'route': 'generation', 'features': features, 'sources': [],
            'delivery': {'path': 'fixture-delivery.txt',
                         'translation_notes': 'Exact synthetic test input.'},
            'criteria': [{'id': 'output', 'strength': 'hard', 'text': 'Inspect actual fixture bytes.'}],
            'world_views': []}
    production_fixtures.task(root, spec, artifact='text', execution='external', focus='supporting-setting')
    if model is not None:
        from reading_fixtures import fixture_reading
        reading = fixture_reading(route=spec['route'], features=features, operation='prepare',
                                  model=model, studio=root, execution=spec['execution'])
        (root / 'reading.json').write_bytes(c.encoded(reading))
        spec['route_reading'] = 'reading.json'
    (root / 'fixture-task.json').write_bytes(c.encoded(spec))
    return root, production_workflow.prepare(root, 'fixture-task.json')['run']


def cli_with_fixture_retrieval(main: Callable[..., Any], argv: list[str]) -> Any:
    """Construct the explicit fixture inputs used by each CLI test scenario."""
    from pack_manager import default_settings
    from catalog_retrieval.runtime import configure_pack_runtime
    values = {}
    for option in ('state-file', 'cache-dir', 'managed-root'):
        flag='--'+option
        if flag in argv:
            values[option.replace('-','_')]=Path(argv[argv.index(flag)+1])
    extra=[Path(argv[i+1]) for i,x in enumerate(argv) if x=='--pack-root']
    configure_pack_runtime(default_settings(extra_roots=extra, **values))
    with tempfile.TemporaryDirectory(prefix='synthetic-cli-inputs-') as temp:
        args=list(argv)
        prepared = None
        if '--references-file' in args:
            reference_path = Path(args[args.index('--references-file') + 1])
            if reference_path.is_file():
                candidate = json.loads(reference_path.read_text(encoding='utf-8'))
                if isinstance(candidate, dict) and 'selected_references' in candidate:
                    prepared = candidate
        for option in ('--prompt-file', '--integrated-prompt-file'):
            if option in args:
                path = Path(args[args.index(option) + 1])
                if path.is_file():
                    source = fixture_reference_prompt(path.read_bytes().decode('utf-8'), prepared)
                    current = Path(temp) / (option[2:] + '.txt')
                    current.write_bytes(source.encode('utf-8'))
                    args[args.index(option) + 1] = str(current)
        argv = args
        model = args[args.index('--model')+1] if '--model' in args else None
        if model is None and '--production-spec-file' in args:
            selected = Path(args[args.index('--production-spec-file')+1])
            if selected.is_file():
                model = json.loads(selected.read_text(encoding='utf-8')).get('target_model')
        if '--production-spec-file' in args and '--prompt-file' in args:
            spec_path=Path(args[args.index('--production-spec-file')+1])
            prompt_path=Path(args[args.index('--prompt-file')+1])
            if spec_path.exists() and prompt_path.is_file():
                from render_contract_fixtures import intent
                spec=json.loads(spec_path.read_text(encoding='utf-8'))
                prompt=prompt_path.read_bytes().decode('utf-8')
                if '--integrated-prompt-file' in args:
                    integrated = Path(args[args.index('--integrated-prompt-file') + 1]).read_text(encoding='utf-8')
                    if integrated.strip():
                        transport_mode = args[args.index('--negative-transport') + 1] if '--negative-transport' in args else 'auto'
                        if transport_mode == 'auto' and model is not None:
                            from generation_references import resolve_model_record
                            transport_mode = resolve_model_record(model)[1]['negative_transport_mode']
                        if transport_mode in {'integrated-critical', 'retained-only'}:
                            prompt = integrated
                ref_mode='text-to-image'
                if '--references-file' in args:
                    ref_path=Path(args[args.index('--references-file')+1])
                    if ref_path.exists():
                        ref=json.loads(ref_path.read_text(encoding='utf-8'))
                        if ref.get('selected_references') or ref.get('single_board'):
                            ref_mode='reference-guided'
                spec['render_intent']=intent(fixture_resolved_prompt(prompt, prepared),ref_mode)
                current=Path(temp)/'fixture-current-production-spec.json'
                current.write_text(json.dumps(spec),encoding='utf-8')
                args[args.index('--production-spec-file')+1]=str(current)
        if '--production-root' not in args:
            prompt_path=Path(argv[argv.index('--prompt-file')+1])
            prompt=prompt_path.read_bytes().decode('utf-8') if prompt_path.is_file() else ''
            features=['state-series'] if main.__module__=='build_state_generation_package' else []
            root,run=fixture_external_delivery(Path(temp)/'studio',prompt or 'synthetic absent prompt',features,
                                               model=model)
            args.extend(['--production-root',str(root),'--production-run',run])
        root=Path(args[args.index('--production-root')+1])
        # Later verification in these tests reads the shared fixture root, so
        # the same synthetic evidence bytes are written there as well.
        from visual_fixtures import fixture_visual, fixture_root
        if '--visual-continuity-file' not in args and '--continuity' not in args:
            spec_path=Path(argv[argv.index('--production-spec-file')+1])
            spec=json.loads(spec_path.read_text(encoding='utf-8')) if spec_path.is_file() else {'subjects': []}
            path=Path(temp)/'visual-continuity.json'
            path.write_text(json.dumps(fixture_visual(spec,root=root)),encoding='utf-8')
            fixture_visual(spec,root=fixture_root())
            args.extend(['--visual-continuity-file',str(path)])
        if '--request-validation-file' not in args:
            from request_validation_fixtures import fixture_validation
            # This helper authors only explicit synthetic test data for models
            # whose request check cannot be derived from an active pack.
            if isinstance(model, str) and model.strip():
                path=Path(temp)/'request-validation.json'
                path.write_text(json.dumps(fixture_validation(root, model, reference_mode='authored-rendition')), encoding='utf-8')
                fixture_validation(fixture_root(), model, reference_mode='authored-rendition')
                args.extend(['--request-validation-file', str(path)])
        if '--retrieval-record-file' not in args:
            path=Path(temp)/'retrieval.json'
            prompt_path=Path(argv[argv.index('--prompt-file')+1])
            plot_path=Path(argv[argv.index('--plot-file')+1])
            value={'artifact_type':'prompt-retrieval-record','settled':False,
                   'elements':[{'element':'synthetic missing input','queries':['synthetic lookup'],
                     'inspected_records':[],'outcome':'composed','composed_wording':'synthetic',
                     'reason':'Exercise an intentionally absent input in a test.'}]}
            if prompt_path.is_file() and plot_path.is_file():
                selected_prompt = prompt_path.read_text(encoding='utf-8')
                if '--integrated-prompt-file' in args:
                    integrated = Path(args[args.index('--integrated-prompt-file') + 1]).read_text(encoding='utf-8')
                    if integrated.strip():
                        mode = args[args.index('--negative-transport') + 1] if '--negative-transport' in args else 'auto'
                        if mode == 'auto' and model is not None:
                            from generation_references import resolve_model_record
                            mode = resolve_model_record(model)[1]['negative_transport_mode']
                        if mode in {'integrated-critical', 'retained-only'}:
                            selected_prompt = integrated
                value=fixture_retrieval(fixture_resolved_prompt(selected_prompt, prepared),
                    json.loads(plot_path.read_text(encoding='utf-8')))
            path.write_text(json.dumps(value),encoding='utf-8')
            args.extend(['--retrieval-record-file',str(path)])
        if main.__module__=='build_generation_payload' and '--prompt-file' in args:
            # The stateless builder reads the prompt from the run's delivery, which the prompt file became above.
            index=args.index('--prompt-file');del args[index:index+2]
        return main(args)
