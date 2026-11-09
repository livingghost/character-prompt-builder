# Production review

Observe the actual artifact before comparing it with the commission and applicable sources. Record independent evaluation and any actual repair or selection decision against that artifact.

## Review, disposition and selection

Production owns the evaluation and disposition of its candidates.
The Studio reads the same records; its iteration ledger keeps the candidate identity, media references and adoption history, not another verdict.

```sh
python scripts/production_workflow.py draft-review --root STUDIO --run RUN --candidate CANDIDATE --out review.json
python scripts/production_workflow.py review --root STUDIO --run RUN --file review.json
python scripts/production_workflow.py draft-disposition --root STUDIO --run RUN --candidate CANDIDATE --out disposition.json
python scripts/production_workflow.py disposition --root STUDIO --run RUN --file disposition.json
python scripts/production_workflow.py candidate-status --root STUDIO --run RUN --candidate CANDIDATE
```

A review names the actual reviewer, observations, the criteria assessed so far, optional supplemental `evidence`, repairs, unresolved matters and a conclusion.
Each observation names its `evidence` (`candidate` or a supplemental evidence ID), a locator, the observed fact, its interpretation and limitations.
Additional evidence entries record path, kind, relation and limitations; their bytes are measured and pinned, not trusted from filenames.

### Observe before interpreting

First inspect the actual candidate and record what it visibly or measurably
establishes, with locators and limits. When a separate reviewer context is
available, give it the candidate and only the technical information needed to
access the relevant file, page, region or stream. Withhold the brief, prompt,
expected portrayal, earlier failures and production history until that first
observation is recorded. `workspace --phase observe --candidate CANDIDATE` supplies only the saved candidate bytes, their access paths and measured media information. Give that view alone to the first observer. The later `workspace --phase review --candidate CANDIDATE` supplies the assessment basis. Even the compact editing draft contains criterion identifiers, so keep it out of the first observer's input.

Then compare the observed depiction with the commissioned result and applicable
source or reference evidence. Use the prepared criteria and allowed variation
within that authority. Additional inspection may answer a
criterion-specific question; keep those later observations distinguishable from
the first reading in their `limitations`. Preserve the direct observation in
`observation`, its meaning against the criterion in `interpretation`, and the
unsupported or uninspected scope in `limitations`. Record the actual reviewer
input boundary and reading order in the review's `conclusion` and relevant
observation limitations. These existing fields require no new record format.

Inspect at the scale the judgment requires. A whole-image view can establish
composition while leaving a small connection, boundary or count unresolved.
When that detail decides a criterion, inspect the available original pixels or
an appropriate region while retaining enough surrounding context to understand
the relationship. A crop or enlargement helps only when it reveals relevant
evidence; it cannot establish detail absent from the source. Record a supported
verdict when the evidence resolves the claim, and retain `indeterminate` when it
does not.

If the same context produced and reviewed the work, state that this is author
self-review and not independent. Describe the artifact before applying the
expected reading, while retaining the limitation that the intent is already
known. An instruction to forget that intent does not erase it. Input-limited
review also remains an interpretation, not a controlled blind comparison; the
[Blind Image Evaluation Protocol](../blind-image-evaluation-protocol.md) owns
study design and release claims.

A face oriented toward someone does not alone show eye contact; cropped eyes
can leave it undecided. A still stance does not establish a path of motion, and
a smile alone need not distinguish the requested emotional state. Assess the
artifact against what its evidence can establish. Use `indeterminate` for an
inspected criterion with inconclusive evidence and `not-assessed` for one not
inspected. Do not infer a pass from the prompt, the intended story or a valid
request. A valid prompt and a rejected candidate can coexist. A different
composition may pass when it preserves the same anchors and allowed variation.

### Apply the prepared review basis

For image inputs, the review workspace includes the original source images and each prepared delivery carrier available in the run. Carrier evidence retains
the source assignment, transformation, attachment position and board region;
external inputs also retain the exact request field. Several logical
references may share one saved carrier while keeping their individual
authority scopes. Compare the candidate against the image and region that
carry each requested attribute, and use the original source to assess what
the preparation preserved. Missing or changed saved bytes fail integrity
validation. The submission evidence separately establishes whether those
prepared inputs were sent.

