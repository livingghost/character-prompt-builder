"""Argument groups for authored inputs, craft consultation and prepared-run changes."""
from __future__ import annotations
from pathlib import Path
from pack_runtime_cli import add_pack_runtime_arguments
from craft_consultation_contract import LAYERS


INPUT_COMMANDS = frozenset({'inspect-inputs', 'compare-inputs', 'explain-inputs', 'draft-inputs', 'stage-inputs', 'build-inputs'})


def add_change_scope_arguments(parser) -> None:
    """Expose authored preservation and change choices at their common owner."""
    from production_reading_scope import CHANGE_SCOPES, RETAIN_SCOPES
    parser.add_argument('--retain', action='append', choices=RETAIN_SCOPES,
        help='Keep this authored decision in a retained amend; repeat for independent decisions. '
             'The declaration belongs to work-basis.json and does not replace source or identity validation.')
    parser.add_argument('--change', action='append', choices=CHANGE_SCOPES,
        help='Declare this intended amendment; repeat to combine changes. The reader also inspects actual '
             'editable differences and adds their required knowledge. Requires amend of an existing input.')


def change_scope_from_arguments(args) -> dict | None:
    """Preserve the explicit declaration without classifying request text."""
    retain, change = getattr(args, 'retain', None), getattr(args, 'change', None)
    if retain is None and change is None:
        return None
    value = {'retain': list(dict.fromkeys(retain or [])), 'change': list(dict.fromkeys(change or []))}
    from production_reading_scope import validate_change_scope
    validate_change_scope(value)
    return value


