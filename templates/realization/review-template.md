# Realization Review

Author-facing working record. Fill the relevant fields from an actual inspected candidate: no
imagined observations, retrospective claim of planned intent, required score or automatic
adoption. A single image, a passage, an unpeopled work or a nonvisual artifact can use the same
review.

## Actual artifact and review boundary

- **review_id_and_scope**:
- **candidate_file_and_hash**:
- **actual_inspection_locator**:
  <!-- Page/line, frame/region, time range or another exact inspected span. State uninspected parts. -->
- **reviewer_and_available_input**:
  <!-- Name the actual reviewer and what it received. A fresh first observer receives the
       artifact and access information, not the prompt, criteria, expected portrayal or history. -->
- **reading_order_and_review_limits**:
  <!-- Record whether direct observation preceded the criterion context. If the production
       context also reviews, say author self-review, not independent. No blind-study claim. -->
- **observed_output_before_comparison**:
  <!-- Concrete observed words, sound, movement, geometry or omission, with locators.
       Preserve this first reading before adding criterion-specific interpretation. -->
- **unobserved_or_inconclusive_properties**:

## Contract comparison

- **plan_bundle_and_source_fingerprints**:
- **authorial_intent_refs**:
  <!-- Applicable exact local Markdown intent links; n/a with reason when no such entry applies. -->
- **persona_or_world_identity_and_phase**:
  <!-- Cite the applicable original definition and its concrete response rules.
       A sheet summary or generated prompt does not replace that owner. -->
- **expected_state_and_boundary_conditions**:
  <!-- Identify the selected condition, available information, audience, degree and
       reaction phase where they affect the portrayal. Keep internal feeling, intended
       display and what must be visible distinct; concealed feeling need not leak. -->
- **reference_role_and_applicability**:
- **recipient_information_boundary**:

- **expected_portrayal**:
  <!-- The requirement and selected effect this span must communicate; cite its source.
       For conditional performance, identify the selected concrete realization,
       relationships that distinguish it, held features and prior permitted variation.
       Keep the stable individual definition and current depiction's choices in scope. -->
- **criterion_specific_observations**:
  <!-- If further inspection follows the criteria, mark that reading order and its limits.
       Do not overwrite the original observation with the expected interpretation.
       Inspect the relevant whole configuration and local channels together, using only
       declared structures. Name required relationships the framing cannot establish. -->
- **interpretation_and_verdict**:
  <!-- Link each judgment to observations. Inspected but inconclusive is indeterminate;
       uninspected is not-assessed. Neither is a pass. Compare with the original
       definition and selected current portrayal, including their permitted variation.
       A broad emotion label or plausible alternative story does not establish that
       this individual's selected response was realized. -->
- **difference_and_affected_scope**:
  <!-- Distinguish requirement failure, unobservable property and optional preference.
       A different realization can preserve the required meaning and fixed features.
       Identify that preservation; do not fix every prompt word or relax an adopted
       feature merely to accommodate the candidate. -->
- **evidence_and_uncertainty**:
- **owning_layer**:
  <!-- Source interpretation, observable condition, state, temporal/spatial construction,
       presentation, projection, reference, expression, rendering, knowledge, execution,
       intentional departure or an explicitly unresolved mixture. Not a hidden-model diagnosis. -->
- **departure_decision_or_open_issue**:
  <!-- Cite an actual scoped decision; do not claim accidental drift was planned.
       A useful unexpected performance is a new proposal at its owning definition or
       current Production direction, not retrospective proof of the earlier intent. -->

## Repair and selection

- **smallest_justified_correction**:
  <!-- Rebuild a wrong construction; use a local edit when the mismatch is local. -->
- **dimensions_to_preserve**:
- **upstream_decision_required**:
  <!-- Do not repair a wrong base fact merely by prompting harder. -->
- **retry_budget_and_stop_condition**:
- **previous_and_new_candidates**:
- **comparison_under_same_contract**:
  <!-- Identify changed prompt, references and settings. Several changed variables
       support a setup comparison, not an isolated causal claim. Identify a changed
       definition or selected portrayal as a new basis, preserving the earlier one. -->
- **selected_candidate_and_reason**:
  <!-- The previous candidate can remain selected. A change is not necessarily an improvement. -->
- **actual_adoption_or_no_adoption**:
- **dependencies_to_rebuild_or_reinspect**:
- **remaining_risks_and_uninspected_scope**:

An observation leaves state, JSON approvals and execution approval as they were; each changes
only through its owning procedure. Use the owning decision/adoption/event procedure only after
an explicit accepted change, then rebuild dependent views.


This prose worksheet is a working aid; executable review evidence comes from `production_workflow.py draft-review`, filled with actual observations, then `review` as described by [Production Execution](../../references/runtime/production-execution.md).
