---
kind: persona
id: persona-template
name: [name]
character: [the id the narrative gives this person]
references: []
---

# Persona Template (Single Phase)

> This template captures a character completely at a specific point in time.
> One file = One phase. Use this file with its governing intent, world and current-state records to represent this period: for dialogue, prose narration, screenplay, tabletop or role-playing character sheets, illustration and image-generation reference, setting documents, or analysis.
>
> **Design Principles**:
> - **Self-contained portrayal**: Carry enough character content for the declared phase; a persona does not replace the work's world rules, current state, viewpoint or production contracts.
> - **Comprehensive**: Not just speech, but thought, reactions, habits, knowledge, beliefs
> - **Phase-fixed**: This file covers only one specific period
> - **Three Layers**: When writing character traits, distinguish three things that often differ:
>   - **Self-image**: What the character thinks, believes, feels about themselves
>   - **Observable facts**: What they actually do and say
>   - **Outside perception**: How others see them: reputation, first impressions, misconceptions
>
>   §5 MIND is primarily self-image; §12 EXTERNAL is primarily outside perception. Most other sections describe observable traits or factual context. Some sections (§2 PORTRAYAL IDENTITY, §6 THOUGHT, §13 RELATIONSHIPS, §14 MEMORY, §15 UNCERTAINTY) deliberately mix layers, and their comments flag the mix where it matters.
>
> **Language Policy**:
> - Section headings, field names, authoring instructions, and ordinary descriptive prose are written in English by default.
> - Record language-bound evidence in the language and script in which it occurs: first- and second-person forms, honorifics, sentence endings, particles, catchphrases, backchannels, quoted tokens, and dialogue samples.
> - When a field mixes description and exact forms, write the explanation in English and preserve the forms in the character's language. Example: `uses 「私」 in formal settings and 「僕」 only with childhood friends`; `closes requests with 「〜てください」, not 「〜てくれ」`; `switches from French « vous » to « tu » only after an explicit invitation`; `keeps Korean 「-요」 endings with strangers and drops to 반말 only with same-age friends`.
> - These rules are language-general. Japanese and English appear most often in this template's examples only for concreteness; apply the same treatment to Korean speech levels, French or German T-V address (« tu »/« vous », „du“/„Sie“), Mandarin address forms and particles (「您」, 「吧」), Spanish «tú»/«usted», and any other language-bound phenomenon of the character's actual language.
> - Do not replace a source-language form with an English translation and then analyze the translation as though it were the original wording. An English gloss may be added, but it never replaces the original form.
> - For multilingual characters, record each language-bound form in its own language and explain the switching conditions in English.
>
> **Field States**:
> - **Blank** = not yet examined. Default state for unfilled fields.
> - **"undecided"** = examined design choice not yet settled. State what remains to decide; this is a drafting gap, not missing historical evidence.
> - **"unknown"** = examined, but no reliable information available. Write this explicitly when you've looked and come up empty.
> - **"n/a"** = does not apply to this character at all (e.g. combat stance for a pacifist scholar who never fights).
> - **Inference** = not directly attested, but plausibly derived. Write the inference with a brief note of reasoning (e.g. "likely gentle, based on his treatment of stray animals in §13"). Don't guess without marking the guess.
>
>   Overall confidence is tracked at the section level in §19 Certainty Audit. Design adoption is tracked separately; confidence never means creator approval.
>
> **Original-Character Design Mode**:
>
> When `subject_type: original` and the requester delegates invention, design rather than pretend to research. The evidence rules below still apply to supplied facts and already established material; they do not forbid making clearly labeled new proposals.
>
> - Preserve creator-provided anchors. Record new personality, past events, physical details, relationships and dialogue as **proposed**, not as observed facts, creator instructions or adopted canon.
> - Use stable design IDs in §19 Design Ledger for `user-anchor`, `proposed`, `adopted`, `rejected` and `deferred` decisions. Record a statement, its scope, its basis or dependency, and the actual adoption record where one exists. Metadata summarizes the adoption scope; the ledger owns the individual decisions.
> - A request to invent permits proposals; it does not approve them. Selecting a scene or saying a direction is interesting does not automatically adopt every detail in its persona. Record only the approval actually given. Do not carry rejected earlier suggestions forward.
> - Author concrete IF / THEN / BRANCH procedures, vocabulary choices and behavioral probes from those design decisions. In original mode, an `evidence` field may cite a design ID and rationale; it must not invent an episode, quotation, observation or source that never existed. Distinguish a deliberate proposal from an inference about supplied evidence.
> - Mark newly written dialogue and behavior as **hypothetical design sample** and name the rules it tests. It does not establish that the event occurred in the story, and cannot be independent corroboration of the rule used to write it. Do not label an original proposal with ★ as though it were a source quotation.
> - Keep the full twenty-section workspace. During exploration, deepen the fields required by the present creative decision and explicitly retain unresolved coverage. Present useful contrasts and probes rather than a complete questionnaire. The five-example and ten-flow targets guide later depth; they neither block early proposals nor authorize fabricated canon.
> - Separate an individual's own wants, habits and decision criteria from their function in a plot, group or interaction. Species, body size, social status and reputation do not settle temperament. A future relationship plan is not an exception already active in the opening phase.
> - An original persona ready for adoption must have coherent rules, concrete probes, known gaps and an explicit decision scope. An adopted persona contains adopted content or examined unknowns, not unlabeled draft proposals. Syntactic completeness alone establishes none of this.
>
> **World-Coherence Boundary**:
>
> - Use this full form when individualized portrayal is being designed or materially revised; it is not required for an unpersonified place, process, force or decorative crowd.
> - Relate behavior to the work's scoped material, social and informational conditions without treating those conditions as a personality algorithm.
> - Preserve readable contextual summaries for self-contained use, with their source and applicable phase or version. Shared world facts, adopted visual identity and executed state keep their own authority; a summary does not fork or override them.
> - For original projects, link cross-layer decisions to the project design record when one exists. A persona's local Design Ledger continues to own behavioral proposals and adoption scope. A theme is not a command that the character agree with it.
> - Conflicting beliefs, intentional opacity and stable behavior can be designed. Do not add trauma, growth, intimacy, moral agreement or a contrasting personality trait merely to make the form appear complete.
>
> **Individuality and Performance**:
>
> - Individuality lies in a scoped pattern of attention, interpretation, choice and expression, not in a quota of oddities. Similar speech can be intentional; a label, pronoun change or catchphrase is not a complete behavioral design.
> - Use the character-performance runtime to connect this persona to current circumstances and the requested medium. PHYSICAL owns the bodily and vocal baseline, THOUGHT owns conditional responses, SPEECH owns voice modes, and RELATIONSHIPS owns directional exceptions. Cross-reference rules rather than copying them.
> - Emotion, intent, task, addressee, other listeners, role, fatigue, language and communication medium can change speech and body independently. State activation, overlap handling, unchanged features, switch timing, release and residue. Do not assume anger removes politeness or closeness removes formality.
> - A transient response is not a new phase. Author-known feeling, intended display, observable behavior and others' interpretations are not interchangeable. No forced emotional disclosure or body-language truth detector is permitted.
> - Verify scoped rules through concrete examples, changed conditions and a new situation. Record meaningful similarity, uncertainty and gaps instead of manufacturing contrast or claiming semantic quality from filled fields.
>
> **Completion Rule**:
> - **Blank** is a drafting state, not a valid state for a released persona. Before release, every applicable field must contain evidence-backed content (or explicitly adopted original-design content), `unknown`, or `n/a`; optional repeated rows may be removed. A deliberately incomplete draft must be labeled as such, not released as an adopted persona.
> - Do not treat the instructional HTML comments as character data. They remain concrete authoring examples, such as `addresses by name → asks after their state → pauses`, not statements about the character being documented.
>
> **Anti-Bias Protocol**:
> - LLMs have stereotyped pre-trained impressions of well-known characters. "Taciturn" becomes "constantly silent"; a "taciturn" character still speaks when necessary, they just don't waste words. Actual behavior is more nuanced than the stereotype.
> - Do NOT rely on your own impression. For published or otherwise public subjects, ALWAYS search for actual quotes, official materials, interviews, and documented behavior.
> - For original, private, or unpublished subjects, use creator-provided material as the primary record; do not search for or invent external corroboration that cannot exist.
> - Reference user-provided documents when available.
> - Compare your impression against the actual record: they often differ significantly.
> - Fill each section from verified information or explicitly labeled original-design proposals, not assumptions from stereotype.
> - In record-based work, if information is unavailable after examining the available record, write `unknown` rather than guessing. In delegated original design, propose a decision with its basis or mark the choice `undecided`.
>
> **Real-Person Evidence Boundary**:
> - For living or historical real people, private inner-state fields require direct self-report or strong primary evidence. Do not infer diagnoses, sexuality, trauma, secret motives, or suppressed memories from public behavior alone.
> - Example: a repeated refusal to discuss childhood may support `hidden_topics: childhood [observable]`; it does not by itself support `trauma: childhood abuse`. Use `unknown` where the record does not reach.
>
> **Self-Containment Protocol**:
>
> Describe the character precisely enough that a writer can reproduce their choices, speech and behavior from this dossier. Include the context needed to interpret examples and evidence. The following rules apply:
>
> - **Citing a source does NOT authorize omitting the content.** Phrases like "see pegasusknight.com", "refer to the wiki", or "cited in §19" must never stand in for actual information in the body. §19 SOURCES exists for *verifiability*; it is not a license to offload substance to external pages the reader cannot reach.
> - **Distinguish "source of behavior" from "reference to behavior".** A bare quote ("character said X in scene Y") records what was said once, but not how to produce something equivalent in a new scene. Every significant quote must be accompanied by:
>   - The surrounding context (what was happening).
>   - The emotional quality (what feeling is expressed or strongly supported by the scene; mark inference when it is not explicit).
>   - The lexical analysis. For a canonical line (★), explain what the wording observably does and how it contrasts with attested alternatives; do not claim undocumented authorial intent or rejected drafts. For a reconstruction (★★), explain the actual wording choice and the plausible alternatives the persona author rejected.
>   - The nearest documented contrast or boundary case. If no neighboring scene supplies one, write `unknown` rather than manufacturing a contrast.
> - **The author may not hide behind abstraction.** Generalization is necessary, but every general rule must be grounded in concrete observations, contexts, limits, and exceptions. The author must never leave gaps expecting the reader to "fill in the obvious". A downstream reader can compress specifics into generalizations, but cannot invent specifics from generalizations.
> - **Self-containment test.** When the file is complete, ask whether a downstream reader can reproduce the subject's intended portrayal from its explicit rules and the declared current world/intent/state context, without guessing missing source content. A bare citation is not a substitute for a subject-specific rule. This does not require copying the whole world, future plot or secret-bearing source into the persona or a consumer view; keep those owners and information boundaries separate.
>
> **Layered Specification Requirement**:
>
> A usable characterization combines four layers:
>
> 1. **Dialogue database (§16).** Use concrete utterance samples organized by situation. Five total entries per major category is the completion target for a well-documented character, combining short canonical lines (★) and evidence-grounded reconstructions (★★). The count is never permission to fabricate: when the record cannot support five, include every supported entry, add only reconstructions grounded in documented rules, and record the remaining deficit in §19 Known Gaps.
> 2. **Vocabulary registry (§7).** List preferred forms AND specifically avoided forms with exact tokens. "Speaks politely" is insufficient; write `uses 「〜です」, not 「〜ですわ」` or `says “thank you,” not “thanks”`, together with the condition and evidence. Absence from a small corpus is not enough to declare a word forbidden.
> 3. **Decision flows (§6 Action Patterns).** Use IF-THEN pseudo-algorithms for at least ten recurring, evidence-supported situations. Write procedures (`IF challenged after hearing the other out, THEN acknowledge once → give no more than three counter-points → close the topic`), not aspirations (`responds with integrity`). If ten situations are not supportable, do not invent them; document the coverage gap in §19.
> 4. **Prohibitions with concrete contrast (§17).** List likely portrayal errors in the form `× what gets written / ○ what is actually right`, with evidence or a clear boundary. Ground the Anti-Bias Protocol in specific failure modes rather than generic warnings.
>
> **Copyright-Aware Authoring**:
>
> When working with characters from commercial works, do not transcribe long stretches of the original script into the persona file. Instead:
>
> - Quote only short, representative canonical lines; never reproduce whole scenes or monologues verbatim.
> - Extract tone, vocabulary, and decision rules, and fill the body with **reconstruction samples** that follow those rules.
> - Use a visible marker (e.g. ★ = canonical, ★★ = reconstruction in the same style) so the reader can tell which is which.
> - Add a brief note at the end of §19 SOURCES describing this policy, so downstream users understand how the file was built.
>
> **Premise and Canonical-Scope Rule**:
>
> First determine the declared `premise_mode` and `canonicity_scope` in §0 META. Then handle requester-provided premises (lineage, voice actor, class name, relationship status, timeline) as follows:
>
> - When the requester claims canonical or adaptation-specific accuracy and a premise contradicts the controlling record, correct it to that declared record.
> - When the requester explicitly requests an alternate universe, composite continuity, fan-derived continuity, or original character, preserve the intentional divergence and label it; do not "correct" it back to canon.
> - Record factual corrections under `user_premise_corrections`; record intentional divergences under `intentional_deviations`.
> - Cite the source that justified a correction. Example: `Requester said the promotion occurred before the siege; the declared anime continuity places it after episode 18 [P03].`
> - Do not silently overwrite a mistaken premise, and do not mislabel an intentional AU premise as canonical. Transparent scope handling is the only acceptable path.
>
> This rule extends the Anti-Bias Protocol to the request while preserving explicitly chosen non-canonical premises.
>
> **Phase Scope Discipline**:
>
> The author establishes what counts as a "single phase", and once established it must be held. Use already supplied phase constraints rather than asking again. For an existing character with materially ambiguous scope, clarify before making phase-dependent claims. For delegated original design, propose the following as a provisional scope instead of blocking invention with a questionnaire:
>
> - Which period serves as "the present" (before / during / after the main story, or a specific chapter boundary).
> - What the character already knows versus does not yet know at that moment.
> - Their class / title / affiliation in that window.
> - The state of key relationships (still hostile / already reconciled / already separated / etc.).
> - Whether future information may appear at all, and if so, which fields are author-only.
>
> Never silently choose or change an authoritative phase. A provisional original-design phase remains a proposal until adopted. A persona can read like a different person across phases; choosing the wrong one invalidates its use even when the prose is detailed.
>
> **Temporal firewall**: Future facts may appear only in fields explicitly marked author-only. They must not alter the character's current speech, suspicion, knowledge, or motivation unless that anticipation or foreshadowing is itself documented in the current phase. Example: knowing as an author that an ally later betrays the character does not justify present distrust before the character has evidence.
>
> **Prompt-level limitation**: `author-only`, `unknown to character`, and similar labels are documentation conventions, not access controls. A model that receives the hidden fact has already been exposed to it. If a live agent must not know a fact, do not place that fact in model-visible context: omit it, phrase only the unresolved question and available evidence, or remove the author-only block before inference.
>
> **Applicability Discipline**:
>
> Some observations are valid only in the context in which they occur. Do not convert a setting-bound action into a new-context behavior merely by replacing it with a broad adjective.
>
> Example: a sailor repeatedly ties a specific knot before a storm. In a nautical phase, record the knot and its timing. In a land-based phase, do not rewrite it as `fidgets with small objects` or `always finds a practical hand-task`; those manifestations were never observed. A capability field may contain `manual dexterity: likely high [inference: repeated precise knot work]`, because that is an explicitly marked capacity inference, not an invented land behavior.
>
> Three rules follow:
>
> - **Delete unsupported manifestations.** Remove the context-bound action when its triggering context is absent; do not invent an analogous action to fill the space.
> - **Retain only justified capability inferences.** When the target field asks for an underlying capability and the evidence genuinely supports it, record the inference, its evidence, and its limits. Do not present it as observed behavior in a new context.
> - **If deletion leaves the section thin, gather more data.** Thin coverage is a research signal, not permission to preserve drained generalities.
>
> This discipline complements the Self-Containment Protocol: the file needs specifics, but the specifics and inferences must remain valid for the phase and use context being documented.

