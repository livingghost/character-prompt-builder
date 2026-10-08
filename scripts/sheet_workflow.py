#!/usr/bin/env python3
"""Prepare panel batches, compare candidates, and adopt exact sheet artwork."""
from __future__ import annotations
import operation_context as _operation_context
import argparse
import json
from pathlib import Path

import execution_contract as c
import sheet_artifacts as fills


def parser() -> argparse.ArgumentParser:
    cli = _operation_context.ArgumentParser(description=__doc__)
    commands = cli.add_subparsers(dest='command', required=True)
    listing = commands.add_parser('batch-list')
    listing.add_argument('--root', type=Path, required=True)
    listing.add_argument('--limit', type=int, default=50)
    listing.add_argument('--offset', type=int, default=0)
    for name in ('batch-init', 'batch-run'):
        sub = commands.add_parser(name)
        sub.add_argument('--root', type=Path, required=True)
        sub.add_argument('--state', required=name == 'batch-run', help='Studio-relative journal; batch-init allocates a dated attempt when omitted')
        if name == 'batch-init':
            sub.add_argument('--plan', required=True, help='Studio-relative sheet-fill-plan JSON')
        else:
            sub.add_argument('--grant', help='Draft exact decisions under this grant; never approve them')
            sub.add_argument('--decisions-file', help='Studio-relative JSON mapping request IDs to completed execution decisions')
            sub.add_argument('--unreceived-only', action='store_true', help='Recover missing results without repeating completed submissions')
    for name in ('status', 'import', 'draft-adoption', 'adopt', 'crop', 'share', 'apply-edit', 'reoffer', 'reject'):
        sub = commands.add_parser(name)
        sub.add_argument('--sheet', type=Path, required=True, help='The selected sheet-data.json')
        if name in {'import', 'draft-adoption', 'reoffer', 'reject'}: sub.add_argument('--slot', required=True)
        if name == 'status':
            sub.add_argument('--slot')
            sub.add_argument('--state-filter', choices=('current', 'candidate', 'history'))
            sub.add_argument('--disposition')
            sub.add_argument('--limit', type=int, default=50)
            sub.add_argument('--offset', type=int, default=0)
            sub.add_argument('--metadata-only', action='store_true')
        elif name == 'apply-edit':
            sub.add_argument('--edit', type=Path, required=True, help='Authored difference exported by the HTML editor')
        elif name == 'reoffer':
            sub.add_argument('--artifact', required=True)
        elif name == 'reject':
            sub.add_argument('--artifact', required=True)
            sub.add_argument('--reason', required=True, help='Why this candidate is dismissed; recorded in the activity log')
            sub.add_argument('--by', required=True, help='Who dismisses it')
        elif name == 'import':
            sub.add_argument('--image', type=Path, required=True)
            sub.add_argument('--package', type=Path, required=True)
            sub.add_argument('--note', required=True, help='Provenance of the external import, not an acceptance')
        elif name == 'draft-adoption':
            sub.add_argument('--artifact', required=True)
            sub.add_argument('--out', type=Path)
        elif name == 'adopt':
            sub.add_argument('--decision-file', type=Path, required=True)
            sub.add_argument('--evidence-root', type=Path, required=True)
        elif name == 'crop':
            sub.add_argument('--source-slot', required=True); sub.add_argument('--target-slot', required=True)
            sub.add_argument('--rectangle', nargs=4, type=int, metavar=('X', 'Y', 'WIDTH', 'HEIGHT'), required=True)
            sub.add_argument('--local-scale', type=int, default=1, help='Explicit Lanczos scale; use an upscale task for a model')
        elif name == 'share':
            sub.add_argument('--source-slot', required=True)
            sub.add_argument('--targets', type=Path, required=True, help='JSON list of {sheet,slot}; sheet paths are relative to this file')
    for name in ('compose-scale', 'review'):
        sub = commands.add_parser(name); sub.add_argument('--spec', type=Path, required=True)
        if name == 'review': sub.add_argument('--out', type=Path)
    return cli


