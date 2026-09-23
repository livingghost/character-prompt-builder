#!/usr/bin/env python3
"""Create a small constructed authoring-material example in an empty workspace.

This demonstrates data flow only. It is not a complete artistic Persona, a real
agent run, a claim of user consent, or a mandatory scene/genre template.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import json

import material_support as m
import scene_persona as scene
import source_material as source


def create(root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError('choose an empty example workspace; no existing authored files are replaced')
    (root/'originals').mkdir()
    (root/'originals/subject.md').write_text(
        '# Controlling definition\nAttend to the recipient before choosing a response.\n'
        '# Expression\nA pause is an available response, not automatically distress.\n'
        '# Contextual condition\nReconsider the application if the recipient or available information changes.\n', encoding='utf-8')
    (root/'originals/scene.md').write_text(
        'A declared activity with one modeled subject and an unspecified recipient.\n'
        'No obligatory conflict, emotional change, human body or spoken dialogue is assumed.\n',encoding='utf-8')
    def committed(identifier,path,role,subjects):
        return {'source_id':identifier,'path':path,'role':role,'subject_ids':subjects,
                'sha256':m.digest((root/path).read_bytes()),
                'reading_basis':'Constructed example: the complete short source is shown; not evidence of real-agent reading.'}
    plan={'material_id':'prepared-activity','scene_id':'activity','scene_source_id':'scene',
          'purpose':'Demonstrate persistent definitions and scoped applications without a mandatory story pattern.',
          'conditions':['Only the stated activity and currently supplied recipient information are in scope.'],
          'subjects':[{'subject_id':'subject','model':'functional','source_ids':['model'],
                       'portrayal_basis':'Use this small declared response model; do not presume human psychology.'}],
          'sources':[committed('model','originals/subject.md','functional',['subject']),committed('scene','originals/scene.md','scene',[])],
          'excerpts':[{'excerpt_id':'attention','source_id':'model','start_line':1,'end_line':2,
                        'subject_ids':['subject'],'depends_on':[],'reason':'The controlling definition governs expression.'},
                       {'excerpt_id':'expression','source_id':'model','start_line':3,'end_line':4,
                        'subject_ids':['subject'],'depends_on':['attention'],'reason':'Do not replace a contextual response with a stock emotion.'}],
          'applications':[{'application_id':'response','subject_ids':['subject'],'definition_ids':['attention','expression'],
                           'kind':'option','text':'A pause may be chosen after attending to the recipient; no exact line or motive is prescribed.'}],
          'interactions':[],'constraints':['Do not infer a human voice or body from this functional model.'],
          'unknowns':['The recipient and final response are intentionally unspecified.'],
          'reopen_when':['The recipient, information, purpose or original model changes.'],
          'review':{'by':'constructed-example-author','decision':'ready','basis':'Software/data-flow demonstration only.',
                    'limitations':['This is not evidence of artistic suitability; read real full Personas when preparing actual work.']}}
    (root/'scene-plan.json').write_bytes(m.encoded(plan))
    scene_result=scene.build(root,'scene-plan.json','scene-material')
    primary='originals/subject.md'
    import_plan={'material_id':'original-material','purpose':'Retain original bytes independently of proposed interpretation.',
                 'documents':[{'source_id':'primary','path':primary,'role':'primary-source','encoding':'utf-8',
                               'sha256':m.digest((root/primary).read_bytes())}],
                 'segments':[{'segment_id':'opening','source_id':'primary','start_line':1,'end_line':4,
                              'label':'An authored analysis span, not an inferred chapter.','completion':'unknown'}],
                 'unresolved':['No claim is made about the completion of a larger work.']}
    (root/'import-plan.json').write_bytes(m.encoded(import_plan))
    imported=source.ingest(root,'import-plan.json','source-material')
    claims={'proposal_id':'extraction-candidates','index_sha256':imported['content_sha256'],
            'claims':[{'claim_id':'available-response','subject_ids':['subject'],'epistemic_status':'source-statement',
                      'text':'The provided document permits a pause without declaring distress.',
                      'proposed_use':'Review as an input to portrayal; do not adopt automatically.',
                      'conflicts_with':[], 'evidence':[{'source_id':'primary','start_line':3,'end_line':4}]}],
            'unresolved':['No final scene response has been selected.']}
    (root/'claims-plan.json').write_bytes(m.encoded(claims))
    proposed=source.propose(root,'source-material','claims-plan.json','extraction-proposal')
    return {'ok':True,'scene':scene_result,'originals':imported,'proposal':proposed,
            'limit':'Constructed data-flow example, not a real-agent or artistic evaluation.'}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True,type=Path)
    args=parser.parse_args()
    try:
        print(json.dumps(create(args.root),ensure_ascii=False,indent=2));return 0
    except (ValueError,OSError) as exc:
        print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False));return 1


if __name__=='__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
