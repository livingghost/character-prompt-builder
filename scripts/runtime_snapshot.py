"""Content-owned execution runtime, distinct from the disposable search cache.

A snapshot keeps every resolved record in full and the complete textual files
of each pack that contributed to the catalogue. Each file is stored once under
`runtime/objects/<sha256>`; a snapshot directory maps every pack path to its
object, so a later snapshot stores only the files that changed. Each named
resource is pinned as the one file it resolved to. Selected media are captured
by the Generation Package.

A prepared run records its binding: the model, service, guides, records and
pack evidence it actually used, each with pack, path and SHA-256. Freshness
checks hash those live files and compare the enabled packs.

One public call verifies a fixed snapshot once and builds its catalogue once.
The call is the current operation, else a `public_call()` block, else the
outermost open production transaction. A forced read verifies again.
"""
from __future__ import annotations
import contextlib
import contextvars
import copy
import dataclasses
import os
import threading
from pathlib import Path
from typing import Iterator

import execution_contract as c
import production_store as store
from production_diagnostics import Diagnostic, ProductionError

TEXT_SUFFIXES = {'.json', '.md', '.txt', '.yaml', '.yml', '.csv'}
RETARGET = ('python scripts/production_workflow.py retarget --root {root} --from {run} '
            '--task TASK_FILE --reason REASON --prepare')


def settings_dict(settings) -> dict:
    return {field.name: ([str(p) for p in getattr(settings,field.name)] if field.name=='roots'
            else str(getattr(settings,field.name)) if isinstance(getattr(settings,field.name),Path)
            else getattr(settings,field.name)) for field in dataclasses.fields(settings)}


def settings_from(value: dict):
    from pack_manager import PackSettings
    fields=copy.deepcopy(value)
    for name in ('state_file','cache_dir','managed_root','quarantine_root'):fields[name]=Path(fields[name])
    fields['roots']=tuple(Path(p) for p in fields['roots'])
    for name in ('default_enabled_packs','protected_pack_ids'):
        fields[name]=tuple(fields.get(name,[]))
    return PackSettings(**fields)


def descriptor(value: dict) -> dict:
    """The fixed runtime a preparation starts from, before it binds its own parts."""
    return {'sha256': value['sha256'], 'settings': copy.deepcopy(value['settings'])}


