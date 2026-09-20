#!/usr/bin/env python3
"""Author a series end to end, and require each command to refuse what it must.

The contract tests settle that the two readers refuse a bad document. This
settles the other half: that a series can actually be written here, from an
empty directory to a narrative with people and places in it that the index and
the coverage report agree about.

It is a real run each time. Every case builds a directory, does one thing to it,
and requires the message that thing is for, so a rule that stops firing is
caught by the case written for it rather than by a count that still adds up.

A rename is exercised against something that actually names the id, because a
rename over an id nothing references checks that a file moved and nothing else,
which is what the first version of this test did while its comment said it
reached the references.

A case asks for the sentence its rule prints and sets up a series that can
answer it either way, because a check that passes whichever way the rule went
is a check that reports nothing. Three here did. The one about a place nobody
names matched on the id, which the same file's unfilled blanks also carry. The
one about the blanks the form ships with matched on a sentence the narrative's
own blanks also print. And the one about which directory the coverage report
treats as the series asked it of a narrative under a directory holding no
places, where walking out and staying put give the same answer.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import narrative  # noqa: E402
import narrative_coverage  # noqa: E402
import narrative_index  # noqa: E402
import scene_plot as scene_plot_module  # noqa: E402

NL = chr(10)


def run(*arguments: str) -> subprocess.CompletedProcess:
    """One command, the way a session runs it, in this interpreter."""

    return subprocess.run(
        [sys.executable, *arguments], cwd=ROOT, text=True, check=False,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def start(directory: Path, *extra: str) -> subprocess.CompletedProcess:
    return run("scripts/narrative_init.py", "--out", str(directory),
               "--series-id", "demo", "--title", "A demo", "--seed", "example", *extra)


def entity(directory: Path, *arguments: str) -> subprocess.CompletedProcess:
    return run("scripts/narrative_entity.py", "--series", str(directory), *arguments)


def scene_plot(series: Path, location: str) -> dict:
    """One scene of the series the templates create, at one place in it."""

    document = json.loads((series / "narrative/narrative.json").read_text(encoding="utf-8"))
    return {
        "artifact_type": "scene-plot",
        "scene_id": "sc01",
        "narrative_sha256": narrative.content_sha256(document),
        "chapter": "ch01",
        "order": 1,
        "arcs": ["a01"],
        "characters": ["C01"],
        "themes": ["t01"],
        "focalization": {"kind": "external"},
        "setting": {
            "interior_exterior": "interior",
            "location": location,
            "where": "by the window",
            "time_of_day": "morning",
        },
        "scene_function": "entry",
        "delivery_role": "chapter_opening",
        "proposition": "the series opens where its habit is visible",
        "turn": {"value": "safety", "from": "assumed", "to": "questioned"},
        "beats": [
            {"id": "b1", "beat": "she comes in and does not sit", "visibility": "visible"},
            {"id": "b2", "beat": "the room has been used by somebody else", "visibility": "visible"},
        ],
        "exchanges": [
            {"id": "x1", "between": ["C01"], "about": "the chair",
             "achieves": "she says nothing about it", "from": ["b1"]},
        ],
        "placement": [{"statement": "she stands at the window", "from": ["b1"]}],
        "must_preserve": [{"statement": "the second lantern stays where it is", "from": ["b2"]}],
        "free": [{"statement": "the weather"}],
        "state_changes": [
            {"target": "C01", "change": "knows somebody was here", "from": ["b2"]},
        ],
        "realization": {
            "kind": "shots",
            "units": [
                {"id": "sh01", "focal_beat": "b1",
                 "shows": [{"statement": "she stops inside the door", "from": ["b1"]}],
                 "composition": [{"statement": "the door frames her", "from": ["b1"]}]},
                {"id": "sh02", "focal_beat": "b2",
                 "shows": [{"statement": "a second lantern on the sill", "from": ["b2"]}],
                 "composition": [{"statement": "the lantern sits low in frame", "from": ["b2"]}]},
            ],
        },
    }


def main() -> int:
    checks = 0
    failures: list[str] = []
    # A case this machine cannot set up. One case here needs a directory link,
    # which not every machine allows an ordinary account to make, and a case
    # that quietly passes when it did not run is worse than one that says so.
    skipped: list[str] = []

    def expect(label: str, condition: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not condition:
            failures.append(f"{label}: {detail}"[:400])

    with tempfile.TemporaryDirectory(prefix="narrative-authoring-") as temp:
        base = Path(temp)

        # A series directory is created, and what it creates answers the contract.
        series = base / "made"
        done = start(series)
        expect("init succeeds", done.returncode == 0, done.stdout)
        expect("init reports a valid narrative",
               '"ok": true' in done.stdout.lower(), done.stdout[:200])
        for relative in ("narrative/narrative.json", "narrative/personas/persona-template.md",
                         "narrative/scenes", "narrative/world/locations", "narrative/glossary"):
            expect(f"init writes {relative}", (series / relative).exists())

        # The medium is a decision the series starts with, not a default to find out about later.
        prose = base / "prose"
        start(prose, "--medium", "prose")
        value = json.loads((prose / "narrative/narrative.json").read_text(encoding="utf-8"))
        expect("medium is written", value.get("medium") == "prose", str(value.get("medium")))

        # An existing non-empty directory is not overwritten.
        again = start(series)
        expect("init refuses a non-empty directory", again.returncode != 0, again.stdout)
        expect("init says why", "not empty" in again.stdout, again.stdout[:200])

        # A bad series id is refused before anything is written.
        bad = run("scripts/narrative_init.py", "--out", str(base / "bad"),
                  "--series-id", "a b", "--title", "x")
        expect("init refuses a bad series id", bad.returncode != 0, bad.stdout)
        expect("the refused series id wrote nothing", not (base / "bad").exists())

        # The index reads what was written and finds the persona the narrative names.
        report = narrative_index.scan(series)
        expect("index reads a fresh series", report["ok"], str(report["errors"])[:200])
        expect("index counts the seeded persona", report["counts"]["persona"] == 1,
               str(report["counts"]))
        # Named files, because two different readings report a blank: the
        # form the persona starts from, and the narrative itself. A check that
        # asked only for the sentence passed on either one, so neither was
        # covered by it.
        expect("index reports the blanks the persona form ships with",
               any("c01.md" in gap and "blank(s) nobody has filled" in gap
                   for gap in report["gaps"]), str(report["gaps"])[:300])
        expect("index reports the blanks the narrative ships with",
               any("narrative.json" in gap and "blank(s) nobody has filled" in gap
                   for gap in report["gaps"]), str(report["gaps"])[:300])

        # The same command as a subprocess, because that is how it is documented.
        spawned = run("scripts/narrative_index.py", str(series), "--json")
        expect("index runs as a command", spawned.returncode == 0, spawned.stdout[:200])
        expect("index prints a report", '"ok"' in spawned.stdout, spawned.stdout[:200])
        strict = run("scripts/narrative_index.py", str(series), "--json", "--strict")
        expect("index --strict fails on a gap", strict.returncode != 0, strict.stdout[:200])

        # A place is created, and the index reports it as named by nothing yet.
        made = entity(series, "add", "location", "the-boathouse", "--name", "The boathouse")
        expect("entity add succeeds", made.returncode == 0, made.stdout)
        expect("entity add writes the file",
               (series / "narrative/world/locations/the-boathouse.md").is_file())
        report = narrative_index.scan(series)
        # The sentence, not the id. A file written from the headings also
        # reports its unfilled blanks, and that gap names the same id, so a
        # check that asked only for the id passed whether or not anything
        # reported the place as named by nothing.
        expect("index reports an unnamed place",
               any("nothing in the series names 'the-boathouse'" in gap
                   for gap in report["gaps"]), str(report["gaps"])[:200])

        # The same id twice is refused rather than overwriting the first.
        twice = entity(series, "add", "location", "the-boathouse")
        expect("entity add refuses a repeat", twice.returncode != 0, twice.stdout)
        expect("the repeat says where the first one is",
               "already exists" in twice.stdout, twice.stdout[:200])

        # Something that names the place, so the rename has references to reach.
        plot_path = series / "narrative/scenes/sc01-plot.json"
        plot = scene_plot(series, "the-boathouse")
        # Approved, because the assertion below is that a rename takes the
        # approval away, and a plot with none to take proves nothing.
        plot["approved"] = {"by": "a test", "at": "2026-01-01T00:00:00Z",
                            "content_sha256": scene_plot_module.content_sha256(plot)}
        plot_path.write_text(json.dumps(plot, ensure_ascii=False, indent=2) + NL,
                             encoding="utf-8", newline="\n")
        persona = series / "narrative/personas/c01.md"
        body = persona.read_text(encoding="utf-8")
        persona.write_text(body.replace("references: []", "references: [the-boathouse]"),
                           encoding="utf-8", newline="\n")

        coverage = narrative_coverage.cover(
            series / "narrative/narrative.json", series / "narrative/scenes", series=series)
        expect("the scene this test wrote is valid", coverage["ok"], str(coverage["errors"])[:300])
        expect("coverage counts it", coverage["scenes"] == 1, str(coverage.get("scenes")))

        # The rename reaches the references, and nothing else in a front matter block.
        renamed = entity(series, "rename", "the-boathouse", "the-galley")
        expect("entity rename succeeds", renamed.returncode == 0, renamed.stdout)
        expect("the old file is gone",
               not (series / "narrative/world/locations/the-boathouse.md").exists())
        expect("the new file is there",
               (series / "narrative/world/locations/the-galley.md").is_file())
        rewritten = json.loads(renamed.stdout).get("rewritten") or []
        expect("the rename reports what it rewrote",
               any("c01.md" in item for item in rewritten)
               and any("sc01-plot.json" in item for item in rewritten), str(rewritten))
        head = persona.read_text(encoding="utf-8").splitlines()[:8]
        expect("the persona still says what kind it is", "kind: persona" in head, str(head))
        expect("the persona's reference moved", "references: [the-galley]" in head, str(head))
        moved = json.loads(plot_path.read_text(encoding="utf-8"))
        expect("the plot's location moved", moved["setting"]["location"] == "the-galley",
               str(moved["setting"]))
        expect("the plot's approval is gone", "approved" not in moved, str(list(moved)))
        expect("the index agrees after a rename", narrative_index.scan(series)["ok"],
               str(narrative_index.scan(series)["errors"])[:200])

        # A rename of an id that is also a word the front matter holds.
        collision = base / "collision"
        start(collision)
        entity(collision, "add", "term", "persona", "--name", "Persona")
        entity(collision, "rename", "persona", "role")
        kinds = (collision / "narrative/personas/c01.md").read_text(encoding="utf-8")
        expect("a rename does not rewrite what a file says it is",
               "kind: persona" in kinds, kinds.splitlines()[:4])

        # A rename over files a person wrote rather than a command. The entity
        # sits below the top of its directory, writes its own id in quotes, and
        # the file naming it indents the line: the index reads all three, so a
        # rename that cannot see one of them says ok and leaves an id behind
        # either on the file it just moved or in the file that names it.
        deep = base / "deep"
        start(deep)
        below = deep / "narrative/world/locations/below"
        below.mkdir(parents=True)
        (below / "the-cellar.md").write_text(
            NL.join(["---", "kind: location", 'id: "the-cellar"', "references: []", "---"]) + NL,
            encoding="utf-8", newline="\n")
        keeper = deep / "narrative/world/artifacts/old"
        keeper.mkdir(parents=True)
        lamp = keeper / "the-lamp.md"
        lamp.write_text(
            NL.join(["---", "kind: artifact", "id: the-lamp",
                     "  references: [the-cellar]", "---"]) + NL,
            encoding="utf-8", newline="\n")
        report = narrative_index.scan(deep)
        expect("the index reads a hand-written corner of a series", report["ok"],
               str(report["errors"])[:300])
        walked = entity(deep, "rename", "the-cellar", "the-vault")
        expect("a rename reaches a file below the top of its directory",
               walked.returncode == 0, walked.stdout[:300])
        vault = below / "the-vault.md"
        text = vault.read_text(encoding="utf-8") if vault.is_file() else "no file was written"
        expect("a quoted id moves with the file it names", 'id: "the-vault"' in text, text[:200])
        naming = lamp.read_text(encoding="utf-8")
        expect("an indented reference below the top of its directory moves",
               "references: [the-vault]" in naming, naming[:200])
        report = narrative_index.scan(deep)
        expect("the index agrees after a rename it had to walk for", report["ok"],
               str(report["errors"])[:300])

        # A rename that moves the narrative drops the approval over it.
        approved = base / "approved"
        start(approved)
        document = approved / "narrative/narrative.json"
        value = json.loads(document.read_text(encoding="utf-8"))
        value["approved"] = {"by": "a test", "at": "2026-01-01T00:00:00Z",
                             "content_sha256": narrative.content_sha256(value)}
        document.write_text(json.dumps(value, ensure_ascii=False, indent=2) + NL,
                            encoding="utf-8", newline="\n")
        entity(approved, "rename", "c01", "c01-school")
        after = json.loads(document.read_text(encoding="utf-8"))
        expect("a rename drops the narrative's approval", "approved" not in after,
               str(list(after)))

        # A persona is created from the installed current form, headed for the character.
        made = entity(series, "add", "persona", "c02", "--character", "C02",
                      "--name", "The second", "--phase", "school")
        expect("entity add persona succeeds", made.returncode == 0, made.stdout)
        written = series / "narrative/personas/c02.md"
        expect("the persona is written", written.is_file())
        if written.is_file():
            body = written.read_text(encoding="utf-8")
            expect("the persona starts from the form", len(body.splitlines()) > 20,
                   f"{len(body.splitlines())} lines")
            expect("the persona carries front matter", body.startswith("---"), body[:40])
            expect("the persona is headed for the character",
                   "# The second (school)" in body,
                   NL.join(body.splitlines()[:12]))
            expect("the form's own title is not the persona's",
                   "# Persona Template" not in body, body[:400])

        current = entity(series, "add", "persona", "c03", "--character", "C03", "--phase", "current")
        expect("entity add current persona succeeds", current.returncode == 0, current.stdout)
        body = (series / "narrative/personas/c03.md").read_text(encoding="utf-8")
        expect("persona carries identity and authorial bindings",
               "## 2. PORTRAYAL IDENTITY" in body and "**authorial_intent_refs**:" in body,
               "current identity-led full form")

        # Removing something the narrative still names is refused, and forced through.
        removed = entity(series, "remove", "c01")
        expect("entity remove refuses a named persona", removed.returncode != 0, removed.stdout)
        forced = entity(series, "remove", "c01", "--force")
        expect("--force removes it anyway", forced.returncode == 0, forced.stdout)
        expect("--force says what is left naming nothing",
               json.loads(forced.stdout).get("left_dangling"), forced.stdout[:200])

        # Coverage reads the narrative against its scenes and reports the gaps.
        empty = base / "empty"
        start(empty)
        coverage = narrative_coverage.cover(
            empty / "narrative/narrative.json", empty / "narrative/scenes", series=empty)
        expect("coverage runs on a fresh series", coverage["ok"], str(coverage["errors"])[:200])
        expect("coverage reports uncovered chapters", bool(coverage["gaps"]),
               "a series with no scenes should report gaps")
        spawned = run("scripts/narrative_coverage.py", str(empty), "--json")
        expect("coverage runs as a command", spawned.returncode == 0, spawned.stdout[:200])
        strict = run("scripts/narrative_coverage.py", str(empty), "--json", "--strict")
        expect("coverage --strict fails on a gap", strict.returncode != 0, strict.stdout[:200])

        # A scene realized in a kind the series is not made of.
        wrong = base / "wrong"
        start(wrong, "--medium", "comics")
        entity(wrong, "add", "location", "the-boathouse", "--name", "The boathouse")
        (wrong / "narrative/scenes/sc01-plot.json").write_text(
            json.dumps(scene_plot(wrong, "the-boathouse"), ensure_ascii=False, indent=2) + NL,
            encoding="utf-8", newline="\n")
        coverage = narrative_coverage.cover(
            wrong / "narrative/narrative.json", wrong / "narrative/scenes", series=wrong)
        expect("a scene in the wrong kind is refused", not coverage["ok"],
               str(coverage["errors"])[:200])

        # The scenes and the world beside them, read against each other. It is
        # a pair of directions and neither is visible from inside one document:
        # a place written down that no scene uses, and a place a scene happens
        # at that nobody wrote down.
        places = base / "places"
        start(places)
        entity(places, "add", "location", "the-larder", "--name", "The larder")
        (places / "narrative/scenes/sc01-plot.json").write_text(
            json.dumps(scene_plot(places, "a-room-nobody-wrote"),
                       ensure_ascii=False, indent=2) + NL,
            encoding="utf-8", newline="\n")
        coverage = narrative_coverage.cover(
            places / "narrative/narrative.json", places / "narrative/scenes", series=places)
        expect("coverage reports a place no scene happens at",
               any("the-larder" in gap and "no scene happens there" in gap
                   for gap in coverage["gaps"]), str(coverage["gaps"])[:300])
        expect("coverage reports a scene at a place nobody wrote down",
               any("a-room-nobody-wrote" in gap and "no file under" in gap
                   for gap in coverage["gaps"]), str(coverage["gaps"])[:300])

        # Two scenes calling themselves one scene, and a scene written against
        # a narrative this one is not. Both are contradictions between
        # documents rather than faults inside either, so nothing that reads one
        # file at a time can see them.
        contested = base / "contested"
        start(contested)
        entity(contested, "add", "location", "the-boathouse", "--name", "The boathouse")
        plot = scene_plot(contested, "the-boathouse")
        for stem in ("sc01-plot", "sc01-again"):
            (contested / f"narrative/scenes/{stem}.json").write_text(
                json.dumps(plot, ensure_ascii=False, indent=2) + NL,
                encoding="utf-8", newline="\n")
        older = scene_plot(contested, "the-boathouse")
        older["scene_id"] = "sc02"
        older["order"] = 2
        older["narrative_sha256"] = "0" * 64
        (contested / "narrative/scenes/sc02-plot.json").write_text(
            json.dumps(older, ensure_ascii=False, indent=2) + NL,
            encoding="utf-8", newline="\n")
        coverage = narrative_coverage.cover(
            contested / "narrative/narrative.json", contested / "narrative/scenes",
            series=contested)
        expect("a series its scenes contradict is refused", not coverage["ok"],
               str(coverage["errors"])[:200])
        expect("coverage names the second scene claiming the first one's id",
               any("is already used by" in item for item in coverage["errors"]),
               str(coverage["errors"])[:300])
        expect("coverage names the scene written against another narrative",
               any("approve it against what it now says" in item
                   for item in coverage["errors"]), str(coverage["errors"])[:300])

        # A narrative named directly, which is not inside a series directory.
        loose = base / "loose.json"
        shutil.copyfile(empty / "narrative/narrative.json", loose)
        spawned = run("scripts/narrative_coverage.py", str(loose), "--json")
        expect("a narrative outside a series still reads", spawned.returncode == 0,
               spawned.stdout[:200])

        # Which directory the report reads as the series is decided by where
        # the narrative sits and by nothing else. The three cases below are the
        # three answers it can give, and only a series holding something can
        # tell them apart: a place no scene happens at is reported when a
        # series was found and reported by nothing when none was, so these same
        # three cases over an empty series would agree with each other whatever
        # the report decided.
        rooted = base / "rooted"
        start(rooted)
        entity(rooted, "add", "location", "the-larder", "--name", "The larder")

        # Named as the directory: the series is that directory.
        spawned = run("scripts/narrative_coverage.py", str(rooted), "--json")
        expect("a series directory finds its own places",
               any("no scene happens there" in gap
                   for gap in json.loads(spawned.stdout)["gaps"]), spawned.stdout[:300])

        # Named as the file, which sits in `narrative/`: the series is the
        # directory holding that, one level above the narrative.
        spawned = run("scripts/narrative_coverage.py",
                      str(rooted / "narrative/narrative.json"), "--json")
        expect("a narrative inside narrative/ finds the series over it",
               any("no scene happens there" in gap
                   for gap in json.loads(spawned.stdout)["gaps"]), spawned.stdout[:300])

        # And a copy that is only sitting inside a series is not that series's
        # narrative. Walking two levels up from any narrative would adopt the
        # larder over there, which this copy says nothing about.
        aside = rooted / "sub"
        aside.mkdir()
        shutil.copyfile(rooted / "narrative/narrative.json", aside / "loose.json")
        spawned = run("scripts/narrative_coverage.py", str(aside / "loose.json"), "--json")
        expect("a loose narrative under a series still reads", spawned.returncode == 0,
               spawned.stdout[:200])
        expect("and walks out of nothing",
               not any("no scene happens there" in gap
                       for gap in json.loads(spawned.stdout)["gaps"]), spawned.stdout[:300])

        # The second answer again, through a link, which is how one series is
        # assembled out of a store shared with others. The series is the
        # directory holding `narrative/`, and that is the directory the report
        # was given: following the link to wherever the files really sit
        # answers the store's own parent instead, and every check that needs a
        # series is then skipped in silence.
        store = base / "store"
        shutil.copytree(rooted / "narrative", store)
        linked = base / "linked"
        linked.mkdir()
        try:
            os.symlink(store, linked / "narrative", target_is_directory=True)
        except OSError as exc:
            skipped.append(f"a narrative reached through a link: {exc}")
        else:
            spawned = run("scripts/narrative_coverage.py",
                          str(linked / "narrative/narrative.json"), "--json")
            expect("a narrative behind a link finds the series the link sits in",
                   any("no scene happens there" in gap
                       for gap in json.loads(spawned.stdout)["gaps"]), spawned.stdout[:300])

        # What the index refuses in a file somebody wrote by hand, which is
        # every entity file a command did not write. Each of these is a sound
        # file on its own and disagrees with something outside it: the name it
        # is filed under, the directory it sits in, or the rest of the series.
        # None of them is visible to a reader of one file.
        hand = base / "hand"
        start(hand)
        locations = hand / "narrative/world/locations"
        # Made rather than assumed: whether init created it is settled above,
        # and a directory missing here would end this run with a traceback
        # instead of with the failure that was already recorded for it.
        locations.mkdir(parents=True, exist_ok=True)

        def front(kind: str, identifier: str, references: str = "[]") -> str:
            return NL.join(["---", f"kind: {kind}", f"id: {identifier}",
                            f"references: {references}", "---"]) + NL

        (locations / "the-pantry.md").write_text(front("location", "the-larder"),
                                                 encoding="utf-8", newline="\n")
        (locations / "the-yard.md").write_text(front("persona", "the-yard"),
                                               encoding="utf-8", newline="\n")
        (locations / "the-hall.md").write_text(front("location", "the-hall"),
                                               encoding="utf-8", newline="\n")
        (locations / "west").mkdir()
        (locations / "west/the-hall.md").write_text(front("location", "the-hall"),
                                                    encoding="utf-8", newline="\n")
        (locations / "east").mkdir()
        (locations / "east/the-scullery.md").write_text(
            front("location", "the-scullery", "[nothing-wrote-this]"),
            encoding="utf-8", newline="\n")
        report = narrative_index.scan(hand)
        expect("index refuses an id that is not the file name",
               any("the-pantry.md" in item and "the file is named" in item
                   for item in report["errors"]), str(report["errors"])[:300])
        expect("index refuses a file whose kind is not what its directory is for",
               any("the-yard.md" in item and "sits where a" in item
                   for item in report["errors"]), str(report["errors"])[:300])
        # Below the top of the directory, because the coverage report reads the
        # whole tree and two readers that disagree about the depth report one
        # file as present and as missing.
        expect("index reads an entity file below the top of its directory",
               "the-scullery" in report["entities"], str(sorted(report["entities"]))[:300])
        expect("index refuses two files claiming one id",
               any("the-hall" in item and "is already used by" in item
                   for item in report["errors"]), str(report["errors"])[:300])
        expect("index refuses a reference with no file behind it",
               any("nothing-wrote-this" in item and "no file under" in item
                   for item in report["errors"]), str(report["errors"])[:300])

        # An invalid narrative is refused by every command rather than half-read.
        broken = base / "broken"
        start(broken)
        (broken / "narrative/narrative.json").write_text("{}", encoding="utf-8", newline="\n")
        report = narrative_index.scan(broken)
        expect("index refuses an invalid narrative", not report["ok"], str(report)[:200])
        expect("index says the narrative is the cause",
               any("does not answer its contract" in item for item in report["errors"]),
               str(report["errors"])[:200])

        shutil.rmtree(prose, ignore_errors=True)

    print(json.dumps({"ok": not failures, "checks": checks, "skipped": skipped,
                      "failures": failures}, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
