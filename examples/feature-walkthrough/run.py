#!/usr/bin/env python3
"""Walk one idea through actual retrieval, one prepare and its exact request preview.

Run: python examples/feature-walkthrough/run.py --out NEW_DIRECTORY

An explicitly synthetic model is used for a no-network preview. The example
author records choices after actual commons catalog lookups and inspections.
The task has no execution authority and no confirmed cost. It is not sent.

Inputs are authored before production_workflow.py prepare. Preparation produces
package, preview, recording checks and execution plan together; status reports
what is still required. transcript.txt records the commands that actually ran.
"""
from __future__ import annotations
import argparse
import contextlib
import importlib
import io
import json
import os
import shlex
import socket
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import catalog_cli
import execution_contract as c
import pack_manager as pm
import studio
from prompt_plot import content_sha256

MODEL = 'walkthrough-synthetic-image'
SERVICE = 'walkthrough-service'
MODEL_IDENTIFIER = 'synthetic:preview'
PACK_ID = '019a0290-2345-789a-8123-0123456789ab'
SCHEMA_PATH = 'resources/preview-schema.json'
COMMONS = c.load(ROOT / 'packs/commons/pack.json')['pack_id']
SYNTHETIC = 'SYNTHETIC WALKTHROUGH FIXTURE - NOT REAL USER CONSENT'
BRIEF = 'A woman waits at a bus stop in light rain.'
PROMPT = ('Photographic portrait. A woman in a green raincoat waits at a bus stop in light rain, seen waist-up at eye level, '
          'soft grey daylight, the shelter glass beaded with drops behind her.')
PLOT = {
    'artifact_type': 'prompt-plot',
    'story': [{'id': 's1', 'beat': 'A woman waits for her bus on a rainy afternoon.', 'visibility': 'visible'}],
    'derived': [
        {'kind': 'shows', 'statement': 'one woman in a green raincoat at a bus stop', 'from': ['s1']},
        {'kind': 'placement', 'statement': 'she stands in front of the shelter glass', 'from': ['s1']},
        {'kind': 'composition', 'statement': 'a waist-up view at eye level', 'from': ['s1']},
        {'kind': 'must_preserve', 'statement': 'light rain and soft grey daylight', 'from': ['s1']},
        {'kind': 'free', 'statement': 'the exact street behind the shelter'},
    ],
}
PLOT['approved'] = {'by': SYNTHETIC, 'at': '2026-09-23T00:00:00Z', 'content_sha256': content_sha256(PLOT)}


def write(path: Path, value) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    path.write_text(text, encoding='utf-8', newline='\n')
    return path


def fixture_pack(path: Path) -> Path:
    """Declare the local preview interface; no live provider capability is claimed."""
    from model_prompt_input_fixtures import prompt_input
    from production_case_fixtures import synthetic_profile
    from transport_synthetic import ENDPOINT

    profile = synthetic_profile()
    profile['modes'] = {'text-to-image': profile['modes']['text-to-image']}
    write(path/'pack.json', {
        'pack_id': PACK_ID, 'name': 'Workflow Preview Fixture',
        'description': 'Local synthetic request-preview interface.', 'release': '2026.01.01.1',
        'content': {'record_globs': ['records/**/*.json'], 'resource_globs': ['resources/**/*'],
                    'resource_bindings': {'service-profiles': 'resources/services.json'}},
        'capabilities': ['model-adapters'], 'dependencies': [], 'optional_dependencies': [],
        'replaces': [], 'license': 'GPL-3.0-only'})
    write(path/'records/models.json', {'kind': 'model', 'records': [{
        'id': MODEL, 'label': 'Synthetic workflow preview', 'aliases': ['synthetic workflow preview'],
        'operation_kind': 'generation', 'prompt_input': prompt_input('descriptive'),
        'supports_negative_prompt': True, 'negative_transport_mode': 'separate-field',
        'negative_transport_notes': 'The synthetic interface declares its own negative field.',
        'prompt_style': 'Authored natural-language image direction.',
        'ordering': ['rendering', 'subject', 'composition', 'environment'],
        'execution_profile': profile,
        'search_terms': [{'phrase': 'synthetic workflow preview', 'facet': 'model', 'weight': 1.0, 'source': 'author'}],
        'offerings': [{'service': SERVICE, 'model_identifier': MODEL_IDENTIFIER,
            'request_keys': {'model': ['model'], 'prompt': ['prompt'], 'negative prompt': ['negative_prompt']},
            'execution_profile': profile, 'constraints': {}, 'observed_at': '2000-01-01',
            'schema_snapshot': SCHEMA_PATH}]}]})
    write(path/'resources/services.json', {'services': {SERVICE: {
        'label': 'Local synthetic preview', 'transport': 'synthetic',
        'endpoint': {'base_url': ENDPOINT, 'method': 'POST'}, 'auth': {'scheme': 'none'},
        'operations': {'generate': {}}}}})
    write(path/SCHEMA_PATH, {
        'artifact_type': 'observed-parameter-schema', 'model_id': MODEL, 'service': SERVICE,
        'model_identifier': MODEL_IDENTIFIER, 'observed_at': '2000-01-01',
        'source': 'Synthetic fixture interface declaration; no provider observation.',
        'schema': {'type': 'object', 'properties': {
            'model': {'type': 'string', 'const': MODEL_IDENTIFIER},
            'prompt': {'type': 'string', 'minLength': 1},
            'negative_prompt': {'type': 'string', 'minLength': 1},
            'count': {'type': 'integer', 'minimum': 1, 'maximum': 20},
            'width': {'type': 'integer', 'minimum': 1, 'maximum': 2048},
            'height': {'type': 'integer', 'minimum': 1, 'maximum': 2048},
            'settings': {'type': 'object', 'properties': {'quality': {'enum': ['draft', 'medium', 'high']}},
                         'additionalProperties': False}},
            'required': ['model', 'prompt', 'width', 'height'], 'additionalProperties': False}})
    pm.write_lock(path)
    return path


