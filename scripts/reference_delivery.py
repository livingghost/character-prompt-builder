#!/usr/bin/env python3
"""Project reference authority onto the actual delivered image order or board regions.

python scripts/reference_delivery.py --prepared-set FILE [--package-root DIRECTORY]
This does not select references, infer identity, inspect images or grant authority.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


def validate_authority_scope(authority: Mapping[str, Any]) -> None:
    """Reject explicit self-conflict, not guessed synonyms or semantic disagreement."""
    positive = {str(x).strip().casefold() for x in authority['controls']}
    negative = {str(x).strip().casefold() for x in authority['must_not_control']}
    conflict = positive & negative
    if conflict:
        raise ValueError('reference authority both allows and forbids: ' + ', '.join(sorted(conflict)))


def bindings(mode: str, references: Sequence[Mapping[str, Any]],
             board: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    if mode not in {'multi-image', 'single-board'}:
        if mode in {'none', 'prompt-artifacts', 'svg-bundle'}:
            return []
        raise ValueError('unsupported reference transport mode')
    if not references:
        raise ValueError('model-facing reference instructions need the actual prepared rows')
    panels = board.get('panels') if board is not None else None
    if mode == 'single-board' and (not isinstance(panels, list) or len(panels) != len(references)):
        raise ValueError('single-board instructions need every actual panel in delivered order')
    if mode == 'multi-image' and board is not None:
        raise ValueError('multi-image instructions cannot refer to a composite board')
    output = []
    for index, row in enumerate(references, 1):
        validate_authority_scope(row['authority'])
        region = None
        if mode == 'single-board':
            panel = panels[index - 1]
            if panel['source_sha256'] != row['source']['sha256'] or panel['transport_sha256'] != row['transport']['sha256']:
                raise ValueError('board panel does not bind the corresponding prepared image bytes')
            if panel['semantic_role'] != row['role']:
                raise ValueError('board panel role differs from its prepared reference')
            box = panel['box']
            if set(box) != {'x', 'y', 'width', 'height'}:
                raise ValueError('board panel requires exact pixel bounds')
            for key, value in box.items():
                if not isinstance(value, int) or isinstance(value, bool) or value < (1 if key in {'width', 'height'} else 0):
                    raise ValueError('invalid board pixel bounds')
            region = dict(box)
        output.append({'reference_number': index, 'attachment_number': 1 if mode == 'single-board' else index,
                       'region_pixels': region, 'role': row['role'],
                       'controls': list(row['authority']['controls']),
                       'must_not_control': list(row['authority']['must_not_control'])})
    return output


def instructions(mode: str, references: Sequence[Mapping[str, Any]],
                 board: Mapping[str, Any] | None = None) -> str:
    rows = bindings(mode, references, board)
    if not rows:
        return ''
    lines = ['Reference numbers below refer to the actual delivery, not a source-library index.']
    if mode == 'single-board':
        lines.append('There is one attached image: Image 1 is a reference board, not the requested output layout. '
                     'Its regions use pixels from the top-left corner. Do not reproduce the board grid unless the authored output explicitly requests it.')
    for row in rows:
        location = f'Image {row["attachment_number"]}'
        if row['region_pixels'] is not None:
            b = row['region_pixels']
            location += f', region x={b["x"]}, y={b["y"]}, width={b["width"]}, height={b["height"]}'
        lines.append(f'Reference {row["reference_number"]} means {location}. '
                     'Use it for: ' + '; '.join(row['controls']) + '. '
                     'Do not inherit: ' + '; '.join(row['must_not_control']) + '.')
    return '\n'.join(lines) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared-set', type=Path, required=True)
    parser.add_argument('--package-root', type=Path)
    args = parser.parse_args()
    try:
        from execution_contract import load
        from prepare_generation_references import validate_prepared_reference_set
        value = validate_prepared_reference_set(load(args.prepared_set), package_root=args.package_root)
        result = {'ok': True, 'bindings': bindings(value['transport_mode'], value['selected_references'], value['single_board']),
                  'reference_preamble': value['reference_preamble'],
                  'limit': 'Byte and order verification does not establish visual suitability.'}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError, RuntimeError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
