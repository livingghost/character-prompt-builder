#!/usr/bin/env python3
"""Summarize real production evidence under explicitly named study conditions.

python scripts/evaluation_evidence.py --project WORK --study study.json --out evaluations/NAME
Add --blind to export media-only review cards, with the operator key outside the cards.
No model is called. Missing observations and measurements are never invented.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import html
import json
import math
from pathlib import Path
import secrets
import statistics
from typing import Any

import artifact_review as review
import execution_contract as c
import production_workflow as workflow


def _rows(value: Any, label: str, *, nonempty: bool = True) -> list[dict]:
    if not isinstance(value, list) or (nonempty and not value) or any(not isinstance(x, dict) for x in value):
        raise ValueError(label + ' must be a list of objects')
    return value


def _indexed(rows: list[dict], label: str) -> dict[str, dict]:
    result = {}
    for row in rows:
        key = c.text(row.get('id'), label + ' id')
        if key in result:
            raise ValueError('duplicate ' + label + ' id')
        result[key] = row
    return result


def _stats(values: list[float]) -> dict:
    return {'count': len(values), 'mean': statistics.mean(values) if values else None,
            'sample_stddev': statistics.stdev(values) if len(values) > 1 else None,
            'minimum': min(values) if values else None, 'maximum': max(values) if values else None}


def _measurements(root: Path, path: str | None) -> dict:
    keys = {'elapsed_seconds', 'total_tokens', 'tool_calls'}
    if path is None:
        return {'values': dict.fromkeys(sorted(keys)), 'record': None, 'basis': None}
    raw = c.read(c.local(root, path))
    data = c.decode(raw)
    c.exact(data, {'values', 'basis', 'evidence_path'}, 'measurements')
    c.exact(data['values'], keys, 'measurement values')
    c.text(data['basis'], 'measurement basis')
    evidence = c.read(c.local(root, data['evidence_path']))
    for key, value in data['values'].items():
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError('measurement must be a finite nonnegative number or null')
        if key != 'elapsed_seconds' and not isinstance(value, int):
            raise ValueError('token and tool counts must be integers, not estimated text lengths')
    runner_evidence = None
    try:
        evidence_object = c.decode(evidence)
    except (ValueError, UnicodeError):
        evidence_object = None
    if isinstance(evidence_object, dict) and evidence_object.get('artifact_type') == 'agent-evaluation-run':
        import agent_evaluation
        runner_evidence = agent_evaluation.verify_measurements(root, data['evidence_path'], data['values'])
    return {'values': data['values'], 'basis': data['basis'], 'runner_evidence': runner_evidence,
            'record': {'path': path, 'sha256': c.digest(raw), 'evidence_path': data['evidence_path'],
                       'evidence_sha256': c.digest(evidence)},
            'limit': (runner_evidence['limit'] if runner_evidence else 'Operator-reported measurements with source bytes; their interpretation is not independently verified.')}


def build(root: Path, study_path: str) -> tuple[dict, list[dict], dict[str, bytes]]:
    root = review.workspace(root)
    study_bytes = c.read(c.local(root, study_path))
    study = c.decode(study_bytes)
    c.exact(study, {'purpose', 'cases', 'conditions', 'trials'}, 'study')
    c.text(study['purpose'], 'study purpose')
    cases = _indexed(_rows(study['cases'], 'cases'), 'case')
    conditions = _indexed(_rows(study['conditions'], 'conditions'), 'condition')
    trials = _indexed(_rows(study['trials'], 'trials'), 'trial')
    inputs = {}
    for condition in conditions.values():
        c.exact(condition, {'id', 'description'}, 'condition')
        c.text(condition['description'], 'condition description')
    for case in cases.values():
        c.exact(case, {'id', 'origin', 'origin_note', 'inputs', 'criteria'}, 'case')
        if case['origin'] not in {'observed-use', 'constructed-case'}:
            raise ValueError('case origin must distinguish actual use from constructed tests')
        c.text(case['origin_note'], 'case origin note')
        criteria = _indexed(_rows(case['criteria'], 'case criteria'), 'criterion')
        for criterion in criteria.values():
            c.exact(criterion, {'id', 'dimension', 'kind', 'text'}, 'criterion')
            c.text(criterion['dimension'], 'dimension')
            c.text(criterion['text'], 'criterion text')
            if criterion['kind'] not in {'technical', 'behavioral', 'expressive'}:
                raise ValueError('criterion kind must distinguish technical, behavioral and expressive evidence')
        if not isinstance(case['inputs'], list) or not case['inputs'] or len(set(case['inputs'])) != len(case['inputs']):
            raise ValueError('case inputs must list distinct actual project files')
        inputs[case['id']] = [{'path': path, 'sha256': c.digest(c.read(c.local(root, path)))} for path in case['inputs']]
    grouped: dict[tuple, Counter] = defaultdict(Counter)
    values: dict[tuple, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    results, cards, files, used = [], [], {}, set()
    for trial in trials.values():
        c.exact(trial, {'id', 'case', 'condition', 'run', 'candidate', 'measurements'}, 'trial')
        if trial['case'] not in cases or trial['condition'] not in conditions:
            raise ValueError('trial names an undeclared case or condition')
        case = cases[trial['case']]
        result = {'id': trial['id'], 'case': case['id'], 'condition': trial['condition'],
                  'origin': case['origin'], 'run': trial['run'], 'candidate': trial['candidate'],
                  'state': 'not-run', 'checks': [], 'source_binding': inputs[case['id']]}
        latest, task_criteria = None, {}
        if trial['run'] is None:
            if trial['candidate'] is not None or trial['measurements'] is not None:
                raise ValueError('a not-run trial cannot claim a candidate or execution measurements')
        else:
            if trial['run'] in used:
                raise ValueError('candidates from the same run cannot count as independent repeated trials')
            used.add(trial['run'])
            report, output_files = review.build(root, trial['run'])
            result['sources'] = report['sources']
            result['candidate_count'] = len(report['candidates'])
            result['candidate_policy'] = 'One explicitly named candidate per independent run; all candidates remain available in the production review.'
            for source in report['sources']:
                f = source['file']
                files[f['download']] = output_files[f['download']]
            _, prepared, _, _ = workflow.load_run(root, trial['run'])
            deps = {(d['space'], d['path']): d['sha256'] for d in prepared['dependencies']}
            for source in inputs[case['id']]:
                if deps.get(('project', source['path'])) != source['sha256']:
                    raise ValueError('trial does not bind the declared case input bytes: ' + source['path'])
            task_criteria = {x['id']: x for x in report['criteria']}
            result.update(state='no-candidate', input_sha256=report['input_sha256'],
                          receipt_head=report['receipt_head'], current=report['current'],
                          changed_dependencies=report['changed_dependencies'])
            if trial['candidate'] is None:
                if report['candidates']:
                    raise ValueError('specify the actual candidate; the evaluator never chooses the best output')
            else:
                candidates = [x for x in report['candidates'] if x['id'] == trial['candidate']]
                if len(candidates) != 1:
                    raise ValueError('trial candidate not found in its run')
                candidate = candidates[0]
                latest = candidate['reviews'][-1]['review'] if candidate['reviews'] else None
                result['state'] = 'reviewed' if latest is not None else 'not-reviewed'
                result['review_receipt'] = candidate['reviews'][-1]['receipt'] if latest else None
                result['review'] = latest
                result['outputs'] = candidate['files']
                files.update({f['download']: output_files[f['download']] for f in candidate['files']})
                cards.append({'trial': trial['id'], 'case': case['id'], 'condition': trial['condition'],
                              'files': candidate['files'], 'criteria': case['criteria']})
            result['consumer'] = report['consumer']
        measured = _measurements(root, trial['measurements'])
        result['measurements'] = measured
        if measured['record'] is not None:
            for path, digest_key in [('path', 'sha256'), ('evidence_path', 'evidence_sha256')]:
                record = measured['record']
                raw = c.read(c.local(root, record[path]))
                if c.digest(raw) != record[digest_key]:
                    raise ValueError('measurement evidence changed during evaluation')
                download = 'measurement-sources/' + record[digest_key] + '.txt'
                files[download] = raw
                record[path + '_download'] = download
        metric_key = (trial['condition'], case['origin'])
        for name, value in measured['values'].items():
            if value is not None:
                values[metric_key][name].append(value)
        checked = {x['criterion']: x for x in latest['checks']} if latest else {}
        for criterion in case['criteria']:
            # A matching ID with different wording is not the same evaluation criterion.
            if trial['run'] is not None and (criterion['id'] not in task_criteria
                    or task_criteria[criterion['id']]['text'] != criterion['text']):
                raise ValueError('study criterion must match the actual task criterion text and ID')
            check = checked.get(criterion['id'])
            verdict = check['verdict'] if check else 'missing'
            if verdict not in {'pass', 'fail', 'not-assessed', 'not-applicable', 'missing'}:
                raise ValueError('unsupported recorded verdict')
            result['checks'].append({'criterion': criterion['id'], 'dimension': criterion['dimension'],
                                     'kind': criterion['kind'], 'verdict': verdict,
                                     'reason': check['reason'] if check else 'No recorded assessment.'})
            grouped[(trial['condition'], case['origin'], criterion['kind'], criterion['dimension'])][verdict] += 1
        results.append(result)
    summary = []
    for key, counts in sorted(grouped.items()):
        assessed = counts['pass'] + counts['fail']
        applicable = sum(counts.values()) - counts['not-applicable']
        summary.append({'condition': key[0], 'origin': key[1], 'kind': key[2], 'dimension': key[3],
                        'counts': {k: counts[k] for k in ['pass', 'fail', 'not-assessed', 'not-applicable', 'missing']},
                        'assessed_pass_fraction': counts['pass'] / assessed if assessed else None,
                        'assessment_coverage': assessed / applicable if applicable else None})
    metrics = [{'condition': cond, 'origin': origin,
                'reported_metrics': {name: _stats(values[(cond, origin)].get(name, []))
                                     for name in ['elapsed_seconds', 'total_tokens', 'tool_calls']}}
               for cond, origin in sorted({(x['condition'], x['origin']) for x in results})]
    output = {'purpose': study['purpose'], 'study_path': study_path, 'study_sha256': c.digest(study_bytes),
              'cases': list(cases.values()), 'conditions': list(conditions.values()),
              'trials': results, 'summary': summary, 'metrics': metrics,
              'trial_states': [{'condition': cond, 'origin': origin,
                  'counts': {state: sum(r['condition'] == cond and r['origin'] == origin and r['state'] == state for r in results)
                             for state in ['not-run', 'no-candidate', 'not-reviewed', 'reviewed']}}
                  for cond, origin in sorted({(r['condition'], r['origin']) for r in results})],
              'limits': ['Descriptive evidence only; no automatic quality, causality or generalization claim.',
                         'Constructed tests and actual-use cases are never pooled.',
                         'Missing, unassessed and inapplicable observations are distinct from failures.',
                         'Technical passes do not establish expressive success.',
                         'A single observed measurement has no sample standard deviation.',
                         'Recorded reviewer judgments are not audience evidence.']}
    return output, cards, files


def _page(title: str, body: str) -> bytes:
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            'img-src \'self\'; media-src \'self\'; style-src \'unsafe-inline\'; base-uri \'none\'">'
            '<title>' + html.escape(title) + '</title><style>body{font:16px/1.6 system-ui;max-width:1000px;'
            'margin:2rem auto;padding:1rem}pre{white-space:pre-wrap;overflow-wrap:anywhere}img,video{max-width:100%}'
            'section{border-top:1px solid;padding:1rem 0}code{overflow-wrap:anywhere}</style></head><body><h1>'
            + html.escape(title) + '</h1>' + body + '</body></html>\n').encode('utf-8')


def export(root: Path, study_path: str, out: str, *, blind: bool = False) -> dict:
    root = review.workspace(root)
    with c.lock(root):
        result, cards, files = build(root, study_path)
        key_path = None
        if blind:
            secrets.SystemRandom().shuffle(cards)
            exported, key, body = {}, [], []
            for index, card in enumerate(cards, 1):
                label = f'Sample {index}'
                key.append({'label': label, 'trial': card['trial'], 'condition': card['condition'], 'case': card['case']})
                body.append('<section><h2>' + label + '</h2><pre>' + html.escape(json.dumps(card['criteria'], ensure_ascii=False, indent=2)) + '</pre>')
                for number, item in enumerate(card['files'], 1):
                    raw = files[item['download']]
                    suffix, kind = review.attachment(raw)
                    path = f'files/sample-{index}-{number}{suffix}'
                    exported[path] = raw
                    safe = {**item, 'path': label, 'sha256': '', 'download': path}
                    body.append(review._file_view(safe))
                body.append('</section>')
            body.insert(0, '<p>Presentation labels conceal condition names. The media itself or its metadata may still reveal a condition. This is not a claim of complete experimental blinding.</p>')
            exported['index.html'] = _page('Artifact assessment', '\n'.join(body))
            key_path = c.local(root, 'evaluation-keys/' + secrets.token_hex(16) + '.json', exists=False)
            c.atomic(key_path, c.encoded({'study_sha256': result['study_sha256'], 'presentation': out, 'key': key}))
            target = review.publish(root, out, exported, prefix='evaluations')
        else:
            files['evidence.json'] = c.encoded(result)
            files['study.json'] = c.read(c.local(root, study_path))
            body = '<p>These counts summarize recorded evidence, not artistic quality.</p><pre>' + html.escape(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)) + '</pre>'
            files['index.html'] = _page('Evaluation evidence', body)
            target = review.publish(root, out, files, prefix='evaluations')
    return {'ok': True, 'output': str(target), 'trials': len(result['trials']),
            'blind': blind, 'operator_key': str(key_path) if key_path else None,
            'models_called': 0, 'mutates_canon': False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--study', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--blind', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(export(args.project, args.study, args.out, blind=args.blind), ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
