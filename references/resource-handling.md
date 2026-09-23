# Resource handling and limits

## What is and is not a content limit

The tools leave these sizes unbounded:

- source-file size;
- Persona (character definition) size;
- dependency-closure count;
- material bundle size;
- production artifact size;
- imported-protocol payload size.

Text and JSON decoding still require working memory; removing an invented byte ceiling leaves an in-memory parser far from a constant-memory database. A real allocation, disk, decoder or operating-system error is a failure rather than an empty or successful result. Keep untrusted workloads in an execution environment with the resource controls appropriate to that machine, because sandboxing belongs to that environment rather than to these local tools.

Some checks stay: paths must remain within their declared root, a symlink that would escape the trust boundary is rejected, and duplicate JSON keys, invalid hashes, invalid coordinates and unapproved operations remain errors. Each of those checks follows a real boundary and says nothing about how long a book or Persona should be.

## Explicit operator budgets

A scene plan can specify `max_document_bytes` when a particular consumer (the downstream writer, actor or renderer) has an actual budget; omitted, it leaves document size unbounded. When the selected material exceeds the budget, preparation reports the conflict, keeps every definition whole and leaves the partial document unready.

`authorial_intent_audit.py` accepts `--max-input-bytes` and `--max-files`; `persona_expression_audit.py` accepts `--max-input-bytes`. These are optional operator budgets with unset defaults; a valid project needs none of them. A budget conflict makes the audit incomplete and unsuccessful rather than silently discarding a linked definition. Duplicate-expression `--min-chars` is an explicitly adjustable advisory display filter rather than a file-size or expressive-quality requirement.

An agent evaluation condition declares `timeout_seconds` as a positive finite duration, or `null` to run free of an application deadline. Optional `max_log_bytes` is a positive integer or `null`, with an unset default. Both values belong to the inspected and explicitly approved study. The declared positive repetition count is the only ceiling on repetitions, and inspecting a study leaves it unexecuted.

Logs are written to disk and read line by line for metrics; artifacts and logs are hashed to EOF. An exceeded log budget stops the run and makes the evidence unsuccessful. Every byte already captured remains on disk, including a burst between polls, and a saved log is kept whole rather than clipped to fit. The threshold is a stop condition rather than a guarantee against a disk quota; strict disk, memory and process containment must be enforced by the execution environment. Missing metrics remain missing.

## Review output is not a summary of the evidence

The default production HTML review includes complete text and all attachments. An operator may request `artifact_review.py --preview-chars N` to limit only the displayed text, measured in Unicode characters. The report records that choice and identifies a shortened preview; the complete attached bytes and their hashes remain available. Source material, production evidence and any quality verdict stay as they were.

## Constraints retained for an actual reason

Three constraints follow the value's own representation:

- normalized opacity is within `[0,1]`;
- a crop has four coordinates within its current canvas;
- a SHA-256 is exactly 64 hexadecimal characters.

Model input dimensions, number of references, text-field lengths and output counts come from the selected model/service contract or an explicit production grant rather than from a universal imagined model. An unknown target limit remains unknown.

The Agent Skills format limits the frontmatter `name` to 64 characters and `description` to 1024 characters. Those metadata-field limits leave README prose and project materials unbounded, and a recommendation for a shorter skill body stays a recommendation rather than a correctness failure. Source: [Agent Skills specification](https://agentskills.io/specification).

Installed image decoders have their own documented safety checks, and the product keeps Pillow's decompression-bomb protection enabled rather than pretending arbitrary allocations are safe. Source: [Pillow Image module](https://pillow.readthedocs.io/en/stable/reference/Image.html). Actual codec and OS failures remain visible.

## Implementation and validation policy

Implementation sizes are separate from accepted-content limits:

- a working buffer, such as a hashing buffer reused until EOF;
- a cache capacity, which bounds retained cache entries only: a search cache may evict a computed entry and rebuild it from the original record, and eviction must leave results and source records untouched;
- a search page size, layout profile or explicit search pagination, which is an output choice rather than a general limit on the authored definition, and whose excerpt complements rather than replaces full-record inspection;
- a numerical tolerance, which must name the measured quantity;
- a test watchdog, which detects a stalled fixture and says nothing about the maximum length of user work.

A presentation default is likewise silent about whether the omitted material matters.

A new content ceiling needs a reason beyond keeping fixtures, context or a release archive small: record the external constraint or explicit operational budget with its units, owner and failure behavior. Preserve complete sources and evidence. Test both successful complete processing and actual contract violations; a passing structural test says nothing about semantic understanding or writing quality.

## Network and media execution deadlines

Each of these variables sets an optional positive finite deadline in seconds:

- `PRODUCTION_HTTP_TIMEOUT_SECONDS`: each HTTP operation;
- `VALIDATE_REGRESSION_TIMEOUT_SECONDS`: each standalone regression that
  `scripts/validate.py` runs, reported in the validation result when exceeded;
- `SEARCH_REGRESSION_TIMEOUT_SECONDS`: each isolated worker that
  `scripts/search_regression.py` runs, reported as a failed case range when exceeded;
- `EXAMPLE_COMMAND_TIMEOUT_SECONDS`: each command an example under `examples/` runs;
- `MEDIA_PROBE_TIMEOUT_SECONDS`: each ffprobe run that measures an audio or video capture.

An absent variable leaves the application free of a deadline of its own. These
are execution settings rather than permission to submit: an ambiguous network
result still follows the recorded recovery path instead of a blind resubmission.

Timeouts stop the operation and report failure; they never certify a shortened
result as the requested complete output. A CI/test harness may independently
limit its own run time, and such a harness deadline is a harness setting rather
than a product input limit.

## Verify the resource behavior

Run `python scripts/resource_handling_smoke_test.py` from this skill directory.
The fixtures exercise:

- complete sources and JSON above 32 MiB;
- complete logs with a metric at the end;
- Unicode previews;
- explicit-budget failure;
- actual service and geometric constraints;
- the locally available media operations.

They run no model and establish nothing about a machine's maximum safe workload.
