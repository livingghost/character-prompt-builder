"""Current authoring bytes acquired for one navigation comparison."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import stat

import execution_contract as c
from private_state import assert_public_path
from production_store import stable_read


@dataclass(frozen=True)
class SourceBytes:
    content: bytes
    sha256: str


def _parts(relative: str) -> tuple[str, ...]:
    if not isinstance(relative,str) or not relative or '\\' in relative:
        raise ValueError('canonical source-relative POSIX path required')
    path=PurePosixPath(relative)
    if not path.parts or path.is_absolute() or path.as_posix()!=relative or any(part in {'.','..'} for part in path.parts):
        raise ValueError('source path must remain within its declared root')
    assert_public_path(path)
    return path.parts


def _plain(path: Path, *, directory: bool):
    info=path.lstat()
    if stat.S_ISLNK(info.st_mode):
        raise ValueError('symbolic link in source path')
    if getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400):
        return None
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise ValueError('source entry is not an ordinary '+('directory' if directory else 'file'))
    return info.st_dev,info.st_ino,stat.S_IFMT(info.st_mode)


def _acquire_root(root: Path, paths: set[str]) -> dict[str, SourceBytes | Exception]:
    """Check shared ancestry once, then each selected file through one handle.

    Shared directory identities exist only while acquisition runs; returned
    bytes and hashes belong to its read boundary. Directory identities are
    checked again before returning, so a replaced ancestor cannot leave a
    successful source set. Missing/invalid members remain individual failures.
    """
    acquired={}
    parts={}
    for relative in paths:
        try:parts[relative]=_parts(relative)
        except (ValueError,OSError) as exc:acquired[relative]=exc
    try:
        base=c._root(root)
        root_identity=_plain(base,directory=True)
    except (ValueError,OSError) as exc:
        return {relative:exc for relative in paths}
    prefixes={piece[:index] for piece in parts.values() for index in range(1,len(piece))}
    directories={():base}
    identities={():root_identity}
    redirected=set()
    for prefix in sorted(prefixes,key=lambda value:(len(value),value)):
        try:
            parent=directories[prefix[:-1]]
            if isinstance(parent,Exception):raise parent
            selected=parent/prefix[-1]
            identity=_plain(selected,directory=True)
            if identity is None or prefix[:-1] in redirected or (os.name=='nt' and prefix[-1][-1] in ' .'):
                # Preserve c.local's full containment checks for junctions,
                # trimmed Windows names and descendants of redirected paths.
                selected=c.local(base,'/'.join(prefix))
                info=selected.stat()
                if not stat.S_ISDIR(info.st_mode):raise ValueError('source entry is not a directory')
                identity=(info.st_dev,info.st_ino,stat.S_IFMT(info.st_mode))
                redirected.add(prefix)
            identities[prefix]=identity
            directories[prefix]=selected
        except (ValueError,OSError) as exc:directories[prefix]=exc
    for relative,piece in sorted(parts.items()):
        try:
            parent=directories[piece[:-1]]
            if isinstance(parent,Exception):raise parent
            selected=parent/piece[-1]
            identity=_plain(selected,directory=False)
            if identity is None or piece[:-1] in redirected or (os.name=='nt' and piece[-1][-1] in ' .'):
                selected=c.local(base,relative)
            raw=stable_read(selected,relative)
            acquired[relative]=SourceBytes(raw,c.digest(raw))
        except (ValueError,OSError) as exc:acquired[relative]=exc
    for prefix,identity in identities.items():
        try:
            if prefix in redirected:
                selected=c.local(base,'/'.join(prefix))
                info=selected.stat()
                actual=(info.st_dev,info.st_ino,stat.S_IFMT(info.st_mode))
            else:
                actual=_plain(directories[prefix],directory=True)
            if actual!=identity or (not prefix and Path(root).resolve()!=base):
                raise ValueError('source directory changed during acquisition')
        except (ValueError,OSError) as exc:
            for relative,piece in parts.items():
                if piece[:len(prefix)]==prefix:acquired[relative]=exc
    return acquired


class LiveSourceRead:
    """Own the current declared source bytes for a navigation observation.

    Consumers can read only the declared set. Another observation reads new
    bytes, without an age or revision cache. A prepared execution reads its
    saved input objects instead and does not construct this current-draft view.
    """

    def __init__(self,root:Path,skill_root:Path,dependencies):
        skill={row['path'] for row in dependencies if row['space']=='skill'}
        studio={row['path'] for row in dependencies if row['space'] not in {'skill','evidence'}}
        self._skill=_acquire_root(skill_root,skill)
        self._studio=_acquire_root(root,studio)

    @staticmethod
    def _take(values:dict,path:str) -> SourceBytes:
        try:found=values[path]
        except KeyError as exc:raise ValueError('source was not declared for this current-draft comparison: '+path) from exc
        if isinstance(found,Exception):raise found
        return found

    def skill_bytes(self,path:str) -> bytes:
        return self._take(self._skill,path).content

    def dependency(self,row:dict) -> SourceBytes:
        return self._take(self._skill if row['space']=='skill' else self._studio,row['path'])
