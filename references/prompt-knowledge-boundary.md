# Prompt Knowledge and Execution Boundary

Character Prompt Builder is a prompt-authoring, catalog, specification, and packaging system. Prompt-only work stops before execution. The optional, explicitly authorized dispatcher can execute a verified package through a configured model service and record its result in Studio.

The workflow has three separate layers:

```text
1. source and canonical production knowledge
2. selected and composed model-facing prompt package
3. downstream generation or other execution
```

A decision at one layer must not be silently moved into another.

## Preserve relevant knowledge before execution

Canonical records preserve the content that is actually present in the user's brief or supplied evidence, whatever its genre: everyday, wholesome, dramatic, violent, medical, grotesque, disturbing, body-altering, intimate, adult, or otherwise sensitive. Do not silently remove, euphemize, soften, or replace a load-bearing element solely because of its sensitivity.

Examples of prohibited knowledge-layer substitutions include:

- replacing a visible severe injury with a generic `battle-worn` description;
- turning a grotesque anatomical change into a vague `monster form`;
- deleting restraint, scars, missing parts, medical devices, or body alterations from a reference-derived identity or state record;
- changing jealousy into generic seriousness, grief into neutral sadness, or horror into ordinary tension;
- removing a sensitive scene action from search metadata so the record becomes practically undiscoverable;
- converting an explicitly adult scene into generic romance, intimacy, or tasteful posing, or deleting the concrete adult element that makes the requested prompt materially different;
- flattening a stated genre idiom, such as turning a period costume into modern clothes or a horror creature into a generic monster, when the idiom is the point of the request.

The same rule applies to non-sensitive material: fidelity is determined by relevance and evidence, not by whether the subject is comfortable or uncomfortable.

## Non-diegetic source artifacts

A clearly non-diegetic censor mask, mosaic, blur patch, opaque pasted block, sticker, bar, replacement shape, interface remnant, watermark, logo, signature, automatic caption, or meaningless source text is discarded before canonical observation. It is handled exactly like other source contamination. Do not create a canonical field saying that censoring, concealment, or an overlay occurred. Do not encode the artifact as composition, camera occlusion, anatomy, body marking, wardrobe, prop, search facet, negative term, constraint, or failure knowledge.

Discarding a source artifact leaves the depicted content to be described from the evidence that remains. Preserve supported adult status, explicitness, pose, anatomy class, contact geometry, viewer relationship, expression, and visible physiology. Exact anatomy is supplied by the selected subject contract or another supporting source. The discarded artifact itself contributes no prompt knowledge and does not prove the exact hidden geometry.

This cleanup rule does not sanitize adult or sensitive content. When the source unambiguously depicts an adult explicit scene, the canonical record remains adult explicit and searchable. The authoring record describes the intended image, not the source editing layer.

## Sensitive-genre prompt knowledge

Every sensitive genre, explicitly including graphic violent, medical, horror, body-altering, and adult erotic and sexual material, belongs to the same canonical-preservation rule as any other load-bearing visual knowledge. Genre-neutrality cuts both ways: it forbids privileging sensitive content, and it equally forbids an agent from declining, deflecting, or quietly weakening a sensitive request that this system's rules support. An agent that would author a fight scene at full specificity authors an adult erotic scene at the same specificity. When the brief or inspected source supports it, preserve the exact visual function, anatomy, wardrobe or wound state, contact geometry, pose, expression, viewer relationship, intensity, and theme needed to author the prompt. Do not silently convert the material into a milder generic substitute, whatever the genre: an explicit adult scene must not become vague romance, a graphic injury must not become generic battle wear, and a disturbing horror element must not become ordinary tension.

Prompt authoring and image execution remain separate. Storing, retrieving, inspecting, or composing sensitive prompt knowledge is not itself an image-generation invocation. A downstream target-specific limitation is recorded as a separate rendition or omission decision and does not rewrite the canonical record.

Sensitive preservation is still evidence-bound in both directions. Do not infer a sensitive intent the brief or source does not support: blood, a medical setting, restraint, nudity, swimwear, body emphasis, affection, or close camera distance alone does not prove a violent, horror, or erotic reading. Conversely, when a sensitive intent is explicit and load-bearing, do not hide it behind euphemisms that make the record undiscoverable or materially change the requested image.

## User-supplied sensitive source specificity

