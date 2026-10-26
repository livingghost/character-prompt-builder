## Creative direction

<one concise sentence>

## Prompt

```text
<complete depiction and necessary instructions for actual supplied media, already rendered for the named target when specified>
```

## Negative prompt

Include this section only when the target or user uses a separate negative field.

```text
<necessary exclusions in the target's supported form, preserving their intended scope>
```

## Execution settings

Include only when native request controls are selected. Keep their field names and values outside the prompt text.

```text
<selected native request fields and values supported by the named target>
```

## Reference mode

`<prompt-only | prompt+1 | prompt+N>`

`prompt-only` means no generation API call and zero selected references. A prompt delivered as the final product can still be `prompt+1` or `prompt+N` when useful Visual Evidence is selected.

## Conditional delivered artifacts

Always deliver `final-prompt.txt`. Deliver `final-negative.txt` only when required.

When one or more references are selected, also deliver:

```text
reference-use-plan.json
reference-artifacts/<selected SVG files>
```

Add `surface-lighting-plan.json` only when source lighting or material response must be preserved, rescoped, or replaced explicitly.

Add the following only for a target-specific or generation-ready package:

```text
prepared-reference-set.json
<model-facing raster carriers or single-board output>
```

Do not create empty placeholder reference files. A path or checksum is not delivery.

## Reference review

Include only when references are selected:

- ordered semantic roles and precedence
- exact authority controls and exclusions
- source-state leakage result
- unnamed-averaging result
- source-lighting mode and material response, when applicable

## Assumptions

<only consequential assumptions; omit when none>

## Modifications

<any user-specified anchor changed by the agent, with the actual reason; omit when none>