def summary(text: str) -> str:
    """A short result: the plain lines a command printed, or a few fields of its JSON."""
    try:
        value = json.loads(text)
    except ValueError:
        value = None
    if isinstance(value, dict):
        fields = [f'{key}: {item}' for key, item in value.items()
                  if isinstance(item, (str, int, bool)) and len(str(item)) <= 80][:3]
        return '; '.join(fields)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    plain = []
    for line in lines:
        if line.startswith('{'):
            break
        plain.append(line)
    return '; '.join(plain[:8] or lines[:1])


class Walkthrough:
    """Run each command in process, as its command line, and keep a short transcript."""

    def __init__(self, out: Path):
        self.out = out
        self.lines = ['# Every command the walkthrough ran, in order, with paths relative to its output directory.']

    def relative(self, text: str) -> str:
        """Paths from the output directory, and scripts from the directory holding SKILL.md."""
        for base in (self.out, ROOT):
            for prefix in (str(base) + '\\', str(base) + '/'):
                text = text.replace(prefix, '')
        return text.replace(str(self.out), '.').replace('\\', '/')

    def note(self, text: str) -> None:
        self.lines.append('# ' + text)

    def run(self, script: str, *argv: str, result=summary) -> str:
        module = importlib.import_module(script)
        stdout = io.StringIO()
        with patch.object(sys, 'argv', [script + '.py', *argv]), contextlib.redirect_stdout(stdout):
            try:
                from operation_context import run_cli
                code = run_cli(module.main) or 0
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 1
        text = stdout.getvalue()
        self.lines.append('$ python scripts/' + script + '.py ' + ' '.join(shlex.quote(self.relative(a)) for a in argv))
        self.lines.append(f'  exit {code}: ' + self.relative(result(text) if code == 0 else summary(text)))
        if code != 0:
            raise RuntimeError(f'{script}.py failed: {summary(text)}')
        return text


