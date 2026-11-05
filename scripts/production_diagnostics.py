"""Machine-readable diagnostics and process exit statuses shared by every production CLI."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Iterable

# Process exit statuses. A diagnostic code selects one through EXIT_CODES.
EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_INPUT = 2
EXIT_WAITING = 3
EXIT_EXECUTION = 4
EXIT_INTERRUPTED = 130

# The author grants permission, configures the runtime, then retries.
WAITING_CODES = frozenset({
    'AUTHORIZATION_REQUIRED', 'AUTHORIZATION_MISMATCH', 'GRANT_SCOPE_EXCEEDED', 'GRANT_REVOKED',
    'GRANT_NOT_EFFECTIVE',
    'CREDENTIAL_UNAVAILABLE', 'HANDOFF_REQUIRED', 'PACK_RUNTIME_REQUIRED', 'PACK_NOT_ENABLED',
    'DEPENDENCY_UNAVAILABLE',
})
# An operation started and failed, or its external outcome is not known yet.
EXECUTION_CODES = frozenset({
    'DISPATCH_ALREADY_CLAIMED', 'REMOTE_OUTCOME_UNKNOWN', 'PROVIDER_REJECTION', 'TRANSPORT_RESULT_INVALID',
    'RESPONSE_CORRUPT', 'SETTLEMENT_CONFLICT', 'SETTLEMENT_EVIDENCE_REQUIRED', 'OUTPUT_COUNT_MISMATCH',
    'UPSCALE_OUTPUT_CONTRACT_MISMATCH', 'STUDIO_PROJECTION_FAILED', 'ARTIFACT_PUBLISH_FAILED',
    'LOG_WRITE_FAILED', 'EXECUTION_STOPPED', 'WORK_PROJECTION_FAILED',
    'PROVIDER_OUTPUT_CHANGED', 'TRANSPORT_IMPLEMENTATION_CHANGED',
})
# Every other code is an input defect: a declared input, a stored record or an argument needs correcting.
EXIT_CODES = {**{code: EXIT_WAITING for code in WAITING_CODES}, **{code: EXIT_EXECUTION for code in EXECUTION_CODES},
              'INTERNAL_ERROR': EXIT_INTERNAL, 'OPERATION_INTERRUPTED': EXIT_INTERRUPTED}

DEFAULT_ACTION = 'Correct the declared input and retry the operation.'
# Phase owners are declared here; diagnostic prose never selects its own help.
PHASE_DOCUMENTS = {
    'task-read': 'references/runtime/production-workflow.md#authoring-and-handoff',
    'task-schema': 'references/runtime/production-workflow.md#authoring-and-handoff',
    'task-contract': 'references/runtime/production-workflow.md#authoring-and-handoff',
    'source-read': 'references/runtime/production-execution.md#prepare-one-complete-input',
    'source-validation': 'references/runtime/production-execution.md#prepare-one-complete-input',
    'delivery-content': 'references/runtime/production-execution.md#assemble-authored-choices',
    'route-reading': 'references/runtime/production-execution.md#apply-the-completed-reading',
    'world-views': 'references/runtime/world-realization.md#local-realization-plan-and-cli',
    'moment-views': 'references/runtime/story-context.md#use-the-moment-in-production',
    'scene-materials': 'references/runtime/story-context.md#prepared-scene-persona-material',
    'image-input': 'references/runtime/production-execution.md#image-input-and-exact-external-requests',
    'identity-coverage': 'references/character-identity-contract.md#source-to-input-and-review-coverage',
    'semantic-edit': 'references/runtime/semantic-instruction-edit.md#author-and-bind-the-task',
    'scene-mask-binding': 'references/runtime/scene-mask-planning.md#use-the-existing-production-pipeline',
    'authority-evidence': 'references/runtime/production-permissions.md#authorization-and-execution-records',
    'external-image-contract': 'references/production-specification.md#ownership-boundary',
    'specification': 'references/production-specification.md#ownership-boundary',
    'plot': 'references/runtime/prompt-composition.md#scene-specification',
    'creative-intent': 'references/runtime/prompt-composition.md#revision-contract',
    'negative-provenance': 'references/runtime/prompt-composition.md#negative-output',
    'negative-transport': 'references/runtime/image-generation.md#model-and-negative-transport',
    'retrieval': 'references/runtime/prompt-composition.md#catalog-retrieval-and-inspection',
    'render-intent': 'references/runtime/render-contract.md#choose-the-finish',
    'target-contract': 'references/runtime/render-contract.md#read-the-models-guidance',
    'execution-profile': 'references/runtime/render-contract.md#declare-controls-by-operation',
    'execution-controls': 'references/runtime/render-contract.md#declare-controls-by-operation',
    'execution-quantity': 'references/runtime/render-contract.md#declare-controls-by-operation',
    'request-validation-evidence': 'references/runtime/model-evidence.md#the-request-validation-record',
    'reference-preparation': 'references/runtime/reference-delivery.md#bind-the-actual-transport',
    'dependency-preflight': 'DEPENDENCIES.md#environment-check-and-installation',
    'runtime-resolution': 'references/runtime/production-execution.md#prepare-one-complete-input',
    'recording-validation': 'references/runtime/studio.md#production-owned-candidates',
    'package-compilation': 'references/runtime/production-execution.md#prepare-one-complete-input',
    'request-compilation': 'references/runtime/render-contract.md#resolve-and-inspect-the-exact-input',
    'execution-plan': 'references/runtime/production-execution.md#execute-the-prepared-request',
    'publication': 'references/runtime/production-execution.md#unpublished-staging-and-interrupted-publication',
    'authorization': 'references/runtime/production-permissions.md#authorization-and-execution-records',
    'readiness': 'references/runtime/production-execution.md#execute-the-prepared-request',
    'resume': 'references/runtime/production-execution.md#status-and-resume',
}
PHASE_SCHEMAS = {
    'task-schema': 'schemas/authoring/production-task.schema.json',
    'task-contract': 'schemas/authoring/production-task.schema.json',
    'identity-coverage': 'schemas/authoring/production-task.schema.json',
    'image-input': 'schemas/authoring/image-input-plan.schema.json',
    'specification': 'protocols/shared-state/schemas/production-spec.schema.json',
    'render-intent': 'schemas/render-intent.schema.json',
}


def guidance(phase: str) -> dict[str, str] | None:
    """Return only the owner explicitly declared for this phase."""
    document = PHASE_DOCUMENTS.get(phase)
    if document is None:
        return None
    return {'document_path': document,
            **({'schema': PHASE_SCHEMAS[phase]} if phase in PHASE_SCHEMAS else {})}


def exit_code(code: str | None) -> int:
    """The exit status for one diagnostic code: 0 without one, 2 for an input defect."""
    if code is None:
        return EXIT_OK
    return EXIT_CODES.get(code, EXIT_INPUT)


def result_exit(diagnostics: Iterable[dict], *, failure: int = EXIT_INPUT) -> int:
    """The exit status of a failed result from its error diagnostics.

    An input defect comes first, because it must be corrected before anything
    else can proceed. An execution failure comes before waiting for permission.
    A failed result with no error diagnostic exits with `failure`.
    """
    statuses = {exit_code(item.get('code')) for item in diagnostics
                if isinstance(item, dict) and item.get('severity', 'error') == 'error'
                and item.get('code') != 'CHECK_NOT_PERFORMED'}
    for status in (EXIT_INPUT, EXIT_EXECUTION, EXIT_WAITING, EXIT_INTERNAL):
        if status in statuses:
            return status
    return failure


@dataclass
class Diagnostic:
    code: str
    message: str
    severity: str = 'error'
    phase: str = 'validation'
    file: str | None = None
    pointer: str | None = None
    required_action: str = DEFAULT_ACTION
    blocked_checks: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    guidance: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        owner = self.guidance or guidance(self.phase)
        return {**{name: getattr(self, name) for name in
                ('code', 'severity', 'phase', 'file', 'pointer', 'message',
                 'required_action', 'blocked_checks')},
                **({'guidance': owner} if owner is not None else {}), **self.details}

class ProductionError(ValueError):
    def __init__(self, code: str, message: str, *, phase: str = 'validation',
                 file: str | None = None, pointer: str | None = None,
                 required_action: str = DEFAULT_ACTION, guidance: dict[str, Any] | None = None,
                 **details: Any):
        self.diagnostic = Diagnostic(code, message, phase=phase, file=file, pointer=pointer,
                                     required_action=required_action, details=details, guidance=guidance)
        super().__init__(f'{code}: {message}')

class CompilationError(ProductionError):
    def __init__(self, report: dict):
        self.report = report
        super().__init__('INPUT_CONSISTENCY_ERROR', 'Compilation did not produce a publishable input.',
                         phase='compilation', required_action='Resolve the reported errors and required unperformed checks.')


def from_exception(error: BaseException, *, phase: str, file: str | None = None,
                   pointer: str | None = None, code: str = 'INPUT_CONSISTENCY_ERROR',
                   guidance: dict[str, Any] | None = None, required_action: str | None = None) -> dict:
    if isinstance(error, ProductionError):
        result = error.diagnostic.as_dict()
        if error.diagnostic.guidance is None and guidance is not None:
            result['guidance'] = guidance
        if result['required_action'] == DEFAULT_ACTION and required_action is not None:
            result['required_action'] = required_action
        return result
    if isinstance(error, FileExistsError):
        code = 'OUTPUT_ALREADY_EXISTS'
    elif isinstance(error, OSError):
        code = 'ARTIFACT_PUBLISH_FAILED' if phase in {'publication', 'storage'} else 'INPUT_UNREADABLE'
    return Diagnostic(code, str(error), phase=phase, file=file, pointer=pointer,
                      guidance=guidance, required_action=required_action or DEFAULT_ACTION).as_dict()


def same_json(expected: Any, actual: Any) -> bool:
    """JSON content identity, including scalar types and ordered array elements."""
    import execution_contract as c
    return c.encoded(expected) == c.encoded(actual)


def compare_exact(expected: Any, actual: Any, *, pointer: str = '$', phase: str = 'authorization',
                  intent: dict | None = None) -> None:
    """Compare complete typed operations and identify the first differing field.

    `intent` names the prepared operation being authorized (operation, targets,
    run, authorization); a mismatch reports it beside the differing field.
    """
    def mismatch(message: str, left=expected, right=actual, at=pointer):
        details = {} if intent is None else {'intent': intent}
        raise ProductionError('AUTHORIZATION_MISMATCH', message, phase=phase, pointer=at,
            expected=left, actual=right, expected_type=type(left).__name__, actual_type=type(right).__name__,
            required_action='Obtain authorization for the complete prepared operation.', **details)
    if type(expected) is not type(actual):
        mismatch('Operation value types differ.')
    if isinstance(expected, dict):
        for key in sorted(set(expected) | set(actual)):
            if key not in expected or key not in actual:
                mismatch('Operation fields differ.', expected.get(key), actual.get(key), f'{pointer}.{key}')
            compare_exact(expected[key], actual[key], pointer=f'{pointer}.{key}', phase=phase, intent=intent)
    elif isinstance(expected, list):
        if len(expected) != len(actual):
            mismatch('Operation array lengths differ.')
        for index, (left, right) in enumerate(zip(expected, actual)):
            compare_exact(left, right, pointer=f'{pointer}[{index}]', phase=phase, intent=intent)
    elif not same_json(expected, actual):
        mismatch('Operation values differ.')
