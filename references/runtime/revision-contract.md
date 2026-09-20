# Revision Contract

Activate this route for a local fix, a requested alternative, a model/interface conversion, or an explicitly approved identity change. The operator chooses meaning; `scripts/revision_contract.py` checks the declared structural difference, not prose quality or whether an image actually obeys a prompt.

## Operation and authority

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

When materializing a revision, pass `--revision-contract revision.json` to `build_prompt_artifacts.py`. For a Generation Package include the same object as `creative_intent.revision_contract`; both builder and verifier validate it. Render the final prompt from the approved candidate semantics and preserve all actual reference commitments. Structured validation does not prove that an independently written prompt faithfully describes the candidate; the executing agent must compare them.

Return the complete current prompt, applicable negative and reference deliverables after a revision. Return a diff only when requested, or retain the deterministic report as production evidence. Do not reinterpret "another target" as "another character" or reuse an approval after its bound content changes.

## Failure and regression

Unrequested changes, altered frozen fields, semantic changes during retarget, scene changes to identity, and missing/mismatched canonical approval block delivery as a completed revision. No generation or canonical mutation is performed by this validator. Run `python scripts/feature_workflow_smoke_test.py` for local edits, exploration, conversion, ancestor replacement and scene-outfit isolation. Run `python scripts/prompt_artifact_smoke_test.py` for draft versus generation-preparation boundaries.


## Artifact evidence and completion

For a saved deliverable, continue through [Production Execution](production-execution.md). Preserve this document's own interpretation, retrieval, approval and adoption boundaries. Prepare the exact inputs, capture the real output, bind review and selection to it, then complete and close the work task. `scripts/production_workflow.py status`, `impact` and `resume` recheck dependencies and artifact bytes. A progress checkbox, a search hit or a newly created image is not production completion or canonical adoption.
