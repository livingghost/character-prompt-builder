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
import copy
import json
import re
from pathlib import Path
from typing import Any
import prompt_weighting as weighting
from pack_runtime_cli import add_pack_runtime_arguments, resolve_pack_runtime

def load_vocabulary(path: Path) -> dict[str, Any]:
    """Index complete dictionary entries and category guidance for author review."""

    data = json.loads(path.read_text(encoding="utf-8"))
    meanings: dict[str, list[dict]] = {}
    for category in data.get("categories") or []:
        for entry in category.get("entries") or []:
            meaning = {"category": category["id"], **copy.deepcopy(entry),
                       "category_definition": copy.deepcopy({key: value for key, value in category.items()
                                                             if key != "entries"})}
            for name in [entry["term"], *(entry.get("aliases") or [])]:
                matches = meanings.setdefault(normalize(name), [])
                if meaning not in matches:
                    matches.append(meaning)
    return {"meanings": meanings}


def normalize(term: str) -> str:
    return re.sub(r"\s+", " ", str(term).replace("_", " ")).strip().casefold()


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
    if record is not None:
        for text, limit, label in [(prompt,record.get('max_positive_prompt_chars'),'prompt'), (negative,record.get('max_negative_prompt_chars'),'negative')]:
            if type(limit) is int and len(text) > limit:
                findings.append({'severity':'problem','check':'length','message':f'{label} is {len(text)} characters; limit is {limit}','terms':[]})
        if negative and record.get('supports_negative_prompt') is False:
            findings.append({'severity':'problem','check':'negative transport','message':'the model declares no negative channel','terms':[]})
    meanings = []
    unmatched_terms = []
    if vocabulary is not None:
        for channel, parsed in report['channels'].items():
            if parsed is None: continue
            for clause in parsed['clauses']:
                for term in sorted({normalize(tag['text']) for tag in clause['tags']}):
                    matches = vocabulary.get('meanings', {}).get(term, [])
                    if matches:
                        meanings.extend({'channel':channel,'clause':clause['index'],'authored_term':term,
                                         **copy.deepcopy(meaning)} for meaning in matches)
                    else:
                        unmatched_terms.append({'channel':channel,'clause':clause['index'],'term':term})
    report['meanings'] = meanings
    report['unmatched_terms'] = unmatched_terms
    report['dialect_guidance'] = copy.deepcopy(dialect)
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
        raise ProductionError('TAG_PROMPT_PROBLEM', 'The final rendition violates its grammar or declared interface constraints.',
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
