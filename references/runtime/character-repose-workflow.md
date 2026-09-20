# Character Persistence and Repose Workflow

## Interface decision before any run

Select the method from the exact active interface. The tag-family, image-to-image and pose-conditioned recipe below applies only when that interface actually exposes those inputs. An instruction-edit interface instead receives the current adopted identity reference, a local-edit contract naming the pose/scene changes, and supported ordinary reference inputs. A text-only interface cannot promise exact identity preservation. Never invent unavailable denoise, mask, ControlNet, or weighting parameters; stop with a portable prompt and declared limitations when no executable interface is available. Any extra bakeoff or second pass requires authorization for its actual prompt, inputs, target and count. Scene clothing does not regenerate identity references. See [Revision Contract](revision-contract.md) and [Adoption Workflow](adoption-workflow.md).

Producing the same character in a new pose or scene on tag-family checkpoints (Illustrious / NoobAI class) without training.

## Why a dedicated workflow is needed

- Image-to-image conditioning locks the pose and the individual together. Pose-change tags lose against the seed image; only state details pass through (blush, sweat drops, expression effects). Raising the strength far enough to break the pose also dissolves the identity, so i2i alone cannot repose a character.
- These checkpoint families often lack structural conditioning channels on hosted platforms - no ControlNet, no IP-Adapter - so line guides and multi-image identity references may simply not be available.
- A character LoRA remains the durable solution once a character graduates to long-term reuse. This workflow covers everything before that point.

## The three-stage repose recipe

Division of labor: the edit model owns geometry through language, the home checkpoint owns style and weight, the graft owns the exact face.

1. **Repose with an instruction-edit model.** Send the character render as the reference image with an instruction built from the preserve-clause template below, following the [Instruction-Edit Adapter](../adapters/instruction-edit.md) for transport.
2. **Restyle with the home checkpoint.** Feed the stage-1 output as the i2i seed at strength near 0.5 with the character's full tag set. The pose lock now works as an ally: pose and layout survive while the house lineart, cel finish, and body-weight tags reassert. Raise toward 0.55 only if the finish stays foreign. This stage cannot fix likeness - the lock preserves stage-1's face as well.
3. **Optional: graft the exact face.** When the face must match a canonical render, transplant the head (or the nose-mouth-eyes unit) from the identity source - canonically the character sheet - with a uniform-scale paste, then run one full-frame pass at strength near 0.32 to fuse the seams. Surgical rules: uniform scaling only, full alpha over the nose-mouth-chin unit, and erase baked expression marks from the base plate before compositing.

### Preserve-clause template (stage 1)

> Change only his pose and expression. [state the new pose, state, and gaze]. Keep everything else exactly as in the image: keep his face exactly the same - the same [muzzle, eyes, brows, ruffs, enumerated]. Keep his [build register] physique exactly the same - the same [enumerated masses], the same body size. Do not make him smaller, slimmer, or younger. Keep the same [coat and marking zones], the same [art style], and the same [background]. Full body in frame.

Both the change-scope opener and the enumerated keep clauses are required. Softer wording ("the same muscular build") lets the engine shrink or youthen the character.

## Selecting an edit engine

Engines change generation to generation; select by procedure, not by name.

1. **Query by capability class.** From the platform catalog, list models flagged image-to-image with an edit operation that follow natural-language instructions (as opposed to mask-only inpainting or plain i2i).
2. **Shortlist.** Prefer the newest generation of each provider's line, keep two or three different providers for diversity in failure modes and moderation regimes, and start from the cheaper tiers - a repose probe costs pennies.
3. **Run a bake-off.** Send the identical instruction and the identical seed image to every candidate.
4. **Audit on six axes.** Pose compliance; facial likeness; physique preservation; style preservation; scene and background compliance; fine-detail integrity at extremities (fingers, toes, whisker zones). Also record which providers accept the register at all.
5. **Use complementary strengths.** One engine often wins the face while another wins the physique or the background. Pick per the current priority, or take the pose from one and graft the face from the canonical render.
6. **Refresh on succession.** When a provider ships a successor line, or the current engine's weak axis starts to bite, re-run the bake-off. Record per-model findings in the model records, which are the versioned layer built to age.

Engine quirks to expect: some constrain output to a fixed dimension list (read the validation error and take the nearest slot); some override scene instructions while preserving the subject perfectly, so restate the background downstream or fix it in the restyle pass.

Moderation differs by provider: some reject bare-torso kemono inputs outright, some reject rendered images of the register in their reference channel while passing line art. Probe acceptance early with one cheap call per provider, and when refused, switch engines rather than iterating against the refusal.


## Artifact evidence and completion

For a saved deliverable, continue through [Production Execution](production-execution.md). Preserve this document's own interpretation, retrieval, approval and adoption boundaries. Prepare the exact inputs, capture the real output, bind review and selection to it, then complete and close the work task. `scripts/production_workflow.py status`, `impact` and `resume` recheck dependencies and artifact bytes. A progress checkbox, a search hit or a newly created image is not production completion or canonical adoption.
