"""Declare synthetic interfaces for tests and executable examples only.

The declarations exercise evidence binding. They are not observations of a live
provider and are never constructed by an operational entrypoint.
"""
from __future__ import annotations
import importlib
from pathlib import Path
import execution_contract as c
from input_evidence import InputEvidence
import request_contract as rc
import request_validation as rv


def fixture_validation(root: Path, model: str, *, reference_mode: str,
                       service: str | None = None) -> dict:
    """Read the selected execution records and label the interface evidence synthetic."""
    from prepare_generation_references import resolve_model_record
    from model_contract import select_offering
    import service_profile
    model_id, record = resolve_model_record(model)
    offering = select_offering(record, service)
    operation = ('imageUpscale' if record.get('operation_kind') == 'upscale' else 'imageInference')
    target = {'service': offering['service'] if offering is not None else 'synthetic-host',
              'model_identifier': offering['model_identifier'] if offering is not None else model_id,
              'operation': operation if offering is not None else 'generation'}
    if offering is None:
        service_record = {'id': target['service'], 'endpoint': {'base_url': 'https://example.invalid/synthetic-interface'},
                          'operations': {target['operation']: {}}}
        transport = importlib.import_module('request_renderer')
    else:
        from catalog_retrieval.runtime import load_pack_catalog
        resource = load_pack_catalog().resources.get('service-profiles')
        if resource is None:
            raise ValueError('synthetic offering fixture needs its active service-profiles resource')
        service_record = service_profile.load_service(offering['service'], Path(resource.path))
        import transport_contract
        transport = transport_contract.load(service_record['transport'])
    return interface_validation(root, target=target, record=record, offering=offering or {},
                                service_record=service_record, transport=transport, reference_mode=reference_mode)


def interface_validation(root: Path, *, target: dict, record: dict, offering: dict,
                         service_record: dict, transport, reference_mode: str) -> dict:
    """Declare an explicitly synthetic interface for an exact test execution context."""
    prefix = 'synthetic-validation/' + c.content_id({'target': target, 'reference_mode': reference_mode, 'record': record,
        'offering': offering, 'service': service_record, 'transport': c.digest(Path(transport.__file__).read_bytes())})[:16]
    root.mkdir(parents=True, exist_ok=True)
    def save(name: str, value: dict | str) -> dict:
        path = prefix + '/' + name
        raw = value.encode('utf-8') if isinstance(value, str) else c.encoded(value)
        destination = root / path
        try:
            c.atomic(destination, raw)
        except FileExistsError:
            if destination.read_bytes() != raw:
                raise ValueError('synthetic interface evidence changed: ' + path)
        return {'path': path, 'sha256': c.digest(raw)}
    basis = {**save('basis.txt', 'Synthetic interface declaration. No provider was contacted.\n'), 'locator': 'whole'}
    # This fixture accepts an object; concrete model constraints remain checked
    # by the normal model validator. It establishes no live provider capability.
    schema = {'type': 'object'}
    response = save('interface.json', {'synthetic': True, 'schema': schema})
    acquisition = save('acquisition.json', {'artifact_type': 'schema-acquisition', 'target': target,
        'source': {'kind': 'document', 'identifier': 'Synthetic interface fixture', 'locator': 'schema member'},
        'acquired_at': '2000-01-01T00:00:00Z', 'response': response,
        'status': {'document_status': 'schema-provided'}})
    contract = save('contract.json', {'artifact_type': 'model-schema-contract', 'target': target,
        'schema': schema, 'schema_sha256': c.content_id(schema), 'response_pointer': '/schema', 'local_overlay': None})
    if reference_mode not in {'authored-rendition', 'prompt-prefix'}:
        raise ValueError('the synthetic fixture needs an explicit supported reference mode')
    dialect = record.get('prompt_dialect') or 'synthetic-prose'
    reference = save('references.json', {'artifact_type': 'reference-render-contract', 'target': target,
        'dialects': [dialect], 'mode': reference_mode,
        'renderer': 'reference-delivery' if reference_mode == 'prompt-prefix' else None,
        'fields': [], 'basis': basis})
    policy = {'artifact_type': 'execution-policy', 'target': target, 'text_dialect': dialect,
        'production_context_transport': 'none', 'reference_instruction_transport': {'mode': reference_mode, 'contract': reference},
        'basis': basis}
    policy_ref = save('policy.json', policy)
    execution = rc.execution_hashes(service_record, offering, Path(transport.__file__), model=record, policy=policy)
    return rv.build_record({'mode': 'target-schema', 'contract': contract['path'], 'evidence': acquisition['path'],
        'execution_policy': policy_ref['path']}, InputEvidence(root), expected_target=target, execution=execution)
