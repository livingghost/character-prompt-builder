"""Local operation diagnostics. Logs are not approval or the production ledger.

Each public call owns a directory. Nested API stages share its context; no raw
argument vector, environment dump, HTTP dump or exception locals are retained.
A child process started during a call records that call as its parent.
"""
from __future__ import annotations
import argparse
import contextlib
import contextvars
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
import uuid
from typing import Any, Callable, Iterator, TextIO

_CURRENT: contextvars.ContextVar['Operation | None'] = contextvars.ContextVar('cpb_operation', default=None)
# A child process reads its parent operation from this variable.
PARENT_VARIABLE = 'CPB_PARENT_OPERATION'
# Read-only commands record the run they inspect as `query_run`, not `run`.
QUERY_COMMANDS = frozenset({'logs', 'logs-export', 'status'})
# production_workflow exits 3 while an execution waits for authority or configuration.
WAITING_EXIT = 3

# A name is split into words, so `max_tokens` or `TOKENIZERS_PARALLELISM` is not a credential name.
_NAME_WORDS = re.compile(r'[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+')
_SECRET_WORD = re.compile(r'.*token|.*(?:secret|password|passwd|passphrase|credential|cookie|apikey)s?|authorization')
_KEY_QUALIFIERS = frozenset({'api', 'access', 'private', 'secret', 'session', 'signing', 'client'})
# These are payload contents, not useful diagnostic references. They stay in their
# formal source artifacts rather than being copied into operation logs.
_PRIVATE_KEYS = re.compile(
    r'^(?:prompt|positivePrompt|negativePrompt|composition_prompt|prompt_expression|negative|positive|'
    r'instructions|document|definition|terms|rendition|lines|chunk|base64|imageData|response_body|'
    r'raw_body|text|query|description)$', re.I)
# Short, boolean and numeric values would redact ordinary words and numbers everywhere.
_MINIMUM_SECRET = 8
_PLAIN_VALUE = re.compile(r'(?i)true|false|yes|no|on|off|none|null|[-+]?[0-9][0-9_.,]*')
_BEARER = re.compile(r'(?i)(Bearer\s+)[^\s"\'<>]+')
_SIGNED_QUERY = re.compile(r'(?i)([?&](?:signature|sig|token|key|x-amz-signature|x-amz-credential|credential|x-goog-signature)=)[^\s&#"\']+')
_SAFE_ARGS = {'command','root','studio_root','run','from_run','task','file','out','out_dir','candidate',
              'character','slot','model','service','parameters_file','settings_file','changes_file','state_file','cache_dir',
              'managed_root','pack_root','pack','directory','grant','reservation','operation','budget','failed',
              'prepare','seed','count','send','help','profile','route','features','feature','production_run','production_root','studio','before','apply'}
_LOG_FILES = frozenset({'operation.json', 'events.jsonl', 'stdout.log', 'stderr.log', 'artifacts.json'})
_STREAM_FILES = ('events.jsonl', 'stdout.log', 'stderr.log')
_CONSOLE_FILES = frozenset({'stdout.log', 'stderr.log'})
# A metadata rewrite interrupted by a crash leaves only this owned temporary file.
_PARTIAL_FILES = frozenset({'.operation.json.tmp', '.artifacts.json.tmp'})
# Output written before the Studio is known, kept to rebuild the record there.
_EARLY_LIMIT = 1 << 20
# Link kinds that collect every value an operation touches.
_LIST_LINKS = {'candidate': 'candidates', 'reservation': 'reservations'}


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def secret_name(key: str) -> bool:
    """True for a field or variable name that holds a credential."""
    words = [word.lower() for word in _NAME_WORDS.findall(key)]
    return (any(_SECRET_WORD.fullmatch(word) for word in words)
            or any(first in _KEY_QUALIFIERS and second == 'key' for first, second in zip(words, words[1:])))


def _sensitive_key(key: str) -> bool:
    return secret_name(key) or bool(_PRIVATE_KEYS.match(key))


def _secret_value(value: Any) -> bool:
    return isinstance(value, str) and len(value) >= _MINIMUM_SECRET and not _PLAIN_VALUE.fullmatch(value.strip())


def _ordered(values) -> tuple[str, ...]:
    return tuple(sorted(set(values), key=len, reverse=True))


def known_secrets(extra: tuple[str, ...] = ()) -> tuple[str, ...]:
    values = {v for k, v in os.environ.items() if secret_name(k)} | set(extra)
    values |= {v.strip() for v in values}
    return _ordered(v for v in values if _secret_value(v))


def scrub(text: str, secrets: tuple[str, ...] = ()) -> str:
    for value in secrets:
        text = text.replace(value, '[REDACTED]')
    text = _BEARER.sub(r'\1[REDACTED]', text)
    return _SIGNED_QUERY.sub(r'\1[REDACTED]', text)


