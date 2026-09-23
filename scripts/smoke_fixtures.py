"""Explicitly synthetic retrieval data for offline smoke tests, never production defaults."""
from __future__ import annotations
import json
import tempfile
from pathlib import Path
from typing import Any, Callable
from prompt_retrieval import settle_retrieval_record


def fixture_retrieval(prompt: str, plot: dict[str, Any]) -> dict[str, Any]:
    return settle_retrieval_record({"artifact_type": "prompt-retrieval-record", "pack_state": "offline-test-fixture",
        "elements": [{"element": "offline fixture composition", "queries": ["offline fixture lookup"],
                      "inspected_records": [], "outcome": "composed", "composed_wording": prompt.strip(),
                      "reason": "Synthetic test data, not a claim that a production search was performed."}]},
        prompt=prompt, plot=plot)


def fixture_run(folder: Path, prompt: str, features: list[str]) -> tuple[Path, str]:
    """Prepare a synthetic dispatcher run whose delivery is the prompt; no authorization is issued."""
    import execution_contract as c
    import production_fixtures
    import production_workflow
    import studio
    import work_ledger
    root = studio.init(folder, 'synthetic-cli', 'Synthetic CLI fixture')
    started = work_ledger.begin(root, 'Synthetic offline package', ['prepare'])
    (root / 'fixture-delivery.txt').write_text(prompt, encoding='utf-8')
    spec = {'task_id': started['task_id'], 'route': 'generation', 'features': features, 'sources': [],
            'delivery': {'path': 'fixture-delivery.txt', 'transport': 'authored-rendition',
                         'translation_notes': 'Exact synthetic test input.'},
            'criteria': [{'id': 'output', 'strength': 'hard', 'text': 'Inspect actual fixture bytes.'}],
            'world_views': []}
    production_fixtures.task(root, spec, artifact='image', execution='dispatcher')
    (root / 'fixture-task.json').write_bytes(c.encoded(spec))
    return root, production_workflow.prepare(root, 'fixture-task.json')['run']


def cli_with_fixture_retrieval(main: Callable[..., Any], argv: list[str]) -> Any:
    """Construct the explicit fixture inputs used by each offline CLI scenario."""
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
        if '--production-root' not in args:
            prompt_path=Path(argv[argv.index('--prompt-file')+1])
            prompt=prompt_path.read_text(encoding='utf-8').strip() if prompt_path.is_file() else ''
            features=['state-series'] if main.__module__=='build_state_generation_package' else []
            root,run=fixture_run(Path(temp)/'studio',prompt or 'synthetic absent prompt',features)
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
            # This helper authors only explicit offline test data for models
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
                     'reason':'Exercise an intentionally absent input in an offline test.'}]}
            if prompt_path.is_file() and plot_path.is_file():
                value=fixture_retrieval(prompt_path.read_text(encoding='utf-8'),json.loads(plot_path.read_text(encoding='utf-8')))
            path.write_text(json.dumps(value),encoding='utf-8')
            args.extend(['--retrieval-record-file',str(path)])
        return main(args)
