"""Own exact pack inputs without turning serialization into an internal API.

Compilation consumes acquired source values directly. Publication preserves
the complete resolved catalogue and textual pack edition used by existing
repeat, variant and retarget operations. The used binding remains distinct
from that complete archive and determines current-source comparisons.

Fixed values are not proof that current inputs or permissions are unchanged.
Publication and current-source boundaries acquire the actual declared files;
domain consumers receive those exact bytes explicitly.
"""
from __future__ import annotations
import contextlib
import contextvars
import copy
import dataclasses
import functools
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Iterator

import execution_contract as c
import production_store as store
from owned_json import FrozenDict, freeze, mutable
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


@dataclasses.dataclass(frozen=True)
class FixedRuntimeRead:
    """Exact bytes and immutable values acquired at one fixed-input boundary."""

    directory: Path
    sha256: str
    raw: bytes = dataclasses.field(repr=False)
    payload: Mapping[str,Any]
    file_bytes: Mapping[tuple[str,str],bytes] = dataclasses.field(repr=False)

    @property
    def pack_roots(self) -> Mapping[str,Path]:
        return FrozenDict((row['pack_id'],self.directory/'packs'/row['pack_id']) for row in self.payload['packs'])

    def read_pack(self, pack: str, relative: str) -> bytes:
        """Read an already acquired member; a missing member has no live fallback."""
        try:
            return self.file_bytes[(pack,relative)]
        except KeyError as exc:
            raise _broken('PINNED_RESOURCE_MISSING','A required input is absent from the fixed runtime.',
                          pack=pack,resource=relative) from exc

    def read_named(self, locator: str) -> bytes:
        pack,relative=_pack_locator(locator)
        return self.read_pack(pack,relative)

    def document(self, pack: str, relative: str):
        return freeze(c.decode(self.read_pack(pack,relative)))

    def model_space(self, model_id: str) -> str:
        entries=[row for row in self.payload.get('entries',())
                 if row['kind']=='model' and row['record'].get('id')==model_id]
        if len(entries)!=1:
            raise ValueError('selected model has no unique fixed source')
        return '@pack/'+entries[0]['source_pack']

    def read_resource(self, name: str):
        """Return one named resource's provenance and verified bytes."""
        from types import SimpleNamespace
        from pack_cache import resource_warning
        resources = self.payload.get('resources', {})
        problem = resource_warning(SimpleNamespace(resources=resources,
            diagnostics=self.payload.get('diagnostics', ()), warnings=()), name)
        if problem:
            raise ValueError(problem)
        resource = resources.get(name)
        if resource is None:
            return None
        key = (resource['pack_id'], resource['path'])
        raw = self.read_pack(*key)
        return {'source_pack': key[0], 'path': key[1], 'sha256': c.digest(raw)}, raw


def _pack_locator(locator: str) -> tuple[str,str]:
    if not isinstance(locator,str) or not locator.startswith('@pack/'):
        raise ValueError('expected a qualified pack input')
    pack,separator,relative=locator[len('@pack/'):].partition('/')
    if not separator or not pack or not relative:
        raise ValueError('pack input has no relative file')
    return pack,relative


def _owned_runtime(directory: Path, descriptor: dict, read: FixedRuntimeRead) -> FixedRuntimeRead:
    if read.directory != Path(directory).resolve() or read.sha256 != descriptor['sha256']:
        raise ValueError('fixed runtime read belongs to another snapshot')
    return read