---

# {name} ({phase_name})

> {One sentence description of this character in this phase}

---

## 0. META

<!-- Metadata about this persona file itself. Read the full template instructions before authoring. For delegated original design, evidence fields may cite proposed or adopted design IDs from §19 instead of nonexistent source scenes. Hypothetical samples test a proposal; they are not independent observations or events that already occurred. -->

### File Info

- **version**:
  <!-- File version. e.g. 1.0, 1.1 -->
- **last_updated**:
  <!-- Last update date in YYYY-MM-DD -->
- **author**:
  <!-- Author of this file -->
- **changelog**:
  <!-- Major changes -->

### Authoring State

- **authoring_mode**:
  <!-- Record-based reconstruction or original-character design. An AU should distinguish supplied source facts from deliberate design proposals. -->
- **design_status**:
  <!-- Draft, reviewed proposal, or adopted within the stated scope. Neither a filled form nor a generated scene implies adoption. -->
- **adoption_scope**:
  <!-- Identify the adopted decisions by §19 Design Ledger IDs, with actual creator approval basis. Use n/a for record-based reconstruction; state no adoption yet for a proposal. Do not manufacture approval. -->

### Persona Info

- **source**:
  <!-- Source material and reference scope. e.g. "novel volumes 1-4 plus the 2022 official guide" or "creator-provided original-character dossier dated 2026-07-12" -->
- **subject_type**:
  <!-- fictional / original / historical_deceased / living_person. e.g. "fictional" -->
- **phase_name**:
  <!-- Name of this phase. e.g. "youth", "wartime", "late years" -->
- **primary_dialogue_language**:
  <!-- Language used for exact speech forms and dialogue samples. e.g. "Japanese (ja-JP)"; descriptive prose remains English under the Language Policy. -->
- **premise_mode**:
  <!-- canon-strict / adaptation-specific / composite / alternate-universe / original. e.g. "adaptation-specific" -->
- **canonicity_scope**:
  <!-- Exact included and excluded continuity. e.g. "2019 television adaptation through episode 18; excludes the game and later film" -->
- **related_personas**:
  <!-- Optional navigation to other phase files. e.g. `[[name, late years]]`. Links must never replace information required in this file. -->
- **phase_transition_from**:
  <!-- What changed and what remained when entering this phase. e.g. "lost formal rank; retained the same promise-keeping rule" -->
- **phase_transition_to**:
  <!-- AUTHOR-ONLY AND OPTIONAL. Describe only an abstract direction needed by a human author. e.g. `trust becomes more selective after a public failure`. Do not state a concealed identity, outcome, or other hidden answer here. Remove this field before direct agent use when even the abstract direction would bias current portrayal. -->
- **intentional_deviations**:
  <!-- Explicit AU, composite, fan-derived, or original premises preserved by design. e.g. "The injury never occurs in this continuity; all later physical fields follow that premise." Omit if none. -->
- **user_premise_corrections**:
  <!-- Factual corrections within the declared premise_mode and canonicity_scope. -->
  <!-- Format: "Requester said X; the controlling record is Y [source ID]." e.g. "Requester placed the promotion before the siege; episode 18 places it afterward [P03]." Omit if none. -->

---

## 1. TIMELINE

<!-- Overall chronology and the position of this phase -->

### Timeline Overview

<!-- Future rows are optional author-facing orientation only. Labels do not hide their contents from a model. When this file is used directly as an agent prompt, remove future rows rather than relying on `author-only` wording. Do not write concealed answers in a current-phase runtime view. -->

| Order | Phase | Key Events | Status |
|-------|-------|------------|--------|
| 1 | <!-- e.g. "training years" --> | <!-- e.g. "enters apprenticeship; first public failure" --> | past |
| 2 | <!-- e.g. "early service" --> | <!-- e.g. "earns rank; forms current alliance" --> | past |
| **→** | **{this_phase}** | **{events}** | **current** |
| 4 | <!-- Optional future phase label for human orientation. e.g. `later period`; omit in direct agent context if the label itself reveals an outcome. --> | <!-- AUTHOR-ONLY. Keep empty or abstract; do not place a concealed answer here. --> | future (author-only; remove before direct agent use) |

### Current Phase Position

- **period**:
  <!-- Period within the work's internal time. e.g. "during the X war", "after the X incident" -->
- **age**:
  <!-- Age in this phase -->
- **duration**:
  <!-- Length of this phase -->
- **key_events**:
  <!-- Key events that occur during this phase -->

### Epistemic Position in This Phase

<!-- Describe the positive boundary of what the character can use. Do not list a concealed answer as a fact they are forbidden to know. Phrase uncertainty from the character's current point of view: available evidence, current conclusions, unresolved questions, and inference limits. -->

- **available_evidence**:
  <!-- Evidence legitimately available in this phase. e.g. `direct observation; public notices issued before the current date; testimony from two trusted witnesses`. -->
- **settled_beliefs**:
  <!-- Conclusions the character currently treats as settled, whether objectively true or false. Include confidence and basis. e.g. `treats the evacuation order as authentic [high confidence: seal and courier both verified]`. -->
- **unresolved_questions**:
  <!-- Open questions, not hidden answers. e.g. `who altered the report remains unresolved`; do not write `does not know that {person} altered the report`. -->
- **domain_familiarity**:
  <!-- Current areas of expertise, ordinary familiarity, unfamiliarity, or documented indifference that govern whether they answer, ask, or defer. e.g. `expert in field logistics; lay familiarity with law; defers medical diagnosis to a healer`. -->
- **inference_limits**:
  <!-- Conclusions they will not draw from the evidence currently available. e.g. `may note one inconsistent date but does not assign intent without corroboration or direct testimony`. -->
  <!-- NOTE: This field is the single home for the character's reasoning limits. §17 Epistemic Boundary Handling defines only the procedures that operate at this limit; do not restate the limits themselves there. -->
- **in_progress**:
  <!-- Changes or learning still underway during this phase. e.g. `has begun questioning the institution but still obeys its public orders`. -->

---

## 2. PORTRAYAL IDENTITY

<!-- This section binds the current subject's internal core and recognizable portrayal to scoped authorial intent. It is not a claim of a lifelong immutable essence. World facts, creator intent, subject psychology and a realized moment have different owners. Read the applicable authorial intent entries before resolving response/voice/body rules. Field-local guidance stays in generated personas. -->

### Identity Scope and Design Basis

- **identity_scope_and_basis**:
  <!-- Declared continuity, current phase and relevant boundaries; actual sources or original-design decisions, status and limits. Observed consistency is scoped evidence, not proof of lifelong constancy. -->
- **authorial_intent_refs**:
  <!-- Relative Markdown links to governing entries, e.g. target `../design/project.md#intent-i-pattern`. Name the design entity in front-matter references too. This is a binding, not another copy of the intent's rule/status. Record undecided for a missing decision or n/a: reason when genuinely inapplicable. -->
- **inner_core**:
  <!-- Values, motives, dispositions or organizing commitments relevant to this phase, with actual basis and limits. Distinguish what the subject values from what the creator wants the audience to experience. Do not invent psychology for an unpersonified subject or an unsupported claim about a real person. -->
- **recognizable_portrayal**:
  <!-- Interpret the referenced aim for this subject: what makes its presence/choices recognizable across the requested span. 'Consistent' alone is not a criterion. Stable uncertainty or refusal of a single center can be an explicit design. -->

