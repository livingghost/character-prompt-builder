# Image input

The common `image_input` task property names a Studio-relative
`image-input-plan`, using `templates/image-input-plan.template.json` and
`schemas/authoring/image-input-plan.schema.json`. It serves both ordinary
reference generation and existing-image editing. A new scene may use several
identity, outfit or environment references without declaring a scene source.
Only an actual edit adds `semantic_edit`, whose owner is source, change,
preserve and review meaning.

The image input declares one model target, ordered references and an
`external_request`. Dispatcher work supplies at least one reference, sets
`external_request: null`, and uses its ordinary prepared set and compiled request.
Every external image task pins one exact saved request through this plan.
External non-image work does not need an image-input plan.

An exact text-only image request uses `references: []` and a complete, non-null
`external_request` with `reference_fields: []`. Preparation pins the model
evidence, saved request and any acquired schema through the same binding.
The recorded host call is compared with that exact request during settlement.
A reference-free plan without an external request is invalid. Semantic editing
still requires its selected source image.

Each reference names `id`, `role`, `file`, optional `sha256`, `use_for` and
`do_not_transfer`. Optional `subject_uses` names Production Specification
subjects and intended uses, with priority `0` highest within the same subject
and use. Empty assignments are valid for environment or other inputs without
a named subject. Role names do not grant additional authority, and assignments
cannot enlarge the source's allowed influence.

For existing canonical references, `prepared_references` names their canonical
prepared-reference-set file. Preparation validates its live source provenance,
adoption and selection, pins that file and keeps the complete set. Logical
rows must match its original bytes, role, authority and subject assignments
exactly. The binding consumes the existing set; it cannot reclassify canon as
supplied pixels to replace a state selection or pack Reference Use Plan. Input
files remain the original images used for the exact external media mapping.
A dispatcher additionally checks its declared set against `generation.references`.
External preparation saves each actual prepared delivery carrier in the run's
ordinary content-addressed object store after checking its recorded hash.
It also archives accepted Studio proofs and every transitive
artwork, provenance and approval file through the existing Studio reference
owner. The run stores these under `image-input.references/studio/` and in its
ordinary snapshot object store. The prepared run uses that saved source
selection and its captured proof for execution and review. Later source edits,
withdrawn placement or changed acceptance do not rewrite this selection. A new
preparation resolves the eligibility of its newly selected references.
Execution and review use saved source and carrier bytes even after their live
files move. Preparation establishes the chosen input; the submission
records establish the actual call and its transmitted media.

External local-file transports are explicit in the request mapping through
`local_file: true`. The host request receives paths to the captured carrier
bytes, including a board or rasterized rendition when selected. An opaque
provider value retains its original value and upload evidence. Source images,
delivered media, logical roles and board regions remain separate in the host
view; none is inferred from a filename or substituted for another.

For original supplied files, the common input directly states task-specific
scope. `prepare_generation_references.py --image-input-plan-file` projects it
into the existing prepared set. Matching source bytes or delivery media can
share one attachment while retaining every logical role, original source and
subject use. A verified board retains its panel lineage. External mappings do
not replace several originals with an untracked board.

[External request inputs](production-external-inputs.md) owns the exact provider schema and authored request fields for external execution. Dispatcher input uses the selected offering and compiled Generation Package.
