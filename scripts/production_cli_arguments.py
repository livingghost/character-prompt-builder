"""Argument groups for authored inputs, craft consultation and prepared-run changes."""
from __future__ import annotations
from pathlib import Path
from pack_runtime_cli import add_pack_runtime_arguments
from craft_consultation_contract import LAYERS


INPUT_COMMANDS = frozenset({'inspect-inputs', 'compare-inputs', 'explain-inputs', 'draft-inputs', 'build-inputs'})

def add_input_arguments(subparsers) -> None:
    for name in sorted(INPUT_COMMANDS):
        parser = subparsers.add_parser(name, help={
            'inspect-inputs': 'Show declared sources, candidates and required input choices.',
            'compare-inputs': 'Read actual editable candidates together through the common comparison owner.',
            'explain-inputs': 'Describe editable fields, source files, schemas, validators and completed examples.',
            'draft-inputs': 'Start a concrete compose or amend operation in a new authoring directory.',
            'build-inputs': 'Resolve authored choices into complete inputs without running production.'}[name])
        parser.add_argument('--root', type=Path, required=True)
        if name == 'compare-inputs':
            parser.add_argument('--choices', action='append', required=True,
                help='Studio-relative choices.json to compare; repeat for the actual candidates.')
            add_pack_runtime_arguments(parser)
            continue
        if name == 'explain-inputs':
            parser.add_argument('--choices', required=True, help='Studio-relative choices.json to explain without compiling.')
            parser.add_argument('--field', help='One choices field, such as authoring.documents.production_spec; '
                                'omit for the field and source index.')
            continue
        source = parser.add_mutually_exclusive_group()
        source.add_argument('--task', help='Studio-relative authored production task JSON.')
        source.add_argument('--from-run', help='Use the saved task and delivery of this existing run.')
        if name == 'inspect-inputs':
            parser.add_argument('--choices', help='Select this registered editable draft when several are pending.')
        if name == 'draft-inputs':
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
                     'and recording destination for the author. Sheet adoption is not required for scene editing.')
            parser.add_argument('--edit-slot', metavar='SLOT',
                help='The source slot of --edit-character whose current accepted image is edited. '
                     'Choose the result destination independently in authoring.task.recording.slot.')
            parser.add_argument('--model',help='Select the canonical model in a new or reopened draft.')
            parser.add_argument('--service',help='Select the offering service in a new or reopened draft.')
            parser.add_argument('--route', help='Initial production route; no prebuilt task is needed.')
            parser.add_argument('--artifact', dest='artifact_kind',
                choices=('text', 'json', 'image', 'video', 'audio', 'binary'),
                help='Initial output kind; defaults to image for upscale and for an edit of an accepted image, otherwise '
                     'text. Existing tasks retain their kind.')
            parser.add_argument('--execution', choices=('authored', 'external', 'dispatcher'),
                help='Initial execution method; defaults to dispatcher for upscale, otherwise authored. An edit of an '
                     'accepted image selects dispatcher or external. Existing tasks retain their method.')
            parser.add_argument('--task-id', help='Existing work task ID; defaults to the open work task.')
            parser.add_argument('--new-task', metavar='GOAL',
                help='Open a new work task for this selected saved source, captured upscale image or accepted image to '
                     'edit; this goal names the work. Give its current actual instruction with --request-file.')
            parser.add_argument('--operation', choices=('compose', 'amend'), required=True,
                help='Compose starts actual content from the current sources and requirements; amend starts from '
                     'the exact selected candidate. Both retain the earlier candidate as comparison evidence.')
            parser.add_argument('--request-file',
                help='UTF-8 file containing the current actual request. A saved work can resume its acquired request; '
                     'an unfinished draft may leave it unanswered. The work-task goal is separate navigation.')
            parser.add_argument('--focus', choices=('character', 'supporting-setting'),
                help='The actual work subject; character by default. A supporting-setting request prepares its stage.')
            parser.add_argument('--apply-source', action='append', dest='apply_sources',
                help='Apply this acquired source ID to the current work; repeat for several sources. '
                     'Other acquired sources remain available in work-basis.json for comparison and selection.')
            parser.add_argument('--feature', action='append', dest='features',
                help='Feature applied to an initial task; repeat for several features.')
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
