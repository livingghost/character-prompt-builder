# Authored revisions

An authored result is the text or JSON the author writes. Its save, actual
delivery and review are separate facts about one immutable revision. Select the
results requested for the current task in `authored.requirements`: `save`,
`delivery`, and `review`. The default is `save`. `authored.completion_state`
defaults to `finished`; select `draft` when unfinished work satisfies the actual
request. Every revision records its saved bytes. Completion checks both its
requested state and all requested results.

## Edit and save

Use the editable choices from `draft-inputs` and the text files named there. The
author supplies the content, material use and assessment basis. The input owner
resolves selected material, captures source bytes, assigns stable reference use
IDs and compiles the current choices.

```bash
uv run python scripts/production_workflow.py save --root STUDIO --choices INPUT/choices.json
```

This saves a finished authored revision. `check --choices` runs the same compiler
without publication. `prepare --choices` also uses that compiler; when its task
is authored, publication records the saved revision. The returned `run` names
that revision and `artifact` names its exact saved text. Saving does not claim
that anyone received, read or approved it.

To retain unfinished work:

```bash
uv run python scripts/production_workflow.py save --root STUDIO --choices INPUT/choices.json --draft
```

A draft retains the current text, source files and unresolved choices. It is not
a completed model input and needs no completed target vocabulary record. A
task can finish on that saved draft when `authored.completion_state` is `draft`
and its requested delivery and review also exist. For example, a commission to
save and deliver an unfinished artifact uses:

```json
{"requirements": ["save", "delivery"], "completion_state": "draft"}
```

Those are the task's `authored` choices. Saving with `--draft` retains the
unfinished artifact; it does not change a request for a finished result into a
draft request. Delivery preserves the saved state. To continue,
use `draft-inputs --from-run REVISION`; the input owner restores editable source
files, then a later save publishes a new revision. The previous revision and
its records remain unchanged.

If publication succeeded but recording the save was interrupted, recover that
fact with `record-save --root STUDIO --run REVISION`. This records the existing
artifact and does not create another revision.

## Finished prompt targets

When the result is a prompt for a particular model, set `authored.target.model`
to the selected catalog definition, or `authored.target.model_file` to the
evidenced definition file. Read that selected model through the operation's
normal reading path. Its selected service and execution mode, when applicable,
determine the prompt syntax together with its input contract. Declare those
choices once in `authored.target.service` and `authored.target.execution_mode`;
use `authored.target.parameters` for required mode selectors. An explicit
`authored.target.syntax` asserts that resolved syntax. It cannot override the
model's supported interface.

The finished save checks the exact primary and negative text with the shared
prompt grammar. A model whose contract requires tag retrieval also requires an
actual retrieval record in `authored.target.vocabulary_record`. Known suitable
dictionary terms take precedence over invented equivalents; an uncovered term
can still be selected with its meaning and basis recorded through the vocabulary
owner. Editing either text invalidates an earlier selection for those bytes.

Plain text uses the entire delivery file. A JSON result can identify its prompt
with `authored.prompt_field`, an array of keys or indices. An optional negative
input uses `authored.negative.path` and, for JSON, `authored.negative.field`.
These selectors describe the current source; the compiler captures the actual
bytes. A portable authored document without a selected target omits
`authored.target`.

## Deliver the saved artifact

For a local delivery, choose the requested Studio-relative destination:

```bash
uv run python scripts/production_workflow.py deliver --root STUDIO --run REVISION --to deliveries/artifact.txt
```

The command copies the exact saved bytes and records the completed local file
delivery. It records whether that artifact is a draft or finished result.
Production's publication namespace belongs to the saved run owner; choose a
delivery destination outside it. An existing file with different bytes is a
conflict. If the copy completed before an interruption, retrying the same
command verifies the file and records the same delivery without overwriting
other content. The event retains the bytes that were delivered, even if the
destination is edited later.

## Record external presentation or attachment

After presenting or handing over the saved artifact, record the actual evidence:

