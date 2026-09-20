# ComfyUI Character Prompt Builder: Incorporated Ideas

Reviewed project:

```text
https://github.com/euan-gwd/comfyui-character-prompt-builder
```

This package redistributes none of that project's code, prompt database, or UI assets. It independently adopts several useful product ideas:

- modular person, fashion, action, and scene concerns
- chainable partial construction
- natural-language prompt output
- explicit pose and placement controls
- editable final text

## Difference in this skill

The modules are a later ingredient rather than the starting point. Character Prompt Builder first chooses a coherent art direction from the user's whole brief; presets and modular categories are then optional craft ingredients.

This keeps the workflow from becoming:

```text
select one value from every node
→ concatenate values
```

Instead it becomes:

```text
understand the desired image
→ choose how to stage it
→ use modular vocabulary where it improves execution
```

## ComfyUI routing

After the agent authors the final prompt:

- route the verified prompt to positive conditioning;
- route the negative prompt to negative conditioning when the workflow supports it;
- preserve the exact hashes and creative-intent metadata for reproducibility;
- use model- or checkpoint-specific adapters while keeping the chosen visual thesis.

## Detailed modular control as a design principle

The external CharacterPromptBuilder project demonstrates a useful separation between person identity, fashion, actions, optional hand, leg, and head placement, props, camera, lighting, location, environment, and an editable natural-language render prompt. Character Prompt Builder adopts that modular control principle; the source code and prompt data stay uncopied.

Here, those modules live in an optional production specification after art direction. They are optional rather than mandatory form fields, and the concept is decided before them. A simple image may use only identity and scene controls, while a complex interaction may activate separate left and right placement, contact geometry, and precise camera or light modules.
