"""Explicit synthetic visual choices for tests and executable examples."""
from __future__ import annotations
import copy
import tempfile
from pathlib import Path
import execution_contract as c
from visual_continuity import file_ref

_WORK = tempfile.TemporaryDirectory(prefix='synthetic-visual-')


def fixture_root() -> Path:
    return Path(_WORK.name)


def fixture_visual(production_spec: dict, *, root: Path | None = None,
                   continuity: str = 'one-off', character_id: str | None = None,
                   studio_character: str | None = None, purpose: str = 'image') -> dict:
    """State a synthetic choice explicitly, without representing user consent."""
    root = root or fixture_root()
    path = root / 'fixture-visual-basis.txt'
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = b'Synthetic visual decisions for one declared test input. Not an author approval.\n'
    if path.exists() and path.read_bytes() != raw:
        raise ValueError('synthetic basis path belongs to another file')
    path.write_bytes(raw)
    return {'purpose':purpose, 'basis':file_ref(root, path.name, locator='whole'),
            'subjects':{item['id']:{'continuity':continuity,'character_id':character_id,
                'studio_character':studio_character, 'identity_refs':[]}
                for item in production_spec.get('subjects', [])}}


def verify(value: dict, *, package_root: Path | None = None, project: Path | None = None, **kwargs) -> dict:
    """Supply the explicit source root belonging to this synthetic fixture."""
    from verify_generation_payload import verify as verify_input
    return verify_input(value, package_root=package_root, project=project or fixture_root(), **kwargs)


def verify_package(value: dict, *, package_root: Path | None = None, project: Path | None = None) -> dict:
    return verify(value, package_root=package_root, project=project)


def emit_paste_for_target(value: dict, target: str, *, package_root: Path | None = None) -> dict:
    from verify_generation_payload import emit_paste_for_target as export
    return export(value, target, package_root=package_root, project=fixture_root())
