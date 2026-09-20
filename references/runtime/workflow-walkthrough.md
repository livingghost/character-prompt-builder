# Workflow Walkthrough

Activate this route to check setup or a changed workflow without service credentials or paid image generation. This is an explicitly synthetic regression fixture, not evidence of real retrieval or human approval.

```bash
python examples/feature-walkthrough/run.py --out /tmp/cpb-walkthrough
```

Use `--help` for inputs. Choose a new output directory: existing work is never overwritten. The example creates a tiny independent locked fixture pack and isolated pack state; writes prompt, negative, plot, retrieval and production inputs; calls `scripts/build_generation_payload.py` through its actual argument parser; calls the actual verifier; then invokes the actual dispatcher with only service-boundary operations mocked. It records one mock image and its request in a new Studio. No real credentials are read, uploaded, or sent.

Output includes all inputs, exact `builder-arguments.json`, `generation-package.json`, `verified.json`, Studio history, `transcript.txt` and `walkthrough-report.json`. The report must say `verified: true`, `external_requests: 0`, and `mock_dispatch_count: 1`. Missing files, stale approval, missing/mismatched retrieval, invalid production or invalid output destination fail instead of marking readiness.

For prompt-only work, stop after delivering an unapproved draft. Without the target interface or visual dependencies, stop at the appropriate portable draft/verified handoff, and state what remains unexecuted. Do not treat fixture success as permission to send. A real run needs actual retrieval, actual approval of plot and exact request, the declared service interface and dependencies, and explicit send authorization. Image adoption and catalog registration require separate scope approvals.

The state-aware executable fixture remains `python examples/state-aware-pilot/build_example.py`. It writes an illustrative settled retrieval record rather than pretending that a production lookup was performed. Its model-facing example in [Image Generation Runtime](image-generation.md) supplies both `--plot-file` and `--retrieval-record-file`.

Run `python scripts/feature_workflow_smoke_test.py` for the complete feature regressions. That suite executes this walkthrough and checks its outputs, not just the presence of strings in a document.