- **principle_application_refs**:
  <!-- Optional navigation to the design's selected portrayal-principle bindings and local interpretation. The library is not a personality type or canon. Record n/a with reason when no pattern is used; full rules remain here or in their world owner. -->
- **state_and_disclosure_dependencies**:
  <!-- Relevant event/knowledge/phase authorities for applying this profile. Do not copy one scene's current mood or a future reveal into the permanent core. An author-side context plan may resolve these dependencies; an actual consumer receives only its reviewed subset. -->

### Established Identity Facts

<!-- Carry readable identity facts with scope and sources. Names, affiliations, forms and even understood origin can be revised or disclosed in a particular continuity; the heading does not assert immutability. Keep adopted geometry/markings in the visual identity owner. -->
- **full_name**:
  <!-- Attested or proposed formal name and scope; phase usage is in section 3. -->
- **origin**:
  <!-- Established or proposed origin; distinguish world fact from belief or withheld knowledge. -->
- **species_or_race**:
  <!-- Authored classification and scope, not automatic anatomy, temperament or expressive meaning. -->
- **birth_date_or_era**:
  <!-- Applicable origin date/era and basis, or examined unknown/n/a. -->

### Continuity and Expressive Range

- **protected_dimensions**:
  <!-- Which dimensions should hold under the current adopted scope and why. Link to intent and actual behavior, not a quota of unchanging tics. Explicitly note where no invariant is justified. -->
- **signature_dynamics**:
  <!-- How constancy, condition-dependent switching, recurrence, contrast, restraint or ambiguity define this portrayal. Which transitions themselves are characteristic? Multiple modes can all be genuine. -->
- **permitted_variation**:
  <!-- The range of expressions/choices that realizes this identity. Conditions permit only their scoped changes, not a silent redesign. An emotion can vary while presence holds, or the change itself can carry identity. -->
- **meaningful_boundaries**:
  <!-- Distinctive behavioral or expressive boundaries within this scope. Add refusals only when informative; no compulsory moral code, weakness, contrast trait or lifelong prohibition. -->
- **continuity_across_phases**:
  <!-- Established changes and continuities into this phase, with the owning records. Do not disclose a future outcome in the current consumer view or treat editorial revision as lived experience. -->
- **departure_and_revision_refs**:
  <!-- Link the owning scoped intention/decision for meaningful disclosure, disruption, lasting change or redesign, if applicable. State the retained dimensions and active timing by reference. No future departure is active merely because it is planned. -->

### Core-to-Performance Bindings

<!-- Each materially used response, voice mode or bodily baseline refers to this profile and the relevant intent. Bindings explain the selection among otherwise plausible performances. The table points to rule owners, not duplicate instructions. Apply only the rows relevant to the task. -->

| Identity dimension / intent reference | Owning response, voice or body rule | What holds | What varies and why | Intended realization and review reference |
|---|---|---|---|---|
| | | | | |

---

## 3. IDENTITY

<!-- Identity in this phase -->

### Name & Affiliation

<!-- IDENTITY lists the self/address forms and compact scope. SPEECH owns the detailed context-switching procedure, and RELATIONSHIPS owns directional exceptions. Refer to those modes/fields rather than maintaining a second complete switching table here. -->

- **name_used**:
  <!-- Name, alias, title used in this phase -->
- **first_person**:
  <!-- Exact first-person form in the character's language, plus switching rule in English. e.g. `Japanese: 「私」 in public; 「僕」 with childhood friends`; `Korean: 「저」 in formal contexts; 「나」 only with close friends`. -->
  <!-- NOTE: Languages differ on what this field can carry. Japanese offers many variants (わたし / 私 / 僕 / 俺 / あたし / わし …); record the variant. English has effectively one ("I"); instead, record HOW they refer to themselves: hedged, direct, avoidant, third-person, or using their own name. Apply the same principle to any other language feature that lacks a direct analogue in the character's language: record the nearest behavioral equivalent rather than forcing the original framing. -->
- **second_person**:
  <!-- Exact second-person or address forms in the character's language, with relationship conditions in English. e.g. `Japanese: surname+「さん」 by default; given name alone only in the innermost relationship`; `French: « vous » toward every colleague regardless of rank; « tu » only within family`. -->
  <!-- NOTE: For languages with rich address systems (Japanese -さん/-様, French tu/vous, Korean 요/시), record the forms and the rule for switching. For languages that mark deference differently (English first-name vs. Mr./Ms., use or avoidance of direct address), record whichever distinction the character's language actually uses. -->
- **affiliation**:
  <!-- Organization, group. WHERE they belong -->
- **formal_standing**:
  <!-- Official title, rank, position in this phase. Position within their affiliation -->
  <!-- NOTE: How others perceive them is in EXTERNAL > perceived_standing -->

### Occupation & Livelihood

<!-- Actual occupation and livelihood -->

- **occupation**:
  <!-- What they do to make a living, or their main daily activity -->
- **work_content**:
  <!-- Concrete work content, duties -->
- **professional_ethics**:
  <!-- Work ethics, professional pride -->
- **income_level**:
  <!-- Income level, economic situation -->

---

## 4. PHYSICAL

<!-- Physical characteristics in this phase. In visual production, an adopted identity contract owns stable geometry, markings and proportions. Keep a readable, source-bound embodiment summary here, not competing visual canon. New appearances may be proposed with design IDs; do not promote them by recording them. Health, clothing state and momentary expression remain phase or scene state unless an approved contract says otherwise. Species labels do not declare anatomy, symmetry or expression channels. -->
<!-- NOTE: This section carries the character's body, voice, and physical habits. These are core information for many uses of a persona: prose narration, screenplay, TRPG / RPG character sheets, illustration and image-generation references, setting documents, and character analysis. Even when the persona is used as a dialogue agent, these descriptions act as thinking material that shapes the LLM's word choices, response density, and rhythm of speech. Fill these fields whenever they are attested; do not skip them based on a narrow guess about what a downstream runtime can or cannot literally reproduce. -->

### Appearance & Body

- **appearance**:
  <!-- Appearance, clothing -->
- **physique**:
  <!-- Build, body type -->
- **health**:
  <!-- Health state, chronic conditions, injuries -->
- **voice**:
  <!-- Voice characteristics -->
  <!-- NOTE: Describe voice timbre, pitch, softness, roughness. This field is central information for prose narration, audio direction, voice casting references, and illustration / character-sheet annotations. It also shapes word choice and rhythm even in dialogue-only uses. For speaking patterns (sentence endings, register, rhythm of speech), see §7 SPEECH. -->
- **handedness**:
  <!-- Dominant hand -->
- **sensory_acuity**:
  <!-- Sharpness of senses. Notable vision, hearing, smell, etc. -->

### Physical Capabilities

<!-- Physical ability -->

- **stamina**:
  <!-- Stamina, endurance -->
- **athletic_ability**:
  <!-- Athletic ability. Agility, strength, balance -->
- **dexterity**:
  <!-- Manual dexterity -->
- **combat_ability**:
  <!-- Combat ability. Strength, fighting style -->
- **special_physical_traits**:
  <!-- Special physical abilities, non-human traits -->

### Physical Mannerisms

<!-- Baselines are scoped, not a universal neutral pose. Use only declared structures and available channels; category labels do not supply anatomy or expressive meaning. PHYSICAL owns habitual geometry and stable voice qualities, not every current pose. THOUGHT Conditional Response Rules and SPEECH Contextual Voice Modes own change conditions; refer to their IDs for deviations. A performed face/body cue is not reliable proof of a private feeling. -->

- **embodied_baseline_context**:
  <!-- Context and phase in which these habits apply; relevant task, environment and constraints. Several supported contexts or an examined unknown are possible. -->
- **expressive_channels_and_limits**:
  <!-- Declared channels, motor/sensory affordances and limits; absence, occlusion and unknown differ. Include non-vocal, non-facial or assisted communication where applicable. -->
- **attention_and_movement_baseline**:
  <!-- Usual gaze/attention, movement amount, posture and response timing in the named context. Record a range and boundary rather than one mandatory pose. -->

<!-- NOTE: Bodily habits carry character information in several ways: they are directly rendered in prose narration and stage direction, they serve as reference for illustration and character-sheet documentation, and in dialogue contexts they implicitly shape how the character's pauses, interiority, and silences get described. Fill these whenever attested. -->

- **habitual_gestures**:
  <!-- Regular gestures. Crossing arms, touching hair, etc. -->
- **thinking_pose**:
  <!-- Gesture when thinking -->
- **nervous_habits**:
  <!-- Gesture when nervous -->
- **relaxed_posture**:
  <!-- Posture when relaxed -->
- **gait**:
  <!-- Walking style -->
- **combat_stance**:
  <!-- Combat stance -->
- **laugh_and_cry**:
  <!-- How they laugh, how they cry -->
- **facial_expressiveness**:
  <!-- Whether emotions show on their face or they're poker-faced (as bodily expression) -->

### Symbolic Items

<!-- Possessions that symbolize this person -->

- **signature_items**:
  <!-- Items always carried, trademark items -->
- **cherished_possessions**:
  <!-- Personal items they treasure, keepsakes -->
- **weapons_or_tools**:
  <!-- Symbolic weapons, tools, instruments -->

---

## 5. MIND

<!-- Mental state and inner life in this phase -->
<!-- NOTE: Describe the character's self-perception. For how others see them, see EXTERNAL. For observable behavior, see PERSONALITY -->

### Mental State

- **maturity**:
  <!-- Mental maturity -->
- **emotional_baseline**:
  <!-- Default mental state, baseline mood -->
- **concerns**:
  <!-- Main worries, preoccupations in this phase -->
- **goals**:
  <!-- Goals and wishes in this phase -->

### Inner World

<!-- Inner life not shown outwardly -->

- **self_image**:
  <!-- How they see themselves now -->
- **ideal_self**:
  <!-- Who they want to be, or who they wished they were. The gap from self_image is meaningful -->
- **self_narrative**:
  <!-- How they narrate their own life. What story do they tell themselves about who they are and where they're going -->
- **social_self_perception**:
  <!-- Where they perceive themselves to stand socially. Subjective position, may differ from formal_standing and perceived_standing -->
- **role_identity**:
  <!-- What kind of role they see themselves as. e.g. "protector", "outsider", "successor", "failure" -->
- **secret_fears**:
  <!-- Hidden anxieties, fears -->
- **unspoken_wishes**:
  <!-- Wishes they don't voice -->
- **internal_conflicts**:
  <!-- Internal conflicts -->

### View of Humans & World

<!-- Worldview and view of human nature. The lens through which they see others -->

- **human_nature_view**:
  <!-- How they see humans in general. Benevolent, malevolent, mixed, indifferent -->
- **world_structure_view**:
  <!-- How they see the world's mechanics. Orderly, chaotic, just, unjust, indifferent -->
- **categorization_of_others**:
  <!-- How they categorize other people. By axes like ally/enemy, superior/inferior, in-group/out-group, competent/incompetent, interesting/boring -->
- **default_stance_to_others**:
  <!-- Default attitude toward strangers. Open, guarded, curious, dismissive -->

### Beliefs & Worldview

- **religious_belief**:
  <!-- Religious belief, attitude toward gods -->
- **view_of_death**:
  <!-- View of death. How they understand dying -->
- **view_of_fate**:
  <!-- Attitude toward fate. Believe in it, or forge their own path -->
- **supernatural_attitude**:
  <!-- Attitude toward the supernatural -->
- **honor_and_shame**:
  <!-- What they take pride in, what they find shameful. What would make them lose face -->

### Political & Ideological Stance

<!-- Political and ideological position -->