def safe_value(value: Any, *, secrets: tuple[str, ...] = (), key: str = '') -> Any:
    if _sensitive_key(key):
        return '[REDACTED]' if secret_name(key) else '[PAYLOAD OMITTED; SEE FORMAL ARTIFACT]'
    if isinstance(value, dict):
        return {str(k): safe_value(v, secrets=secrets, key=str(k)) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [safe_value(v, secrets=secrets) for v in value]
    if isinstance(value, Path):
        value = str(value)
    return scrub(value, secrets) if isinstance(value, str) else value


class RedactingWriter:
    """Bounded redaction of text and JSON values across arbitrary write boundaries.

    Sensitive JSON subtrees are replaced with a string, including array, object,
    scalar and escaped-key forms. Raw authorization tokens are suppressed until
    their delimiter instead of exposing the tail of a long token. Each write is
    scanned with compiled expressions that jump to the next significant character.
    """
    _auth_prefix = re.compile(
        r'(?i)(?:Bearer\s+|[?&](?:signature|sig|token|key|x-amz-signature|'
        r'x-amz-credential|credential|x-goog-signature)=)')
    _auth_end = re.compile(r"""[\s&#"'<>]""")
    _string_stop = re.compile(r'["\\]')
    _plain_stop = re.compile(r'[":]')
    _nonspace = re.compile(r'\S')
    _scalar_end = re.compile(r'[\s,}\]]')
    _container_stop = re.compile(r'["\[\]{}]')

    def __init__(self, emit: Callable[[str], None], secrets: tuple[str, ...]):
        self.emit = emit
        self.secrets = _ordered(secrets)
        self.pending = ''
        self.keep = max([len(s) for s in secrets] + [512])
        self.string = False
        self.escape = False
        self.token = ''
        self.long_token = False
        self.last_string = ''
        self.after_key: str | None = None
        self.suppression: str | None = None
        self.depth = 0
        self.nested_string = False
        self.nested_escape = False
        self.auth_tail = False

    def add_secrets(self, values: tuple[str, ...]) -> None:
        self.secrets = _ordered((*self.secrets, *values))
        self.keep = max([self.keep] + [len(v) for v in values])

    def _plain(self, text: str, *, final: bool = False) -> None:
        if self.auth_tail:
            end = self._auth_end.search(text)
            if end is None:
                return
            text = text[end.start():]
            self.auth_tail = False
        self.pending += text
        # Replace raw token spans before selecting a safe streaming boundary.
        position = 0
        while match := self._auth_prefix.search(self.pending, position):
            start = match.end()
            end = self._auth_end.search(self.pending, start)
            if end is None:
                if start == len(self.pending) and not final:
                    break
                self.pending = self.pending[:start] + '[REDACTED]'
                self.auth_tail = not final
                break
            self.pending = self.pending[:start] + '[REDACTED]' + self.pending[end.start():]
            position = start + len('[REDACTED]') + 1
        if not final and len(self.pending) <= self.keep * 2:
            return
        end = len(self.pending) if final else len(self.pending) - self.keep
        for secret in self.secrets:
            start = self.pending.find(secret)
            while start >= 0:
                if start < end < start + len(secret):
                    end = start
                start = self.pending.find(secret, start + 1)
        if end:
            raw = self.pending[:end]
            for secret in self.secrets:
                raw = raw.replace(secret, '[REDACTED]')
            self.emit(raw)
            self.pending = self.pending[end:]

    def _token(self, segment: str) -> None:
        room = 512 - len(self.token)
        if room > 0:
            self.token += segment[:room]
        if len(segment) > room:
            self.long_token = True

    def _copy_string(self, value: str, index: int, output: list[str]) -> int:
        if self.escape:
            char = value[index]
            output.append(char)
            self._token(char)
            self.escape = False
            return index + 1
        found = self._string_stop.search(value, index)
        stop = len(value) if found is None else found.end()
        segment = value[index:stop]
        output.append(segment)
        self._token(segment)
        if found is None:
            return stop
        if found.group() == '\\':
            self.escape = True
        else:
            self.string = False
            try:
                self.last_string = 'credential' if self.long_token else json.loads('"' + self.token)
            except (ValueError, TypeError):
                self.last_string = 'credential'
            self.token = ''
            self.long_token = False
        return stop

    def _skip_string(self, value: str, index: int) -> int:
        while index < len(value):
            if self.nested_escape:
                self.nested_escape = False
                index += 1
                continue
            found = self._string_stop.search(value, index)
            if found is None:
                return len(value)
            index = found.end()
            if found.group() == '\\':
                self.nested_escape = True
            else:
                if self.suppression == 'string':
                    self.suppression = None
                else:
                    self.nested_string = False
                return index
        return index

    def write(self, value: str) -> None:
        output: list[str] = []
        index, end = 0, len(value)
        while index < end:
            if self.suppression == 'scalar':
                found = self._scalar_end.search(value, index)
                if found is None:
                    break
                # The delimiter itself belongs to the surrounding document.
                self.suppression = None
                index = found.start()
            elif self.suppression == 'string' or (self.suppression == 'container' and self.nested_string):
                index = self._skip_string(value, index)
            elif self.suppression == 'container':
                found = self._container_stop.search(value, index)
                if found is None:
                    break
                index = found.end()
                char = found.group()
                if char == '"':
                    self.nested_string = True
                elif char in '[{':
                    self.depth += 1
                else:
                    self.depth -= 1
                    if self.depth == 0:
                        self.suppression = None
            elif self.string:
                index = self._copy_string(value, index, output)
            elif self.after_key is not None:
                found = self._nonspace.search(value, index)
                if found is None:
                    output.append(value[index:])
                    break
                output.append(value[index:found.start()])
                char = found.group()
                index = found.end()
                key, self.after_key = self.after_key, None
                if _sensitive_key(key):
                    output.append('"[REDACTED]"')
                    self.nested_escape = False
                    self.nested_string = False
                    self.depth = 1
                    self.suppression = 'string' if char == '"' else 'container' if char in '[{' else 'scalar'
                else:
                    output.append(char)
                    self.string = char == '"'
            else:
                found = self._plain_stop.search(value, index)
                if found is None:
                    output.append(value[index:])
                    break
                output.append(value[index:found.end()])
                index = found.end()
                if found.group() == '"':
                    self.string = True
                else:
                    self.after_key = self.last_string
        self._plain(''.join(output))

    def flush(self, *, final: bool = False) -> None:
        if final:
            # End an unterminated raw token without dropping the pending prefix.
            self.auth_tail = False
            self._plain('', final=True)


def _replace(source: Path, target: Path) -> None:
    # A concurrent reader on Windows briefly holds the old file open.
    for attempt in range(20):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if os.name != 'nt' or attempt == 19:
                raise
            time.sleep(0.01)


def _sync_directory(path: Path) -> None:
    if os.name == 'posix':
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _exit_code(exc: SystemExit) -> int:
    if exc.code is None:
        return 0
    return exc.code if isinstance(exc.code, int) else 1


def _failure_name(exc: BaseException) -> str:
    name = type(exc).__name__
    number = getattr(exc, 'errno', None)
    return f'{name}:{errno.errorcode[number]}' if number in errno.errorcode else name


class Operation:
    def __init__(self, command: str, *, parent: str | None = None):
        self.id = str(uuid.uuid4())
        self.command = command
        self.parent = parent
        self.secrets = known_secrets()
        self.started = time.monotonic()
        self.closed = False
        self.failures: list[str] = []
        self.artifacts: dict[str, dict] = {}
        self.links: dict[str, Any] = {}
        # The argument or validation diagnostic that ends the call, if any.
        self.outcome: dict | None = None
        self._identities: dict[str, tuple[int, int]] = {}
        self._artifacts_dirty = False
        self._streams: dict[str, TextIO] = {}
        self._unsynced: set[str] = set()
        self._redactors: list[RedactingWriter] = []
        self._warned = False
        self._settled = False
        self._early: dict[str, list[str]] | None = {name: [] for name in _STREAM_FILES}
        self._early_size = 0
        self.path = _configuration_home()/'logs/operations'/datetime.now(timezone.utc).date().isoformat()/self.id
        self.metadata = {'operation_id': self.id, 'parent_operation': parent, 'command': command,
                         'created_at': timestamp(), 'pid': os.getpid(), 'arguments': {}, 'context': {}}
        self._start()

    def _warn(self) -> None:
        if self._warned:
            return
        self._warned = True
        try:
            sys.__stderr__.write('LOG_WRITE_FAILED: operation diagnostics are incomplete; inspect filesystem availability.\n')
        except Exception:
            pass

    def _failure(self, exc: BaseException) -> None:
        name = _failure_name(exc)
        if name not in self.failures:
            self.failures.append(name)
        # Before arguments are parsed the record may still move into a Studio.
        if self._settled:
            self._warn()

    def _settle(self) -> None:
        if not self._settled:
            self._settled = True
            if self.failures:
                self._warn()

    def _remember(self, name: str, raw: str) -> None:
        if self._early is None or not raw:
            return
        self._early_size += len(raw)
        if self._early_size > _EARLY_LIMIT:
            self._early = None
        else:
            self._early[name].append(raw)

    def _store(self, name: str, raw: str, *, append: bool) -> None:
        if append:
            stream = self._streams.get(name)
            if stream is None:
                self.path.mkdir(parents=True, exist_ok=True, mode=0o700)
                stream = self._streams[name] = (self.path/name).open('a', encoding='utf-8', newline='')
            stream.write(raw)
            stream.flush()
            self._unsynced.add(name)
        else:
            self.path.mkdir(parents=True, exist_ok=True, mode=0o700)
            # The previous whole file stays readable until the new one replaces it.
            temporary = self.path/('.' + name + '.tmp')
            try:
                with temporary.open('w', encoding='utf-8', newline='') as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                _replace(temporary, self.path/name)
            except BaseException:
                with contextlib.suppress(OSError):
                    temporary.unlink(missing_ok=True)
                raise

    def _close(self, name: str) -> None:
        stream = self._streams.pop(name, None)
        self._unsynced.discard(name)
        if stream is not None:
            try:
                stream.close()
            except OSError as exc:
                self._failure(exc)

    def _write(self, name: str, raw: str, *, append: bool = False) -> None:
        if append:
            self._remember(name, raw)
        try:
            self._store(name, raw, append=append)
        except OSError as exc:
            if append:
                self._close(name)
            self._failure(exc)

    def sync(self) -> None:
        """Flush appended diagnostics to disk; called at stage boundaries and at exit."""
        for name in sorted(self._unsynced):
            stream = self._streams.get(name)
            try:
                if stream is not None:
                    os.fsync(stream.fileno())
            except OSError as exc:
                self._close(name)
                self._failure(exc)
        self._unsynced.clear()

    def json(self, name: str, value: Any) -> None:
        self._write(name, json.dumps(safe_value(value, secrets=self.secrets), ensure_ascii=False, sort_keys=True, default=str)+'\n')

    def _start(self) -> None:
        self.json('operation.json', self.metadata)
        self.json('artifacts.json', [])
        self._write('stdout.log', '', append=True); self._write('stderr.log', '', append=True)
        self.event('started')

    def event(self, event_name: str, /, **facts: Any) -> None:
        # Domain facts may themselves contain a kind/event. They must not collide
        # with the call signature or overwrite the operation's event envelope.
        value = {**safe_value(facts, secrets=self.secrets), 'event': event_name, 'at': timestamp()}
        self._write('events.jsonl', json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)+'\n', append=True)

    def register_secret(self, value: str) -> None:
        values = {value, value.strip()} if isinstance(value, str) else set()
        added = tuple(v for v in values if _secret_value(v) and v not in self.secrets)
        if added:
            self.secrets = _ordered((*self.secrets, *added))
            for writer in self._redactors:
                writer.add_secrets(added)

    def _relocate(self, target: Path) -> None:
        """Move the record into the Studio, rebuilding it there if the configuration directory failed."""
        if self.path == target:
            return
        for name in list(self._streams):
            self._close(name)
        source = self.path
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if self.failures and self._early is not None:
                lost, self.failures = self.failures, []
                self.path = target
                self.json('artifacts.json', list(self.artifacts.values()))
                for name in _STREAM_FILES:
                    self._store(name, ''.join(self._early[name]), append=True)
                self.event('user_log_unavailable', phase='arguments', log_failures=lost)
                shutil.rmtree(source, ignore_errors=True)
            elif source.exists():
                shutil.move(str(source), str(target))
                self.path = target
            else:
                self.path = target
        except OSError as exc:
            self._failure(exc)

    def arguments(self, namespace: argparse.Namespace) -> None:
        values = vars(namespace)
        self.metadata['arguments'] = {k: safe_value(v, secrets=self.secrets, key=k) if k in _SAFE_ARGS else '[VALUE OMITTED]'
                                      for k, v in values.items()}
        query = values.get('command') in QUERY_COMMANDS
        for key in ('run','task','candidate','grant','reservation'):
            if values.get(key) is not None:
                self._link('query_run' if query and key == 'run' else key, safe_value(values[key], secrets=self.secrets))
        # Explicit studio roots name a Studio itself; --studio also accepts a
        # directory inside a Studio, as the public Studio/dispatch interfaces do.
        root = None
        for key in ('production_root', 'root', 'studio_root', 'studio'):
            selected = values.get(key)
            if not selected:
                continue
            location = Path(selected).resolve()
            candidates = (location, *location.parents) if key == 'studio' else (location,)
            root = next((p for p in candidates if (p/'studio.json').is_file()), None)
            if root is not None:
                break
        # Merely naming an output directory does not create a Studio.
        if root is not None:
            self._relocate(root/'logs/operations'/self.path.parent.name/self.id)
            self.metadata['context']['studio'] = str(root)
        self._early = None
        self._settle()
        self.json('operation.json', self.metadata)
        self.event('arguments_parsed')

    def _link(self, kind: str, value: Any) -> bool:
        if value is None:
            return False
        context = self.metadata['context']
        plural = _LIST_LINKS.get(kind)
        if plural is not None:
            values = context.setdefault(plural, [])
            if value in values:
                return False
            values.append(value)
            self.links[plural] = values
            return True
        if context.get(kind) == value:
            return False
        context[kind] = self.links[kind] = value
        return True

    def link(self, **facts: Any) -> None:
        """Associate the operation with tasks, runs, grants, reservations and candidates.

        `candidate` and `reservation` accumulate lists; other kinds hold one value.
        """
        changed = False
        for kind, value in facts.items():
            changed = self._link(kind, safe_value(value, secrets=self.secrets)) or changed
        if changed:
            self.json('operation.json', self.metadata)

    def artifact(self, path: Path, *, content_sha256: str | None = None, size: int | None = None) -> None:
        try:
            path = Path(path)
            if self.path in path.parents or path.is_symlink() or not path.is_file():
                return
            info = path.stat()
            if content_sha256 is None:
                with path.open('rb') as source:
                    content_sha256 = hashlib.file_digest(source, 'sha256').hexdigest()
            self.artifacts[str(path)] = {'path': str(path), 'sha256': content_sha256,
                                         'size': info.st_size if size is None else size}
            self._identities[str(path)] = (info.st_size, info.st_mtime_ns)
            # Batched at stage boundaries, before irreversible I/O, and at exit.
            # Rewriting the whole index for every runtime file is quadratic.
            self._artifacts_dirty = True
        except OSError as exc:
            self._failure(exc)

    def relocate_artifacts(self, old: Path, new: Path) -> None:
        """Point artifacts registered below `old` at the same files below `new`."""
        old, new = Path(old).absolute(), Path(new).absolute()
        moved: dict[str, dict] = {}
        identities: dict[str, tuple[int, int]] = {}
        for key, entry in self.artifacts.items():
            try:
                target = str(new / Path(entry['path']).relative_to(old))
            except ValueError:
                target = key
            moved[target] = {**entry, 'path': target}
            if key in self._identities:
                identities[target] = self._identities[key]
        self.artifacts, self._identities = moved, identities
        self._artifacts_dirty = True

    def _reconcile_artifacts(self) -> None:
        """Describe registered files as they are at exit: removed ones leave the index."""
        withdrawn = []
        for key, entry in list(self.artifacts.items()):
            path = Path(entry['path'])
            try:
                if path.is_symlink() or not path.is_file():
                    raise FileNotFoundError(key)
                info = path.stat()
                if (info.st_size, info.st_mtime_ns) != self._identities.get(key):
                    with path.open('rb') as source:
                        entry.update(sha256=hashlib.file_digest(source, 'sha256').hexdigest(), size=info.st_size)
                    self._identities[key] = (info.st_size, info.st_mtime_ns)
            except FileNotFoundError:
                withdrawn.append(entry['path'])
                del self.artifacts[key]
            except OSError:
                continue
        if withdrawn:
            self.event('artifacts_withdrawn', phase='cli', paths=withdrawn)

    def flush_artifacts(self) -> None:
        if self._artifacts_dirty:
            self.json('artifacts.json', list(self.artifacts.values()))
            self._artifacts_dirty = False

    def durable(self) -> None:
        self._settle()
        self.flush_artifacts()
        self.event('durability_check')
        self.sync()
        try:
            _sync_directory(self.path)
        except OSError as exc:
            self._failure(exc)
        if self.failures:
            from production_diagnostics import ProductionError
            raise ProductionError('LOG_WRITE_FAILED', 'Operation record cannot be saved before an irreversible effect.',
                                  phase='before-send', required_action='Restore durable storage before starting an external effect.')

    def finish(self, code: int, *, error: BaseException | None = None) -> None:
        self._settle()
        self._reconcile_artifacts()
        self.json('artifacts.json', list(self.artifacts.values()))
        self._artifacts_dirty = False
        details: dict[str, Any] = {}
        if error is not None and not isinstance(error, SystemExit):
            from production_diagnostics import from_exception
            details['diagnostic'] = from_exception(error, phase='cli')
        elif code and self.outcome is not None:
            details['diagnostic'] = self.outcome
        self.event('completed', exit_code=code, duration_seconds=time.monotonic()-self.started,
                   complete=not self.failures, log_failures=self.failures, **details)
        self.sync()
        for name in list(self._streams):
            self._close(name)
        try:
            _sync_directory(self.path)
        except OSError:
            pass
        self.closed = True


