"""Bind local input records to their captured source bytes and canonical hashes."""
from __future__ import annotations
import copy
from pathlib import Path
import execution_contract as c
import runtime_evidence
import request_validation
from execution_policy import load_policy


def capture_validation(record:dict,*,root:Path|None,snapshots:dict|None=None,live:bool=True):
    reader=runtime_evidence.reader(root,snapshots=copy.deepcopy(snapshots) if snapshots is not None else None,live=live)
    report=request_validation.require(record,reader)
    policy,local=load_policy(record,reader,record['target'])
    reference=policy.get('reference_instruction_transport')
    if reference is not None:
        contract=local.json(reference['contract']);local.at(reference['contract']).basis(contract['basis'])
    return reader,report


def verify_fields(data:dict,*,root:Path|None,live:bool=True):
    for field in ('request_validation','input_snapshots'):
        if field not in data or field+'_sha256' not in data or c.content_id(data[field])!=data[field+'_sha256']:
            raise ValueError(field+' does not match its committed input hash')
    return capture_validation(data['request_validation'],root=root,snapshots=data['input_snapshots'],live=live)


def attach(data:dict,record:dict,reader)->None:
    data['request_validation']=copy.deepcopy(record);data['request_validation_sha256']=c.content_id(record)
    data['input_snapshots']=copy.deepcopy(reader.snapshots);data['input_snapshots_sha256']=c.content_id(data['input_snapshots'])
    if 'generation_contract' in data:
        for field in ('request_validation_sha256','input_snapshots_sha256'):data['generation_contract'][field]=data[field]
