"""Use only studio, skill and active catalog roots for local input evidence."""
from pathlib import Path
from input_evidence import InputEvidence

ROOT = Path(__file__).resolve().parents[1]


def reader(root:Path|None,*,snapshots:dict|None=None,live:bool=True,source=None)->InputEvidence:
    roots={'@skill':ROOT}
    if live:
        if source is None:
            from catalog_retrieval.runtime import load_pack_catalog
            pack_roots=load_pack_catalog().pack_roots
        else:
            pack_roots=source.pack_roots
        roots.update(('@pack/'+pack_id,path) for pack_id,path in pack_roots.items())
    return InputEvidence(root,snapshots=snapshots,live=live,named_roots=roots,
                         read_source=source.read_named if source is not None else None)


def acquisition(root:Path|None,*,source=None):
    """Acquire evidence from explicit runtime values before semantic compilation."""
    from input_evidence import EvidenceAcquisition
    if source is None:
        from catalog_retrieval.runtime import load_pack_catalog,selected_pack_settings
        from runtime_snapshot import CompileRuntime
        source=CompileRuntime.from_catalog(load_pack_catalog(),selected_pack_settings())
    roots={'@skill':ROOT,**{'@pack/'+pack:path for pack,path in source.pack_roots.items()}}
    return EvidenceAcquisition(root,named_roots=roots,read_source=source.read_named)


def model_space(model_id:str,*,source=None)->str:
    if source is not None:
        return source.model_space(model_id)
    from catalog_retrieval.runtime import load_pack_catalog
    entries=[x for x in load_pack_catalog().entries if x.kind=='model' and x.record.get('id')==model_id]
    if len(entries)!=1:raise ValueError('selected model has no unique active provider')
    return '@pack/'+entries[0].source_pack
