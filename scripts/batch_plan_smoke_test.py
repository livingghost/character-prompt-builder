#!/usr/bin/env python3
"""Exercise batch generation plan construction, rejection paths, and result ledgers."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_batch_plan.py"
EXPECTED_CHECKS = 55


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def expect_error(fn: Callable[[], Any], text: str) -> bool:
    try:
        fn()
    except (ValueError, OSError) as exc:
        return text in str(exc)
    return False


def run_cli(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *argv],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def make_image(path: Path, size: int, value: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes([value]) * size)


def main() -> int:
    passed = 0
    total = 0

    def check(condition: bool, name: str) -> None:
        nonlocal passed, total
        total += 1
        if condition:
            passed += 1
            print(f"ok {total} - {name}")
        else:
            print(f"FAIL {total} - {name}")

    with tempfile.TemporaryDirectory(prefix="cpb-batch-plan-") as temporary:
        workdir = Path(temporary)
        package_a = workdir / "packages" / "closeup-flux.json"
        package_b = workdir / "packages" / "scene-sdxl.json"
        write_json(package_a, {"generation_input_sha256": "a" * 64})
        write_json(package_b, {"generation_input_sha256": "b" * 64})
        package_a_sha = hashlib.sha256(package_a.read_bytes()).hexdigest()
        package_b_sha = hashlib.sha256(package_b.read_bytes()).hexdigest()

        jobs = {
            "label": "portrait closeups",
            "jobs": [
                {
                    "job_id": "closeup-flux",
                    "target_model": "flux-1-dev",
                    "transport": "runware-mcp",
                    "generation_package": "packages/closeup-flux.json",
                    "count": 3,
                    "seeds": [11, 22, 33],
                    "parameters": {"width": 1024, "height": 1024, "nested": {"steps": 28}},
                    "note": "front closeup variants",
                },
                {
                    "job_id": "scene-sdxl",
                    "target_model": "sdxl-base",
                    "transport": "comfyui-local",
                    "generation_package": "packages/scene-sdxl.json",
                },
            ],
        }
        jobs_path = workdir / "batch-jobs.json"
        plan_path = workdir / "batch-plan.json"
        write_json(jobs_path, jobs)
        result = run_cli("plan", "--jobs", str(jobs_path), "--out", str(plan_path))
        check(result.returncode == 0, "plan command succeeds")
        summary = json.loads(result.stdout)
        check(summary["job_count"] == 2, "plan reports both jobs")
        check(summary["variant_count"] == 4, "plan expands count into variants")
        check(
            summary["endpoints"] == ["comfyui-local", "runware-mcp"],
            "plan reports one endpoint group per transport",
        )

        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        check(plan["label"] == "portrait closeups", "plan preserves the batch label")
        check(
            plan["jobs"][0]["generation_package_sha256"] == package_a_sha,
            "plan commits package hash",
        )
        variant_ids = [variant["variant_id"] for variant in plan["variants"]]
        check(
            variant_ids
            == [
                "closeup-flux#v01",
                "closeup-flux#v02",
                "closeup-flux#v03",
                "scene-sdxl#v01",
            ],
            "variant ids are deterministic",
        )
        check(
            [variant["seed"] for variant in plan["variants"]] == [11, 22, 33, None],
            "seeds map per variant and default to null",
        )
        check(
            plan["dispatch"]["endpoint_groups"]
            == [
                {
                    "transport": "comfyui-local",
                    "models": {"sdxl-base": ["scene-sdxl#v01"]},
                },
                {
                    "transport": "runware-mcp",
                    "models": {
                        "flux-1-dev": [
                            "closeup-flux#v01",
                            "closeup-flux#v02",
                            "closeup-flux#v03",
                        ]
                    },
                },
            ],
            "dispatch groups variants by endpoint, then model",
        )
        default_transport_jobs = {
            "jobs": [
                {
                    "job_id": "plain",
                    "target_model": "m",
                    "generation_package": "packages/closeup-flux.json",
                }
            ]
        }
        default_transport_path = workdir / "default-transport-jobs.json"
        write_json(default_transport_path, default_transport_jobs)
        default_plan = _build_plan(default_transport_path, workdir)
        check(
            all(variant["transport"] == "default" for variant in default_plan["variants"]),
            "jobs without a transport share one default endpoint group",
        )

        rejection_cases: list[tuple[dict[str, Any], str, str]] = [
            (
                {"jobs": [{"job_id": "a", "target_model": "m", "generation_package": "packages/closeup-flux.json"}, {"job_id": "a", "target_model": "m", "generation_package": "packages/closeup-flux.json"}]},
                "duplicate",
                "rejects duplicate job ids",
            ),
            (
                {"jobs": [{"job_id": "a", "target_model": "m", "generation_package": "packages/missing.json"}]},
                "existing regular file",
                "rejects a missing generation package",
            ),
            (
                {"jobs": [{"job_id": "a", "target_model": "m", "generation_package": "packages/closeup-flux.json", "count": 2, "seeds": [1]}]},
                "one seed per variant",
                "rejects seed count mismatch",
            ),
            (
                {"jobs": [{"job_id": "a", "target_model": "m", "generation_package": "packages/closeup-flux.json", "count": 0}]},
                "positive integer",
                "rejects a zero variant count",
            ),
            (
                {"jobs": [{"job_id": "a", "target_model": "m", "generation_package": "packages/closeup-flux.json", "parameters": [1]}]},
                "parameters must be a JSON object",
                "rejects non-object parameters",
            ),
            ({"jobs": []}, "nonempty list", "rejects an empty job list"),
        ]
        for invalid, text, name in rejection_cases:
            invalid_path = workdir / "invalid-jobs.json"
            write_json(invalid_path, invalid)
            check(expect_error(lambda p=invalid_path: _build_plan(p, workdir), text), name)

        absolute_jobs = {
            "jobs": [
                {
                    "job_id": "abs",
                    "target_model": "m",
                    "generation_package": str(package_a),
                }
            ]
        }
        absolute_path = workdir / "absolute-jobs.json"
        write_json(absolute_path, absolute_jobs)
        result = run_cli("plan", "--jobs", str(absolute_path), "--out", str(workdir / "unused.json"))
        check(result.returncode == 2 and "relative path" in result.stderr, "rejects absolute package paths")

        escape_jobs = {
            "jobs": [
                {
                    "job_id": "escape",
                    "target_model": "m",
                    "generation_package": "../outside/pkg.json",
                }
            ]
        }
        escape_path = workdir / "escape-jobs.json"
        write_json(escape_path, escape_jobs)
        outside = workdir.parent / f"cpb-outside-{os.getpid()}"
        outside.mkdir(parents=True, exist_ok=True)
        write_json(outside / "pkg.json", {"generation_input_sha256": "c" * 64})
        try:
            check(
                expect_error(lambda: _build_plan(escape_path, workdir), "parent references"),
                "rejects parent-reference generation packages",
            )
        finally:
            shutil.rmtree(outside, ignore_errors=True)

        link_path = workdir / "packages" / "link-flux.json"
        try:
            link_path.symlink_to(package_a)
            link_supported = link_path.is_symlink()
        except OSError:
            link_supported = False
        if link_supported:
            link_jobs = {
                "jobs": [
                    {
                        "job_id": "linked",
                        "target_model": "m",
                        "generation_package": "packages/link-flux.json",
                    }
                ]
            }
            link_jobs_path = workdir / "link-jobs.json"
            write_json(link_jobs_path, link_jobs)
            check(
                expect_error(lambda: _build_plan(link_jobs_path, workdir), "symbolic link"),
                "rejects symlinked generation packages",
            )
        else:
            check(True, "rejects symlinked generation packages (symlinks unavailable; skipped)")

        real_dir = workdir / "real-packages"
        real_dir.mkdir()
        write_json(real_dir / "inner.json", {"generation_input_sha256": "c" * 64})
        alias_dir = workdir / "alias-packages"
        try:
            alias_dir.symlink_to(real_dir, target_is_directory=True)
            alias_supported = alias_dir.is_symlink()
        except OSError:
            alias_supported = False
        if alias_supported:
            alias_jobs = {
                "jobs": [
                    {
                        "job_id": "alias",
                        "target_model": "m",
                        "generation_package": "alias-packages/inner.json",
                    }
                ]
            }
            alias_jobs_path = workdir / "alias-jobs.json"
            write_json(alias_jobs_path, alias_jobs)
            check(
                expect_error(lambda: _build_plan(alias_jobs_path, workdir), "symbolic link"),
                "rejects ancestor-symlinked package directories",
            )
        else:
            check(True, "rejects ancestor-symlinked package directories (symlinks unavailable; skipped)")

        image_one = workdir / "renders" / "closeup-flux-v01.png"
        image_two = workdir / "renders" / "closeup-flux-v02.png"
        image_three = workdir / "renders" / "closeup-flux-v03.png"
        image_scene = workdir / "renders" / "scene-sdxl-v01.png"
        make_image(image_one, 64, 1)
        make_image(image_two, 64, 2)
        make_image(image_three, 64, 3)
        make_image(image_scene, 64, 4)
        results = {
            "variants": {
                "closeup-flux#v01": {"image_path": "renders/closeup-flux-v01.png", "status": "accepted"},
                "closeup-flux#v02": {"image_path": "renders/closeup-flux-v02.png", "status": "rejected", "note": "ear drift"},
                "closeup-flux#v03": {"image_path": "renders/closeup-flux-v03.png", "status": "pending"},
                "scene-sdxl#v01": {"image_path": "renders/scene-sdxl-v01.png", "status": "accepted"},
            }
        }
        results_path = workdir / "batch-results.json"
        ledger_path = workdir / "batch-ledger.json"
        write_json(results_path, results)
        result = run_cli(
            "record",
            "--plan",
            str(plan_path),
            "--results",
            str(results_path),
            "--out",
            str(ledger_path),
        )
        check(result.returncode == 0, "record command succeeds")
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        check(ledger["summary"] == {"variant_count": 4, "accepted": 2, "rejected": 1, "pending": 1, "failed": 0}, "ledger summarizes review statuses")
        check(
            ledger["batch_plan_sha256"] == hashlib.sha256(plan_path.read_bytes()).hexdigest(),
            "ledger commits the plan hash",
        )
        first_variant = ledger["jobs"][0]["variants"][0]
        check(
            first_variant["result"]["image_sha256"] == hashlib.sha256(image_one.read_bytes()).hexdigest(),
            "ledger commits image hashes",
        )

        incomplete = {"variants": {"closeup-flux#v01": results["variants"]["closeup-flux#v01"]}}
        incomplete_path = workdir / "incomplete-results.json"
        write_json(incomplete_path, incomplete)
        result = run_cli("record", "--plan", str(plan_path), "--results", str(incomplete_path), "--out", str(workdir / "unused-ledger.json"))
        check(result.returncode == 2 and "missing variants" in result.stderr, "record rejects incomplete results")

        unknown = {"variants": {**results["variants"], "ghost#v01": {"image_path": "renders/closeup-flux-v01.png", "status": "accepted"}}}
        unknown_path = workdir / "unknown-results.json"
        write_json(unknown_path, unknown)
        result = run_cli("record", "--plan", str(plan_path), "--results", str(unknown_path), "--out", str(workdir / "unused-ledger.json"))
        check(result.returncode == 2 and "unknown variants" in result.stderr, "record rejects unknown variants")

        missing_file = {"variants": {**results["variants"], "scene-sdxl#v01": {"image_path": "renders/nope.png", "status": "accepted"}}}
        missing_path = workdir / "missing-file-results.json"
        write_json(missing_path, missing_file)
        result = run_cli("record", "--plan", str(plan_path), "--results", str(missing_path), "--out", str(workdir / "unused-ledger.json"))
        check(result.returncode == 2 and "existing regular file" in result.stderr, "record rejects missing image files")

        absolute_image = {"variants": {**results["variants"], "scene-sdxl#v01": {"image_path": str(image_scene), "status": "accepted"}}}
        absolute_image_path = workdir / "absolute-image-results.json"
        write_json(absolute_image_path, absolute_image)
        result = run_cli("record", "--plan", str(plan_path), "--results", str(absolute_image_path), "--out", str(workdir / "unused-ledger.json"))
        check(result.returncode == 2 and "relative path" in result.stderr, "record rejects absolute image paths")

        parent_image = {"variants": {**results["variants"], "scene-sdxl#v01": {"image_path": "../elsewhere/image.png", "status": "accepted"}}}
        parent_image_path = workdir / "parent-image-results.json"
        write_json(parent_image_path, parent_image)
        result = run_cli("record", "--plan", str(plan_path), "--results", str(parent_image_path), "--out", str(workdir / "unused-ledger.json"))
        check(result.returncode == 2 and "parent references" in result.stderr, "record rejects parent-reference image paths")

        image_link = workdir / "renders" / "link-scene.png"
        try:
            image_link.symlink_to(image_scene)
            image_link_supported = image_link.is_symlink()
        except OSError:
            image_link_supported = False
        if image_link_supported:
            linked_image = {"variants": {**results["variants"], "scene-sdxl#v01": {"image_path": "renders/link-scene.png", "status": "accepted"}}}
            linked_image_path = workdir / "linked-image-results.json"
            write_json(linked_image_path, linked_image)
            result = run_cli("record", "--plan", str(plan_path), "--results", str(linked_image_path), "--out", str(workdir / "unused-ledger.json"))
            check(result.returncode == 2 and "symbolic link" in result.stderr, "record rejects symlinked image paths")
        else:
            check(True, "record rejects symlinked image paths (symlinks unavailable; skipped)")

        failed = {
            "variants": {
                "closeup-flux#v01": {"image_path": "renders/closeup-flux-v01.png", "status": "accepted"},
                "closeup-flux#v02": {"image_path": "renders/closeup-flux-v02.png", "status": "rejected"},
                "closeup-flux#v03": {"status": "failed", "error": "host returned no image"},
                "scene-sdxl#v01": {"image_path": "renders/scene-sdxl-v01.png", "status": "accepted"},
            }
        }
        failed_path = workdir / "failed-results.json"
        failed_ledger_path = workdir / "failed-ledger.json"
        write_json(failed_path, failed)
        result = run_cli("record", "--plan", str(plan_path), "--results", str(failed_path), "--out", str(failed_ledger_path))
        check(result.returncode == 0, "record accepts failed dispatches with an error")
        failed_ledger = json.loads(failed_ledger_path.read_text(encoding="utf-8"))
        check(failed_ledger["summary"]["failed"] == 1, "ledger counts failed dispatches")

        bad_status = {"variants": {**results["variants"], "closeup-flux#v03": {"image_path": "renders/closeup-flux-v03.png", "status": "maybe"}}}
        bad_status_path = workdir / "bad-status-results.json"
        write_json(bad_status_path, bad_status)
        result = run_cli("record", "--plan", str(plan_path), "--results", str(bad_status_path), "--out", str(workdir / "unused-ledger.json"))
        check(result.returncode == 2 and "status must be one of" in result.stderr, "record rejects unknown statuses")

        tampered_plan = json.loads(plan_path.read_text(encoding="utf-8"))
        tampered_plan["variants"].append(
            {
                "variant_id": "ghost#v01",
                "job_id": "ghost",
                "target_model": "m",
                "transport": "default",
                "generation_package": "packages/closeup-flux.json",
                "generation_package_sha256": package_a_sha,
                "parameters": {},
                "seed": None,
                "note": None,
            }
        )
        tampered_path = workdir / "tampered-plan.json"
        write_json(tampered_path, tampered_plan)
        result = run_cli(
            "record",
            "--plan",
            str(tampered_path),
            "--results",
            str(results_path),
            "--out",
            str(workdir / "unused-ledger.json"),
        )
        check(
            result.returncode == 2 and "unknown job_id" in result.stderr,
            "record rejects plan variants without a matching job",
        )

        jobless_plan = {key: value for key, value in plan.items() if key != "jobs"}
        jobless_path = workdir / "jobless-plan.json"
        write_json(jobless_path, jobless_plan)
        result = run_cli(
            "record",
            "--plan",
            str(jobless_path),
            "--results",
            str(results_path),
            "--out",
            str(workdir / "unused-ledger.json"),
        )
        check(
            result.returncode == 2 and "batch plan has no jobs" in result.stderr,
            "record rejects a plan without jobs",
        )

        malformed_plan = dict(plan)
        malformed_plan["variants"] = [plan["variants"][0]["variant_id"]]
        malformed_path = workdir / "malformed-variants-plan.json"
        write_json(malformed_path, malformed_plan)
        result = run_cli(
            "record",
            "--plan",
            str(malformed_path),
            "--results",
            str(results_path),
            "--out",
            str(workdir / "unused-ledger.json"),
        )
        check(
            result.returncode == 2 and "must be a JSON object" in result.stderr,
            "record rejects a plan whose variants are not objects",
        )

        def tampered_plan_file(name: str, mutate: Callable[[dict[str, Any]], None]) -> Path:
            document = json.loads(plan_path.read_text(encoding="utf-8"))
            mutate(document)
            path = workdir / name
            write_json(path, document)
            return path

        def expect_record_reject(path: Path, text: str, name: str) -> None:
            result = run_cli(
                "record",
                "--plan",
                str(path),
                "--results",
                str(results_path),
                "--out",
                str(workdir / "unused-ledger.json"),
            )
            check(result.returncode == 2 and text in result.stderr, name)

        expect_record_reject(
            tampered_plan_file(
                "duplicate-variant-plan.json",
                lambda d: d["variants"].append(dict(d["variants"][0])),
            ),
            "duplicate variant_id",
            "record rejects duplicate variant ids",
        )
        expect_record_reject(
            tampered_plan_file("no-model-plan.json", lambda d: d["jobs"][0].pop("target_model")),
            "has no target_model",
            "record rejects a job without target_model",
        )
        expect_record_reject(
            tampered_plan_file("blank-id-plan.json", lambda d: d["jobs"][0].__setitem__("job_id", "   ")),
            "has no job_id",
            "record rejects whitespace-only job ids",
        )
        expect_record_reject(
            tampered_plan_file(
                "transport-mismatch-plan.json",
                lambda d: d["variants"][0].__setitem__("transport", "default"),
            ),
            "does not match job",
            "record rejects a variant whose copied field differs from its job",
        )
        expect_record_reject(
            tampered_plan_file(
                "missing-field-plan.json",
                lambda d: d["variants"][0].pop("transport"),
            ),
            "does not match job",
            "record rejects a variant with a missing copied field",
        )
        expect_record_reject(
            tampered_plan_file(
                "bad-hash-plan.json",
                lambda d: d["jobs"][0].__setitem__("generation_package_sha256", "not-a-hash"),
            ),
            "64 hexadecimal characters",
            "record rejects a malformed package hash",
        )
        expect_record_reject(
            tampered_plan_file(
                "variant-parameters-mismatch.json",
                lambda d: d["variants"][0].__setitem__("parameters", {"steps": 1}),
            ),
            "parameters does not match job",
            "record rejects variant parameters that differ from the job",
        )
        expect_record_reject(
            tampered_plan_file(
                "variant-seed-mismatch.json",
                lambda d: d["variants"][0].__setitem__("seed", {"bad": True}),
            ),
            "seed does not match job",
            "record rejects malformed or mismatched variant seeds",
        )
        expect_record_reject(
            tampered_plan_file(
                "variant-note-mismatch.json",
                lambda d: d["variants"][0].__setitem__("note", "different note"),
            ),
            "note does not match job",
            "record rejects variant notes that differ from the job",
        )
        expect_record_reject(
            tampered_plan_file(
                "job-parameters-malformed.json",
                lambda d: d["jobs"][0].__setitem__("parameters", []),
            ),
            "parameters must be a JSON object",
            "record revalidates job parameter types",
        )
        expect_record_reject(
            tampered_plan_file(
                "job-seeds-malformed.json",
                lambda d: d["jobs"][0].__setitem__("seeds", [1]),
            ),
            "one seed per variant",
            "record revalidates job seed cardinality",
        )
        # The ledger side must re-derive the package hash from the file on
        # disk: results recorded against a swapped or deleted package would
        # otherwise commit to a provenance hash matching nothing that exists.
        package_backup = package_a.read_bytes()
        try:
            write_json(package_a, {"generation_input_sha256": "f" * 64})
            expect_record_reject(
                tampered_plan_file(
                    "intact-hash-swapped-package.json", lambda d: None
                ),
                "no longer matches its recorded generation_package_sha256",
                "record rejects a package whose content no longer matches its hash",
            )
            package_a.unlink()
            expect_record_reject(
                tampered_plan_file(
                    "intact-hash-deleted-package.json", lambda d: None
                ),
                "missing",
                "record rejects a deleted generation package",
            )
        finally:
            package_a.write_bytes(package_backup)
        # The dispatch block is generated alongside the variants; a hand edit
        # that changes either side without regenerating the other must be
        # caught before results are recorded.
        expect_record_reject(
            tampered_plan_file(
                "dispatch-count-plan.json",
                lambda d: d["dispatch"].__setitem__("variant_count", 1),
            ),
            "does not match the plan variants",
            "record rejects a dispatch count that disagrees with the plan variants",
        )
        expect_record_reject(
            tampered_plan_file(
                "dispatch-group-plan.json",
                lambda d: d["dispatch"].__setitem__(
                    "endpoint_groups", d["dispatch"]["endpoint_groups"][:1]
                ),
            ),
            "must cover exactly the transports",
            "record rejects a dispatch block missing a transport group",
        )

        def reassign_variant(document: dict[str, Any]) -> None:
            # Move closeup-flux#v01 under scene-sdxl with scene-sdxl's copied
            # metadata. Every copied field reconciles, so only the variant
            # ownership rule can catch the reassignment.
            variant = document["variants"][0]
            target = document["jobs"][1]
            variant["job_id"] = target["job_id"]
            variant["target_model"] = target["target_model"]
            variant["transport"] = target["transport"]
            variant["generation_package"] = target["generation_package"]
            variant["generation_package_sha256"] = target["generation_package_sha256"]
            variant["parameters"] = copy.deepcopy(target["parameters"])
            variant["note"] = target["note"]
            variant["seed"] = target["seeds"][0] if target["seeds"] is not None else None

        expect_record_reject(
            tampered_plan_file("reassign-plan.json", reassign_variant),
            "must own exactly its expanded variants",
            "record rejects a variant reassigned across jobs",
        )

        # The placement the runtime document asks for: the batch artifacts in the
        # studio root, and every image_path the iteration's own result file, which
        # the dispatcher wrote. A results file may only name paths under its own
        # directory, so the studio root is the one place this works from.
        studio_root = workdir / "studio"
        write_json(studio_root / "packages" / "studio-job.json", {"generation_input_sha256": "c" * 64})
        make_image(studio_root / "characters" / "C01" / "iterations" / "it-0001" / "result.png", 64, 5)
        studio_jobs = studio_root / "batch-jobs.json"
        write_json(studio_jobs, {
            "label": "studio batch",
            "jobs": [{
                "job_id": "studio-job",
                "target_model": "flux-1-dev",
                "transport": "runware-mcp",
                "generation_package": "packages/studio-job.json",
            }],
        })
        studio_plan = studio_root / "batch-plan.json"
        studio_results = studio_root / "batch-results.json"
        studio_ledger = studio_root / "batch-ledger.json"
        planned = run_cli("plan", "--jobs", str(studio_jobs), "--out", str(studio_plan))
        write_json(studio_results, {
            "variants": {
                "studio-job#v01": {
                    "image_path": "characters/C01/iterations/it-0001/result.png",
                    "status": "accepted",
                }
            }
        })
        recorded = run_cli("record", "--plan", str(studio_plan), "--results", str(studio_results), "--out", str(studio_ledger))
        check(
            planned.returncode == 0
            and recorded.returncode == 0
            and json.loads(studio_ledger.read_text(encoding="utf-8"))["summary"]["accepted"] == 1,
            "a batch in a studio root records results that point at the recorded iterations",
        )

        expanded_plan = _build_plan(jobs_path, workdir)
        first_parameters = expanded_plan["variants"][0]["parameters"]
        second_parameters = expanded_plan["variants"][1]["parameters"]
        check(
            first_parameters is not second_parameters
            and first_parameters["nested"] is not second_parameters["nested"],
            "variant parameters are independent deep copies",
        )

    check(total + 1 == EXPECTED_CHECKS, f"expected check count ({EXPECTED_CHECKS})")

    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


def _build_plan(jobs_path: Path, root: Path) -> dict[str, Any]:
    import importlib.util

    spec = importlib.util.spec_from_file_location("build_batch_plan_module", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.build_batch_plan(
        json.loads(jobs_path.read_text(encoding="utf-8")), root
    )


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