def capture(catalog, settings, destination: Path) -> dict:
    """Capture a validated resolved catalogue without changing pack selection.

    A pack with `pack.lock.json` must match its lock. Commons and a pack still
    being edited have no lock: their files are inventoried at capture, and every
    captured file must match that inventory.
    """
    from pack_manager import PackError,load_effective_state,discover_packs,inventory_rows,canonical_json,sha256_bytes
    state=load_effective_state(settings)
    discovered,_=discover_packs(settings,state)
    sources=[(r.source_pack,r.relative_path) for r in catalog.resources.values()]
    present={e.source_pack for e in catalog.entries}|{pack for pack,_ in sources}
    selected=set(state['enabled_packs'])
    if present-selected:
        raise ProductionError('PACK_SELECTION_CHANGED','The resolved catalogue contains a pack no longer selected.',phase='runtime-resolution',expected=sorted(present),actual=sorted(selected))
    packs=[]
    for ident in sorted(present):
        if ident not in discovered:
            raise ProductionError('RECORD_NOT_FOUND','A selected runtime pack has no unique current root.',phase='runtime-resolution',pack=ident)
        pack=discovered[ident];base=pack.root
        locked=(base/'pack.lock.json').is_file()
        try:
            if locked:
                lock=c.load(base/'pack.lock.json');rows=lock['files'];content=lock['content_sha256']
            else:
                rows=inventory_rows(base);content=sha256_bytes(canonical_json(rows).encode('utf-8'))
        except (PackError,KeyError,TypeError) as exc:
            raise ProductionError('INPUT_CONSISTENCY_ERROR','The pack inventory cannot be read: '+str(exc),phase='runtime-resolution',pack=ident,file=str(base)) from exc
        listed={row['path']:row for row in rows}
        required={e.source_file for e in catalog.entries if e.source_pack==ident}
        required|={relative for pack,relative in sources if pack==ident}
        # Keep complete textual dependency files, including execution policies
        # referenced indirectly by model/offering records and provider schemas.
        required|={item for item in listed if Path(item).suffix.lower() in TEXT_SUFFIXES}
        required|={'pack.json'}
        if locked:required.add('pack.lock.json')
        files=[]
        for relative in sorted(required):
            raw=store.stable_bytes(base,relative);digest=c.digest(raw)
            if relative!='pack.lock.json':
                expected=listed.get(relative)
                if expected is None or expected['sha256']!=digest:
                    raise ProductionError('PACK_CONTENT_MISMATCH',
                        'Captured bytes differ from the pack lock.' if locked else 'A pack file changed while the runtime was captured.',
                        phase='runtime-resolution',pack=ident,resource=relative,expected=expected['sha256'] if expected else None,actual=digest,
                        required_action='Rebuild the lock of a released pack, or finish the edit, then prepare again.')
            c.atomic(destination/'packs'/ident/relative,raw)
            files.append({'path':relative,'sha256':digest,'size':len(raw)})
        packs.append({'pack_id':ident,'release':pack.release,'content_sha256':content,'files':files})
    entries=[{'kind':e.kind,'category':e.category,'record':e.record,'source_pack':e.source_pack,'source_file':e.source_file} for e in catalog.entries]
    # One resolved file per name: the pack that supplies it and its path there.
    resources={name:{'media_type':r.media_type,'pack_id':r.source_pack,'path':r.relative_path}
               for name,r in sorted(catalog.resources.items())}
    payload={'selection':{'enabled_packs':state['enabled_packs']},
             'packs':packs,'entries':entries,'phrases':catalog.phrases,'profiles':catalog.profiles,'resources':resources,
             'diagnostics':list(catalog.diagnostics)}
    digest=c.content_id(payload)
    c.atomic(destination/'snapshot.json',c.encoded(payload))
    return {'sha256':digest,'settings':settings_dict(settings)}


def path(root:Path, descriptor:dict) -> Path:
    return c.local(root,'runtime/snapshots/'+c.sha(descriptor['sha256']),exists=False)


# What a public call without an operation has verified, while `public_call()` is open.
_PUBLIC_CALL: contextvars.ContextVar[dict|None] = contextvars.ContextVar('cpb_public_call', default=None)
# What each open production transaction has verified, by connection.
_TRANSACTIONS: dict[int,tuple[object,dict]] = {}
# Threads in transactions on different studios share `_TRANSACTIONS`.
_TRANSACTIONS_GUARD = threading.Lock()


@contextlib.contextmanager
def public_call() -> Iterator[None]:
    """Share verified content among the stages of one public call.

    A block inside an open block or inside an operation adds no scope of its own.
    """
    if _PUBLIC_CALL.get() is not None:
        yield
        return
    token=_PUBLIC_CALL.set({})
    try:yield
    finally:_PUBLIC_CALL.reset(token)


def _transaction_scope(connection) -> dict:
    with _TRANSACTIONS_GUARD:
        held=_TRANSACTIONS.get(id(connection))
        if held is None or held[0] is not connection:
            open_now={id(item) for item in store._CONNECTIONS.get().values()}
            for key in list(_TRANSACTIONS):
                if key not in open_now:_TRANSACTIONS.pop(key,None)
            held=_TRANSACTIONS[id(connection)]=(connection,{})
        return held[1]


def call_scope() -> dict|None:
    """What the current public call has verified, or None outside any call.

    The call is the current operation, else the open `public_call()` block, else
    the outermost open production transaction. It holds snapshot verifications,
    catalogues and pack comparisons.
    """
    from operation_context import current
    operation=current()
    if operation is not None:
        scope=getattr(operation,'_verified_content',None)
        if scope is None:scope=operation._verified_content={}
        return scope
    scope=_PUBLIC_CALL.get()
    if scope is not None:return scope
    connections=store._CONNECTIONS.get()
    return _transaction_scope(next(iter(connections.values()))) if connections else None


