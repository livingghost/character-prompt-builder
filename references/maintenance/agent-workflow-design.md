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

## Changes and dependencies

Recompute deterministic consequences of a changed selection in the owning
builder. Preserve unchanged choices and source evidence. Return unresolved
meaning or authority to the agent without manufacturing a conclusion.
The same rule applies to references, prompt text, direction, criteria,
parameters, rendering, target changes and external requests.

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

## Storage and read boundaries

Give persistence I/O an explicit owner. A consumer receives decoded values for
its operation, rather than rediscovering files whenever it needs the same
fact. Keep these boundaries visible in the API:

| Data | Read owner | Consumers |
| --- | --- | --- |
| Pack state, discovery and selected file contents | `pack_manager.RuntimeInputs` and `PackInput` | Validation, record/resource resolution, catalog persistence and Production snapshot capture use the same acquired input |
| Installed builder sources and schema documents | `builder_inputs.BuilderInputs`, `state_protocol.SchemaDocuments` and `protocol_contract.ContractSet` | One pure evaluator consumes immutable documents and lazy reference resolution bound to their exact contents |
| Registered run and immutable publication | `production_read_model.RunReader` | A shared `RunView` owns prepared inputs, consumer data, manifest-verified bytes, the compiled documents its consumers use and event history |
| Acquired compilation inputs and fixed runtime files | `runtime_snapshot.CompileRuntime` and `FixedRuntimeRead` | Compilation consumes owned catalog and file values; publication preserves the complete selected runtime; a route receipt reads its named resources without reconstructing the catalog |
| Current route documents and prepared live sources | `live_source_read.LiveSourceRead` | One current-input boundary acquires the declared files and passes the same bytes to route receipts and dependency comparisons |
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
The external-effect boundary still forces the current source, authority and
runtime checks before committing its one durable start.

`production_workflow.read_current` acquires actual live sources, fixed runtime
inputs and reference proofs. Authorization, handoff and claim helpers receive
these values and the transaction's current authority explicitly. They do not
look up a retained successful freshness check. A subsequent current-input
acquisition checks the actual files again. Result projection preserves the
same readiness checks, complete audit and next actions as explicit status.
Result capture and sheet publication use the recorded execution target. A
later model-definition edit affects readiness for new work, not recovery of
an image already returned under the prepared target.

One execution may pass its immutable fixed-runtime metadata as an explicit
prior value. Acquisition still reads `snapshot.json` and every declared member,
checks exact membership and current sources, and acquires current authority.
It shares the decoded metadata only after the actual JSON bytes match exactly.
The newly acquired owner contains newly read member bytes. No run publication,
event state, authority or successful check crosses a transaction through this
value. An independent command starts without a prior runtime observation.

Content hashes identify acquired bytes. A read-phase token only ends reuse
inside the current operation or transaction; it is not persisted or numbered.
Do not introduce a version counter or a generated identifier to stand in for
content equality. Keep current grant state distinct from published creative
input, and use the existing event digest to identify a committed predecessor.

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
complete documents delivered by the existing route read. Owning references
retain their full bodies in that read. A link, search hit or available source
file alone does not deliver its context, and the agent must not have to search
backward for a caller's restrictions. Page large reads without omitting sources,
return an executable continuation and issue a reading record only after all
pages have been delivered. Implementation-only maintenance details can remain
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
Report automated contract checks, observed agent behavior, reading volume and
unverified artistic or live-service behavior separately. Evaluate the actual
reading, search, editing and context-reconstruction work needed to finish the
task; a shorter first read alone establishes no workflow improvement. Measured
time and context consumption describe only the task and environment actually
observed.
