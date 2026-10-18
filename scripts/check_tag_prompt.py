#!/usr/bin/env python3
"""Inspect final prompt clauses with their explicitly selected weighting syntax.

The model's tag family owns vocabulary and meaning. The request's promptWeighting
control owns parentheses, suffixes and conditioning expressions. Independent
Compel clauses are inspected separately and never flattened into one tag list.
The author reviews dictionary notes and clause interactions; the service computes
embeddings. This command preserves the supplied text.
"""
from __future__ import annotations
import operation_context as _operation_context

import argparse
import json
import re
from pathlib import Path
from typing import Any
import prompt_weighting as weighting
from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime

LONG_NEGATIVE = 30

def load_vocabulary(path: Path) -> dict[str, Any]:
    """Term to category, the categories that describe one figure at a time, and what each term opposes."""

    data = json.loads(path.read_text(encoding="utf-8"))
    category_of: dict[str, str] = {}
    opposes: dict[str, list[str]] = {}
    single_valued: set[str] = set()
    counts: set[str] = set()
    meanings: dict[str, dict] = {}
    for category in data.get("categories") or []:
        if category.get("single_valued"):
            single_valued.add(category["id"])
        counts.update(normalize(term) for term in (category.get("multiple_figures_terms") or []))
        for entry in category.get("entries") or []:
            for name in [entry["term"], *(entry.get("aliases") or [])]:
                category_of.setdefault(normalize(name), category["id"])
                meanings.setdefault(normalize(name), {'term': entry['term'], 'category': category['id'],
                    'description': entry.get('description'), 'usage_notes': entry.get('usage_notes', [])})
            if entry.get("opposes"):
                opposes[normalize(entry["term"])] = [normalize(row) for row in entry["opposes"]]
    return {"category_of": category_of, "opposes": opposes, "single_valued": single_valued,
            "multiple_figures": counts, "name": data.get("name"), "meanings": meanings}


def normalize(term: str) -> str:
    return re.sub(r"\s+", " ", str(term).replace("_", " ")).strip().casefold()