class ArgumentParser(argparse.ArgumentParser):
    def parse_args(self, args=None, namespace=None):
        prior=getattr(self,'_parsing_arguments',False)
        self._parsing_arguments=True
        try:
            result = super().parse_args(args, namespace)
        finally:
            self._parsing_arguments=prior
        operation = _CURRENT.get()
        if operation:
            operation.arguments(result)
        return result

    def parse_known_args(self, args=None, namespace=None):
        prior=getattr(self,'_parsing_arguments',False)
        self._parsing_arguments=True
        try:
            return super().parse_known_args(args,namespace)
        finally:
            self._parsing_arguments=prior

    def error(self, message):
        from production_diagnostics import Diagnostic
        operation = _CURRENT.get()
        if operation and getattr(self,'_parsing_arguments',False):
            # argparse can echo unknown values. Keep only a conservative message.
            operation.outcome = Diagnostic('INPUT_ARGUMENT_INVALID', 'Arguments do not match the command interface; consult --help.',
                                           phase='arguments').as_dict()
            operation.event('argument_error', code='INPUT_ARGUMENT_INVALID', phase='arguments',
                            message='Arguments do not match the command interface; consult --help.')
            names = sorted({option for action in self._actions for option in action.option_strings})
            mentioned = [name for name in names if name in message]
            category = 'missing required arguments' if 'required' in message else 'invalid arguments'
            message = category + (': ' + ', '.join(mentioned) if mentioned else '') + '; consult --help.'
        elif operation:
            # Validators call parser.error after parsing as a CLI diagnostic.
            # Preserve their actionable field/path information, not raw argv.
            message=scrub(str(message),operation.secrets)
            operation.outcome = Diagnostic('INPUT_CONSISTENCY_ERROR', message, phase='validation').as_dict()
            operation.event('validation_error',code='INPUT_CONSISTENCY_ERROR',phase='validation',message=message)
        super().error(message)