def check_scope(root:Path) -> dict|None:
    """The scope one run check may reuse: the outermost open transaction of `root`, else the public call.

    A new transaction starts empty. `begin_step` checks the run and its live
    sources again even inside a caller's transaction.
    """
    connection=store._CONNECTIONS.get().get(str(Path(root).resolve()))
    return _transaction_scope(connection) if connection is not None else call_scope()


def _retarget_action(root, run) -> dict:
    studio=str(root) if root else 'STUDIO'
    if ' ' in studio:studio=f'"{studio}"'
    return {'operation':'retarget','command':RETARGET.format(root=studio,run=run or 'RUN'),
            'effect':'Prepare a new run from this one against the current runtime, keeping its lineage.'}


def _broken(code:str,message:str,**details) -> ProductionError:
    return ProductionError(code,message,phase='runtime-integrity',
        required_action='Retarget from this run to prepare against the current runtime; the fixed runtime cannot be repaired in place.',
        actions=[_retarget_action(None,None)],**details)


def _mark_verified(directory:Path,descriptor:dict) -> None:
    scope=call_scope()
    if scope is not None:scope[('runtime-files',str(directory.resolve()),descriptor['sha256'])]=True


def read(directory:Path, descriptor:dict, *, verify_files:bool=True, force_verify:bool=False) -> dict:
    """The fixed runtime metadata, checked against its digest, with each pinned pack file checked.

    One public call checks the same snapshot bytes once. `force_verify` checks
    the metadata and every file again, as the last check before an external effect.
    """
    try:
        raw=c.read(c.local(directory,'snapshot.json'));payload=c.decode(raw)
    except (OSError,ValueError) as exc:
        raise _broken('RUNTIME_SNAPSHOT_CORRUPT','Required fixed runtime metadata is missing or unreadable.',expected=descriptor['sha256'],file=str(directory)) from exc
    scope=None if force_verify else call_scope()
    place=(str(directory.resolve()),descriptor['sha256'])
    held=c.digest(raw)
    if scope is None or scope.get(('runtime-payload',*place))!=held:
        if c.content_id(payload)!=descriptor['sha256']:
            raise _broken('RUNTIME_SNAPSHOT_CORRUPT','Fixed runtime metadata differs from its digest.',expected=descriptor['sha256'],actual=c.content_id(payload))
        recorded=call_scope()
        if recorded is not None:recorded[('runtime-payload',*place)]=held
    if verify_files and (scope is None or ('runtime-files',*place) not in scope):
        files=[(pack['pack_id'],'packs/'+pack['pack_id']+'/'+item['path'],item) for pack in payload['packs'] for item in pack['files']]
        for pack,relative,item in files:
            local=c.local(directory,relative,exists=False)
            if not local.is_file():
                raise _broken('PINNED_RESOURCE_MISSING','A fixed runtime resource is missing.',pack=pack,resource=relative,expected=item['sha256'],file=str(local))
            if c.sha256_file(local)!=item['sha256'] or local.stat().st_size!=item['size']:
                raise _broken('RUNTIME_SNAPSHOT_CORRUPT','A fixed runtime resource differs from its recorded contents.',pack=pack,resource=relative,expected=item['sha256'],file=str(local))
        _mark_verified(directory,descriptor)
    return payload


def _alias(source:Path,target:Path) -> None:
    """Make `target` a hard link to `source`, or keep its verified copy where the link fails."""
    temporary=target.parent/(c.TEMPORARY_PREFIX+os.urandom(8).hex())
    try:
        os.link(source,temporary)
    except OSError:
        return
    try:os.replace(temporary,target)
    finally:temporary.unlink(missing_ok=True)