@dataclasses.dataclass
class CompileRuntime:
    """Acquired inputs and the exact members a compilation actually consumes.

    ``files`` and ``resources`` are the producer's dependency manifest, not a
    successful-current-check cache. This object never authorizes publication
    or an effect. A failed compilation discards it without publishing a runtime.
    """

    catalog: Any
    settings: Any
    _read: Any = dataclasses.field(repr=False)
    fixed: FixedRuntimeRead|None = None
    files: dict[tuple[str,str],bytes] = dataclasses.field(default_factory=dict,repr=False)
    resources: set[str] = dataclasses.field(default_factory=set)

    @property
    def pack_roots(self) -> Mapping[str,Path]:
        return self.catalog.pack_roots

    @classmethod
    def from_catalog(cls,catalog,settings) -> CompileRuntime:
        if catalog.inputs is None:
            raise ProductionError('PACK_RUNTIME_REQUIRED','Compilation requires acquired pack inputs.',phase='runtime-resolution')
        inputs=catalog.inputs
        def read(pack,relative):
            try:
                acquired=inputs.packs[pack]
                item=acquired.files[relative]
            except KeyError as exc:
                raise ProductionError('RECORD_NOT_FOUND','A required file is absent from the acquired pack.',
                                      phase='runtime-resolution',pack=pack,resource=relative) from exc
            return item.bytes_for_capture(lambda path:store.stable_bytes(acquired.root,path))
        return cls(catalog,settings,read)

    @classmethod
    def from_fixed(cls,read:FixedRuntimeRead,descriptor:dict) -> CompileRuntime:
        if read.sha256!=descriptor['sha256']:
            raise ValueError('fixed compilation inputs belong to another runtime')
        selected=catalogue(read.directory,read.payload,fingerprint=read.sha256,read=read)
        return cls(selected,settings_from(descriptor['settings']),read.read_pack,fixed=read)

    def read_pack(self,pack:str,relative:str) -> bytes:
        key=(pack,relative)
        if key not in self.files:
            self.files[key]=self._read(pack,relative)
        return self.files[key]

    def read_named(self,locator:str) -> bytes:
        return self.read_pack(*_pack_locator(locator))

    def document(self,pack:str,relative:str):
        return freeze(c.decode(self.read_pack(pack,relative)))

    def model_space(self,model_id:str) -> str:
        found=[entry for entry in self.catalog.entries
               if entry.kind=='model' and entry.record.get('id')==model_id]
        if len(found)!=1:
            raise ValueError('selected model has no unique acquired provider')
        return '@pack/'+found[0].source_pack

    def read_resource(self,name:str):
        from pack_cache import resource_warning
        problem=resource_warning(self.catalog,name)
        if problem:
            raise ValueError(problem)
        resource=self.catalog.resources.get(name)
        if resource is None:
            return None
        self.resources.add(name)
        raw=self.read_pack(resource.source_pack,resource.relative_path)
        return {'source_pack':resource.source_pack,'path':resource.relative_path,'sha256':c.digest(raw)},raw

    @contextlib.contextmanager
    def using(self):
        """Adapt standalone lookup APIs to these already acquired inputs."""
        from catalog_retrieval import runtime
        previous=(runtime._PACK_SETTINGS,runtime._PACK_CATALOG_CACHE)
        runtime._PACK_SETTINGS=self.settings
        runtime._PACK_CATALOG_CACHE=dataclasses.replace(self.catalog,
            resources=_Lookups(self.catalog.resources,self.resources),resource_reader=self.read_resource)
        try:
            yield self
        finally:
            runtime._PACK_SETTINGS,runtime._PACK_CATALOG_CACHE=previous


@dataclasses.dataclass(frozen=True)
class CompileInputs:
    """The source choice and retained target for one explicit compile operation."""

    mode: str
    runtime: CompileRuntime
    target: Mapping[str,Any]|None = None
    parent_descriptor: Mapping[str,Any]|None = None
    parent_read: FixedRuntimeRead|None = None
    diagnostics: tuple = ()


def compilation_inputs(root:Path,*,mode:str='prepare',parent:dict|None=None,
                       target:Mapping[str,Any]|None=None,run:str|None=None) -> CompileInputs:
    """Acquire current preparation inputs, or a derivation's fixed parent edition."""
    if mode not in {'prepare','repeat','variant','retarget'}:
        raise ValueError('unknown compilation input operation')
    if (parent is None)!=(mode in {'prepare','retarget'}):
        raise ValueError('repeat and variant require their parent runtime')
    if mode in {'repeat','variant'} and target is None:
        raise ValueError('repeat and variant require their retained execution target')
    parent_read=None
    diagnostics=[]
    if parent is not None:
        parent_read=acquire_runtime(path(root,parent),parent)
    if mode in {'repeat','variant'}:
        diagnostics=_current_diagnostics(root,parent,parent_read,run)
        _require_current_result(diagnostics,run)
        runtime=CompileRuntime.from_fixed(parent_read,parent)
    else:
        from catalog_retrieval.runtime import selected_pack_settings
        from pack_cache import load_runtime_catalog
        settings=settings_from(parent['settings']) if parent is not None else selected_pack_settings()
        if not settings.state_file.is_file():
            raise ProductionError('PACK_RUNTIME_REQUIRED','Pack state has not been initialized.',phase='runtime-resolution',
                                  required_action='Initialize the selected pack runtime before compiling.')
        catalog=load_runtime_catalog(settings)
        if not catalog.active_pack_count:
            raise ProductionError('PACK_NOT_ENABLED','No active pack satisfies the declared runtime.',phase='runtime-resolution')
        runtime=CompileRuntime.from_catalog(catalog,settings)
    return CompileInputs(mode,runtime,freeze(target) if target is not None else None,
                         freeze(parent) if parent is not None else None,parent_read,tuple(freeze(diagnostics)))


def require_retained(root:Path,inputs:CompileInputs,descriptor:dict,*,run:str|None=None) -> list[dict]:
    """A derivation keeps its target and exact parent runtime edition.

    These values describe the already acquired inputs, not current permission
    or a successful-check cache. Publication checks current sources again.
    """
    if inputs.parent_descriptor is None:
        return []
    old=inputs.parent_descriptor['binding'];new=descriptor['binding']
    if (old['model'],old['service'])!=(new['model'],new['service']):
        raise ProductionError('TARGET_CHANGE_REQUIRED','A variant retains its model and service; retarget to select another.',
                              phase='variation',run=run)
    if descriptor['sha256']!=inputs.parent_descriptor['sha256']:
        raise ProductionError('REPEAT_INPUT_MISMATCH','A derivation changed its fixed runtime edition.',phase='variation',run=run)
    return [mutable(row) for row in inputs.diagnostics]


