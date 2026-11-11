#!/usr/bin/env python3
"""Exercise a studio end to end on a temporary directory: init, a character, iterations, acceptance, the recipe, the work trail, validation."""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


import execution_contract  # noqa: E402
import studio  # noqa: E402
import studio_gallery  # noqa: E402
import validate_studio  # noqa: E402
import work_ledger  # noqa: E402
from build_generation_payload import validate_generation_package_carrier_paths  # noqa: E402

EXPECTED_CHECKS = 100


def gallery_details(root: Path) -> str:
    """Read every independently linked detail for assertions on recorded content."""
    index = json.loads((root / "gallery.json").read_text(encoding="utf-8"))
    return "\n".join(studio_gallery.detail_file(root / "gallery.html", entry["entry_id"]).read_text(encoding="utf-8")
                     for entry in index["entries"])


def refused(fn, text: str) -> bool:
    try:
        fn()
    except ValueError as exc:
        return text in str(exc)
    return False


def layout(prompt: list[Any] | None, negative: list[Any] | None = None, *, model: list[Any] | None = None,
           operation: list[Any] | None = None, management: list[list[Any]] | None = None,
           media: list[list[Any]] = (), seed: list[Any] | None = None) -> dict[str, Any]:
    """A request layout of the shape a transport records with its request."""
    content = ([{"id": "prompt", "field": prompt}] if prompt else []) + ([{"id": "negative", "field": negative}] if negative else [])
    return {"model": model or ["model"], "operation": operation or ["taskType"], "primary_text": prompt,
            "negative_text": negative, "output_count": None, "fixed_output_count": 1, "seed": seed,
            "media": [{"index": index, "field": field} for index, field in enumerate(media)],
            "management": management if management is not None else [["taskUUID"]], "content": content,
            "fields": [{"id": item["id"], "field": item["field"], "kind": "content"} for item in content]}