def _store_objects(root:Path,staged:Path,payload:dict) -> dict:
    """Store each staged file once under runtime/objects and alias the view to it.

    A file system without hard links gets a copy of the same checked bytes, and
    the snapshot view keeps its own verified copy.
    """
    counts={'files':0,'stored':0,'reused':0}
    for pack in payload['packs']:
        for item in pack['files']:
            counts['files']+=1
            view=c.local(staged,'packs/'+pack['pack_id']+'/'+item['path'])
            stored=c.local(root,'runtime/objects/'+c.sha(item['sha256']),exists=False)
            if not stored.is_file():
                raw=c.read(view)
                if c.digest(raw)!=item['sha256'] or len(raw)!=item['size']:
                    raise _broken('RUNTIME_SNAPSHOT_CORRUPT','A captured runtime file changed before storage.',pack=pack['pack_id'],resource=item['path'],expected=item['sha256'],file=str(view))
                stored.parent.mkdir(parents=True,exist_ok=True)
                try:
                    os.link(view,stored)
                except FileExistsError:
                    pass
                except OSError:
                    c.atomic(stored,raw,replace=True);counts['stored']+=1;continue
                else:
                    counts['stored']+=1;continue
            if c.sha256_file(stored)!=item['sha256'] or stored.stat().st_size!=item['size']:
                raise _broken('RUNTIME_SNAPSHOT_CORRUPT','A stored runtime object differs from its content digest.',pack=pack['pack_id'],resource=item['path'],expected=item['sha256'],file=str(stored))
            counts['reused']+=1
            if not os.path.samefile(view,stored):_alias(stored,view)
    return counts


def publish(root:Path, staged:Path, descriptor:dict) -> Path:
    """Publish a captured snapshot, storing only file contents not already stored."""
    import shutil
    from operation_context import current
    target=path(root,descriptor)
    with c.lock(root):
        if target.exists():
            read(target,descriptor)
            shutil.rmtree(staged)
            counts={'snapshot_reused':True}
        else:
            payload=read(staged,descriptor,verify_files=False)
            counts=_store_objects(root,staged,payload)
            target.parent.mkdir(parents=True,exist_ok=True)
            c.publish_directory(staged,target)
            c.fsync_dir(target.parent)
            # Every view file was hashed as it was stored or matched to an object.
            _mark_verified(target,descriptor)
            counts['snapshot_reused']=False
    if current() is not None:
        current().event('runtime_snapshot_published',phase='artifact-publication',snapshot=descriptor['sha256'],**counts)
    return target


def _pinned(payload:dict) -> dict:
    return {(pack['pack_id'],item['path']):item['sha256'] for pack in payload['packs'] for item in pack['files']}


def _reading_resources(directory:Path) -> dict:
    """Named pack resources the route reading declared, from the issued reading copy."""
    found={}
    ledger=directory/'reads.jsonl'
    if not ledger.is_file():return found
    for line in c.read(ledger).decode('utf-8').splitlines():
        if line.strip():
            for name,row in (c.decode(line.encode('utf-8')).get('resources') or {}).items():
                if row.get('status')=='present':found[name]=row
    return found


def bind(directory:Path, payload:dict, looked_up:set[str]) -> dict:
    """The fixed runtime parts one preparation actually used.

    `directory` is the compile directory: it holds the resolved target, the
    issued reading, the retrieval record and the pack evidence the package read.
    `looked_up` holds the named resources looked up while compiling.
    """
    pinned=_pinned(payload)
    def located(pack,relative):
        digest=pinned.get((pack,relative))
        if digest is None:
            raise ProductionError('PINNED_RESOURCE_MISSING','A resolved runtime dependency is not part of the fixed runtime.',
                                  phase='runtime-binding',pack=pack,resource=relative)
        return {'pack':pack,'path':relative,'sha256':digest}
    entries={}
    for entry in payload['entries']:
        if isinstance(entry['record'].get('id'),str):entries[entry['record']['id']]=entry
    target=c.load(directory/'execution-target.json')
    package=c.load(directory/'package.json') if (directory/'package.json').is_file() else {}
    records={}
    def record(ident,role):
        entry=entries.get(ident)
        if entry is not None and ident not in records:
            records[ident]={'id':ident,'role':role,**located(entry['source_pack'],entry['source_file'])}
    record(target['model_id'],'model')
    if target['model_id'] not in records:
        raise ProductionError('RECORD_NOT_FOUND','The resolved model record is not part of the fixed runtime.',phase='runtime-binding',record=target['model_id'])
    retrieval=package.get('retrieval_record') if isinstance(package.get('retrieval_record'),dict) else {}
    for element in retrieval.get('elements') or []:
        for ident in [*(element.get('adopted_records') or []),*(element.get('inspected_records') or [])]:
            record(ident,'retrieval')
    roles={name:'guide' for name in _reading_resources(directory)}
    roles['service-profiles']='service'
    for name in looked_up:roles.setdefault(name,'lookup')
    resources=[]
    for name in sorted(roles):
        resource=payload['resources'].get(name)
        if resource is not None:
            resources.append({'name':name,'role':roles[name],**located(resource['pack_id'],resource['path'])})
    evidence=[]
    for locator in sorted(package.get('input_snapshots') or {}):
        if locator.startswith('@pack/'):
            pack,_,relative=locator[len('@pack/'):].partition('/')
            evidence.append({'locator':locator,**located(pack,relative)})
    return {'model':target['model_id'],'service':target['offering']['service'],
            'records':sorted(records.values(),key=lambda row:(row['role'],row['id'])),'resources':resources,'evidence':evidence}


