"""Use only studio, skill and active catalog roots for local input evidence."""
from pathlib import Path
from input_evidence import InputEvidence
import execution_contract as c


def reader(root:Path|None,*,snapshots:dict|None=None,live:bool=True)->InputEvidence:
    roots={'@skill':Path(__file__).resolve().parents[1]}
    if live:
        from catalog_retrieval.runtime import load_pack_catalog
        catalog=load_pack_catalog()
        for entry in catalog.entries:
            name='@pack/'+entry.source_pack;path=Path(entry.source_root).resolve()
            if name in roots and roots[name]!=path:raise ValueError('active pack ID has multiple roots')
            roots[name]=path
        for pack_id,path in catalog.pack_roots.items():
            name='@pack/'+pack_id;path=Path(path).resolve()
            if name in roots and roots[name]!=path:raise ValueError('active pack ID has multiple roots')
            roots[name]=path
    return InputEvidence(root,snapshots=snapshots,live=live,named_roots=roots)


def model_space(model_id:str)->str:
    from catalog_retrieval.runtime import load_pack_catalog
    entries=[x for x in load_pack_catalog().entries if x.kind=='model' and x.record.get('id')==model_id]
    if len(entries)!=1:raise ValueError('selected model has no unique active provider')
    return '@pack/'+entries[0].source_pack