class _Tee:
    def __init__(self, original, operation: Operation, name: str):
        self.original = original
        self.operation = operation
        self.redactor = RedactingWriter(lambda value: operation._write(name, value, append=True), operation.secrets)
        operation._redactors.append(self.redactor)
    def write(self, value):
        result = self.original.write(value)
        self.redactor.write(value)
        return result
    def flush(self):
        self.original.flush()
        self.redactor.flush()
    def __getattr__(self, name):
        return getattr(self.original, name)


def current() -> Operation | None:
    return _CURRENT.get()


def current_operation_id() -> str | None:
    operation = current()
    return operation.id if operation is not None else None


def register_secret(value: str) -> None:
    """Redact a credential the running operation has read, in every later log write."""
    operation = current()
    if operation is not None:
        operation.register_secret(value)


def relocate_artifacts(old: Path, new: Path) -> None:
    """Point the running operation's artifacts from a staging directory to its published place."""
    operation = current()
    if operation is not None:
        operation.relocate_artifacts(old, new)


def _inherited_parent() -> str | None:
    value = os.environ.get(PARENT_VARIABLE, '')
    try:
        return str(uuid.UUID(value)) if value else None
    except ValueError:
        return None


@contextlib.contextmanager
def stage(name: str, **facts: Any) -> Iterator[None]:
    operation = current()
    start = time.monotonic()
    if operation: operation.event('stage_started', phase=name, **facts)
    try:
        yield
    except SystemExit as exc:
        # Help and argument exits end the call; they are not stage failures.
        if operation:
            code = _exit_code(exc)
            if code:
                operation.event('stage_exited', phase=name, duration_seconds=time.monotonic()-start, exit_code=code)
            else:
                operation.event('stage_completed', phase=name, duration_seconds=time.monotonic()-start)
            operation.sync()
        raise
    except KeyboardInterrupt:
        if operation:
            operation.event('stage_cancelled', phase=name, duration_seconds=time.monotonic()-start)
            operation.sync()
        raise
    except BaseException as exc:
        if operation:
            from production_diagnostics import from_exception
            operation.event('stage_failed', phase=name, duration_seconds=time.monotonic()-start,
                            diagnostic=from_exception(exc, phase=name))
            operation.sync()
        raise
    else:
        if operation:
            operation.flush_artifacts()
            operation.event('stage_completed', phase=name, duration_seconds=time.monotonic()-start)
            operation.sync()