def dependencies(binding:dict) -> list[dict]:
    """Every bound record, resource and evidence file, as pack, path and SHA-256."""
    return [*binding['records'],*binding['resources'],*binding['evidence']]


def _run_bindings(root:Path) -> list[tuple[str,dict]]:
    """Registered runs and their bindings, read once per public call and run set."""
    rows=store.runs(root)
    key=('run-bindings',str(Path(root).resolve()),tuple(row['run_id'] for row in rows))
    cache=call_scope()
    if cache is None:cache={}
    if key not in cache:
        found=[]
        for row in rows:
            try:
                prepared=c.load(c.local(root,row['directory']+'/prepared.json'))
                found.append((row['run_id'],prepared['runtime_snapshot']['binding']))
            except (OSError,ValueError,KeyError,TypeError):
                continue
        cache[key]=found
    return cache[key]


def _affects(binding:dict,match:tuple) -> bool:
    kind=match[0]
    if kind=='pack':return any(row['pack']==match[1] for row in dependencies(binding))
    if kind=='file':return any((row['pack'],row['path'])==match[1:] for row in dependencies(binding))
    if kind=='records':return any(row['id'] in match[1] for row in binding['records'])
    if kind=='resources':return any(row['name'] in match[1] for row in binding['resources'])
    return False


