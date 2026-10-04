#!/usr/bin/env python3
"""Choose a render intent, inspect model guidance, or compile an explicit plan."""
from __future__ import annotations
import operation_context as _operation_context
import argparse
import json
from pathlib import Path
import render_contract_lib as r


def load(path: str):
    from state_protocol import parse_json
    return parse_json(Path(path).read_text(encoding='utf-8'))


def measured_basis(model_id: str, record: dict, offering: dict | None) -> dict | None:
    """Verify the adopted observed request profile a measured basis names; None for any other basis.

    Request validation checks the observed profile, its observation and the adoption
    decision. The offering's own contract hash includes the execution profile that names
    the basis, so the observation is held to the current service record and
    transport, and to its own recorded offering contract.
    """
    owner = offering if offering is not None else record
    profile = owner.get('execution_profile')
    reference = r.observed_profile_reference(profile) if profile is not None else None
    if reference is None:
        return None
    if offering is None:
        raise ValueError('a measured basis rests on a request observed on one service; declare the execution profile on that offering')
    import request_contract as rc
    import request_validation
    import runtime_evidence
    import service_profile
    import transport_contract
    from catalog_retrieval.runtime import load_pack_catalog
    reader = runtime_evidence.reader(None)
    contract = runtime_evidence.model_space(model_id) + '/' + reference['path']
    selected = reader.select(contract)
    if selected['sha256'] != reference['sha256']:
        raise ValueError('the observed profile a measured basis names has other content: ' + reference['path'])
    observed = reader.json(selected)
    if not isinstance(observed, dict) or observed.get('artifact_type') != 'observed-request-profile' \
            or not isinstance(observed.get('observation'), dict) or not isinstance(observed.get('execution'), dict):
        raise ValueError('a measured basis names an adopted observed request profile: ' + reference['path'])
    resource = load_pack_catalog().resources.get('service-profiles')
    if resource is None:
        raise ValueError('the active packs provide no service-profiles resource')
    service = service_profile.load_service(offering['service'], Path(resource.path))
    transport = transport_contract.load(service['transport'])
    current = rc.execution_hashes(service, offering, Path(transport.__file__), model=record, policy=None)
    recorded = observed['execution']
    for key in ('service_execution_sha256', 'transport_sha256'):
        if recorded.get(key) != current[key]:
            raise ValueError('the observed profile a measured basis names was observed with another ' + key.split('_')[0])
    target = {'service': offering['service'], 'model_identifier': offering['model_identifier'],
              'operation': transport.OPERATIONS[record.get('operation_kind') or 'generation']}
    return request_validation.build_record(
        {'mode': 'observed-profile', 'contract': contract,
         'evidence': reader.at(selected).qualify(observed['observation']['path']), 'execution_policy': None},
        reader, expected_target=target, execution=recorded)


def main(argv=None) -> int:
    parser = _operation_context.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('presets', help='List orthogonal finish choices; no model or subject is selected')
    make = sub.add_parser('intent', help='Create a consciously selected rendering intent')
    make.add_argument('--preset', required=True)
    make.add_argument('--mode', required=True, choices=sorted(r.MODES))
    make.add_argument('--chosen-by', required=True, choices=['user','agent'])
    make.add_argument('--reason', required=True)
    make.add_argument('--presentation', required=True)
    make.add_argument('--prompt-expression', default='', help='Exact authored prompt span; required before generation')
    make.add_argument('--out')
    check = sub.add_parser('validate-intent');check.add_argument('file')
    check.add_argument('--draft', action='store_true')
    check = sub.add_parser('validate-profile');check.add_argument('file')
    from pack_runtime_cli import add_pack_runtime_arguments
    for command in ('model', 'compile'):
        p = sub.add_parser(command)
        p.add_argument('--model', required=True);p.add_argument('--service')
        add_pack_runtime_arguments(p)
        if command == 'compile':
            p.add_argument('--intent', required=True);p.add_argument('--parameters', required=True)
            p.add_argument('--prompt-file', required=True);p.add_argument('--reference-count', required=True, type=int)
            p.add_argument('--out');p.add_argument('--text', action='store_true')
    args = parser.parse_args(argv)
    configured = False
    try:
        if args.command == 'presets':
            result = {'presets':list(r.presets().values()),'custom':'Set preset=null and explicitly author all axes.'}
        elif args.command == 'intent':
            result = r.make_intent(args.preset, mode=args.mode, chosen_by=args.chosen_by,
                                  reason=args.reason, presentation=args.presentation,
                                  prompt_expression=args.prompt_expression)
        elif args.command == 'validate-intent':
            r.validate_intent(load(args.file), for_generation=not args.draft);result={'ok':True}
        elif args.command == 'validate-profile':
            r.validate_profile(load(args.file));result={'ok':True}
        else:
            from pack_runtime_cli import resolve_pack_runtime
            from catalog_cli import configure_pack_runtime
            from prepare_generation_references import resolve_model_record
            from model_contract import select_offering
            runtime = resolve_pack_runtime(parser, args)
            configure_pack_runtime(runtime.settings);configured=True
            model_id, record = resolve_model_record(args.model)
            offering = select_offering(record, args.service)
            if args.command == 'model':
                result = r.model_card(record, offering)
                measured_basis(model_id, record, offering)
            else:
                if args.reference_count < 0:
                    raise ValueError('reference count must be nonnegative')
                result = r.compile_contract(record, offering, load(args.intent), load(args.parameters),
                    prompt=Path(args.prompt_file).read_text(encoding='utf-8'),reference_count=args.reference_count)
        raw = json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n'
        if getattr(args,'out',None):
            path=Path(args.out)
            with path.open('x',encoding='utf-8',newline='\n') as f:f.write(raw)
        print(r.summary(result) if getattr(args,'text',False) else raw, end='\n' if getattr(args,'text',False) else '')
        return 0
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(json.dumps({'ok':False,'errors':[str(exc)]},ensure_ascii=False));return 1
    finally:
        if configured:
            from catalog_cli import configure_pack_runtime
            configure_pack_runtime(None)

if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
