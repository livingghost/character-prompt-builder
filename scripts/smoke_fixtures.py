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


def fixture_external_delivery(folder: Path, prompt: str, features: list[str]) -> tuple[Path, str]:
    """Prepare input for an independent package-construction test, not automatic dispatch.

    These tests inspect reference/package bytes and never execute a service. The
    external delivery contract does not claim to have compiled a provider request.
    Complete automatic execution is covered by production_case_fixtures instead.
    """
    import execution_contract as c
    import production_fixtures
    import production_workflow
    import studio
    import work_ledger
    root = studio.init(folder, 'synthetic-cli', 'Synthetic CLI fixture')
    started = work_ledger.begin(root, 'Synthetic package', ['prepare'])
    (root / 'fixture-delivery.txt').write_bytes(prompt.encode('utf-8'))
    spec = {'task_id': started['task_id'], 'route': 'generation', 'features': features, 'sources': [],
            'delivery': {'path': 'fixture-delivery.txt', 'transport': 'authored-rendition',
                         'translation_notes': 'Exact synthetic test input.'},
            'criteria': [{'id': 'output', 'strength': 'hard', 'text': 'Inspect actual fixture bytes.'}],
            'world_views': []}
    production_fixtures.task(root, spec, artifact='image', execution='external')
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
        if '--production-spec-file' in args and '--prompt-file' in args:
            spec_path=Path(args[args.index('--production-spec-file')+1])
            prompt_path=Path(args[args.index('--prompt-file')+1])
            if spec_path.exists() and prompt_path.is_file():
                from render_contract_fixtures import intent
                spec=json.loads(spec_path.read_text(encoding='utf-8'))
                prompt=prompt_path.read_bytes().decode('utf-8')
                ref_mode='text-to-image'
                if '--references-file' in args:
                    ref_path=Path(args[args.index('--references-file')+1])
                    if ref_path.exists():
                        ref=json.loads(ref_path.read_text(encoding='utf-8'))
                        if ref.get('selected_references') or ref.get('single_board'):
                            ref_mode='reference-guided'
                spec['render_intent']=intent(prompt,ref_mode)
                current=Path(temp)/'fixture-current-production-spec.json'
                current.write_text(json.dumps(spec),encoding='utf-8')
                args[args.index('--production-spec-file')+1]=str(current)
        if '--production-root' not in args:
            prompt_path=Path(argv[argv.index('--prompt-file')+1])
            prompt=prompt_path.read_bytes().decode('utf-8') if prompt_path.is_file() else ''
            features=['state-series'] if main.__module__=='build_state_generation_package' else []
            root,run=fixture_external_delivery(Path(temp)/'studio',prompt or 'synthetic absent prompt',features)
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
            model = args[args.index('--model')+1] if '--model' in args else 'gpt-image-2.5-flare'
            path=Path(temp)/'request-validation.json'
            path.write_text(json.dumps(fixture_validation(root, model, reference_mode='prompt-prefix')), encoding='utf-8')
            fixture_validation(fixture_root(), model, reference_mode='prompt-prefix')
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
                value=fixture_retrieval(prompt_path.read_text(encoding='utf-8'),json.loads(plot_path.read_text(encoding='utf-8')))
            path.write_text(json.dumps(value),encoding='utf-8')
            args.extend(['--retrieval-record-file',str(path)])
        if main.__module__=='build_generation_payload' and '--prompt-file' in args:
            # The stateless builder reads the prompt from the run's delivery, which the prompt file became above.
            index=args.index('--prompt-file');del args[index:index+2]
        return main(args)