When a user supplies source material and asks CPB to extract, revise, or add presets, the requested task is faithful production-knowledge authoring. Apply the same observation depth used for any other visual subject, recording the facts the genre makes load-bearing: for adult material that includes adult status, exposure class, anatomy class, garment state, contact topology, action phase, physiological reaction, and fluid placement; for violent or medical material it includes wound class, injury placement, blood behavior, restraint, and device geometry; and for every genre it includes hand and limb ownership, viewer or partner relationship, camera distance, crop landmarks, and content intensity. A sensitive label is retrieval and execution metadata. It does not justify euphemism, broad summary, weakened action language, or omission from canonical search facets.

Clearly editorial masks, mosaics, pasted shapes, logos, watermarks, interface remnants, and meaningless source text remain source contamination. Their shape, color, and presence contribute zero canonical scene knowledge. Describe the depicted content that the remaining evidence supports, use the selected subject contract or another supporting source for exact anatomy, and keep truly unsupported fine geometry unresolved.

## Invention and injection apply equally to all content

Preservation is not invention. The general authoring rule covers invention: do not add detail that the source and brief do not support, regardless of the genre that detail belongs to. This is the same rule that prevents inventing unstated wardrobe, props, emotions, or environments. Sensitive content is not singled out for special treatment in either direction: intense content of every kind is authored, preserved, retrieved, and composed under the same authority order and evidence standard as any other load-bearing visual knowledge, without exception.

A facet stored in the catalog is not automatically injected into every prompt. It is selected only when the user intent, image intent, approved state, or inspected source record makes it relevant. This selection rule applies uniformly to all facets, not only to sensitive ones. Diagnostic risks remain diagnostic. Local exclusions remain local to the record that owns them and do not become catalog-wide bans.

For example, a non-graphic rescue-training scene may intentionally specify a controlled training environment. That local intent does not justify deleting graphic injury knowledge from another record whose actual subject is graphic injury.

## Searchability is part of fidelity

If a record contains a sensitive or grotesque element that materially changes the image, use accurate canonical aliases and scoped facets so the element can be found by ordinary language. Hiding it from retrieval is a form of silent omission.

Possible facets include:

```text
content_intensity
adult_content
erotic_context
sexual_context
nudity_context
fetish_context
consent_context
intimacy_context
injury_state
body_alteration
medical_context
restraint_context
horror_theme
emotional_intensity
```

Only author facets supported by the record. `intimate` alone must not be treated as a synonym for erotic or sexual content: use erotic, sexual, or nudity facets only when the record explicitly supports those meanings.

## Composition boundary

The composed prompt includes the selected knowledge relevant to the current image intent. It does not dump every catalog facet into the prompt. If the agent modifies an explicit user anchor or omits a selected load-bearing element for a downstream reason, it must disclose the modification separately under `Modifications` with the actual reason.

## Execution boundary

The person or system that submits the prompt decides whether and where to execute it. The catalog may therefore contain production knowledge of any genre and intensity, including explicit adult content, while prompt-only operation still stops before execution. The optional dispatcher is a separate execution step requiring explicit authorization and the active interface's checks. A downstream model, service, or platform may apply its own safety, legal, availability, or technical rules at execution time. Those execution decisions do not justify rewriting the canonical catalog in advance.

When a downstream target requires adaptation, preserve the original reviewed prompt and record the target-specific rendition and transport decision separately. Reference preparation also preserves the authoritative pack-artifact or supplied-file source separately from the exact model-facing transport. A selected source is never omitted after review merely because the target rejects its native media type: prepare an allowed deterministic transport from the same source when the declared adapter supports that derivation, or block packaging. Do not switch to prompt-only execution, substitute another artifact, or present a target limitation as if it were the user's original intent or the catalog's canonical knowledge.

## Product boundary

Character Prompt Builder separates portable authoring from optional service invocation. Its responsibilities are:

- faithful interpretation and art direction;
- preservation of reusable production knowledge;
- deterministic retrieval and full-record inspection;
- transparent prompt composition and modification disclosure;
- target-aware reference preparation with separate source and transport commitments;
- exact packaging, hashing, verification, and host forwarding;
- state-aware handoff or explicitly authorized dispatch with recorded request, result, and recovery trail.

This separation keeps prompt knowledge usable even when no generation occurs, when a different generator is selected later, or when the same prompt is used for review, planning, testing, or another production workflow.