def cli(*argv: str) -> tuple[int, str, str]:
    """Run the studio command line in this process; its exit code, output and error output."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = studio.main(list(argv))
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def completes_while_owner_is_locked(owner: Path, action) -> bool:
    """An unrelated operation finishes before the mutable owner is released."""
    held, release = threading.Event(), threading.Event()
    finished = threading.Event()
    failures: list[BaseException] = []

    def holder() -> None:
        with execution_contract.lock(owner):
            held.set()
            release.wait(60)

    def writer() -> None:
        try:
            action()
        except BaseException as exc:  # noqa: BLE001 - reported through the check
            failures.append(exc)
        finally:
            finished.set()

    holding = threading.Thread(target=holder)
    holding.start()
    ready = held.wait(10)
    writing = threading.Thread(target=writer)
    try:
        writing.start()
        completed = finished.wait(10)
    finally:
        release.set()
        holding.join(10)
        writing.join(10)
    return ready and completed and not failures and not writing.is_alive()


def failure(fn) -> str:
    """The message a call fails with, or an empty string when it succeeds."""
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 - the message is what is checked
        return f"{type(exc).__name__}: {exc}"
    return ""


def render_preferences(tmp: Path, source: Path, check) -> None:
    """Keep unselected treatment and authored project preferences distinct."""
    open_root = tmp / "open-rendering"
    code, _, error = cli("init", "--out", str(open_root), "--studio-id", "open-rendering", "--title", "Open rendering")
    open_manifest = studio.manifest(open_root)
    check("CLI initialization leaves rendering unselected",
          code == 0 and open_manifest["default_render_profile"] is None
          and open_manifest["default_style_family"] is None and validate_studio.validate(open_root) == [], error)

    selected = tmp / "selected-rendering"
    profile = "profile-clear-2d-illustration"
    family = "style-family-clear-portrait"
    code, _, error = cli("init", "--out", str(selected), "--studio-id", "selected-rendering", "--title", "Selected rendering",
                         "--default-render-profile", profile, "--default-style-family", family)
    check("CLI initialization preserves selected project rendering preferences",
          code == 0 and studio.manifest(selected)["default_render_profile"] == profile
          and studio.manifest(selected)["default_style_family"] == family
          and validate_studio.validate(selected) == [], error)

    home = studio.add_character(selected, "R01", "")
    candidate = studio.iterate(selected, "R01", "base.front", source / "a.png",
                               package=None, request=None, response=None, note="Authored project treatment")
    accepted = studio.accept(selected, "R01", candidate["iteration_id"])
    recorded_paths = [selected / studio.MANIFEST, home / "iterations.jsonl", home / "accepted" / "base.front.png"]
    before = {path: path.read_bytes() for path in recorded_paths}
    status_code, _, status_error = cli("status", "--studio", str(selected))
    validation_errors = validate_studio.validate(selected)
    check("reading and validation preserve project preferences and adopted work",
          status_code == 0 and not validation_errors and accepted["status"] == "accepted"
          and all(path.read_bytes() == data for path, data in before.items()),
          {"status_error": status_error, "validation_errors": validation_errors})

    invalid = dict(open_manifest, default_render_profile=[])
    studio.write_json(open_root / studio.MANIFEST, invalid)
    validation_errors = validate_studio.validate(open_root)
    invalid_target = tmp / "invalid-rendering"
    check("an invalid rendering preference is diagnosed without creating a project",
          refused(lambda: studio.init(invalid_target, "invalid-rendering", "Invalid rendering", default_render_profile=" "),
                  "nonempty profile id or null")
          and not invalid_target.exists()
          and any("default_render_profile must be a nonempty profile id or null" in item for item in validation_errors),
          validation_errors)


def package_attachments(tmp: Path, check) -> None:
    """Recover an original package on the same imported image, with real carriers.

    The bytes and decisions below are explicit synthetic fixtures. No external
    generation is performed and none of the source declarations are user consent.
    """
    import adoption_workflow
    import catalog_cli
    import pack_manager as pm
    from build_generation_payload import materialize_cli_reference_bundle
    from generation_payload_smoke_test import _write_fixture_pack, _package, PACK_ID, MODEL_ID
    from prepare_generation_references import prepare_references
    from verify_generation_payload import verify_content
    from studio_activity import chronological
    from PIL import Image

    base = tmp / 'attachments'; base.mkdir()
    pack = base / 'pack'; _write_fixture_pack(pack)
    settings = pm.PackSettings(roots=(pack,), state_file=base / 'state.json', cache_dir=base / 'cache',
        managed_root=base / 'managed', quarantine_root=base / 'quarantine', default_enabled_packs=(PACK_ID,))
    pm.save_state(settings.state_file, {'pack_roots': [], 'enabled_packs': [PACK_ID]})
    catalog_cli.configure_pack_runtime(settings)
    image_path = base / 'image.png'; Image.new('RGB', (24, 24), 'blue').save(image_path)
    references = prepare_references([{'role': 'scene-geometry', 'source': {'kind': 'supplied-file',
        'reference_id': 'synthetic-scene', 'resolved_path': str(image_path)}}], model=MODEL_ID,
        output_dir=base / 'prepared')
    original = base / 'original'; original.mkdir()
    references, companion = materialize_cli_reference_bundle(references, model=MODEL_ID,
        source_root=base / 'prepared', staging_root=original, companion_name='original.references')
    package = _package(references, prepared_reference_root=original)
    package_path = original / 'original.json'; package_path.write_bytes(execution_contract.encoded(package))
    evidence = base / 'receipt.txt'
    evidence.write_text('Synthetic fixture source receipt: the retained image is attributed to original.json. '
                        'This tests a later authored attribution, not proof of image generation.\n', encoding='utf-8')
    root = studio.init(base / 'studio', 'attachment-studio', 'Package attachment fixture')
    home = studio.add_character(root, 'C01', '')
    old = studio.iterate(root, 'C01', 'outfit.front', image_path,
        package=None, request=None, response=None, note='Synthetic original import')
    studio.accept(root, 'C01', old['iteration_id'])
    row = studio.iterate(root, 'C01', 'outfit.front', image_path,
        package=None, request=None, response=None, note='Synthetic selected import')
    row = studio.accept(root, 'C01', row['iteration_id'])
    before = studio.read_iterations(home, project=False)
    accepted = (root / row['accepted_path']).read_bytes()
    kwargs = {'package': package_path, 'evidence': evidence,
              'actor': 'SYNTHETIC FIXTURE AUTHOR', 'reason': 'The retained synthetic source receipt relates these exact files.'}

    check('a missing package status names attach-package and its evidence requirement',
        'studio.py attach-package' in studio.status(root) and 'ADOPTION_PACKAGE_REQUIRED' in studio.status(root))
    code, out, err = cli('attach-package', '--studio', str(root), '--character', 'C01', '--iteration', row['iteration_id'],
        '--package', str(package_path), '--evidence', str(evidence), '--actor', kwargs['actor'], '--reason', kwargs['reason'])
    check('attach-package CLI records the original full package with its discovered companion', code == 0, err)
    attached = json.loads(out)
    receipt = studio.validate_package_attachment(root, attached)
    after = studio.read_iterations(home, project=False)
    check('package attachment preserves both iterations, accepted image, provenance and acceptance history',
        len(after) == 2 and after[0] == before[0]
        and {key: value for key, value in after[1].items() if key not in {'package', 'package_attachment'}} == {
            key: value for key, value in before[1].items() if key != 'package'}
        and (root / row['accepted_path']).read_bytes() == accepted
        and attached['provenance'] == 'external-import' and attached.get('production') is None)
    check('attachment receipt retains distinct attribution time, actor, source and exact evidence bytes',
        chronological(receipt['recorded_at']) >= chronological(attached['at']) and receipt['actor'] == kwargs['actor']
        and receipt['source']['package'] == str(package_path)
        and (root / attached['package_attachment']['path']).parent.joinpath(receipt['evidence']['path']).read_bytes() == evidence.read_bytes()
        and receipt['package']['sha256'] == execution_contract.sha256_file(package_path))
    kept = root / attached['package']['path']
    check('attached Generation Package verifies with its actual retained companion',
        verify_content(studio.read_json(kept), package_root=kept.parent)['content_verified'] is True
        and bool(receipt['companion_files'])
        and (kept.parent / companion.name).is_dir())
    saved_rows = (home / 'iterations.jsonl').read_bytes()
    saved_receipt = (root / attached['package_attachment']['path']).read_bytes()
    retried = studio.attach_package(root, 'C01', row['iteration_id'], **kwargs)
    check('identical attachment retry preserves record time and never creates another iteration',
        retried == attached and (home / 'iterations.jsonl').read_bytes() == saved_rows
        and (root / attached['package_attachment']['path']).read_bytes() == saved_receipt)
    original_evidence = evidence.read_bytes(); evidence.write_bytes(original_evidence + b'Changed source.\n')
    message = failure(lambda: studio.attach_package(root, 'C01', row['iteration_id'], **kwargs))
    check('changed attribution evidence is refused without rewriting the first receipt', bool(message)
        and (home / 'iterations.jsonl').read_bytes() == saved_rows
        and (root / attached['package_attachment']['path']).read_bytes() == saved_receipt, message)
    evidence.write_bytes(original_evidence)
    original_package = package_path.read_bytes(); package_path.write_bytes(original_package + b'\n')
    message = failure(lambda: studio.attach_package(root, 'C01', row['iteration_id'], **kwargs))
    check('changed original package bytes cannot replace a recorded attachment', bool(message)
        and (home / 'iterations.jsonl').read_bytes() == saved_rows, message)
    package_path.write_bytes(original_package)
    carrier = next(path for path in companion.rglob('*') if path.is_file())
    carrier_raw = carrier.read_bytes(); carrier.write_bytes(b'Changed carrier')
    message = failure(lambda: studio.attach_package(root, 'C01', row['iteration_id'], **kwargs))
    check('changed source companion fails before changing the retained package', bool(message)
        and (home / 'iterations.jsonl').read_bytes() == saved_rows, message)
    carrier.write_bytes(carrier_raw)
    kept_evidence = kept.parent / receipt['evidence']['path']; kept_evidence.write_bytes(b'Changed retained evidence')
    errors = validate_studio.validate(root)
    readiness = adoption_workflow.adoption_readiness(root, 'C01', attached)
    check('validator and adoption readiness both reject damaged retained attribution evidence',
        any('invalid package attachment' in error for error in errors) and not readiness['source_ready'], errors)
    kept_evidence.write_bytes(original_evidence)
    approval = {'scope': 'sheet', 'influence': 'outfit', 'character': 'C01', 'iteration_id': row['iteration_id'],
        'slot': row['slot'], 'image_sha256': row['result']['sha256'], 'by': 'SYNTHETIC FIXTURE AUTHOR', 'at': '2000-01-01T00:00:00Z'}
    adoption_workflow.adopt(root, 'C01', row['iteration_id'], approval)
    check('the same imported iteration can be adopted after attachment without a new acceptance',
        (home / 'iterations.jsonl').read_bytes() == saved_rows and validate_studio.validate(root) == [],
        validate_studio.validate(root))

    recovery = studio.add_character(root, 'C02', '')
    candidate = studio.iterate(root, 'C02', 'base.front', image_path,
        package=None, request=None, response=None, note='Synthetic interrupted attachment')
    initial = (recovery / 'iterations.jsonl').read_bytes()
    destination = recovery / 'iterations' / candidate['iteration_id'] / 'package-attachment'
    with mock.patch.object(execution_contract, 'publish_directory', side_effect=OSError('Synthetic publish failure')):
        message = failure(lambda: studio.attach_package(root, 'C02', candidate['iteration_id'], **kwargs))
    check('attachment publication failure leaves the original iteration and no partial publication',
        'Synthetic publish failure' in message and not destination.exists()
        and (recovery / 'iterations.jsonl').read_bytes() == initial, message)
    with mock.patch.object(studio, 'write_iterations', side_effect=OSError('Synthetic ledger failure')):
        message = failure(lambda: studio.attach_package(root, 'C02', candidate['iteration_id'], **kwargs))
    published = (destination / 'record.json').read_bytes()
    check('a ledger failure retains a complete retryable attachment without changing the iteration',
        'Synthetic ledger failure' in message and (recovery / 'iterations.jsonl').read_bytes() == initial, message)
    recovered = studio.attach_package(root, 'C02', candidate['iteration_id'], **kwargs)
    check('retry completes the same published attachment and keeps its first recorded time',
        (destination / 'record.json').read_bytes() == published
        and len(studio.read_iterations(recovery)) == 1
        and studio.validate_package_attachment(root, recovered) is not None and validate_studio.validate(root) == [],
        validate_studio.validate(root))
    check('attachment requires actual attribution actor and a separate evidence file',
        'actor' in failure(lambda: studio.attach_package(root, 'C02', candidate['iteration_id'], **{**kwargs, 'actor': ''}))
        and 'separate' in failure(lambda: studio.attach_package(root, 'C02', candidate['iteration_id'], **{**kwargs, 'evidence': package_path})))

    # A genuine local Production package remains source evidence for a separately
    # imported row even after the run is abandoned. The original projection stays.
    from test_production_adoption import AdoptionTests
    import production_workflow as workflow
    import production_store as store
    fixture_type = type('AttachmentAdoptionFixture', (AdoptionTests,), {})
    case = fixture_type('test_separate_authorized_adoption_and_completion')
    case.addCleanup(fixture_type.doClassCleanups)
    try:
        fixture_type.setUpClass()
        case.setUp()
        origin_root, origin_row = case.root, case.row
        origin_home = studio.character_home(origin_root, 'robot')
        imported = studio.iterate(origin_root, 'robot', origin_row['slot'], origin_root / origin_row['result']['path'],
            package=None, request=None, response=None, note='Synthetic imported image with distinct ownership')
        studio.accept(origin_root, 'robot', imported['iteration_id'])
        workflow.abandon_task(origin_root, case.task['task_id'], actor='SYNTHETIC FIXTURE AUTHOR',
                              reason='Synthetic source run stopped; the imported image has a separate adoption decision.')
        before_rows = studio.read_iterations(origin_home, project=False)
        before_events = store.event_rows(origin_root, case.run)
        bound_kwargs = {**kwargs, 'package': origin_root / origin_row['package']['path'], 'evidence': origin_root / 'adoption-basis.txt'}
        recovered = studio.attach_package(origin_root, 'robot', imported['iteration_id'], **bound_kwargs)
        source_receipt = studio.validate_package_attachment(origin_root, recovered)
        check('a bound package retains imported ownership and its original abandoned Production projection',
            recovered.get('production') is None and recovered['provenance'] == 'external-import'
            and studio.read_iterations(origin_home, project=False)[0] == before_rows[0]
            and len(studio.read_iterations(origin_home)) == 2
            and source_receipt['production_candidates'] == [case.candidate]
            and studio.read_json(origin_root / recovered['package']['path'])['production_binding']['run'] == case.run)
        check('attaching a bound package creates no Production selection, claim, authorization or event',
            store.event_rows(origin_root, case.run) == before_events)
        approval = {**case.approval, 'iteration_id': imported['iteration_id']}
        adoption_workflow.adopt(origin_root, 'robot', imported['iteration_id'], approval)
        check('an abandoned run does not block a separately approved imported image adoption',
            store.event_rows(origin_root, case.run) == before_events and validate_studio.validate(origin_root) == [],
            validate_studio.validate(origin_root))
        other = studio.iterate(origin_root, 'robot', 'outfit.front', image_path,
            package=None, request=None, response=None, note='Synthetic unrelated imported image')
        message = failure(lambda: studio.attach_package(origin_root, 'robot', other['iteration_id'], **bound_kwargs))
        check('a bound package for another local candidate image is refused without creating an attachment',
            'no matching image candidate' in message
            and not (origin_home / 'iterations' / other['iteration_id'] / 'package-attachment').exists(), message)
        check('attach-package cannot rewrite a Production-owned iteration',
            'external-import' in failure(lambda: studio.attach_package(origin_root, 'robot', origin_row['iteration_id'], **bound_kwargs))
            and studio.read_iterations(origin_home, project=False)[0] == before_rows[0])
    finally:
        case.doCleanups()


def regressions(tmp: Path, source: Path, check) -> None:
    """One check or more for each defect the studio had."""

    def recorded(root: Path, character: str, name: str, **files: Any) -> dict[str, Any]:
        return studio.iterate(root, character, "base", source / name, package=files.get("package"),
                              request=files.get("request"), response=None, note=None, layout=files.get("layout"))

    # The studio is named before or after the command; the documentation writes it after.
    after = studio.init(tmp / "after", "after-studio", "After")
    code, _, err = cli("character", "add", "C04", "--studio", str(after))
    check("--studio after the command adds the character", code == 0 and (after / "characters" / "C04").is_dir(), err)
    code, _, err = cli("--studio", str(after), "character", "add", "C05")
    check("--studio before the command works", code == 0 and (after / "characters" / "C05").is_dir(), err)
    named = ["--studio", str(after), "--character", "C04"]
    steps = [
        ["iterate", *named, "--slot", "base", "--result", str(source / "a.png")],
        ["iterate", *named, "--slot", "base", "--result", str(source / "b.png")],
        ["accept", *named, "--iteration", "it-0001"],
        ["reject", *named, "--iteration", "it-0002", "--reason", "too dark", "--actor", "Synthetic test author"],
        ["status", "--studio", str(after)],
        ["gallery", "--studio", str(after)],
    ]
    outcomes = [cli(*step) for step in steps]
    check("every recording command takes --studio after it",
          [code for code, _, _ in outcomes] == [0] * len(steps) and validate_studio.validate(after) == [],
          [err for _, _, err in outcomes])
    guide = (ROOT / "references" / "runtime" / "studio.md").read_text(encoding="utf-8")
    check("Studio Runtime writes --studio after the command everywhere", "studio.py --studio" not in guide)

    # A character's record is replaced whole under that mutable owner's lock.
    crash = studio.init(tmp / "crash", "crash-studio", "Crash")
    crash_home = studio.add_character(crash, "C06", "")
    recorded(crash, "C06", "a.png")
    before = (crash_home / "iterations.jsonl").read_bytes()
    interrupted = False
    with mock.patch("os.replace", side_effect=KeyboardInterrupt):
        try:
            recorded(crash, "C06", "b.png")
        except KeyboardInterrupt:
            interrupted = True
    check("an interrupted record leaves the previous record whole and readable",
          interrupted and (crash_home / "iterations.jsonl").read_bytes() == before
          and "1 generated image," in studio.status(crash) and not list(crash.rglob(".pending-*"))
          and validate_studio.validate(crash) == [],
          {"interrupted": interrupted, "errors": validate_studio.validate(crash)})
    locked = studio.init(tmp / "locked", "locked-studio", "Locked")
    locked_owner = studio.add_character(locked, "C07", "")
    independent_owner = studio.add_character(locked, "C08", "")
    recorded(locked, "C07", "a.png")
    recorded(locked, "C07", "b.png")
    actions = {
        "independent character": lambda: recorded(locked, "C08", "c.png"),
        "gallery projection": lambda: studio.write_gallery(locked),
    }
    completed = {name: completes_while_owner_is_locked(locked_owner, action) for name, action in actions.items()}
    check("an unrelated character and gallery complete while another character owner is locked",
          all(completed.values()) and len(studio.read_iteration_records(locked_owner)) == 2
          and len(studio.read_iteration_records(independent_owner)) == 1
          and len(studio.read_json(locked / 'gallery.json')['entries']) == 3, completed)
    swap = studio.init(tmp / "swap", "swap-studio", "Swap")
    swap_home = studio.add_character(swap, "C09", "")
    (source / "d.jpg").write_bytes(b"\xff\xd8JPEG-d")
    png = recorded(swap, "C09", "a.png")
    jpg = recorded(swap, "C09", "d.jpg")
    studio.accept(swap, "C09", png["iteration_id"])
    (swap / jpg["result"]["path"]).unlink()
    message = failure(lambda: studio.accept(swap, "C09", jpg["iteration_id"]))
    check("a failed acceptance leaves the slot's accepted image in place",
          "missing file: " + jpg["result"]["path"] in message and (swap_home / "accepted" / "base.png").read_bytes() == b"\x89PNG-a"
          and studio.read_iterations(swap_home)[0]["status"] == "accepted",
          message)
    (swap / jpg["result"]["path"]).write_bytes(b"\xff\xd8JPEG-d")
    studio.accept(swap, "C09", jpg["iteration_id"])
    check("an accepted image of another file type replaces the old copy",
          sorted(path.name for path in (swap_home / "accepted").iterdir()) == ["base.jpg"]
          and validate_studio.validate(swap) == [],
          sorted(path.name for path in (swap_home / "accepted").iterdir()))

    # Accepting an earlier image again.
    again = studio.init(tmp / "again", "again-studio", "Again")
    again_home = studio.add_character(again, "C10", "")
    for name in ("a.png", "b.png", "c.png"):
        recorded(again, "C10", name)
    for chosen in ("it-0001", "it-0002", "it-0001"):
        studio.accept(again, "C10", chosen)
    rows = {row["iteration_id"]: row for row in studio.read_iterations(again_home)}
    check("accepting an earlier image again leaves a record the validator accepts",
          validate_studio.validate(again) == [] and rows["it-0001"]["status"] == "accepted"
          and "superseded_by" not in rows["it-0001"] and rows["it-0002"]["superseded_by"] == "it-0001"
          and (again_home / "accepted" / "base.png").read_bytes() == b"\x89PNG-a",
          {"errors": validate_studio.validate(again), "rows": rows})
    studio.accept(again, "C10", "it-0003")
    studio.accept(again, "C10", "it-0002")
    rows = {row["iteration_id"]: row for row in studio.read_iterations(again_home)}
    history = {key: [item.get("supersedes") for item in row.get("acceptances") or []] for key, row in rows.items()}
    page = gallery_details(again)
    check("every acceptance stays in the slot's history with what it replaced",
          history == {"it-0001": [None, "it-0002"], "it-0002": ["it-0001", "it-0003"], "it-0003": ["it-0001"]}
          and "in place of it-0003" in page and validate_studio.validate(again) == [],
          history)
    tampered = [dict(row) for row in studio.read_iterations(again_home)]
    tampered[0]["acceptances"] = [{"at": "2026-01-01T00:00:00Z", "supersedes": "it-0099"}]
    studio.write_iterations(again_home, tampered)
    check("an acceptance that names no acceptance in its historical slot is reported",
          any("has no acceptance in slot 'base'" in error for error in validate_studio.validate(again)),
          validate_studio.validate(again))

    # A character id names one directory on every system.
    ids = studio.init(tmp / "ids", "ids-studio", "Ids")
    dotted = failure(lambda: studio.add_character(ids, "hero.", ""))
    plain = failure(lambda: studio.add_character(ids, "hero", ""))
    check("a character id ending in a dot is refused and the plain id stays free",
          "not ending with a dot" in dotted and not plain and studio.listed_characters(ids) == ["hero"], [dotted, plain])
    check("an id that differs only by case from a character is refused",
          refused(lambda: studio.add_character(ids, "HERO", ""), "differs only by case")
          and studio.listed_characters(ids) == ["hero"])
    devices = [failure(lambda name=name: studio.add_character(ids, name, "")) for name in ("con", "NUL", "com1.png")]
    check("a Windows device name is refused as a character id, and a longer name that starts with one is not",
          all("Windows device name" in message for message in devices)
          and not failure(lambda: studio.add_character(ids, "console", ""))
          and sorted(studio.listed_characters(ids)) == ["console", "hero"], devices)
    document = studio.manifest(ids)
    document["characters"] += [{"id": "Hero", "added_at": "2026-01-01T00:00:00Z"},
                               {"id": "villain.", "added_at": "2026-01-01T00:00:00Z"}]
    studio.write_json(ids / studio.MANIFEST, document)
    errors = validate_studio.validate(ids)
    check("the validator reports ids that differ only by case or end in a dot",
          any("'Hero' and 'hero' differ only by case" in error or "'hero' and 'Hero' differ only by case" in error for error in errors)
          and any("'villain.' is not a valid character id" in error for error in errors),
          errors)

    # A mistyped path is one sentence, and nothing is half recorded.
    missing = (tmp / "no-such-studio").resolve()
    code, _, err = cli("status", "--studio", str(missing))
    check("a --studio directory that does not exist is named as missing",
          code == 1 and f"the directory {missing} does not exist" in err and "not in a studio" not in err, err)
    iterations = after / "characters" / "C04" / "iterations"

    def kept() -> list[str] | None:
        return sorted(path.name for path in iterations.iterdir()) if iterations.is_dir() else None

    before_typos = kept()
    code, _, err = cli("iterate", *named, "--slot", "base", "--result", str(tmp / "typo.png"))
    check("a mistyped result path is one sentence and records nothing",
          code == 1 and err.count("\n") == 1 and "the result file" in err and "does not exist" in err
          and "Errno" not in err and before_typos is not None and kept() == before_typos, err)
    code, _, err = cli("iterate", *named, "--slot", "base", "--result", str(source / "a.png"), "--request", str(tmp / "typo.json"))
    check("a mistyped request path leaves no half-recorded iteration",
          code == 1 and "the request file" in err and before_typos is not None and kept() == before_typos, err)
    (tmp / "plain.txt").write_text("not a directory\n", encoding="utf-8")
    code, _, err = cli("init", "--out", str(tmp / "plain.txt" / "studio"), "--studio-id", "plain", "--title", "Plain")
    check("init below a file says so in one sentence", code == 1 and "is a file" in err and "Error" not in err, err)
    code, out, _ = cli("init", "--out", str(tmp / "opened"), "--studio-id", "opened", "--title", "Opened")
    printed = next((line for line in out.splitlines() if "work_ledger.py" in line), "")
    command = printed.partition(": ")[2].replace("<goal>", "Synthetic-goal").replace("<step>", "Synthetic-step")
    opened = subprocess.run(command, shell=True, cwd=tmp, capture_output=True, text=True, encoding="utf-8")
    check("init prints the command that opens a task in the new studio, and that command opens one",
          code == 0 and opened.returncode == 0
          and (work_ledger.read_current(tmp / "opened") or {}).get("goal") == "Synthetic-goal", {"out": out, "command": command})
    check("validate_studio names a directory that does not exist",
          validate_studio.validate(missing) == [f"the directory {missing} does not exist"], validate_studio.validate(missing))
    code, _, err = cli("accept", "--studio", str(after), "--character", "nobody", "--iteration", "it-0001")
    check("a mistyped character is named, not reported as a missing iteration",
          code == 1 and "character 'nobody' is not in this studio" in err, err)

    # The gallery shows what was sent, through the fields the transport named.
    shown = studio.init(tmp / "shown", "shown-studio", "Shown")
    studio.add_character(shown, "C11", "")
    (source / "acme-request.json").write_text(json.dumps({
        "endpoint_model": "acme/m1", "op": "txt2img", "input": {"text": "a heron", "avoid": "blur", "images": ["media-1"]},
        "steps": 20, "seed": 5, "request_id": "r-1"}), encoding="utf-8")
    (source / "upscale-request.json").write_text(json.dumps({
        "taskType": "imageUpscale", "model": "acme/up", "upscaleFactor": 2, "inputImage": "media-2", "taskUUID": "u-1"}), encoding="utf-8")
    (source / "hand-request.json").write_text(json.dumps({"prompt": "a heron by hand", "cfg": 4}), encoding="utf-8")
    (source / "acme-package.json").write_text(json.dumps({"generation_payload": {
        "prompt": "package prompt", "negative_prompt": "package negative never sent"}}), encoding="utf-8")
    acme = recorded(shown, "C11", "a.png", package=source / "acme-package.json", request=source / "acme-request.json",
                    layout=layout(["input", "text"], ["input", "avoid"], model=["endpoint_model"], operation=["op"],
                                  management=[["request_id"]], media=[["input", "images", 0]], seed=["seed"]))
    recorded(shown, "C11", "b.png", request=source / "upscale-request.json", layout=layout(None, media=[["inputImage"]]))
    recorded(shown, "C11", "c.png", package=source / "acme-package.json", request=source / "hand-request.json")
    entries = sorted(json.loads((shown / "gallery.json").read_text(encoding="utf-8"))["entries"], key=lambda e:e["iteration_id"])
    page = gallery_details(shown)
    check("the gallery reads prompt, negative, settings and media through the recorded fields",
          entries[0]["prompt"] == "a heron" and entries[0]["negative_prompt"] == "blur"
          and entries[0]["settings"] == {"steps": 20, "seed": 5} and entries[0]["media"] == {"input.images.0": "media-1"}
          and acme["seed"] == 5 and (acme.get("service") or {}).get("model_identifier") == "acme/m1",
          entries[0])
    upscale = page[page.index("/ it-0002 <span"):].split("</section>")[0]
    check("a request that carried no prompt or negative shows that none was sent",
          entries[1]["prompt"] is None and entries[1]["negative_prompt"] is None and entries[1].get("prompt_fields_known") is True
          and "<b>prompt</b> none sent" in upscale and "<b>negative</b> none sent" in upscale,
          upscale)
    check("text only in the package is never shown as sent",
          "package negative never sent" not in page and "package prompt" not in page
          and entries[2]["settings"] == {"prompt": "a heron by hand", "cfg": 4} and validate_studio.validate(shown) == [],
          {"entry": entries[2], "errors": validate_studio.validate(shown)})
    before_rows = studio.read_iterations(shown / "characters" / "C11")
    check("a layout that does not describe the recorded request is refused before anything is kept",
          refused(lambda: recorded(shown, "C11", "a.png", request=source / "hand-request.json", layout=layout(["positivePrompt"])),
                  "does not describe the recorded request")
          and studio.read_iterations(shown / "characters" / "C11") == before_rows)


def main() -> int:
    results: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: Any = None) -> None:
        results.append({"name": name, "passed": bool(passed), "detail": detail})

    with tempfile.TemporaryDirectory() as tmp:
        root = studio.init(Path(tmp) / "studio", "smoke-studio", "Smoke studio")
        check("init writes the manifest and every directory", all((root / name).is_dir() for name in studio.DIRECTORIES) and (root / studio.MANIFEST).is_file())
        check("API initialization leaves rendering unselected", studio.manifest(root)["default_render_profile"] is None
              and studio.manifest(root)["default_style_family"] is None)
        check("init refuses a non-empty directory", refused(lambda: studio.init(root, "again", "Again"), "not empty"))
        check("a fresh studio validates", validate_studio.validate(root) == [], validate_studio.validate(root))
        check("the studio is found from a directory inside it", studio.studio_root(root / "packages") == root)

        # The work trail.
        task = work_ledger.begin(root, "C01 base front", ["generate candidates", "present and record the choice", "accept one"])
        check("a task opens with its first step next", task["next"] == "generate candidates" and uuid.UUID(task["task_id"]).version == 7)
        check("a second task cannot open while one is open", refused(lambda: work_ledger.begin(root, "other", ["x"]), "already open"))
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
        (source / "request.json").write_text(json.dumps({"taskType": "imageInference", "model": "vendor:model@1", "positivePrompt": "a wolf", "width": 1024, "height": 1024, "seed": 7, "taskUUID": "x"}), encoding="utf-8")
        (source / "response.json").write_text(json.dumps({"seed": 7, "imageURL": "https://example.invalid/a.png"}), encoding="utf-8")
        (source / "package.json").write_text(json.dumps({"generation_input_sha256": "0" * 64, "generation_payload": {"service": {"id": "svc", "model_identifier": "vendor:model@1", "observed_at": "2026-09-13", "schema_snapshot": None}}}), encoding="utf-8")
        first = studio.iterate(root, "C01", "base.front", source / "a.png", package=source / "package.json", request=source / "request.json", response=source / "response.json", note="first", layout=layout(["positivePrompt"], seed=["seed"]))
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
        check("accepting another iteration supersedes the previous one", rows[0]["status"] == "superseded" and rows[0]["superseded_by"] == "it-0002" and (again.get("acceptances") or [{}])[-1].get("supersedes") == "it-0001")
        check("the accepted copy follows the newly accepted iteration", (root / again["accepted_path"]).read_bytes() == b"\x89PNG-b" and len(list((home / "accepted").glob("base.front.*"))) == 1)
        check("an accepted iteration cannot be rejected", refused(lambda: studio.reject(root, "C01", "it-0002", "no", actor="Synthetic test author"), "is accepted"))
        rejected = studio.reject(root, "C01", "it-0003", "jaw too narrow", actor="Synthetic test author")
        check("a rejected iteration keeps its reason", rejected["status"] == "rejected" and rejected["reason"] == "jaw too narrow")
        check("a rejected iteration cannot be accepted", refused(lambda: studio.accept(root, "C01", "it-0003"), "was rejected"))
        recipe = studio.recipe(root, "C01", "base.front")
        laid_out = studio.recipe(root, "C01", "base.front", iteration="it-0001")
        check("the recipe leaves out the run's identifiers and seed its recorded layout names, and keeps every field without one",
              recipe["iteration_id"] == "it-0002" and recipe["seed"] == 7
              and recipe["settings"] == json.loads((source / "request.json").read_text(encoding="utf-8"))
              and laid_out["settings"] == {"taskType": "imageInference", "model": "vendor:model@1", "positivePrompt": "a wolf", "width": 1024, "height": 1024}
              and laid_out["seed"] == 7, (recipe, laid_out))
        check("a slot with nothing accepted has no recipe", refused(lambda: studio.recipe(root, "C01", "outfit.back"), "no accepted iteration"))
        report = studio.status(root)
        check("status names the accepted slot and the open task", "accepted base.front: it-0002" in report and f"open task {task["task_id"]}" in report, report)
        check(
            "status speaks in plain words with correct plurals",
            "3 generated images, 1 slot accepted, 0 candidates waiting" in report
            and "1 slots" not in report and "next=" not in report and "adopt-with-sheet-scope" not in report
            and "base.front as a reference: accepted, not bound to the sheet; use studio.py attach-package" in report
            and "including the evidence that relates it to this image" in report,
            report,
        )

        check("the gallery exists from init and is current after every recording command, unasked", studio.gallery_stale(root) is None and (root / "gallery.html").is_file(), studio.gallery_stale(root))
        (root / "gallery.json").write_text('{"entries": []}', encoding="utf-8")
        check("a gallery that does not match the records is reported", any("gallery" in e for e in validate_studio.validate(root)), validate_studio.validate(root))
        html_path, json_path = studio.write_gallery(root)
        index = json.loads(json_path.read_text(encoding="utf-8"))
        check(
            "the gallery index lists every iteration newest first with prompt, model, settings, and seed",
            [e["iteration_id"] for e in index["entries"]] == ["it-0003", "it-0002", "it-0001"]
            and index["entries"][2]["prompt"] == "a wolf"
            and index["entries"][2]["settings"] == {"width": 1024, "height": 1024, "seed": 7}
            and index["entries"][2]["service"]["model_identifier"] == "vendor:model@1"
            and index["entries"][2]["seed"] == 7,
            index["entries"][2],
        )
        page = gallery_details(root)
        check(
            "each gallery detail shows its image, actual prompt and acceptance",
            'src="./characters/C01/iterations/it-0002/result.png"' in page and "a wolf" in page and 'class="iteration accepted"' in page and "it-0003" in page,
        )
        sections = {entry: page[page.index(f"/ {entry} <span"):] for entry in ("it-0001", "it-0002", "it-0003")}
        check(
            "the gallery labels an unknown seed and model record instead of leaving them blank",
            "<b>seed</b> 7" in sections["it-0001"]
            and "<b>seed</b> not recorded" in sections["it-0003"] and "<b>model record</b> not recorded" in sections["it-0003"]
            and "<b>seed</b> </p>" not in page and "<b>record</b>" not in page,
            sections["it-0003"][:600],
        )
        check(
            "a request recorded without its layout is listed field by field, with no prompt named",
            index["entries"][1].get("prompt_fields_known") is False and index["entries"][1]["prompt"] is None
            and index["entries"][1]["settings"].get("positivePrompt") == "a wolf"
            and "does not say which field held the prompt" in sections["it-0002"].split("</section>")[0]
            and "<b>request</b> not recorded" in sections["it-0003"].split("</section>")[0],
            index["entries"][1],
        )

        check("the studio validates with iterations recorded", validate_studio.validate(root) == [], validate_studio.validate(root))
        (root / first["result"]["path"]).write_bytes(b"changed")
        check("a result whose bytes moved is reported", any("no longer matches" in error for error in validate_studio.validate(root)), validate_studio.validate(root))
        (root / first["result"]["path"]).write_bytes(b"\x89PNG-a")

        question = work_ledger.read_current(root)['questions'][-1]
        work_ledger.respond(root, question['question_id'], 'Use the second synthetic image.', actor='Synthetic test author')
        # This test's explicit synthetic review binds the delivered real fixture
        # bytes. Studio acceptance above remains a separate operation.
        import execution_contract as evidence
        import production_workflow as production
        import production_fixtures
        (root / "delivery.txt").write_text("Deliver the selected test image.\n", encoding="utf-8")
        spec = {"task_id": task["task_id"], "route": "development", "features": [], "execution": "external",
                "sources": [], "world_views": [],
                "delivery": {"path": "delivery.txt",  "translation_notes": "Synthetic fixture."},
                "criteria": [{"id": "fixture", "strength": "hard", "text": "Deliver the inspected image fixture."}]}
        production_fixtures.task(root,spec,artifact="binary",execution="external")
        (root / "production-task.json").write_bytes(evidence.encoded(spec))
        run = production.prepare(root, "production-task.json")["run"]
        production_fixtures.handoff(root, run, "synthetic fixture", "manual")
        token = production_fixtures.grant(root, run, production.external_intent(root, run, 1))
        production.claim_external(root, run, 1, token)
        candidate = production.capture(root, run, again["accepted_path"], "Synthetic image bytes, not generated media.")
        (root / "synthetic-receipt.json").write_bytes(evidence.encoded({"synthetic": True, "status": "received"}))
        production.receive_external(root, run, response_file="synthetic-receipt.json", artifacts=[again["accepted_path"]],
                                    final=True, reason="The synthetic delegated fixture was received.")
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
        check("finishing with steps left is refused", refused(lambda: work_ledger.finish(root, run), "not done"))
        work_ledger.step_done(root, 2)
        work_ledger.step_done(root, 3)
        work_ledger.finish(root, run)
        check("a finished task leaves no open task and stays in the ledger", work_ledger.read_current(root) is None and any(e["event"] == "finished" for e in work_ledger.read_ledger(root)))
        shown = work_ledger.show(root)
        check("show reports the trail when nothing is open, and the command that opens the next task",
              "no task is open; the last recorded" in shown and shown.splitlines()[-1].endswith(work_ledger.begin_command(root)), shown)
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

        regressions(Path(tmp), source, check)
        render_preferences(Path(tmp), source, check)
        package_attachments(Path(tmp), check)

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
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