def _compare(root:Path,payload:dict,binding:dict,settings) -> list[dict]:
    from pack_manager import load_effective_state,discover_packs,declared_record_ids
    rows=[]
    def issue(code,message,severity='error',match=None,**details):
        rows.append({'code':code,'severity':severity,'message':message,'match':match,'details':details})
    if not settings.state_file.is_file():
        issue('PACK_SELECTION_CHANGED','The pack state used for this runtime is missing.',file=str(settings.state_file),
              expected=str(settings.state_file),actual=None)
        return rows
    state=load_effective_state(settings);discovered,_=discover_packs(settings,state)
    enabled=set(state['enabled_packs'])-set(state.get('disabled_packs',[]))
    releases={pack['pack_id']:pack['release'] for pack in payload['packs']}
    bound=dependencies(binding)
    bound_packs=sorted({row['pack'] for row in bound})
    for ident in bound_packs:
        if ident not in enabled:
            issue('PACK_NOT_ENABLED','The author no longer enables a pack this run uses.',match=('pack',ident),pack=ident,expected='enabled',actual='disabled');continue
        live=discovered.get(ident)
        if live is None:
            issue('RECORD_NOT_FOUND','A pack this run uses has no unique accessible root.',match=('pack',ident),pack=ident,expected='one pack root',actual=None);continue
        if live.release!=releases[ident]:
            issue('PACK_RELEASE_MISMATCH','The current and pinned pack releases differ.',match=('pack',ident),pack=ident,expected=releases[ident],actual=live.release)
        checked=set()
        for row in bound:
            if row['pack']!=ident or row['path'] in checked:continue
            checked.add(row['path'])
            try:
                source=c.local(live.root,row['path']);actual=c.sha256_file(source)
            except (ValueError,OSError):
                issue('RECORD_NOT_FOUND','A file this run uses is missing from its pack.',match=('file',ident,row['path']),
                      pack=ident,resource=row['path'],file=str(live.root/row['path']),expected=row['sha256'],actual=None);continue
            if actual==row['sha256']:continue
            wanted=[item['id'] for item in binding['records'] if (item['pack'],item['path'])==(ident,row['path'])]
            try:
                document=c.load(source);present={item.get('id') for item in document.get('records',[]) if isinstance(item,dict)}
            except (OSError,ValueError,AttributeError):
                present=set(wanted)
            lost=[name for name in wanted if name not in present]
            if lost:
                issue('RECORD_NOT_FOUND','A record this run uses is no longer in its pack file.',match=('records',tuple(lost)),
                      pack=ident,resource=row['path'],record=lost,file=str(source),expected=lost,actual=None)
            else:
                issue('PACK_CONTENT_MISMATCH','Current source bytes differ from the fixed execution resource.',match=('file',ident,row['path']),
                      pack=ident,resource=row['path'],file=str(source),expected=row['sha256'],actual=actual)
    before=set(payload['selection']['enabled_packs'])
    for ident in sorted(before-enabled-set(bound_packs)):
        issue('PACK_SELECTION_CHANGED','A pack enabled at preparation is no longer enabled. This run uses nothing from it.',
              severity='warning',match=('pack',ident),pack=ident,expected='enabled',actual='disabled')
    used={row['id']:row['pack'] for row in binding['records']}
    named={row['name'] for row in binding['resources']}
    for ident in sorted(enabled-before):
        live=discovered.get(ident)
        declared=set();bindings=set()
        if live is not None:
            declared=declared_record_ids(live.root,live.manifest)
            declared|={str(row.get('record_id')) for row in live.manifest.get('replaces') or [] if isinstance(row,dict)}
            bindings=set((live.manifest.get('content') or {}).get('resource_bindings') or {})
        replaced=sorted(declared&set(used));bound=sorted(bindings&named)
        if replaced:
            issue('PACK_SELECTION_CHANGED','A newly enabled pack declares a record this run uses, so it replaces or excludes that record.',
                  match=('records',tuple(replaced)),pack=ident,record=replaced,expected='disabled',actual='enabled')
        if bound:
            issue('PACK_SELECTION_CHANGED','A newly enabled pack binds a named resource this run uses, so the resolved resource may come from it or be excluded.',
                  match=('resources',tuple(bound)),pack=ident,resource=bound,expected='disabled',actual='enabled')
        if not replaced and not bound:
            issue('PACK_SELECTION_CHANGED','A pack was enabled after preparation. This run uses nothing it declares.',
                  severity='warning',match=('pack',ident),pack=ident,expected='disabled',actual='enabled')
    return rows


def _guidance(row:dict,*,root:Path,run:str|None,command:str) -> tuple[str,list[dict]]:
    """The required action and the possible operations for one freshness finding."""
    details=row['details'];pack=details.get('pack');retarget=_retarget_action(root,run)
    if row['severity']=='warning':
        return ('No action is required for this run. Review the change if it was not intended.',
                [{'operation':'continue','command':None,'effect':'The run keeps its fixed runtime; the change does not touch what it uses.'}])
    restore={'operation':'restore','command':None,'effect':'Restore the pinned content or selection; the run then continues unchanged.'}
    code=row['code']
    if code=='PACK_NOT_ENABLED':
        return ('Enable the pack again to keep this run, or retarget from it to adopt the current selection.',
                [{'operation':'enable-pack','command':f'{command} enable {pack}','effect':'Enable the pack this run uses.'},retarget])
    if code=='PACK_SELECTION_CHANGED' and (details.get('record') or details.get('resource')):
        return ('Disable the newly enabled pack to keep this run, or retarget from this run to adopt what it changes.',
                [{'operation':'disable-pack','command':f'{command} disable {pack}','effect':'Leave out the pack that changes a record or named resource this run uses.'},retarget])
    if code=='PACK_SELECTION_CHANGED':
        return ('Restore the pack state file this run was prepared with, or retarget from this run.',[restore,retarget])
    if code=='RECORD_NOT_FOUND':
        return ('Restore the missing pack, file or record, or retarget from this run to prepare against the current packs.',[restore,retarget])
    if code=='PACK_RELEASE_MISMATCH':
        return ('Restore the pinned pack release, or retarget from this run to adopt the current release.',[restore,retarget])
    return ('Restore the pinned content, or retarget from this run to adopt the edited pack content.',[restore,retarget])