The review workspace presents the prepared purpose and intended effect once, followed by each criterion's evidence kind, applicable selected realization, craft questions and accepted variations. The editing draft contains unanswered observations and verdicts, with empty reasons. Write the actual judgment there. Its `evidence` list is for additional authored sources; the runtime resolves prepared source and carrier evidence automatically, using the stable IDs shown in the workspace. The formal review retains all effective evidence and its saved bytes. Source records establish what was commissioned; observations
establish what the candidate supplies. Assess the chosen realization and the
returned result against the commission and applicable source requirements.
Accept a suitable alternative that meets those requirements; assess the actual
effect when a renderer follows choices that miss the request. Review the basis
of a mistaken criterion in the same assessment and revise the responsible task
through its existing authority before formal selection. Preserve inherited
identity, necessary use conditions and the scope of any authorized local edit
when correcting a criterion grounded only in the author's chosen means.
Keep uncertainty about an unsupported judgment in the review's limitations.
An intentionally ambiguous portrayal is itself assessable when the artifact
requests it. Changes to a live task leave this prepared review basis unchanged.

For adopted identity sources, the `decision` and `review` workspaces include
the frozen `identity_coverage` report in their assessment basis. It preserves original
values, grouped selections, subject scope, effective scene treatments and the
exact text or media carriers bound to each criterion. Original source bytes
remain available as `identity-source:SOURCE_ID` evidence, including sources
derived from selected state or reference owners. The report is comparison
context, not a verdict; the editing draft still begins unassessed. Neither the
candidate-only `observe` view nor the blind `input` view includes this context.
When source scopes share the same original bytes, the workspace includes that
original text once. Later scopes name its first source ID in `content_ref`
while keeping their own scope, pointer and saved access path.

Use the applicable original definitions, conditions and relations to establish
the character being depicted, including requirements inherited by this scene.
Assess each required whole-subject criterion against that source independently
of the prepared prompt and extracted checks. Record a supported pass when the
candidate preserves the adopted construction within the commission's scope,
including through a different suitable realization. Retain the original definition for
`not-exposed` and `not-applicable` scopes, with the scene treatment and visibility
limits in the existing observations and reasons. Assess discrepancies and
uncertain details by their effect on the applicable identity requirements and
selection. Keep nonblocking uncertainty in observations, reasons or limitations
and optional improvements in proposed repairs. Use `unresolved` for issues that
need resolution or explicit owner acceptance before selection, including
findings beyond the extracted criteria. A necessary repair describes the
construction or relationship the revised result should show at the affected scope.

A passing identity criterion must cite the actual candidate in its required
medium. An effective `unresolved` binding blocks a pass for its criterion and
the affected subjects' whole-identity criteria; resolve its owning source or
scene choice in a newly prepared input, or retain the actual nonpassing
assessment. More specific authored treatments determine the effective scope.
Omitting a required whole-subject check, or leaving it `not-assessed`, cannot
permit selection or be waived as an assessed departure. A supported
whole-subject pass remains limited to the depicted identity that this scene's
evidence establishes.

Locators are `whole`; `description` with text; one-based inclusive `lines` or `bytes`; `image-region` with normalized x, y, width and height; or `time`.
A `time` locator names an integer stream index and decimal-string `start_seconds` and `end_seconds` within that measured stream.
A motion check needs a nonzero video interval, and audio needs an audio stream.
Neither whole-file labels nor two still images prove the motion between them.
Text or binary evidence cannot pass an image check.

Each criterion gets one verdict:

- `pass` cites observations that support the criterion's declared evidence kind;
- `fail` records a decisive failure, which may come before other criteria are assessed;
- `indeterminate` means the reviewer observed the criterion and could not decide; it cites observations like `pass` and `fail`;
- `not-assessed` leaves the criterion unassessed and permits an empty reason; every judged verdict needs a reason. `not-applicable` excludes the criterion with its explanation.

The candidate's latest review sets its evaluation, by the first row that applies:

| Latest review | Evaluation |
|---|---|
| none, or every criterion `not-assessed` | `unreviewed` (the review reference is kept) |
| any `fail` | `nonconforming` |
| any `indeterminate`, or an unresolved issue listed | `indeterminate` |
| some criteria not assessed | `partially_reviewed` |
| every criterion `pass` or `not-applicable` | `conforming` |

