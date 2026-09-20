## Observable change

Describe which real file, field, setting, exact submitted text, evidence requirement, or review observation changes.

## Deletion/contrast test

Explain why the new label or distinction cannot be removed without changing the submission package. Include a minimal contrast pair when applicable.

## Evidence

- [ ] Target-specific facts include a dated official source or direct observation.
- [ ] Behavioral claims include a real run record and all returned variants.
- [ ] Documentation-only examples say `not run`.
- [ ] Exact submitted text contains no internal IDs or unresolved references.

## Validation

The required checks are in [CONTRIBUTING.md](../CONTRIBUTING.md), and
[Release Validation](../references/release/validation.md) is the sole authority for
publication. Neither is copied here: a copied sequence drifts from the document it
claims to follow, and this one had already lost the dependency profile and the
documentation gate.

- [ ] Core dependency profile checked, and the focused smoke test run for every subsystem changed.
- [ ] Generated artifacts rebuilt before validating anything that depends on them.
- [ ] Documentation changes ran the documentation contract gate.
- [ ] Public declarations, exact payloads and schema closures were checked with local conformance fixtures.
- [ ] Publication, where it applies, followed Release Validation rather than this checklist.
