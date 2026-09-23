"""Use only project, skill and active catalog roots for local input evidence."""
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
        for resource in catalog.resources.values():
            name='@pack/'+resource.source_pack
            if name in roots:continue
            for path in Path(resource.path).parents:
                manifest=path/'pack.json'
                if manifest.is_file() and c.load(manifest).get('pack_id')==resource.source_pack:
                    roots[name]=path.resolve();break
    return InputEvidence(root,snapshots=snapshots,live=live,named_roots=roots)


def model_space(model_id:str)->str:
    from catalog_retrieval.runtime import load_pack_catalog
    entries=[x for x in load_pack_catalog().entries if x.kind=='model' and x.record.get('id')==model_id]
    if len(entries)!=1:raise ValueError('selected model has no unique active provider')
    return '@pack/'+entries[0].source_pack
