# Revision Contract

Activate this route for a local fix, a requested alternative, a model/interface conversion, or an explicitly approved identity change. The operator chooses meaning; `scripts/revision_contract.py` checks the declared structural difference, not prose quality or whether an image actually obeys a prompt.

## Operation and authority

This contract governs changes to an identified baseline. An assessment or a
repair recommendation alone is not an edit instruction. Use
[Observe and repair](production-direction.md#observe-and-repair) to establish
the intended result, the material the request authorizes changing and the
requirements it preserves before projecting changes into paths.

The baseline records the depiction being changed; its presence does not make
every choice permanent or approved. A local property edit preserves surrounding
choices because the requested operation is local. A correction to the event,
function or overall effect can require coordinated construction changes within
that correction. A request to reconsider the construction can reopen selected
means while preserving explicit requirements and adopted design. Derive that
scope from the request and applicable approvals. Follow a changed choice's
consequences through the same construction. Preserve genuinely frozen choices;
ask for the smallest necessary decision when those conflict. Feedback that
redirects the review calls for reassessment; it does not itself specify an
image edit.

`edit` is the default. Preserve the current baseline except the requested paths and necessary consistency repairs, each with a disclosed reason. "Change the eyes to blue" does not reopen clothing, lighting or camera. `explore` may change non-frozen axes only when alternatives were requested. `retarget` keeps structured semantics exactly equal and changes wording/target settings separately. Any target limitation that changes meaning must return for approval as an edit, not be hidden in retargeting.

Temporary clothing belongs to `/scene/outfit`. Explicitly fixed wardrobe belongs under `/identity/fixed_wardrobe`. Preserve `/identity` and `/identity_slots` during scene work; an outfit-only edit must not regenerate the approved identity images. A model-specific outfit reference can be added under outfit authority without making it identity. These namespaces are the canonical revision projection; include all meaningful baseline decisions, including source hashes, and never omit an inconvenient decision to evade the diff.

Retaining an agent-invented draft choice during a local edit is not permanent canon. An explicit identity change needs `scope: identity` and a `canonical_approval` recording `by`, `at`, `baseline_sha256` and `candidate_sha256`. This is separate from plot approval and from the image-adoption approval. A scene edit cannot obtain identity authority simply by listing an identity path as requested.

## Input and commands

```json
{
  "operation": "edit",
  "scope": "scene",
  "baseline": {"identity": {"face": "unchanged"}, "identity_slots": {}, "scene": {"eyes": "green", "lighting": "soft"}},
  "candidate": {"identity": {"face": "unchanged"}, "identity_slots": {}, "scene": {"eyes": "blue", "lighting": "soft"}},
  "requested_paths": ["/scene/eyes"],
  "frozen_paths": ["/identity", "/identity_slots"],
  "consistency_changes": []
}
```

```bash
python scripts/revision_contract.py revision.json --out revision-report.json
```

Use `--help` for the CLI. `requested_paths` and `frozen_paths` are non-root RFC6901 JSON pointers. Each optional `consistency_changes` entry has exactly `path` and a nonempty `reason`. Objects are compared recursively; arrays are atomic so reordering cannot hide a change. Replacing an ancestor does not count as a permitted child edit. Output includes `ok`, `operation`, `scope`, exact `changed_paths`, both hashes, disclosed consistency changes and errors. Invalid input or an out-of-scope change returns nonzero.

Build the candidate from the intended result through
[Select the depiction](prompt-composition.md#select-the-depiction). Describe the
corrected appearance, action, relationship or degree and its necessary premises.
The baseline supplies the meaning and selected properties the change preserves;
evaluate its wording against those requirements. Preserve required identity,
useful context and exclusions at their subject, region, time and modifier scope.
A direct exclusion can supply a complete boundary. An exploratory prompt may
reconsider incidental choices within its delegated scope. Removing an
instruction needs no replacement permission or contrary statement.

Interpret image sources for their assigned contribution through
[Construction order](prompt-composition.md#construction-order) and bind the
actual delivered media under [Reference Delivery](reference-delivery.md).
Rebuild the affected passage, then apply the
[complete-input readback](prompt-composition.md#prompt-assembly-and-review).
Judge the whole result against the current request and the requirements the
change must preserve. Carry those requirements into candidate review and
complete a satisfied repair. Record semantic changes and necessary consistency
repairs through this contract. Observations, change history, story-management
decisions and reasons stay in their owning records.

When materializing a revision, pass `--revision-contract revision.json` to `build_prompt_artifacts.py`. For a Generation Package include the same object as `creative_intent.revision_contract`; both builder and verifier validate it. Render the final prompt from the approved candidate semantics and preserve all actual reference commitments. Source-preservation or change instructions concern the images actually supplied. Structured validation does not prove that an independently written prompt faithfully describes the candidate; the executing agent must compare them.

Return the complete current prompt, applicable negative and reference deliverables after a revision. Return a diff only when requested, or retain the deterministic report as production evidence. Do not reinterpret "another target" as "another character" or reuse an approval after its bound content changes.

## Failure and regression

Unrequested changes, altered frozen fields, semantic changes during retarget, scene changes to identity, and missing/mismatched canonical approval block delivery as a completed revision. No generation or canonical mutation is performed by this validator. Run `python scripts/feature_workflow_smoke_test.py` for local edits, exploration, conversion, ancestor replacement and scene-outfit isolation. Run `python scripts/prompt_artifact_smoke_test.py` for draft versus generation-preparation boundaries.


## Artifact evidence and completion

Complete the operation actually commissioned under [Production workflow](production-workflow.md), preserving this document's interpretation, retrieval, authority and adoption boundaries. An authored plan, prompt or design uses [Authored storage](production-authored-storage.md): save its exact revision and perform delivery or review when requested. Model execution instead prepares its exact input, captures the actual result and binds review and selection to that result. Canonical adoption records its own decision and destination.

`production_workflow.py status`, `impact` and `resume` expose current dependencies, artifact integrity and the next action. Close the owning work task when its requested result is complete. A search hit, saved revision, generated image and adoption each establish their own scope.
