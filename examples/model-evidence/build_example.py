#!/usr/bin/env python3
"""Run attributed schema import through the public CLI using synthetic local evidence."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import execution_contract as c


def execute(args):
    result=subprocess.run([sys.executable,*args],capture_output=True,text=True,timeout=60)
    if result.returncode:raise ValueError(result.stdout+result.stderr)
    return json.loads(result.stdout)


def build():
    with tempfile.TemporaryDirectory(prefix='synthetic-model-evidence-') as directory:
        root=Path(directory)
        import generation_payload_smoke_test as fixture
        import pack_manager as pm
        import observe_model_schema as observer
        pack=root/'source-pack';fixture._write_fixture_pack(pack);pm.write_lock(pack)
        _,document,i,j=observer._selection(pack,fixture.OFFERED_MODEL_ID,'runware')
        offering=document['records'][i]['offerings'][j]
        schema=c.load(pack/offering['schema_snapshot'])['schema']
        target={'service':'runware','model_identifier':offering['model_identifier'],'operation':'imageInference'}
        before=c.read(pack/'records/models.json')
        raw=b'{ "schema" : '+json.dumps(schema).encode()+b' }\n'
        (root/'response.json').write_bytes(raw)
        acquisition={'artifact_type':'schema-acquisition','target':target,
            'source':{'kind':'document','identifier':'Synthetic service document','locator':'schema'},
            'acquired_at':'2000-01-01T00:00:00Z','response':{'path':'response.json','sha256':c.digest(raw)},
            'status':{'document_status':'schema-provided'}}
        (root/'acquisition.json').write_bytes(c.encoded(acquisition))
        result=execute([str(ROOT/'scripts/observe_model_schema.py'),'schema','--root',str(root),
            '--pack',str(pack),'--out-pack',str(root/'observed-pack'),'--release','2026.09.22.1',
            '--model',fixture.OFFERED_MODEL_ID,'--service','runware','--operation','imageInference',
            '--entry','synthetic-source','--acquisition','acquisition.json','--pointer','/schema'])
        target_pack=root/'observed-pack'
        _,updated,i,j=observer._selection(target_pack,fixture.OFFERED_MODEL_ID,'runware')
        observed=updated['records'][i]['offerings'][j]
        contract=c.load(target_pack/observed['schema_contract']['path'])
        same_raw=c.read(target_pack/'resources/model-evidence/synthetic-source/response.json')==raw
        result_report={'synthetic':True,'target':result['target'],'source_records_unchanged':c.read(pack/'records/models.json')==before,
            'acquired_response_unchanged':same_raw,'schema_content_matches':contract['schema']==schema,
            'new_pack_valid':pm.validate_pack(target_pack,require_lock=True,verify_lock=True).valid,
            'activation_required':result['activation_required'],'external_effect':result['external_effect'],
            'budget_effect':result['budget_effect']}
        if not all(result_report[k] for k in ('source_records_unchanged','acquired_response_unchanged','schema_content_matches','new_pack_valid')):
            raise ValueError('Published evidence differs from the selected synthetic source.')
        return result_report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true')
    args=parser.parse_args();path=Path(__file__).with_name('report.json');raw=c.encoded(build())
    if args.check:
        if not path.is_file() or c.read(path)!=raw:raise ValueError('Rebuild the synthetic model evidence report.')
    else:path.write_bytes(raw)
    print(raw.decode(),end='');return 0

if __name__=='__main__':raise SystemExit(main())
