#!/usr/bin/env python3
"""Project reference authority onto the actual delivered image order or board regions.

python scripts/reference_delivery.py --prepared-set FILE [--package-root DIRECTORY]
python scripts/reference_delivery.py --image-input-plan FILE [--studio DIRECTORY]
This does not select references, infer identity, inspect images or grant authority.
"""
from __future__ import annotations
import operation_context as _operation_context
import argparse
import copy
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

SUBJECT_USE_RULE = ('Subject IDs identify characters, not extra people per reference. '
                    'Each use is limited by its declared source authority. Lower priority numbers win only '
                    'within the same subject and use; equal priorities provide complementary evidence.')


def validate_subject_uses(value: Any, *, subject_ids: set[str] | None = None,
                          allowed_uses: Sequence[str] | None = None) -> list[dict[str, Any]]:
    """Check authored subject/use priorities without inventing visual authority."""
    from reference_contract import INTENDED_INFLUENCES
    if not isinstance(value, list):
        raise ValueError('subject_uses must be an array')
    seen = set()
    for row in value:
        if not isinstance(row, Mapping) or set(row) != {'subject_id', 'use', 'priority'}:
            raise ValueError('each subject use requires subject_id, use and priority')
        subject, use, priority = row['subject_id'], row['use'], row['priority']
        if not isinstance(subject, str) or not subject.strip() or subject != subject.strip():
            raise ValueError('subject use requires a nonempty subject_id')
        if subject_ids is not None and subject not in subject_ids:
            raise ValueError('reference names an unknown subject: ' + subject)
        if use not in INTENDED_INFLUENCES:
            raise ValueError('subject use must name a declared reference influence')
        if allowed_uses is not None and use not in allowed_uses:
            raise ValueError('subject use exceeds the source influence: ' + use)
        if not isinstance(priority, int) or isinstance(priority, bool) or priority < 0:
            raise ValueError('subject use priority must be a nonnegative integer')
        if (subject, use) in seen:
            raise ValueError('a reference repeats a subject and use')
        seen.add((subject, use))
    return copy.deepcopy(value)


def validate_reference_subjects(references: Sequence[Mapping[str, Any]],
                                production_spec: Mapping[str, Any]) -> None:
    """Resolve every authored subject name against this image's actual cast."""
    subjects = production_spec.get('subjects')
    if not isinstance(subjects, list):
        raise ValueError('reference subject checks require Production Specification subjects')
    ids = {row['id'] for row in subjects if isinstance(row, Mapping) and isinstance(row.get('id'), str)}
    for reference in references:
        validate_subject_uses(reference.get('subject_uses', []), subject_ids=ids)


def validate_reference_selection_subjects(selection: Mapping[str, Any] | None,
                                          production_spec: Mapping[str, Any]) -> None:
    """Match each independent reference state to its actual scene subject."""
    if production_spec['state_context']['mode'] == 'stateless':
        if selection is not None:
            raise ValueError('stateless generation must use a null reference-selection origin')
        return
    if selection is None:
        raise ValueError('state-aware generation requires a finalized reference-selection')
    subjects = {row['id']: row for row in production_spec['subjects'] if 'state_snapshot_ref' in row}
    contexts = {row['subject_id']: row for row in selection['subjects']}
    if len(contexts) != len(selection['subjects']) or set(contexts) != set(subjects):
        raise ValueError('reference-selection subjects must exactly match the state-aware Production Specification')
    for subject_id, context in contexts.items():
        subject = subjects[subject_id]
        for selected_field, spec_field in (
            ('identity_contract_sha256', 'identity_contract_ref'),
            ('state_snapshot_sha256', 'state_snapshot_ref'),
        ):
            if context[selected_field] != (subject.get(spec_field) or {}).get('sha256'):
                raise ValueError(f'reference-selection {selected_field} differs from subject {subject_id}')
    validate_reference_subjects(selection['selected_references'], production_spec)


def reference_selection_lineage_subject(selection: Mapping[str, Any],
                                        lineage: Mapping[str, Any]) -> Mapping[str, Any]:
    """Locate the subject governed by an existing single-character state lineage."""
    matches = [row for row in selection['subjects']
               if all(row[field] == lineage.get(field)
                      for field in ('identity_contract_sha256', 'state_snapshot_sha256'))]
    if len(matches) != 1:
        raise ValueError('reference-selection must contain the unique subject governed by state lineage')
    context = matches[0]
    for field in ('era_contract_sha256', 'appearance_variant_sha256'):
        if context[field] != lineage.get(field):
            raise ValueError(f'reference-selection {field} differs from state lineage')
    return context


def attachment_numbers(references: Sequence[Mapping[str, Any]]) -> list[int]:
    """Retain logical references while sending identical committed media once."""
    seen: dict[tuple[str | None, str], int] = {}
    result = []
    for row in references:
        transport = row['transport']
        key = (transport.get('media_type'), transport['sha256'])
        if key not in seen:
            seen[key] = len(seen) + 1
        result.append(seen[key])
    return result