def capture_compilation(source:CompileRuntime,destination:Path|None,*,target:dict,package:dict,
                        reading_resources:Mapping[str,Any],evidence_bytes:Mapping[str,bytes]|None=None) -> tuple[dict,FixedRuntimeRead|None]:
    """Bind the compilation and retain the complete, existing runtime edition.

    Live inputs are serialized only after semantic compilation. Derivations
    use their parent's existing snapshot without copying or changing its hash.
    A check computes the same descriptor but writes no disposable runtime tree.
    """
    supplied=evidence_bytes or {}
    projection={**package,'input_snapshots':{**(package.get('input_snapshots') or {}),**supplied}}
    for locator in projection['input_snapshots']:
        if locator.startswith('@pack/'):
            raw=source.read_named(locator)
            if locator in supplied and supplied[locator]!=raw:
                raise ProductionError('PACK_CONTENT_MISMATCH','Pack evidence differs from its acquired source bytes.',
                                      phase='runtime-binding',file=locator)
    if source.fixed is not None:
        payload=source.fixed.payload
        result={'sha256':source.fixed.sha256,'settings':settings_dict(source.settings)}
        owned=source.fixed
    else:
        payload,files=_catalogue_inputs(source.catalog,retained=source.files)
        result,owned=_write_runtime(payload,files,source.settings,destination)
    result['binding']=bind(None,payload,source.resources,inputs={
        'target':target,'package':projection,'reading_resources':reading_resources})
    return result,owned


def _catalogue_inputs(catalog,*,retained:Mapping|None=None) -> tuple[dict,dict]:
    """Project the complete existing snapshot from the acquired catalogue.

    Selection, manifests, inventories and text come from the same input owner
    that selected the catalog. Binary payloads are verified against that owner
    when copied. Capture never discovers a second pack state for the same catalog.
    """
    from pack_manager import PackError,canonical_json,sha256_bytes
    inputs = catalog.inputs
    if inputs is None:
        raise ProductionError('PACK_RUNTIME_REQUIRED', 'Runtime capture requires an acquired live catalog.',
                              phase='runtime-resolution')
    state=inputs.state
    sources=[(r.source_pack,r.relative_path) for r in catalog.resources.values()]
    present={e.source_pack for e in catalog.entries}|{pack for pack,_ in sources}
    packs=[]
    file_bytes={}
    for ident in sorted(present):
        if ident not in inputs.packs:
            raise ProductionError('RECORD_NOT_FOUND','A catalog pack is absent from its acquired inputs.',phase='runtime-resolution',pack=ident)
        acquired=inputs.packs[ident]
        pack=inputs.discovered[ident];base=acquired.root
        locked='pack.lock.json' in acquired.files
        try:
            if locked:
                lock=acquired.json('pack.lock.json');rows=lock['files'];content=lock['content_sha256']
            else:
                rows=acquired.inventory();content=sha256_bytes(canonical_json(rows).encode('utf-8'))
        except (PackError,KeyError,TypeError) as exc:
            raise ProductionError('INPUT_CONSISTENCY_ERROR','The acquired pack inventory is invalid: '+str(exc),phase='runtime-resolution',pack=ident,file=str(base)) from exc
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
            try:
                raw=((retained or {})[(ident,relative)] if (ident,relative) in (retained or {})
                     else acquired.files[relative].bytes_for_capture(lambda path: store.stable_bytes(base, path)))
            except (PackError,KeyError,OSError) as exc:
                raise ProductionError('PACK_CONTENT_MISMATCH','A pack file no longer matches its acquired content: '+str(exc),
                    phase='runtime-resolution',pack=ident,resource=relative,
                    required_action='Finish the pack edit, then prepare again.') from exc
            digest=c.digest(raw)
            if relative!='pack.lock.json':
                expected=listed.get(relative)
                if expected is None or expected['sha256']!=digest:
                    raise ProductionError('PACK_CONTENT_MISMATCH',
                        'Captured bytes differ from the pack lock.' if locked else 'A pack file changed while the runtime was captured.',
                        phase='runtime-resolution',pack=ident,resource=relative,expected=expected['sha256'] if expected else None,actual=digest,
                        required_action='Rebuild the lock of a released pack, or finish the edit, then prepare again.')
            file_bytes[(ident,relative)]=raw
            files.append({'path':relative,'sha256':digest,'size':len(raw)})
        packs.append({'pack_id':ident,'release':pack.release,'content_sha256':content,'files':files})
    entries=[{'kind':e.kind,'category':e.category,'record':e.record,'source_pack':e.source_pack,'source_file':e.source_file} for e in catalog.entries]
    # One resolved file per name: the pack that supplies it and its path there.
    resources={name:{'media_type':r.media_type,'pack_id':r.source_pack,'path':r.relative_path}
               for name,r in sorted(catalog.resources.items())}
    payload={'selection':{'enabled_packs':state['enabled_packs'],'pack_order':state['pack_order']},
             'packs':packs,'entries':entries,'phrases':catalog.phrases,'profiles':catalog.profiles,'resources':resources,
             'diagnostics':list(catalog.diagnostics)}
    return payload,file_bytes


def _write_runtime(payload:dict,files:Mapping,settings,destination:Path|None) -> tuple[dict,FixedRuntimeRead|None]:
    raw=c.encoded(payload)
    digest=c.digest(raw)
    owned=None
    if destination is not None:
        from publication_artifacts import StagedArtifacts
        artifacts=StagedArtifacts(destination)
        for (pack,relative),content in sorted(files.items()):
            artifacts.write('packs/'+pack+'/'+relative,content)
        artifacts.write('snapshot.json',raw)
        owned=FixedRuntimeRead(Path(destination).resolve(),digest,raw,freeze(payload),freeze(files))
    return {'sha256':digest,'settings':settings_dict(settings)},owned


