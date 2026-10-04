"""Explicitly local synthetic transport for examples and deterministic tests.

No network code is called and no credential is read. The coloured PNG is
protocol test data, not an AI image or evidence about a provider's image
quality. Synthetic approval and a synthetic target never authorize another
transport.

The synthetic service takes one JSON object. Its own envelope names the
operation in `operation` and the run's identifier in `request_id`; the model
sits on the offering's `model` key, the output count in `count` and the seed
in `seed`. The prompt, the negative and the media go on the keys the offering
gives them. An upscale takes its image in `image` and its factor in `scale`,
and the offering must declare those keys. The service remembers each request
it answered for the life of the process, and lookup returns that same answer by
`request_id`.
"""
from __future__ import annotations
import base64
import copy
import hashlib
import struct
import uuid
import zlib
import execution_contract as c

OPERATIONS={'generation':'generate','upscale':'upscale'}
RESULT_HOSTS=frozenset()
CREDENTIAL_FREE=True
ENDPOINT='http://localhost/cpb-synthetic-no-network'
ROLES={'seed-image':'seed image','references':'reference images','input-image':'input image'}
_ANSWERED:dict[str,dict]={}


def endpoint(service:dict)->str:
    address=(service.get('endpoint') or {}).get('base_url')
    if address!=ENDPOINT:
        raise ValueError('The synthetic transport accepts only its declared non-network fixture endpoint.')
    return address


def _key(offering:dict,role:str)->list:
    from request_contract import path_parts
    keys=(offering.get('request_keys') or {}).get(role)
    if not keys:
        raise ValueError(f'the synthetic offering declares no {role!r} request key')
    return path_parts(keys[0])


def _writer(offering:dict,model_identifier:str):
    from request_contract import RequestWriter
    writer=RequestWriter()
    source=[{'kind':'offering','service':offering['service'],'model_identifier':model_identifier}]
    def write(path,value,kind,transform,bindings=None):
        writer.write(path,value,source_kind=kind,source_refs=source,transform_id=transform,binding_ids=bindings)
    return writer,write


def _envelope(write,operation:str,model_field:list,model_identifier:str)->None:
    write(['operation'],operation,'transport-envelope','operation')
    write(['request_id'],str(uuid.uuid4()),'transport-envelope','task-identifier')
    write(model_field,model_identifier,'model-setting','model-identifier')


