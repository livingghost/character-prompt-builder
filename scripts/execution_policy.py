"""Resolve local execution policy and preserve its original byte witnesses."""
from __future__ import annotations
from pathlib import Path
import execution_contract as c
from input_evidence import InputEvidence


def load_policy(record:dict|None,reader:InputEvidence,target:dict,*,dialect:str|None=None)->tuple[dict,InputEvidence]:
    ref=(record or {}).get('execution_policy')
    if ref is None:return {},reader
    value=reader.json(ref);local=reader.at(ref)
    required={'artifact_type','target','text_dialect','production_context_transport','reference_instruction_transport','basis'}
    optional={'label','observed_at','parameter_observations','reference_schemas','host_interface'}
    if not isinstance(value,dict) or set(value)-required-optional or not required<=set(value):raise ValueError('invalid local execution policy fields')
    if value['artifact_type']!='execution-policy' or value['target']!=target:raise ValueError('execution policy target mismatch')
    c.text(value['text_dialect'],'explicit text dialect');local.basis(value['basis'])
    if dialect is not None and value['text_dialect']!=dialect:raise ValueError('execution policy text dialect differs from the selected model record')
    if value['production_context_transport'] not in {'none','prompt-prefix'}:raise ValueError('unknown production context transport')
    if value['reference_instruction_transport'] is not None:
        c.exact(value['reference_instruction_transport'],{'mode','contract'},'reference instruction policy')
    return value,local
