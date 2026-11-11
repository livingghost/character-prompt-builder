# Use adopted Studio artwork as a state-aware reference

A `studio-artifact` source selects a character, sheet slot, immutable artwork and
its exact current adoption. The preparer reads the image hash and approval from
the Studio. Working artwork needs no pack record. Packs remain a choice for
reusable, distributed reference material.

## Choose the current source and its influence

Keep the source choice separate from the state it may control. An adopted front
view may establish identity without prescribing today's clothing, expression or
lighting. Record the allowed influence, visible features, excluded state, story
range and review dimensions. The author decides those values.

This synthetic scope declares an identity anchor, not a current-clothing reference:

```json
{
  "binding_id": "identity-front",
  "role": "identity",
  "effective_story_range": {"from_order": 0, "to_order": null},
  "visibly_supported_state": ["identity-anchor"],
  "unsupported_or_occluded_state": ["current-clothing"],
  "intended_influence": ["identity"],
  "unsupported_assumptions": ["Do not infer current clothing from the identity reference."],
  "review_dimensions": ["identity"]
}
```

Save the reviewed scope in `scope.json`. Supply the actual finalized identity
contract and state snapshot; add era and appearance contracts when the snapshot
binds them. The following reads IDs and hashes from the adopted slot and those
contracts. It neither adopts a candidate nor fills in a missing state decision.

```sh
python scripts/studio_reference.py --studio STUDIO --character hero --slot canon.primary bind \
  --scope scope.json --identity-contract identity-contract.json \
  --state-snapshot state-snapshot.json --out identity-binding.json

python scripts/select_state_references.py --binding identity-binding.json \
  --selection-id scene-identity --identity-contract identity-contract.json \
  --state-snapshot state-snapshot.json --story-order 20 \
  --required-feature identity-anchor --out reference-selection.json

python scripts/prepare_generation_references.py --state-selection-file reference-selection.json \
  --model MODEL_ID --output-dir prepared-references --out prepared-reference-set.json
```

Repeat `--binding` to select several separately finalized binding files. Selection
uses the supplied graph hashes and story range; an out-of-range source cannot
satisfy the required features. Pass the same pack-runtime arguments used to choose
the model into selection and materialization. Feed the resulting prepared set into
the normal state-aware task, then inspect `check` and `prepare` before authorizing
`execute`. See [State-Aware Series](state-aware-series.md) for the complete state graph.

To inspect the current source without a state scope:

```sh
python scripts/studio_reference.py --studio STUDIO --character hero --slot canon.primary source --out source.json
```

The source contains `studio_root`, `studio_id`, `character`, `sheet`, `slot`,
`artifact_id`, `acceptance_sha256`, `proof_sha256`, the exact image path, media type
and SHA-256. Matching pixels alone do not identify the owner or adoption. A new
adoption of the same pixels is a different reference.

An accepted Studio scene can be edited without adopting it as character-sheet
artwork. Select its current slot acceptance explicitly:

```sh
python scripts/studio_reference.py --studio STUDIO --character hero --slot episode.opening accepted-source --out scene-source.json
```

This source has kind `studio-accepted-image` and names the Studio, character,
current slot, immutable iteration ID, original image path and SHA-256, and the
exact acceptance and proof hashes. The proof keeps the original recording slot,
acceptance receipt, retained image and the producing run's candidate and
selection evidence when present. Preparation and a new send verify the current
slot acceptance and both the retained and accepted image copies. A later slot
decision does not change a package's archived proof or its recoverable result.

