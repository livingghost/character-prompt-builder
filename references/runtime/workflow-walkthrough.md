# Workflow Walkthrough

Activate this route to check setup or a changed workflow without service credentials or paid image generation. This is an explicitly synthetic regression fixture, not evidence of real retrieval or human approval.

```bash
python examples/feature-walkthrough/run.py --out /tmp/cpb-walkthrough
```

Use `--help` for inputs. Choose a new output directory: existing work is never overwritten. The example enables the bundled commons pack in a new pack state under the output directory, and any network connection attempt fails the run. It runs these steps:

1. create a studio, add a character and open a work task;
2. read the generation route and the model's guidance card for `grok-imagine-image-2.0` on Runware;
3. run real catalog lookups and inspections, then settle retrieval with labeled synthetic author choices;
4. write the render intent, draft the Production Specification for a one-off portrait of a person, and write the task;
5. run `production_workflow.py prepare`, then `status --budget` on the prepared run.

The output directory holds the studio, `pack-state.json`, `prepare-arguments.json`, `preview.json` (the request preview and execution plan), `transcript.txt` and `walkthrough-report.json`. `transcript.txt` lists each command it ran with a short result. Missing files, stale approval, missing or mismatched retrieval, invalid production or an invalid output destination fail instead of marking readiness. The report, trimmed:

```json
{"ok": true, "synthetic_fixture": true, "external_requests": 0, "sent": false,
 "production_run": "01a10326-b95b-7a89-a7ca-4a734c69bed1",
 "request_validation": {"mode": "target-schema",
   "contract": "@pack/01a0043b-2250-720d-87b7-f1e6fd7ed230/resources/observed-schemas/grok-imagine-image-2.0.runware.json"},
 "request": {"height": 1248, "model": "xai:grok-imagine@image-2.0", "numberResults": 1, "settings": {"quality": "medium"},
   "taskType": "imageInference", "width": 832, "positivePrompt": "Photographic portrait. A woman in a green raincoat ..."},
 "readiness": {"state": "configuration_required", "executable": false,
   "diagnostics": [{"code": "AUTHORIZATION_REQUIRED"}, {"code": "COST_UNCONFIRMED"}]}}
```

For prompt-only work, stop after delivering an unapproved draft. Without the target interface or visual dependencies, stop at the appropriate portable draft/verified handoff, and state what remains unexecuted. Do not treat fixture success as permission to send. A real run needs actual retrieval, actual approval of plot and exact request, the declared service interface and dependencies, and explicit send authorization. Image adoption and catalog registration require separate scope approvals.

The state-aware executable fixture remains `python examples/state-aware-pilot/build_example.py`. It writes an illustrative settled retrieval record rather than pretending that a production lookup was performed. Its model-facing example in [Image Generation Runtime](image-generation.md) supplies both `--plot-file` and `--retrieval-record-file`.

Run `python scripts/feature_workflow_smoke_test.py` for the complete feature regressions. That suite executes this walkthrough and checks its outputs, not just the presence of strings in a document.
