"""Capture the byte witnesses read while constructing a local input contract."""
from __future__ import annotations
import base64
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable
import execution_contract as c
from owned_json import freeze
from private_state import assert_public_path

class InputEvidence:
    """A content verifier uses stored bytes; an execution verifier checks current bytes."""
    def __init__(self,root:Path|None,*,snapshots:dict|None=None,live:bool=True,named_roots:dict[str,Path]|None=None,space:str="",
                 read_source:Callable[[str],bytes]|None=None):
        self.named_roots=named_roots or {};self.space=space
        self.read_source=read_source
        self.root=root;self.live=live;self.snapshots={} if snapshots is None else snapshots
        self.read_paths=set();self.locators={}
        for path,item in self.snapshots.items():
            if not isinstance(path,str):raise ValueError('input snapshot path must be a string')
            assert_public_path(path)
            c.exact(item,{'sha256','size','base64'},'input snapshot')
            raw=self._decode(item)
            if c.digest(raw)!=item['sha256'] or len(raw)!=item['size']:raise ValueError('input snapshot content mismatch')
    def qualify(self,path:str)->str:
        c.text(path,'input path')
        assert_public_path(path)
        return self.space+'/'+path if self.space and not path.startswith('@') else path
    def resolve(self,path:str)->Path:
        path=self.qualify(path)
        if path.startswith('@'):
            matches=[(name,root) for name,root in self.named_roots.items() if path.startswith(name+'/')]
            if len(matches)!=1:raise ValueError('input names no unique active source root: '+path)
            name,root=matches[0];return c.local(root,path[len(name)+1:])
        if self.root is None:raise ValueError('current input validation requires a declared studio root')
        return c.local(self.root,path)
    def at(self,parent:dict)->'InputEvidence':
        path=self.qualify(parent['path']);space=''
        if path.startswith('@pack/'):
            parts=path.split('/')
            if len(parts)<3:raise ValueError('pack input has no relative path')
            space='/'.join(parts[:2])
        elif path.startswith('@skill/'):space='@skill'
        result=InputEvidence(self.root,snapshots=self.snapshots,live=self.live,named_roots=self.named_roots,space=space,
                             read_source=self.read_source)
        result.read_paths=self.read_paths;result.locators=self.locators
        return result
    def _live(self,path:str)->bytes:
        """Read current bytes as one stable file, so a file being written is never taken as complete."""
        path=self.qualify(path)
        if path.startswith('@pack/') and self.read_source is not None:
            return self.read_source(path)
        from production_store import stable_read
        selected=self.resolve(path)
        if selected.is_symlink() or not selected.is_file():raise ValueError(f'not a regular file: {selected.name}')
        return stable_read(selected,path)
    @staticmethod
    def _decode(item:dict)->bytes:
        try:return base64.b64decode(item['base64'],validate=True)
        except (ValueError,TypeError) as exc:raise ValueError('input snapshot is not canonical base64') from exc
    def read(self,ref:Any)->bytes:
        c.exact(ref,{'path','sha256'},'input file reference');c.sha(ref['sha256'])
        path=self.qualify(ref['path'])
        if self.live:
            raw=self._live(path)
        else:
            if path not in self.snapshots:raise ValueError('recorded input snapshot is missing: '+path)
            raw=self._decode(self.snapshots[path])
        if c.digest(raw)!=ref['sha256']:raise ValueError('input reference bytes differ: '+path)
        snapshot={'sha256':ref['sha256'],'size':len(raw),'base64':base64.b64encode(raw).decode('ascii')}
        if path in self.snapshots and self.snapshots[path]!=snapshot:raise ValueError('input changed from its captured snapshot: '+path)
        self.snapshots[path]=snapshot;self.read_paths.add(path)
        return raw
    def json(self,ref:dict)->Any:return c.decode(self.read(ref))
    def select(self,path:str)->dict:
        path=self.qualify(path)
        raw=self._live(path);ref={'path':path,'sha256':c.digest(raw)};self.read(ref);return ref
    def basis(self,ref:dict)->bytes:
        c.exact(ref,{'path','sha256','locator'},'source basis');c.text(ref['locator'],'source locator')
        raw=self.read({k:ref[k] for k in ('path','sha256')})
        self.locators.setdefault(self.qualify(ref['path']),ref['locator'])
        return raw


@dataclass(frozen=True)
class _EvidenceFile:
    raw: bytes
    sha256: str
    decoded: tuple = ()