These labels summarize all recorded criteria, including advisory ones. They
do not decide selection eligibility. An advisory failure or an inconclusive
advisory observation can coexist with supported passes on every hard criterion.
Keep the limitation and any optional repair visible rather than changing its
verdict to obtain a preferred aggregate label. The owner's explicit acceptance
can permit selection of assessed departures or uncertainties under the rules
below; the candidate keeps its actual evaluation.

Disposition is a separate axis: `pending`, `not_selected`, or `selected`, from the candidate's latest decision event.
A disposition file allows `pending` and `not_selected`; only `select` establishes `selected`.
Not selecting a candidate says nothing about its quality.
After completion, `not_selected` can retire an existing candidate that the
Studio no longer holds as its accepted image. The run retains its original
completion and owning task state. A later disposition of the delivered
candidate withdraws its current selection for further adoption; completion
verification still checks the selection and evidence recorded when the run
completed. Repeating the same disposition returns its existing receipt.
Returning a candidate to `pending`, recording another review or selection,
and starting new production require an open run. Abandoned runs keep their
existing closed decision policy.
Each review event names the review it follows in `previous_review`, and submitting the latest review again records nothing.
A synthetic candidate rejected on one failed criterion, with the other left unassessed (trimmed):

```json
{
  "candidate": "43c4d65069b4...", "candidate_sha256": "d035bda74f89...",
  "evaluation": "nonconforming", "disposition": "not_selected", "unassessed_criteria": ["output"],
  "review": "7a64a5f4e4dd...", "decision": "4f422dc3f32d...",
  "reviewed_at": "2026-10-03T19:02:37Z", "decided_at": "2026-10-03T19:02:44Z",
  "selection_current": null, "selection_diagnostics": []
}
```

`selection_current` is true or false for a selected candidate and null otherwise.
`selection_diagnostics` names `SELECTION_REVIEW_CHANGED` or `SELECTION_REPLACED` when a selection is not current.
`status` reports the same states for every candidate.
`selection_basis` distinguishes `review-pass` from `owner-allowance`, and
`owner_acceptance` exposes the recorded allowance. `selection_requirements`
retains the latest review's `unassessed_hard_criteria`,
`nonpassing_hard_criteria` and `unresolved_indices`; acceptance does not erase
those findings.
## Review, repair and a new run

The same review carries repairs (`id`, decision IDs, observation indices, operation, changed targets, reason).
Identify the responsible layer from the observations before choosing the
operation. [Production direction](production-direction.md#observe-and-repair)
connects the criterion, construction, presentation and rendition. A wrong
temporal phase or spatial relationship can require rebuilding the scene; an
incidental facial or garment edit cannot establish an event the view cannot
show. Use a local correction when the mismatch is local, and retain uncertainty
when the evidence does not isolate a cause.
Draft from the source run, edit the responsible authored choices and build
the revised task. Preserve the earlier input and candidate evidence.
`revision-intent` compares the whole prepared input, checks the reviewed scope, and returns an exact `edit` payload:

```text
python scripts/production_workflow.py revision-intent --root STUDIO --run RUN --task revised-task.json --candidate CANDIDATE --repair REPAIR_ID
python scripts/production_workflow.py revise --root STUDIO --run RUN --task revised-task.json --candidate CANDIDATE --repair REPAIR_ID --authorization EDIT_AUTHORIZATION
```

Authorize the returned edit intent, then `revise` creates a new run linked to the parent candidate, latest review, repair and exact changed input.
The new run needs its own direction and submit authorization and real evidence.
Its preparation transfers none of the parent's passing checks or permission to send.
Changed approval evidence requires new authority, not a repair that grants itself more power.
## Deterministic pixel realization

Read [Image Editing](image-editing.md) for the `image-edit` feature.
Its exact intent binds the plan, pinned input pixels, latest reviewed repair and new PNG path to an existing edit authorization.
This creates a candidate in the current run, not a new selected direction or an inherited review.
Contract changes still use `revision-intent` and `revise`.
Retained image outputs can be republished without rerendering.
## Inspectable production evidence

After capture or review, a requested inspection export uses the same prepared sources, consumer, receipts and bytes through [Evidence Review](evidence-review.md).
Exporting a report or study is read-only with respect to production and canon.
Exported observations never authorize a new action; continue decisions through the authority-bearing workflow.
