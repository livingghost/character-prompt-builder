#!/usr/bin/env python3
"""Prepare, authorize, execute, observe, revise and complete a production task.

Every operation uses the current authored contract. Planning and observation do
not establish consent. Only explicit, scoped grants authorize actions; hashes
prove consistency of recorded bytes, never artistic success or user identity.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import operation_context as _operation_context
from production_cli_arguments import (INPUT_COMMANDS, CRAFT_COMMANDS, add_input_arguments, add_craft_arguments, add_variation_arguments)


COMMAND_HELP = {
    'check': 'Check a task and show its request preview and execution plan without creating a run.',
    'prepare': 'Check a task and publish it as a prepared run with its exact request and execution plan.',
    'save': 'Save an authored revision from its editable choices, retaining unresolved input when --draft is selected.',
    'record-save': 'Record the saved authored revision after an interrupted publication.',
    'deliver': 'Copy this saved authored revision to a local destination, or record actual external presentation or attachment evidence.',
    'review-authored': 'Record an evidence-backed review of the saved authored artifact against its independent assessment basis.',
    'draft-execution': 'Write the unanswered execution decision file for every operation of a prepared run.',
    'acquire-source': 'Acquire one complete Production source row and regenerate its applications, subjects and derived task sources.',
    'draft-principal-approval': 'Retain an actual instruction and bind an unanswered approval draft to this exact run and request.',
    'draft-authority-update': 'Draft additions to current authority for this run, retaining issuer and expected predecessor.',
    'execute': 'Apply the separate execution decisions, then dispatch or hand the exact request to its external host once.',
    'resume': 'Recover the same execution without sending it again where a send has started; --watch keeps asking '
              'while the provider task is pending.',
    'draft-outcome': "Write the statement to fill when the provider's records hold no task for a started send.",
    'status': 'Report each run by preparation, readiness, submission, capture, review and disposition.',
    'authority-import': 'Import the grant file of the named work task, or replace the current one.',
    'recover-publication': 'Register a verified publication whose registration was interrupted.',
    'staging-cleanup': "List one ended operation's unpublished staging, unclaimed journals and unrecoverable publications.",
    'logs': 'List automatic operation logs of the studio, or of the configuration directory without --root.',
    'logs-export': 'Copy operation logs to a new directory with a manifest of what it includes.',
    'logs-cleanup': 'List diagnostic operation logs that may be deleted; production records stay.',
    'handoff-intent': 'Show the exact direction operation that a handoff needs authorized.',
    'handoff': 'Record a conversation or manual handoff that happened under an exact direction authorization.',
    'external-intent': 'Show the exact submission operation that an external host call needs authorized.',
    'claim-external': 'Commit the boundary before an external host invokes its tool under an exact authorization.',
    'receive-external': 'Receive actual response files and images, derive their receipt and settle the existing host call.',
    'workspace': 'Read the exact input, decision basis, candidate observation or review context without editing records.',
    'draft-authorization': 'Write an unanswered authorization request for one exact operation intent.',
    'authorize': 'Record a completed authorization request for one exact operation of a run.',
    'capture': 'Record a received result file as a candidate of the run.',
    'draft-review': 'Write the unanswered review form of a saved authored revision or one generated candidate.',
    'review': 'Record a completed review of one candidate.',
    'draft-disposition': 'Write the form that records a candidate as not selected.',
    'disposition': 'Record an explicit decision that a candidate is not selected.',
    'candidate-status': "Show one candidate's evaluation and disposition.",
    'draft-selection': 'Write the selection form of one reviewed candidate.',
    'draft-acceptance': 'Write one exact reviewed-result decision for delivery or an existing Studio slot.',
    'accept': 'Apply or recover the reviewed decision, its requested scope and production completion.',
    'selection-intent': 'Show the exact selection operation that a selection file needs authorized.',
    'select': 'Record an authorized selection of a reviewed candidate.',
    'revision-intent': 'Show the exact edit operation that a reviewed repair needs authorized.',
    'revise': 'Prepare a revised task as a new run under an authorized edit of a reviewed repair, or return that run once it exists.',
    'draft-adoption': 'Write one unanswered canonical-use decision, or reassess an existing claim under current authority.',
    'adopt': 'Apply one authored adoption decision, or recover its exact recorded claim.',
    'complete': 'Complete the work task with its required authored results or current selected execution result.',
    'impact': 'Compare a run with its current sources and list what each change affects.',
}
# Every readiness value status reports, with what it tells about the run.
READINESS_HELP = {
    'ready': 'The saved run is usable and nothing reported here blocks the next action; '
             'source-change notices do not select a different revision.',
    'authorization_required': 'A prepared operation of this unsent run has no exact authorization yet; '
                              'draft-execution writes the decision file that execute applies.',
    'configuration_required': 'The next provider step needs a credential that its selected authentication source '
                              'does not supply.',
    'blocked': 'The saved run or fixed runtime cannot be used, or current authority or another execution '
               'requirement prevents continuation; readiness_diagnostics names the required repair.',
    'not-applicable': 'The run is completed or abandoned; it is shown from its retained records and is not compared.',
    'unchecked': 'The run is open and its work task is completed or abandoned, so the view of the whole Studio did '
                 'not compare it; --run RUN compares it.',
    'saved': 'An authored revision whose save is recorded.',
    'published': 'An authored revision published before its save was recorded; record-save records it.',
}
# task_disposition belongs to the run; its work task closes on its own record.
DISPOSITION_HELP = {
    'open': 'The run has neither a completion nor an abandonment; its work task may already be closed.',
    'completed': 'The run holds its completion.',
    'abandoned': 'The run was abandoned.',
}


def _status_epilog() -> str:
    import textwrap
    def block(title: str, values: dict) -> str:
        width = max(map(len, values))
        return title + ':\n' + '\n'.join(
            textwrap.fill(text, 100, initial_indent=f'  {name.ljust(width)}  ', subsequent_indent=' ' * (width + 4))
            for name, text in values.items())
    return (block('readiness values', READINESS_HELP) + '\n\n'
            + block('task_disposition values, of the run and not of its work task', DISPOSITION_HELP))


# One sentence for each option, by destination; a (command, destination) entry is more specific.
OPTION_HELP = {
    'root': 'The studio directory that holds the production records.',
    'run': 'ID of the prepared run.',
    'task': 'Studio-relative task JSON file; a file only, not stdin.',
    'out': 'New studio-relative file to write; an existing file is never replaced.',
    'out_dir': 'New studio-relative directory to write.',
    'decisions_file': 'Completed execution decision file from draft-execution, or - for stdin.',
    'outcome_file': "Statement from draft-outcome that the provider's records hold no task for the started send, or - for stdin.",
    'grant': 'ID of the grant the drafted decisions use.',
    'expected_event': 'Digest of the current authority event that this import replaces.',
    'failed': 'Only operations that failed or did not finish.',
    'recipient': 'Who receives the consumer.',
    'method': 'How the consumer is handed over.',
    'authorization': 'Digest of the authorization event that covers this operation.',
    'count': 'Number of outputs the host call makes.',
    'candidate': 'Digest of the candidate event.',
    'artifact': 'Studio-relative file that was received; a file only, not stdin.',
    'note': 'Where the received file came from.',
    'intent': 'Operation intent JSON from an intent command, or - for stdin.',
    'repair': 'ID of the repair in the latest review of the candidate.',
    'character': 'Studio character ID.',
    'iteration': 'Studio iteration ID of the candidate.',
    'registration_record': 'Catalog registration record of a catalog adoption, or - for stdin.',
    'pack_dir': 'Pack directory that receives a catalog adoption.',
    'without_streams': 'Leave stdout.log and stderr.log out of the export.',
    'from_run': 'Saved run of the same work task and production to start from.',
    'choices': 'Editable choices file from draft-inputs.',
    'draft': 'Save unfinished authored text with its unresolved choices instead of claiming finished model input.',
    'focus': 'Craft layer to consult.',
    'inspect': 'Craft asset IDs to show in full.',
    'consultation': 'Studio-relative craft consultation report to apply.',
    'decisions': 'Studio-relative decisions about the consulted craft assets.',
    'spec': 'Studio-relative production specification the decisions annotate.',
    ('status', 'run'): 'Report only this run; an open run is compared with its current sources even after its work task closed.',
    ('logs', 'run'): 'Only operations linked to this run.',
    ('logs-export', 'run'): 'Only operations linked to this run.',
    ('logs', 'root'): 'Studio whose logs to list; without it, the configuration directory.',
    ('logs-export', 'root'): 'Studio whose logs to export; without it, the configuration directory.',
    ('logs-cleanup', 'root'): 'Studio whose logs to assess; without it, the configuration directory.',
    ('logs-export', 'out'): 'New directory for the export; relative to --root, or absolute without --root.',
    ('logs', 'operation'): 'Only this operation ID.',
    ('staging-cleanup', 'operation'): 'Owner operation ID whose items --apply removes.',
    ('staging-cleanup', 'apply'): 'Remove the eligible items of --operation; without it, only list them.',
    ('authority-import', 'file'): 'Grant file of the work task, or - for stdin.',
    ('authorize', 'file'): 'Completed authorization request file, or - for stdin.',
    ('review', 'file'): 'Completed review file from draft-review, or - for stdin.',
    ('deliver', 'file'): 'Receipt identifying actual presentation or attachment evidence, or - for stdin.',
    ('review-authored', 'file'): 'Completed common review form from draft-review, with observed evidence and limitations, or - for stdin.',
    ('select', 'file'): 'Completed selection file from draft-selection, or - for stdin.',
    ('accept', 'file'): 'Completed owner decision from draft-acceptance, or - for stdin; omit to resume the recorded selection.',
    ('adopt', 'file'): 'Completed canonical-use decision from draft-adoption, or - for stdin; derives approval and exact authorization.',
    ('adopt', 'claim'): 'Exact adoption claim to recover from retained approval and evidence; no new adoption decision is made.',
    ('draft-adoption', 'influence'): 'Required with --candidate: intended reusable influence. A --claim keeps its recorded influence.',
    ('draft-adoption', 'scope'): 'Destination for --candidate (default sheet); catalog also publishes the chosen record in a pack. A --claim keeps its scope.',
    ('draft-adoption', 'claim'): 'Retained adoption claim to reassess under current authority without changing its approval or destination.',
    ('selection-intent', 'file'): 'Completed selection file from draft-selection, or - for stdin.',
    ('disposition', 'file'): 'Completed disposition file from draft-disposition, or - for stdin.',
    ('revise', 'task'): 'Studio-relative revised task JSON file; a file only, not stdin.',
    ('revision-intent', 'task'): 'Studio-relative revised task JSON file; a file only, not stdin.',
}
# Arguments that name one JSON input file and accept - for stdin.
STDIN_INPUTS = ('decisions_file', 'file', 'request', 'intent', 'outcome_file', 'registration_record', 'changes_file')
# Arguments that name a studio file.
FILE_ARGUMENTS = STDIN_INPUTS + ('task', 'choices', 'artifact', 'response_file', 'submission_file',
                               'source_row', 'instruction_file', 'approval_evidence')

SUMMARY_COMMANDS = frozenset({'status', 'check', 'prepare', 'save', 'authority-import', 'draft-execution',
    'execute', 'resume', 'draft-inputs', 'inspect-inputs', 'build-inputs', 'acquire-source',
    'draft-principal-approval', 'draft-authority-update'})


def build_parser():
    """The complete command interface, each command and option with its one-sentence help."""
    parser = _operation_context.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    add_input_arguments(sub)
    add_craft_arguments(sub)
    add_variation_arguments(sub)
    sub.add_parser('new-production-id', help='Assign an explicit stable identity to a new production series.',
                   description='Assign an explicit stable identity to a new production series.')
    for name in COMMAND_HELP:
        p = sub.add_parser(name, help=COMMAND_HELP[name], description=COMMAND_HELP[name])
        p.add_argument('--root', type=Path, required=name not in {'logs', 'logs-export', 'logs-cleanup'})
        if name not in {'prepare', 'check', 'save', 'authority-import', 'staging-cleanup', 'logs', 'logs-export', 'logs-cleanup', 'status', 'acquire-source'}:
            p.add_argument('--run', required=True)
        if name in {'status', 'logs', 'logs-export'}:
            p.add_argument('--run')
        if name == 'status':
            p.epilog, p.formatter_class = _status_epilog(), argparse.RawDescriptionHelpFormatter
            p.add_argument('--view', choices=['summary', 'full'], default='summary',
                           help='Navigation with complete blockers and next actions, or full current evidence and declarations.')
        if name == 'execute':
            p.add_argument('--decisions-file')
        if name == 'acquire-source':
            p.add_argument('--choices', required=True, help='Current Studio-relative editable choices.json.')
            p.add_argument('--source-row', required=True,
                help='Studio-relative JSON file containing one public ProductionTask source row: id, path, role, '
                     'disposition, locator, reason and any identity.subject_ids/selectors. Acquisition derives the task sources.')
        if name == 'draft-principal-approval':
            p.add_argument('--instruction-file', required=True, help='Studio-relative UTF-8 file with the actual instruction, retained verbatim.')
            p.add_argument('--actor', required=True, help='The actual instructing principal; drafting does not assert approval.')
        if name == 'draft-authority-update':
            p.add_argument('--approval-evidence', help='Studio-relative file containing actual approval evidence for this run; absent evidence leaves decisions unanswered.')
            p.add_argument('--phase', choices=['execution', 'selection'], default='execution',
                help='execution (default) drafts direction/submission grants; selection drafts select/delivery for --candidate.')
            p.add_argument('--candidate', help='Exact reviewed candidate required for --phase selection; no candidate is inferred.')
        if name == 'resume':
            from execution_watch_options import WATCH_LIMIT_SECONDS
            recovery = p.add_mutually_exclusive_group()
            recovery.add_argument('--outcome-file')
            recovery.add_argument('--watch', action='store_true',
                                  help='Resume, then ask for the provider task again every --interval seconds while it '
                                       'stays pending, registering each output as it finishes, until none is pending '
                                       'or --limit ends.')
            p.add_argument('--interval', type=float, metavar='SECONDS',
                           help='Seconds --watch waits between lookups, the same every time, asking at once. When left '
                                'out, the run\'s sealed service record declares the schedule for its kind of output: '
                                'a first delay after the provider accepted the task, a first wait, and a factor and '
                                'upper bound by which later waits grow. A record that declares none needs --interval.')
            p.add_argument('--limit', type=float, metavar='SECONDS',
                           help='Seconds --watch keeps asking in all, after which it returns the run as a plain resume '
                                f'leaves it; {WATCH_LIMIT_SECONDS} when left out.')
        if name in {'draft-outcome', 'draft-execution', 'logs-export', 'draft-review', 'draft-selection',
                    'draft-authorization', 'draft-disposition', 'draft-acceptance', 'draft-adoption',
                    'draft-principal-approval', 'draft-authority-update'}:
            p.add_argument('--out', required=True)
        if name in {'draft-execution', 'draft-authorization', 'draft-acceptance', 'draft-adoption'}:
            p.add_argument('--grant', required=name == 'draft-authorization')
        if name == 'draft-acceptance':
            p.add_argument('--scope', choices=['delivery-only', 'studio-slot'], default='delivery-only',
                           help='Requested result scope; delivery-only leaves Studio acceptance unchanged.')
        if name == 'authority-import':
            p.add_argument('--file', required=True)
            p.add_argument('--expected-event')
        if name == 'staging-cleanup':
            p.add_argument('--operation')
            p.add_argument('--apply', action='store_true')
        if name == 'logs':
            p.add_argument('--failed', action='store_true')
            p.add_argument('--operation')
        if name == 'logs-export':
            p.add_argument('--without-streams', action='store_true')
        if name == 'logs-cleanup':
            group = p.add_mutually_exclusive_group(required=True)
            group.add_argument('--before', help='Select completed diagnostic operations created before YYYY-MM-DD.')
            group.add_argument('--operation', help='Select one operation ID for cleanup assessment.')
            p.add_argument('--apply', action='store_true', help='Delete eligible diagnostic logs. Omit for a dry-run plan.')
        if name in {'revision-intent', 'revise'}:
            p.add_argument('--task', required=True)
        if name in {'check', 'prepare'}:
            p.epilog = ('Input diagnostics name the source file, field and required_action. Parameter failures include '
                        'the expected value schema or available controls; a combined constraint points to the '
                        'parameter document root. CHECK_NOT_PERFORMED names the failed prerequisite to repair first.')
            source = p.add_mutually_exclusive_group(required=True)
            source.add_argument('--task')
            source.add_argument('--choices')
        if name == 'save':
            p.add_argument('--choices', required=True)
            p.add_argument('--draft', action='store_true')
        if name in {'prepare', 'check', 'save'}:
            from pack_runtime_cli import add_pack_runtime_arguments
            add_pack_runtime_arguments(p)
        if name in {'handoff', 'handoff-intent'}:
            p.add_argument('--recipient', required=True)
            p.add_argument('--method', required=True, choices=['conversation', 'manual', 'dispatcher'])
        if name in {'handoff', 'claim-external', 'revise'}:
            p.add_argument('--authorization', required=True)
        if name in {'external-intent', 'claim-external'}:
            p.add_argument('--count', type=int, required=True)
        if name in {'draft-selection', 'draft-acceptance', 'draft-disposition', 'candidate-status', 'revision-intent', 'revise'}:
            p.add_argument('--candidate', required=True)
        if name == 'draft-review':
            p.add_argument('--candidate', help='Actual candidate for a generated result; omit for an authored revision.')
            p.epilog = ('--out contains only the unanswered editable review form. Standard output is a report '
                        'with choices (that form), draft_file, review_guide and next_action. The guide names the '
                        'reserved candidate evidence ID, automatic comparison evidence and observation format. '
                        'Complete the saved form from actual observations; submit that file with review or review-authored.')
        if name == 'deliver':
            delivery = p.add_mutually_exclusive_group(required=True)
            delivery.add_argument('--to', help='Studio-relative local destination; an existing different file is a conflict.')
            delivery.add_argument('--file', help='Actual external presentation or attachment evidence, or - for stdin.')
        if name in {'authorize', 'review', 'select', 'selection-intent', 'disposition', 'review-authored'}:
            p.add_argument('--file', required=True)
        if name == 'accept':
            p.add_argument('--file')
        if name == 'adopt':
            chosen = p.add_mutually_exclusive_group(required=True)
            chosen.add_argument('--file')
            chosen.add_argument('--claim')
        if name == 'capture':
            p.add_argument('--artifact', required=True)
            p.add_argument('--note', required=True)
        if name == 'workspace':
            p.add_argument('--phase', required=True, choices=['input', 'decision', 'observe', 'review'],
                           help='The context to read; observe exposes candidate evidence before the assessment basis.')
            p.add_argument('--candidate', help='Candidate event ID for observe or review.')
        if name == 'receive-external':
            p.add_argument('--response', dest='response_file', required=True, help='Actual saved host response file.')
            p.add_argument('--artifact', dest='artifacts', action='append', default=[], help='Received file; repeat for several files.')
            p.add_argument('--image-pointer', dest='image_pointers', action='append', type=json.loads, default=[],
                           help='JSON array of keys/indices selecting a base64 image or image data URL in the response; repeat as needed.')
            p.add_argument('--call', dest='submission_file', help='Actual saved host call, when available.')
            p.add_argument('--request-pointer', type=json.loads, help='JSON key/index array selecting the request in --call; [] selects its root.')
            p.add_argument('--model-identity-pointer', type=json.loads, help='JSON key/index array selecting observed model identity in --call.')
            p.add_argument('--cost-pointer', type=json.loads, help='JSON key/index array selecting actual {currency, amount} in the response.')
            p.add_argument('--pending', action='store_true', help='The host has not delivered its final outcome yet.')
            p.add_argument('--reason', required=True, help='Executor explanation of the observed final or pending outcome.')
        if name == 'draft-authorization':
            p.add_argument('--intent', required=True)
        if name in {'revision-intent', 'revise'}:
            p.add_argument('--repair', required=True)
        if name == 'draft-adoption':
            from reference_contract import INTENDED_INFLUENCES
            chosen = p.add_mutually_exclusive_group(required=True)
            chosen.add_argument('--candidate')
            chosen.add_argument('--claim')
            p.add_argument('--scope', choices=['sheet', 'catalog'])
            p.add_argument('--influence', choices=INTENDED_INFLUENCES)
            p.add_argument('--registration-record')
            p.add_argument('--pack-dir', type=Path)
        if name == 'adopt':
            from pack_runtime_cli import add_pack_runtime_arguments
            add_pack_runtime_arguments(p)
    for command, child in sub.choices.items():
        if command in SUMMARY_COMMANDS and command != 'status':
            child.add_argument('--view', choices=['summary', 'full'], default='full',
                help='Show actionable current results and a saved complete report, or the full JSON result (default).')
        if child.description is None:
            child.description = next(action.help for action in sub._choices_actions if action.dest == command)
        for action in child._actions:
            if action.help is None and action.dest != 'help':
                action.help = OPTION_HELP.get((command, action.dest), OPTION_HELP.get(action.dest))
    return parser


def _print_report(args, result: dict) -> None:
    """Select presentation without changing the outcome of the actual operation."""
    if getattr(args, 'view', 'full') == 'summary' and args.root is not None:
        from production_report_view import present
        result = present(args.root, result, command=args.command,
            run=getattr(args, 'run', None), choices=getattr(args, 'choices', None))
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _studio_arguments(root: Path, args) -> None:
    """Name every file argument relative to the studio root, refusing other forms with the form to use.

    An absolute path is accepted when it lies inside the studio.
    """
    from production_diagnostics import ProductionError
    from production_binding import studio_file

    def normalize(name: str, value: str) -> str:
        if value == '-':
            return value
        option = '--' + name.replace('_', '-')
        # A missing task is named here; its compiler reports an unreadable input.
        path = studio_file(root, value, option=option, exists=name != 'task')
        try:
            return path.resolve().relative_to(root).as_posix() if Path(value).is_absolute() else value
        except ValueError as exc:
            raise ProductionError('INPUT_SCHEMA_INVALID', f'{option} names a file outside the studio: {value}',
                                  phase='arguments', file=str(value), option=option,
                                  required_action='Copy the file into the studio and name it relative to --root.') from exc

    for name in FILE_ARGUMENTS:
        value = getattr(args, name, None)
        if value is None:
            continue
        selected = [normalize(name, item) for item in value] if isinstance(value, list) else normalize(name, value)
        setattr(args, name, selected)


def _new_output(root: Path | None, out: str) -> Path:
    """The --out destination, refused when anything already occupies it."""
    from production_binding import new_output
    return new_output(root, out, option='--out')


def _write_new(root: Path, out: str, value: Any) -> None:
    import execution_contract as c
    from production_binding import write_new
    write_new(_new_output(root, out), c.encoded(value), option='--out', value=out)


def _write_decision_draft(root: Path, run: str, kind: str, out: str, value: dict,
                          *, candidate: str | None = None) -> None:
    """Register the exact producer-owned basis before publishing editable answers."""
    import production_operations as operations
    import production_authoring_state
    from production_execution import decision_context
    loaded = operations.read_run(root, run)
    prepared, rows = loaded.prepared, loaded.rows
    grant, scope = None, None
    if kind == 'review':
        reviews = [row for row in rows if row['event'] == 'authored-review'] if candidate is None else [
            row for row in rows if row['event'] == 'review' and row['data']['candidate'] == candidate]
        basis = reviews[-1]['sha256'] if reviews else None
    elif kind == 'selection':
        basis = {'review': value['review'], 'replaces': value['replaces']}
    elif kind == 'acceptance':
        basis = {'review': value['review'], 'expected_slot': value.get('expected_slot'),
                 'expected_placement': value.get('expected_placement'),
                 'authority': value['authority_sha256']}
        grant, scope = value['grant'], value['scope']
    elif kind == 'adoption':
        from production_adoption import decision_basis
        basis = decision_basis(value)
        grant, scope = value['grant'], value['scope']
    elif kind == 'outcome':
        basis = {'claim': value['claim']}
    elif kind == 'execution':
        basis = prepared['input_sha256']
    else:
        raise ValueError('unknown decision draft kind')
    context = decision_context(prepared, candidate=candidate, basis=basis, grant=grant, scope=scope)
    production_authoring_state.remember_decision_draft(root, prepared['task']['task_id'], run,
                                                       kind, out, context=context)
    _write_new(root, out, value)


def _stdin_inputs(root: Path, args) -> None:
    """Store a JSON input read from stdin as an object of its run, and name it by that object's path.

    Standard input feeds one input per call. Every other JSON input is a file.
    """
    from production_diagnostics import ProductionError
    from production_binding import single_stdin
    single_stdin({'--' + name.replace('_', '-'): getattr(args, name, None) for name in STDIN_INPUTS})
    dashed = [name for name in STDIN_INPUTS if getattr(args, name, None) == '-']
    if not dashed or dashed[0] == 'changes_file':
        return
    import execution_contract as c
    import production_operations as operations
    raw = c.read_input_bytes('-')
    try:
        c.decode(raw)
    except ValueError as exc:
        raise ProductionError('INPUT_SCHEMA_INVALID', 'Standard input is not UTF-8 JSON.', phase='arguments', file='-',
                              pointer='$', cause=str(exc), required_action='Supply one complete JSON document on stdin.') from exc
    base = operations.run_dir(root, args.run) if getattr(args, 'run', None) else c.local(root, 'production', exists=False)
    key = c.object_store(base, raw)
    setattr(args, dashed[0], (base / 'objects' / key).relative_to(root).as_posix())


def main() -> int:
    from production_diagnostics import CompilationError, EXIT_EXECUTION, EXIT_INPUT, exit_code, from_exception, result_exit
    parser = build_parser()
    args = parser.parse_args()
    if args.command == 'new-production-id':
        from pack_manager import generate_uuid7
        print(json.dumps({'production_id': generate_uuid7()}))
        return 0
    import execution_contract as c
    from production_diagnostics import ProductionError
    name = args.command
    try:
        # The user's explicit CLI root may be a volume/system alias. Resolve that
        # choice once, then recheck the canonical ancestors at every internal use.
        # Paths beneath it never gain permission to follow symbolic links.
        args.root = root = c._root(args.root.resolve()) if args.root is not None else None
        if getattr(args, 'out', None) is not None:
            _new_output(root, args.out)
        if root is not None:
            _studio_arguments(root, args)
            _stdin_inputs(root, args)
        if name in {'prepare', 'check', 'save', 'retarget'}:
            from pack_runtime_cli import resolve_pack_runtime, has_pack_runtime_arguments
            if has_pack_runtime_arguments(args):
                from catalog_retrieval import runtime
                runtime.configure_pack_runtime(resolve_pack_runtime(parser, args).settings)
        if name in CRAFT_COMMANDS:
            import craft_consultation
            result = craft_consultation.command(args, parser)
        elif name in {'variant', 'repeat', 'retarget'}:
            import production_variation
            result = production_variation.command(args, parser)
        elif name in INPUT_COMMANDS:
            import production_inputs
            result = production_inputs.command(args, parser)
        elif name == 'acquire-source':
            from production_source_acquisition import acquire_source
            result = acquire_source(root, args.choices, args.source_row)
        elif name in {'draft-principal-approval', 'draft-authority-update'}:
            from production_execution import draft_principal_approval, draft_authority_update
            result = (draft_principal_approval(root, args.run, args.instruction_file, args.actor)
                if name == 'draft-principal-approval' else
                draft_authority_update(root, args.run, args.approval_evidence,
                                       phase=args.phase, candidate=args.candidate))
            _write_new(root, args.out, result['choices'])
            result['draft_file'] = args.out
            if name == 'draft-authority-update':
                from cli_invocation import python_argv
                result['next_action'] = {'command': 'authority-import',
                    'argv': python_argv(Path(__file__), 'authority-import', '--root', str(root),
                        '--file', args.out, '--expected-event', result['choices']['expected_event']),
                    'requires_author_input': True,
                    'reason': 'Complete the actual authority choices in the saved draft, then import with this predecessor.'}
            else:
                result['approval_selection'] = {'path': args.out, 'locator': 'whole'}
                result['required_action'] += (' After recording the actual approval judgment, use approval_selection '
                    'as principal_approval in the execution decision; the same file can supply --approval-evidence '
                    'to draft-authority-update when current grants need additions.')
        elif name == 'draft-disposition':
            import production_operations as operations
            result = operations.draft_disposition(root, args.run, args.candidate)
            _write_new(root, args.out, result)
        elif name == 'disposition':
            import production_operations as operations
            result = operations.disposition(root, args.run, args.file)
        elif name == 'candidate-status':
            import production_operations as operations
            result = operations.candidate_state(root, args.run, args.candidate)
        elif name == 'check':
            from production_compiler import check_task
            if args.choices:
                import production_inputs
                compiled_choices = production_inputs.compile_choices(root, args.choices)
                try:
                    result = compiled_choices.report
                    if result.get('execution_plan') is not None:
                        result['execution_plan']['run'] = None
                finally:
                    if compiled_choices.directory is not None:
                        shutil.rmtree(compiled_choices.directory)
            else:
                result = check_task(root, args.task)
        elif name == 'save':
            import production_operations as operations
            result = operations.save(root, args.choices, draft=args.draft)
        elif name == 'record-save':
            from production_authored import record_save
            result = record_save(root, args.run)
        elif name == 'deliver':
            import production_operations as operations
            result = operations.deliver(root, args.run, args.file, destination=args.to)
        elif name == 'review-authored':
            import production_operations as operations
            result = operations.review_authored(root, args.run, args.file)
        elif name == 'draft-execution':
            from production_execution import draft_execution
            import production_authoring_state
            result = draft_execution(root, args.run, args.grant)
            _write_decision_draft(root, args.run, 'execution', args.out, result['choices'])
            result['decisions_file'] = args.out
            result['next_action'] = production_authoring_state._action(root, 'execute',
                '--run', args.run, '--decisions-file', args.out,
                reason='Complete the selected authority and decisions, then execute this exact saved draft.')
        elif name == 'execute':
            from production_execution import execute
            result = execute(root, args.run, decisions_file=args.decisions_file)
        elif name == 'authority-import':
            import production_store as store
            result = store.import_authority(root, args.file, expected=args.expected_event, report_changes=True)
        elif name == 'recover-publication':
            from production_compiler import recover_publication
            result = recover_publication(root, args.run)
        elif name == 'staging-cleanup':
            from production_compiler import staging_cleanup
            result = staging_cleanup(root, operation_id=args.operation, apply=args.apply)
        elif name == 'logs':
            result = {'operations': _operation_context.list_operations(root, run=args.run, failed=args.failed, operation_id=args.operation)}
        elif name == 'logs-export':
            result = _operation_context.export_logs(root, _new_output(root, args.out), run=args.run,
                                                     include_streams=not args.without_streams)
        elif name == 'logs-cleanup':
            result = _operation_context.cleanup_logs(root, before=args.before, operation_id=args.operation, apply=args.apply)
        elif name == 'resume':
            from production_execution import resume, watch
            times = {key: value for key, value in (('interval', args.interval), ('limit', args.limit)) if value is not None}
            if args.watch:
                result = watch(root, args.run, **times)
            elif times:
                raise ProductionError('INPUT_ARGUMENT_INVALID', '--interval and --limit set the waits of resume --watch.',
                                      phase='arguments', run=args.run,
                                      required_action='Add --watch to keep asking while the provider task is pending, or '
                                                      'leave out --interval and --limit to ask once.')
            else:
                result = resume(root, args.run, outcome_file=args.outcome_file)
        elif name == 'draft-outcome':
            from production_execution import draft_outcome
            result = draft_outcome(root, args.run)
            _write_decision_draft(root, args.run, 'outcome', args.out, result)
        elif name == 'prepare':
            import production_operations as operations
            result = operations.prepare(root, args.task, choices=args.choices)
        elif name == 'handoff-intent':
            import production_operations as operations
            result = operations.handoff_intent(root, args.run, args.recipient, args.method)
        elif name == 'handoff':
            import production_operations as operations
            result = operations.handoff(root, args.run, args.recipient, args.method, args.authorization)
        elif name == 'external-intent':
            import production_operations as operations
            result = operations.external_intent(root, args.run, args.count)
        elif name == 'claim-external':
            import production_operations as operations
            from production_execution import external_instruction
            claim = operations.claim_external(root, args.run, args.count, args.authorization)
            result = external_instruction(root, args.run, claim=claim)
        elif name == 'draft-authorization':
            import production_operations as operations
            result = operations.draft_authorization(root, args.run, args.grant, c.load(c.local(root, args.intent)))
            _write_new(root, args.out, result)
        elif name == 'authorize':
            import production_operations as operations
            result = operations.authorize(root, args.run, args.file)
        elif name == 'receive-external':
            import production_operations as operations
            from production_binding import studio_file
            artifacts = [studio_file(root, path, option='--artifact').relative_to(root).as_posix()
                         for path in args.artifacts]
            result = operations.receive_external(root, args.run, response_file=args.response_file, artifacts=artifacts,
                image_pointers=args.image_pointers, final=not args.pending, reason=args.reason,
                submission_file=args.submission_file, request_pointer=args.request_pointer,
                model_identity_pointer=args.model_identity_pointer, cost_pointer=args.cost_pointer)
        elif name == 'workspace':
            from production_workspace import workspace
            result = workspace(root, args.run, phase=args.phase, candidate=args.candidate)
        elif name == 'capture':
            import production_operations as operations
            result = operations.capture(root, args.run, args.artifact, args.note)
        elif name in {'draft-review', 'draft-selection'}:
            import production_operations as operations
            function = operations.draft_review if name == 'draft-review' else operations.draft_selection
            result = function(root, args.run, args.candidate)
            guide = (operations.review_authoring_guide(root, args.run, args.candidate, review_file=args.out)
                     if name == 'draft-review' else None)
            _write_decision_draft(root, args.run, name.removeprefix('draft-'), args.out, result,
                                  candidate=args.candidate)
            if name == 'draft-review':
                result = {'choices': result, 'draft_file': args.out, 'review_guide': guide,
                          'next_action': guide['next_action']}
        elif name == 'review':
            import production_operations as operations
            result = operations.review(root, args.run, args.file)
        elif name == 'selection-intent':
            import production_operations as operations
            result = operations.selection_intent(c.load(c.local(root, args.file)))
        elif name == 'select':
            import production_operations as operations
            result = operations.select(root, args.run, args.file)
        elif name == 'draft-acceptance':
            from production_acceptance import draft
            result = draft(root, args.run, args.candidate, args.grant, scope=args.scope)
            _write_decision_draft(root, args.run, 'acceptance', args.out, result, candidate=args.candidate)
        elif name == 'accept':
            from production_acceptance import accept
            result = accept(root, args.run, decision_file=args.file)
        elif name == 'revision-intent':
            import production_operations as operations
            result = operations.revision_intent(root, args.run, args.task, args.candidate, args.repair)
        elif name == 'revise':
            import production_operations as operations
            result = operations.revise(root, args.run, args.task, args.candidate, args.repair, args.authorization)
        elif name == 'draft-adoption':
            import production_adoption
            if args.claim is not None:
                if any(value is not None for value in (args.scope, args.influence, args.registration_record, args.pack_dir)):
                    raise ValueError('claim reassessment retains its scope, influence, catalog record and destination')
                result = production_adoption.draft_reassessment(root, args.run, args.claim, grant=args.grant)
            else:
                if args.influence is None:
                    raise ValueError('a new adoption needs its intended --influence')
                result = production_adoption.draft(root, args.run, args.candidate, scope=args.scope or 'sheet',
                    influence=args.influence, grant=args.grant, registration_file=args.registration_record,
                    pack_dir=args.pack_dir)
            _write_decision_draft(root, args.run, 'adoption', args.out, result, candidate=result['candidate'])
        elif name == 'adopt':
            import production_adoption
            from pack_runtime_cli import resolve_pack_runtime
            selected_scope = production_adoption.scope(root, args.run, decision_file=args.file, claim_id=args.claim)
            runtime = resolve_pack_runtime(parser, args) if selected_scope == 'catalog' else None
            result = production_adoption.apply(root, args.run, decision_file=args.file, claim_id=args.claim,
                settings=runtime.settings if runtime else None)
        elif name == 'complete':
            import production_operations as operations
            result = operations.complete(root, args.run)
        elif name == 'impact':
            import production_operations as operations
            result = operations.impact(root, args.run)
        else:
            import production_operations as operations
            result = operations.status(root, args.run)
        status = 0 if result.get('ok', True) else result_exit(result.get('diagnostics') or [],
            failure=EXIT_EXECUTION if name in {'execute', 'resume'} else EXIT_INPUT)
        _print_report(args, result)
        return status
    except (ValueError, OSError, UnicodeError, KeyError, TypeError) as exc:
        if isinstance(exc, CompilationError):
            _print_report(args, exc.report)
            return result_exit(exc.report['diagnostics'])
        diagnostic = from_exception(exc, phase='cli')
        _print_report(args, {'ok': False, 'diagnostics': [diagnostic]})
        return exit_code(diagnostic['code'])


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(_operation_context.run_cli(main))
