# Authoring work

Compose and amend actual candidates through
[`authoring_work.py`](../../scripts/authoring_work.py) for a
prompt delivered in conversation, a saved artifact or a model request. The work
contains the current request, acquired source material, its applications and
the actual content being authored. The same author develops the character,
chooses the construction and judges the result. Studio provides saving and
execution when those operations are requested.

## Contents

- [Begin from the current request](#begin-from-the-current-request)
- [Apply sources to this candidate](#apply-sources-to-this-candidate)
- [Compose or amend actual content](#compose-or-amend-actual-content)
- [Compare actual candidates](#compare-actual-candidates)
- [Inspect and deliver](#inspect-and-deliver)
- [Save or execute the same work](#save-or-execute-the-same-work)

## Begin from the current request

Preserve the actual request in a UTF-8 file. Read supplied material in its
assigned role and use [Production direction](production-direction.md) to
establish the character, intended effect and meaningful creative scope. Develop
open details within delegation. A concise definition can supply everything the
current depiction needs; elaborate it when a later choice needs more. Use
[definition wording](prompt-vocabulary.md#define-a-character-with-usable-wording)
to investigate dictionary terms while developing those details, and retain the
inspected meanings and authored phrases with their definitions.

Begin a candidate with the available request and sources:

```bash
python scripts/authoring_work.py begin --operation compose --request request.txt \
  --source character=definition.md --application "character=character#" \
  --subject lead=character --out work.json
```

The files in this command contain this task's actual request and definition.
The application selects the definition's content; `lead` names the character
using it. Use the relevant number of subjects and source applications. The
command can also begin partially resolved work with only the material currently
available. `inspect` exposes the current content and selections. Add the next actual
choice through `context` as the work develops:

```bash
python scripts/authoring_work.py context work.json --source character=definition.md \
  --application "character=character#" --subject lead=character
```

Ask the user when a consequential choice needs their decision. Otherwise make
a coherent provisional choice, show a useful proposal and continue. Complete
the definition needed for this artifact before its finished export. A character
may be human, animal, creature, machine, personified matter or another designed
entity. Use its actual body or functional assembly and expressive channels.

## Apply sources to this candidate

The source catalog retains acquired material. `basis.applications` owns which
parts are active for this candidate. Each application selects a source and a
JSON Pointer; an empty pointer selects the complete source. Text and binary
sources use the empty pointer. A JSON source can select one exact value with
an RFC6901 pointer, as in `--application "design=source#/definition"`.

Use `--subject SUBJECT=APP[,APP...]` to associate a character with its concrete
source applications. Use `--requirement APP` for a source application that
carries a retained requirement. Keep the complete source available for context
while applying the portions that govern this work. An identity application
carries its adopted character properties; the current construction chooses
how to depict them. A full-body source can support a close view, and one
rendered example can support another presentation within its assigned scope.

Use `context --remove-application APP` or `--remove-subject SUBJECT` to update
those current assignments. Keep subject and requirement references consistent
within the same update. The acquired source catalog remains available for
comparison and later selection. Repeated `--requirement APP` arguments replace
the current requirement selection; its actual ID list can also be edited in
the basis when clearing that selection within authority.

Capture a changed source and update its application when the work adopts that
change. The owner checks source hashes and pointers against the acquired
content. Read the actual definitions and their allowed scope; a successful
binding establishes which material is applied, while the author judges its
meaning and suitability. Carry the relevant visible definition, bodily
relationships and researched wording into the candidate's actual prompt or
selected references.

For a deliberate adaptation, acquire the adapted actual text or JSON under a
separate source ID and select that source for its intended use. Retain the
original in the acquired catalog with its applicable requirements and authority.
This keeps both the original material and the authored adaptation available for
comparison, with an explicit current application.

The default `focus` is `character`. For an explicitly commissioned supporting
setting, background or similar artifact, select `--focus supporting-setting`
from that request. That work can contain no depicted character. This choice
records the artifact being commissioned; open character work proceeds through
its character definition. `check` and `export` require the current request and,
for character work, subjects linked to applied source content. Beginning and
inspecting work allow these choices to develop progressively.

## Compose or amend actual content

Choose the operation from the current request and the relationships it retains
or reopens. `compose` begins an actual candidate from the current request and
source applications. Supply a drafted rendition with `--prompt FILE`, an
applicable negative with `--negative FILE`, or a complete JSON content object
with `--content FILE`. Otherwise develop the initially empty content directly.
An earlier candidate can remain available as comparison without supplying the
new candidate's current choices.

`amend` starts from the actual baseline content supplied with `--baseline FILE`.
For an existing authoring work, extract its actual content to obtain that file:

```bash
python scripts/authoring_work.py extract previous-work.json --pointer '' --out baseline.json
python scripts/authoring_work.py begin --operation amend --request request.txt \
  --baseline baseline.json --source character=definition.md \
  --application "character=character#" --subject lead=character --out work.json
```

Apply the requested change and its necessary consequences to that candidate.
Retain the baseline choices that the current request keeps. The significance
of a change comes from its effect on the construction and requirements; a
property name does not select the operation. A change in the intended experience
may call for another organization of the picture. A well-directed picture can
benefit from a bounded correction.

Edit `content` in the work file, or use the commands that update that same owner:

```bash
python scripts/authoring_work.py edit work.json --operation add --pointer /prompt --text-file prompt.txt
python scripts/authoring_work.py edit work.json --operation add --pointer /documents --value-file documents.json
python scripts/authoring_work.py replace-text work.json --pointer /prompt --old-file selected-text.txt --new-file replacement.txt
```

Choose `add`, `replace` or `remove` for the actual JSON operation; `replace` is
the default. `add` and `replace` take exact UTF-8 text with `--text-file` or a
JSON value with `--value-file`. `remove` takes no value. The selected value and
its enclosing structure determine the operation's effect; other values retain
their contents. `replace-text` changes the selected text within the
current string. The owner derives the difference from the actual baseline and
current content. Keep one actual content owner; extract its bytes when another
tool needs an intermediate text or JSON file.

Use `extract` for intermediate content needed by vocabulary lookup, settlement
or an unfinished baseline:

```bash
python scripts/authoring_work.py extract work.json --pointer /prompt --out prompt-for-lookup.txt
```

It reads the actual current value while allowing unfinished context, and reports
`state: intermediate`. Continue the investigation or edit from those exact bytes,
then use the completed export when delivering the final prompt.

## Compare actual candidates

When the user requests alternatives or a broad reconsideration, use the actual
work files to compare the proposed constructions as they develop. Begin each
from the applicable request, character definitions and retained requirements.
Keep a candidate's authored choices open at that candidate's owner until their
contribution to the commission has been assessed. The comparison can include
unfinished candidates; develop them far enough to read the consequential
relationships without completing their incidental details.

```bash
python scripts/authoring_work.py compare work-a.json work-b.json --out comparison.json
```

Supply the works being considered. The operation reads their actual current
values without editing them. It resolves each request, selected subject
definition and requirement, the complete candidate content, other applied
material, and any comparison baseline. Read the request and definitions, then
the complete inputs together: prompt text, references, controls and selected
documents all contribute to the proposed result. A baseline remains comparison
material or an amendment's starting content according to the work's operation.

The report's `common` and `differences` derive equal and differing values at
JSON Pointers within each candidate's `view`. Objects and arrays retain their
actual relationships, and an absent value is distinct from `null`. Applied
material outside subject and requirement assignments appears under
`other_applications`. Its shared values can reveal an organizing choice that
all candidates have already selected. Source pointers, original digests and
provenance remain visible alongside the selected values; equal wording alone
does not establish equal source authority. Unapplied catalog material remains
at its acquired owner.

Use this shared view to judge what each complete construction makes the viewer
encounter and whether the common choices themselves serve the commission.
A shared planning note or repeated rationale supplies no comparison of actual
pictures. For broad reconsideration or requested alternatives, identify a
common authored choice that is narrowing the constructions under consideration.
Distinguish it from the request and adopted definitions. When that governing
choice remains open, construct an actual candidate that resolves it another
way before choosing among the resulting inputs. Follow the change through the
whole depiction so its consequences can be compared. The choice comes from
these candidates and this commission; it is not a fixed category to vary.
Develop the consequential question without enumerating every open detail.
Retain shared choices when the comparison supports their contribution to the
request. Select or present the candidates the task calls for, using their
realized differences and fit rather than their names or count.

The report is derived working material with `state: intermediate`. It neither
completes the inputs nor judges artistic significance. Its `work_digest` values
identify the JSON works read, and `baseline_changes` exposes each actual change
against an available baseline. Continue through the original work files and
refresh the comparison after relevant edits. The report supplies no second
editable candidate, required rationale field or creative-quality gate. A
routine bounded amendment can proceed through its existing edit and inspection
operations.

## Inspect and deliver

Inspect the actual work and complete its current input checks:

```bash
python scripts/authoring_work.py inspect work.json
python scripts/authoring_work.py check work.json
python scripts/authoring_work.py export work.json --pointer /prompt --out prompt.txt
```

Inspection exposes the request, applied sources, subjects, retained requirements,
baseline, current content and derived difference. Check the complete candidate
against the request and source roles through
[Observe and repair](production-direction.md#observe-and-repair). For a revision,
[Revision contract](revision-contract.md) inspects the same work. The scripts
check content, source bindings and structural relationships. The author judges
whether the construction and its actual wording satisfy the commissioned result.

Export the requested pointer from the current candidate. A string exports as
its exact UTF-8 text; structured content exports as JSON. A completed `/prompt`
or `/negative` export checks the candidate's whole prompt input through
[Prompt-only core](prompt-only-core.md), including its selected target's grammar,
required real vocabulary work and selected documents. This applies to a final
prompt delivered in conversation as well as a saved file. For an explicit pack
runtime, give `--state-file`, `--cache-dir` and `--managed-root` together, with
repeatable `--pack-root` for additional roots. Present the completed result in
the requested form. The specialized exporter reads the same work when a prompt
package is requested.

## Save or execute the same work

For saving or execution, use [Production authoring](production-authoring.md).
`draft-inputs --operation compose|amend` exposes the same authoring work through
the Studio's editable choices. Supply a changed commission with
`--request-file FILE`. Continuing the same commission can use its saved request.
The registered work goal names the task for navigation; the actual request is
retained for production and review. Source applications determine the active
sources projected into the saved task.

The Studio stores the acquired basis in `work-basis.json` and the actual
candidate in `choices.json` with its selected editable files. `context.json`
records those locations. Acquire or update the request and source material
through the same context command, selecting the basis file explicitly:

```bash
python scripts/authoring_work.py context STUDIO/work/draft/work-basis.json --basis-only \
  --request request.txt --source character=definition.md \
  --application "character=character#" --subject lead=character
```

This changes the acquired basis and derives its hashes while retaining the
candidate's editing sources. Use the Studio's `inspect-inputs --choices FILE`
to inspect their combined current work. `draft-inputs --apply-source ID` can
apply an already acquired source when starting a saved branch. Use this same
acquisition and application operation for a separately authored adaptation.

Use the Studio's [current-work comparison](production-authoring.md#keep-branches-and-reopen-completed-work)
to read several saved editable candidates through this same owner:

```bash
python scripts/production_workflow.py compare-inputs --root STUDIO \
  --choices work/first-draft/choices.json --choices work/second-draft/choices.json
```

It resolves the current delivery and selected documents, including task-local
definition edits, before calling the common comparison. The intermediate view
keeps the source choices and saved history intact.

When the compiler materializes a JSON sub-selection, the compiled task source's
`path` names the selected JSON. Its derived `origin: {path, sha256}` identifies
the complete acquired original. The source's `applications` is the public
selection contract, derived from the common basis: each entry contains its
`id`, original JSON `pointer`, assigned `subjects` and `requirement` boolean.
The projector orders applications by application ID and assigned subjects by
subject ID. These derived orders remain stable when the basis is saved and read
again. One application produces its value itself; several produce an array of
their values in that canonical application order. An authored sequence remains
an array within the selected source value.

The snapshot checks the complete original's hash and verifies the ordered
applications and projected content against the acquired basis. Acquiring an exported
task restores each application's pointer, subject assignments and requirement
individually. Two characters using different parts of one original therefore
retain their separate applications. Canonical identity metadata keeps the
authority of its adopted definition. The compiler derives these files and
bindings; update the common applications or acquire changed material through
the context command.

For a task-local definition derived from the currently selected Production
Specification, `source.definition_owner` identifies
`{document: "production_spec", subject_id: ID}`. The compiler derives this
relationship so that task reacquisition restores the actual editable subject.
Changes to that subject's identity or its removal update the applied definition
and subject relationships. A composition that retains an earlier definition
as independent acquired material uses that source's ownership. Canonical and
external definitions likewise keep their own owners.

Save the actual authored revision or prepare its exact model input. Follow
[Production workflow](production-workflow.md) for the requested operation and
its completion. Previous revisions retain their requests, source evidence and
results; the current candidate receives the choices selected for this work.

A public ProductionTask selects the acquired basis with `work_basis`, a path to
that actual basis JSON. The input compiler supplies this path for normal saved
work. When authoring a task directly, acquire its basis through the same core
commands and extract its actual basis:

```bash
python scripts/authoring_work.py extract work.json --basis --out STUDIO/work/basis.json
```

Select `work/basis.json` as the task's `work_basis`. This extraction is an
intermediate artifact. Draft inspection allows unfinished context;
completed checks, saving and preparation require the actual request, applicable
character definitions and consistent applications. They capture the current
delivery and selected documents, then check the task sources and current
Production Specification against those acquired selections. Correct a missing
request or definition at its owner; correct a differing application or document
at the actual selection that owns it.

The editable structure follows
[`authoring-work.schema.json`](../../schemas/authoring/authoring-work.schema.json).
Use `python scripts/authoring_work.py --help` and a command's `--help` for its
exact arguments and diagnostics.

[`test_authoring_work.py`](../../scripts/test_authoring_work.py) exercises actual
composition, exact changes, source selection and completed candidate export.
