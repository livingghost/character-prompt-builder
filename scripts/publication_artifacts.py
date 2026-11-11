"""Producer-owned files and their immutable publication representation."""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

import execution_contract as c
from production_diagnostics import ProductionError

RESTORE_CONTENTS = ('Restore the exact bytes matching the expected digest at this path, then run the command again; '
                    'never recreate different contents.')
# A refused declaration is continued by who made it: the stored rows a set was
# loaded from, or the running operation that writes into the set or reads from it.
DECLARATION_DAMAGED = ('The stored file list of this set is not a valid declaration, and no valid copy of it is known. '
                       'Nothing is read from this set; records outside it are unaffected.')
OPERATION_CONFLICT = ('This file set refuses a file that the running operation declared, requested or staged; path names '
                      'it when one is given. Nothing is restored for this: the operation stops, and the runs already '
                      'registered are unaffected. Run the same command again. Staging that a failed preparation leaves is '
                      'listed by staging-cleanup and removed with --apply --operation once its owner operation has ended.')


class ArtifactSet:
    """One set of exact file contents, declared by the producers that write them.

    The publication manifest persists these rows. A directory walk checks
    membership; producers establish which files the publication owns.
    `damaged` is the repair reported when `rows`, a stored declaration, are
    refused; the reader that knows what holds those rows supplies it.
    """

    def __init__(self, root: Path, rows=(), *, damaged: str = DECLARATION_DAMAGED):
        self._root_spelling = Path(root).absolute()
        self.root = c._root(self._root_spelling)
        self._files: dict[str, dict] = {}
        self._repair = damaged
        seen = set()
        for row in rows:
            added = self.add_record(row)
            if added['path'] in seen:
                self._invalid('An artifact is declared twice.', path=added['path'])
            seen.add(added['path'])
        self._repair = OPERATION_CONFLICT

    def _invalid(self, message: str, **details) -> None:
        raise ProductionError('ARTIFACT_MANIFEST_CORRUPT', message, phase='integrity',
                              file=str(self.root), required_action=self._repair, **details)

    def _relative(self, path: str | Path) -> str:
        if isinstance(path, Path):
            absolute = path.absolute()
            relative = None
            for root in (self.root, self._root_spelling):
                try:
                    relative = absolute.relative_to(root).as_posix()
                    break
                except ValueError:
                    pass
            if relative is None:
                self._invalid('A producer path must belong to its artifact root.', path=str(path))
            # Preserve every child component for c.local to check. Resolving
            # the child here could turn a symbolic link into an owned target.
            path = relative
        if (not isinstance(path, str) or not path or '\\' in path or
                PurePosixPath(path).is_absolute() or '..' in path.split('/') or
                PurePosixPath(path).as_posix() != path or path == '.'):
            self._invalid('An artifact path must be a normalized relative file path.', path=str(path))
        return path

    def add_record(self, row: dict, *, replace: bool = False) -> dict:
        """Merge a producer's verified file record; conflicting ownership fails."""
        try:
            c.exact(row, {'path', 'sha256', 'size'}, 'artifact record')
            relative = self._relative(row['path'])
            c.sha(row['sha256'])
            if type(row['size']) is not int or row['size'] < 0:
                raise ValueError('artifact size must be a nonnegative integer')
        except (TypeError, ValueError) as exc:
            if isinstance(exc, ProductionError):
                raise
            self._invalid(str(exc))
        known = self._files.get(relative)
        if known is not None and known != row and not replace:
            self._invalid('Two producers declared different contents at one path.',
                          path=relative, expected=known, actual=row)
        self._files[relative] = dict(row)
        return dict(row)

    def add(self, path: str | Path, raw: bytes, *, replace: bool = False) -> dict:
        """Record the exact bytes a producer wrote or verified."""
        return self.add_record({'path': self._relative(path), 'sha256': c.digest(raw), 'size': len(raw)},
                               replace=replace)

    def write(self, path: str | Path, raw: bytes, *, replace: bool = False) -> dict:
        """Write one owned file and register its producer's bytes."""
        relative = self._relative(path)
        row = {'path': relative, 'sha256': c.digest(raw), 'size': len(raw)}
        known = self._files.get(relative)
        if known is not None and known != row and not replace:
            self._invalid('A producer tried to replace another declared content.',
                          path=relative, expected=known, actual=row)
        self._write(c.local(self.root, relative, exists=False), raw, replace=replace and known is not None)
        return self.add_record(row, replace=replace)

    def _write(self, path: Path, raw: bytes, *, replace: bool) -> None:
        c.atomic(path, raw, replace=replace)

    def files(self) -> list[dict]:
        return [dict(self._files[name]) for name in sorted(self._files)]

    def subtree(self, path: str) -> ArtifactSet:
        """The complete declared membership of one immutable companion."""
        relative = self._relative(path)
        prefix = relative + '/'
        return ArtifactSet(c.local(self.root, relative, exists=False),
                           [{**row, 'path': name[len(prefix):]} for name, row in self._files.items()
                            if name.startswith(prefix)])

    def require_membership(self, *, controls=()) -> None:
        """Check one completely owned tree and its root lifecycle controls."""
        controls = {self._relative(name) for name in controls}
        if any('/' in name for name in controls):
            self._invalid('Lifecycle controls must name direct children.')
        expected = set(self._files)
        directories = {parent.as_posix() for name in expected | controls
                       for parent in PurePosixPath(name).parents if parent.as_posix() != '.'}
        actual = set()
        unexpected = set()

        def visit(directory: Path) -> None:
            for item in sorted(directory.iterdir()):
                relative = item.relative_to(self.root).as_posix()
                if item.is_symlink() or item.is_junction():
                    unexpected.add(relative)
                elif item.is_dir():
                    if relative not in directories:
                        unexpected.add(relative + '/')
                    visit(item)
                elif item.is_file():
                    if relative not in controls or relative in expected:
                        actual.add(relative)
                else:
                    unexpected.add(relative)

        visit(c._root(self.root))
        unexpected.update(actual - expected)
        missing = expected - actual
        if unexpected or missing:
            raise ProductionError('ARTIFACT_SET_MISMATCH',
                'Stored files differ from the complete set declared by their producers.',
                phase='integrity', file=str(self.root), unexpected=sorted(unexpected), missing=sorted(missing),
                required_action='Inspect the listed paths and restore the declared contents; keep the failed staging evidence.')

    def read(self, path: str) -> bytes:
        """Read one content through its producer's committed digest and size."""
        relative = self._relative(path)
        if relative not in self._files:
            self._invalid('A requested file is outside the declared artifact set.', path=relative)
        row = self._files[relative]
        source = c.local(self.root, relative, exists=False)
        if not source.is_file():
            raise ProductionError('ARTIFACT_MISSING', 'A declared artifact is missing.',
                                  phase='integrity', file=str(source), expected=row['sha256'],
                                  required_action=RESTORE_CONTENTS)
        raw = c.read(source)
        if c.digest(raw) != row['sha256'] or len(raw) != row['size']:
            raise ProductionError('ARTIFACT_CORRUPT', 'A declared artifact differs from its committed contents.',
                                  phase='integrity', file=str(source), expected=row['sha256'], actual=c.digest(raw),
                                  required_action=RESTORE_CONTENTS)
        return raw

    def copy_file(self, path: str, destination: Path) -> Path:
        """Copy one declared content, verifying the bytes that will be written."""
        c.atomic(destination, self.read(path))
        return destination

    def copy_to(self, destination: Path) -> Path:
        """Copy a complete immutable tree from this same declared set."""
        self.require_membership()
        for name in sorted(self._files):
            self.copy_file(name, c.local(destination, name, exists=False))
        return destination


