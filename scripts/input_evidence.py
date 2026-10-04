"""Capture the byte witnesses read while constructing a local input contract."""
from __future__ import annotations
import base64
from pathlib import Path
from typing import Any
import execution_contract as c

class InputEvidence:
    """A content verifier uses stored bytes; an execution verifier checks current bytes."""
    def __init__(self,root:Path|None,*,snapshots:dict|None=None,live:bool=True,named_roots:dict[str,Path]|None=None,space:str=""):
        self.named_roots=named_roots or {};self.space=space
        self.root=root;self.live=live;self.snapshots={} if snapshots is None else snapshots
        self.read_paths=set();self.locators={}
        for path,item in self.snapshots.items():
            if not isinstance(path,str):raise ValueError('input snapshot path must be a string')
            c.exact(item,{'sha256','size','base64'},'input snapshot')
            raw=self._decode(item)
            if c.digest(raw)!=item['sha256'] or len(raw)!=item['size']:raise ValueError('input snapshot content mismatch')
    def qualify(self,path:str)->str:
        c.text(path,'input path')
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
        result=InputEvidence(self.root,snapshots=self.snapshots,live=self.live,named_roots=self.named_roots,space=space)
        result.read_paths=self.read_paths;result.locators=self.locators
        return result
    def _live(self,path:str)->bytes:
        """Read current bytes as one stable file, so a file being written is never taken as complete."""
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
