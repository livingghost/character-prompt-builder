#!/usr/bin/env python3
"""Exercise a studio end to end on a temporary directory: init, a character, iterations, acceptance, the recipe, the work trail, validation."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import studio  # noqa: E402
import validate_studio  # noqa: E402
import work_ledger  # noqa: E402
from build_generation_payload import validate_generation_package_carrier_paths  # noqa: E402

EXPECTED_CHECKS = 46


def refused(fn, text: str) -> bool:
    try:
        fn()
    except ValueError as exc:
        return text in str(exc)
    return False


def main() -> int:
    results: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: Any = None) -> None:
        results.append({"name": name, "passed": bool(passed), "detail": detail})

    with tempfile.TemporaryDirectory() as tmp:
        root = studio.init(Path(tmp) / "studio", "smoke-studio", "Smoke studio")
        check("init writes the manifest and every directory", all((root / name).is_dir() for name in studio.DIRECTORIES) and (root / studio.MANIFEST).is_file())
        check("init refuses a non-empty directory", refused(lambda: studio.init(root, "again", "Again"), "not empty"))
        check("a fresh studio validates", validate_studio.validate(root) == [], validate_studio.validate(root))
        check("the studio is found from a directory inside it", studio.studio_root(root / "packages") == root)

        # The work trail.
        task = work_ledger.begin(root, "C01 base front", ["generate candidates", "present and record the choice", "accept one"])
        check("a task opens with its first step next", task["next"] == "generate candidates" and uuid.UUID(task["task_id"]).version == 7)
        check("a second task cannot open while one is open", refused(lambda: work_ledger.begin(root, "other", ["x"]), "already open"))
        check("finishing with steps left is refused", refused(lambda: work_ledger.finish(root), "not done"))
        work_ledger.step_done(root, 1, "it-0001 to it-0003")
        shown = work_ledger.show(root)
        check("show names the next step after one is done", "next: present and record the choice" in shown and "[done] 1." in shown, shown)
        work_ledger.block(root, "which of the three")
        check("a blocked task shows what it waits on", "blocked on: which of the three" in work_ledger.show(root))
        check("a step cannot be done twice", refused(lambda: work_ledger.step_done(root, 1), "already done"))
        check("the trail validates while a task is open", work_ledger.check(root) == [], work_ledger.check(root))

        # Another process reads the same state: what a session that lost its context sees.
        printed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "studio.py"), "--studio", str(root), "status"],
            capture_output=True, text=True, encoding="utf-8", check=False,
        )
        check("a fresh process prints the open task and its next step", printed.returncode == 0 and f"open task {task["task_id"]}" in printed.stdout and "blocked on: which of the three" in printed.stdout, printed.stdout[-400:])

        # A character and its iterations.
        home = studio.add_character(root, "C01", "")
        check("a character gets its directories and a blank sheet", (home / "sheet" / "sheet-data.json").is_file() and (home / "iterations.jsonl").is_file())
        check("a character id cannot be added twice", refused(lambda: studio.add_character(root, "C01", ""), "already exists"))
        source = Path(tmp) / "inputs"
        source.mkdir()
        (source / "a.png").write_bytes(b"\x89PNG-a")
        (source / "b.png").write_bytes(b"\x89PNG-b")
        (source / "c.png").write_bytes(b"\x89PNG-c")
        (source / "request.json").write_text(json.dumps({"model": "vendor:model@1", "positivePrompt": "a wolf", "width": 1024, "height": 1024, "seed": 7, "taskUUID": "x"}), encoding="utf-8")
        (source / "response.json").write_text(json.dumps({"seed": 7, "imageURL": "https://example.invalid/a.png"}), encoding="utf-8")
        (source / "package.json").write_text(json.dumps({"generation_input_sha256": "0" * 64, "generation_payload": {"service": {"id": "svc", "model_identifier": "vendor:model@1", "observed_at": "2026-09-13", "schema_snapshot": None}}}), encoding="utf-8")
        first = studio.iterate(root, "C01", "base.front", source / "a.png", package=source / "package.json", request=source / "request.json", response=source / "response.json", note="first")
        check("an iteration records the seed and service from what produced it", first["seed"] == 7 and (first.get("service") or {}).get("id") == "svc" and first["iteration_id"] == "it-0001", first)
        check("an iteration keeps hashed copies of its files", all(first[name] and (root / first[name]["path"]).is_file() for name in ("result", "package", "request", "response")))
        second = studio.iterate(root, "C01", "base.front", source / "b.png", package=None, request=source / "request.json", response=None, note="second")
        third = studio.iterate(root, "C01", "base.front", source / "c.png", package=None, request=None, response=None, note="third")
        check("an iteration without a package still records the model from the request", (second.get("service") or {}).get("model_identifier") == "vendor:model@1")
        check("a slot name is checked", refused(lambda: studio.iterate(root, "C01", "Base Front", source / "a.png", package=None, request=None, response=None, note=None), "slot must be"))

        accepted = studio.accept(root, "C01", "it-0001")
        check("accepting copies the image under accepted/", (root / accepted["accepted_path"]).read_bytes() == b"\x89PNG-a")
        again = studio.accept(root, "C01", "it-0002")
        rows = studio.read_iterations(home)
        check("accepting another iteration supersedes the previous one", rows[0]["status"] == "superseded" and rows[0]["superseded_by"] == "it-0002" and again["supersedes"] == "it-0001")
        check("the accepted copy follows the newly accepted iteration", (root / again["accepted_path"]).read_bytes() == b"\x89PNG-b" and len(list((home / "accepted").glob("base.front.*"))) == 1)
        check("an accepted iteration cannot be rejected", refused(lambda: studio.reject(root, "C01", "it-0002", "no"), "is accepted"))
        rejected = studio.reject(root, "C01", "it-0003", "jaw too narrow")
        check("a rejected iteration keeps its reason", rejected["status"] == "rejected" and rejected["reason"] == "jaw too narrow")
        check("a rejected iteration cannot be accepted", refused(lambda: studio.accept(root, "C01", "it-0003"), "was rejected"))
        recipe = studio.recipe(root, "C01", "base.front")
        check("the recipe is the accepted request without what names a run", recipe["iteration_id"] == "it-0002" and recipe["settings"] == {"model": "vendor:model@1", "positivePrompt": "a wolf", "width": 1024, "height": 1024} and recipe["seed"] == 7, recipe)
        check("a slot with nothing accepted has no recipe", refused(lambda: studio.recipe(root, "C01", "outfit.back"), "no accepted iteration"))
        report = studio.status(root)
        check("status names the accepted slot and the open task", "accepted base.front: it-0002" in report and f"open task {task["task_id"]}" in report, report)

        check("the gallery exists from init and is current after every recording command, unasked", studio.gallery_stale(root) is None and (root / "gallery.html").is_file(), studio.gallery_stale(root))
        (root / "gallery.json").write_text('{"entries": []}', encoding="utf-8")
        check("a gallery that does not match the records is reported", any("gallery" in e for e in validate_studio.validate(root)), validate_studio.validate(root))
        html_path, json_path = studio.write_gallery(root)
        index = json.loads(json_path.read_text(encoding="utf-8"))
        check(
            "the gallery index lists every iteration oldest first with prompt, model, settings, and seed",
            [e["iteration_id"] for e in index["entries"]] == ["it-0001", "it-0002", "it-0003"]
            and index["entries"][0]["prompt"] == "a wolf"
            and index["entries"][0]["settings"] == {"width": 1024, "height": 1024, "seed": 7}
            and index["entries"][0]["service"]["model_identifier"] == "vendor:model@1"
            and index["entries"][0]["seed"] == 7,
            index["entries"][0],
        )
        page = html_path.read_text(encoding="utf-8")
        check(
            "the gallery page shows each image with its prompt and marks the accepted one",
            'src="characters/C01/iterations/it-0002/result.png"' in page and "a wolf" in page and 'class="iteration accepted"' in page and "it-0003" in page,
        )

        check("the studio validates with iterations recorded", validate_studio.validate(root) == [], validate_studio.validate(root))
        (root / first["result"]["path"]).write_bytes(b"changed")
        check("a result whose bytes moved is reported", any("no longer matches" in error for error in validate_studio.validate(root)), validate_studio.validate(root))
        (root / first["result"]["path"]).write_bytes(b"\x89PNG-a")

        work_ledger.step_done(root, 2)
        work_ledger.step_done(root, 3)
        # This test's explicit synthetic review binds the delivered real fixture
        # bytes. Studio acceptance above remains a separate operation.
        import execution_contract as evidence
        import production_workflow as production
        import production_fixtures
        (root / "delivery.txt").write_text("Deliver the selected test image.\n", encoding="utf-8")
        spec = {"task_id": task["task_id"], "route": "development", "features": [],
                "sources": [], "world_views": [],
                "delivery": {"path": "delivery.txt", "transport": "authored-rendition", "translation_notes": "Synthetic offline fixture."},
                "criteria": [{"id": "fixture", "strength": "hard", "text": "Deliver the inspected image fixture."}]}
        production_fixtures.task(root,spec,artifact="binary")
        (root / "production-task.json").write_bytes(evidence.encoded(spec))
        run = production.prepare(root, "production-task.json")["run"]
        production_fixtures.handoff(root, run, "offline fixture", "manual")
        candidate = production.capture(root, run, again["accepted_path"], "Synthetic image bytes, not generated media.")
        review = production.draft_review(root, run, candidate["sha256"])
        review.update(reviewer="synthetic fixture reviewer", observations=[{"locator": {"kind": "whole"}, "observation": "Fixture bytes match the test result."}], conclusion="Synthetic test only.")
        review["checks"][0].update(verdict="pass", observation_indices=[0], reason="Synthetic inspection.")
        production_fixtures.observation(review)
        (root / "production-review.json").write_bytes(evidence.encoded(review))
        production.review(root, run, "production-review.json")
        selection = production.draft_selection(root, run, candidate["sha256"])
        selection.update(selector="synthetic fixture selector", reason="Deliver the reviewed test result.")
        production_fixtures.selection(root,run,selection)
        (root / "production-selection.json").write_bytes(evidence.encoded(selection))
        production.select(root, run, "production-selection.json")
        production.complete(root, run)
        work_ledger.finish(root)
        check("a finished task leaves no open task and stays in the ledger", work_ledger.read_current(root) is None and any(e["event"] == "finished" for e in work_ledger.read_ledger(root)))
        check("show reports the trail when nothing is open", "no task is open; the last recorded" in work_ledger.show(root))
        work_ledger.begin(root, "C02 base front", ["one"])
        work_ledger.abandon(root, "the owner changed the brief")
        check("an abandoned task records what was left", any(e["event"] == "abandoned" and e.get("left") == ["one"] for e in work_ledger.read_ledger(root)))
        check("the trail validates after finishing and abandoning", work_ledger.check(root) == [], work_ledger.check(root))

        # Two recorders at once: a studio is a directory, and two processes that
        # read the record, copy files into it and write it back lose one another's
        # rows unless the recording is serialized.
        busy = studio.init(Path(tmp) / "busy", "busy-studio", "Busy studio")
        studio.add_character(busy, "C02", "")
        driver = Path(tmp) / "record_many.py"
        driver.write_text(
            "import sys\n"
            f"sys.path.insert(0, {str(ROOT / 'scripts')!r})\n"
            "from pathlib import Path\n"
            "import studio\n"
            "root, tag, image = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])\n"
            "for number in range(8):\n"
            "    studio.iterate(root, 'C02', 'base', image, package=None, request=None,\n"
            "                   response=None, note=f'{tag}-{number}')\n",
            encoding="utf-8", newline="\n",
        )
        recorders = [
            subprocess.Popen([sys.executable, str(driver), str(busy), tag, str(source / "a.png")],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
            for tag in ("a", "b")
        ]
        outcomes = [(process.wait(timeout=300), process.communicate()[1]) for process in recorders]
        busy_home = busy / "characters" / "C02"
        busy_rows = studio.read_iterations(busy_home)
        busy_ids = [row.get("iteration_id") for row in busy_rows]
        busy_directories = sorted(path.name for path in (busy_home / "iterations").iterdir() if path.is_dir())
        check(
            "two processes recording at once keep every iteration, each with its own id",
            all(code == 0 for code, _ in outcomes)
            and len(busy_rows) == 16
            and len(set(busy_ids)) == 16
            and len(busy_directories) == 16
            and sorted(row.get("note") for row in busy_rows) == sorted(f"{tag}-{number}" for tag in ("a", "b") for number in range(8))
            and validate_studio.validate(busy) == [],
            {"exit": [code for code, _ in outcomes], "stderr": [text[-200:] for _, text in outcomes],
             "rows": len(busy_rows), "ids": len(set(busy_ids)), "directories": len(busy_directories),
             "errors": validate_studio.validate(busy)},
        )
        spare = Path(tmp) / "spare"
        (spare / "iterations" / "it-0003").mkdir(parents=True)
        check("an id is never reused, even where the row that held it is gone", studio.next_iteration_id(spare, []) == "it-0004", studio.next_iteration_id(spare, []))

        # One slot name is the prefix of another: accepting the shorter one must
        # not take the longer one's accepted copy with it.
        prefixes = studio.init(Path(tmp) / "prefixes", "prefix-studio", "Prefix studio")
        studio.add_character(prefixes, "C03", "")
        prefix_home = prefixes / "characters" / "C03"
        long_slot = studio.iterate(prefixes, "C03", "base.front", source / "a.png", package=None, request=None, response=None, note="long")
        short_slot = studio.iterate(prefixes, "C03", "base", source / "b.png", package=None, request=None, response=None, note="short")
        long_accepted = studio.accept(prefixes, "C03", long_slot["iteration_id"])
        short_accepted = studio.accept(prefixes, "C03", short_slot["iteration_id"])
        check(
            "accepting a slot leaves the accepted copy of a slot it is a prefix of alone",
            (prefix_home / "accepted" / "base.front.png").is_file()
            and (prefix_home / "accepted" / "base.png").is_file()
            and (prefixes / long_accepted["accepted_path"]).is_file()
            and (prefixes / short_accepted["accepted_path"]).is_file(),
            sorted(path.name for path in (prefix_home / "accepted").iterdir()),
        )
        # The seed of the image, not the seed that was asked for: one request that
        # returns several images answers with a different seed for each.
        (source / "asked.json").write_text(json.dumps({"model": "vendor:m@1", "seed": 7, "numberResults": 2}), encoding="utf-8")
        (source / "answered.json").write_text(json.dumps({"seed": 4242424242}), encoding="utf-8")
        (source / "answered-none.json").write_text(json.dumps({"seed": None}), encoding="utf-8")
        answered = studio.iterate(prefixes, "C03", "seeded", source / "a.png", package=None, request=source / "asked.json",
                                  response=source / "answered.json", note="answered")
        check("the seed recorded is the one the service answered with",
              answered["seed"] == 4242424242 and (answered.get("service") or {}).get("model_identifier") == "vendor:m@1", answered)
        blank = studio.iterate(prefixes, "C03", "seeded", source / "b.png", package=None, request=source / "asked.json",
                               response=source / "answered-none.json", note="answered with none")
        check("a service that answers with no seed leaves the requested one standing", blank["seed"] == 7, blank)
        unanswered = studio.iterate(prefixes, "C03", "seeded", source / "c.png", package=None, request=source / "asked.json",
                                    response=None, note="recorded by hand")
        check("an iteration with no response keeps the seed of the request", unanswered["seed"] == 7, unanswered)

        replacement = studio.iterate(prefixes, "C03", "base.front", source / "c.png", package=None, request=None, response=None, note="long again")
        studio.accept(prefixes, "C03", replacement["iteration_id"])
        superseded = next(row for row in studio.read_iterations(prefix_home) if row["iteration_id"] == long_slot["iteration_id"])
        check(
            "a superseded row keeps no accepted copy, and the neighbouring slot is untouched",
            superseded["status"] == "superseded"
            and superseded["accepted_path"] is None
            and (prefix_home / "accepted" / "base.png").read_bytes() == b"\x89PNG-b"
            and validate_studio.validate(prefixes) == [],
            validate_studio.validate(prefixes),
        )

        # The carriers a package names live in a companion beside it, so the copy
        # an iteration keeps is a readable package only with the companion along.
        carriers = Path(tmp) / "carrier"
        companion = carriers / "demo-package.references"
        companion.mkdir(parents=True)
        (companion / "ref-0.png").write_bytes(b"\x89PNG-ref")
        reference_set = {"selected_references": [{"transport": {"resolved_path": "demo-package.references/ref-0.png"}}]}
        (carriers / "demo-package.json").write_text(json.dumps({"prepared_reference_set": reference_set}), encoding="utf-8")
        carried = studio.iterate(prefixes, "C03", "carried", source / "a.png", package=carriers / "demo-package.json",
                                 request=None, response=None, note="with its companion", package_companion=companion)
        carried_home = prefix_home / "iterations" / carried["iteration_id"]
        check(
            "an iteration keeps the package's .references companion beside the package it copied",
            (carried_home / "package.json").is_file()
            and (carried_home / "demo-package.references" / "ref-0.png").is_file()
            and validate_generation_package_carrier_paths(reference_set, package_root=carried_home) == "demo-package.references",
            sorted(path.name for path in carried_home.iterdir()),
        )
        alone = studio.iterate(prefixes, "C03", "carried", source / "b.png", package=carriers / "demo-package.json",
                               request=None, response=None, note="without its companion")
        alone_home = prefix_home / "iterations" / alone["iteration_id"]
        try:
            validate_generation_package_carrier_paths(reference_set, package_root=alone_home)
            unresolved = False
        except (ValueError, OSError):
            unresolved = True
        check("an iteration that kept no companion cannot resolve the carriers its package names", unresolved)

    passed = sum(1 for row in results if row["passed"])
    report = {
        "ok": len(results) == EXPECTED_CHECKS and passed == len(results),
        "checks": len(results),
        "expected_checks": EXPECTED_CHECKS,
        "passed": passed,
        "failures": [row for row in results if not row["passed"]],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