def add_input_arguments(subparsers) -> None:
    for name in sorted(INPUT_COMMANDS):
        parser = subparsers.add_parser(name, help={
            'inspect-inputs': 'Inspect current work inputs, or an explicitly selected retained source.',
            'compare-inputs': 'Read actual editable candidates together through the common comparison owner.',
            'explain-inputs': 'Describe editable fields, source files, schemas, validators and completed examples.',
            'draft-inputs': 'Start a concrete compose or amend operation in a new authoring directory.',
            'stage-inputs': 'Continue definition, depiction, rendition or prepare while retaining the editable files.',
            'build-inputs': 'Resolve authored choices into complete inputs without running production.'}[name])
        parser.add_argument('--root', type=Path, required=True)
        if name == 'stage-inputs':
            from production_reading_scope import STAGES
            parser.add_argument('--choices', required=True, help='Studio-relative choices.json to continue.')
            parser.add_argument('--stage', required=True, choices=STAGES,
                help='Select the actual work: definition establishes sources and character; depiction develops the picture; '
                     'rendition writes its prompt; prepare binds the completed input for saving or generation preparation.')
            parser.epilog = ('Selected source files and earlier results remain intact. Read the returned current-stage '
                'action before changing its content. After a context reset, inspect this same choices file and reread '
                'the current stage; an earlier delivery receipt does not carry knowledge into a new context.')
            add_pack_runtime_arguments(parser)
            continue
        if name == 'compare-inputs':
            parser.add_argument('--choices', action='append', required=True,
                help='Studio-relative choices.json to compare; repeat for the actual candidates.')
            add_pack_runtime_arguments(parser)
            continue
        if name == 'explain-inputs':
            parser.add_argument('--choices', required=True, help='Studio-relative choices.json to explain without compiling.')
            parser.add_argument('--field', help='One display selector, such as task_changes.semantic_edit, authoring.documents.production_spec '
                                'or authoring.references.additional_references; follow returned child contracts '
                                'for exact schemas and editable owner pointers. Container selectors are not '
                                'permission to replace the parent. Omit for the field and source index.')
            continue
        source = parser.add_mutually_exclusive_group()
        source.add_argument('--task', help='Studio-relative authored production task JSON.')
        source.add_argument('--from-run', help='Use the saved task and delivery of this existing run.')
        if name == 'inspect-inputs':
            parser.add_argument('--choices', help='Inspect only this registered editable draft, including a retained '
                'draft from an earlier work revision; leave the current work and plan selection unchanged.')
            parser.epilog = ('Without a source selector, inspect every unfinished input of the current plan, or '
                'every input registered since the current work revision was reopened. Earlier inputs remain '
                'available through comparison actions. A later creation time does not choose one current branch. '
                'Saved inputs use their registered producer runtime. An explicit pack runtime '
                'supplies inputs with no registered runtime and is retained in their continuation actions; '
                'inspection does not change the saved inputs or registration.')
        if name == 'draft-inputs':
            from production_reading_scope import STAGES
            parser.epilog = ('To edit a captured candidate without a Studio slot, first create its draft with '
                '--from-run RUN --operation amend and declare the actual --retain and --change owners. Follow its '
                'current inspection and reading actions, then select the actual image file from '
                'input_reuse.captured_outputs. Apply it as this task\'s source and '
                'scene reference, and declare the semantic edit; no slot acceptance or canonical adoption is required. '
                'Follow references/runtime/production-authoring.md#start-an-existing-image-edit. Prepared results '
                'require an explicitly reopened work revision; see '
                'references/runtime/production-work-plan.md#revise-the-result-or-items.')
            source.add_argument('--choices',
                help='Use this actual editable candidate as the content of a new compose operation, including '
                     'an explicitly retained proposal from a refused edit. The earlier candidate remains comparison evidence.')
            parser.add_argument('--stage', choices=STAGES,
                help='Current authored work; new character drafts start with definition. A saved unfinished draft '
                     'retains its stage. A declared amend begins at its first affected stage. '
                     'Select prepare for binding already authored content.')
            add_change_scope_arguments(parser)
            image_source = parser.add_mutually_exclusive_group()
            image_source.add_argument('--source-image', type=Path,
                help='Upscale only (--route upscale): the raster image to enlarge, Studio-relative or an absolute '
                     'local path to import.')
            image_source.add_argument('--source-candidate',
                help='Upscale only (--route upscale): the exact captured candidate ID to enlarge, with --source-run.')
            parser.add_argument('--source-run', help='Upscale only: the run owning the selected --source-candidate.')
            parser.add_argument('--scale', type=float, help='Upscale only: the requested upscale factor.')
            parser.add_argument('--purpose',
                help='Upscale only: the actual upscale request; initializes unanswered purpose and criteria.')
            parser.add_argument('--edit-character', metavar='CHARACTER',
                help='Start an instruction edit of the accepted image of this Studio character, with --edit-slot, '
                     '--route generation and --execution dispatcher or external. The draft selects the image with '
                     'its acceptance evidence and any separately adopted identity; leaves the edit, prompt, criteria '
                     'and recording destination for the author. Sheet adoption is not required for scene editing. '
                     'For a candidate without a slot, use --from-run and the candidate-edit guidance below.')
            parser.add_argument('--edit-slot', metavar='SLOT',
                help='The source slot of --edit-character whose current accepted image is edited. '
                     'Choose the result destination independently in authoring.task.recording.slot.')
            parser.add_argument('--model',help='Select a catalog model in a new or reopened draft. For an unlisted '
                                'host, omit this selector and complete target.kind external in the choices.')
            parser.add_argument('--service',help='Select the offering service in a new or reopened draft.')
            parser.add_argument('--route', help='Select the production route in a new or reopened draft; no prebuilt task is needed.')
            parser.add_argument('--artifact', dest='artifact_kind',
                choices=('text', 'json', 'image', 'video', 'audio', 'binary'),
                help='Select the output kind. A new task defaults to image for upscale or an accepted-image edit, '
                     'otherwise text; an existing task retains its kind when this option is omitted.')
            parser.add_argument('--execution', choices=('authored', 'external', 'dispatcher'),
                help='Select the execution method. A new task defaults to dispatcher for upscale, otherwise authored. '
                     'Use external for an available host image tool. An accepted-image edit selects dispatcher or '
                     'external; an existing task retains its method '
                     'when this option is omitted.')
            parser.add_argument('--task-id', help='Existing work task ID; defaults to the open work task.')
            parser.add_argument('--new-task', metavar='GOAL',
                help='Open a new work task for this selected saved source, captured upscale image or accepted image to '
                     'edit; this goal names the work. Omit this option for another draft within the current open work. '
                     'Give its current actual instruction with --request-file.')
            parser.add_argument('--operation', choices=('compose', 'amend'),
                help='Both operations seed actual selected content. Compose opens identity-source selection; amend '
                     'retains the selected identity-source boundary. Required except with --choices, which selects compose. '
                     'Both retain the earlier candidate as comparison evidence.')
            parser.add_argument('--request-file',
                help='UTF-8 file containing the current actual request. A saved work can resume its acquired request; '
                     'an unfinished draft may leave it unanswered. The work-task goal is separate navigation.')
            parser.add_argument('--focus', choices=('character', 'supporting-setting'),
                help='The actual work subject; character by default. A supporting-setting request prepares its stage.')
            parser.add_argument('--apply-source', action='append', dest='apply_sources',
                help='Apply this acquired source ID to the current work; repeat for several sources. '
                     'Other acquired sources remain available in work-basis.json for comparison and selection.')
            parser.add_argument('--feature', action='append', dest='features',
                help='Select the task features in a new or reopened draft; repeat for several features.')
        if name != 'inspect-inputs':
            parser.add_argument('--out-dir', required=True, help='New studio-relative directory; existing files are preserved.')
        if name == 'build-inputs':
            parser.add_argument('--choices', required=True, help='Edited choices.json from draft-inputs, or a complete choices object.')
        add_pack_runtime_arguments(parser)