class EvidenceAcquisition(InputEvidence):
    """Acquire one operation's exact inputs before producing immutable evidence.

    This builder owns bytes and their decoded values. A path is acquired once
    in this boundary. Its finished result has no filesystem reader. Failure
    poisons the acquisition so a partial input graph cannot be published.
    """

    def __init__(self,root:Path|None,*,named_roots:dict[str,Path]|None=None,
                 read_source:Callable[[str],bytes]|None=None):
        self.root=root;self.named_roots=named_roots or {};self.space=''
        self.read_source=read_source
        self._owner=self;self._files={};self._failure=None;self._closed=False
        self.read_paths=set();self.locators={}

    def at(self,parent:dict)->'EvidenceAcquisition':
        path=self.qualify(parent['path'])
        space='/'.join(path.split('/')[:2]) if path.startswith('@pack/') else '@skill' if path.startswith('@skill/') else ''
        result=object.__new__(type(self));result.__dict__.update(self.__dict__);result.space=space
        return result

    def _acquire(self,path:str)->_EvidenceFile:
        owner=self._owner
        if owner._failure is not None:
            raise ValueError('input acquisition already failed') from owner._failure
        if owner._closed:
            raise ValueError('input acquisition is complete; consume its immutable evidence')
        if path not in owner._files:
            raw=self._live(path)
            owner._files[path]=_EvidenceFile(raw,c.digest(raw))
        return owner._files[path]

    def read(self,ref:Any)->bytes:
        try:
            c.exact(ref,{'path','sha256'},'input file reference');c.sha(ref['sha256'])
            path=self.qualify(ref['path']);item=self._acquire(path)
            if item.sha256!=ref['sha256']:
                raise ValueError('input reference bytes differ: '+path)
            self.read_paths.add(path)
            return item.raw
        except (ValueError,OSError,KeyError,TypeError) as exc:
            self._owner._failure=exc
            raise

    def basis(self,ref:dict)->bytes:
        try:
            return super().basis(ref)
        except (ValueError,OSError,KeyError,TypeError) as exc:
            self._owner._failure=exc
            raise

    def json(self,ref:dict)->Any:
        try:
            raw=self.read(ref);path=self.qualify(ref['path']);item=self._owner._files[path]
            if not item.decoded:
                item=_EvidenceFile(raw,item.sha256,(freeze(c.decode(raw)),))
                self._owner._files[path]=item
            return item.decoded[0]
        except (ValueError,OSError,KeyError,TypeError) as exc:
            self._owner._failure=exc
            raise

    def select(self,path:str)->dict:
        try:
            path=self.qualify(path);item=self._acquire(path);self.read_paths.add(path)
            return {'path':path,'sha256':item.sha256}
        except (ValueError,OSError,KeyError,TypeError) as exc:
            self._owner._failure=exc
            raise

    @property
    def bytes(self):
        return MappingProxyType({path:item.raw for path,item in self._owner._files.items()})

    @property
    def snapshots(self):
        """Export the exchange representation only at an artifact boundary."""
        return _snapshots(self._owner._files)

    def finish(self)->'EvidenceInputs':
        return EvidenceInputs(self)


def _snapshots(files)->dict:
    return {path:{'sha256':item.sha256,'size':len(item.raw),
                  'base64':base64.b64encode(item.raw).decode('ascii')}
            for path,item in files.items()}


@dataclass(frozen=True,init=False)
class EvidenceInputs:
    """Immutable exact evidence; every read resolves in the acquired graph."""

    _files: Any
    space: str
    root: Path|None
    named_roots: Any
    read_paths: frozenset
    locators: Any

    qualify=InputEvidence.qualify

    def __init__(self,acquisition:EvidenceAcquisition):
        if not isinstance(acquisition,EvidenceAcquisition):
            raise TypeError('evidence requires a completed input acquisition')
        owner=acquisition._owner
        if owner._failure is not None:
            raise ValueError('failed input acquisition cannot produce evidence') from owner._failure
        if owner._closed:
            raise ValueError('input acquisition was already consumed')
        object.__setattr__(self,'_files',MappingProxyType(dict(owner._files)))
        object.__setattr__(self,'space',acquisition.space)
        object.__setattr__(self,'root',acquisition.root)
        object.__setattr__(self,'named_roots',MappingProxyType(dict(acquisition.named_roots)))
        object.__setattr__(self,'read_paths',frozenset(acquisition.read_paths))
        object.__setattr__(self,'locators',MappingProxyType(dict(acquisition.locators)))
        owner._closed=True

    def at(self,parent:dict)->'EvidenceInputs':
        path=self.qualify(parent['path'])
        space='/'.join(path.split('/')[:2]) if path.startswith('@pack/') else '@skill' if path.startswith('@skill/') else ''
        result=object.__new__(type(self))
        for name in ('_files','root','named_roots','read_paths','locators'):
            object.__setattr__(result,name,getattr(self,name))
        object.__setattr__(result,'space',space)
        return result

    def read(self,ref:Any)->bytes:
        c.exact(ref,{'path','sha256'},'input file reference');c.sha(ref['sha256'])
        path=self.qualify(ref['path'])
        if path not in self._files:
            raise ValueError('recorded input snapshot is missing: '+path)
        item=self._files[path]
        if item.sha256!=ref['sha256']:
            raise ValueError('input reference bytes differ: '+path)
        return item.raw

    def json(self,ref:dict)->Any:
        raw=self.read(ref);item=self._files[self.qualify(ref['path'])]
        return item.decoded[0] if item.decoded else freeze(c.decode(raw))

    def select(self,path:str)->dict:
        path=self.qualify(path)
        if path not in self._files:
            raise ValueError('recorded input snapshot is missing: '+path)
        return {'path':path,'sha256':self._files[path].sha256}

    def basis(self,ref:dict)->bytes:
        c.exact(ref,{'path','sha256','locator'},'source basis');c.text(ref['locator'],'source locator')
        return self.read({key:ref[key] for key in ('path','sha256')})

    @property
    def bytes(self):
        return MappingProxyType({path:item.raw for path,item in self._files.items()})

    @property
    def snapshots(self):
        return _snapshots(self._files)
