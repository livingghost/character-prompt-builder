# Midjourney and Niji Adapter

Use this adapter only for an active Midjourney or Niji model record. Complete [Image Generation Runtime](../runtime/image-generation.md) first.

## Prompt rendition

Read the [Prompt Writing Guide Runtime](../runtime/prompt-writing-guide.md) before final rendition. Use its interface-neutral hierarchy and controlled-comparison rules, but keep platform parameters under this adapter and do not treat Stable Diffusion brackets as Midjourney or Niji emphasis syntax.

For Midjourney, use a concise content-first prompt and place platform parameters at the end. Preserve the chosen image intent, subject relationships, composition, and medium thesis rather than reducing the prompt to disconnected tags.

For Niji, use concise anime-oriented phrasing with explicit character performance, spatial relationships, and color hierarchy. Do not import anime phrasing when the selected medium is not anime.

Platform parameters go after the prompt text, each written as the flag and its value. The version flag names the active record's version, `--v` for Midjourney and `--niji` for Niji. A stylization of `--stylize 100` is a neutral working point. `--raw` tightens adherence to a stated treatment where the record's version supports it. The aspect ratio goes through `--ar` from the record's declared ratios, and the native negative subset through `--no`.

## Negative transport

Use `native-subset`. Transmit only the verified native negative subset through `--no`. Retain the complete portable negative in the package for traceability, but never claim that the full negative was sent to the platform.

## Reference and parameter forwarding

Use only media, reference count, and parameters declared by the active model record and endpoint. Keep platform parameters outside the descriptive sentence hierarchy. Forward the verifier's exact effective prompt, native subset, parameters, and committed reference carriers. Stop rather than dropping or averaging a planned reference.
