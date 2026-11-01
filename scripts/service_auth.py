"""One service authentication setting in the Studio's private JSON document.

Each service stores its API key directly or names one process environment
variable. Execution receives the value separately from its recorded source.
"""
from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
import getpass
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any
import warnings

from cli_invocation import python_argv, shown
import execution_contract as contract
import operation_context as operations
from private_state import PRIVATE_CREDENTIALS_FILE as CONFIG_FILE
from private_state import PRIVATE_TEMPORARY_PREFIX, PrivateStateError, ensure_private_ignored
from production_diagnostics import ProductionError

ROOT = Path(__file__).resolve().parents[1]
IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9-]*$")
ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_UNSELECTED = object()


class AuthConfigurationError(ValueError):
    """An owner-authored diagnostic whose message contains no input bytes."""
    def __init__(self, message: str, *, repair: str = "status",
                 input_path: Path | None = None, input_service: str | None = None):
        self.repair = repair
        self.input_path = input_path
        self.input_service = input_service
        super().__init__(message)


@dataclass(frozen=True)
class Credential:
    value: str = field(repr=False)
    selection: dict[str, Any]


def validate_identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise AuthConfigurationError("Use a " + label + " identifier containing lowercase letters, digits and hyphens, beginning with a letter or digit.")
    return value


def validate_environment(value: Any) -> str:
    if not isinstance(value, str) or not ENVIRONMENT_NAME.fullmatch(value):
        raise AuthConfigurationError("Use a valid source environment variable name.")
    return value


def validate_selection(value: Any, *, service: str | None = None) -> dict[str, Any]:
    """Validate the nonsecret service and source identity saved with execution."""
    fields = {"api_key": {"service", "source"},
              "api_key_env": {"service", "source", "variable"}}
    if (not isinstance(value, dict) or not isinstance(value.get("source"), str) or
            value["source"] not in fields or set(value) != fields[value["source"]]):
        raise AuthConfigurationError("Authentication selection declares its service and api_key source, or its service, api_key_env source and variable.")
    selected_service = validate_identifier(value["service"], "service")
    if value["source"] == "api_key_env":
        validate_environment(value["variable"])
    if service is not None and selected_service != validate_identifier(service, "service"):
        raise AuthConfigurationError("Authentication selection belongs to a different service.")
    return dict(value)


def _selection(service: str, entry: Any) -> dict:
    if not isinstance(entry, dict) or len({"api_key", "api_key_env"} & entry.keys()) != 1:
        raise AuthConfigurationError("Select one api_key or api_key_env source for this service.")
    source = {"service": service, "source": "api_key"}
    if "api_key_env" in entry:
        source.update(source="api_key_env", variable=entry["api_key_env"])
    return validate_selection(source, service=service)


def _input(path: Path, service: str | None = None) -> dict:
    pointer = "/" + service + "/api_key" if service is not None else ""
    instructions = (
        "Open this JSON file in a text editor, enter the API key as the string value at " + pointer +
        ", and save the complete file as UTF-8 JSON. Preserve the other service settings. "
        "The Agent checks this service after you finish saving."
        if service is not None else
        "Open this private file in a text editor and restore a UTF-8 JSON object whose service entries "
        "each contain api_key or api_key_env. Preserve the existing service settings and values, then save. "
        "The Agent checks authentication after you finish saving.")
    return {"path": str(path.absolute()), "format": "json", "encoding": "utf-8",
            "json_pointer": pointer, "instructions": instructions}


def _repair(root: Path, service: str | None, expected: dict | None = None, *,
            repair: str = "status", input_path: Path | None = None,
            input_service: str | None = None) -> dict:
    service = service if isinstance(service, str) and IDENTIFIER.fullmatch(service) else None
    expected = expected if service is not None else None
    command = "status"
    if service is not None:
        if repair in {"prepare", "restore"}:
            command = "prepare"
        elif repair == "set":
            command = "set"
    if input_path is not None:
        command = "status"
    args = ["credentials", command]
    if service is not None:
        args.append(service)
    args += ["--studio", str(root)]
    if command == "prepare":
        if expected is not None:
            args += (["--environment", expected["variable"]] if expected["source"] == "api_key_env" else ["--stored"])
        if repair == "restore":
            reason = "Confirm the intended service authentication, then restore the source recorded by this execution."
        elif expected is not None and expected["source"] == "api_key_env":
            reason = "Restore this service's named environment source and make that variable available in the executing process."
        else:
            reason = "Prepare the service entry in credentials.json, then give the owner the returned file path and JSON Pointer when a value is needed."
    elif command == "set":
        args.append("--stdin")
        reason = "Supply the private value through standard input to save authentication for this service."
    else:
        reason = "Inspect the service's authentication setting and repair the reported source or availability."
    action = {"command": "credentials-" + command,
              "argv": python_argv(ROOT / "scripts" / "studio.py", *args),
              "reason": reason, "requires_author_input": command != "prepare" or repair == "restore"}
    if input_path is not None:
        action["input"] = _input(input_path, input_service)
        action["reason"] = action["input"]["instructions"] + " Then run this availability check."
    return action