def delivered_reference_count(reference_set: Mapping[str, Any]) -> int:
    references = reference_set.get('selected_references') or []
    if reference_set.get('transport_mode') == 'single-board':
        return int(bool(references))
    return len(set(attachment_numbers(references)))


def prepared_origin_projection(reference_set: Mapping[str, Any]) -> dict[str, Any]:
    """Preserve source authority while allowing committed carriers to be relocated."""
    result = copy.deepcopy(dict(reference_set))
    for field in ('image_input_binding', 'set_id', 'prepared_reference_set_sha256'):
        result.pop(field, None)
    for row in result.get('selected_references', []):
        row['transport'].pop('resolved_path', None)
    if result.get('single_board') is not None:
        result['single_board'].pop('resolved_path', None)
    return result


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
    positions = attachment_numbers(references)
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
        item = {'reference_number': index, 'attachment_number': 1 if mode == 'single-board' else positions[index - 1],
                       'region_pixels': region, 'role': row['role'],
                       'controls': list(row['authority']['controls']),
                       'must_not_control': list(row['authority']['must_not_control'])}
        if 'subject_uses' in row:
            item['subject_uses'] = validate_subject_uses(row['subject_uses'])
        if 'subject_id' in row:
            item['subject_id'] = row['subject_id']
        output.append(item)
    return output


def instructions(mode: str, references: Sequence[Mapping[str, Any]],
                 board: Mapping[str, Any] | None = None) -> str:
    rows = bindings(mode, references, board)
    return binding_instructions(rows)


def binding_instructions(rows: Sequence[Mapping[str, Any]]) -> str:
    """Render the same committed subject, scope and image map for every request."""
    if not rows:
        return ''
    lines = ['Reference numbers below refer to the actual delivery, not a source-library index.']
    if any(row.get('subject_uses') for row in rows):
        lines.append(SUBJECT_USE_RULE)
    if any(row['region_pixels'] is not None for row in rows):
        lines.append('There is one attached image: Image 1 is a reference board, not the requested output layout. '
                     'Its regions use pixels from the top-left corner. Do not reproduce the board grid unless the authored output explicitly requests it.')
    for row in rows:
        if 'request_field' in row:
            path = row['request_field']
            if (not isinstance(path, list) or not path
                    or any(not isinstance(part, (str, int)) or isinstance(part, bool)
                           or (isinstance(part, int) and part < 0)
                           or (isinstance(part, str) and not part) for part in path)):
                raise ValueError('reference request_field must be a nonempty JSON field path')
            location = 'request field ' + json.dumps(path, ensure_ascii=False, separators=(',', ':'))
        else:
            location = f'Image {row["attachment_number"]}'
        if row['region_pixels'] is not None:
            b = row['region_pixels']
            location += f', region x={b["x"]}, y={b["y"]}, width={b["width"]}, height={b["height"]}'
        line = f'Reference {row["reference_number"]} means {location}. Use it for: ' + '; '.join(row['controls']) + '.'
        if row.get('subject_id'):
            line += f' Apply this reference only to subject {row["subject_id"]}.'
        if row.get('subject_uses'):
            line += ' Apply these uses: ' + '; '.join(
                f'subject {use["subject_id"]}, {use["use"]}, priority {use["priority"]}'
                for use in row['subject_uses']) + '.'
        if row['must_not_control']:
            line += ' Do not inherit: ' + '; '.join(row['must_not_control']) + '.'
        lines.append(line)
    groups: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for row in rows:
        for use in row.get('subject_uses', []):
            groups.setdefault((use['subject_id'], use['use']), []).append((use['priority'], row['reference_number']))
    for (subject, use), members in groups.items():
        if len(members) > 1:
            lines.append(f'For subject {subject}, {use} sources in priority order: ' + '; '.join(
                f'Reference {number} (priority {priority})' for priority, number in sorted(members)) + '.')
    return '\n'.join(lines) + '\n'


def main() -> int:
    parser = _operation_context.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--prepared-set', type=Path)
    source.add_argument('--image-input-plan', type=Path)
    parser.add_argument('--package-root', type=Path)
    parser.add_argument('--studio', type=Path, help='Resolve an image input plan\'s existing prepared references')
    args = parser.parse_args()
    try:
        from execution_contract import load
        if args.image_input_plan is not None:
            import image_input
            plan = load(args.image_input_plan)
            rows = image_input.reference_bindings(plan, base=args.studio)
            print(json.dumps({'ok': True, 'bindings': rows,
                'reference_preamble': binding_instructions(rows),
                'limit': 'Request field and scope projection does not establish visual suitability.'},
                ensure_ascii=False, indent=2))
            return 0
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
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
