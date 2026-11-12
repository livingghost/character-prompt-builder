"""Resolve local execution policy and preserve its original byte witnesses."""
from __future__ import annotations
from pathlib import Path
import execution_contract as c
from input_evidence import InputEvidence

REQUIRED_FIELDS = frozenset({'artifact_type', 'target', 'text_dialect', 'reference_instruction_transport', 'basis'})
OPTIONAL_FIELDS = frozenset({'label', 'observed_at', 'parameter_observations', 'reference_schemas', 'host_interface'})


def load_policy(record:dict|None,reader:InputEvidence,target:dict,*,dialect:str|None=None)->tuple[dict,InputEvidence]:
    ref=(record or {}).get('execution_policy')
    if ref is None:return {},reader
    value=reader.json(ref);local=reader.at(ref)
    if not isinstance(value,dict) or set(value)-REQUIRED_FIELDS-OPTIONAL_FIELDS or not REQUIRED_FIELDS<=set(value):
        raise ValueError('invalid local execution policy fields; required fields: '+', '.join(sorted(REQUIRED_FIELDS))+
                         '; permitted fields: '+', '.join(sorted(REQUIRED_FIELDS|OPTIONAL_FIELDS)))
    if value['artifact_type']!='execution-policy' or value['target']!=target:raise ValueError('execution policy target mismatch')
    c.text(value['text_dialect'],'explicit text dialect');local.basis(value['basis'])
    if dialect is not None and value['text_dialect']!=dialect:raise ValueError('execution policy text dialect differs from the selected model record')
    if value['reference_instruction_transport'] is not None:
        c.exact(value['reference_instruction_transport'],{'mode','contract'},'reference instruction policy')
    return value,local