def capture_owned(catalog, settings, destination: Path) -> tuple[dict, FixedRuntimeRead]:
    """Export the complete catalogue from its acquired inputs."""
    payload,files=_catalogue_inputs(catalog)
    result,owned=_write_runtime(payload,files,settings,destination)
    assert owned is not None
    return result,owned


def capture(catalog, settings, destination: Path) -> dict:
    """Export a complete catalogue and its editable descriptor, without a run."""
    return capture_owned(catalog,settings,destination)[0]


def path(root:Path, descriptor:dict) -> Path:
    return c.local(root,'runtime/snapshots/'+c.sha(descriptor['sha256']),exists=False)


# What a public call without an operation has verified, while `public_call()` is open.
_PUBLIC_CALL: contextvars.ContextVar[dict|None] = contextvars.ContextVar('cpb_public_call', default=None)
# What each open production transaction has verified, by connection.
_TRANSACTIONS: contextvars.ContextVar[dict[int,tuple[object,dict]]] = contextvars.ContextVar(
    'cpb_transaction_reads', default={})


@contextlib.contextmanager
def public_call(*, fresh: bool = False) -> Iterator[None]:
    """Share verified content among the stages of one public call.

    Nested blocks share their caller unless ``fresh`` starts a new publication
    read boundary. A new boundary ends reuse in its enclosing call as well;
    leaving it must not restore an older successful read after a newer failure.
    Active transaction readers also discard their earlier observations. A
    projection owner starts publication after committing its transaction.
    """
    if not fresh and _PUBLIC_CALL.get() is not None:
        yield
        return
    enclosing = ([call_scope(), *(_transaction_scope(connection)
                  for connection in store._CONNECTIONS.get().values())] if fresh else [])
    for scope in enclosing:
        if scope is not None:
            scope.clear()
    token=_PUBLIC_CALL.set({})
    try:
        import protocol_contract
        with protocol_contract.read_scope(fresh=fresh):
            yield
    finally:
        for scope in enclosing:
            if scope is not None:
                scope.clear()
        _PUBLIC_CALL.reset(token)


def _transaction_scope(connection) -> dict:
    scopes = _TRANSACTIONS.get()
    held = scopes.get(id(connection))
    if held is None or held[0] is not connection:
        open_now = {id(item) for item in store._CONNECTIONS.get().values()}
        scopes = {key: item for key, item in scopes.items() if key in open_now}
        held = (connection, {})
        scopes[id(connection)] = held
        _TRANSACTIONS.set(scopes)
    return held[1]


def release_transaction(connection) -> None:
    """Dispose the completed connection's read state in its execution context."""
    scopes = _TRANSACTIONS.get()
    if id(connection) in scopes:
        _TRANSACTIONS.set({key: value for key, value in scopes.items() if key != id(connection)})


def operation(function):
    """Give a public Python operation the same read boundary as a CLI call."""
    @functools.wraps(function)
    def call(*args, **kwargs):
        with public_call():
            return function(*args, **kwargs)
    return call


def invalidate_runs(root: Path, *, source_boundary: bool = False) -> None:
    """Discard decoded run state after a write or a rolled-back write.

    Event state belongs to the transaction or public read boundary that
    observed it, never to a pathname. A transaction boundary also discards
    verified publication proof. Current-source and authority checks acquire
    their own inputs independently of these decoded values.
    """
    identity = str(Path(root).resolve())
    invalidate_studio(root)
    scopes = [call_scope()]
    connection = store._CONNECTIONS.get().get(identity)
    if connection is not None:
        scopes.append(_transaction_scope(connection))
    for scope in scopes:
        if scope is not None:
            for key in tuple(scope):
                if isinstance(key, tuple) and key[:2] == ('verified-run', identity):
                    del scope[key]
                elif source_boundary and isinstance(key, tuple) and key[:2] == ('verified-publication',identity):
                    del scope[key]


def invalidate_studio(root: Path) -> None:
    """End the current Studio read phase after an owned write or rollback.

    Reference readers retain the phase identity with their decoded values. A
    new marker makes even a resolver passed through nested calls reacquire its
    Studio inputs before using them again. Nothing survives the public call or
    the transaction whose scope holds this marker.

    """
    identity = str(Path(root).resolve())
    # A run can reference another Studio, including while its own transaction
    # remains open. Every active reference reader must observe an owned source
    # write, not only readers in the changed Studio's transaction.
    scopes = [call_scope(), *(_transaction_scope(connection)
                             for connection in store._CONNECTIONS.get().values())]
    for scope in scopes:
        if scope is not None:
            scope[('studio-read-phase', identity)] = object()


def call_scope() -> dict|None:
    """What the current public call has verified, or None outside any call.

    The call is the open `public_call()` block, else the current operation, else
    the outermost open production transaction. Fixed-runtime input acquisition
    uses explicit owners rather than entries in this run/Studio read scope.
    """
    scope=_PUBLIC_CALL.get()
    if scope is not None:return scope
    from operation_context import current
    operation=current()
    if operation is not None:
        scope=getattr(operation,'_verified_content',None)
        if scope is None:scope=operation._verified_content={}
        return scope
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


