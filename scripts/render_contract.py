#!/usr/bin/env python3
"""Choose a render intent, inspect model guidance, or compile an explicit plan."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import render_contract_lib as r


def load(path: str):
    from state_protocol import parse_json
    return parse_json(Path(path).read_text(encoding='utf-8'))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
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
            _, record = resolve_model_record(args.model)
            offering = select_offering(record, args.service)
            if args.command == 'model':
                result = r.model_card(record, offering)
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
    raise SystemExit(main())