def run_cli(function: Callable[[], int | None]) -> int:
    if current() is not None:
        return int(function() or 0)
    operation = Operation(Path(sys.argv[0]).name, parent=_inherited_parent())
    token = _CURRENT.set(operation)
    inherited = os.environ.get(PARENT_VARIABLE)
    os.environ[PARENT_VARIABLE] = operation.id
    out, err = _Tee(sys.stdout, operation, 'stdout.log'), _Tee(sys.stderr, operation, 'stderr.log')
    code = 1
    error: BaseException | None = None
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with stage('command'):
                code = int(function() or 0)
    except SystemExit as exc:
        code = _exit_code(exc)
        if not isinstance(exc.code, (int, type(None))):
            # SystemExit(text) ordinarily prints its text at the interpreter
            # boundary. This wrapper owns that boundary, including redaction.
            err.write('error: ' + scrub(str(exc.code), operation.secrets) + '\n')
    except KeyboardInterrupt as exc:
        error, code = exc, 130
        operation.event('cancelled', phase='cli')
    except Exception as exc:
        error = exc
        from production_diagnostics import ProductionError, from_exception
        diagnostic = safe_value(from_exception(exc, phase='cli'), secrets=operation.secrets)
        out.write(json.dumps({'ok': False, 'diagnostics': [diagnostic]}, ensure_ascii=False) + '\n')
        err.write('error: ' + str(diagnostic['message']) + '\n')
        if isinstance(exc, (ValueError, OSError)) and not isinstance(exc, ProductionError):
            code = 2
    finally:
        if inherited is None:
            os.environ.pop(PARENT_VARIABLE, None)
        else:
            os.environ[PARENT_VARIABLE] = inherited
        out.redactor.flush(final=True); err.redactor.flush(final=True)
        operation.finish(code, error=error)
        _CURRENT.reset(token)
    return code


