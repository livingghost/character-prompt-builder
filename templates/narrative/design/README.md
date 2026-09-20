# Design records

These are author-facing records of the work's scope, chosen experience, form, world interfaces,
decision provenance, alternatives and change impact. They are not in-world facts, personas,
shared narrative JSON, executable state, or generation approvals.

Start with `project.md`, created from the full design template at initialization. Create another
scoped note only when useful with `narrative_entity.py ... add design <id> --name "<name>"`.
Creation uses the installed current full design template. Read its instructions; fill
relevant sections, and mark examined inapplicability or deliberate deferral rather than making
up a protagonist, theme, conflict or plot to satisfy the form.

Every note uses the ordinary entity front matter: `kind: design`, a filename-matching `id`, an
optional `name`, and `references: []` listing entity or declared character IDs it relies on.
Design notes are explicit authoring roots in the index, so a world rule can be connected before
any character or scene exists. Their references are checked and updated by entity rename just
like other declared references. The body contains rationale and source sections; prose mentions
and Markdown links are not automatically rewritten or interpreted as canonical claims.

The index checks drafting blanks and ID links; it does not understand the decision ledger or
infer dependencies, approval, theme, genre or world coherence from prose. All design notes are
indexed, including proposals and alternate branches. Index reachability is not adoption.
Do not hand an author-only note to a limited-viewpoint consumer when it exposes concealed facts.

## Portrayal intent and review

The Authorial intent register explicitly retains the creator's choices about recognition,
variation, contrast/cadence, departure and audience information. Each `### Intent <id>` entry owns
its status and rule; the decision ledger refers to it. Use `authorial_intent_refs` links from
subject profiles or realization notes, and entity IDs in front-matter references. World facts
stay in world records, internal traits in persona, and actual cues in a realization.

The installed skill's `authorial_intent_audit.py` checks exact intent targets, required fields and
source fingerprints. It does not establish approval, applicability, artistic success or spoiler-safe
views. Use the Portrayal review to inspect actual outputs and their cumulative pattern rather than
claim coherence from a filled register. No number of subjects, theme, genre or fixed essence is required.
