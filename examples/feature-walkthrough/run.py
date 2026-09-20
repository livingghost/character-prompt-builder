#!/usr/bin/env python3
"""Create an offline executable workflow fixture, never a production approval.

python examples/feature-walkthrough/run.py --out /tmp/cpb-walkthrough
All external service operations are mocked. Existing output is never replaced.
"""
from __future__ import annotations
import argparse
import contextlib
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import studio
import dispatch
import catalog_cli
import pack_manager as pm
from generation_payload_smoke_test import (_write_fixture_pack,_production_spec,_stateless_lineage,
    PACK_ID,MODEL_ID,APPROVED_PLOT,PROMPT,NEGATIVE,INTEGRATED_PROMPT,NEGATIVE_PROVENANCE)
from smoke_fixtures import fixture_retrieval
from build_generation_payload import main as build_main
from verify_generation_payload import verify


def run(out:Path)->dict:
    out=out.resolve()
    if out.exists():raise ValueError('walkthrough output already exists; choose a new directory')
    out.mkdir(parents=True)
    pack=out/'fixture-pack';_write_fixture_pack(pack)
    state=out/'pack-state.json';pm.save_state(state,{'pack_roots':[str(pack)],'enabled_packs':[PACK_ID],'resource_providers':{}})
    settings=pm.default_settings(state_file=state,cache_dir=out/'cache',managed_root=out/'managed')
    for name,text in [('prompt.txt',PROMPT),('negative.txt',NEGATIVE),('integrated.txt',INTEGRATED_PROMPT)]:
        (out/name).write_text(text+'\n',encoding='utf-8')
    plot=json.loads(json.dumps(APPROVED_PLOT));plot['approved']['by']='OFFLINE WALKTHROUGH FIXTURE - NOT REAL USER CONSENT'
    objects={'plot.json':plot,'retrieval.json':fixture_retrieval(PROMPT,plot),
             'intent.json':{'image_promise':'Offline fictional character fixture'},
             'production.json':_production_spec(MODEL_ID,_stateless_lineage()),'negative-provenance.json':NEGATIVE_PROVENANCE}
    for name,value in objects.items():pm.atomic_write_json(out/name,value)
    import production_fixtures as fixture
    import production_workflow as workflow
    root=studio.init(out/'studio','offline-walkthrough','Offline workflow fixture')
    studio.add_character(root,'C01','')
    run_id=fixture.prepare_dispatch(root,PROMPT)
    args=['--production-root',str(root),'--production-run',run_id,'--model',MODEL_ID,'--prompt-file',str(out/'prompt.txt'),'--negative-file',str(out/'negative.txt'),
          '--integrated-prompt-file',str(out/'integrated.txt'),'--plot-file',str(out/'plot.json'),
          '--retrieval-record-file',str(out/'retrieval.json'),'--production-spec-file',str(out/'production.json'),
          '--intent-file',str(out/'intent.json'),'--negative-provenance-file',str(out/'negative-provenance.json'),
          '--state-file',str(state),'--cache-dir',str(out/'cache'),'--managed-root',str(out/'managed'),
          '--parameters','{"size":"1024x1024","quality":"high"}','--out',str(out/'generation-package.json')]
    pm.atomic_write_json(out/'builder-arguments.json',args)
    transcript=io.StringIO()
    with contextlib.redirect_stdout(transcript):build_main(args)
    catalog_cli.configure_pack_runtime(settings)
    package=pm.load_json(out/'generation-package.json')
    verified=verify(package,package_root=out);pm.atomic_write_json(out/'verified.json',verified)
    options=argparse.Namespace(package=out/'generation-package.json',service=None,profiles=None,seed=7,count=1,
        send=True,character='C01',slot='base.front',note='OFFLINE MOCK RESULT')
    transport=SimpleNamespace(build=Mock(return_value={'taskUUID':'offline-fixture','prompt':PROMPT}),
        media_paths=Mock(return_value=[]),upload=Mock(side_effect=AssertionError('unexpected upload')),
        send=Mock(return_value={'data':'OFFLINE MOCK'}),rejections=Mock(return_value=[]),
        results=Mock(return_value=[{'url':'https://example.invalid/offline.png','id':'offline','seed':7}]))
    def save(url,destination):
        from PIL import Image
        Image.new('RGB',(24,24),'white').save(destination)
        return studio.sha256_file(destination)
    offering={'service':'fixture','model_identifier':MODEL_ID,'observed_at':'2026-09-15'}
    options.production_root=root
    options.production_run=run_id
    options.production_authorization=fixture.grant(root,run_id,workflow.submission_intent(
        package,seed=7,count=1,offering=offering,service={}))
    with contextlib.ExitStack() as stack:
        stack.enter_context(contextlib.redirect_stdout(transcript))
        for name,kw in {'select_offering':{'return_value':offering},'service_for':{'return_value':('fixture',{},transport)},
            'check_request':{},'api_key':{'return_value':'OFFLINE-NO-REAL-KEY'},'save':{'side_effect':save}}.items():
            stack.enter_context(patch.object(dispatch,name,**kw))
        dispatch.dispatch_generation(options,root)
    report={'ok':True,'offline_fixture':True,'external_requests':0,'mock_dispatch_count':transport.send.call_count,
            'verified':verified['verified'],'iterations':len(studio.read_iterations(studio.character_dir(root,'C01'))),
            'output':str(out),'note':'Synthetic lookups and approvals exercise structure, not real consent or image quality.'}
    pm.atomic_write_json(out/'walkthrough-report.json',report)
    (out/'transcript.txt').write_text(transcript.getvalue(),encoding='utf-8')
    catalog_cli.configure_pack_runtime(None)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args(argv)
    try:report=run(args.out)
    except (ValueError,OSError,RuntimeError) as exc:parser.error(str(exc))
    print(json.dumps(report,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