def _error(root: Path, service: str | None, message: str, *,
           selection: dict | None = None, expected: dict | None = None,
           repair: str = "status", input_path: Path | None = None,
           input_service: str | None = None) -> ProductionError:
    action = _repair(root, service, expected, repair=repair,
                     input_path=input_path, input_service=input_service)
    return ProductionError("CREDENTIAL_UNAVAILABLE", message, phase="credential-resolution",
                           file=str(input_path) if input_path is not None else None,
                           required_action=action["reason"] + " " + shown(action["argv"]),
                           selection=selection, expected_selection=expected, next_action=action)


def _studio(root: Path) -> Path:
    root = contract._root(Path(root))
    if not root.is_dir() or not contract.local(root, "studio.json", exists=False).is_file():
        raise AuthConfigurationError("Authentication management requires an existing Studio.")
    return root


def _validate_document(value: Any) -> None:
    if not isinstance(value, dict):
        raise AuthConfigurationError("Authentication JSON contains an object of service settings.")
    for entry in value.values():
        if isinstance(entry, dict) and isinstance(entry.get("api_key"), str):
            operations.register_secret(entry["api_key"])


def _snapshot(root: Path) -> tuple[dict, bytes | None]:
    path = root / CONFIG_FILE
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return {}, None
    try:
        value = json.loads(raw.decode("utf-8-sig"))
        _validate_document(value)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, AuthConfigurationError):
        raise AuthConfigurationError("Restore valid authentication JSON with one api_key or api_key_env setting per service while preserving existing values.", input_path=path) from None
    return value, raw


def _document(root: Path) -> dict:
    return _snapshot(_studio(root))[0]


def selections(root: Path) -> dict:
    """Expose each service's source identity while keeping saved values private."""
    return {service: _selection(service, entry) for service, entry in _document(root).items()}


