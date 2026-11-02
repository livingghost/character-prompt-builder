"""Explicit fictional input contracts for tests and executable examples only.

Runtime code must resolve the selected model's authored contract. This module
does not supply a default for missing model metadata or claim provider evidence.
"""
from __future__ import annotations


def prompt_input(mode: str, *, vocabularies: tuple[str, ...] = (),
                 forms: tuple[str, ...] | None = None) -> dict:
    """Declare a fixture's chosen input form; callers must choose the mode."""
    if mode not in {'tag-based', 'descriptive', 'unresolved', 'none'}:
        raise ValueError('Choose an explicit synthetic input mode.')
    if mode == 'tag-based':
        if not vocabularies:
            raise ValueError('A synthetic tag target needs explicit vocabularies.')
        selected_forms = forms if forms is not None else ('tags',)
    elif mode == 'descriptive':
        selected_forms = forms if forms is not None else ('natural-language',)
    else:
        selected_forms = forms if forms is not None else ()
    return {
        'mode': mode,
        'forms': list(selected_forms),
        'vocabularies': list(vocabularies),
        'basis': [{
            'kind': 'synthetic-fixture',
            'source': 'scripts/model_prompt_input_fixtures.py',
            'scope': 'operation' if mode == 'none' else 'model',
            'observed_at': '2000-01-01',
            'statement': 'Explicitly authored fictional input contract for a local test; no provider capability is claimed.',
        }],
    }
