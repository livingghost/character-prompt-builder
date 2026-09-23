"""Preserve schema acquisition bytes and explicit scope in a local evidence bundle."""
from __future__ import annotations
import copy
from pathlib import Path
import tempfile
import execution_contract as c
from input_evidence import InputEvidence
import request_validation as rv


def assemble(root: Path, *, target: dict, acquisition: str, pointer: str, prefix: str,
             kind: str, relationship: dict | None = None, overlay: str | None = None) -> tuple[dict, dict]:
    """Resolve supplied evidence without a network call or target-name inference."""
    import request_contract as rc
    rc.target(target)
    if kind not in {'schema', 'reference'}:
        raise ValueError('select schema or reference explicitly')
    c.local(root, prefix, exists=False)
    reader = InputEvidence(root)
    original = reader.select(acquisition)
    metadata = reader.json(original)
    acquired = rv.acquisition(metadata, reader, expected=target if kind == 'schema' else None, successful=True)
    schema = rv.pointer(c.decode(acquired['body']), pointer)
    rv._schema_shape(schema)
    files = {}
    def put(name: str, raw: bytes) -> dict:
        files[name] = raw
        return {'path': prefix + '/' + name, 'sha256': c.digest(raw)}
    response = put('response.json', acquired['body'])
    put('original-acquisition.json', reader.read(original))
    copied = copy.deepcopy(metadata); copied['response'] = response
    evidence = put('acquisition.json', c.encoded(copied))
    if kind == 'schema':
        overlay_ref = None
        if overlay is not None:
            selected = reader.select(overlay); value = reader.json(selected)
            c.exact(value, {'artifact_type','target','fields','basis'}, 'local envelope overlay')
            if value['artifact_type'] != 'request-envelope-overlay' or value['target'] != target:
                raise ValueError('overlay target differs from the selected model')
            raw = reader.basis(value['basis'])
            basis = put('overlay-basis.txt', raw)
            value = copy.deepcopy(value); value['basis'] = dict(basis, locator=value['basis']['locator'])
            overlay_ref = put('overlay.json', c.encoded(value))
        contract = {'artifact_type':'model-schema-contract','target':target,'schema':schema,
            'schema_sha256':c.content_id(schema),'response_pointer':pointer,'local_overlay':overlay_ref}
        contract_ref = put('contract.json', c.encoded(contract))
    else:
        if overlay is not None or relationship is None:
            raise ValueError('a reference requires its relationship basis and carries no target overlay')
        raw = reader.basis(relationship)
        basis = put('relationship.txt', raw)
        contract = {'artifact_type':'model-schema-reference','target':target,'source_target':metadata['target'],
            'acquisition':evidence,'schema':schema,'response_pointer':pointer,
            'relationship':dict(basis, locator=relationship['locator'])}
        contract_ref = put('reference.json', c.encoded(contract))
    manifest = {'artifact_type':'local-schema-evidence','kind':kind,'target':target,
        'source_target':metadata['target'],'contract':contract_ref,'evidence':evidence,
        'original_acquisition':original,'original_response':metadata['response'],
        'files':[{'path':prefix+'/'+name,'sha256':c.digest(raw)} for name,raw in sorted(files.items())]}
    put('manifest.json', c.encoded(manifest))
    # Exercise the ordinary validators against the exact bytes to be published.
    with tempfile.TemporaryDirectory(prefix='schema-evidence-check-') as temp:
        check_root = Path(temp)
        for name,raw in files.items():
            c.atomic(c.local(check_root,prefix+'/'+name,exists=False),raw)
        checked = InputEvidence(check_root)
        if kind == 'schema':
            rv.schema_contract(contract,copied,checked,target)
        else:
            rv.reference_schema(contract_ref,checked)
    for path in sorted(reader.read_paths):
        reader.read({'path':path,'sha256':reader.snapshots[path]['sha256']})
    return files, manifest


def publish(root: Path, relative: str, files: dict[str, bytes]) -> dict:
    """Publish one complete new directory while retaining all existing evidence."""
    target = c.local(root,relative,exists=False)
    if target.exists():
        raise FileExistsError('select a new evidence destination')
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.schema-evidence-',dir=target.parent) as temp:
        staging=Path(temp)
        for name,raw in files.items():c.atomic(c.local(staging,name,exists=False),raw)
        with c.lock(root):
            if target.exists():raise FileExistsError('evidence destination already exists')
            c.publish_directory(staging,target);c.fsync_dir(target.parent)
    return {'path':relative+'/manifest.json','sha256':c.digest(files['manifest.json'])}
