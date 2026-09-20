# Batch Generation Runtime

Use this document only when the user requests several images at once: several variants of one model dispatched concurrently, or several models dispatched through their endpoints at the same time. Complete [Image Generation Runtime](image-generation.md) first; a batch changes how verified generation inputs are dispatched and reviewed, never how any single image is directed, packaged, or forwarded.

## Contents

- [Batch scope and authority](#batch-scope-and-authority)
- [Authoring the job list](#authoring-the-job-list)
- [Building the plan](#building-the-plan)
- [Dispatch and results](#dispatch-and-results)
- [Failure policy](#failure-policy)

## Batch scope and authority

A batch is a dispatch and review layer over verified Generation Packages. It does not merge prompts, share one image intent across jobs, or let one model's output stand in for another's. Each job keeps its own image intent, adapter, negative transport, and reference set exactly as the Image Generation Runtime requires.

Keep judgment and automation separate. The agent owns meaning, per-job direction, model selection, review, and acceptance. The plan script owns deterministic job validation, variant expansion, hashing, and batch-ledger construction. The batch never decides what an image should look like.

Every result is recorded where a single image would be recorded, as its own iteration in the studio with the record it came from, that record's family, the request as sent, and the answer. `scripts/dispatch.py` writes that record itself, for a variant of a batch exactly as for one image. The batch's own two artifacts sit beside that record rather than in place of it: `batch-results.json` reconciles the variants that were planned against the images that came back, and `batch-ledger.json` commits the plan hash and rolls the review up per batch and per job. Neither is the trail of what was generated; the studio is.

A job's model decides how its prompt is written. Models do not read a prompt the same way: a rating term one family carries is unknown to the next, the quality block differs, multi-word tags are spelled differently, the working weight differs, and the blocks and their order differ. Resolve each job's family with `python scripts/prompt_dialect.py --model <model-id>` and compose that job from what comes back. Never carry one job's quality block, rating term, period term, or weight into a job on another model, and never reuse one job's rendition for a different model by changing only the model name.

Every job forwards its own verified Generation Package. A batch plan is usable only when every referenced package already passed `verify_generation_payload.py` for its target model. The plan commits each package's SHA-256 so a package edited after planning is detectable; if any committed hash no longer matches the file, rebuild the plan before dispatching.

## Authoring the job list

Write one `batch-jobs.json` UTF-8 artifact per batch:

```json
{
  "label": "portrait closeups",
  "jobs": [
    {
      "job_id": "closeup-flux",
      "target_model": "flux-1-dev",
      "transport": "runware-mcp",
      "generation_package": "packages/closeup-flux.json",
      "count": 3,
      "seeds": [11, 22, 33],
      "parameters": {"width": 1024, "height": 1024},
      "note": "front closeup variants"
    },
    {
      "job_id": "scene-sdxl",
      "target_model": "sdxl-base",
      "transport": "comfyui-local",
      "generation_package": "packages/scene-sdxl.json"
    }
  ]
}
```

Each job requires a unique nonempty `job_id`, a nonempty `target_model` naming the model its Generation Package was built for, and a `generation_package` relative to the jobs file. The batch layer records that name; the model record itself was already resolved against the enabled packs when the Generation Package was built, and the adapter resolves it again at dispatch. Optional `count` (default 1) expands one job into that many concurrent variants of the same model; optional `seeds` must supply exactly one nonnegative integer per variant; optional `parameters` and `note` copy onto every variant of the job. Package paths, image paths, and result paths are relative, must stay inside the directory of their referencing file, and may not be symbolic links; absolute paths and parent references such as `../` are rejected.

`transport` names the endpoint a job's variants are sent through: one host interface with one configuration, such as a hosted inference API, a local UI, or a tool connection. Jobs that will be dispatched through the same configured endpoint share one `transport` value; jobs that need a different endpoint configuration use a different value. Omitted `transport` defaults to `default`. Two models from different providers cannot share one dispatch block because no single endpoint configuration serves both; give them different `transport` values so the plan groups them honestly.

## Building the plan

```bash
python scripts/build_batch_plan.py plan --jobs batch-jobs.json --out batch-plan.json
```

The command rejects duplicate job ids, missing packages, seed-count mismatches, nonpositive variant counts, and non-object parameters. It expands every job into deterministic variants (`<job_id>#v01`, `#v02`, ...), commits each package hash, and writes a dispatch summary grouped by `transport`, then by model. The plan output reports job count, variant count, and the sorted endpoint groups on stdout.

## Dispatch and results

Dispatch concurrency is real only inside one endpoint. For each `transport` group, send that group's variants through its configured endpoint as one concurrent block: multiple models on the same endpoint run as separate simultaneous calls, and one model's variants run as simultaneous calls with their per-variant seed and parameters. Groups with different `transport` values go through different endpoint configurations; issue them as separate requests and never merge them into one call. Separate requests may still overlap at the agent layer, but each request is formed, sent, and answered by exactly one endpoint.

How each variant reaches its model is unchanged: form the request from that variant's verified Generation Package exactly as the Image Generation Runtime and its adapter require (effective prompt, negative channel, per-variant parameters and seed, and any references the package declares), then send it through the endpoint named by `transport`. The batch plan carries hashes and grouping only; it never carries credentials, builds requests, or substitutes one variant's package for another's. Do not start several catalog CLI processes in parallel; dispatch concurrency is at the model-call layer only.

Where a variant's model record carries an offering, that send is one dispatch per variant, and the same command records it:

```bash
python scripts/dispatch.py <generation-package.json> --studio <dir> --character <id> --slot <slot> [--seed N] --send
```

A model exposed on no service here is sent by hand, and its result is recorded with `python scripts/studio.py iterate` before anything else is done with it. Either way the iteration exists before the batch results are written, because the batch results point at it.

After generation, write one `batch-results.json` mapping every planned variant id to its outcome. Keep it in the studio root, so that every `image_path` is the iteration's own file, `characters/<id>/iterations/<it>/result.png`: a results file may only name paths under its own directory, and the studio root is the one directory that holds every variant's image.

```json
{
  "variants": {
    "closeup-flux#v01": {"image_path": "renders/closeup-flux-v01.png", "status": "accepted"},
    "closeup-flux#v02": {"image_path": "renders/closeup-flux-v02.png", "status": "rejected", "note": "ear drift"},
    "closeup-flux#v03": {"status": "failed", "error": "host returned no image"}
  }
}
```

`status` is `accepted`, `rejected`, `pending`, or `failed`. Every non-failed variant requires an existing nonempty `image_path` relative to the results file, staying inside the results directory; `failed` requires a nonempty `error` and no image. Then record the batch ledger:

```bash
python scripts/build_batch_plan.py record --plan batch-plan.json --results batch-results.json --out batch-ledger.json
```

The record command revalidates every job and variant before accepting results: copied model, transport, package path/hash, parameters, seed, and note must still match the owning job with their original JSON types. It also rejects incomplete results, unknown variant ids, missing or empty image files, and unknown statuses. The batch ledger commits the plan hash and every accepted or rejected image hash, and rolls review counts up per batch and per job. Review stays per image against its own image intent; a batch acceptance is never inherited across variants.

## Failure policy

Stop when any referenced package fails verification, its committed hash no longer matches the file, or a job's target model lacks an enabled record. One failed dispatch does not invalidate the other variants; record it as `failed`, re-dispatch that variant individually, and update the results before recording the batch ledger. Never drop a planned variant silently, never let one model's accepted output replace another job's rejected output, and never widen a batch by reusing one job's package under a different model.


## Artifact evidence and completion

For a saved deliverable, continue through [Production Execution](production-execution.md). Preserve this document's own interpretation, retrieval, approval and adoption boundaries. Prepare the exact inputs, capture the real output, bind review and selection to it, then complete and close the work task. `scripts/production_workflow.py status`, `impact` and `resume` recheck dependencies and artifact bytes. A progress checkbox, a search hit or a newly created image is not production completion or canonical adoption.
