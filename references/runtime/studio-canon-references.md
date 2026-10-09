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

Identity influence uses the existing explicit Studio identity approval and work
character decision. An adopted crop or externally imported image without that
identity authority is not automatically promoted to an identity anchor. Its
allowed nonidentity uses remain available. Adopt or declare identity through the
existing workflow; do not relabel the file as canon to bypass it.

## Deliver several adopted images on one board

For direct Studio references, save the ordered choices without copying hashes:

```json
[
  {"character": "hero", "slot": "canon.primary", "role": "identity"},
  {"character": "partner", "slot": "canon.primary", "role": "identity"}
]
```

```sh
python scripts/prepare_generation_references.py --studio STUDIO \
  --studio-selection-file choices.json --model MODEL_ID \
  --transport-mode single-board --output-dir prepared-references \
  --out prepared-reference-set.json
```

`single-board` is also accepted with `--state-selection-file`. It packages all
references already selected for that state graph; it does not merge unrelated
character contracts into one identity graph. Select each character's state under
its own contracts when a work uses multiple state graphs. The existing state
builder still binds one explicit state graph per package.

The model attachment limit counts the resulting board as one image. Each panel
retains its source identity, original image hash, prepared transport hash, role
and pixel bounds. Source identity and adoption stay separate for two characters
with identical image bytes. Resizing does not claim that a panel's pixels are
byte-identical to the original source image. Review the board preamble and each
subject's `visual_continuity` before approval.

## Preserve current acceptance and recorded recovery

Preparation and every new upload/send boundary check the selected slot's current
artwork and exact adoption. Replacement, withdrawal, altered evidence, an
incomplete adoption or a different owner stops the new external operation.
Adding candidates or changing an unrelated slot does not change this reference.

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

`pack-artifact`, `supplied-file` and `studio-artifact` are current source variants.
A pack-artifact uses an active Reference Use Plan. Supplied and Studio state
references use the direct prepared-set path and preserve the binding's authority
and exclusions. The pack-oriented plan is not a container for fictitious Studio
record IDs. This change neither relaxes pack checks nor changes the state resolver
or the Studio adoption procedure.

A directory rename or another Studio with the same image does not silently
retarget a live source. A new live location needs a new explicit source selection;
the old package remains auditable through its recorded companion.
