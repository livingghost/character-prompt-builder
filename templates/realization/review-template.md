# Realization Review

Author-facing working record. Fill the relevant fields from an actual inspected candidate: no
imagined observations, retrospective claim of planned intent, required score or automatic
adoption. A single image, a passage, an unpeopled work or a nonvisual artifact can use the same
review.

## Contract and evidence

- **review_id_and_scope**:
- **candidate_file_and_hash**:
- **actual_inspection_locator**:
  <!-- Page/line, frame/region, time range or another exact inspected span. State uninspected parts. -->
- **plan_bundle_and_source_fingerprints**:
- **authorial_intent_refs**:
  <!-- Applicable exact local Markdown intent links; n/a with reason when no such entry applies. -->
- **persona_or_world_identity_and_phase**:
- **expected_state_and_boundary_conditions**:
- **reference_role_and_applicability**:
- **recipient_information_boundary**:

## Finding

- **expected_portrayal**:
  <!-- What this span should retain, vary, reveal, withhold or deliberately break. -->
- **observed_output**:
  <!-- Concrete observed words, sound, movement, geometry or omission. Do not substitute inference. -->
- **difference_and_affected_scope**:
- **evidence_and_uncertainty**:
- **owning_layer**:
  <!-- Source interpretation, state, projection, reference, expression, rendering, knowledge,
       intentional departure or an explicitly unresolved mixture. Not a hidden-model diagnosis. -->
- **departure_decision_or_open_issue**:
  <!-- Cite an actual scoped decision; do not claim accidental drift was planned. -->

## Repair and selection

- **smallest_justified_correction**:
- **dimensions_to_preserve**:
- **upstream_decision_required**:
  <!-- Do not repair a wrong base fact merely by prompting harder. -->
- **retry_budget_and_stop_condition**:
- **previous_and_new_candidates**:
- **comparison_under_same_contract**:
- **selected_candidate_and_reason**:
  <!-- The previous candidate can remain selected. A change is not necessarily an improvement. -->
- **actual_adoption_or_no_adoption**:
- **dependencies_to_rebuild_or_reinspect**:
- **remaining_risks_and_uninspected_scope**:

An observation leaves state, JSON approvals and execution approval as they were; each changes
only through its owning procedure. Use the owning decision/adoption/event procedure only after
an explicit accepted change, then rebuild dependent views.


This prose worksheet is a working aid; executable review evidence comes from `production_workflow.py draft-review`, filled with actual observations, then `review` as described by [Production Execution](../../references/runtime/production-execution.md).
