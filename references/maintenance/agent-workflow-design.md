# Agent workflow design

Use this document when designing, changing or reviewing the Skill's authoring,
execution and recovery interfaces. It defines maintenance criteria for the
whole production workflow. It adds no production approval, reading receipt or
checklist to an agent's ordinary task.

## Contents

- [Responsibilities](#responsibilities)
- [One editable source across a task](#one-editable-source-across-a-task)
- [Changes and dependencies](#changes-and-dependencies)
- [Context for judgment](#context-for-judgment)
- [Storage and read boundaries](#storage-and-read-boundaries)
- [Interruption and external effects](#interruption-and-external-effects)
- [Instructions and knowledge](#instructions-and-knowledge)
- [Evaluation](#evaluation)

## Responsibilities

The agent interprets the commission and sources, chooses the depiction, writes
the rendition, assesses evidence and applies actual authority. The runtime
turns those choices into consistent input files, declared references, exact
requests and recoverable records. A normal task must not require the agent to
read implementation code, reconstruct an internal dependency graph, or repair
generated files to make those responsibilities meet.

| Information | Owner |
| --- | --- |
| Required result, source definitions and necessary use conditions | The commission and applicable source authority, interpreted by the author at their scope |
| Selected depiction, intended influence and exclusions | The author, within those requirements and source scopes |
| Prompt wording, supported controls, independent criteria and result assessment | The author, in their respective roles |
| File placement, attachment positions, content hashes, repeated identifiers and request bindings | The owning builder, derived from selected inputs |
| Submission, capture, cleanup and recovery state | The execution runtime, from actual effects and saved observations |
| Permission and canonical adoption | The relevant authority; no builder or saved file invents a decision |

Independent responsibilities do not require independently retyping the same
fact. Keep each meaningful choice at one editable location and derive or
reference its other representations. Preserve a review basis grounded in the
commission and applicable sources independently of the prompt it judges.
Carry inherited identity and state requirements through later requests, while
keeping selected methods open within the task's authority. Judge a rendition
by the required result it provides and the source meaning it preserves.

An authored adoption decision selects its exact result, intended canonical
scope and applicable authority once. The runtime derives the corresponding
approval, operation intent, authorization binding and recovery claim. Keep
actual author judgments and grant conditions in that editable decision;
generated hashes and intermediate records require no manual transcription.

## One editable source across a task

Initial creation, revision and resumption use the same authored contract.
An agent can inspect the current content, change selected choices, and ask the
runtime to build the corresponding task. Drafting from a saved task or run
restores editable content and provenance rather than requiring a new set of
handwritten intermediary documents.

Keep the authored surface appropriate to the task. Show the fields and
selected content that apply, with explicit unresolved choices where necessary.
Do not replace a collection of internal documents with an equally demanding
form containing every possible route's fields. Preserve arbitrary detailed
meaning, literal prompt bytes and model-native values where the contract
supports them; compact authoring does not mean a restricted creative language.

Generated artifacts are inspectable products of the authored input. Give them
stable roles and clear provenance, and keep edits at their owning authored
location. A failure must identify that location and a concrete recovery action.
Adding another report that describes manual coordination does not transfer
responsibility for that coordination to the implementation.

A fresh Studio must be able to author its first input from public instructions,
contract discovery and complete executable examples. Earlier task files are
useful creative sources, never the only available specification of an input.
Selected specialist documents keep one editable file; choices select that file
and any JSON field, while compilation owns hashes and immutable copies.
Expose the actual owning schema or logical contract, permitted and required
fields, remaining contextual checks and the exact file to repair. A generated
context view must not become a second document body to update manually.

## Changes and dependencies

Recompute deterministic consequences of a changed selection in the owning
builder. Preserve unchanged choices and source evidence. Return unresolved
meaning or authority to the agent without manufacturing a conclusion.
The same rule applies to references, prompt text, direction, criteria,
parameters, rendering, target changes and external requests.

Production is a branching process. Preparing, generating, selecting or
completing a result must not make its useful inputs unreachable. Retain the
immutable result, selected evidence and decisions; open an explicitly bound
new authored revision when the commission changes. A later revision does not
rewrite the earlier completion. Several model or prompt trials may coexist,
and the agent must be able to name each editable branch without a latest-file
heuristic silently choosing one. These are shared lifecycle properties rather
than a fixed list of supported rework scenarios.

Separate a result's generation provenance from later curation. A prepared
recording destination describes the original generation; a later placement,
acceptance or canonical withdrawal is an authored decision with its own exact
target and retained evidence. Resolve current placement through one owning read
model. Verify historical completion against the decision and destination it
actually recorded. Retrying that historical operation must not undo a newer
decision. Recovery identifies a captured result by its exact origin, including
the output identity when equal image bytes occur more than once.

Moving between generation, editing and enlargement preserves the selected
source bytes and provenance at their relevant scope. A changed operation
obtains its own applicable input contract, current authorization and criteria;
it does not inherit irrelevant prompt fields or turn a scene result into
canonical character authority. Adding, removing or reordering attachments
changes the selected use and derived bindings without deleting source files
or overwriting the original run. Unchanged reference roles, exclusions and
other meaningful choices remain available.

A reference's use, subject scope, source authority and prohibited influence
remain authored decisions. Attachment order, board placement, relative paths
and hashes follow the selected source content. A setting change must not
require a second editable copy of that setting solely to satisfy a downstream
builder. Independently meaningful evidence retains its own purpose and source.

Do not infer semantic consistency with keyword lists, regular expressions or
feature-specific interpretation tables. Mechanical checks can establish
identities, explicit coverage, constraints and content equality. The agent
judges the relationship between changed meaning and the commission.

Keep service-specific requirements within their adapters. A new supported
service must not silently become a requirement for unrelated production work.
Transport choices follow their declared API contract and existing product
dependencies. A local implementation shortcut does not justify expanding the
Skill's scope or installation requirements.

## Context for judgment

At each phase, expose the commission, applicable source material, current
choices, actual model input, unresolved questions and relevant execution state.
Link to complete original documents and actual images from that view. Present
the applicable requirements and selected means in their distinct roles so the
agent can assess alternative realizations and correct a mistaken criterion at
its owning choice. Reserve selection-blocking issues for matters that need
resolution or acceptance to decide the required result; expose nonblocking
limitations and optional repairs in their existing roles. Separate
the model-facing input from its assessment basis when an independent reading
is needed, then make their relationship available for the decision.

Context is a view of existing evidence. It does not certify comprehension,
perform a review, grant permission or require the agent to re-enter established
facts. Do not make the agent reconstruct these relationships by inspecting a
set of internal JSON files. Do not omit necessary knowledge solely to produce
a smaller response.

Navigation views prioritize current identities, all available branches,
unanswered choices, blockers and executable next actions. Supply complete
decision evidence through explicit phase views; do not repeat the full
request or source bodies in every status projection. Several valid candidates
need explicit alternatives, not a first-item selection disguised as guidance.
Presentation never changes the verified evidence used at an effect boundary.

Keep the cost of a navigation view proportional to the work that can still
proceed, not to the Studio's history. Compare current sources with prepared
ones for the open runs of open work. A completed or abandoned run is shown
from its retained records, and an open run left by closed work is compared
when it is selected. A prepared run keeps its sealed request and fixed
runtime, so later changes to authoring files, reading records, source placement,
the installation or the packs are notices that leave that saved revision
usable. Damage to the run's saved records and current authority restrictions
remain separate execution blockers. A variant or repeat compiles against the current
installation and packs and is told what differs from its parent. Report one
cause once: files that changed
together and share one remedy form one finding that lists them. An inspection
owns the observations its parts share, such as a source run several drafts
were reopened from, and passes that owner explicitly; an effect boundary
acquires its own inputs.

An agent continues from what a command prints, from `--help` and from a search
of the documents and code. Keep the meaning of every reported value within
reach of those three. The report states the meaning or gives the next action
that resolves it. `--help` of the reporting command lists the values of an
axis whose meaning the output does not carry. The routed document describes
the same values in the same terms. A refusal or blocking diagnostic names its
repair in `required_action`: the command to run, the record to correct, or the
choice its author owns. The default action text says nothing about the cause,
so a producer that knows the cause supplies its own. Use a diagnostic code for
the condition its table entry describes, and extend the entry when a producer
gives the code another cause.

A change that adds or alters a state, a reported value, an option, a refusal
or a diagnostic updates these surfaces in the same change. Where a schema or
table enumerates the values, a mechanical check ties the help or document to
that enumeration, so a new value cannot ship unexplained.

## Storage and read boundaries

Give persistence I/O an explicit owner. A consumer receives decoded values for
its operation, rather than rediscovering files whenever it needs the same
fact. Keep these boundaries visible in the API:

| Data | Read owner | Consumers |
| --- | --- | --- |
| Pack state, discovery and selected file contents | `pack_manager.RuntimeInputs` and `PackInput` | Validation, record/resource resolution, catalog persistence and Production snapshot capture use the same acquired input |
| Installed builder sources and schema documents | `builder_inputs.BuilderInputs`, `state_protocol.SchemaDocuments` and `protocol_contract.ContractSet` | One pure evaluator consumes immutable documents and lazy reference resolution bound to their exact contents |
| Registered run and immutable publication | `production_read_model.RunReader` | A shared `RunView` owns prepared inputs, consumer data, manifest-verified bytes, the compiled documents its consumers use and event history |
| Selected saved input revision | `production_saved_inputs.CapturedInputs` and `RetainedSelection` | Variants, reopened choices and registered exports acquire unchanged sources from the selected run; explicit replacements acquire current files. `InputEvidence` retains `@run` source identities and nested evidence bytes in each resulting package, without walking ancestor history. |
| Acquired compilation inputs and fixed runtime files | `runtime_snapshot.CompileRuntime` and `FixedRuntimeRead` | Compilation consumes owned catalog and file values; publication preserves the runtime inputs the compilation bound or read; a route receipt reads its named resources without reconstructing the catalog |
| Current route documents and original source files | `live_source_read.LiveSourceRead` | A navigation or impact observation acquires the declared files and passes the same bytes to route receipts and dependency comparisons |
| Lifecycle transitions and event lookups | `execution_lifecycle.ReplayState` and `EventHistory` | One ordered replay publishes read-only indexes and applies the same rules to a proposed append |
| Current authority | `production_store.CurrentAuthority` | Permission checks consume the checked grant document, owning event and evidence bytes without changing prepared input |
| Studio manifest, iterations, sidecars and run states | `studio.StudioRead` and `studio_reference.ReferenceReads` | Source, identity, continuity, gallery, readiness and status share a read model per canonical Studio root and read phase |
| Rebuildable Studio displays | `studio_activity.operation` | One refresh of the affected views after the owning mutation |

A public read checks the observed content. An outer production transaction starts a
new read boundary and rechecks stored content before deciding a write. Nested
reads share decoded data within that boundary. An own write or rollback
invalidates the retained event history and dependent Studio reads. Existing
read values remain observations of their original inputs. Internal consumers
share deeply read-only values; an editing boundary explicitly exports an
independent graph with `load_run`, `RunView.snapshot` or `owned_json.mutable`.
Pass an existing owned value to later consumers before adding another cache.
Each new transaction or forced acquisition reads and verifies every declared
publication file and decodes the documents its domain consumers need. Decoded
documents and event evidence belong to that read phase. They are not carried
over from an earlier transaction after comparing hashes. A nested fresh read
discards the enclosing scope's retained values before starting and before
returning, including when acquisition fails. Persistent
caches require their own consistency contract and maintenance cost; a new
representation alone is not a reason to add one.
A forced check rereads both publication and event evidence.
The external-effect boundary checks the saved publication and runtime together
with current authority before committing its one durable start. It does not
reacquire mutable authoring files or current Studio placement.

`production_workflow.read_current` acquires the stored run and its fixed runtime.
Authorization, handoff and claim helpers receive these values and the
transaction's current authority explicitly. Source comparisons belong to
`freshness` for navigation and impact; their warnings neither select another
revision nor stop the saved request. Result projection preserves the
same readiness checks, complete audit and next actions as explicit status.
Result capture and sheet publication use the recorded execution target. A
later model-definition edit affects readiness for new work, not recovery of
an image already returned under the prepared target.

One execution may pass its immutable fixed-runtime metadata as an explicit
prior value. Acquisition still reads `snapshot.json` and every declared member,
checks exact membership, and acquires current authority separately.
It shares the decoded metadata only after the actual JSON bytes match exactly.
The newly acquired owner contains newly read member bytes. No run publication,
event state, authority or successful check crosses a transaction through this
value. An independent command starts without a prior runtime observation.

Content hashes identify acquired bytes. A read-phase token only ends reuse
inside the current operation or transaction; it is not persisted or numbered.
Do not introduce a version counter or a generated identifier to stand in for
content equality. Keep current grant state distinct from published creative
input, and use the existing event digest to identify a committed predecessor.

State the baseline and scope of each content comparison. Capturing an edited
authoring file records its current revision; it does not establish the file's
original issuance, the author's identity or approval. Hashes and event chains
stored with the editable local data are consistency records, not an independent
authentication boundary. A dispatcher check covers the acquired request and
the steps it owns; an external host's actual call remains outside that check.
Keep these limits explicit when describing execution evidence.

Resolve inconsistent observations by giving the operation one owner for the
bytes it parses and records. Deriving both values from that acquisition avoids
another comparison and another opportunity for them to disagree. Evaluate
added checks against a demonstrated failure, their blocking scope and their
reading, writing and authoring cost. A stronger integrity claim alone does not
justify more gates, duplicate editable content or manual hash maintenance.

Pack acquisition hashes each selected file while retaining the text that
validation needs. All-file validation, parsed records, resource conflicts and
catalog fingerprints use those same values. Database persistence receives a
resolved `CatalogBuild` and never discovers or reads pack files. Production
snapshot capture reuses acquired text and verifies large binary content when
copying it. A new catalog boundary reads current contents even if file sizes
and timestamps did not change. Disabled packs contribute only their manifests
to discovery.

An imported event export has no verified-store provenance. Check its shape,
sequence, previous digest and content hash before replaying it. A replay
advances indexes once per event; it does not revalidate every earlier prefix
for each later event. Keep transition rules in that replay owner so append and
recovery use the same policy.

Use exclusive atomic publication for immutable files and directories. A
concurrent publisher of identical content can reuse the verified result;
different content at the same destination is a conflict. SQLite owns writer
serialization for its existing event and authority records, including unique
claims and expected predecessor checks. Do not add a filesystem lock around a
SQLite transaction. Keep rendering and network work outside that transaction.

Compile final output values before writing their published representation.
`publication_artifacts.StagedArtifacts` materializes complete private files
and flushes their contents before any file or hard link becomes public. It
flushes nested directory entries together before the exclusive rename.
Publication flushes the destination parent before registering the run. A
failed flush preserves the unregistered stage. Checks consume the same
compiled values and encoding constraints without syncing disposable stage
contents or writing final documents that would be immediately discarded.

Retain owner-scoped exclusion where several existing mutable files form one
read-modify-write operation, such as a character's acceptance journal or the
open work task. State which files the owner protects, and keep unrelated
characters, read-only inspection and immutable publication outside that scope.
A display refresh owns derived files, not permission or the authoritative
record. Nested mutations mark affected views; the outer operation publishes
them once, retains concurrent dirty receipts and reports a repair warning if
publication fails after the formal effect committed.

Writers identify the affected view and subject scope. Routine navigation
verifies the current facts it reports and explains that scope; a complete
historical audit or display repair has an explicit operation. A generated
display may reuse its publication only under an explicit dependency contract
covering actual source content, relevant discovery results and its producing
implementation. File timestamps and event sequence numbers alone do not prove
that those inputs are unchanged. Missing or damaged owned display data is
rebuildable. A display cache never supplies an authority decision, a run's
verified publication or an effect-boundary validation result.

## Interruption and external effects

Save the current authoring location and its connection to published inputs.
Detect later edits by content, including edits to a draft that has already
been built. A newer draft remains discoverable when an older run exists.
Identify each continuation's purpose so that editing, preparing and recovering
an external operation cannot be confused.

Preserve the operation's durable start, response and capture boundaries.
Resuming an uncertain operation recovers that operation's evidence; it does
not authorize another submission. New authored work can reuse creative input
without inheriting a claim, a result review or exact-request authorization.
An existing grant remains subject to its actual scope rather than being
discarded or broadened merely because the agent changed an input file.

Keep an operation's completion tied to the result and scope it established.
Later authorized use of its retained artifact records its own decision while
preserving that completion. Derive continuation guidance and mutation preflight
from the same eligibility rules, and distinguish a source prerequisite from
the authority to act on it.

## Instructions and knowledge

Ordinary instructions teach what to understand and decide, which operation
receives the decision, and how to act on its result. Lead with the intended
content or completed behavior and the actions that construct it. Constraints
refine that positive procedure at their applicable scope. Carry useful choices
into the work, with reasons or qualifications where they affect its use.
Keep ordinary operation specifications and their applicable prerequisites,
authority, constraints, exceptions and recovery instructions together in the
complete documents delivered through the route reader. Owning references
retain their full bodies. A link, search hit or available source
file alone does not deliver its context, and the agent must not have to search
backward for a caller's restrictions. Page large reads without omitting sources,
return an executable continuation and issue a reading record only after the
required bodies have complete delivery evidence. Explicit same-context reuse
can combine earlier complete deliveries with new complete bodies, matching
content and current resource/model scope and retaining per-body provenance.
Changed or missing bodies require full delivery. A fresh context never gains
knowledge from a historical receipt alone. Keep body text, progress and actions
in separate structured fields, including an explicit terminal continuation.
Implementation-only maintenance details can remain
in their owning maintenance references.

Technical specifications and maintenance procedures keep their complete
requirements in their owning references. Contributor and host entry guides
route readers to those sources. Runtime and maintenance instructions obtain
technical prerequisites from the technical references themselves, so their
meaning remains independent of contributor-facing navigation.

Retain specialized production knowledge at the specificity its uses require.
Before moving or consolidating instructions, examine their dependent uses,
examples, failure cases and explanatory roles. Document length or a passing
test alone is no justification for removal. A recorded read establishes
delivery of source content under its contract, not understanding or correct
application to the current task.

Follow Production direction for the picture as a whole: emotional register,
visual language, palette and light, mark and surface treatment, and framing.
A generic draft does not quietly choose a mood, medium or finish, or supply a
shot, body coverage, margin or visibility requirement solely to simplify an
agent's inspection. Leave unselected constraints absent, and validate the
authored values when supplied. Keep templates and resource examples within
their stated use so that a finish, identity inventory or quality check cannot
quietly select the picture. Preserve the author's declared style, adopted scenes
and local edits. Correct the decision process at its owner rather than replacing
an unchosen default with another favorite mood, medium or shot, banning media,
or requiring novelty quotas or random rotation.

## Evaluation

Assess complete agent tasks from realistic briefs and raw source artifacts.
Cover more than the example that first exposed a problem: new authoring,
changed meaning, reference changes, settings, alternate execution branches,
and recovery at distinct phases. Check that the agent can finish without
editing generated files, inspecting implementation code for normal usage, or
manually propagating one choice into unrelated records.

Use independent agents without implementation history where possible. Retain
their actual commands, edits, diagnostics and results. Repair a demonstrated
interface defect in its owning contract, then exercise the affected task.
For creative-direction changes, give fresh agents the Skill and raw briefs
without the diagnosis, desired picture, expected answer or earlier evaluations.
Retain exact requests and each first response before feedback, including failed
or incomplete attempts. Assess each first proposal as a whole against the
brief, including declared style, full coverage when required, selective views,
open briefs, and preservation of an adopted scene and frame during a local edit.
Across the sample, inspect repeated emotional register, visual language,
palette/light, mark/surface and framing, including recurring combinations.
Different subject names or scenes alone do not establish that a default has
changed. Similarity alone is not failure and difference alone is not success.
Repeat with fresh contexts after a consequential correction; keep evaluation
artifacts outside the Skill the next agent receives.
Evaluate open creation with topic-only or actual sparse requests. Added focus,
gestures, mood, medium, palette or spatial scale can cue a picture even without
naming a shot. Select the cases before seeing outputs and retain every outcome.
Keep evidence for following a stated purpose separate from evidence about what
the agent chooses when that purpose is itself open.
Report the Skill revision, model and setup. Recurrence alone does not identify
its cause; limit causal claims to the comparable evidence and cross-model claims
to the models actually exercised.
Report automated contract checks, observed agent behavior, reading volume and
unverified artistic or live-service behavior separately. Evaluate the actual
reading, search, editing and context-reconstruction work needed to finish the
task; a shorter first read alone establishes no workflow improvement. Measured
time and context consumption describe only the task and environment actually
observed.
