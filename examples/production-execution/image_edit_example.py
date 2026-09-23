#!/usr/bin/env python3
"""Keep an actual synthetic reviewed pixel repair. Never manufactures user consent."""
from __future__ import annotations
import argparse
import io
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import execution_contract as c
import production_fixtures as fixture
import production_workflow as w
import image_edit
import work_ledger


def run(out: Path) -> dict:
    from PIL import Image
    if out.exists():raise ValueError('choose a new output directory')
    out.mkdir(parents=True)
    def write(name,value):
        path=out/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(value if isinstance(value,bytes) else value.encode() if isinstance(value,str) else c.encoded(value))
    opened=work_ledger.begin(out,'Synthetic reviewed pixel repair, not artwork evaluation.',['deliver'])
    pixels=io.BytesIO();Image.new('RGBA',(12,8),(20,40,60,255)).save(pixels,format='PNG')
    write('source.png',pixels.getvalue());write('candidate.png',pixels.getvalue());write('delivery.txt','A six-by-four synthetic crop of the pinned plate.')
    task={'task_id':opened['task_id'],'route':'development','features':['image-edit'],
          'sources':[{'id':'plate','path':'source.png','role':'world','disposition':'applied','locator':'whole','reason':'Synthetic input.'}],
          'delivery':{'path':'delivery.txt','transport':'authored-rendition','translation_notes':'No private dossier.'},
          'criteria':[{'id':'dimensions','strength':'hard','text':'A six-by-four actual image.'}],'world_views':[]}
    fixture.task(out,task,artifact='image');task['criteria'][0]['evidence']='image';write('task.json',task)
    rid=w.prepare(out,'task.json')['run'];fixture.handoff(out,rid,'Synthetic image editor','manual')
    initial=w.capture(out,rid,'candidate.png','A twelve-by-eight synthetic starting plate.')
    review=w.draft_review(out,rid,initial['sha256'])
    review.update(reviewer='SYNTHETIC PIXEL INSPECTION',conclusion='Wrong measured dimensions.',observations=[{
        'evidence':'candidate','locator':{'kind':'whole'},'observation':'Decoded image is 12 by 8.',
        'interpretation':'This fixture requires 6 by 4.','limitations':['No artwork or audience assessment.']}],
        repairs=[{'id':'crop','decisions':[],'observation_indices':[0],'operation':'Crop to six by four.',
                  'targets':['delivery'],'reason':'The measured input is larger than the declared deliverable.'}])
    review['checks'][0].update(verdict='fail',observation_indices=[0],reason='Measured 12 by 8, not 6 by 4.')
    write('initial-review.json',review);w.review(out,rid,'initial-review.json')
    plan={'input_sha256':w.load_run(out,rid)[1]['input_sha256'],'source':{'path':'candidate.png','sha256':c.digest(pixels.getvalue())},
          'operations':[{'operation':'crop','box':[1,2,7,6]}],'output':'edited.png','targets':['delivery'],
          'repair':{'candidate':initial['sha256'],'repair':'crop'},'reason':'Apply the reviewed synthetic crop.',
          'limitations':['No artistic evaluation or generated content.']}
    write('edit.json',plan);intent=image_edit.edit_intent(out,rid,'edit.json');write('edit-intent.json',intent)
    grant=fixture.grant(out,rid,intent);edited=image_edit.execute(out,rid,'edit.json',grant)
    with Image.open(out/'edited.png') as actual:
        if actual.size!=(6,4) or actual.getpixel((0,0))!=(20,40,60,255):raise ValueError('unexpected actual pixels')
    reviewed=w.draft_review(out,rid,edited['sha256']);reviewed.update(reviewer='SYNTHETIC PIXEL INSPECTION',conclusion='Measured fixture meets its dimensions.',observations=[{
        'evidence':'candidate','locator':{'kind':'whole'},'observation':'Decoded output is 6 by 4 with the original sample color.',
        'interpretation':'The specified pixel operation succeeded.','limitations':['No artwork or audience assessment.']}])
    reviewed['checks'][0].update(verdict='pass',observation_indices=[0],reason='Measured the actual PNG.')
    write('edited-review.json',reviewed);w.review(out,rid,'edited-review.json')
    choice=w.draft_selection(out,rid,edited['sha256']);choice['reason']='Select the observed synthetic output.';fixture.selection(out,rid,choice)
    write('selection.json',choice);w.select(out,rid,'selection.json');done=w.complete(out,rid)
    work_ledger.step_done(out,1);work_ledger.finish(out)
    result={'ok':True,'run':rid,'source_candidate':initial['sha256'],'edited_candidate':edited['sha256'],'completion':done['sha256'],
            'measurements':{'width':6,'height':4,'pixel':[20,40,60,255]},'limits':['Synthetic processing only; not consent or artwork quality.']}
    write('result.json',result);return result


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True,type=Path);args=parser.parse_args()
    try:print(json.dumps(run(args.out.absolute()),indent=2));return 0
    except (ValueError,OSError) as exc:print(json.dumps({'ok':False,'error':str(exc)}));return 1
if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
