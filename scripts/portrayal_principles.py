#!/usr/bin/env python3
"""Read a small CPB-authored portrayal-pattern library, not prompt-performance evidence.

    python scripts/portrayal_principles.py search 'steady contrast'
    python scripts/portrayal_principles.py inspect persistence
    python scripts/portrayal_principles.py validate

Exact English token retrieval only. Read complete selected records before use.
No persona is generated or adopted, no state is mutated and no quality is scored.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
from typing import Any, Sequence
from state_protocol import parse_json

ROOT=Path(__file__).resolve().parents[1]
LIBRARY=ROOT/'references/portrayal-principles.json'
TEXT_FIELDS=('id','name','recognition_logic','held_dimensions','variation_envelope','temporal_shape',
             'channel_translation','world_constraints','example','counterexample','adoption_instruction','source_basis')
LIST_FIELDS=('tags','activation_questions','misuses')


def validate(value: Any) -> list[str]:
    if not isinstance(value,dict) or set(value)!={'collection','scope','records'}:
        return ['expected collection, scope and records']
    if value['collection']!='portrayal-principles' or not isinstance(value['scope'],str) or not value['scope'].strip():
        return ['invalid collection declaration']
    if not isinstance(value['records'],list):
        return ['records must be an array']
    errors=[]; ids=set()
    for index,row in enumerate(value['records']):
        if not isinstance(row,dict) or set(row)!=set(TEXT_FIELDS+LIST_FIELDS):
            errors.append(f'record {index}: incomplete record structure'); continue
        for key in TEXT_FIELDS:
            if not isinstance(row[key],str) or not row[key].strip():
                errors.append(f'record {index}: missing {key}')
        for key in LIST_FIELDS:
            if not isinstance(row[key],list) or not row[key] or any(not isinstance(x,str) or not x.strip() for x in row[key]):
                errors.append(f'record {index}: invalid {key}')
        identifier=row['id']
        if not isinstance(identifier,str) or not re.fullmatch('[a-z][a-z0-9-]*',identifier):
            errors.append(f'record {index}: invalid ID')
        elif identifier in ids:
            errors.append(f'duplicate ID: {identifier}')
        else:
            ids.add(identifier)
    return errors


def load() -> dict[str,Any]:
    value=parse_json(LIBRARY.read_text(encoding='utf-8'))
    errors=validate(value)
    if errors: raise ValueError('; '.join(errors))
    return value


def search(value: dict[str,Any], query: str, limit: int = 8) -> list[dict[str,Any]]:
    words=set(re.findall('[a-z0-9]+',query.lower()))
    rows=[]
    for row in value['records']:
        haystack=' '.join([row['id'],row['name'],row['recognition_logic'],*row['tags']]).lower()
        matches=sorted(words & set(re.findall('[a-z0-9]+',haystack)))
        if matches:
            rows.append({'id':row['id'],'name':row['name'],'matched_terms':matches})
    return sorted(rows,key=lambda r:(-len(r['matched_terms']),r['id']))[:limit]


def main(argv: Sequence[str]|None=None) -> int:
    p=argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('command',choices=('search','inspect','validate')); p.add_argument('value',nargs='?')
    p.add_argument('--limit',type=int,default=8)
    a=p.parse_args(argv)
    if a.limit<1: p.error('limit must be a positive integer')
    if a.command!='validate' and (not a.value or not a.value.strip()): p.error('search or inspect requires nonblank text')
    try:
        data=load()
        if a.command=='validate': result={'ok':True,'record_count':len(data['records'])}
        elif a.command=='search': result={'ok':True,'scope':data['scope'],'results':search(data,a.value,a.limit)}
        else:
            matches=[x for x in data['records'] if x['id']==a.value]
            if not matches: raise ValueError(f'unknown principle ID: {a.value}')
            result={'ok':True,'scope':data['scope'],'record':matches[0]}
        print(json.dumps(result,ensure_ascii=False,indent=2)); return 0
    except (OSError,ValueError) as exc:
        print(json.dumps({'ok':False,'errors':[str(exc)]},indent=2)); return 1


if __name__=='__main__': raise SystemExit(main())
