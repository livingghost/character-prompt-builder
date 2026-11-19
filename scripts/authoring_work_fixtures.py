"""Acquired character inputs for protocol tests, never runtime authoring defaults."""
from __future__ import annotations

import execution_contract as c


def prompt_work(content: dict, *, request: str = 'Prepare the synthetic character depiction.',
                operation: str = 'compose', baseline: dict | None = None) -> dict:
    from authoring_work import acquire_source, begin_work
    definition = {'id': 'fixture-character', 'kind': 'synthetic character',
                  'definition': 'A fictional articulated robot used only to test input transport.'}
    return begin_work(operation=operation, request=request,
        sources={'definition': acquire_source(c.encoded(definition), format='json',
                                             origin={'fixture': 'synthetic-character'})},
        applications={'character-definition': {'source': 'definition', 'pointer': ''}},
        subjects={'fixture-character': ['character-definition']}, requirements=[],
        baseline=baseline, content=content)
