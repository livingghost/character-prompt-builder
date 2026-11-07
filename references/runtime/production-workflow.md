# Common runtime sequence

Use [Production direction](production-direction.md) to author, assess or revise
the commissioned depiction. The runtime carries that work into saved inputs,
execution and evidence. Conversation-only text needs no generation workflow.
The operations below apply only to the deliverable being made.

## Authoring and handoff

Establish the Studio, open its work task and read the applicable route for saved work. Construct
the depiction through Production direction, consulting composition, source,
performance and other knowledge for the questions it raises. Preserve actual
requirements and source roles. For character reuse, resolve reference coverage
and stage targets. A specification records the selected picture; its fields
are not a sentence-generation order or independent criteria of success.

Read interface guidance; resolve the optional `prompt-writing-guide` and
read the complete selected guide before final rendition. Use it for syntax
and target evidence while preserving the authored meaning. Inspect complete selected knowledge records. A retrieval record contains actual investigated
questions and may be empty when the sources already suffice. Resolve the
execution profile for a dispatcher target.

Judge the final text, applicable negatives, controls and delivered media under
[Observe and repair](production-direction.md#observe-and-repair). Evaluate what
their combined depiction provides for the commission. Agreement with chosen
means alone is insufficient. Retain plot approval and settle retrieval against
the exact wording for generation preparation.

Use `draft-inputs` for the editable production choices, including when starting
new work. A saved task or run supplies its current content for further editing.
Keep the prompt, selected direction, independent criteria, controls and
reference-use choices at their authored locations in that draft. Use
`build-inputs` to materialize the task and its related files, then prepare the
task returned by the builder. The builder owns paths, hashes, attachment
positions and repeated field bindings. Do not repair a generated file to make
a normal authoring change.

A change can require a new judgment without requiring every source document
to change. Assess whether the current plot, criteria, investigated knowledge
and authority still apply. Preserve independent criteria and valid evidence;
change their owning choices only when their meaning or applicability changes.
Detailed choices, invocation forms and unresolved fields are described in
[Assemble authored choices](production-execution.md#assemble-authored-choices).

## Prepare and execute

`production_workflow.py prepare --root STUDIO --task task.json` publishes the
request preview, execution plan and any dispatcher Generation Package.
`check` performs the same compilation without creating a run and is available
when diagnostics are needed; it is not an obligatory duplicate preparation.
Review the actual request and operation targets. Transport changes that affect
the depiction return to the same judgment in Production direction.

Prepared model work uses one compact `draft-execution` document, actual independent decisions and `execute`. Use the current run's `status.next_action` and its context views when needed; complete the existing draft rather than copying records or managing filenames yourself.
During input authoring, `inspect-inputs --root STUDIO` and
`status.current_task.authoring` locate the open task's saved choices, input
files and reading progress, including newer edits alongside an existing run.
Follow [Resume input authoring](production-execution.md#resume-input-authoring)
after interruption, then continue preparation from those inputs.
[Studio authentication](studio-authentication.md) owns the selected service
and the owner's chosen source. Prepare its `api_key` field for saved input or
its `api_key_env` reference for a named environment variable. For saved input,
finish setup, provide the actual path and JSON Pointer, and pause edits while
the owner supplies and saves the value. Check that service and the run's
authentication selection and readiness before continuing. Each service has one
source; the owner supplies its value through that method.

For external image work, `execute` records the separate direction and submission authorizations, handoff and one claim, then returns the exact input for the host to invoke once. `receive-external` consumes the actual response and images, derives hashes and receipt fields, captures each file and settles that call. After interruption, recover the existing host result instead of invoking the tool again. Dispatcher `resume` recovers its existing execution. Production Execution
owns the commands and their scope; all operate under `--root STUDIO`.

## Returned work and completion

[Observe the actual candidate first](production-execution.md#observe-before-interpreting),
then assess what it provides for the same commission and applicable sources.
A faithful execution of a poorly chosen prompt can still miss that commission.
Keep prompt choice, rendition adherence and observed result distinguishable.
Use existing review fields for the supported conclusion, meaningful findings,
input boundary and evidence limits. Inconclusive evidence is `indeterminate`.
An authorized repair addresses the responsible construction or local defect.
Use `draft-inputs --from-run` and `build-inputs` to revise authored content
through the same editing surface used for its creation. Dispatcher trials also
support `variant`, `repeat` or `retarget` for their declared operations. External
trials materialize changed choices into a new task with exact input binding.
Edits need semantic plans. Preserve earlier
candidates and reviews.

When the owner chooses an existing reviewed Production image for its Studio
slot, use `draft-acceptance --run RUN --candidate CANDIDATE --grant GRANT --out
acceptance.json` and `accept --run RUN --file acceptance.json`. Author only the
actual decision, its scope and any explicitly accepted review findings. The
runtime reuses the original run, candidate and iteration, preserving every
review verdict. It records selection, slot acceptance and completion without
another generation or capture. Resume a committed acceptance with `accept
--run RUN`. [Production execution](production-execution.md#accept-an-existing-candidate-for-its-studio-slot)
owns the complete procedure. Close the owning work task with `work_ledger.py
finish --studio STUDIO --run RUN` after its actual steps and questions are
resolved. When the requested result includes sheet or catalog reuse, use its
separate adoption procedure. A later reuse request can adopt the existing
selected candidate after completion or abandonment under its own current
authority; the original production decision and work-task closure remain intact.

`status` reports runs, next commands and execution records. Inspect the
specific run's readiness and next action; top-level `ok` reports only successful
status inspection. After a key-entry handoff, continue the original task from
that run's state. [Operation logs](operation-logs.md) owns inspection, export
and cleanup. Inspect staging before cleanup of its exact owner operation.
