# Security policy

## Supported version

Security fixes are applied to the latest release.

## Reporting

Please report vulnerabilities privately through GitHub's security advisory feature when available. Do not include secrets, private media, credentials, or user-identifying production data in a public issue.

## Relevant threat boundaries

This repository is a local agent skill with pack-backed prompt, state, visual-reference, and generation-package workflows. Important risks include:

- instructions embedded in imported project notes, filenames, metadata, prompts, logs, or media captions;
- secrets or private absolute paths copied into production records;
- stale pack state or derived catalog caches resolving removed or superseded records;
- a pack artifact being attached to the wrong canonical record or granted authority outside its declared intended influence;
- a Generation Package referring to carriers outside its named package companion;
- production-only identifiers leaking into model-facing text;
- target documentation becoming stale while a saved submission recipe is treated as current;
- a fictional or partial example being represented as an observed generator result;
- generated accidents being written into canon without user approval;
- release workflows granting write permission to build steps or unpinned third-party actions.

The project does not operate a public archive-upload or extraction service. Its validation boundary addresses realistic skill use: imported content, changing packs, stale derived state, incorrect reference authority, incomplete publication, and accidental disclosure. The release workflow separates read-only build/validation from the write-enabled publication job and pins GitHub Actions to full commit SHAs.

## Non-secret example inputs

The example inputs and generated artifacts under `examples/state-aware-pilot/` are original illustrative records created for this repository. They contain no user data, no credentials, and no private absolute paths. Bundled evidence artifacts are project-owned text content; user-owned and third-party packs are not part of the tracked core release.