def current_diagnostics(root:Path,descriptor:dict,*,run:str|None=None,force:bool=False)->list[dict]:
    """Compare a run's fixed runtime with the author's current packs and selection.

    Only the live files the run is bound to are hashed. One public call reuses
    a comparison while the descriptor, its binding and the pack state file
    bytes are unchanged; `force` compares again, as the last check before an
    external effect does. A live edit never changes the fixed runtime.
    """
    from pack_manager import pack_cli_command
    root=Path(root)
    payload=read(path(root,descriptor),descriptor)
    settings=settings_from(descriptor['settings'])
    try:state=c.digest(c.read(settings.state_file))
    except (OSError,ValueError):state=None
    key=('pack-comparison',str(root.resolve()),descriptor['sha256'],c.content_id(descriptor['binding']),state)
    cache=call_scope()
    if cache is None:cache={}
    if force or key not in cache:
        rows=_compare(root,payload,descriptor['binding'],settings)
        if rows:
            bindings=_run_bindings(root)
            for row in rows:
                row['affected_runs']=sorted(ident for ident,bound in bindings if row['match'] and _affects(bound,row['match']))
        cache[key]=rows
    command=pack_cli_command(settings)
    result=[]
    for row in cache[key]:
        action,actions=_guidance(row,root=root,run=run,command=command)
        details=copy.deepcopy(row['details']);file=details.pop('file',None)
        affected=list(row['affected_runs'])
        if run is not None and run not in affected:affected=sorted([*affected,run])
        result.append(Diagnostic(row['code'],row['message'],severity=row['severity'],phase='runtime-freshness',file=file,
            required_action=action,details={'run':run,**details,'affected_runs':affected,'actions':actions}).as_dict())
    return result


def require_current(root:Path,descriptor:dict,*,run:str|None=None,force:bool=False)->list[dict]:
    """Stop on a freshness error; return the warnings that leave this run usable."""
    result=current_diagnostics(root,descriptor,run=run,force=force)
    errors=[row for row in result if row['severity']=='error']
    if errors:
        first=errors[0]
        extra={key:value for key,value in first.items() if key not in {'code','severity','phase','file','pointer','message','required_action','blocked_checks','run'}}
        raise ProductionError(first['code'],first['message'],phase=first['phase'],file=first['file'],
                              required_action=first['required_action'],diagnostics=result,run=run,**extra)
    return result


class _Lookups(dict):
    """Named resources that remember which names were looked up."""
    def __init__(self,values:dict,seen:set[str]):
        super().__init__(values)
        self.seen=seen

    def __getitem__(self,name):
        self.seen.add(name)
        return super().__getitem__(name)

    def get(self,name,default=None):
        if name in self:self.seen.add(name)
        return super().get(name,default)


def _refuse(self,*args,**kwargs):
    raise TypeError('fixed runtime content is read-only; change a copy of it')


class _FixedRecord(dict):
    """A mapping of a fixed runtime: readable and serializable, refusing every change.

    `copy.deepcopy` gives an editable copy. `dict(value)` and `copy.copy` copy
    only the top level; nested values stay read-only.
    """
    __setitem__=__delitem__=__ior__=clear=pop=popitem=setdefault=update=_refuse
    def __copy__(self):return dict(self)
    def __deepcopy__(self,memo):
        result=memo[id(self)]={}
        for key,value in self.items():result[key]=copy.deepcopy(value,memo)
        return result
    def __reduce__(self):return (dict,(dict(self),))