def _clause_checks(clause: dict, vocabulary: dict, dialect: dict | None, *, channel: str) -> list[dict]:
    findings = []
    # Zero-weight fragments remain visible in the syntax report, but are not
    # asserted to conflict with the terms actively requested in this clause.
    tags = [tag for tag in clause['tags'] if any(value != 0 for value in tag['weights'])]
    if clause['weight'] == 0:
        return []
    direct = clause['weight'] > 0 and all(value >= 0 for tag in tags for value in tag['weights'])
    def report(severity, check_name, message, terms=None):
        if not direct and check_name in {'one at a time', 'opposed pair', 'subject count', 'rating term', 'period term'}:
            severity = 'note'
            message += '; signed conditioning needs author interpretation'
        findings.append({'severity': severity, 'check': check_name, 'message': message,
                         'terms': terms or [], 'channel': channel, 'clause': clause['index'],
                         'range': clause['range']})
    category_of = vocabulary['category_of']
    seen = {}
    for tag in tags:
        name = normalize(tag['text']); seen[name] = seen.get(name, 0) + 1
    for name, count in seen.items():
        if count > 1:
            report('problem', 'repeated tag', f'{name!r} appears {count} times in this conditioning clause', [name])
    present = set(seen)
    for tag in tags:
        text = tag['text']
        if text != text.lower() and normalize(text) in category_of:
            report('note', 'capitals', f'{text!r} is carried by the vocabulary in lower case', [text])
    unknown = sorted(present - set(category_of))
    if unknown:
        report('note', 'not in the vocabulary', f'{len(unknown)} terms are not carried by the vocabulary; inspect their intended meaning', unknown)
    if channel == 'negative':
        if len(tags) > LONG_NEGATIVE:
            report('note', 'negative length', f'the negative clause carries {len(tags)} terms; review its scope')
        return findings
    by_category = {}
    for tag in tags:
        key = normalize(tag['text']); category = category_of.get(key)
        if category in vocabulary['single_valued']:
            by_category.setdefault(category, []).append(key)
    crowded = sorted(present & vocabulary['multiple_figures'])
    if not crowded:
        for category, terms in by_category.items():
            unique = sorted(set(terms))
            if len(unique) > 1:
                report('problem', 'one at a time', f'{category} describes one at a time and carries {len(unique)} terms in this clause', unique)
    reported = set()
    for term in sorted(present):
        for other in vocabulary['opposes'].get(term, []):
            pair = frozenset({term, other})
            if other in present and pair not in reported:
                reported.add(pair)
                report('problem', 'opposed pair', f'{term!r} and {other!r} pull against each other in this clause', sorted(pair))
    if len(crowded) > 1:
        report('problem', 'subject count', f'{len(crowded)} terms each put multiple figures in this clause', crowded)
    if crowded and 'solo' in present and frozenset({'solo', crowded[0]}) not in reported:
        report('problem', 'subject count', f'solo sits beside {crowded[0]!r}', ['solo', crowded[0]])
    chunks = sorted({tag['chunk'] for tag in tags})
    if len(chunks) > 1:
        counting = vocabulary['multiple_figures'] | {'solo'}
        gated = {tag['chunk'] for tag in tags if normalize(tag['text']) in counting
                 or category_of.get(normalize(tag['text'])) == 'subject-count-and-groups'}
        if gated:
            for index in set(chunks) - gated:
                report('note', 'count gating', f'chunk {index + 1} carries no count tag; inspect the intended subject scope')
    if dialect is not None:
        for field, label in [('rating_terms', 'rating'), ('period_terms', 'period')]:
            values = sorted(present & {normalize(term) for term in dialect.get(field) or []})
            if len(values) > 1:
                report('problem', f'{label} term', f"{len(values)} {label} terms from {dialect['id']} in the same clause", values)
        inert = sorted(present & {normalize(term) for term in dialect.get('inert_terms') or []})
        if inert:
            report('problem', 'inert term', f"{dialect['id']} declares these terms inert", inert)
        family_terms = {}
        for field, label in [('rating_terms', 'rating'), ('period_terms', 'period'), ('quality_terms', 'quality')]:
            for term in dialect.get(field) or []: family_terms.setdefault(normalize(term), label)
        for tag in tags:
            words = tag['text'].casefold().split()
            for term, label in family_terms.items():
                inner = term.split()
                if len(inner) < len(words) and any(words[i:i + len(inner)] == inner for i in range(len(words) - len(inner) + 1)):
                    report('note', 'family term inside a tag',
                        f"{tag['text']!r} also contains {term!r}, a {label} term; inspect the family's spelling guidance", [tag['text'], term])
        bounds = dialect.get('weight_range')
        if bounds:
            for tag in tags:
                if any(value > 1 and not bounds[0] <= value <= bounds[1] for value in tag['weights']):
                    report('note', 'weight range', f"{tag['text']!r} has a weight outside the family's stated working range {bounds}", [tag['text']])
    return findings