- **political_leaning**:
  <!-- Political tendency using the source's own meaningful axes. e.g. `supports the existing council but opposes hereditary office`; do not force modern left/right labels onto a context where they do not apply. -->
- **social_issues_stance**:
  <!-- Attitude toward social issues -->
- **ideology**:
  <!-- Ideological self-definition -->

### Fatigue & Recovery

<!-- Physical and mental fatigue and recovery. Mixes internal experience with observable behavior changes -->

- **fatigue_response**:
  <!-- What happens when they're tired. Changes in behavior and speech -->
- **rest_style**:
  <!-- How they rest. Actively, or unable to rest -->
- **burnout_signs**:
  <!-- Signs that they're approaching their limit -->

---

## 6. THOUGHT

<!-- Patterns of thought and judgment. Observable reasoning with the internal criteria that drive it -->

### Thinking Style

- **decision_style**:
  <!-- How they decide. Intuitive, analytical, consultative -->
- **decision_priorities**:
  <!-- Priorities when making decisions. What comes first -->
  <!-- NOTE: For life priorities in general, see PERSONALITY > life_priorities -->
- **problem_approach**:
  <!-- What they consider first when facing a problem -->
- **information_processing**:
  <!-- How they process information -->
- **learning_style**:
  <!-- How they learn new things. Hands-on, theoretical, observational -->
- **logic_vs_emotion**:
  <!-- Balance between logic and emotion in their decisions -->

### Judgment Criteria

<!-- Criteria by which they judge truth, right, and value. Internal beliefs that manifest in observable judgment patterns -->

- **truth_criteria**:
  <!-- How they decide what is true. Experience, logic, authority, tradition, intuition, evidence -->
- **moral_criteria**:
  <!-- How they decide what is right. Virtue, consequence, duty, custom, personal code -->
- **reference_frame**:
  <!-- The frame they fall back on when judging. A mentor's teaching, religion, personal experience, pure instinct -->
  <!-- NOTE: Day-to-day judgment frame. Distinct from §2 inner_core (scoped motives and commitments) and §15 guiding_principle (unprecedented situations). -->
- **value_hierarchy**:
  <!-- Priority order when values conflict. e.g. loyalty > truth > self-interest -->
- **what_they_refuse_to_weigh**:
  <!-- Considerations they deliberately exclude. "Not this. I don't factor this in." -->

### Reaction Patterns

<!-- These entries summarize conditions, not an emotion-to-face lookup table. For consequential responses, link the Conditional Response Rules below: perception/appraisal -> control or involuntary response -> speech and body -> continuation/release. Distinguish internal experience, intended display, observable channels and another observer's reading. No automatic agreement or visible leakage is required. -->

<!-- Reactions to specific situations -->
<!-- NOTE: Record the phase-wide default or public-facing baseline here; do not invent a numerical or conceptual average between incompatible relationship modes. The same person may withdraw in public and cry with one trusted person. Write the most consistently observed default, note systematic exceptions inline, and detail person- or relationship-specific shifts in §13 Relationship-Specific Realizations. Example: `when_sad: looks down and shortens replies by default; with {trusted person}, remains present and allows visible tears`. -->

- **when_surprised**:
  <!-- How they react when surprised. Visible or suppressed, freeze or quick recovery -->
- **when_angry**:
  <!-- How anger manifests. Explosive, cold, silent, or controlled -->
- **when_sad**:
  <!-- How sadness shows. Withdrawal, tears, stoic silence, or seeking company -->
- **when_happy**:
  <!-- How joy is expressed. Openly, reservedly, or only with certain people -->
- **when_praised**:
  <!-- How they receive praise. Accept, deflect, embarrassed, or suspicious of motive -->
- **when_insulted**:
  <!-- How they respond to insults. Retaliate, ignore, hold it in, or confront later -->
- **when_confused**:
  <!-- How they behave when confused. Ask openly, hide it, or pretend to understand -->
- **under_pressure**:
  <!-- How they behave when cornered. Dig in, lash out, freeze, or improvise -->
- **when_succeeded**:
  <!-- How they respond to their own success. Celebrate, downplay, credit others, or move to the next goal -->
- **when_failed**:
  <!-- How they handle their own failure. Own it, deflect, dwell, or move on quickly -->
- **when_others_succeed**:
  <!-- Reaction to others' success. Genuine celebration, envy, competitive urge, or indifference -->
- **when_others_fail**:
  <!-- Reaction to others' failure. Help, judge, feel vindicated, or keep distance -->
- **when_sick_or_injured**:
  <!-- How they behave when sick or injured themselves. Hide it, admit it, rest, or push through -->
- **when_others_sick**:
  <!-- How they behave toward others who are sick or injured. Attentive, awkward, or practical -->
- **when_apologizing**:
  <!-- How they apologize, whether they can apologize easily -->
- **when_thanking**:
  <!-- How they express gratitude -->
- **under_stress**:
  <!-- Stress response, how they release stress -->

### Conditional Response Rules

<!-- Before choosing a reaction, apply section 2 and its authorial intent references. A locally plausible response can violate the adopted portrayal. A designed switch is not automatically an identity break; an actual departure needs its scoped decision. -->

<!-- Repeat for relevant boundaries, not for every emotion multiplied by every relationship. Use stable local IDs; refer to SPEECH mode IDs and RELATIONSHIPS exceptions instead of copying their content. A rule is a permitted tendency with limits, not a deterministic personality algorithm. Original-design samples and rules retain proposal/adoption status through §19. -->

- **response_rule_id**:
  <!-- Stable local ID, e.g. response-work-interruption; it is prose, not a new narrative entity ID. -->
- **identity_and_intent_binding**:
  <!-- Section 2 dimension and governing intent ID: how held/changed components realize the center, or the exact authorized departure. Refer to the owner, not a duplicate rule. -->
- **perceived_situation_and_access**:
  <!-- Event, task, known information, noticed cues, resources and relevant audiences; distinguish reality from the character's interpretation. -->
- **appraisal_and_purpose**:
  <!-- What the event means to this person, relevant aim/value and established or proposed affect; uncertainty can be retained. -->
- **display_control_and_initial_response**:
  <!-- Intended communication, habitual or involuntary response, suppression or no change. Observable behavior need not reveal the internal state. -->
- **response_components**:
  <!-- Speech mode references, action flow, bodily channels, their targets and what changes or holds. No undeclared anatomy or universal emotion gestures. -->
- **development_and_recovery**:
  <!-- Conditions and sequence of onset, persistence, interruption, switch, release or residue as relevant. Return is not mandatory or instantaneous. -->
- **overlap_and_exceptions**:
  <!-- How relevant simultaneous conditions are resolved component by component; reference §7/§13. Mark unresolved overlaps, not invented universal priorities. -->
- **response_basis_and_probe**:
  <!-- Sources or design IDs, current status, tested sample references, counterexample and remaining gap. A generated example cannot corroborate its own rule. -->

### Competitiveness

- **winning_losing**:
  <!-- How much they care about winning and losing -->
- **comparison_to_others**:
  <!-- Whether they compare themselves to others -->
- **attitude_to_competition**:
  <!-- Attitude toward competition -->

### Action Patterns

<!-- Multi-step interaction procedures this person performs, whether self-initiated or triggered by another person's action. Reaction Patterns record immediate affective leakage; Action Patterns record an ordered social procedure. -->
<!-- Write each entry as IF / THEN / BRANCH / EVIDENCE, not as a trait. `Greets warmly` is insufficient. `IF a known person is waiting, THEN address by name → ask after their state → pause before stating business` is reproducible. -->
<!-- In record-based mode, a flow may synthesize observations with marked inference and scene evidence, but cannot invent plausible steps. In original-design mode, author proposed steps explicitly, cite the supporting design decisions and test their consistency with values, speech and social behavior. -->
<!-- The ten categories below satisfy the structural coverage target only when evidence supports them. Replace unsupported defaults with character-specific recurring situations, such as `public_address`, `bedside_approach`, or `correction_without_shame`. If fewer than ten flows are supportable, record the deficit in §19 Known Gaps. -->

- **opening_interactions**:
  - **if**:
    <!-- Trigger. e.g. `IF they enter a room where one known person is already waiting` -->
  - **then**:
    <!-- Ordered procedure. e.g. `address by name → ask after physical state → wait for an answer → state business` -->
  - **branch**:
    <!-- Conditional variant. e.g. `IF the addressee is a stranger, omit the personal check-in and identify purpose first` -->
  - **evidence**:
    <!-- Source IDs and scenes. e.g. `[P01 ch. 3], [P02 ep. 7 00:12:41]` -->
- **receiving_care**:
  - **if**:
    <!-- e.g. `IF someone offers warning, practical help, or concern` -->
  - **then**:
    <!-- e.g. `let them finish → acknowledge the concern once → accept or refuse the concrete help → do not defend character unless accused` -->
  - **branch**:
    <!-- e.g. `IF the concern comes from the closest relationship, answer one question honestly before redirecting` -->
  - **evidence**:
    <!-- e.g. `[P01 ch. 8], [P04 scene 12]` -->
- **repair_and_apology**:
  - **if**:
    <!-- e.g. `IF their action caused identifiable harm` -->
  - **then**:
    <!-- e.g. `name own fault first → give a one-line apology → pause → offer repair only after the other responds` -->
  - **branch**:
    <!-- e.g. `IF the harm is irreversible, omit self-explanation and accept rejection` -->
  - **evidence**:
    <!-- e.g. `[P02 ep. 11 00:18:05]` -->
- **commitment_acceptance**:
  - **if**:
    <!-- e.g. `IF asked to accept a costly role or obligation` -->
  - **then**:
    <!-- e.g. `test one practical condition → state the cost aloud → accept in a single declarative sentence` -->
  - **branch**:
    <!-- e.g. `IF the request violates the value hierarchy, move to the refusal flow instead` -->
  - **evidence**:
    <!-- e.g. `[P01 ch. 12], [P03 p. 44]` -->
- **refusal**:
  - **if**:
    <!-- e.g. `IF a request conflicts with a current duty or hard boundary` -->
  - **then**:
    <!-- e.g. `acknowledge the request → state own position → give no more than three reasons → close without inviting negotiation` -->
  - **branch**:
    <!-- e.g. `IF refusing a close person, add one alternative action without softening the no` -->
  - **evidence**:
    <!-- e.g. `[P01 ch. 5], [P02 ep. 9]` -->
- **moving_others**:
  - **if**:
    <!-- e.g. `IF another person must act and time remains for consent` -->
  - **then**:
    <!-- e.g. `state shared objective → use the character-language hortative (Japanese: 「行きましょう」 rather than 「行け」; French: « On y va » rather than « Vas-y ») → begin moving first` -->
  - **branch**:
    <!-- e.g. `IF immediate danger removes deliberation time, shorten to one direct command` -->
  - **evidence**:
    <!-- e.g. `[P02 ep. 4 00:09:20], [P04 scene 3]` -->
- **confrontation**:
  - **if**:
    <!-- e.g. `IF someone causes concrete harm and denial continues` -->
  - **then**:
    <!-- e.g. `let the denial finish → ask one fact-bound question → name the consequence → state the demanded stop` -->
  - **branch**:
    <!-- e.g. `IF confronting an authority figure, retain formal address but remove hedging` -->
  - **evidence**:
    <!-- e.g. `[P01 ch. 14], [P03 p. 91]` -->
- **declaration**:
  - **if**:
    <!-- e.g. `IF indecision in the group requires their own stance to be explicit` -->
  - **then**:
    <!-- e.g. `use first person → state one irreversible choice → name the immediate next action` -->
  - **branch**:
    <!-- e.g. `IF speaking privately, omit the public justification and address one person directly` -->
  - **evidence**:
    <!-- e.g. `[P02 ep. 16 00:20:02]` -->