class _FixedList(list):
    """A list of a fixed runtime: readable and serializable, refusing every change."""
    __setitem__=__delitem__=__iadd__=__imul__=append=extend=insert=pop=remove=clear=sort=reverse=_refuse
    def __copy__(self):return list(self)
    def __deepcopy__(self,memo):
        result=memo[id(self)]=[]
        result.extend(copy.deepcopy(value,memo) for value in self)
        return result
    def __reduce__(self):return (list,(list(self),))


def _fixed(value):
    if isinstance(value,dict):return _FixedRecord((key,_fixed(item)) for key,item in value.items())
    if isinstance(value,list):return _FixedList(_fixed(item) for item in value)
    return value


def catalogue(directory:Path,payload:dict,*,looked_up:set[str]|None=None,fingerprint:str|None=None):
    """The catalogue of one fixed snapshot, as read-only records shared by every lookup."""
    from pack_cache import RuntimePackCatalog,RuntimePackEntry,RuntimePackResource
    entries=tuple(RuntimePackEntry(kind=e['kind'],category=e['category'],record=_fixed(e['record']),source_pack=e['source_pack'],
                   source_root=directory/'packs'/e['source_pack'],source_file=e['source_file']) for e in payload['entries'])
    resources=_FixedRecord((name,RuntimePackResource(name=name,path=directory/'packs'/r['pack_id']/r['path'],media_type=r['media_type'],
                                                     source_pack=r['pack_id'],relative_path=r['path']))
                           for name,r in payload['resources'].items())
    if looked_up is not None:resources=_Lookups(resources,looked_up)
    assets={str(e.record['id']):[] for e in entries if e.kind!='asset' and e.record.get('id')}
    for entry in entries:
        if entry.kind=='asset':
            for ident in entry.record.get('canonical_record_ids',[]):
                if ident in assets:assets[ident].append(entry)
    return RuntimePackCatalog(fingerprint or c.content_id(payload),len(payload['packs']),entries,_fixed(payload['phrases']),_fixed(payload['profiles']),resources,
                              _FixedRecord((k,tuple(v)) for k,v in assets.items()),tuple(_fixed(payload['diagnostics'])),
                              pack_roots=_FixedRecord((pack['pack_id'],directory/'packs'/pack['pack_id']) for pack in payload['packs']))


def _shared_catalogue(directory:Path,descriptor:dict,payload:dict,looked_up:set[str]|None):
    """Build the catalogue of a verified snapshot once per public call; a binding block records its lookups."""
    scope=call_scope()
    key=('catalogue',str(directory.resolve()),descriptor['sha256'])
    built=scope.get(key) if scope is not None else None
    if built is None:
        # `read` checked that the payload's content digest is the descriptor's.
        built=catalogue(directory,payload,fingerprint=descriptor['sha256'])
        if scope is not None:scope[key]=built
    if looked_up is None:return built
    return dataclasses.replace(built,resources=_Lookups(built.resources,looked_up))


@contextlib.contextmanager
def using(directory:Path,descriptor:dict,*,binding:Path|None=None)->Iterator[dict]:
    """Serve catalogue lookups from one fixed snapshot.

    With `binding`, the compile directory of a preparation, the block's named
    resource lookups are recorded. When the block completes, the descriptor
    gains `binding`: the model, service, guides, records and pack evidence the
    preparation used.
    """
    from catalog_retrieval import runtime
    payload=read(directory,descriptor)
    previous=(runtime._PACK_SETTINGS,runtime._PACK_CATALOG_CACHE)
    looked_up:set[str]|None=set() if binding is not None else None
    runtime._PACK_SETTINGS=settings_from(descriptor['settings'])
    runtime._PACK_CATALOG_CACHE=_shared_catalogue(directory,descriptor,payload,looked_up)
    try:yield payload
    finally:runtime._PACK_SETTINGS,runtime._PACK_CATALOG_CACHE=previous
    if binding is not None:
        descriptor['binding']=bind(binding,payload,looked_up)