def inspect(prompt: str, negative: str, vocabulary: dict | None, record: dict | None,
            dialect: dict | None = None, *, syntax: str = 'literal') -> dict:
    report = weighting.inspect_pair(prompt, negative, syntax)
    findings = report['findings']
    for channel, parsed in report['channels'].items():
        if parsed is None: continue
        if parsed['operator'] in {'blend', 'and'}:
            findings.append({'severity': 'note', 'check': 'conditioning clauses', 'channel': channel,
                'message': f"{parsed['operator']} has {len(parsed['clauses'])} separately inspected clauses; the author assesses their combined intent.", 'terms': []})
        if any(clause['weight'] < 0 or any(value < 0 for tag in clause['tags'] for value in tag['weights']) for clause in parsed['clauses']):
            findings.append({'severity': 'note', 'check': 'signed conditioning', 'channel': channel, 'message': 'Signed weights are retained; lexical overlap is not a proof of the combined embedding effect.', 'terms': []})
        if syntax == 'compel' and re.search(r'(?<![\\\w])BREAK(?!\w)', prompt if channel == 'positive' else negative):
            findings.append({'severity': 'note', 'check': 'literal BREAK', 'channel': channel,
                'message': 'BREAK is not a Compel conjunction; use an explicitly authored .and() when separate conditioning is intended.', 'terms': ['BREAK']})
        if vocabulary is not None:
            for clause in parsed['clauses']:
                findings.extend(_clause_checks(clause, vocabulary, dialect, channel=channel))
    positive = report['channels']['positive']; excluded = report['channels']['negative']
    if vocabulary is not None and positive is not None and excluded is not None:
        for clause in positive['clauses']:
            if clause['weight'] == 0: continue
            names = {normalize(tag['text']) for tag in clause['tags'] if any(tag['weights'])}
            for neg in excluded['clauses']:
                if neg['weight'] == 0: continue
                both = sorted(names & {normalize(tag['text']) for tag in neg['tags'] if any(tag['weights'])})
                for term in both:
                    signed = clause['weight'] < 0 or neg['weight'] < 0 or any(value < 0 for selected in (clause, neg) for tag in selected['tags'] for value in tag['weights'])
                    findings.append({'severity': 'note' if signed else 'problem', 'check': 'in both',
                        'message': f'{term!r} occurs in positive clause {clause["index"] + 1} and negative clause {neg["index"] + 1}',
                        'terms': [term], 'channel': 'positive', 'clause': clause['index'], 'negative_clause': neg['index']})
    if record is not None:
        for text, limit, label in [(prompt,record.get('max_positive_prompt_chars'),'prompt'), (negative,record.get('max_negative_prompt_chars'),'negative')]:
            if type(limit) is int and len(text) > limit:
                findings.append({'severity':'problem','check':'length','message':f'{label} is {len(text)} characters; limit is {limit}','terms':[]})
        if negative and record.get('supports_negative_prompt') is False:
            findings.append({'severity':'problem','check':'negative transport','message':'the model declares no negative channel','terms':[]})
    meanings = []
    if vocabulary is not None:
        for channel, parsed in report['channels'].items():
            if parsed is None: continue
            for clause in parsed['clauses']:
                for term in sorted({normalize(tag['text']) for tag in clause['tags']}):
                    meaning = vocabulary.get('meanings', {}).get(term)
                    if meaning is not None and (meaning['description'] or meaning['usage_notes']):
                        meanings.append({'channel':channel,'clause':clause['index'],'authored_term':term,**meaning})
    report['meanings'] = meanings
    return report


def check(prompt: str, negative: str, vocabulary: dict, record: dict | None,
          dialect: dict | None = None, *, syntax: str = 'literal') -> list[dict]:
    return inspect(prompt, negative, vocabulary, record, dialect, syntax=syntax)['findings']