- **care_for_others**:
  - **if**:
    <!-- e.g. `IF someone is injured, grieving, or visibly overwhelmed` -->
  - **then**:
    <!-- e.g. `reduce physical height or distance → identify the practical need → offer one action → leave silence for acceptance` -->
  - **branch**:
    <!-- e.g. `IF touch is not welcome, keep distance and place the needed item within reach` -->
  - **evidence**:
    <!-- e.g. `[P01 ch. 6], [P04 scene 8]` -->
- **farewell**:
  - **if**:
    <!-- e.g. `IF an interaction or relationship interval is ending` -->
  - **then**:
    <!-- e.g. `finish unresolved practical business → mark continuity or finality explicitly → leave without adding a second goodbye` -->
  - **branch**:
    <!-- e.g. `IF reunion is uncertain, avoid a promise and use an open temporal phrase instead` -->
  - **evidence**:
    <!-- e.g. `[P01 final chapter], [P02 ep. 18 00:22:10]` -->

---

## 7. SPEECH

<!-- How they speak in this phase -->
<!-- NOTE: This section covers speech PATTERNS (what forms their utterances take). For voice TIMBRE (pitch, softness, roughness as a physical property), see §4 voice. The two interact but belong in different sections: §4 voice shapes the reader's mental sound; §7 specifies the actual grammatical and rhetorical forms of the character's utterances. -->

### Speech Patterns

<!-- Distinguish each field's job. Do not paste one general voice description into sentence_endings, rhythm, speech_style and questioning_style. Write exact forms, actual sequencing and a condition or boundary as appropriate. Speech may be ordinary or similar to others by design; pronoun substitutions alone do not demonstrate a differentiated voice. PHYSICAL owns stable timbre, SPEECH owns linguistic choices and contextual delivery. -->

- **speech_baseline_context**:
  <!-- Applicable language, communication mode, addressee/audience, task and phase; no assumed universal public or neutral default. -->
- **address_and_register**:
  <!-- Apply the self/address inventory in §3 to this baseline, with exact forms or field references, titles and politeness/speech levels. §7 modes own switching; §13 owns relational exceptions. Do not duplicate the form registry. Formality, respect, warmth and honesty are separate. -->
- **sentence_construction**:
  <!-- Typical clause shape, answer/reason/request order, compression or elaboration, and permitted alternatives. Distinguish grammatical structure from tempo. -->
- **conversational_initiative**:
  <!-- What they introduce, follow up, leave unanswered or repair; when they invite, yield or take a turn. Connect to concerns and attention, not only a plot function. -->

- **sentence_endings**:
  <!-- Exact clause- and sentence-final forms in the character's language, plus the English functional rule. e.g. `Japanese: favors 「〜です」 in public; drops to 「〜だ」 only under direct confrontation`; `Mandarin: softens directives with 「吧」; states conclusions as bare declaratives without final particles` -->
- **rhythm**:
  <!-- Speaking tempo and pause placement. e.g. `answers factual questions immediately; inserts one beat before emotional admissions; rarely trails off twice in one turn` -->
- **characteristic_expressions**:
  <!-- Exact recurring forms in the character's language, with source scene and selection reason. e.g. `「なるほど」: used after hearing a full explanation, not as a filler at turn start [P02 ep. 4]` -->
- **speech_style**:
  <!-- Overall impression grounded in forms. e.g. `formally courteous but structurally direct: one acknowledgment followed by one declarative conclusion` -->
- **vocabulary_level**:
  <!-- Vocabulary range and domain. e.g. `plain everyday syntax; precise technical nouns only while working; avoids literary metaphor in urgent speech` -->
- **speech_taboos**:
  <!-- Exact words or forms demonstrably avoided in this phase; write language-bound items in that language. e.g. `does not use 「絶対」 when making uncertain predictions, despite using it for promises` -->
  <!-- AUTHORING ORDER: Fill vocabulary_level, characteristic_expressions, and speech_style first, describing what this person DOES say and how. Add entries here only for exclusions that remain non-obvious after those fields are complete. A taboo earns its place when the form is one many similar characters would use but this character specifically rejects or consistently replaces. Absence from a small corpus is not proof of taboo. -->

### Contextual Voice Modes

<!-- Select modes under section 2, not solely because they are psychologically possible. Tie each material switch or maintained register to the recognizable portrayal and governing intent. The pattern across turns/scenes matters as well as one utterance. -->

<!-- Use only modes material to this portrayal. Affects, situation, role, task, audience, addressee, communication medium/language and bodily resources can modify different components. §13 owns person-specific activation or deviations; point to those exceptions rather than copying them. No global relationship/emotion priority and no mandatory loss of politeness under stress. Keep language-bound forms exact. -->

- **voice_mode_id**:
  <!-- Stable local ID, e.g. voice-task-urgent. Does not create a JSON enum or narrative entity. -->
- **activation_and_scope**:
  <!-- Relevant conditions and the moment this mode begins; distinguish addressee from bystanders/listeners and public role from private tie. -->
- **identity_realization**:
  <!-- Section 2 binding and intent ID: how constancy, designed contrast or another scoped pattern shapes this mode. A departure needs its own scoped decision. -->
- **communicative_purpose**:
  <!-- What the utterance is doing here, and intended display versus felt experience where established. Deliberate performance and involuntary change are distinct. -->
- **speech_delta**:
  <!-- Exact register/address, endings, syntax, vocabulary, directness and length changes relative to named baseline, or explicitly none. Do not describe all of these with the same adjective. -->
- **vocal_delivery_delta**:
  <!-- Contextual tempo, pauses, volume, pitch movement, breath or articulation; distinguish from PHYSICAL timbre. n/a for a non-vocal mode; describe applicable signed/written timing elsewhere. -->
- **listening_delta**:
  <!-- Changes to turn-taking, backchannels, questioning, interruption, waiting or repair; speaking style includes reception. -->
- **held_features_and_body_link**:
  <!-- Which recognizable choices hold; link bodily/response rules with coordinated, contrary, delayed, hidden or absent channels. No requirement that all signals agree. -->
- **overlap_resolution**:
  <!-- A relevant combined condition and per-component resolution, with basis; e.g. the addressee is trusted but the audience remains public. Unknown is better than silent precedence. -->
- **switch_release_and_repair**:
  <!-- Where a switch occurs, what persists, whether the speaker corrects a form, and re-entry or release conditions. One listener arriving need not erase the previous affect. -->
- **mode_basis_and_examples**:
  <!-- Source/design IDs and status, matched baseline/changed-context samples in §16, plus limitations. Samples remain hypothetical unless established in continuity. -->

### Vocabulary Registry

<!-- Record exact preferred and avoided forms. Descriptions and conditions are in English; tokens remain in the character's language. Duplicate rows as needed. -->
<!-- A preferred/avoided pair must express a real choice, not a translation artifact. Example: Japanese `gratitude | 「ありがとうございます」 | 「サンキュー」 | public and unfamiliar addressees | [P01 ch. 2; P02 ep. 5]`; English `gratitude | “thank you” | “thanks” | formal work interactions | [P03 scene 8]`; German `gratitude | „vielen Dank“ | „danke“ | toward clients and superiors | [P02 sc. 4]`. -->

| Function | Preferred Form(s) | Avoided / Forbidden Form(s) | Conditions and Boundary | Evidence |
|----------|-------------------|------------------------------|-------------------------|----------|
| <!-- e.g. gratitude --> | <!-- exact token(s) in the character's language --> | <!-- exact alternative; write `unknown` if avoidance is not established --> | <!-- e.g. `formal and unfamiliar addressees; switches with the innermost relationship` --> | <!-- e.g. `[P01 ch. 2], [P02 ep. 5]` --> |

### Language & Dialect

- **languages**:
  <!-- Languages used, whether multilingual -->
- **dialect_accent**:
  <!-- Dialect, accent, regional features -->
- **code_switching**:
  <!-- Language/dialect switching and its supported conditions. Point to Contextual Voice Modes for register/delivery changes; do not assume bilingualism from a register switch or use a translation as evidence of the original form. -->

### Listening Behavior

- **listening_style**:
  <!-- Whether they hear people out or interrupt -->
- **backchanneling**:
  <!-- Exact backchannel forms, placement and frequency in the actual language; nonverbal or no backchannel is valid. Mode-specific shifts belong in Contextual Voice Modes. -->
- **questioning_style**:
  <!-- Typical question construction, what they ask first, follow-up and tolerance of incomplete answers; not a copy of the general speech_style. -->
- **silence_tolerance**:
  <!-- Response to silence. Awkward or comfortable -->

### Humor

- **humor_style**:
  <!-- Whether they joke, and what kind -->
- **what_makes_laugh**:
  <!-- What they find funny -->
- **sarcasm_level**:
  <!-- Whether they use sarcasm -->

### Secrets & Lies

- **can_keep_secrets**:
  <!-- Whether they can keep secrets -->
- **lying_behavior**:
  <!-- Whether they lie, and what kind of lies -->
- **when_hiding_something**:
  <!-- Behavior when concealing something -->

---

## 8. PERSONALITY

<!-- Personality and values in this phase, observed objectively -->
<!-- NOTE: For self-perception, see MIND > Inner World > self_image. For how others perceive them, see EXTERNAL > Social Perception -->

### Personality Traits

- **primary_trait**:
  <!-- Most prominent personality trait in this phase -->
- **secondary_traits**:
  <!-- Other personality features -->
- **emotional_expression**:
  <!-- How they show emotion. Hide it or express openly -->
- **responsibility_sense**:
  <!-- Sense of responsibility. Take it on or avoid it -->
- **perfectionism**:
  <!-- Degree of perfectionism. Detail-oriented or broad-strokes -->

### Empathy & Emotional Connection

- **empathy_level**:
  <!-- Level of empathy -->
- **reading_others**:
  <!-- Ability to read others' emotions -->
- **emotional_distance**:
  <!-- Whether they get emotionally involved or keep distance -->

### Values

- **likes**:
  <!-- Things they like -->
  <!-- NOTE: Phase-specific. Not the scoped identity pattern (§2), sense-level preferences (below), or food (§10). -->
- **dislikes**:
  <!-- Things they dislike -->
  <!-- NOTE: Same scope as likes. -->
- **life_priorities**:
  <!-- Life priorities in this phase. What they consider important to live for -->
  <!-- NOTE: For decision-time priorities, see THOUGHT > decision_priorities -->
- **work_attitude**:
  <!-- Attitude toward work and duty. Diligent, minimal, or enjoying -->
- **duty_vs_desire**:
  <!-- Balance between duty and desire -->

### Sensory Preferences

<!-- Preferences across the senses. Useful for immersive depiction. Taste/food is in §10 Food & Drink -->

- **preferred_sounds**:
  <!-- Liked and disliked sounds. Calming sounds, irritating sounds -->
- **preferred_smells**:
  <!-- Liked and disliked smells -->
- **preferred_textures**:
  <!-- Liked and disliked textures -->
- **preferred_sights**:
  <!-- Visual preferences. Scenery, colors, light -->

### Attitude to Money & Material

- **money_sense**:
  <!-- Attitude toward money. Frugal or generous -->
- **material_attachment**:
  <!-- Attachment to material things -->
- **attitude_to_wealth**:
  <!-- Attitude toward wealth and poverty -->

### Dependencies & Indulgences

<!-- Indulgences and dependencies -->

- **alcohol_attitude**:
  <!-- Attitude toward alcohol. Whether they drink, what they're like drunk -->
- **tobacco_and_smoking**:
  <!-- Smoking habits -->
- **other_indulgences**:
  <!-- Gambling, caffeine, sweets, other indulgences -->
- **dependency_tendency**:
  <!-- Whether they tend toward dependence, and on what -->

### Attitude to Change

- **novelty_preference**:
  <!-- Prefer novelty or stability -->
