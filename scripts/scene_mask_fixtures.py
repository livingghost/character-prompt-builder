"""Constructed mask inputs for tests/examples; never an authoring shortcut."""
from __future__ import annotations
import copy
from pathlib import Path
from PIL import Image, ImageDraw
import execution_contract as c
import scene_mask_planner as masks


def pixels(root: Path, size=(32, 32)) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    source = Image.new('RGB', size, (70, 105, 135))
    source.save(root/'source.png')
    def ref(path):
        return {'path':path,'sha256':c.digest((root/path).read_bytes())}
    regions=[]
    for name,box,role in [('front',(12,10,21,25),'garment'),('sleeve-a',(6,12,10,22),'garment'),
                          ('sleeve-b',(23,12,27,22),'garment'),('protected',(11,1,22,8),'protect')]:
        image=Image.new('L',size);ImageDraw.Draw(image).rectangle(box,fill=255)
        image.save(root/(name+'.png'))
        regions.append({'id':name,'role':role,'image':ref(name+'.png'),
                        'provenance':'Constructed rectangular test region; not real segmentation.'})
    plan={'format':masks.FORMAT,'source':ref('source.png'),'regions':regions,
          'selected':['front','sleeve-a','sleeve-b'],'required':['front','sleeve-a','sleeve-b'],
          'feather':0,'unresolved':[]}
    (root/'mask-plan.json').write_bytes(c.encoded(plan))
    Image.new('RGB',(16,16),(240,230,200)).save(root/'guidance.png')
    return plan


def reviewed(root:Path, plan:dict|None=None,*,out='masks/a',guidance:bool=True) -> dict:
    if plan is None:plan=pixels(root)
    (root/'mask-plan.json').write_bytes(c.encoded(plan))
    report=masks.build(root,'mask-plan.json',out)
    if not report['geometry_valid']:raise ValueError(report)
    bundle=c.load(root/out/'bundle.json')
    review={'format':'cpb-scene-mask-review','bundle_sha256':c.content_id(bundle),
            'reviewer':'SYNTHETIC TEST REVIEWER - NOT USER APPROVAL','verdict':'ready',
            'observations':[{'region':row['id'],'observation':'Constructed mask matches the rectangle in this fixture.'}
                            for row in plan['regions'] if row['id'] in plan['selected'] or row['role']=='protect'],
            'unresolved':[]}
    (root/'mask-review.json').write_bytes(c.encoded(review))
    return masks.bind(root,bundle_path=out+'/bundle.json',review_path='mask-review.json',
                      guidance_path='guidance.png' if guidance else None,out='mask-binding.json')


def production(root:Path,runtime_root:Path)->dict:
    import production_case_fixtures as f
    import pack_manager as packs
    from catalog_retrieval import runtime
    from prepare_generation_references import prepare_references
    from reading_fixtures import task_reading
    from request_validation_fixtures import fixture_validation
    from prompt_retrieval import settle_retrieval_record
    case=f.create(root,runtime_root)
    models=c.load(case['pack']/'records/models.json')
    model=models['records'][0]
    model['offerings'][0]['request_keys']['mask image']=['mask_image']
    f.write(case['pack']/'records/models.json',models);packs.write_lock(case['pack']);runtime.configure_pack_runtime(case['settings'])
    binding=reviewed(root)
    task=c.load(root/'task.json')
    task['features'].append(masks.FEATURE)
    task['sources'].append({'id':'mask-source','path':'source.png','role':'scene-source','locator':'whole',
                            'disposition':'applied','reason':'Exact constructed source for a synthetic mask execution.'})
    task['generation']['mask_binding']='mask-binding.json'
    spec=c.load(root/'spec.json');spec['render_intent']['execution_mode']='image-to-image';f.write(root/'spec.json',spec)
    references=prepare_references([{'role':'composition','source':{'kind':'supplied-file',
                       'reference_id':'synthetic-scene-source','resolved_path':str(root/'source.png')}}],
                       model=f.MODEL_ID,output_dir=root/'source-preparation')
    f.write(root/'references.json',references);task['generation']['references']='references.json'
    params=c.load(root/'parameters.json');params['strength']=.7;f.write(root/'parameters.json',params)
    retrieval=c.load(root/'retrieval.json');retrieval['pack_state']=runtime.load_pack_catalog().fingerprint
    f.write(root/'retrieval.json',settle_retrieval_record(retrieval,prompt=(root/'prompt.txt').read_text(encoding='utf-8'),plot=c.load(root/'plot.json')))
    f.write(root/'validation.json',fixture_validation(root,f.MODEL_ID,reference_mode='authored-rendition',service='synthetic'))
    task_reading(root,task);f.write(root/'task.json',task)
    return case