def check_request(rendered: dict, record: dict) -> dict:
    """Inspect both final wire channels using the actual sealed weighting control."""
    import execution_contract as c
    import request_contract as rc
    from catalog_retrieval.runtime import load_pack_catalog
    from prompt_dialect import find_dialect
    from production_diagnostics import ProductionError
    rc.validate_seal(rendered)
    syntax = weighting.wire_selection(rendered)
    dialect_id = record.get('prompt_dialect')
    vocabulary = dialect = None
    dictionary_ref = dialect_ref = None
    if dialect_id:
        catalog = load_pack_catalog()
        vocabulary_resource = catalog.resources.get('prompt-vocabulary')
        dialect_resource = catalog.resources.get('prompt-dialects')
        if vocabulary_resource is None or dialect_resource is None:
            raise ProductionError('PROMPT_VOCABULARY_REQUIRED', 'A tag target requires prompt-vocabulary and prompt-dialects resources.',
                phase='tag-prompt-check', required_action='Enable the resources for this model and prepare again.')
        vocabulary_path, dialect_path = Path(vocabulary_resource.path), Path(dialect_resource.path)
        vocabulary, dialect = load_vocabulary(vocabulary_path), find_dialect(dialect_id, dialect_path)
        dictionary_ref = {'resource':'prompt-vocabulary','sha256':c.sha256_file(vocabulary_path)}
        dialect_ref = {'id':dialect_id,'sha256':c.sha256_file(dialect_path)}
    layout = rendered['layout']
    prompt = rc.get(rendered['request'],layout['primary_text']) if layout['primary_text'] is not None else ''
    negative = rc.get(rendered['request'],layout['negative_text']) if layout['negative_text'] is not None else ''
    report = inspect(prompt, negative, vocabulary, record, dialect, syntax=syntax)
    return {'state':'checked' if dialect_id else 'syntax-checked','request_sha256':rendered['request_sha256'],
            'dictionary':dictionary_ref,'dialect':dialect_ref,**report}


def require_request(rendered: dict, record: dict) -> dict:
    from production_diagnostics import ProductionError
    report = check_request(rendered, record)
    if any(item['severity'] == 'problem' for item in report['findings']):
        raise ProductionError('TAG_PROMPT_PROBLEM', 'The final rendition contains syntax or mechanical tag problems.',
            phase='tag-prompt-check', prompt_check=report,
            required_action='Correct the authored text or selected weighting grammar; inspect model recommendations and prepare again.')
    return report

def main(argv: list[str] | None = None) -> int:
    parser = _operation_context.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--weighting", choices=weighting.SYNTAXES, default="literal", help="The actual request grammar, separate from the model tag family")
    parser.add_argument("--dictionary", required=True, type=Path, help="A prompt-vocabulary dictionary.json")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--negative", default="")
    parser.add_argument("--model", help="A model record, to check the rendition against its declared limits and its family")
    parser.add_argument("--dialect", help="A model family by its id, for a family with no model record")
    parser.add_argument("--dialects", help="A prompt-dialects JSON file, instead of the active pack's")
    add_pack_runtime_arguments(parser)
    args = parser.parse_args(argv)
    if not args.dictionary.is_file():
        raise SystemExit(f"{args.dictionary} is not a file")
    from catalog_cli import configure_pack_runtime
    runtime = resolve_pack_runtime(parser, args)
    configure_pack_runtime(runtime.settings)
    try:
        record = None
        dialect_id = args.dialect
        if args.model:
            from prepare_generation_references import resolve_model_record

            model_id, record = resolve_model_record(args.model)
            named = record.get("prompt_dialect")
            if args.dialect and named and named != args.dialect:
                raise SystemExit(f"model record {model_id!r} names the {named!r} family, not {args.dialect!r}")
            dialect_id = dialect_id or named
        dialect = None
        if dialect_id:
            from pack_manager import PackError
            from prompt_dialect import find_dialect, resolve_resource

            try:
                path = resolve_resource("prompt-dialects", args.dialects, settings=runtime.settings,
                                        required=bool(args.dialect))
                dialect = find_dialect(dialect_id, path) if path is not None else None
            except PackError as exc:
                raise SystemExit(str(exc)) from None
        report = inspect(args.prompt, args.negative, load_vocabulary(args.dictionary), record, dialect, syntax=args.weighting)
        findings = report["findings"]
        problems = [row for row in findings if row["severity"] == "problem"]
        print(json.dumps({"ok": not problems, "problems": len(problems), "notes": len(findings) - len(problems),
                          "dialect": dialect["id"] if dialect else None, **report},
                         ensure_ascii=False, indent=2))
        return 1 if problems else 0
    finally:
        configure_pack_runtime(None)


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
