# Workflow Walkthrough

Activate this route to check setup or a changed workflow without service credentials or paid image generation. This is an explicitly synthetic regression fixture, not evidence of real retrieval or human approval.

```bash
python examples/feature-walkthrough/run.py --out /tmp/cpb-walkthrough
```

Use `--help` for inputs. Choose a new output directory: existing work is never overwritten. The example enables the bundled commons pack in a new pack state under the output directory. It creates a studio, opens a work task, reads the generation route, writes the task, prompt and synthetic authority, and prepares a production run. It settles retrieval, builds the package for `grok-imagine-image-2.0` with `scripts/build_generation_payload.py`, and runs `scripts/dispatch.py` without `--send`. Any network connection attempt fails the run.

Output includes the authored inputs, `builder-arguments.json`, the project with `generation-package.json`, `preview.json`, `transcript.txt` and `walkthrough-report.json`. The report shows the exact request, its validation, `external_requests: 0` and `sent: false`. Missing files, stale approval, missing or mismatched retrieval, invalid production or an invalid output destination fail instead of marking readiness.

For prompt-only work, stop after delivering an unapproved draft. Without the target interface or visual dependencies, stop at the appropriate portable draft/verified handoff, and state what remains unexecuted. Do not treat fixture success as permission to send. A real run needs actual retrieval, actual approval of plot and exact request, the declared service interface and dependencies, and explicit send authorization. Image adoption and catalog registration require separate scope approvals.

The state-aware executable fixture remains `python examples/state-aware-pilot/build_example.py`. It writes an illustrative settled retrieval record rather than pretending that a production lookup was performed. Its model-facing example in [Image Generation Runtime](image-generation.md) supplies both `--plot-file` and `--retrieval-record-file`.

Run `python scripts/feature_workflow_smoke_test.py` for the complete feature regressions. That suite executes this walkthrough and checks its outputs, not just the presence of strings in a document.
