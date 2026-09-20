# Production permissions

A task points to an `authority` JSON file. Its `issuer` and
`evidence.path`/`locator` refer to the instruction or approval whose bytes are
pinned during preparation. The host must check that this is the user's real
authority: the schema authenticates no issuer, proves no natural-language
condition, and turns no agent-filled form into consent.

Each grant names an `id`, `actor`, `mode` (`direct` or `delegated`), allowed
`operations`, exact `targets`, `limits`, `protected_criteria`, and optional UTC
`expires_at`. Modes describe the source of the instruction; both are bounded,
and both bind the actual operation. Use an explicit stop decision for
ambiguity, contradictory constraints, unavailable controls or exhausted
authority.

Operations are independent: `direction`, `edit`, `submit`, `select`, `adopt`.
A budget leaves personality change and canonical adoption unauthorized, and
permission to select a delivery leaves a new submission unauthorized. Delegated
creative decisions can proceed on their own, within their scope, protected
conditions and stop conditions.

Targets are exact strings rather than wildcards. Direction uses `purpose` and
`decision:<id>`; submission and delivery selection use `delivery`. Repairs can
affect `purpose`, `decision:<id>`, `source:<id>`, `criterion:<id>`, `delivery`,
`execution`, or `authority` as detected by the preparation comparison.
Canonical owner operations use `canon:sheet` or `canon:catalog`. Grant only the
necessary targets. A changed source or criterion is detected whatever the
repair is labeled, "local edit" included. Protected criteria are checked on
revision and the next direction handoff.

`limits.uses` counts authorization reservations, `limits.outputs` counts
authorized submissions, and `limits.cost` is null (no paid work) or
`{currency, amount}`. Money is a nonnegative decimal **string**, never a
floating-point estimate. A submit request also carries a quoted `basis`, an
explicit zero-cost basis when applicable, and binds its exact output count.
Reserve a conservative permitted upper bound rather than a promise of final
billing. Independent grants share a budget only when the author deliberately
uses the same grant identity and limit.

## Reservation and consumption

Obtain an operation intent, then use `draft-authorization` to write an
**unapproved** draft; it starts with a blank reason, an empty cost and stop
assessments false, and creating it grants nothing. Fill its reason, quote if
submitting, and every stop assessment from actual evidence. `authorize` checks
the declared grant and appends a reservation to the existing production run.
The returned receipt SHA-256 is passed to the consuming operation, which
rechecks the exact payload, actor, target set, authority, expiry and cumulative
limits.

Reservations accumulate across all preparations with the same work task and
grant ID; repeating preparation or revising the task leaves usage where it is,
and an uncertain or unused reservation stays counted. Input changes require
current preparation: edits may intentionally change the parent's source files,
while changed authority evidence and changed implementation are excluded from
reuse. A changed quote, service, package, seed, count, selection reason or
recipient requires a new matching authorization. Receipts are integrity records
rather than cryptographic user signatures. Leave run files unedited and
undeleted, whatever budget they hold.

External execution uses `claim-external` before the host calls its chosen tool.
It pins recipient, consumer and output count; the script cannot observe an
unreported call outside this process. Dispatcher execution reserves before
upload or send, refuses a response-count mismatch before downloading unexpected
outputs, and treats an uncertain call as one submission rather than retrying
it. `recover-recording` only records already acquired, verified files and makes
no network call.

Canonical adoption has a separate owner approval plus an `adopt` authorization.
Obtain `adoption-intent`, reserve it, then use `adopt`; it calls the owning
adoption workflow and its journal. A later `studio-adoption` selection verifies
the actual adopted bytes. Low-level packaging and owner utilities show nothing
about whether a production task has passed these gates.