CRAFT_COMMANDS = frozenset({'consult-presets', 'apply-presets'})

def add_craft_arguments(subparsers) -> None:
    from pack_runtime_cli import add_pack_runtime_arguments
    for name in sorted(CRAFT_COMMANDS):
        parser = subparsers.add_parser(name, help='Consult craft assets or record their scoped application without execution.')
        parser.add_argument('--root', type=Path, required=True)
        parser.add_argument('--task', required=True)
        parser.add_argument('--out-dir', required=True, help='New studio-relative directory.')
        add_pack_runtime_arguments(parser)
        if name == 'consult-presets':
            group = parser.add_mutually_exclusive_group()
            group.add_argument('--query', help='Agent-authored canonical craft question.')
            group.add_argument('--questions', help='Studio-relative array of explicit questions and focuses.')
            parser.add_argument('--focus', choices=['all', *LAYERS], default='all')
            parser.add_argument('--inspect', nargs='*', default=[], metavar='ID')
            parser.add_argument('--previous', help='Previous studio-relative consultation report from this runtime.')
        else:
            parser.add_argument('--consultation', required=True)
            parser.add_argument('--decisions', required=True)
            parser.add_argument('--spec', required=True)

VARIATION_HELP = {
    'variant': 'Prepare a new input from a run with declared field changes; nothing is claimed or sent.',
    'repeat': 'Prepare another run of a run\'s unchanged input, with its own claim and authorization.',
    'retarget': 'Prepare a run from another one against a reassessed target or the current pack runtime.'}

def add_variation_arguments(subparsers) -> None:
    for name in ('variant', 'repeat', 'retarget'):
        parser = subparsers.add_parser(name, help=VARIATION_HELP[name], description=VARIATION_HELP[name])
        parser.add_argument('--root', type=Path, required=True, help='The studio directory that owns the run.')
        parser.add_argument('--from', dest='source_run', required=True, metavar='RUN', help='The prepared run to derive from.')
        parser.add_argument('--prepare', action='store_true', help='Publish the new run; without it the result is a check only.')
        if name == 'variant':
            parser.add_argument('--changes-file', required=True, metavar='FILE',
                                help='JSON {"changes": {FIELD_ID: value}, "reason": text}, studio-relative, absolute, or - for stdin.')
            parser.add_argument('--candidate', action='append', default=[], metavar='CANDIDATE_ID',
                                help='A captured candidate of the source run that this change answers; repeat for each.')
        elif name == 'retarget':
            selected = parser.add_mutually_exclusive_group(required=True)
            selected.add_argument('--task', help='Complete reassessed task with current target and evidence.')
            selected.add_argument('--choices', help='Editable choices.json owning the current target and authored inputs.')
            parser.add_argument('--reason', required=True, help='Authored reason for changing the target or adopting the current runtime.')
            from pack_runtime_cli import add_pack_runtime_arguments
            add_pack_runtime_arguments(parser)
