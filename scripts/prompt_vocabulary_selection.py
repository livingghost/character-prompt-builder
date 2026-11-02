"""Search and select wording for one model-bound tag rendition.

The dictionary is a curated vocabulary, not an exhaustive training-corpus list.
Search supplies existing words and alternatives; the author chooses their sense
and may retain an authored expression when existing words do not carry it.
Every verification performs the searches again against the current resources.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import prompt_weighting
from model_prompt_input import resolve_prompt_input
from search_prompt_vocabulary import VocabularyIndex, _term_index, load_vocabulary, normalize_identity


ARTIFACT_TYPE = 'prompt-vocabulary-selection'
TERM_FIELDS = ('quality_terms', 'rating_terms', 'period_terms', 'dataset_terms', 'meta_terms')


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False).encode('utf-8')).hexdigest()


def _text_sha(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def word_key(value: str) -> str:
    return normalize_identity(value.replace('_', ' '))


def _resources(model: dict, *, dictionary_path: Path | None = None,
               dialect_path: Path | None = None) -> tuple[list[dict], dict, dict]:
    from prompt_dialect import find_dialect
    if dictionary_path is None or dialect_path is None:
        from catalog_retrieval.runtime import load_pack_catalog
        catalog = load_pack_catalog()
        dictionary = catalog.resources.get('prompt-vocabulary')
        dialects = catalog.resources.get('prompt-dialects')
        if dictionary is None or dialects is None:
            raise ValueError('tag-based input requires the active prompt-vocabulary and prompt-dialects resources')
        dictionary_path = Path(dictionary.path)
        dialect_path = Path(dialects.path)
    dictionary = load_vocabulary(dictionary_path)
    dialect = find_dialect(model['prompt_dialect'], dialect_path)
    # Model controls are sourced from the selected family, never another family.
    # Their descriptions remain guidance; dictionary membership proves no effect.
    categories = []
    for field in TERM_FIELDS:
        terms = dialect.get(field, [])
        if terms:
            categories.append({'id': field.replace('_', '-'), 'name': field,
                'description': 'Declared terms of the selected ' + dialect['id'] + ' family. Read its version and usage notes.',
                'entries': [{'term': term} for term in dict.fromkeys(terms)]})
    vocabularies = [dictionary]
    if categories:
        vocabularies.append({'name': 'Selected family ' + dialect['id'], 'categories': categories})
    identity = {'dictionary_sha256': hashlib.sha256(dictionary_path.read_bytes()).hexdigest(),
                'dialect_sha256': _sha(dialect)}
    return vocabularies, dialect, identity


def _terms(prompt: str, negative: str, syntax: str) -> list[dict]:
    parsed = prompt_weighting.inspect_pair(prompt, negative, syntax)
    problems = [row['message'] for row in parsed['findings'] if row['severity'] == 'problem']
    if problems:
        raise ValueError('cannot search malformed prompt syntax: ' + '; '.join(problems))
    rows = []
    for channel, value in parsed['channels'].items():
        if value is None:
            continue
        for clause in value['clauses']:
            seen = set()
            for tag in clause['tags']:
                term = word_key(tag['text'])
                if not term or term in seen:
                    continue
                seen.add(term)
                rows.append({'id': channel + ':' + str(clause['index']) + ':' + term,
                             'channel': channel, 'clause': clause['index'], 'term': term})
    if not rows:
        raise ValueError('tag-based input needs wording to search')
    return rows


def search_selection(*, prompt: str, negative: str, model_record: dict,
                     syntax: str = 'literal', previous: dict | None = None,
                     dictionary_path: Path | None = None,
                     dialect_path: Path | None = None) -> dict:
    """Run real dictionary searches for every final clause term and supplied alternative query.