def run(out: Path) -> dict:
    out=out.resolve()
    if out.exists():raise ValueError('walkthrough output already exists; choose a new directory')
    out.mkdir(parents=True)
    pack=fixture_pack(out/'fixture-pack')
    state=out/'pack-state.json'
    pm.save_state(state,{'pack_roots':[],'enabled_packs':[PACK_ID,COMMONS],'pack_order':[PACK_ID,COMMONS]})
    runtime=['--state-file',str(state),'--cache-dir',str(out/'cache'),
             '--managed-root',str(out/'managed'),'--pack-root',str(pack)]
    settings=pm.default_settings(extra_roots=(pack,),state_file=state,cache_dir=out/'cache',managed_root=out/'managed')
    catalog_cli.configure_pack_runtime(settings)
    attempts=[]
    def refuse(*args,**kwargs):
        attempts.append(args[1:] or args)
        raise OSError('this request-preview example forbids network connections')
    walk=Walkthrough(out);root=out/'studio'
    environment={key:value for key,value in os.environ.items() if key!='CPB_READS_LEDGER'}
    try:
        with patch.object(socket.socket,'connect',refuse),patch.object(socket,'create_connection',refuse),patch.dict(os.environ,environment,clear=True):
            walk.run('studio','init','--out',str(root),'--studio-id','request-preview-walkthrough','--title','Request preview walkthrough')
            walk.run('studio','character','add','C01','--studio',str(root))
            walk.run('work_ledger','--studio',str(root),'begin','--goal','Preview one portrait request','--step','prepare','--step','preview')
            task_id=c.load(root/'work/current.json')['task_id']
            walk.run('execution_routes','read','generation','--root',str(root),'--model',MODEL,*runtime,
                     result=lambda text:f'{len(text)} characters read; '+text.strip().splitlines()[-1])
            walk.run('render_contract','model','--model',MODEL,'--service',SERVICE,*runtime)
            elements={
                'subject':'woman portrait','wardrobe':'green raincoat','setting':'bus stop shelter',
                'weather':'light rain','framing':'waist-up portrait','camera':'eye level',
                'lighting':'soft grey daylight','surface':'glass beaded with rain drops','rendering':'photographic portrait'}
            write(root/'queries.json',[{'request_id':name,'command':'search','canonical_query':query,'limit':1} for name,query in elements.items()])
            found=json.loads(walk.run('catalog_cli',*runtime,'batch','--input',str(root/'queries.json'),'--record',str(root/'lookups.json')))
            for result in found['results']:
                if not result['ok']:raise ValueError('synthetic walkthrough lookup did not complete: '+result['request_id'])
                candidates=result['result']['results']
                if candidates:
                    row=candidates[0]
                    walk.run('catalog_cli',*runtime,'inspect',row['id'],'--record',str(root/'lookups.json'),'--element',result['request_id'])
            # These predetermined decisions belong to the labeled example author.
            # Lookup and full inspections above are real; no user acceptance is inferred.
            from prompt_retrieval import mark_outcome
            record=c.load(root/'lookups.json')
            for name,wording in elements.items():
                mark_outcome(record,name,composed=wording,reason=SYNTHETIC+': use the explicitly authored example wording; inspected catalog records are not adopted as a character identity.')
            write(root/'lookups.json',record);write(root/'plot.json',PLOT);write(root/'prompt.txt',PROMPT+'\n')
            walk.note('recorded actual lookups and labeled synthetic author choices; no actual user approval or execution authority')
            walk.run('prompt_retrieval',str(root/'lookups.json'),'--settle','--prompt-file',str(root/'prompt.txt'),'--plot-file',str(root/'plot.json'),'--out',str(root/'retrieval.json'))
            walk.run('render_contract','intent','--preset','photographic','--mode','text-to-image','--chosen-by','agent',
                     '--reason','A photographic treatment supports the synthetic rainy-day portrait.','--presentation','waist-up portrait',
                     '--prompt-expression','Photographic portrait.','--out',str(root/'render-intent.json'))
            walk.run('production_spec','draft',str(root/'production-spec.json'),'--render-intent',str(root/'render-intent.json'),
                     '--model',MODEL,'--brief',BRIEF,'--kind','human','--continuity','one-off')
            write(root/'parameters.json',{'width':832,'height':1248,'settings':{'quality':'medium'}})
            write(root/'creative-intent.json',{'image_promise':'An explicitly synthetic preview of a quiet rainy-day portrait.'})
            # The fixture helper quotes actual route documents and labels every
            # application as synthetic. It cannot supply real execution consent.
            from reading_fixtures import fixture_reading
            catalog_cli.configure_pack_runtime(settings)
            write(root/'reading.json',fixture_reading(route='generation',studio=root,ledger=root/'work/reads.jsonl'))
            task={'task_id':task_id,'production_id':pm.generate_uuid7(),'route':'generation','features':[],
                'sources':[],'world_views':[],'authority':None,'route_reading':'reading.json','artifact':'image','execution':'dispatcher',
                'delivery':{'path':'prompt.txt','translation_notes':'The prompt is sent exactly as authored, including its final newline.'},
                'criteria':[{'id':'framing','strength':'hard','evidence':'image','text':'One woman in a green raincoat, waist-up, at a bus stop in light rain.'}],
                'direction':{'purpose':'Preview the request for one one-off portrait.','intended_effect':'A quiet readable rainy-day portrait.',
                             'basis':[],'decisions':[],'action_slice':None,'limitations':[SYNTHETIC]},
                'generation':{'parameters':'parameters.json','production_spec':'production-spec.json','plot':'plot.json','retrieval_record':'retrieval.json',
                              'creative_intent':'creative-intent.json','service':SERVICE,'count':1,'seed':None,'continuity':{'C01':'one-off'}},
                'recording':{'character':'C01','slot':'explore','subject_map':{},'sheet_panel':False,'role':'walkthrough-preview'}}
            write(root/'task.json',task)
            prepared=json.loads(walk.run('production_workflow','prepare','--root',str(root),'--task','task.json',*runtime))
            run_id=prepared['run'];directory=Path(prepared['package']).parent
            shown=c.load(directory/'request-contract.json');built=c.load(directory/'package.json')
            # Exports are projections, not independently edited requests.
            write(out/'preview.json',{'request':prepared['request_preview'],'execution_plan':prepared['execution_plan']})
            write(out/'prepare-arguments.json',['--root',str(root),'--task','task.json',*runtime])
            walk.run('production_workflow','status','--root',str(root),'--run',run_id)
    finally:
        write(out/'transcript.txt','\n'.join(walk.lines)+'\n');catalog_cli.configure_pack_runtime(None)
    report={'ok':True,'synthetic_fixture':True,'external_requests':len(attempts),'sent':False,
            'production_run':run_id,'package_run':built['production_binding']['run'],
            'request_validation':{'mode':built['request_validation']['mode'],'contract':built['request_validation']['contract']['path']},
            'request':shown['request'],'validation':{'checked':[built['request_validation']['mode']]},
            'iterations':len(studio.read_iterations(studio.character_dir(root,'C01'))),'output':str(out),
            'readiness':prepared['execution_plan']['readiness'],
            'note':'Real lookup and package compilation with synthetic author choices. No execution authority, cost claim, credential, or external request.'}
    write(out/'walkthrough-report.json',report);return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = run(args.out)
    except (ValueError, OSError, RuntimeError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
