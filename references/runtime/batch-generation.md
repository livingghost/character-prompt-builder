# Batch Generation Runtime

Use this document only when the user requests several images at once: several variants of one model dispatched concurrently, or several models dispatched through their endpoints at the same time. Complete [Image Generation Runtime](image-generation.md) first; a batch changes how verified generation inputs are dispatched and reviewed, never how any single image is directed, packaged, or forwarded.

## Contents

- [Batch scope and authority](#batch-scope-and-authority)
- [Managed child runs](#managed-child-runs)
- [Authoring the job list](#authoring-the-job-list)
- [Building the plan](#building-the-plan)
- [Dispatch and results](#dispatch-and-results)
- [Failure policy](#failure-policy)

## Batch scope and authority

A batch is a dispatch and review layer over verified Generation Packages. It does not merge prompts, share one image intent across jobs, or let one model's output stand in for another's. Each job keeps its own image intent, adapter, negative transport, and reference set exactly as the Image Generation Runtime requires.

Keep judgment and automation separate. The agent owns meaning, per-job direction, model selection, review, and acceptance. The batch owner derives grouping and results from selected managed runs. An externally assembled job list uses deterministic validation, variant expansion and evidence recording. The batch never decides what an image should look like.

Every result is recorded where a single image would be recorded, as its own
iteration in the studio with the record it came from, that record's family, the
request as sent, and the answer. `production_workflow.py execute` writes that
record itself. A managed batch selects these child runs and projects their
verified publications, candidates and existing evaluations. Do not retype their
model, transport, image path or result status into a separate results document.

A job's model decides how its prompt is written. Models do not read a prompt the same way: a rating term one family carries is unknown to the next, the quality block differs, multi-word tags are spelled differently, the working weight differs, and the blocks and their order differ. Resolve each job's family with `python scripts/prompt_dialect.py --model <model-id>` and compose that job from what comes back. Never carry one job's quality block, rating term, period term, or weight into a job on another model, and never reuse one job's rendition for a different model by changing only the model name.

Every job forwards its own verified Generation Package. A batch plan is usable only when every referenced package already passed `verify_generation_payload.py` for its target model. The plan commits each package's SHA-256 so a package edited after planning is detectable; if any committed hash differs from the file, rebuild the plan before dispatching.

## Managed child runs

Prepare each intended input through its normal owner. `variant` derives a child
with authored changes; `repeat` makes another execution of the same input. Their
authorizations, captures, reviews and selections remain independent:

```bash
python scripts/production_workflow.py prepare --root STUDIO --task task.json
python scripts/production_workflow.py variant --root STUDIO --from RUN --changes-file changes.json --prepare
python scripts/production_workflow.py repeat --root STUDIO --from RUN --prepare
python scripts/production_workflow.py draft-execution --root STUDIO --run CHILD_RUN --grant GRANT --out decisions.json
python scripts/production_workflow.py execute --root STUDIO --run CHILD_RUN --decisions-file decisions.json
```

Select the child runs to include, before or after execution:

```bash
python scripts/build_batch_plan.py project --root STUDIO \
  --run FIRST_RUN --run SECOND_RUN --label "Selected variants" --out batch-report.json
```

The report obtains the exact model, service, transport, package/request
commitments and planned output count from each child's stored preparation. It
groups the selected children by their actual execution configuration. Its
results come from the same verified history used by ordinary Production:

- submission and execution accounting describe actual external effects;
- capture describes retained output bytes and includes every candidate;
- each candidate keeps its actual evaluation and disposition, with whether a
  selection is still current;
- canonical adoption appears only when its own operation has a recorded result.

An acknowledged execution with a captured image remains unreviewed until an
actual review exists. A conforming image need not be selected, and a selected
image need not be canonically adopted. Unknown send outcomes and unstarted runs
remain visible beside completed children. No result from one child fills
another's missing output.

`batch-report.json` is a replaceable projection with each observed event tail,
not an approval, dispatch permission or second evidence store. Rerun `project`
after actual child operations change their records. It does not send requests,
perform image review or change selection. The same path works for registered
external executions after their real handoff and captures are recorded.

## Authoring the job list

Use this path for externally assembled jobs whose own managed child runs are
not available. Retain the actual request and received-output evidence in the
normal external execution/import owner; a batch declaration cannot establish
that an execution occurred. Write one `batch-jobs.json` UTF-8 artifact.
This synthetic example illustrates two models using separate endpoints:

```json
{
  "label": "portrait closeups",
  "jobs": [
    {
      "job_id": "closeup-sample",
      "target_model": "sample-image-a",
      "transport": "synthetic-host-b",
      "generation_package": "packages/closeup-sample.json",
      "count": 3,
      "seeds": [11, 22, 33],
      "parameters": {"width": 1024, "height": 1024},
      "note": "front closeup variants"
    },
    {
      "job_id": "scene-sample",
      "target_model": "sample-image-b",
      "transport": "synthetic-host-a",
      "generation_package": "packages/scene-sample.json"
    }
  ]
}
```

Each job requires a unique nonempty `job_id`, a nonempty `target_model` naming the model its Generation Package was built for, and a `generation_package` relative to the jobs file. The batch layer records that name; the model record itself was already resolved against the enabled packs when the Generation Package was built, and the adapter resolves it again at dispatch. Optional `count` (default 1) expands one job into that many concurrent variants of the same model; optional `seeds` must supply exactly one nonnegative integer per variant; optional `parameters` and `note` copy onto every variant of the job. Package paths, image paths, and result paths are relative, must stay inside the directory of their referencing file, and may not be symbolic links; absolute paths and parent references such as `../` are rejected.

`transport` names the endpoint a job's variants are sent through: one host interface with one configuration, such as a hosted inference API, a local UI, or a tool connection. Jobs that will be dispatched through the same configured endpoint share one `transport` value; jobs that need a different endpoint configuration use a different value. Omitted `transport` defaults to `default`. Group by the actual endpoint configuration, not by a presumed relationship between a model name and provider.

## Building the plan

```bash
python scripts/build_batch_plan.py plan --jobs batch-jobs.json --out batch-plan.json
```

The command rejects duplicate job ids, missing packages, seed-count mismatches, nonpositive variant counts, and non-object parameters. It expands every job into deterministic variants (`<job_id>#v01`, `#v02`, ...), commits each package hash, and writes a dispatch summary grouped by `transport`, then by model. The plan output reports job count, variant count, and the sorted endpoint groups on stdout.

## Dispatch and results

For each selected endpoint configuration, use its supported dispatch behavior.
Independent requests may overlap within or across endpoints, subject to their
own authorization and limits. Keep every request bound to the exact input and
configured endpoint that owns it; grouping never merges unrelated requests.

How each variant reaches its model is unchanged: form the request from that variant's verified Generation Package exactly as the Image Generation Runtime and its adapter require (effective prompt, negative channel, per-variant parameters and seed, and any references the package declares), then send it through the endpoint named by `transport`. The batch plan carries hashes and grouping only; it never carries credentials, builds requests, or substitutes one variant's package for another's. Do not start several catalog CLI processes in parallel; dispatch concurrency is at the model-call layer only.

For an external execution with no managed child run, record the actual imported
result with `studio.py iterate` and retain its request provenance. Map each
planned external variant in `batch-results.json` to that real result and its
actual review decision. Keep the file in the studio root, so every `image_path`
is the iteration's own file, `characters/<id>/iterations/<it>/result.png`: a
results file may only name paths under its own directory. Managed runs use
`project` above and require no such mapping.

```json
{
  "variants": {
    "closeup-sample#v01": {"image_path": "characters/C01/iterations/it-0004/result.png", "status": "accepted"},
    "closeup-sample#v02": {"image_path": "characters/C01/iterations/it-0005/result.png", "status": "rejected", "note": "ear drift"},
    "closeup-sample#v03": {"status": "failed", "error": "host returned no image"}
  }
}
```

`status` is `accepted`, `rejected`, `pending`, or `failed`. Every non-failed variant requires an existing nonempty `image_path` relative to the results file, staying inside the results directory; `failed` requires a nonempty `error` and no image. Then record the batch ledger:

```bash
python scripts/build_batch_plan.py record --plan batch-plan.json --results batch-results.json --out batch-ledger.json
```

The record command revalidates every job and variant before accepting results: copied model, transport, package path/hash, parameters, seed, and note must still match the owning job with their original JSON types. It also rejects incomplete results, unknown variant ids, missing or empty image files, and unknown statuses. The batch ledger commits the plan hash and every accepted or rejected image hash, and rolls review counts up per batch and per job. Review stays per image against its own image intent; a batch acceptance is never inherited across variants.

## Failure policy

Stop when any referenced package fails verification, its committed hash differs from the file, or a job's target model lacks an enabled record. One failed send does not invalidate the other variants. Recover a managed execution with `resume`, or prepare a `repeat` run for an intentional new execution, then regenerate its batch projection. For external evidence, record an actual failure as `failed` and update results before recording its ledger. Never drop a planned variant silently, never let one model's accepted output replace another job's rejected output, and never widen a batch by reusing one job's package under a different model.


## Artifact evidence and completion

Complete the operation actually commissioned under [Production workflow](production-workflow.md), preserving this document's interpretation, retrieval, authority and adoption boundaries. An authored plan, prompt or design uses [Authored storage](production-authored-storage.md): save its exact revision and perform delivery or review when requested. Model execution instead prepares its exact input, captures the actual result and binds review and selection to that result. Canonical adoption records its own decision and destination.

`production_workflow.py status`, `impact` and `resume` expose current dependencies, artifact integrity and the next action. Close the owning work task when its requested result is complete. A search hit, saved revision, generated image and adoption each establish their own scope.