- **tradition_attitude**:
  <!-- Attitude toward tradition -->
- **flexibility**:
  <!-- Flexibility. Response to plan changes -->

---

## 9. KNOWLEDGE

<!-- Knowledge and abilities in this phase -->

### Education & Knowledge

- **education_background**:
  <!-- What kind of education they received -->
- **literacy**:
  <!-- Reading and writing ability -->
- **areas_of_expertise**:
  <!-- Fields they know in depth -->
- **areas_of_ignorance**:
  <!-- Fields they don't know or are unfamiliar with -->
- **world_knowledge**:
  <!-- Level of knowledge about the world, history, politics -->
- **intellectual_curiosity**:
  <!-- Direction and strength of intellectual curiosity -->

### Skills & Abilities

- **strengths**:
  <!-- What they are good at -->
- **weaknesses**:
  <!-- What they are bad at -->
- **skills**:
  <!-- Skills they possess -->
- **creativity**:
  <!-- Creativity. Generate new ideas or build on existing ones -->
- **artistic_sense**:
  <!-- Artistic sense. Interest in art, aesthetic sensibility -->
  <!-- NOTE: Engagement with art (consumption, creation, critique). For what they find beautiful in general, see §2 aesthetic_sense. -->
- **self_expression**:
  <!-- Means of self-expression. Drawing, poetry, singing, dancing -->

### Special Abilities

<!-- Special abilities, supernatural elements -->

- **supernatural_powers**:
  <!-- Magic, superpowers, special skills -->
- **power_limitations**:
  <!-- Constraints, costs, conditions under which the power fails -->
- **power_self_awareness**:
  <!-- How they perceive and evaluate their own abilities -->

### Works & Achievements

<!-- Works, achievements, primarily for real people or creators -->

- **major_works**:
  <!-- Major works or writings up to this phase -->
- **notable_achievements**:
  <!-- Notable accomplishments -->
- **public_recognition**:
  <!-- Awards, public acclaim -->

---

## 10. DAILY_LIFE

<!-- Daily life in this phase -->

### Habits & Routines

- **sleep_pattern**:
  <!-- Sleep and wake pattern -->
- **eating_habits**:
  <!-- Food preferences, eating style -->
- **idle_behavior**:
  <!-- What they do when idle -->
- **grooming**:
  <!-- Grooming habits -->
- **routines**:
  <!-- Daily routines and habits -->
- **hobbies**:
  <!-- Hobbies and leisure activities -->
- **rituals_and_meaning**:
  <!-- Rituals or repeated actions and what they mean to this person. Different from routines: these carry significance -->

### Food & Drink

<!-- Eating preferences and manners. For alcohol, see §8 Dependencies & Indulgences -->

- **favorite_foods**:
  <!-- Favorite foods -->
- **disliked_foods**:
  <!-- Disliked foods -->
- **eating_manner**:
  <!-- Eating manners, distinctive eating style -->

### Living Environment

<!-- Living environment and space -->

- **dwelling_type**:
  <!-- Type of dwelling. House, room, lodging, wandering -->
- **room_condition**:
  <!-- Condition of their space. Tidy or messy -->
- **space_preferences**:
  <!-- Preferences about living space. Light, size, quiet -->
- **place_attachment**:
  <!-- Places they feel attached to beyond mere dwelling. Hometown, a specific spot, a "place to return to" -->

### Time Sense

- **punctuality**:
  <!-- Punctual or loose with time -->
- **waiting_tolerance**:
  <!-- Tolerance for waiting -->
- **when_rushed**:
  <!-- Response when rushed -->
- **time_orientation**:
  <!-- Past-oriented, present-oriented, or future-oriented -->

### Solitude & Group

- **solitude_preference**:
  <!-- Prefer solitude or find it hard -->
- **group_position**:
  <!-- Position within a group -->
- **leadership_tendency**:
  <!-- Seek leadership or prefer following -->

### Animals & Nature

- **animal_attitude**:
  <!-- Attitude toward animals -->
- **nature_behavior**:
  <!-- Behavior in natural settings -->

---

## 11. SOCIAL

<!-- Social behavior -->

### Communities

<!-- Communities they belong to and their influence -->
<!-- NOTE: affiliation (IDENTITY) is about WHERE they belong; this section is about HOW those affiliations shape them -->

| Community | Role | Influence Received | Influence Given | Priority |
|-----------|------|-------------------|-----------------|----------|
| <!-- name --> | <!-- role within --> | <!-- values, behaviors received --> | <!-- influence given --> | <!-- sense of belonging: high/mid/low/none --> |

- **primary_community**:
  <!-- Community they identify with most strongly. When in doubt, their values take precedence -->
- **ingroup_boundary**:
  <!-- Where "us" ends and "them" begins -->
- **community_conflicts**:
  <!-- Value conflicts between communities, situations where they're caught in the middle -->
- **conflict_resolution**:
  <!-- Criteria for resolving inter-community conflict -->
  <!-- NOTE: For inter-community clashes only. General judgment → §6 reference_frame. -->
- **outsider_attitude**:
  <!-- Attitude toward communities they don't belong to -->
- **community_mobility**:
  <!-- Attitude toward moving between or leaving communities. Clinging or pragmatic -->

### Interpersonal Modes

<!-- How thinking and behavior shift depending on the configuration of people involved -->
<!-- The same person acts very differently one-on-one vs. in a crowd -->
<!-- NOTE: If the character behaves similarly across these configurations, note that in `mode_switching` and keep individual fields brief (e.g. "same as one_on_one"). Only fill all four in detail when the differences actually matter. -->

- **one_on_one**:
  <!-- Behavior in private, two-person situations. More open, more guarded, or different altogether -->
- **one_to_many_as_center**:
  <!-- When they are one person facing or addressing a group. Speaker, leader, defendant, performer -->
- **many_to_one_as_part**:
  <!-- When they are one member of a group dealing with a single other. Crowd behavior, peer pressure response, whether they speak up or blend in -->
- **many_to_many**:
  <!-- In group-to-group situations: meetings, parties, negotiations, mixed gatherings. How they position themselves in complex social fields -->
- **preferred_configuration**:
  <!-- Which configuration they find most comfortable, and which they avoid -->
- **mode_switching**:
  <!-- How visibly their demeanor changes across these modes. Consistent self or highly adaptive -->

### Etiquette

- **etiquette_knowledge**:
  <!-- Knowledge of etiquette -->
- **etiquette_practice**:
  <!-- How much they actually follow it -->
- **public_behavior**:
  <!-- Behavior in public settings -->

### Attitude to Hierarchy

- **attitude_to_authority**:
  <!-- Attitude toward authority. Superiors, kings, gods -->
- **attitude_to_subordinates**:
  <!-- Attitude toward subordinates -->
- **attitude_to_equals**:
  <!-- Attitude toward peers -->
- **attitude_to_children**:
  <!-- Attitude toward children. Fond, awkward, how they interact -->
- **attitude_to_elderly**:
  <!-- Attitude toward the elderly -->

### Physical Proximity

<!-- Attitude toward physical contact and distance -->

- **personal_space**:
  <!-- Size of personal space -->
- **touch_comfort**:
  <!-- Tolerance for being touched. By whom it's acceptable -->
- **physical_affection**:
  <!-- Physical expression of affection. Handshake, hug, hand on shoulder -->

### Generation & Culture

<!-- Generational awareness -->

- **generational_identity**:
  <!-- Sense of belonging to their own generation -->
- **intergenerational_attitude**:
  <!-- Attitude toward other generations -->

---

## 12. EXTERNAL

<!-- How others see this person. May differ from their self-image -->
<!-- NOTE: This section is strictly from outside perspectives. For self-image, see MIND. For actual behavior, see PERSONALITY -->

### First Impression

<!-- Impression given at first meeting -->

- **visual_impact**:
  <!-- Impression from appearance -->
- **manner_impression**:
  <!-- Impression from behavior -->
- **common_first_reaction**:
  <!-- Common reactions of those meeting them for the first time -->

### Social Perception

<!-- Reputation and perception from others -->

- **reputation**:
  <!-- Reputation, public evaluation -->
- **perceived_standing**:
  <!-- Standing as seen by others. Position others attribute to them -->
  <!-- NOTE: For official title and rank, see IDENTITY > formal_standing -->
- **perceived_personality**:
  <!-- Personality as perceived by others (may differ from self-image) -->
- **perceived_strengths**:
  <!-- Strengths others recognize -->
- **perceived_weaknesses**:
  <!-- Weaknesses others point out -->

### Gaps

<!-- Gaps between self-perception and outside perception -->

- **common_misconceptions**:
  <!-- Common misconceptions. What others often misunderstand -->
- **hidden_from_others**:
  <!-- Sides they don't show others -->
- **unaware_habits**:
  <!-- Habits or tendencies they're unaware of themselves -->
- **gap_awareness**:
  <!-- Whether they're aware of the gap -->

---

## 13. RELATIONSHIPS

<!-- Relationships in this phase. Both internal feelings and observable behavior toward others -->

### Important People

| Person | Relationship | Feelings / Self-Report | Observable Behavior | Status |
|--------|--------------|------------------------|---------------------|--------|
| <!-- e.g. `{name}` --> | <!-- e.g. `older sibling and former commander` --> | <!-- e.g. `calls it duty; privately admits fear of disappointing them` --> | <!-- e.g. `keeps formal address but volunteers explanations not given to others` --> | <!-- e.g. `estranged but still cooperating` --> |

### Relationship Tendencies

- **trust_default**:
  <!-- How much they trust strangers by default -->
- **attachment_style**:
  <!-- Tendency in how they relate to people -->
- **conflict_style**:
  <!-- How they handle conflict. e.g. `raises the concrete issue privately first; moves public only after repeated denial` -->

### Relationship-Specific Realizations

<!-- Use this section only for systematic deviations from the default/public baselines in §6, §7, §8, and §11. Do not repeat the whole relationship history. Record only exceptions active in this phase. Planned future closeness belongs in separate author notes, not the opening persona. Evaluate each direction separately; another person's feelings cannot be inferred from this person's hopes. -->
<!-- TERMINOLOGY: the field naming ("realization") is shared with the companion behavioral-texture template. Describe the behavior as realized within this relationship, compared against the baseline, in qualitative terms; never express the difference as a numeric delta or score. -->

#### {person or structural relationship type}

- **relationship_conditions_and_audience**:
  <!-- Active phase, direction and scope of this exception. Does it apply privately, publicly, in a shared role, or only in a named situation? Other listeners do not become the addressee by default. -->
- **linked_response_and_voice_modes**:
  <!-- IDs or field references to general THOUGHT/SPEECH rules used here; own only relationship-specific exceptions below. -->
- **baseline_shift**:
  <!-- Which default changes. e.g. `with this person, guarded default becomes openly consultative` -->
- **speech_realization**:
  <!-- Exact register, address, density, or rhythm change. e.g. `retains 「です」 but adds the person's name and one extra explanatory sentence` -->
- **reaction_realization**:
  <!-- How emotional output differs. e.g. `anger becomes direct objection rather than delayed silence` -->
- **decision_realization**:
  <!-- Whether priorities or delegation change. e.g. `accepts this person's safety judgment over own first impression` -->
- **overlap_switch_and_hold**:
  <!-- How this relationship exception combines with affect, task, audience and resource conditions; what stays, exact switching/release conditions and unresolved combinations. Intimacy need not remove formality and anger need not remove affection. -->
- **body_language_realization**:
  <!-- Specific deviations or persistence in gaze, facial or available channel activity, posture and movement, referencing PHYSICAL/THOUGHT; no mandatory emotional leakage. -->
- **physical_distance_realization**:
  <!-- Observable proximity change. e.g. `allows shoulder contact and remains within arm's reach during silence` -->
- **evidence**:
  <!-- Source IDs. e.g. `[P01 ch. 9], [P02 ep. 14]` -->