def _write(path: Path, document: dict, *, expected_raw: bytes | None) -> None:
    """Publish private JSON after checking the exact bytes read for this edit."""
    _validate_document(document)
    raw = (json.dumps(document, sort_keys=True, indent=2) + "\n").encode("utf-8")
    ensure_private_ignored(path.parent)
    descriptor, name = tempfile.mkstemp(prefix=PRIVATE_TEMPORARY_PREFIX, dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            current = path.read_bytes()
        except FileNotFoundError:
            current = None
        if current != expected_raw:
            raise AuthConfigurationError("Authentication JSON changed during this update. Retain the editor's saved file, inspect the current selection, and repeat the intended change.")
        os.replace(temporary, path)
        contract.fsync_dir(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _value(value: Any) -> str:
    """Return an available string unchanged; the service owns its key format."""
    if isinstance(value, str) and value:
        operations.register_secret(value)
    if not isinstance(value, str) or value == "":
        raise AuthConfigurationError("Supply the authentication value as a nonempty string.", repair="set")
    return value


def _stored_value(root: Path, entry: dict, service: str) -> str:
    value = entry["api_key"]
    if value == "":
        raise AuthConfigurationError("The private JSON entry is ready and awaits the credential owner's API key.",
                                     input_path=root / CONFIG_FILE, input_service=service)
    try:
        return _value(value)
    except AuthConfigurationError:
        raise AuthConfigurationError("Enter the API key as a JSON string.",
                                     input_path=root / CONFIG_FILE, input_service=service) from None


@contextlib.contextmanager
def _locked(root: Path):
    """Serialize authentication edits with other work in this Studio."""
    with contract.lock(root):
        yield


@contextlib.contextmanager
def _management(root: Path, service: str | None = None):
    """Translate local configuration errors without exposing parser or OS input."""
    try:
        yield
    except ProductionError:
        raise
    except AuthConfigurationError as exc:
        raise _error(Path(root), service, str(exc), repair=exc.repair,
                     input_path=exc.input_path, input_service=exc.input_service) from None
    except PrivateStateError as exc:
        raise _error(Path(root), service, str(exc)) from None
    except PermissionError:
        raise _error(Path(root), service,
                     "The operating system denied access to authentication storage. Restore private access permissions before retrying.") from None
    except (OSError, ValueError, TypeError):
        raise _error(Path(root), service,
                     "Authentication configuration could not be read or updated. Check the service setting, Studio path and private access permissions.") from None


def resolve(root: Path, service: str, *, expected: dict | None = None) -> Credential:
    """Resolve this service, verifying an existing execution's recorded source."""
    selection = None
    checked_expected = None
    try:
        root = _studio(root)
        service = validate_identifier(service, "service")
        if expected is not None:
            checked_expected = validate_selection(expected, service=service)
        document = _document(root)
        if service not in document:
            message = ("Restore the authentication source recorded by this execution for the service."
                       if checked_expected is not None else
                       "Prepare this service's API key entry or select an explicitly named process environment variable.")
            raise AuthConfigurationError(message, repair="prepare")
        entry = document[service]
        try:
            selection = _selection(service, entry)
        except AuthConfigurationError as exc:
            raise AuthConfigurationError(str(exc), input_path=root / CONFIG_FILE) from None
        if checked_expected is not None and selection != checked_expected:
            raise AuthConfigurationError("The service's authentication source changed. Confirm the intended account before restoring its recorded source.", repair="restore")
        if "api_key" in entry:
            value = _stored_value(root, entry, service)
        else:
            variable = entry["api_key_env"]
            value = os.environ.get(variable, "")
            if value == "":
                raise AuthConfigurationError("Supply the selected process environment variable " + variable + " in the executing process.")
            try:
                value = _value(value)
            except AuthConfigurationError as exc:
                raise AuthConfigurationError("Correct the authentication value in process environment variable " + variable + ". " + str(exc)) from None
        return Credential(value, selection)
    except ProductionError:
        raise
    except AuthConfigurationError as exc:
        raise _error(Path(root), service, str(exc), selection=selection,
                     expected=checked_expected or selection, repair=exc.repair,
                     input_path=exc.input_path, input_service=exc.input_service) from None
    except PermissionError:
        raise _error(Path(root), service,
                     "The operating system denied access to authentication storage. Restore private access permissions and inspect the selected source.",
                     selection=selection, expected=checked_expected or selection) from None
    except (OSError, ValueError, TypeError):
        raise _error(Path(root), service,
                     "The selected authentication source is unavailable or invalid. Inspect this service's setting.",
                     selection=selection, expected=checked_expected or selection) from None


def inspect(root: Path, service: str, *, expected: dict | None = None) -> dict:
    """Report local availability; this operation makes no provider request."""
    try:
        credential = resolve(root, service, expected=expected)
        return {"available": True, "selection": credential.selection, "diagnostics": []}
    except ProductionError as exc:
        diagnostic = exc.diagnostic.as_dict()
        return {"available": False, "selection": diagnostic.get("selection"), "diagnostics": [diagnostic]}


def prepare(root: Path, service: str, *, environment: str | None = None,
            stored: bool = False) -> dict:
    """Prepare a service entry, retaining its value unless a source is selected."""
    with _management(root, service):
        root = _studio(root)
        service = validate_identifier(service, "service")
        if environment is not None and stored:
            raise AuthConfigurationError("Choose one preparation: a saved API key or a named environment variable.")
        if environment is not None:
            validate_environment(environment)
        with _locked(root):
            document, raw = _snapshot(root)
            ensure_private_ignored(root)
            previous = document.get(service)
            if environment is not None:
                entry = {"api_key_env": environment}
            elif stored:
                entry = {"api_key": previous.get("api_key", "") if isinstance(previous, dict) else ""}
            elif service not in document:
                entry = {"api_key": ""}
            else:
                entry = previous
            try:
                selected = _selection(service, entry)
            except AuthConfigurationError as exc:
                raise AuthConfigurationError(str(exc), input_path=root / CONFIG_FILE) from None
            changed = previous != entry
            if changed:
                document[service] = entry
                _write(root / CONFIG_FILE, document, expected_raw=raw)
            operation = "created" if previous is None else "updated" if changed else "retained"
            observed = inspect(root, service, expected=selected)
            return {"ok": True, "selection": selected, "available": observed["available"],
                    "operation": operation,
                    "input": _input(root / CONFIG_FILE, service) if "api_key" in entry else None,
                    "next_action": None if observed["available"] else observed["diagnostics"][0]["next_action"],
                    "diagnostics": observed["diagnostics"], "remote_validation": "not-performed"}


def read_input(root: Path, service: str, *, from_env: str | None = None,
               stdin: bool = False) -> str:
    """Receive a value for private storage through hidden input, stdin or import."""
    with _management(root, service):
        root = _studio(root)
        service = validate_identifier(service, "service")
        if from_env is not None and stdin:
            raise AuthConfigurationError("Choose one input source for the authentication value.")
        try:
            if from_env is not None:
                value = os.environ.get(validate_environment(from_env), "")
            elif stdin:
                stream = getattr(sys.stdin, "buffer", None)
                value = stream.read().decode("utf-8") if stream is not None else sys.stdin.read()
            else:
                if not sys.stdin.isatty():
                    raise AuthConfigurationError("Hidden input needs a terminal; use --stdin or prepare the owner's private JSON entry.", repair="prepare")
                with warnings.catch_warnings():
                    warnings.simplefilter("error", getpass.GetPassWarning)
                    value = getpass.getpass("Authentication value for " + service + ": ")
            return _value(value)
        except (OSError, ValueError, EOFError, getpass.GetPassWarning) as exc:
            if isinstance(exc, AuthConfigurationError):
                raise
            raise AuthConfigurationError("Authentication input is unavailable. Prepare the owner's private JSON entry or supply a value through an available input channel.", repair="prepare") from None


def set_from_input(root: Path, service: str, *, from_env: str | None = None,
                   stdin: bool = False) -> dict:
    """Retain the observed service setting while its owner supplies a value."""
    with _management(root, service):
        root = _studio(root)
        service = validate_identifier(service, "service")
        previous = _document(root).get(service)
        value = read_input(root, service, from_env=from_env, stdin=stdin)
        return set_value(root, service, value, expected_entry=previous)


def set_value(root: Path, service: str, value: str, *,
              expected_entry: Any = _UNSELECTED) -> dict:
    """Save or rotate this service's API key, replacing an environment source."""
    with _management(root, service):
        value = _value(value)
        service = validate_identifier(service, "service")
        root = _studio(root)
        with _locked(root):
            document, raw = _snapshot(root)
            previous = document.get(service)
            if (expected_entry is not _UNSELECTED and
                    contract.encoded(previous) != contract.encoded(expected_entry)):
                raise AuthConfigurationError("The service's authentication setting changed while its value was supplied. Inspect this service and repeat the intended update.")
            entry = {"api_key": value}
            changed = previous != entry
            if changed:
                document[service] = entry
                _write(root / CONFIG_FILE, document, expected_raw=raw)
            else:
                ensure_private_ignored(root)
        operation = ("created" if previous is None else "retained" if not changed else
                     "rotated" if isinstance(previous, dict) and "api_key" in previous else "updated")
        return {"ok": True, "selection": _selection(service, entry), "available": True,
                "operation": operation, "remote_validation": "not-performed"}


def remove(root: Path, service: str) -> dict:
    """Remove this service's local value or environment reference."""
    with _management(root, service):
        root = _studio(root)
        service = validate_identifier(service, "service")
        with _locked(root):
            document, raw = _snapshot(root)
            present = service in document
            previous = document.pop(service, None)
            if present:
                _write(root / CONFIG_FILE, document, expected_raw=raw)
        try:
            previous_selection = _selection(service, previous) if present else None
        except AuthConfigurationError:
            previous_selection = None
        return {"ok": True, "service": service, "removed": present,
                "previous_selection": previous_selection,
                "provider_key": "unchanged", "remote_validation": "not-performed"}


def status(root: Path, service: str | None = None) -> dict:
    """Inspect each service's source and local availability, keeping values private."""
    with _management(root, service):
        root = _studio(root)
        document = _document(root)
        services = [validate_identifier(service, "service")] if service is not None else sorted(document)
        reports = [{"service": name, **inspect(root, name)} for name in services]
        return {"ok": all(entry["available"] for entry in reports), "studio": str(root), "services": reports,
                "scope": "Configured services" if service is None else "Named service",
                "remote_validation": "not-performed"}