def _configuration_home() -> Path:
    """The configuration directory pack_manager defines, which holds the logs of an operation outside a Studio."""
    import pack_manager
    return pack_manager._user_data_home()


def _log_base(root: Path | None) -> Path:
    import execution_contract as c
    from production_diagnostics import ProductionError
    owner = Path(root) if root is not None else _configuration_home()
    try:
        return c.local(owner, 'logs/operations', exists=False)
    except (OSError, ValueError) as exc:
        raise ProductionError('LOG_PATH_UNSAFE', 'The diagnostic tree is not an owned regular directory.',
                              phase='logs', file=str(owner / 'logs/operations')) from exc


def _log_folders(root: Path | None):
    import execution_contract as c
    base = _log_base(root)
    if not base.exists():
        return
    for day in sorted(base.iterdir()):
        if day.is_symlink() or not day.is_dir():
            continue
        for folder in sorted(day.iterdir()):
            if not folder.is_dir() or folder.is_symlink():
                continue
            # Validate ancestors before opening any metadata.
            c.local(base, folder.relative_to(base).as_posix())
            yield folder


def _read_operation(folder: Path) -> dict:
    import execution_contract as c
    metadata = c.load(c.local(folder, 'operation.json'))
    if (not isinstance(metadata, dict) or metadata.get('operation_id') != folder.name
            or not isinstance(metadata.get('context'), dict)):
        raise ValueError('diagnostic owner metadata differs from its directory')
    last = _operation_last_event(folder)
    complete = bool(last and last.get('event') == 'completed')
    return {'operation_id': folder.name, 'path': str(folder), 'metadata': metadata,
            'complete': complete, 'exit_code': last.get('exit_code') if complete else None,
            'log_complete': last.get('complete', False) if complete else False}


def _failed(row: dict) -> bool:
    return not row['complete'] or not row['log_complete'] or row['exit_code'] not in {0, WAITING_EXIT}


def _secrets() -> tuple[str, ...]:
    active = current()
    return known_secrets(active.secrets if active is not None else ())


def list_operations(root: Path | None = None, *, run: str | None = None, failed: bool = False,
                    operation_id: str | None = None) -> list[dict]:
    """List diagnostics of a Studio, or of the configuration directory when `root` is None.

    `run` selects operations of that run; queries that only inspected it are left out.
    """
    output = []
    active = current()
    secrets = _secrets()
    try:
        for folder in _log_folders(root):
            if (active and folder.name == active.id) or (operation_id and folder.name != operation_id):
                continue
            try:
                row = _read_operation(folder)
                if run and row['metadata']['context'].get('run') != run:
                    continue
                if not failed or _failed(row):
                    output.append(safe_value(row, secrets=secrets))
            except (OSError, ValueError, TypeError, KeyError) as exc:
                output.append({'operation_id': folder.name, 'path': str(folder), 'complete': False,
                               'diagnostic': type(exc).__name__})
    except (OSError, ValueError) as exc:
        # Read-only state inspection remains usable even if the diagnostic tree is broken.
        output.append({'operation_id': None, 'complete': False, 'log_complete': False,
                       'diagnostic': getattr(getattr(exc, 'diagnostic', None), 'code', type(exc).__name__)})
    return output