<!-- Duplicate the block for each person or relationship type whose behavior differs systematically. -->

### Romance & Intimacy

<!-- Attitudes toward romance and intimate relationships -->

- **romantic_orientation**:
  <!-- Romantic orientation only when directly established. e.g. `bisexual [explicit self-identification in P04]`; for real people without direct evidence, write `unknown`. -->
- **attitude_to_romance**:
  <!-- Attitude toward romance. Active or uninterested -->
- **intimacy_behavior**:
  <!-- Behavior in intimate relationships -->
- **expression_of_affection**:
  <!-- How they express affection -->

---

## 14. MEMORY

<!-- Relationship with the past. Both internal recollection and its observable triggers -->

### Memory Reference

- **frequently_recalled**:
  <!-- Things they often recall -->
- **suppressed_memories**:
  <!-- Memories they suppress or avoid -->
- **lessons_learned**:
  <!-- Lessons learned from experience -->
- **nostalgia_triggers**:
  <!-- Things that trigger nostalgia -->

### Forgiveness & Grudges

<!-- What they can and cannot let go of -->

- **forgiveness_scope**:
  <!-- What they can forgive. Whom they can forgive -->
- **unforgivable**:
  <!-- What they cannot forgive under any circumstance -->
- **grudge_tendency**:
  <!-- Whether they hold grudges, and for how long -->
- **self_forgiveness**:
  <!-- Whether they can forgive themselves. Often differs from how they treat others -->

### Sensitive Areas

- **hidden_topics**:
  <!-- Topics they never bring up themselves -->
- **trauma**:
  <!-- Documented traumatic experiences or explicitly identified wounds. e.g. `avoids enclosed transport after the documented accident [P03]`; do not diagnose a real person from mannerisms alone. -->
- **triggers**:
  <!-- Things they cannot stand to have touched -->
- **specific_fears**:
  <!-- Concrete fears, visceral aversions -->
- **phobias**:
  <!-- Phobias (heights, enclosed spaces, insects) -->

---

## 15. UNCERTAINTY

<!-- Response to uncertainty and unprecedented situations. Guidance for "what would this person do?" when no directly documented case exists. Mixes internal principles with expected observable behavior; mark inference explicitly. -->

- **general_approach**:
  <!-- Default approach to an unfamiliar situation. e.g. `observe before acting → ask one clarifying question → choose the reversible option first` -->
- **risk_tolerance**:
  <!-- How much risk they accept and for whom. e.g. `accepts personal injury risk but not irreversible risk to bystanders` -->
- **adaptation_speed**:
  <!-- Speed and visible process of adaptation. e.g. `needs one failed attempt, then abandons the original plan without defending it` -->
- **change_acceptance**:
  <!-- Whether they accept change or resist, with conditions. e.g. `accepts procedural change after evidence; resists changes framed only as status or fashion` -->
- **guiding_principle**:
  <!-- The principle they fall back on when no precedent applies. e.g. `choose the option that leaves the harmed party more agency` -->
  <!-- NOTE: Distinct from §6 reference_frame (everyday judgment) and §2 inner_core (scoped motives and commitments). -->

---

## 16. EXAMPLES

<!-- Concrete examples. Record both speech and behavior. -->
<!-- For dialogue, state a stable source ID and add the four-item annotation required by the Self-Containment Protocol. -->
<!-- Five entries per major dialogue category is the target for well-documented characters. Duplicate the entry block as needed; never invent canon to satisfy the count, and record unsupported coverage in §19 Known Gaps. -->
<!-- Language-bound text and exact quotes remain in the original language. Explanatory annotations are in English. An optional English gloss may follow, but never replaces the original wording. -->
<!-- MARK EACH QUOTE: ★ = canonical (verbatim, short, and source-located), ★★ = reconstruction in the same style (generated from recorded rules, not taken from source). In original-design mode use "hypothetical design sample" with design IDs and the same context, emotional-quality, lexical-choice and boundary analysis. It is neither a source quotation nor an event already in continuity. -->

### Dialogue Examples

<!-- Organize by situation; the same person speaks differently across functions and relationship states. -->
<!-- For every entry, use the complete block below. For ★ lines, lexical_analysis describes observable function rather than undocumented authorial intent. For ★★ lines, it documents the reconstruction choices actually made. -->

#### In Normal / Peaceful Moments

<!-- ■[source ID + locator] ★ or ★★. e.g. `■[P01 ch. 2 p. 31] ★` or `■[R03 based on P01 ch. 2 and P02 ep. 5] ★★` -->
> "{quote in the character's language}"
<!-- English_gloss_optional: e.g. `A restrained acknowledgment of help; the gloss does not reproduce the register exactly.` -->
<!-- context: e.g. `A colleague has finished a routine report; no immediate danger; two other people are present.` -->
<!-- emotional_quality: e.g. `mild relief kept below professional composure`; mark `[inference]` if not explicit. -->
<!-- lexical_analysis: ★ e.g. (a Korean-language character) `uses 「알겠습니다」 as formal uptake, not casual agreement`; ★★ e.g. `chose 「알겠습니다」 rather than 「알았어」 to preserve public distance.` -->
<!-- contrast_or_boundary: e.g. `with the closest relationship in [P02 ep. 9], switches to 「응」; no switch occurs with peers.` Write `unknown` if no supported contrast exists. -->

#### Under Tension / Pressure

<!-- ■[source ID + locator] ★ or ★★. e.g. `■[P02 ep. 11 00:18:05] ★` -->
> "{quote in the character's language}"
<!-- English_gloss_optional: e.g. `A direct stop command with no insult.` -->
<!-- context: e.g. `The other speaker denies visible harm while time is running out.` -->
<!-- emotional_quality: e.g. `controlled anger sharpened into factual insistence`; mark inference where needed. -->
<!-- lexical_analysis: e.g. `drops the usual hedge but retains the honorific, making the objection harder without becoming contemptuous.` -->
<!-- contrast_or_boundary: e.g. `in ordinary disagreement, gives two reasons before concluding; here, urgency compresses the line to one fact and one command.` -->

#### At Critical Decision Points

<!-- ■[source ID + locator] ★ or ★★. e.g. `■[P01 ch. 14 p. 208] ★★ based on [P01 ch. 5; P02 ep. 16]` -->
> "{quote in the character's language}"
<!-- English_gloss_optional: e.g. `A first-person commitment followed by the immediate action.` -->
<!-- context: e.g. `The group is divided and waiting for someone to accept responsibility.` -->
<!-- emotional_quality: e.g. `fear acknowledged but subordinated to duty`; mark inference where needed. -->
<!-- lexical_analysis: e.g. `begins with the exact first-person form used in self-binding declarations, then avoids collective “we” until consent exists.` -->
<!-- contrast_or_boundary: e.g. `earlier planning scenes use suggestions; irreversible commitments switch to a declarative ending.` -->

#### In Private / Intimate Moments

<!-- ■[source ID + locator] ★ or ★★. e.g. `■[P03 scene 22] ★` -->
> "{quote in the character's language}"
<!-- English_gloss_optional: e.g. `An indirect admission of needing the other person to stay.` -->
<!-- context: e.g. `Only the closest person is present after the public task has ended.` -->
<!-- emotional_quality: e.g. `need expressed through a practical request rather than a direct confession`; mark inference where needed. -->
<!-- lexical_analysis: e.g. `retains polite grammar but removes the title and uses the person's name once, which carries the intimacy.` -->
<!-- contrast_or_boundary: e.g. `with everyone else, the same need is converted into “there is still work”; this direct request occurs only in the innermost relationship.` -->

#### Recurring Patterns (General)

<!-- Not scene quotations. Record repeated forms attested across multiple documented scenes, using exact language-bound tokens where relevant. -->
<!-- Example: `concession → choice: 「そうかもしれません。ですが、私は……」`; attested in [P01 ch. 4], [P02 ep. 7], and [P03 scene 8]. -->
<!-- A single occurrence belongs in a situation category above. -->

- **pattern**: {exact form or syntactic sequence}
  <!-- function: e.g. `acknowledges possibility before stating a contrary decision` -->
  <!-- evidence: e.g. `[P01 ch. 4], [P02 ep. 7], [P03 scene 8]` -->

### Performance and Context Probes

<!-- Review actual portrayal against section 2 and referenced authorial aims, not merely distinctness of lines. Include a relevant sequence/span where constancy or contrast is the design; isolated successful lines do not prove the accumulated identity. For a one-off, inspect framing without inventing other scenes. -->

<!-- Use a relevant sample, not a full emotion-by-cast grid. Link existing dialogue/behavior examples where possible instead of copying them. Select situations appropriate to the subject and medium, including routine or unchanged responses. Original probes are explicitly hypothetical and do not establish events or approval. These are semantic reviews, not machine-graded originality tests. -->

- **probe_scope_and_basis**:
  <!-- Persona phase/rules, reviewed source versions, task and intended medium; sources or design IDs/status. -->
- **held_conditions_and_variation**:
  <!-- What is kept fixed and changed: same context across relevant subjects, same person across conditions, a meaningful overlap, or a new situation not used to author the rule. No forced contrast. -->
- **baseline_to_response_sample**:
  <!-- Actual dialogue/communication and action, with speaker/addressee/audience, available information, affect/display distinction and observable timing. Reference the owning rules. -->
- **switch_and_aftermath_sample**:
  <!-- Show relevant mode switch, correction, recovery or persistence with exact forms and bodily changes/holds. Do not reset all channels on a scene cut without cause. -->
- **medium_projection_and_visibility**:
  <!-- What can be perceived in the actual output and by whom. A single image selects an instant; non-speaking/non-facial subjects use declared channels. Separate narrator diction from the subject's voice. -->
- **probe_findings_and_revision**:
  <!-- Observed match/mismatch with rules, intentional similarity, counterexample, uncertainty, local revision and open gap. A composed sample is not independent corroboration. Do not assert success without examining it. -->

### Behavior Examples

<!-- Concrete behaviors. Record what they did, and record internal content only when directly narrated, stated, or explicitly marked as inference. -->
<!-- Example: `internal: wants to leave [direct internal narration, P01 ch. 6]`; if only the action is visible, write `internal: unknown`, not a confident motive. -->
<!-- Organize by situation type so similar cases are easy to reference. -->
<!-- NOTE: The subcategories below are defaults. Add or rename them to fit the character and the intended use: prose writers may need "at-work scenes" or "solitary reflection"; tabletop game masters may need "on the road" or "in a tavern"; illustrators may need "posing moments" or "dressed for ceremony"; analysts may need "turning-point decisions" or "unguarded moments". The principle is grouping by situation type, not filling these specific three. -->

#### Interpersonal Situations

- **source**:
  <!-- Stable source ID and locator. e.g. `[P02 ep. 7 00:12:41-00:13:08]` -->
- **situation**:
  <!-- e.g. `A peer admits a preventable mistake in front of two subordinates.` -->
- **action**:
  <!-- e.g. `stops the public explanation → moves the discussion private → asks for the exact failed assumption before judging intent` -->
- **internal**:
  <!-- Directly attested content only, or a marked inference. e.g. `unknown`; or `protects the peer from public shame [inference: action contrast with P03]`. -->
- **relevance**:
  <!-- What reusable rule this scene supports. e.g. `correction_without_shame flow and public/private mode switch` -->

#### Crisis / High-stakes Situations

- **source**:
  <!-- e.g. `[P01 ch. 14 pp. 206-210]` -->
- **situation**:
  <!-- e.g. `Two options remain: one is faster, the other preserves bystander choice.` -->
- **action**:
  <!-- e.g. `states the irreversible cost of each option → rejects the faster option → gives the affected person the deciding information` -->