```bash
uv run python scripts/production_workflow.py deliver --root STUDIO --run REVISION --file delivery.json
```

The receipt follows
[`production-authored-delivery.schema.json`](../../schemas/authoring/production-authored-delivery.schema.json).
It names `recipient`, `channel`, `note`, and `evidence.path`. If the evidence is a
JSON host record, `evidence.field` selects the presented text or actual attachment
handle. When recording text presentation, that selected text must match the
saved revision exactly. When recording attachment delivery, also name the
actually attached Studio file in `artifact`; its bytes must match the revision
and the selected host evidence must contain the actual nonempty delivery handle.
Use the host's real records. A copied receipt template or a planned delivery is
not evidence of an external action.

The command snapshots those files and binds the delivery to this revision and
its actual saved state. It
does not send a message, infer a recipient acknowledgement, or mark another
revision delivered. A delivery can be recorded later even if a save-only task
has already completed; its original completion remains a statement of what was
known at that time.

## Review the saved result

Read the saved artifact before assessing it against the task's criteria and
source basis. The current request supplies those criteria; the text under
review cannot define its own success. A model-ready prompt review concerns the
image it instructs the model to produce, as well as any required format. It is
not a claim that a generated image has already been observed.

```bash
uv run python scripts/production_workflow.py workspace --root STUDIO --run REVISION --phase input
uv run python scripts/production_workflow.py workspace --root STUDIO --run REVISION --phase review
uv run python scripts/production_workflow.py draft-review --root STUDIO --run REVISION --out review.json
uv run python scripts/production_workflow.py review-authored --root STUDIO --run REVISION --file review.json
```

The input view exposes the artifact before the assessment basis. The review
view supplies the original commission, its criteria, current direction and
criteria, and complete saved source evidence. `source:ID` identifies the
captured original when the author edited a source rendition;
`adaptation:ID` identifies that separate rendition. Restoring an authored run
retains the originals even when the working source files have since changed.
An optional `build-inputs` export carries the same captured basis in the
generated task's `authored_basis` and its copied original files, following
[`production-authored-basis.schema.json`](../../schemas/authoring/production-authored-basis.schema.json).
Preparing that exported task uses the same evidence as saving its editable
choices. The materializer derives those paths and hashes.

The unanswered form and recorded review use the existing
[`production-review.schema.json`](../../schemas/authoring/production-review.schema.json)
and its evidence validator. The form derives `input_sha256` and `candidate`;
for authored work, `candidate` identifies the saved artifact digest and creates
no generated candidate event. Name the `reviewer`, add actual `observations`
with evidence IDs and locators, and cite those observations from the criterion
`checks`. `candidate` evidence is the saved artifact. Source evidence is
available by the IDs above; the form's `evidence` accepts additional actual
reviewer material. The runtime snapshots that material before recording the
assessment and checks observation ranges against those bytes.

Keep the review's observed facts, interpretations, limitations, repairs and
unresolved questions explicit. Omitted criteria remain unassessed under the
common review contract. A requested review assesses every criterion, but does
not require a passing verdict or approval. Failed and indeterminate findings
can satisfy that assessment requirement. An unreviewed or partially assessed
artifact still needs its requested review. Status reports those states as
`unreviewed` and `partial` rather than treating the review event as completion.

## Complete and continue

```bash
uv run python scripts/work_ledger.py finish --studio STUDIO --run REVISION
```

Finishing verifies the revision's save, requested `authored.completion_state`
and each result requested by `authored.requirements`. The authored owner records
its ordinary completion event when those facts satisfy the commission; no
separate completion command is needed before finishing the work task.
`production_workflow.py complete` remains available to record that result
without closing the work task. Authored completion does not require an
external-generation candidate, selection, character slot or fictional handoff.
Work-task completion consumes that verified result. Finish each work step and
resolve open author questions before closing the task.
Changing the text publishes another revision; delivery and review of the prior
one never complete the new one. `status` reports the saved state, delivery,
review and outstanding requested result separately.