def spec_path(path: str, spec: Path) -> Path:
    """A composition/review author may name a sheet relative to the spec or absolutely."""
    selected = Path(path)
    return selected if selected.is_absolute() else (spec.parent / selected).resolve()


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command.startswith('batch-'):
            import studio, sheet_batch
            root = studio.require_studio(args.root)
            if args.command == 'batch-list':
                result = sheet_batch.list_batches(root, limit=args.limit, offset=args.offset)
            elif args.command == 'batch-init':
                result = sheet_batch.initialize(root, args.plan, args.state)
            else:
                decisions = c.load(c.local(root, args.decisions_file)) if args.decisions_file else None
                if decisions is not None and not isinstance(decisions, dict):
                    raise ValueError('execution decisions must map panel IDs to Studio-relative decision paths')
                result = sheet_batch.advance(root, args.state, grant=args.grant, decisions=decisions,
                                             unreceived_only=args.unreceived_only)
        elif args.command == 'status':
            import sheet_inventory
            result = sheet_inventory.status(args.sheet, slot=args.slot, state_filter=args.state_filter,
                disposition=args.disposition, limit=args.limit, offset=args.offset, verify=not args.metadata_only)
        elif args.command == 'apply-edit':
            import sheet_edits
            result = sheet_edits.apply(args.sheet, c.load(args.edit))
        elif args.command == 'reoffer':
            result = fills.reoffer(args.sheet, args.slot, args.artifact)
        elif args.command == 'reject':
            result = fills.reject_candidate(args.sheet, args.slot, args.artifact, by=args.by, reason=args.reason)
        elif args.command == 'import':
            kind = 'upscale' if c.load(args.package).get('artifact_type') == 'upscale-package' else 'generation'
            artifact = fills.publish(args.sheet.parent, args.image, kind=kind, recipe={}, package=args.package,
                                     origin={'kind': 'external-import', 'note': c.text(args.note, 'import note')})
            result = fills.register_candidates(args.sheet, [(args.slot, artifact)])
        elif args.command == 'draft-adoption':
            result = fills.draft_adoption(args.sheet, args.slot, args.artifact)
            target = args.out or args.sheet.parent / '.fills/drafts/adoption' / (c.content_id(result) + '.json')
            if target.exists():
                held = c.load(target)
                for key in ('sheet', 'slot', 'artifact_id', 'expected_current'):
                    if held.get(key) != result[key]: raise ValueError('adoption draft destination belongs to another decision')
                result = held
            else:
                c.atomic(target, c.encoded(result))
            result = {**result, 'draft_file': str(target)}
        elif args.command == 'adopt':
            result = fills.adopt(args.sheet, c.load(args.decision_file), evidence_root=args.evidence_root)
        elif args.command == 'crop':
            result = fills.crop(args.sheet, args.source_slot, args.target_slot, args.rectangle, scale=args.local_scale)
        elif args.command == 'share':
            rows = c.load(args.targets)
            if not isinstance(rows, list) or not rows: raise ValueError('share targets must be a nonempty list')
            for row in rows: c.exact(row, {'sheet', 'slot'}, 'share target')
            result = fills.share(args.sheet, args.source_slot, [(spec_path(row['sheet'], args.targets), row['slot']) for row in rows])
        elif args.command == 'compose-scale':
            spec = c.load(args.spec)
            c.exact(spec, {'sheet', 'slot', 'sources', 'pixels_per_unit', 'padding', 'gap', 'background'}, 'scale composition')
            rows = [{**row, 'sheet': str(spec_path(row['sheet'], args.spec))} for row in spec['sources']]
            result = fills.compose_scale(spec_path(spec['sheet'], args.spec), spec['slot'], rows,
                        pixels_per_unit=spec['pixels_per_unit'], padding=spec['padding'], gap=spec['gap'], background=spec['background'])
        else:
            import sheet_review
            spec = c.load(args.spec)
            c.exact(spec, {'anchor', 'candidates', 'regions', 'cell_size', 'pairs_per_page'}, 'sheet review')
            anchor = {**spec['anchor'], 'sheet': str(spec_path(spec['anchor']['sheet'], args.spec))}
            candidates = [{**row, 'sheet': str(spec_path(row['sheet'], args.spec))} for row in spec['candidates']]
            from studio_activity import timestamp
            from pack_manager import generate_uuid7
            stamp = timestamp()
            target = args.out or Path(anchor['sheet']).parent / '.fills/reviews' / stamp[:10] / (stamp[11:26].replace(':','').replace('.','')+'Z-'+generate_uuid7())
            result = sheet_review.build_review(anchor, candidates, spec['regions'], out_dir=target,
                        cell_size=spec['cell_size'], pairs_per_page=spec['pairs_per_page'])
            result['output_directory'] = str(target)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return result.get('exit_code', 2 if result.get('ok') is False else 0)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