def _runtime_artifacts(directory: Path, payload: dict, raw: bytes, *, staged: bool = False):
    from publication_artifacts import ArtifactSet, StagedArtifacts
    rows = [{**item, 'path': 'packs/' + pack['pack_id'] + '/' + item['path']}
            for pack in payload['packs'] for item in pack['files']]
    artifacts = (StagedArtifacts if staged else ArtifactSet)(directory, rows)
    artifacts.add('snapshot.json', raw)
    return artifacts


def _require_membership(directory: Path, payload: dict, raw: bytes) -> None:
    """The snapshot owns its metadata and the exact declared pack files."""
    try:
        _runtime_artifacts(directory, payload, raw).require_membership()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        details = exc.diagnostic.as_dict() if isinstance(exc, ProductionError) else {'message': str(exc)}
        raise _broken('RUNTIME_SNAPSHOT_CORRUPT', 'Fixed runtime membership differs from its declared files.',
                      file=str(directory), cause=details) from exc


def _verify_fixed_file(directory: Path, pack: str, item: dict) -> bytes:
    relative='packs/'+pack+'/'+item['path']
    local=c.local(directory,relative,exists=False)
    if not local.is_file():
        raise _broken('PINNED_RESOURCE_MISSING','A fixed runtime resource is missing.',pack=pack,
                      resource=relative,expected=item['sha256'],file=str(local))
    raw=c.read(local)
    actual,size=c.digest(raw),len(raw)
    if actual!=item['sha256'] or size!=item['size']:
        raise _broken('RUNTIME_SNAPSHOT_CORRUPT','A fixed runtime resource differs from its recorded contents.',
                      pack=pack,resource=relative,expected=item['sha256'],file=str(local))
    return raw


def acquire_runtime(directory:Path, descriptor:dict, *, force_verify:bool=False,
                    previous:FixedRuntimeRead|None=None) -> FixedRuntimeRead:
    """Acquire actual metadata, every declared file, and complete membership.

    An explicitly passed owner may supply identical immutable metadata after
    its actual bytes match. It never skips current file verification. There is
    no ambient successful-read entry to restore after a failed acquisition.
    ``force_verify`` marks callers' irreversible boundaries; every acquisition
    already performs the same complete input check.
    """
    directory=c._root(Path(directory))
    if previous is not None:
        previous=_owned_runtime(directory,descriptor,previous)
    try:
        raw=c.read(c.local(directory,'snapshot.json'))
        if previous is not None and raw==previous.raw:
            payload=previous.payload
        else:
            decoded=c.decode(raw)
            actual=c.digest(raw)
            if actual!=descriptor['sha256']:
                actual=c.content_id(decoded)
            if actual!=descriptor['sha256']:
                raise _broken('RUNTIME_SNAPSHOT_CORRUPT','Fixed runtime metadata differs from its digest.',
                              expected=descriptor['sha256'],actual=actual)
            if not isinstance(decoded,dict):
                raise ValueError('fixed runtime metadata must be an object')
            payload=freeze(decoded)
    except (OSError,ValueError) as exc:
        if isinstance(exc,ProductionError):
            raise
        raise _broken('RUNTIME_SNAPSHOT_CORRUPT','Required fixed runtime metadata is missing or unreadable.',
                      expected=descriptor['sha256'],file=str(directory)) from exc
    retained={}
    for pack in payload['packs']:
        ident=pack['pack_id']
        for item in pack['files']:
            retained[(ident,item['path'])]=_verify_fixed_file(directory,ident,item)
    _require_membership(directory,payload,raw)
    return FixedRuntimeRead(directory,descriptor['sha256'],raw,payload,freeze(retained))


def read(directory:Path, descriptor:dict, *, force_verify:bool=False) -> dict:
    """Export independent editable metadata from a verified fixed runtime."""
    return mutable(acquire_runtime(directory,descriptor,force_verify=force_verify).payload)


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
    changed_directories=set()
    for pack in payload['packs']:
        for item in pack['files']:
            counts['files']+=1
            view=c.local(staged,'packs/'+pack['pack_id']+'/'+item['path'])
            stored=c.local(root,'runtime/objects/'+c.sha(item['sha256']),exists=False)
            raw=None
            if not stored.is_file():
                if raw is None:raw=c.read(view)
                if c.digest(raw)!=item['sha256'] or len(raw)!=item['size']:
                    raise _broken('RUNTIME_SNAPSHOT_CORRUPT','A captured runtime file changed before storage.',pack=pack['pack_id'],resource=item['path'],expected=item['sha256'],file=str(view))
                if not stored.parent.exists():
                    parent=stored.parent
                    while not parent.exists():
                        changed_directories.add(parent.parent)
                        parent=parent.parent
                    stored.parent.mkdir(parents=True,exist_ok=True)
                try:
                    os.link(view,stored)
                except FileExistsError:
                    pass
                except OSError:
                    try:
                        c.atomic(stored,raw)
                    except FileExistsError:
                        pass
                    else:
                        counts['stored']+=1
                        changed_directories.add(stored.parent)
                        continue
                else:
                    counts['stored']+=1
                    changed_directories.add(stored.parent)
                    continue
            if c.sha256_file(stored)!=item['sha256'] or stored.stat().st_size!=item['size']:
                raise _broken('RUNTIME_SNAPSHOT_CORRUPT','A stored runtime object differs from its content digest.',pack=pack['pack_id'],resource=item['path'],expected=item['sha256'],file=str(stored))
            if raw is None and (c.sha256_file(view)!=item['sha256'] or view.stat().st_size!=item['size']):
                raise _broken('RUNTIME_SNAPSHOT_CORRUPT','A captured runtime file changed before storage.',pack=pack['pack_id'],resource=item['path'],expected=item['sha256'],file=str(view))
            counts['reused']+=1
            if not os.path.samefile(view,stored):_alias(stored,view)
    for directory in sorted(changed_directories,key=lambda value:-len(value.parts)):
        c.fsync_dir(directory)
    return counts