class StagedArtifacts(ArtifactSet):
    """A private artifact tree made durable at its publication boundary.

    Writes materialize complete files without syncing disposable work to disk.
    Before any part becomes public, flush_files persists the file contents.
    Before the tree's exclusive rename, flush_directories persists its nested
    directory entries from the leaves to the root. Publication then flushes
    the destination parent. A check can discard its private tree directly.
    """

    def _write(self, path: Path, raw: bytes, *, replace: bool) -> None:
        c.atomic(path, raw, replace=replace, durable=False)

    def flush_files(self) -> None:
        """Persist every declared file before publishing the tree or its links."""
        for name in sorted(self._files):
            path = c.local(self.root, name)
            if not path.is_file():
                self._invalid('A staged artifact is not a regular file.', path=name)
            # Windows requires write access when flushing file buffers. The
            # owner created these private files; opening them never truncates.
            with path.open('r+b' if os.name == 'nt' else 'rb') as stream:
                os.fsync(stream.fileno())

    def flush_directories(self, *, controls=()) -> None:
        directories = {'.'}
        for name in (*self._files, *(self._relative(name) for name in controls)):
            directories.update(parent.as_posix() for parent in PurePosixPath(name).parents)
        for name in sorted(directories, key=lambda value: (-len(PurePosixPath(value).parts), value)):
            directory = c._root(self.root) if name == '.' else c.local(self.root, name)
            c.fsync_dir(directory)
