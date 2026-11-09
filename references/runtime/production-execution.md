# Production operations

The operation owner compiles authored input, saves revisions, prepares and
executes requests, records actual results, or evaluates and adopts those results.
Select the current operation with `execution_routes.py read ROUTE --operation
OPERATION --execution EXECUTION`, using the task's `authored`, `external` or
`dispatcher` execution kind. The reader delivers the complete applicable operation documents and selected
specialist knowledge; this index alone is not their contract.

| Operation | Complete owner |
| --- | --- |
| Author or revise | [Production authoring](production-authoring.md) and [Production direction](production-direction.md) |
| Save and deliver authored text | [Authored storage](production-authored-storage.md) |
| Prepare a model request | [Production preparation](production-preparation.md) |
| Author an external image request | [Image input](production-image-inputs.md) and [External request inputs](production-external-inputs.md) |
| Compile a dispatcher image request | [Generation Package](generation-package.md) |
| Execute a prepared request | [Prepared request execution](production-request-execution.md), [Production permissions](production-permissions.md), and the selected [dispatcher](production-dispatch.md) or [external host](production-external-execution.md) contract |
| Recover an execution | [Production status and recovery](production-recovery.md) with its selected execution contract |
| Observe and assess | [Production review](production-review.md) |
| Select and adopt | [Production adoption](production-adoption.md) and [Production permissions](production-permissions.md) |
| Interpret a failure | [Production diagnostics](production-diagnostics.md) |

A saved revision, prepared request, actual external result, evaluation and
adoption each record the action that occurred. The requested result determines
completion. Discussion without a saved artifact needs no Production run.

## Maintenance checks

When changing these public contracts, follow [Maintenance testing](../maintenance/testing.md#required-checks).
Its [production execution coverage](../maintenance/testing.md#production-execution-checks) maps each contract to its regression suites.