def publish(root:Path, staged:Path, descriptor:dict, *, read:FixedRuntimeRead|None=None) -> Path:
    """Publish immutable content with an exclusive rename, without a Studio lock."""
    import shutil
    from operation_context import current
    target=path(root,descriptor)
    if target.exists():
        acquire_runtime(staged,descriptor,force_verify=True,previous=read)
        acquire_runtime(target,descriptor,force_verify=True)
        c.fsync_dir(target.parent)
        shutil.rmtree(staged)
        counts={'snapshot_reused':True}
    else:
        owned=acquire_runtime(staged,descriptor,previous=read)
        payload=owned.payload
        _require_membership(staged,payload,owned.raw)
        artifacts=_runtime_artifacts(staged,payload,owned.raw,staged=True)
        # Shared objects become visible outside the private stage. Their file
        # contents must be durable before a hard link exposes them there.
        artifacts.flush_files()
        counts=_store_objects(root,staged,payload)
        _require_membership(staged,payload,owned.raw)
        artifacts.flush_directories()
        created_parents=set()
        parent=target.parent
        while not parent.exists():
            created_parents.add(parent.parent)
            parent=parent.parent
        target.parent.mkdir(parents=True,exist_ok=True)
        for parent in sorted(created_parents,key=lambda value:-len(value.parts)):
            c.fsync_dir(parent)
        try:
            c.publish_directory(staged,target)
        except ProductionError as exc:
            if exc.diagnostic.code != 'OUTPUT_ALREADY_EXISTS':
                raise
            # A competing publisher may have installed the same content. Only
            # its complete, independently checked tree can replace our stage.
            acquire_runtime(staged,descriptor,force_verify=True,previous=owned)
            acquire_runtime(target,descriptor,force_verify=True)
            c.fsync_dir(target.parent)
            shutil.rmtree(staged)
            counts['snapshot_reused']=True
        else:
            counts['snapshot_reused']=False
            c.fsync_dir(target.parent)
        _require_membership(target,payload,owned.raw)
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


def bind(directory:Path, payload:dict, looked_up:set[str], *, inputs:dict|None=None) -> dict:
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
    if inputs is None:
        target=c.load(directory/'execution-target.json')
        package=c.load(directory/'package.json') if (directory/'package.json').is_file() else {}
        reading_resources=_reading_resources(directory)
    else:
        target=inputs['target']
        package=inputs['package']
        reading_resources=inputs['reading_resources']
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
    roles={name:'guide' for name in reading_resources}
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


def _run_bindings(root:Path) -> tuple[tuple[str,dict], ...]:
    """Acquire only the registered inputs needed for diagnostic affected-run lists.

    Each diagnostic reads current registrations and their bound prepared
    envelopes. Impact discovery neither replays their events nor inspects
    their media. This projection cannot certify a decision or external effect,
    and it retains no result across registration or rollback.
    """
    found=[]
    for row in store.runs(root):
        try:
            prepared=c.load(c.local(root,row['directory']+'/prepared.json'))
            if not isinstance(prepared,dict):
                continue
            envelope=dict(prepared)
            expected=envelope.pop('envelope_sha256',None)
            if (expected!=row['envelope_sha256'] or c.content_id(envelope)!=expected
                    or prepared.get('run')!=row['run_id'] or prepared.get('input_sha256')!=row['input_sha256']):
                continue
            found.append((row['run_id'],freeze(prepared['runtime_snapshot']['binding'])))
        except (OSError,ValueError,KeyError,TypeError):
            continue
    return tuple(found)


def _affects(binding:dict,match:tuple) -> bool:
    kind=match[0]
    if kind=='pack':return any(row['pack']==match[1] for row in dependencies(binding))
    if kind=='file':return any((row['pack'],row['path'])==match[1:] for row in dependencies(binding))
    if kind=='records':return any(row['id'] in match[1] for row in binding['records'])
    if kind=='resources':return any(row['name'] in match[1] for row in binding['resources'])
    return False