def compile_request(verified:dict,offering:dict,service:dict,media_ids:dict|None=None,seed:int|None=None,count:int=1)->dict:
    from request_contract import MANAGEMENT_VALUE,path_parts
    operation=OPERATIONS['generation']
    if operation not in service.get('operations',{}):
        raise ValueError('service does not declare '+operation)
    if type(count) is not int or count<1:
        raise ValueError('output count must be a positive integer')
    if seed is not None and type(seed) is not int:
        raise ValueError('seed must be an integer or omitted')
    forwarding=verified['host_forwarding'];media_ids=media_ids or {}
    writer,write=_writer(offering,offering['model_identifier'])
    model_field=_key(offering,'model')
    _envelope(write,operation,model_field,offering['model_identifier'])
    prompt=_key(offering,'prompt')
    write(prompt,forwarding['effective_prompt'],'authored','selected-rendition')
    if forwarding.get('prompt_trace'):
        kept=[row for row in writer.trace if row['target_field']!=prompt]
        writer.trace=kept+[{**row,'target_field':prompt} for row in forwarding['prompt_trace']]
    layout={'model':model_field,'operation':['operation'],'primary_text':prompt,'negative_text':None,
            'output_count':['count'],'fixed_output_count':None,'seed':None,'media':[],'management':[['request_id']],
            'content':[{'id':'prompt','field':prompt}],
            'fields':[{'id':'prompt','field':prompt,'kind':'content'},{'id':'model','field':model_field,'kind':'fixed'},
                      {'id':'operation','field':['operation'],'kind':'fixed'},{'id':'count','field':['count'],'kind':'parameter'}]}
    selected=forwarding['selected_transport'];negative=selected['rendition'].get('negative') or ''
    if selected['mode'] in {'separate-field','native-subset'} and negative:
        field=_key(offering,'negative prompt')
        write(field,negative,'authored','selected-negative-channel')
        layout['negative_text']=field;layout['content'].append({'id':'negative','field':field})
        layout['fields'].append({'id':'negative','field':field,'kind':'content'})
    parameters=dict(forwarding.get('parameters') or {})
    if 'count' in parameters and parameters['count']!=count:
        raise ValueError('package output count differs from the explicit dispatch count')
    if 'seed' in parameters:
        if seed is not None and parameters['seed']!=seed:
            raise ValueError('package seed differs from the explicit dispatch seed')
        seed=parameters['seed']
    for name,value in sorted(parameters.items()):
        if name in {'seed','count'}:continue
        write(path_parts(name),value,'model-setting','selected-parameter')
        layout['fields'].append({'id':'parameter:'+name,'field':path_parts(name),'kind':'parameter'})
    paths=[str(item['resolved_path']) for item in forwarding.get('selected_references') or [] if item.get('resolved_path')]
    if paths:
        role=ROLES.get(forwarding.get('reference_media_role'))
        if role is None or role not in (offering.get('request_keys') or {}):
            raise ValueError('selected reference transport must be explicit and exposed by the offering')
        if role!='reference images' and len(paths)!=1:
            raise ValueError('selected source-image transport takes exactly one image')
        field=_key(offering,role);many=role=='reference images'
        values=[media_ids.get(path,MANAGEMENT_VALUE) for path in paths]
        write(field,values if many else values[0],'reference-binding','ordered-media',[f'attachment:{i+1}' for i in range(len(paths))])
        for index in range(len(paths)):
            location=field+[index] if many else field
            layout['media'].append({'index':index,'field':location})
            layout['fields'].append({'id':f'media:{index+1}','field':location,'kind':'media'})
    for control in forwarding.get('native_reference_controls',[]):
        write(control['field'],control['value'],'reference-binding','native-reference-controls',control['binding_ids'])
        layout['fields'].append({'id':control['id'],'field':control['field'],'kind':'fixed'})
    write(['count'],count,'model-setting','explicit-output-count')
    if seed is not None:
        write(['seed'],seed,'model-setting','explicit-seed')
        layout['seed']=['seed'];layout['fields'].append({'id':'seed','field':['seed'],'kind':'parameter'})
    return {'request':writer.request,'layout':layout,'request_trace':writer.trace}


def added_parameters(offering:dict,seed:int|None=None,count:int=1)->dict:
    if type(count) is not int or count<1:
        raise ValueError('positive explicit output count required')
    return {'count':count,**({'seed':seed} if seed is not None else {})}


def compile_upscale(model_identifier:str,source_path:str,scale:float,settings:dict,offering:dict,service:dict,
                    media_ids:dict,guidance:str|None=None)->dict:
    from request_contract import MANAGEMENT_VALUE,path_parts
    operation=OPERATIONS['upscale']
    if operation not in service.get('operations',{}):
        raise ValueError('service does not declare '+operation)
    if guidance:
        raise ValueError('the synthetic upscale takes no guidance prompt')
    if (offering.get('parameter_keys') or {}).get('scale')!='scale' or _key(offering,'input image')!=['image']:
        raise ValueError("the synthetic upscale offering must declare its factor on 'scale' and its image on 'image'")
    writer,write=_writer(offering,model_identifier)
    model_field=['model']
    _envelope(write,operation,model_field,model_identifier)
    write(['scale'],scale,'model-setting','selected-scale')
    write(['image'],media_ids.get(source_path,MANAGEMENT_VALUE),'reference-binding','upscale-source')
    layout={'model':model_field,'operation':['operation'],'primary_text':None,'negative_text':None,'output_count':None,
            'fixed_output_count':1,'seed':None,'media':[{'index':0,'field':['image']}],'management':[['request_id']],'content':[],
            'fields':[{'id':'model','field':model_field,'kind':'fixed'},{'id':'operation','field':['operation'],'kind':'fixed'},
                      {'id':'scale','field':['scale'],'kind':'parameter'},{'id':'media:1','field':['image'],'kind':'media'}]}
    for name,value in sorted(settings.items()):
        write(path_parts(name),value,'model-setting','selected-upscale-setting')
        layout['fields'].append({'id':'parameter:'+name,'field':path_parts(name),'kind':'parameter'})
    return {'request':writer.request,'layout':layout,'request_trace':writer.trace}


