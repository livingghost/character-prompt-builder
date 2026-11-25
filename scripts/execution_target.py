"""Keep a saved model as the sole owner of its selected execution offering."""
from __future__ import annotations

import execution_contract as c


FIELDS = frozenset({'model', 'model_id', 'selected_service', 'service', 'transport_sha256'})


def _selection(value: dict) -> tuple[int, dict]:
    c.exact(value, FIELDS, 'execution target')
    model_id = c.text(value['model_id'], 'execution target model')
    selected_service = c.text(value['selected_service'], 'execution target service')
    c.sha(value['transport_sha256'])
    model = value['model']
    if not isinstance(model, dict) or model.get('id') != model_id:
        raise ValueError('published target model identity differs from its saved model')
    offerings = model.get('offerings')
    if not isinstance(offerings, list):
        raise ValueError('published target model must declare its offerings')
    services = set()
    selected = None
    for index, candidate in enumerate(offerings):
        if not isinstance(candidate, dict):
            raise ValueError('published target offerings must be objects')
        service = c.text(candidate.get('service'), 'published offering service')
        if service in services:
            raise ValueError('published target model repeats offering service ' + repr(service))
        services.add(service)
        if service == selected_service:
            selected = (index, candidate)
    if selected is None:
        raise ValueError('published target selects no offering of its saved model')
    return selected


def record(resolved) -> dict:
    """Retain the exact model and service, identifying its offering once."""
    from production_diagnostics import same_json
    value = {'model': resolved.model, 'model_id': resolved.model_id,
             'selected_service': resolved.offering['service'], 'service': resolved.service,
             'transport_sha256': resolved.transport_sha256}
    if not same_json(offering(value), resolved.offering):
        raise ValueError('selected offering differs from its acquired model')
    return value


def offering(value: dict) -> dict:
    """Return the selected value from an acquired model without copying it."""
    return _selection(value)[1]


def offering_pointer(value: dict) -> str:
    """Locate that same value in the saved execution-target document."""
    return '/model/offerings/' + str(_selection(value)[0])