def _selected_resources(discovered:dict,enabled:set[str],names:set[str],order:list,read_file) -> dict:
    """Resolve only used names from acquired manifests and their candidate files."""
    from pack_cache import _precedence,_highest
    packs=[(pack,[]) for ident,pack in sorted(discovered.items()) if ident in enabled]
    outranks=_precedence(packs,order)
    found={}
    for name in sorted(names):
        candidates={pack.pack_id:pack.manifest['content']['resource_bindings'][name]
                    for pack,_ in packs if name in (pack.manifest.get('content',{}).get('resource_bindings') or {})}
        highest=_highest(sorted(candidates),outranks)
        if len(highest)>1:
            try:
                digests={c.digest(read_file(ident,candidates[ident])) for ident in highest}
            except (OSError,ValueError):
                highest=[]
            else:
                if len(digests)==1:
                    highest=highest[:1]
        selected=None if len(highest)!=1 else (highest[0],candidates[highest[0]])
        found[name]=(selected,candidates)
    return found


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
    current_files={}
    def read_file(ident,relative):
        key=(ident,relative)
        if key not in current_files:
            current_files[key]=store.stable_bytes(discovered[ident].root,relative)
        return current_files[key]
    releases={pack['pack_id']:pack['release'] for pack in payload['packs']}
    bound=dependencies(binding)
    bound_packs=sorted({row['pack'] for row in bound})
    previous_order=list(payload['selection'].get('pack_order',()))
    current_order=list(state.get('pack_order',()))
    if previous_order!=current_order:
        issue('PACK_SELECTION_CHANGED','The explicit pack precedence differs from the prepared selection.',
              match=('records',tuple(row['id'] for row in binding['records'])),
              resource='pack_order',expected=previous_order,actual=current_order)
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
                raw=read_file(ident,row['path']);actual=c.digest(raw)
            except (ValueError,OSError):
                issue('RECORD_NOT_FOUND','A file this run uses is missing from its pack.',match=('file',ident,row['path']),
                      pack=ident,resource=row['path'],file=str(live.root/row['path']),expected=row['sha256'],actual=None);continue
            if actual==row['sha256']:continue
            wanted=[item['id'] for item in binding['records'] if (item['pack'],item['path'])==(ident,row['path'])]
            try:
                document=c.decode(raw);present={item.get('id') for item in document.get('records',[]) if isinstance(item,dict)}
            except (OSError,ValueError,AttributeError):
                present=set(wanted)
            lost=[name for name in wanted if name not in present]
            if lost:
                issue('RECORD_NOT_FOUND','A record this run uses is no longer in its pack file.',match=('records',tuple(lost)),
                      pack=ident,resource=row['path'],record=lost,file=str(live.root/row['path']),expected=lost,actual=None)
            else:
                issue('PACK_CONTENT_MISMATCH','Current source bytes differ from the fixed execution resource.',match=('file',ident,row['path']),
                      pack=ident,resource=row['path'],file=str(live.root/row['path']),expected=row['sha256'],actual=actual)
    before=set(payload['selection']['enabled_packs'])
    for ident in sorted(before-enabled-set(bound_packs)):
        issue('PACK_SELECTION_CHANGED','A pack enabled at preparation is no longer enabled. This run uses nothing from it.',
              severity='warning',match=('pack',ident),pack=ident,expected='enabled',actual='disabled')
    used={row['id']:row['pack'] for row in binding['records']}
    named={row['name'] for row in binding['resources']}
    resolved=_selected_resources(discovered,enabled,named,current_order,read_file)
    for resource in binding['resources']:
        name=resource['name']
        if resource['pack'] not in enabled or resource['pack'] not in discovered:
            continue
        selected,candidates=resolved[name]
        # Newly enabled bindings keep their established refusal below, even
        # when the previous provider still wins. Resolve existing providers
        # here to detect changes that enabling checks alone cannot observe.
        if any(ident not in before for ident in candidates):
            continue
        expected=(resource['pack'],resource['path'])
        if selected!=expected:
            changed=([selected[0]] if selected is not None else
                     sorted(set(candidates)-{resource['pack']}) or [resource['pack']])
            issue('PACK_SELECTION_CHANGED','A used named resource resolves from a different source or is now ambiguous.',
                  match=('resources',(name,)),pack=changed[0],resource=[name],
                  expected={'pack':expected[0],'path':expected[1]},
                  actual=None if selected is None else {'pack':selected[0],'path':selected[1]})
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
    if code=='PACK_SELECTION_CHANGED' and details.get('resource')=='pack_order':
        return ('Restore the prepared pack order, or retarget to adopt the new precedence.',[restore,retarget])
    if (code=='PACK_SELECTION_CHANGED' and isinstance(details.get('expected'),dict)
            and details['expected'].get('pack')==pack):
        return ('Restore the pack binding that supplied this resource, or retarget to adopt the current resource.',[restore,retarget])
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


def _current_diagnostics(root:Path,descriptor:dict,read:FixedRuntimeRead,run:str|None)->list[dict]:
    """Compare current selected sources with the already acquired fixed input."""
    from pack_manager import pack_cli_command
    root=Path(root)
    settings=settings_from(descriptor['settings'])
    rows=_compare(root,read.payload,descriptor['binding'],settings)
    if rows:
        bindings=_run_bindings(root)
        for row in rows:
            row['affected_runs']=sorted(ident for ident,bound in bindings if row['match'] and _affects(bound,row['match']))
    command=pack_cli_command(settings)
    result=[]
    for row in rows:
        action,actions=_guidance(row,root=root,run=run,command=command)
        details=copy.deepcopy(row['details']);file=details.pop('file',None)
        affected=list(row['affected_runs'])
        if run is not None and run not in affected:affected=sorted([*affected,run])
        result.append(Diagnostic(row['code'],row['message'],severity=row['severity'],phase='runtime-freshness',file=file,
            required_action=action,details={'run':run,**details,'affected_runs':affected,'actions':actions}).as_dict())
    return result