Exact existing words and aliases retain their complete definitions. An authored
extension stays open until the author records why available wording does not
preserve the intended meaning, scope or degree. No semantic choice is inferred
from lexical ranking.
    """
    contract = resolve_prompt_input(model_record)
    if contract['mode'] != 'tag-based':
        raise ValueError('vocabulary selection requires an explicitly tag-based model')
    model_id = model_record.get('id')
    if not isinstance(model_id, str) or not model_id.strip():
        raise ValueError('vocabulary selection requires the exact model or evidenced family identity')
    vocabularies, dialect, resources = _resources(model_record, dictionary_path=dictionary_path,
                                                 dialect_path=dialect_path)
    context = {'model': model_id, 'prompt_input_sha256': _sha(contract),
               'dialect': model_record['prompt_dialect'], **resources,
               'prompt_sha256': _text_sha(prompt), 'negative_sha256': _text_sha(negative),
               'syntax': syntax}
    if previous is not None:
        from state_protocol import validate_against_schema
        schema = json.loads((Path(__file__).resolve().parents[1] /
                             'schemas/prompt-vocabulary-selection.schema.json').read_text(encoding='utf-8'))
        errors = validate_against_schema(previous, schema)
        if errors:
            raise ValueError('invalid vocabulary selection: ' + '; '.join(errors))
    old = {row['id']: row for row in (previous or {}).get('entries', [])}
    index = VocabularyIndex(vocabularies)
    meanings = _term_index(vocabularies)
    entries = []
    for row in _terms(prompt, negative, syntax):
        prior = old.get(row['id'], {})
        queries = list(dict.fromkeys([row['term'], *prior.get('additional_queries', [])]))
        searches = []
        for query in queries:
            if not isinstance(query, str) or not query.strip():
                raise ValueError('vocabulary queries must be nonempty strings')
            candidates = []
            for match in index.search(query, limit=20):
                candidates.append({**match.as_json(), 'definitions': copy.deepcopy(meanings.get(word_key(match.term), []))})
            searches.append({'query': query, 'candidates': candidates})
        definitions = copy.deepcopy(meanings.get(row['term'], []))
        choice = None
        if definitions:
            choice = {'kind': 'dictionary', 'definitions': definitions}
        else:
            retained = prior.get('choice')
            if isinstance(retained, dict) and retained.get('kind') == 'authored':
                reason = retained.get('reason')
                if isinstance(reason, str) and reason.strip():
                    choice = {'kind': 'authored', 'reason': reason}
        entries.append({**row, 'additional_queries': queries[1:], 'searches': searches, 'choice': choice})
    unresolved = [row['id'] for row in entries if row['choice'] is None]
    return {'artifact_type': ARTIFACT_TYPE, 'context': context,
            'vocabularies': list(contract['vocabularies']),
            'dialect_guidance': copy.deepcopy(dialect),
            'entries': entries, 'unresolved': unresolved}


def resolve_authored(selection: dict, term: str, reason: str, *, queries: list[str] | None = None) -> dict:
    """Record the author's reason for a searched expression, preserving its candidate evidence."""
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('authored vocabulary needs a reason that compares the intended meaning with available wording')
    result = copy.deepcopy(selection)
    matched = False
    for row in result.get('entries', []):
        if row['id'] == term or row['term'] == word_key(term):
            if isinstance(row.get('choice'), dict) and row['choice'].get('kind') == 'dictionary':
                raise ValueError('this expression already has dictionary definitions; choose its appropriate sense in the rendition review')
            if not row.get('searches'):
                raise ValueError('search the vocabulary before retaining authored wording')
            row['choice'] = {'kind': 'authored', 'reason': reason}
            row['additional_queries'] = list(dict.fromkeys([*row.get('additional_queries', []), *(queries or [])]))
            matched = True
    if not matched:
        raise ValueError('no searched expression matches ' + repr(term))
    result['unresolved'] = [row['id'] for row in result['entries'] if row['choice'] is None]
    return result


def require_selection(selection: Any, *, prompt: str, negative: str,
                      model_record: dict, syntax: str = 'literal',
                      dictionary_path: Path | None = None,
                      dialect_path: Path | None = None) -> dict:
    """Re-run mandatory searches and require current, complete author selections.

The caller cannot opt out by leaving the retrieval list empty or saying the
wording is already understood. Lexical coverage does not certify picture meaning.
    """
    # Search even when the supplied record is absent. The failure can therefore
    # expose actual candidates instead of inviting an agent to fabricate proof.
    current = search_selection(prompt=prompt, negative=negative, model_record=model_record,
        syntax=syntax, previous=selection if isinstance(selection, dict) else None,
        dictionary_path=dictionary_path, dialect_path=dialect_path)
    if not isinstance(selection, dict) or selection.get('artifact_type') != ARTIFACT_TYPE:
        error = ValueError('tag-based input requires a searched vocabulary selection; run prompt_retrieval.py --search-vocabulary before settling')
        error.vocabulary_search = current
        raise error
    if selection.get('context') != current['context']:
        raise ValueError('vocabulary selection belongs to different text, model, syntax or dictionary; search and select for this rendition')
    if current['unresolved']:
        raise ValueError('choose an existing term or explain the authored wording after search: ' + ', '.join(current['unresolved']))
    if selection != current:
        raise ValueError('vocabulary search evidence is incomplete or changed; run the search again before settling')
    return current


def require_final_selection(selection: Any, *, prompt: str, negative: str,
                            model_record: dict, syntax: str = 'literal',
                            dictionary_path: Path | None = None,
                            dialect_path: Path | None = None) -> dict:
    """Search actual wire text after declared recommendation/transport processing.

    The authored rendition is checked separately against its exact receipt.
    Unchanged expressions retain their selected meanings; newly added family
    controls must also be found. An unknown injected phrase cannot inherit an
    unrelated authored choice.
    """
    current = search_selection(prompt=prompt, negative=negative, model_record=model_record,
        syntax=syntax, previous=selection if isinstance(selection, dict) else None,
        dictionary_path=dictionary_path, dialect_path=dialect_path)
    if not isinstance(selection, dict) or selection.get('artifact_type') != ARTIFACT_TYPE:
        error = ValueError('final tag text requires the authored vocabulary selection')
        error.vocabulary_search = current
        raise error
    text_fields = {'prompt_sha256', 'negative_sha256'}
    source_context = {key: value for key, value in selection['context'].items() if key not in text_fields}
    final_context = {key: value for key, value in current['context'].items() if key not in text_fields}
    if source_context != final_context:
        raise ValueError('final vocabulary selection does not match the selected model, syntax or dictionary')
    if current['unresolved']:
        error = ValueError('final text adds wording needing vocabulary selection: ' + ', '.join(current['unresolved']))
        error.vocabulary_search = current
        raise error
    return current


def require_for_model(record: dict, *, prompt: str, negative: str, model_record: dict,
                      syntax: str = 'literal') -> dict | None:
    """Apply the explicit input mode to a construction retrieval record."""
    contract = resolve_prompt_input(model_record)
    if contract['mode'] == 'unresolved':
        raise ValueError('resolve the selected model prompt input before finalizing its rendition')
    if contract['mode'] == 'none':
        raise ValueError('the selected model has no text prompt surface')
    if contract['mode'] == 'tag-based':
        return require_selection(record.get('vocabulary'), prompt=prompt, negative=negative,
                                 model_record=model_record, syntax=syntax)
    return None