def _operation_last_event(folder: Path) -> dict | None:
    last = None
    import execution_contract as c
    with c.local(folder, 'events.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            if line.strip():
                if not line.endswith('\n'):
                    raise ValueError('diagnostic event has an incomplete final line')
                last = json.loads(line)
                if not isinstance(last, dict):
                    raise ValueError('diagnostic event must be an object')
    return last


def _process_alive(pid: Any) -> bool:
    """True unless the recorded process has certainly ended on this computer."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return True
    if pid == os.getpid():
        return True
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() != 87  # ERROR_INVALID_PARAMETER: no such process
        try:
            status = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(status)):
                return True
            return status.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _run_has_unresolved_external_effect(root: Path, run: str) -> bool:
    """Conservatively protect diagnostics while an external outcome is unresolved.

    A reservation is resolved once it is settled, or released because every
    step it started was evidenced as rejected or not executed. A send the
    author evidenced as not executed resolves the claim it belongs to.
    """
    try:
        import production_workflow as workflow
        import reservation_lifecycle as accounting
        _, prepared, _, rows = workflow.load_run(root, run)
        claims = [row for row in rows if row['event'] in {'dispatch-claim', 'external-claim'}]
        if not claims:
            return False
        outcomes = [row for row in rows if row['event'] == 'execution-outcome']
        if (outcomes and outcomes[-1]['data'].get('submission') == 'not_executed'
                and outcomes[-1]['data'].get('claim') == claims[-1]['sha256']):
            return False
        states = accounting.derive(rows, prepared, run)
        resolved = {'settled', 'released'}
        if any(state.get('steps') and state.get('status') not in resolved for state in states.values()):
            return True
        external = [row for row in claims if row['event'] == 'external-claim']
        if external:
            tokens = {token for row in external for token in row['data']['authorizations']}
            owned = [state for state in states.values() if state.get('authorization_sha256') in tokens]
            if len(owned) != len(tokens) or any(state.get('status') not in resolved for state in owned):
                return True
        # A previous timeout is not the current truth after formal capture and
        # settlement. Keep uncertain claims protected until their real evidence
        # exists; do not infer resolution merely from a closed CLI operation.
        if outcomes and outcomes[-1]['data'].get('submission') == 'outcome_unknown':
            return not (states and all(state.get('status') in resolved for state in states.values()))
        return False
    except Exception:
        # A damaged formal run is exactly when its diagnostics are most valuable.
        return True


def _cleanup_assessment(root: Path | None, folder: Path, *, cutoff=None) -> dict:
    import execution_contract as c
    row = {'operation_id': folder.name, 'path': str(folder), 'eligible': False}
    try:
        base = _log_base(root)
        c.local(base, folder.relative_to(base).as_posix())
        children = list(folder.iterdir())
        names = {p.name for p in children}
        if not names <= _LOG_FILES | _PARTIAL_FILES or any(p.is_symlink() or not p.is_file() for p in children):
            row['reason'] = 'unowned-or-missing-content'
            return row
        state = _read_operation(folder)
        metadata = state['metadata']
        stamp = datetime.fromisoformat(metadata['created_at'].replace('Z', '+00:00'))
        if stamp.tzinfo is None or folder.parent.name != stamp.astimezone(timezone.utc).date().isoformat():
            raise ValueError('diagnostic date or owner is invalid')
        row.update(created_at=metadata['created_at'], run=metadata['context'].get('run'))
        # Formal accounting lives in the Studio that holds, or held, this record.
        studio = root if root is not None else metadata['context'].get('studio')
        active = current()
        if active and active.id == folder.name:
            row['reason'] = 'active-operation'
        elif state['complete'] and names != _LOG_FILES:
            row['reason'] = 'unowned-or-missing-content'
        elif not state['complete'] and (cutoff is None or stamp.astimezone(timezone.utc).date() >= cutoff
                                        or _process_alive(metadata.get('pid'))):
            row['reason'] = 'incomplete-operation'
        elif state['complete'] and not state['log_complete']:
            row['reason'] = 'diagnostic-incomplete'
        elif row['run'] and studio is None:
            row['reason'] = 'formal-studio-unknown'
        elif row['run'] and _run_has_unresolved_external_effect(Path(studio), str(row['run'])):
            row['reason'] = 'remote-outcome-unresolved'
        else:
            # A killed process left no completed event; its record is closed for good.
            row.update(eligible=True, reason='eligible' if state['complete'] else 'abandoned-incomplete')
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        row['reason'] = 'diagnostic-corrupt-or-unsafe'
    return row


def cleanup_logs(root: Path | None, *, before: str | None = None, operation_id: str | None = None, apply: bool = False) -> dict:
    """List or delete only closed, owned diagnostics of a Studio, or of the configuration directory when `root` is None.

    An operation killed before the `before` date whose process has ended is closed.
    Selection is rechecked under a lock immediately before deletion.
    Formal evidence and directories with unexpected files are never cleanup targets.
    """
    import execution_contract as c
    from production_diagnostics import ProductionError
    if (before is None) == (operation_id is None):
        raise ProductionError('INPUT_ARGUMENT_INVALID', 'Select --before YYYY-MM-DD or --operation OPERATION_ID.', phase='logs-cleanup')
    if before is not None:
        try:
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}', before) is None:
                raise ValueError('date only')
            cutoff = datetime.fromisoformat(before).date()
        except (ValueError, TypeError) as exc:
            raise ProductionError('INPUT_ARGUMENT_INVALID', 'Cleanup date must be YYYY-MM-DD.', phase='logs-cleanup') from exc
    else:
        cutoff = None
    root = Path(root) if root is not None else None
    base = _log_base(root)
    rows, deleted = [], []
    for folder in _log_folders(root):
        if operation_id is not None and folder.name != operation_id:
            continue
        row = _cleanup_assessment(root, folder, cutoff=cutoff)
        if cutoff is not None and row.get('created_at'):
            if datetime.fromisoformat(row['created_at'].replace('Z', '+00:00')).date() >= cutoff:
                continue
        if apply and row['eligible']:
            with c.lock(root if root is not None else base):
                updated = _cleanup_assessment(root, folder, cutoff=cutoff)
                if updated != row:
                    row = {**updated, 'eligible': False, 'reason': 'changed-since-inspection'}
                else:
                    try:
                        shutil.rmtree(folder)
                        deleted.append(row['operation_id'])
                    except OSError as exc:
                        raise ProductionError('LOG_WRITE_FAILED', 'Owned diagnostics could not be removed.',
                            phase='logs-cleanup', file=str(folder), actual=type(exc).__name__) from exc
        rows.append(row)
    return {'ok': True, 'apply': bool(apply), 'selector': {'before': before, 'operation': operation_id},
            'candidates': [row for row in rows if row['eligible']],
            'protected': [row for row in rows if not row['eligible']],
            'deleted': deleted, 'formal_artifacts_deleted': False}


def export_logs(root: Path | None, out: Path, *, run: str | None = None, include_streams: bool = True) -> dict:
    """Publish a bounded, re-redacted diagnostic export as one complete directory.

    `root` None exports the configuration directory. `include_streams` False leaves out
    stdout.log and stderr.log, which can quote work text a command printed.
    """
    import tempfile
    from production_diagnostics import ProductionError
    import execution_contract as c
    root, out = (Path(root).absolute() if root is not None else None), Path(out).absolute()
    try:
        if root is not None:
            c.local(root, out.relative_to(root).as_posix(), exists=False)
        else:
            c.local(out.parent, out.name, exists=False)
    except (ValueError, OSError) as exc:
        raise ProductionError('LOG_EXPORT_PATH_INVALID', 'Select a new studio-relative diagnostic export directory.'
                              if root is not None else 'Select a new diagnostic export directory.',
                              phase='logs-export', file=str(out)) from exc
    base = _log_base(root)
    # Both paths are compared resolved, so a link in either one cannot hide an overlap.
    exported, logged = out.resolve(), base.resolve()
    if exported == logged or logged in exported.parents or exported in logged.parents:
        raise ProductionError('LOG_EXPORT_PATH_INVALID', 'An export cannot overlap the source diagnostic tree.', phase='logs-export')
    if out.exists():
        raise ProductionError('OUTPUT_ALREADY_EXISTS', 'Log export destination already exists.', phase='logs-export', file=str(out))
    rows = list_operations(root, run=run)
    out.parent.mkdir(parents=True, exist_ok=True)
    secrets = _secrets()
    names = sorted(_LOG_FILES if include_streams else _LOG_FILES - _CONSOLE_FILES)
    included, omissions, incomplete = [], [], []
    with tempfile.TemporaryDirectory(prefix='.pending-log-export-', dir=out.parent) as temporary:
        staging = Path(temporary) / 'export'
        staging.mkdir(mode=0o700)
        for row in rows:
            if not row.get('operation_id') or not row.get('path'):
                omissions.append({'operation_id': row.get('operation_id'), 'reason': row.get('diagnostic', 'unreadable')})
                continue
            source = Path(row['path'])
            if not row.get('complete') or not row.get('log_complete'):
                incomplete.append(row['operation_id'])
            try:
                c.local(base, source.relative_to(base).as_posix())
                target = staging / row['operation_id']
                target.mkdir()
                for name in names:
                    try:
                        path = c.local(source, name)
                        with path.open(encoding='utf-8', newline='') as stream, \
                                (target/name).open('w', encoding='utf-8', newline='') as destination:
                            writer = RedactingWriter(destination.write, secrets)
                            for block in iter(lambda: stream.read(65536), ''):
                                writer.write(block)
                            writer.flush(final=True)
                            destination.flush()
                            os.fsync(destination.fileno())
                        included.append(f'{row["operation_id"]}/{name}')
                    except (OSError, ValueError) as exc:
                        omissions.append({'operation_id': row['operation_id'], 'file': name, 'reason': type(exc).__name__})
                        incomplete.append(row['operation_id'])
                        partial = target/name
                        if partial.exists():
                            partial.unlink()
            except (OSError, ValueError) as exc:
                omissions.append({'operation_id': row['operation_id'], 'reason': type(exc).__name__})
                incomplete.append(row['operation_id'])
        excluded = ['image files and image data', 'formal production artifacts: requests, responses, candidates and reviews']
        if include_streams:
            work = ('stdout.log and stderr.log copy the console output of each command after redaction. '
                    'They can quote prompt, character or source text that a command printed.')
        else:
            excluded.append('stdout.log and stderr.log console output')
            work = 'Console output is excluded. The remaining files hold identifiers, paths, digests and diagnostics.'
        manifest = {'included': included, 'excluded': excluded, 'work_content': work,
                    'redaction': ('Known credentials, authentication fields and signed URL secrets are replaced with [REDACTED]. '
                                  'Named payload fields such as prompts, terms and renditions are omitted.'),
                    'limitations': 'Unknown secrets in free text cannot be guaranteed absent.',
                    'incomplete_operations': sorted(set(incomplete)), 'omissions': omissions}
        c.atomic(staging/'export.json', c.encoded(manifest))
        try:
            c.publish_directory(staging, out)
            c.fsync_dir(out.parent)
        except (OSError, ValueError) as exc:
            raise ProductionError('OUTPUT_ALREADY_EXISTS' if out.exists() else 'ARTIFACT_PUBLISH_FAILED',
                                  'Diagnostic export could not be published to its new destination.',
                                  phase='logs-export', file=str(out)) from exc
    return manifest