def current_diagnostics(root:Path,descriptor:dict,*,run:str|None=None,force:bool=False)->list[dict]:
    """Inspect current bound sources, acquiring their fixed comparison input once.

    The caller's source-check boundary determines when a comparison is needed.
    This boundary reads current pack files and selection on every invocation;
    it does not keep a second successful-result cache beside that owner.
    """
    owned=acquire_runtime(path(root,descriptor),descriptor,force_verify=force)
    return _current_diagnostics(root,descriptor,owned,run)


def _require_current_result(result:list[dict],run:str|None) -> None:
    errors=[row for row in result if row['severity']=='error']
    if errors:
        first=errors[0]
        extra={key:value for key,value in first.items() if key not in {'code','severity','phase','file','pointer','message','required_action','blocked_checks','run'}}
        raise ProductionError(first['code'],first['message'],phase=first['phase'],file=first['file'],
                              required_action=first['required_action'],diagnostics=result,run=run,**extra)


def require_current(root:Path,descriptor:dict,*,run:str|None=None,force:bool=False)->list[dict]:
    """Stop on a freshness error; export the warnings that leave this run usable."""
    result=current_diagnostics(root,descriptor,run=run,force=force)
    _require_current_result(result,run)
    return result


def require_current_read(root:Path,descriptor:dict,*,run:str|None=None,force:bool=False,
                         previous:FixedRuntimeRead|None=None)->FixedRuntimeRead:
    """Return the verified fixed input used by this current-source boundary."""
    owned=acquire_runtime(path(root,descriptor),descriptor,force_verify=force,previous=previous)
    _require_current_result(_current_diagnostics(root,descriptor,owned,run),run)
    return owned


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


def catalogue(directory:Path,payload:dict,*,looked_up:set[str]|None=None,fingerprint:str|None=None,
              read:FixedRuntimeRead|None=None):
    """Adapt the complete fixed catalogue for explicit authoring and lookup APIs."""
    from pack_cache import RuntimePackCatalog,RuntimePackEntry,RuntimePackResource
    entries=tuple(RuntimePackEntry(kind=e['kind'],category=e['category'],record=freeze(e['record']),source_pack=e['source_pack'],
                   source_root=directory/'packs'/e['source_pack'],source_file=e['source_file']) for e in payload['entries'])
    resources=FrozenDict((name,RuntimePackResource(name=name,path=directory/'packs'/r['pack_id']/r['path'],media_type=r['media_type'],
                                                     source_pack=r['pack_id'],relative_path=r['path']))
                           for name,r in payload['resources'].items())
    if looked_up is not None:resources=_Lookups(resources,looked_up)
    assets={str(e.record['id']):[] for e in entries if e.kind!='asset' and e.record.get('id')}
    for entry in entries:
        if entry.kind=='asset':
            for ident in entry.record.get('canonical_record_ids',[]):
                if ident in assets:assets[ident].append(entry)
    fingerprint=fingerprint or c.content_id(payload)
    return RuntimePackCatalog(fingerprint,len(payload['packs']),entries,freeze(payload.get('phrases',{})),freeze(payload.get('profiles',{})),resources,
                              FrozenDict((k,tuple(v)) for k,v in assets.items()),tuple(freeze(payload.get('diagnostics',()))),
                              pack_roots=FrozenDict((pack['pack_id'],directory/'packs'/pack['pack_id']) for pack in payload['packs']),
                              resource_reader=read.read_resource if read is not None else None)


@contextlib.contextmanager
def using(directory:Path,descriptor:dict,*,binding:Path|None=None,
          read:FixedRuntimeRead|None=None,binding_inputs:dict|None=None)->Iterator[dict]:
    """Explicitly adapt a fixed input for standalone catalogue lookup APIs.

    With `binding`, the compile directory of a preparation, the block's named
    resource lookups are recorded. When the block completes, the descriptor
    gains `binding`: the model, service, guides, records and pack evidence the
    preparation used.
    """
    from catalog_retrieval import runtime
    if read is None:
        read=acquire_runtime(directory,descriptor)
    owned=_owned_runtime(directory,descriptor,read)
    payload=owned.payload
    previous=(runtime._PACK_SETTINGS,runtime._PACK_CATALOG_CACHE)
    looked_up:set[str]|None=set() if binding is not None else None
    runtime._PACK_SETTINGS=settings_from(descriptor['settings'])
    runtime._PACK_CATALOG_CACHE=catalogue(directory,payload,looked_up=looked_up,
                                        fingerprint=descriptor['sha256'],read=owned)
    try:yield payload
    finally:runtime._PACK_SETTINGS,runtime._PACK_CATALOG_CACHE=previous
    if binding is not None:
        descriptor['binding']=bind(binding,payload,looked_up,inputs=binding_inputs)