Slot acceptance grants no canonical identity authority. An edit that also uses
an adopted character identity retains that `studio-artifact` source separately,
with its actual adoption and subject scope. The ordinary edit shortcut selects
these sources through [Instruction editing](semantic-instruction-edit.md#start-from-the-accepted-image).
An arbitrary key in the sheet's artwork registry is not a panel declaration;
the resolved layout and its explicit aliases own character-panel requirements.

A refusal of `source` or `bind` writes no output file and prints
`{"ok": false, "diagnostics": [...]}` with the exit status its codes select in
[Production diagnostics](production-diagnostics.md#exit-codes). For a synthetic
Production adoption whose adoption record was deleted, `source` exits 2 and
prints (trimmed, with the run, candidate and authorization digests written as
RUN, CANDIDATE and AUTHORIZATION):

```json
{"ok": false, "diagnostics": [{"code": "ADOPTION_RECORD_CORRUPT", "phase": "adoption-integrity",
  "file": "characters/robot/adoptions/it-0001.json",
  "message": "The adoption record characters/robot/adoptions/it-0001.json is missing.",
  "required_action": "Repeat the completed adoption with production_workflow.py adopt --run RUN --claim CLAIM. It writes this record again from the adoption result the run recorded and does not adopt the image again."}]}
```

Identity influence uses the existing explicit Studio identity approval and work
character decision. An adopted crop or externally imported image without that
identity authority is not automatically promoted to an identity anchor. Its
allowed nonidentity uses remain available. Adopt or declare identity through the
existing workflow; do not relabel the file as canon to bypass it.

## Deliver several adopted images on one board

For direct Studio references, save the ordered choices without copying hashes:

```json
[
  {"character": "hero", "slot": "canon.primary", "role": "identity",
   "subject_uses": [{"subject_id": "A", "use": "identity", "priority": 0}]},
  {"character": "partner", "slot": "canon.primary", "role": "identity",
   "subject_uses": [{"subject_id": "B", "use": "identity", "priority": 0}]}
]
```

```sh
python scripts/prepare_generation_references.py --studio STUDIO \
  --studio-selection-file choices.json --model MODEL_ID \
  --transport-mode single-board --output-dir prepared-references \
  --out prepared-reference-set.json
```

`single-board` is also accepted with `--state-selection-file`. Select each
character under its own contracts, then combine finalized selections through
`select_state_references.py --selection A.json --selection B.json`. The resulting
`subjects` array retains independent state commitments. Pass all concrete graphs
through `generation.state_graphs` or the state builder's `--state-graphs-file`.
Each graph is fully validated against its subject and the shared scene.

When only A has state history, retain A's selection and add B's ordinary Studio
choices with `--state-selection-file selection-a.json --studio-selection-file choices-b.json`.
For A's pack sources, pass the same B choices to `reference_runtime.py execute`
beside `--reference-selection selection-a.json` and the reviewed pack plan.
B's choices name B's subject uses; they add no state context or graph for B.

The model attachment limit counts the resulting board as one image. Each panel
retains its source identity, original image hash, prepared transport hash, role
and pixel bounds. Source identity and adoption stay separate for two characters
with identical image bytes. Resizing does not claim that a panel's pixels are
byte-identical to the original source image. Review the authored prompt against the board's actual panels and each
subject's `visual_continuity` before approval.

## Preserve current acceptance and recorded recovery

Preparation and every new upload/send boundary check the selected slot's current
artwork and exact adoption. Replacement, withdrawal, altered evidence, an
incomplete adoption or a different owner stops the new external operation.
Adding candidates or changing an unrelated slot does not change this reference.

Withdraw a current adoption with `sheet_workflow.py draft-withdrawal --sheet
SHEET_JSON --slot SLOT --evidence-path AUTHOR_EVIDENCE --evidence-locator LOCATOR
--evidence-root EVIDENCE_DIR --out DECISION.json`. The evidence path is relative
to that root; the tool records its hash. Fill the actual author, time and reason,
then run `sheet_workflow.py withdraw --sheet SHEET_JSON
--decision-file DECISION.json --evidence-root EVIDENCE_DIR`. The exact adoption
and its proof remain in history; current canonical reuse ends. The operation
preserves Studio slot acceptance and does not revoke exported files or registered
packs. Follow [Adoption Workflow](adoption-workflow.md#withdraw-current-canonical-reuse)
for the complete decision and re-adoption procedure. A new approval can adopt
the same retained artwork again, but its new acceptance is a different source;
an old request never silently follows it.

Materialization stores the selected image, adoption decision, evidence and
transitive artwork provenance inside the Generation Package's existing reference
companion. Live verification consults the current Studio; `verify_content` verifies
those recorded bytes. It is not permission for another send.

A run whose answer was saved before a later adoption change recovers from its
fixed package and proof archive. Use `production_workflow.py resume`; never remove
an execution claim or recreate the old source merely to repeat a completed send.
Keep the package companion with the package when moving or recording it.

The freshness diagnostic `STUDIO_REFERENCE_CHANGED` identifies the affected
Studio character, slot and artifact. Prepare a new exact request for new work;
recover already sent work from the original run.

## Keep source responsibilities distinct

`pack-artifact`, `supplied-file`, `studio-artifact` and `studio-accepted-image` are
current source variants.
A pack-artifact uses an active Reference Use Plan. The same executor can retain
direct state references and additional ordinary Studio or supplied sources.
Each keeps its own authority, exclusions and applicable acceptance or adoption
proof. Studio choices use
their actual slots and artifacts; the plan contains only its genuine pack records.

A directory rename or another Studio with the same image does not silently
retarget a live source. A new live location needs a new explicit source selection;
the old package remains auditable through its recorded companion.
