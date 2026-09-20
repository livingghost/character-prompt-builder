# FilmWorld: Source-Derived Ideas and CPB Design Decisions

Source: Jialong Zuo et al., *FilmWorld: Agentic Novel-to-Film Generation through Dynamic Cinematic World Modeling*, arXiv:2607.19038v1, supplied manuscript, 42 pages. This note records what was borrowed from that manuscript; a reproduction result, a code integration, or an update on the public project's availability is a different document. This skill leaves the PDF out.

## Source-derived concepts

Section 3.3 (page 5) distinguishes entities, state assignments, state identifiers, plot-conditioned transitions and rendering directives. Section 4.1 (page 6) and Figure 3 (page 7) separate symbolic state planning from pixel generation. Section 4.2.2 (page 8) describes the paper's discretized character/location/prop tuples and first-appearance visual anchoring. Section 4.3.2 (pages 9-10, Figure 4) combines textual terminal constraints and visual keyframes for actual cross-shot motion. Section 4.3.3 (pages 10-11) describes diagnostic correction and selection between candidates.

Appendix E.1 (page 42) explicitly identifies upstream interpretation errors, continuous phenomena quantized into discrete states, missing geometric priors, limited artistic evaluation and explicit directorial intent as limitations or future work. Provenance links and uncertainty-aware construction are suggested safeguards there, and this CPB note treats them as suggestions rather than implemented guarantees. Section 6.4 and Figure 16 (pages 22-23) distinguish correct symbolic specifications from remaining perceptual generation failures.

## CPB adaptations, not claims made by the paper

CPB keeps its existing event ledger and deterministic resolver. A local realization plan binds sources and coordinates independently requested snapshots; state stays in the ledger rather than forking into a new canonical cinematic world model. FilmWorld's agents, numerical evaluation, latency, model choices, benchmark and parallel image/video renderer stay unreproduced by the helper.

CPB's method reaches beyond adapting prose into film. It admits static, unpeopled, nonlinear, non-dramatic and nonvisual work, and it leaves themes, genres, cast and moral open. Story order and presentation order are separate; state continuity assertions are explicit rather than required between every adjacent artifact. Untimed or unresolved chronological designs may stay outside the helper's integer-order serialization.

A reference key hashes only explicitly chosen role-relevant facets rather than a universal age/costume identity tuple. It is a retrieval aid rather than evidence of perceptual identity or asset adoption. An initial generated visual is a candidate until adopted through the existing reference workflow.

Source locators, pinned files and consumer leaf selection implement a bounded bookkeeping and export mechanism. Interpreting source truth, resolving ambiguity, certifying creator consent and inferring which facts a recipient may know all stay outside it. Actual instructions and exports need editorial review. Creator intent and persona patterns stay separate from fact and state.

The eight portrayal principles are original CPB authoring heuristics. The manuscript lacks an identity-core dictionary. No numerical personality ranking, stereotyped trait bundle, proven image wording or universal emotion-to-gesture mapping is derived from it.

Current tests check structure, deterministic states, explicit comparisons, source changes and output boundaries using synthetic fixtures. FilmEval scores, model experiments and any assessment of a finished work's quality lie outside them. Symbolic correctness leaves faithful pixels, convincing acting and an accomplished authorial voice unguaranteed.
