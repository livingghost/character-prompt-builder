# Scenes

One scene plot per file, as `<scene-id>-plot.json`. A scene plot is where the story meets the
coverage, which is why it sits here with the narrative and not with the artifacts made from it: it
is written from the narrative, and the shot artifacts are written from it.

A scene plot records its purpose, setting, viewpoint, presented beats, preserved conditions,
creative freedoms and realization. It names its chapter, order and source narrative hash. Cast,
explicit themes and arc lists can be empty; no exchange or relationship change is required.
`turn` is optional and can describe persistence; `state_changes: []` means no lasting consequence.
An observation or held condition does not need an invented person or reversal to count as a scene.
Declared references, visible-beat support and source approvals remain enforceable.

A unit is a shot, a page, or a passage, depending on what the series is made of. The narrative's
`medium` decides which, and a scene realized in another kind is refused.

It names no target and no model. The interface is chosen after the plot is approved, because a
plot written once the interface is known takes that interface's limits in as though they were
story decisions, and nothing afterwards can tell the two apart.

```
python <skill>/scripts/scene_plot.py narrative/scenes/<scene-id>-plot.json
python <skill>/scripts/scene_plot.py narrative/scenes/<scene-id>-plot.json --content-sha256
```

The second prints the hash the approval block has to carry. A shot submission names its scene plot,
and the gate refuses a submission whose plot is missing, unapproved, edited after approval, or does
not contain the shot being submitted.

## Reusable scene preparation

Keep a reviewed scene-persona plan and its generated `material.json` / `persona.md`
beside the scene or in a named local material directory. Prepare after reading the
complete applicable Persona, authorial intent, world and current state. Preserve
actual definition text and conditions, not only section links or trait summaries.
Select it via production task `features: ["scene-persona"]` and `scene_materials`.
The whole originals are pinned, including text not excerpted. New scope or changed
sources requires preparation review; local rewrites within the scope reuse the
prepared document. See [Scene Persona Material](../../../references/runtime/scene-persona.md).