def upload_bytes(data:bytes,media_type:str,service:dict,key:str)->dict:
    endpoint(service)
    if not data:raise ValueError('Synthetic input must contain actual bytes.')
    dimensions=struct.unpack('>II',data[16:24]) if data.startswith(b'\x89PNG\r\n\x1a\n') and len(data)>=24 else (32,32)
    identifier='synthetic:'+hashlib.sha256(data).hexdigest()+':'+':'.join(str(n) for n in dimensions)
    return {'provider_id':identifier,'response':{'synthetic':True,'media_id':identifier},
            'usage':{'currency':'USD','amount':'0','final':True}}


def _png(width:int,height:int,colour:bytes)->bytes:
    def chunk(name:bytes,content:bytes)->bytes:
        return struct.pack('>I',len(content))+name+content+struct.pack('>I',zlib.crc32(name+content)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+colour*width)*height))+chunk(b'IEND',b'')


def _answer(request:dict)->dict:
    width=request.get('width',32);height=request.get('height',32);count=request.get('count',0)
    if request.get('operation')==OPERATIONS['upscale']:
        try:
            width,height=(int(n) for n in request['image'].rsplit(':',2)[1:])
            scale=request['scale'];width=int(width*scale);height=int(height*scale);count=1
        except (ValueError,TypeError,KeyError,AttributeError):
            return {'errors':[{'code':'synthetic-source','message':'The fixture requires its actually uploaded PNG source.'}]}
    if not (type(width) is int and type(height) is int and 1<=width<=2048 and 1<=height<=2048):
        return {'errors':[{'code':'synthetic-size','message':'Synthetic example dimensions must be integers from 1 through 2048.'}]}
    if not 1<=count<=20:
        return {'errors':[{'code':'synthetic-count','message':'Synthetic example output count is outside its declared contract.'}]}
    results=[]
    for index in range(count):
        identity=c.content_id({'request':request,'index':index})
        raw=_png(width,height,bytes.fromhex(identity[:6]))
        results.append({'id':'synthetic-'+identity,'seed':request.get('seed'),'data':base64.b64encode(raw).decode('ascii')})
    return {'synthetic':True,'limitations':['Local protocol fixture, not generated artwork or a provider observation.'],
            'data':results,'usage':{'currency':'USD','amount':'0','final':True}}


def send(request:dict,service:dict,key:str)->dict:
    endpoint(service)
    answer=_answer(request)
    if isinstance(request.get('request_id'),str):
        _ANSWERED[request['request_id']]=copy.deepcopy(answer)
    return answer


def lookup(request:dict,service:dict,key:str)->dict|None:
    """The answer this process's synthetic service gave to the same request_id, or None."""
    endpoint(service)
    identifier=request.get('request_id') if isinstance(request,dict) else None
    found=_ANSWERED.get(identifier) if isinstance(identifier,str) else None
    return copy.deepcopy(found) if found is not None else None


def rejections(answer:dict)->list[dict]:return list(answer.get('errors',[]))
def results(answer:dict)->list[dict]:return list(answer.get('data',[]))
def observation_outcome(answer:dict)->str:return 'rejected' if rejections(answer) else 'accepted'


def usage(answer:dict)->dict|None:
    return answer.get('usage')
