# Exact reference delivery

Read this when preparing or inspecting model-facing reference attachments. Package dispatch uses one committed prepared reference set.
Image inputs use the common original-file mapping described in [Semantic instruction editing](semantic-instruction-edit.md).
Dispatcher and external requests retain the same source bytes, subject assignments, order and authority.

## Selection and authority

Retrieve applicable production knowledge and inspect each selected source before preparing it. Decide what the source may control, what it must leave alone, and why this request needs it. Choose only task-relevant sources rather than filling an arbitrary count. A model's observed attachment limit is an execution constraint, unlike a fixed aesthetic reference quota.

A character sheet is a document containing views of its assigned subject.
Use relevant views within the source's declared scope; panel selection need not
be prescribed when several views carry complementary information. State the
target outfit, action and expression separately. Add individual detail images
when needed for legibility rather than enforcing a fixed reference count.

Identity, current expression, wardrobe, lighting, pose and camera are different scopes; a transient state propagates only when requested, whatever identity the source shows. Express each source's `controls` and `must_not_control` authority scopes explicitly. Identical positive and excluded scopes are contradictory and rejected. The script leaves synonyms and semantic conflicts to the agent, who resolves them against the actual source and current intent.

Use `prepare_generation_references.py --image-input-plan-file PLAN --studio STUDIO`
for authored `use_for` and `do_not_transfer` scopes. The plan can pin an existing
prepared set through `prepared_references`. Its source, state, adoption and pack
scope must match exactly. Existing candidates remain candidates until their
actual owner adopts them.

The supplied-selection input is an ordered array with `role`, `source` and
optional `subject_uses`. A synthetic two-character example:

```json
[
  {"role": "identity-a", "source": {"kind": "supplied-file", "reference_id": "a-original",
   "resolved_path": "/absolute/studio/inputs/a.png"},
   "subject_uses": [{"subject_id": "A", "use": "identity", "priority": 0}]},
  {"role": "identity-b", "source": {"kind": "supplied-file", "reference_id": "b-original",
   "resolved_path": "/absolute/studio/inputs/b.png"},
   "subject_uses": [{"subject_id": "B", "use": "identity", "priority": 0}]}
]
```

The preparer measures media type and hashes. Each `subject_id` must resolve to
an actual Production Specification subject. `use` names a canonical intended
influence. Lower `priority` numbers win within the same subject and use;
equal priorities supply complementary evidence. Priority grants no additional
influence and never settles a conflict between different people or purposes.
Leave the array absent or empty for references without a character assignment,
such as a room plan. Multiple characters without story state require no state graph.

One image may carry several subject/use entries. A pack record declares them in
its selected-record decision, for example:

```sh
python scripts/reference_runtime.py plan \
  --record-use '{"record_id":"wardrobe-record","intended_influence":"outfit","subject_uses":[{"subject_id":"A","use":"outfit","priority":1}]}' \
  --transport-mode prompt-artifacts --source-lighting-mode replace --out reference-use-plan.json
```

A state binding limits assignments to its character and declared influences.
A plan narrows them to its selected influence. Studio identity use requires the
matching identity adoption. The Reference Use Plan retains canonical pack
technical authority. Identity use leaves current expression, action and camera
to their target-scene owners.

One prepared set may contain state-aware A's pack references and stateless B's
accepted Studio face and outfit. Execute the pack plan with `--reference-selection`
and append B's `--studio-selection-file` choices, using `--studio` for their owner.
Use `--supplied-selection-file` for direct source choices instead.
Without pack sources, combine `--state-selection-file` with either direct input.
State eligibility covers the managed rows; other subjects require no invented history.
The state row's `subject_id` remains in the model instructions even without optional use priorities.

## Bind the actual transport

The following prepared-set commands apply to reference-runtime and Generation Package delivery.
An external request binds the same logical rows to its declared field paths and upload evidence.

After rendering or copying the actual transports, the reference preparation runtime derives the canonical prompt preamble from their actual order. For multi-image input, identical committed transport hashes and media types share one attachment. Logical reference rows retain their distinct sources, adoption, roles and subject uses. For a single-board input, every logical reference points to attachment 1 and its exact panel rectangle in pixels from the top-left, and a board with several source panels consumes one model image slot in total. Source hashes, transport hashes, roles and panel rectangles must agree with the prepared set.

The map and its prompt text are generated only after those transports exist. The text names delivered sources, assigned scopes and any precedence needed between competing sources. Numeric priorities remain in the binding record; prompt text expresses the relevant order and complementary groups. Do not retain an earlier numbering scheme, hand-rewrite the canonical preamble, or tell a model to use attachment 2 when only a board is attached. The board instruction distinguishes source panels from desired output composition and requests a collage only when the author's target does.

```sh
python scripts/reference_delivery.py --prepared-set prepared.json --package-root WORK
```

This inspection validates the complete prepared set and shows its attachment mapping and canonical instruction; it submits and mutates nothing. Normal preparation uses the same functions through `prepare_generation_references.py` and `reference_runtime.py`; the map is part of the exact preamble bound into generation packaging rather than an operator report alone.

For an external request, prepare the same instruction text from its declared image field paths:

```sh
python scripts/reference_delivery.py --image-input-plan image-input.json --studio STUDIO
```

This reads an existing prepared origin when the plan names one. The rendered location is an exact request field, such as `["images",0,"uri"]`. Include the resulting `reference_preamble` in the authored external prompt. Preparation verifies its presence and the complete image mapping.

For prompt-artifacts, SVG-bundle, or no-reference delivery, never claim that model-visible attachments were sent. An unsupported target or missing selected transport is an explicit failure rather than silent reference omission. Targets and their observed limits are resolved from actual model records rather than fixed service names in this procedure.

Run `python scripts/reference_delivery_smoke_test.py` and the existing reference runtime tests. They test mappings and transport contracts, not whether a generator actually follows them.