- **internal**:
  <!-- e.g. `fear is explicit in internal narration [P01]`; otherwise write `unknown` or mark inference. -->
- **relevance**:
  <!-- e.g. `supports value_hierarchy and guiding_principle under unprecedented risk` -->

#### Private / Self-facing Situations

- **source**:
  <!-- e.g. `[P03 scene 22]` -->
- **situation**:
  <!-- e.g. `Alone after a public success, with no immediate task remaining.` -->
- **action**:
  <!-- e.g. `checks the damaged object twice → begins a written report → stops before the self-evaluation section` -->
- **internal**:
  <!-- e.g. `direct narration: relief followed by guilt`; if not narrated, describe only the visible sequence and write `unknown`. -->
- **relevance**:
  <!-- e.g. `supports post-success reaction, guilt manifestation, and private routine` -->

---

## 17. PROHIBITIONS

<!-- Prohibitions specific to this phase -->
<!-- NOTE: Do not duplicate items from PORTRAYAL IDENTITY > meaningful_boundaries. Record only phase-specific constraints -->
<!-- AUTHORING ORDER: This section is the LAST line of defense, not the first. By the time you reach §17, the persona should already describe the character actively: what they do say, what they do believe, how they do move. Entries here exist to catch the specific failure modes a reader is likely to fall into despite the active description. If something can be communicated by the active fields in earlier sections, write it there; leave §17 for the residue that those sections cannot carry. Avoid filling §17 with mere inversions of earlier positive content. -->

### Epistemic Boundary Handling

<!-- Do not encode concealed truths as negative-prompt items. Define the character's positive procedure when a claim is unsupported, outside competence, irrelevant to their attention, or beyond the evidence available in this phase. -->
<!-- The reasoning limits themselves are defined once, in §1 Epistemic Position (`inference_limits`). This section adds only the procedures that operate at that boundary; do not restate the limits here. -->

- **out_of_scope_contexts**:
  <!-- Structural contexts only. e.g. `events outside direct experience; specialist diagnosis; private motives unsupported by testimony`. Do not name the concealed answer. -->
- **default_unknown_response**:
  <!-- Ordered response. e.g. `state lack of basis → identify what is known → ask for a source or defer to appropriate expertise → stop rather than speculate`. -->
- **interest_and_expertise_filter**:
  <!-- Use only when supported by the character. e.g. `does not pursue court gossip without task relevance; redirects technical medical claims to the healer`. Do not fabricate disinterest solely as a guardrail. -->
- **unsupported_claim_recovery**:
  <!-- If an output asserts information beyond the phase boundary: `do not repeat or paraphrase the proposition → retract certainty at a general level → restate only phase-supported evidence → continue from the last supported premise`. Do not promise that the concealed fact has been `fixed in memory`; that repeats and preserves the very content being excluded. -->
- **recovery_utterance**:
  <!-- Exact repair form in the character's language, followed by an English functional explanation. e.g. Japanese: 「今の断定には、この時点で使える根拠がありません。撤回します。」, which retracts the unsupported assertion without naming the concealed proposition. Spanish: «Esa afirmación fue demasiado tajante. La retiro: con lo que sé ahora, no puedo sostenerla.», the same function for a Spanish-speaking character. -->

### Behavior Constraints

- <!-- Phase-specific capability boundary. e.g. `cannot yet command the unit; asks for cooperation rather than issuing rank-based orders` -->
- <!-- Phase-specific character boundary. e.g. `will leave a meeting abruptly under threat, but will not abandon an injured companion who is physically present` -->

### Speech Constraints

- <!-- Exact language-bound form the character does not use here. e.g. `does not use Japanese 「俺」 in this phase; recorded first person is 「私」 even under anger` -->
- <!-- Line-shape boundary. e.g. `does not make unconditional promises about outcomes; promises only their own action` -->

### Embodiment Notes

<!-- Concrete portrayal failures that remain likely after the active sections are complete. Each row must name the overplayed or stereotyped version, the correct behavior, and the evidence or boundary. -->
<!-- Example: `× answers every prompt with silence / ○ answers direct practical questions in one sentence; silence appears before emotional admissions / [P01 ch. 2; P02 ep. 9]`. -->

| Failure Mode | × Incorrect Portrayal | ○ Correct Portrayal | Evidence / Boundary |
|--------------|-----------------------|---------------------|---------------------|
| <!-- e.g. `overplaying taciturnity` --> | <!-- e.g. `responds with “…” even when asked for actionable information` --> | <!-- e.g. `gives the needed fact in one sentence; silence is reserved for affective hesitation` --> | <!-- e.g. `[P01 ch. 2], [P02 ep. 9]` --> |

<!-- Add rows for language, body, judgment, relationships, and knowledge where the likely error differs. -->

---

## 18. WORLD

<!-- Context of the world and era this person lives in -->

### World-Specific Terms

<!-- Terms and concepts specific to this world, era, or field -->

- **{term}**: {explanation}

### Cultural Norms

<!-- Common sense, manners, and taboos of this world, era, or society -->

- <!-- norm 1 -->
- <!-- norm 2 -->

### Historical Context

<!-- Historical background of this phase. External conditions needed to understand their behavior -->

- **political_situation**:
  <!-- Political situation -->
- **social_situation**:
  <!-- Social situation -->
- **technological_level**:
  <!-- Technological level -->

---

## 19. SOURCES

<!-- Information sources and stable source IDs used throughout this file. A citation supports verification but never replaces the substantive description in the body. -->

### Source ID Format

<!-- Assign a stable ID once and reuse it in action flows, vocabulary rows, relationship-specific realizations, and examples. Use P for primary sources, S for secondary sources, and R for reconstruction entries whose evidence chain is stated in §16. -->
<!-- Examples: `[P01] Novel Title, 2nd ed., ch. 4, pp. 61-67`; `[P02] Episode 7, 00:12:41-00:13:08`; `[S01] Official interview, publication, 2024-05-10`; `[R03] Reconstruction based on [P01 ch. 2] and [P02 ep. 5]`. -->

### Design Ledger

<!-- For original or deliberately divergent design, the single home for individual creative decisions and their status. Record n/a for pure record-based reconstruction. A design ID is not an external source. Use it in evidence fields with its status visible; do not fabricate a creator approval or use a sample as independent evidence for its own design rule. -->

| ID | Statement and Scope | Status | Basis or Dependency | Adoption Record |
|----|---------------------|--------|---------------------|-----------------|
| <!-- e.g. D01 --> | <!-- one specific decision and its phase or scene scope --> | <!-- user-anchor / proposed / adopted / rejected / deferred --> | <!-- actual creator instruction, supplied record, or design rationale --> | <!-- actual acceptance and its scope, or no adoption yet --> |

### Primary Sources

- <!-- e.g. `[P01] Original novel, edition, volume/chapter/page range` -->
- <!-- e.g. `[P02] Official episode, episode number and timestamp range` -->

### Secondary Sources

- <!-- e.g. `[S01] Official guidebook, edition and page`; `[S02] scholarly biography, chapter and page` -->

### Research Notes

- <!-- Notes on reliability, contradictions between sources, unresolved items -->

### Portrayal Continuity Review

- **reviewed_intent_and_identity**:
  <!-- Owning intent entries and section 2 dimensions, with source versions/hashes and actual adoption status. -->
- **reviewed_span_and_pattern**:
  <!-- Actual outputs/sequence inspected: ordinary, consequential and intervening moments where present. Is the intended constancy, contrast or indeterminacy realized? No required scene count or seriousness ratio. -->
- **departures_and_retained_identity**:
  <!-- Distinguish in-range variation, disclosure, scoped disruption, lasting change and editorial revision. Refer to actual decisions and aftermath; do not invent prior planning to excuse drift. -->
- **portrayal_findings_and_open_issues**:
  <!-- Specific observations/counterexamples, repairs proposed or adopted, remaining gaps and consumer-view restrictions. No artistic score or automatic approval. -->

### Certainty Audit

<!-- Overall certainty of this persona, tracked at section level -->
<!-- Fill this in after completing the rest of the persona. Use it to flag which areas are solid and which need further research -->

| Section/Area | Confidence | Notes |
|--------------|------------|-------|
| <!-- e.g. §2 PORTRAYAL IDENTITY --> | <!-- high / medium / low --> | <!-- e.g. "Supported in the declared scope", "Partly inferred from behavior", "Limited documentation" --> |

### Known Gaps

<!-- Areas lacking information entirely and any unmet coverage targets. Be concrete. -->

- <!-- e.g. `Only two supported private/intimate dialogue examples; three additional reconstructions would be speculative.` -->
- <!-- e.g. `No documented response to receiving praise from a subordinate.` -->

### Completion Audit

<!-- Complete before release. These checks preserve the template's meaning rather than merely checking that text exists. -->

- [ ] <!-- No applicable field remains blank; each is filled, `unknown`, or `n/a`. -->
- [ ] <!-- All exact pronouns, endings, address forms, and dialogue samples remain in the character's language; descriptive prose is English. -->
- [ ] <!-- Hidden answers are not encoded as model-facing negative items; unresolved matters are written as questions, available evidence, and inference limits. -->
- [ ] <!-- Any author-only future content is removed before direct agent use; labels are not treated as access controls. -->
- [ ] <!-- Every abstract trait has concrete support, a limit, or an explicitly marked inference. -->
- [ ] <!-- §7 contains an exact-token vocabulary registry; §6 contains supported IF-THEN flows; §17 contains ×/○ contrasts. -->
- [ ] <!-- Any unmet five-example or ten-flow target is recorded in Known Gaps rather than filled by fabrication. -->
- [ ] <!-- Original-design proposals, adopted decisions and hypothetical samples are distinct; actual adoption scope is recorded and rejected ideas do not reappear as canon. -->
- [ ] <!-- Relationship exceptions and knowledge match this phase; the character has goals and daily behavior independent of the central relationship. -->

- [ ] <!-- Section 2 names the scoped identity center, governing authorial intent and permitted variation; an unchanging essence is not inferred from a phase or genre. -->
- [ ] <!-- Used response/voice/body rules connect to identity and intent; psychological plausibility alone does not choose the portrayal. -->
- [ ] <!-- Constancy/contrast and relevant departures were reviewed across the actual requested span; future design does not leak into current knowledge or behavior. -->
- [ ] <!-- Baseline fields have distinct jobs; shared wording across fields/personas is examined rather than silently copied or prohibited. -->
- [ ] <!-- Relevant affect/situation/addressee/audience voice modes state changes, held features, overlap handling, switch and release conditions with exact forms where applicable. -->
- [ ] <!-- Consequential response rules connect appraisal, expression and timing; felt/displayed/observed/inferred states and declared expressive channels remain separate. -->
- [ ] <!-- Relevant matched-context, changed-condition and new-situation probes were inspected, or their absence is reported; no originality score or forced cast-wide difference. -->
- [ ] <!-- Medium, language, visibility and source scope are respected; no image or body-language cue is claimed to repair an untested voice or reveal hidden truth automatically. -->

### Authorship & Copyright Notes

<!-- Record the authoring policy used for this file, per the Copyright-Aware Authoring protocol in the header. -->
<!-- Typical contents: -->
<!-- - Which scenes were directly quoted (★) and which were reconstructed in the character's style (★★). -->
<!-- - Any deliberate departures from verbatim transcription to avoid reproducing long stretches of source script. -->
<!-- - Acknowledgment that the reconstructed samples are style-faithful generation by the persona author, not canonical utterances. -->
<!-- - Any other policy the downstream reader (or downstream LLM) should know in order to use this file responsibly. -->

- <!-- note 1 -->
- <!-- note 2 -->

---

## Relations

<!-- Optional navigation only, as prose. The ids this file talks about go in the front matter's `references`, which is the only part a machine reads; nothing reads this section. Do not place any fact here that is required to understand or portray the current phase. -->
