#!/usr/bin/env python3
"""Check that this side's scene plot reader reaches the verdict each rule is for.

The contract is published in `references/narrative-protocol.md`, and every rule
it states has a case here, so a rule that stops firing is caught by the case
written for it rather than by a count that still adds up.

Each case here changes one thing in a plot that answers the contract and names
the fragment the message has to carry.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from scene_plot import content_sha256, validate_scene_plot  # noqa: E402

# The narrative this plot was written against. The reader checks the shape of
# the hash; whether it is the narrative's current one is the coverage report's
# question, because that needs the narrative.
NARRATIVE = "a" * 64


def plot() -> dict[str, Any]:
    """A scene plot that answers the contract, for a case to change one thing in."""

    return {
        "artifact_type": "scene-plot",
        "scene_id": "sc01",
        "narrative_sha256": NARRATIVE,
        "chapter": "ch1",
        "order": 1,
        "arcs": ["a1"],
        "characters": ["C01", "C02"],
        "themes": ["t1"],
        "focalization": {"kind": "internal", "through": "C02"},
        "setting": {
            "interior_exterior": "interior",
            "location": "riverside-boathouse",
            "where": "at the bench, the hatch behind him",
            "time_of_day": "early, before either of them has spoken",
            "season": "the first cold week",
            "weather": "clear and still",
        },
        "scene_function": "entry",
        "delivery_role": "chapter_opening",
        "proposition": ("From a shared boathouse before either of them speaks, one of them lights "
                        "a second lantern, leaving the morning admitted rather than said."),
        "turn": {"value": "what is admitted between them",
                 "from": "unspoken", "to": "set burning on the bench"},
        "structure": {"profile": "kishotenketsu",
                      "parts": {"ki": "b1", "sho": "b2", "ten": "b3", "ketsu": "b4"}},
        "beats": [
            {"id": "b1", "beat": "He lifts one lantern down.", "visibility": "visible"},
            {"id": "b2", "beat": "He fills the oil for more than one.", "visibility": "visible"},
            {"id": "b3", "beat": "He lights a second lantern beside the first.", "visibility": "visible",
             "teaches": ["audience"]},
            {"id": "b4", "beat": "He leaves it burning and goes.", "visibility": "visible"},
            {"id": "b5", "beat": "The other one is still asleep up the ladder.",
             "visibility": "context"},
        ],
        "exchanges": [],
        "placement": [
            {"statement": "he stands at the bench, the lanterns in front of him", "from": ["b1"]},
        ],
        "must_preserve": [
            {"statement": "the linen shirt and the leather apron", "from": ["b1"]},
        ],
        "free": [{"statement": "what hangs on the far wall"}],
        "state_changes": [
            {"target": "the second lantern", "change": "it is lit on the bench", "from": ["b3"]},
        ],
        "relationship_delta": [
            {"channel": "initiates-contact", "between": ["C01", "C02"],
             "change": "he moves first, without being asked", "from": ["b3"]},
        ],
        "realization": {
            "kind": "shots",
            "units": [
                {"id": "sc01-m01", "focal_beat": "b1",
                 "shows": [{"statement": "one lantern coming down from the hook", "from": ["b1"]}],
                 "composition": [{"statement": "from the hatch, waist level", "from": ["b1"]}]},
                {"id": "sc01-m02", "focal_beat": "b2",
                 "shows": [{"statement": "the oil filling past one measure", "from": ["b2"]}],
                 "composition": [{"statement": "close on the oil line", "from": ["b2"]}]},
                {"id": "sc01-m03", "focal_beat": "b3",
                 "shows": [{"statement": "two lanterns side by side", "from": ["b3"]}],
                 "composition": [{"statement": "the bench across frame", "from": ["b3"]}]},
                {"id": "sc01-m04", "focal_beat": "b4",
                 "shows": [{"statement": "the hatch, empty, the lanterns still burning",
                            "from": ["b4"]}],
                 "composition": [{"statement": "held wide from the same hatch", "from": ["b4"]}]},
            ],
        },
    }


def approve(value: dict[str, Any]) -> dict[str, Any]:
    value["approved"] = {"by": "the case author", "at": "2026-09-11T00:00:00Z",
                         "content_sha256": content_sha256(value)}
    return value


def changed(**edits: Any) -> dict[str, Any]:
    value = plot()
    value.update(copy.deepcopy(edits))
    return value


def dropped(key: str) -> dict[str, Any]:
    value = plot()
    value.pop(key, None)
    return value


def setting(**edits: Any) -> dict[str, Any]:
    value = plot()
    value["setting"].update(copy.deepcopy(edits))
    return value


def without_setting(key: str) -> dict[str, Any]:
    value = plot()
    value["setting"].pop(key, None)
    return value


def unit(index: int, **edits: Any) -> dict[str, Any]:
    value = plot()
    value["realization"]["units"][index].update(copy.deepcopy(edits))
    return value


def realized(kind: str, units: list[dict[str, Any]]) -> dict[str, Any]:
    return changed(realization={"kind": kind, "units": units})


PAGES = [
    {"id": "p1", "focal_beat": "b1", "panels": 4,
     "shows": [{"statement": "one lantern coming down", "from": ["b1"]}]},
    {"id": "p2", "focal_beat": "b2", "panels": 3,
     "shows": [{"statement": "the oil filling past one measure", "from": ["b2"]}]},
    {"id": "p3", "focal_beat": "b3", "panels": 1, "spread": True, "ends_on_turn": True,
     "shows": [{"statement": "two lanterns side by side", "from": ["b3"]}]},
    {"id": "p4", "focal_beat": "b4", "panels": 5,
     "shows": [{"statement": "the empty doorway", "from": ["b4"]}]},
]
PASSAGES = [
    {"id": "s1", "focal_beat": "b1", "mode": "scene",
     "covers": [{"statement": "the reach for the hook", "from": ["b1"]}]},
    {"id": "s2", "focal_beat": "b2", "mode": "summary",
     "covers": [{"statement": "the morning to that point", "from": ["b2"]}]},
    {"id": "s3", "focal_beat": "b3", "mode": "scene",
     "covers": [{"statement": "the second lantern lit beside the first", "from": ["b3"]}]},
    {"id": "s4", "focal_beat": "b4", "mode": "scene",
     "covers": [{"statement": "the leaving", "from": ["b4"]}]},
]

CASES: list[dict[str, Any]] = [
    {"name": "the contract answered", "value": plot(), "error": None},
    {"name": "an unknown key", "value": changed(notes="something"), "error": "unknown keys"},
    {"name": "the plot names a target", "value": changed(target="some-interface"),
     "error": "the interface is chosen after it"},
    {"name": "the plot names a model", "value": changed(model="some-model"),
     "error": "the interface is chosen after it"},
    {"name": "the wrong artifact type", "value": changed(artifact_type="prompt-plot"),
     "error": "artifact_type must be 'scene-plot'"},
    {"name": "no scene id", "value": changed(scene_id="  "),
     "error": "scene_id must be a non-empty string"},
    {"name": "no chapter", "value": dropped("chapter"),
     "error": "chapter must be a non-empty string"},

    # The narrative this was approved against.
    {"name": "no narrative hash", "value": dropped("narrative_sha256"),
     "error": "narrative_sha256 must be the content hash of the narrative"},
    {"name": "a narrative hash that is not a hash", "value": changed(narrative_sha256="recent"),
     "error": "narrative_sha256 must be the content hash of the narrative"},

    # Where the scene falls in its chapter.
    {"name": "no place in the chapter", "value": dropped("order"),
     "error": "order must be this scene's place in its chapter, from 1"},
    {"name": "a place before the first", "value": changed(order=0),
     "error": "order must be this scene's place in its chapter, from 1"},

    {"name": "no declared arc", "value": changed(arcs=[]), "error": None},
    {"name": "no characters", "value": dropped("characters"),
     "error": "characters must be an array naming who is in this scene"},
    {"name": "an empty character id", "value": changed(characters=["C01", "  "]),
     "error": "characters[1] must be a non-empty string"},

    # Which of the series' themes the scene carries.
    {"name": "no themes", "value": dropped("themes"),
     "error": "themes must be an array naming the declared themes this scene carries"},
    {"name": "an empty theme id", "value": changed(themes=["  "]),
     "error": "themes[0] must be a non-empty string"},

    # How the scene is told.
    {"name": "no focalization", "value": dropped("focalization"),
     "error": "focalization must say how this scene is told"},
    {"name": "a focalization of no known kind",
     "value": changed(focalization={"kind": "limited"}),
     "error": "focalization.kind must be one of"},
    {"name": "internal focalization through nobody",
     "value": changed(focalization={"kind": "internal"}),
     "error": "focalization.through must name the character this scene is restricted to"},
    {"name": "zero focalization through somebody",
     "value": changed(focalization={"kind": "zero", "through": "C01"}),
     "error": "does not belong to zero focalization"},
    {"name": "external focalization staying with somebody",
     "value": changed(focalization={"kind": "external", "through": "C01"}), "error": None},
    {"name": "zero focalization", "value": changed(focalization={"kind": "zero"}), "error": None},
    {"name": "told through somebody the scene does not contain",
     "value": changed(focalization={"kind": "internal", "through": "C09"}),
     "error": "focalization.through names 'C09', who the scene does not say is in it"},

    # Where and when.
    {"name": "no setting at all", "value": dropped("setting"),
     "error": "setting must say where and when this scene happens"},
    {"name": "a setting with an unknown key", "value": setting(mood="quiet"),
     "error": "setting has unknown keys: ['mood']"},
    {"name": "a setting that does not say inside or out",
     "value": without_setting("interior_exterior"),
     "error": "setting.interior_exterior must be one of"},
    {"name": "a place that is not an id", "value": setting(location="the boathouse, sort of"),
     "error": "setting.location must be the id of a place"},
    {"name": "a setting that says where but not when", "value": without_setting("time_of_day"),
     "error": "setting.time_of_day must be a non-empty string"},
    {"name": "a setting that names the place and not the part of it used",
     "value": setting(where="  "), "error": "setting.where must be a non-empty string"},
    {"name": "a season the series does not turn on, left unsaid",
     "value": changed(setting={key: item for key, item in plot()["setting"].items()
                               if key not in ("season", "weather")}),
     "error": None},
    {"name": "a scene context outside the project",
     "value": setting(scene_context="../elsewhere.json"),
     "error": "setting.scene_context must be a path inside the project"},
    {"name": "a scene context in the project",
     "value": setting(scene_context="state/scene-contexts/sc01.json"), "error": None},

    {"name": "a scene function of no known kind", "value": changed(scene_function="middle"),
     "error": None},
    {"name": "a delivery role of no known kind", "value": changed(delivery_role="teaser"),
     "error": None},
    {"name": "no proposition", "value": dropped("proposition"),
     "error": "proposition must be a non-empty string"},

    # What is different at the end.
    {"name": "an omitted turn", "value": dropped("turn"), "error": None},
    {"name": "a turn with no value",
     "value": changed(turn={"from": "unspoken", "to": "said"}),
     "error": "turn.value must be a non-empty string"},
    {"name": "a turn that ends where it began",
     "value": changed(turn={"value": "what is admitted", "from": "unspoken", "to": "unspoken"}),
     "error": None},
    {"name": "a turn with an unknown key",
     "value": changed(turn={**plot()["turn"], "polarity": "positive"}),
     "error": "turn has unknown keys: ['polarity']"},

    # The tradition the series works in, declared rather than assumed.
    {"name": "no declared structure, which is allowed", "value": dropped("structure"),
     "error": None},
    {"name": "a structure of no known profile",
     "value": changed(structure={"profile": "hero-journey", "parts": {}}),
     "error": "structure.parts must be a non-empty map"},
    {"name": "a profile missing one of its parts",
     "value": changed(structure={"profile": "kishotenketsu",
                                 "parts": {"ki": "b1", "sho": "b2", "ten": "b3"}}),
     "error": None},
    {"name": "a profile naming a part it does not have",
     "value": changed(structure={"profile": "kishotenketsu",
                                 "parts": {"ki": "b1", "sho": "b2", "ten": "b3", "ketsu": "b4",
                                           "crisis": "b1"}}),
     "error": None},
    {"name": "a part naming a beat that does not exist",
     "value": changed(structure={"profile": "kishotenketsu",
                                 "parts": {"ki": "b9", "sho": "b2", "ten": "b3", "ketsu": "b4"}}),
     "error": "structure.parts.ki names a beat that does not exist: 'b9'"},
    {"name": "the five commandments, which is another tradition",
     "value": changed(structure={"profile": "five-commandments",
                                 "parts": {"inciting_incident": "b1",
                                           "progressive_complication": "b2",
                                           "crisis": "b3", "climax": "b3", "resolution": "b4"}}),
     "error": None},

    {"name": "no beats", "value": changed(beats=[]), "error": "beats must be a non-empty array"},
    {"name": "two beats with one id",
     "value": changed(beats=[plot()["beats"][0], {**plot()["beats"][1], "id": "b1"}]),
     "error": "repeats 'b1'"},
    {"name": "a beat that is neither visible nor context",
     "value": changed(beats=[{**plot()["beats"][0], "visibility": "implied"},
                             *plot()["beats"][1:]]),
     "error": "visibility must be one of"},
    {"name": "a context beat that teaches somebody",
     "value": changed(beats=[*plot()["beats"][:4],
                             {**plot()["beats"][4], "teaches": ["C02"]}]),
     "error": "a beat the scene does not show teaches nobody"},

    # What is said, and what saying it accomplishes.
    {"name": "an exchange that accomplishes nothing",
     "value": changed(exchanges=[{"id": "e1", "between": ["C01", "C02"],
                                  "about": "the second lantern", "from": ["b3"]}]),
     "error": "exchanges[0].achieves must be a non-empty string"},
    {"name": "an exchange with somebody the scene does not contain",
     "value": changed(exchanges=[{"id": "e1", "between": ["C01", "C09"],
                                  "about": "the second lantern", "achieves": "he is answered",
                                  "from": ["b3"]}]),
     "error": "names 'C09', who the scene does not say is in it"},
    {"name": "an exchange said in no beat",
     "value": changed(exchanges=[{"id": "e1", "between": ["C01", "C02"],
                                  "about": "the second lantern", "achieves": "he is answered"}]),
     "error": "exchanges[0].from must name the beat this is said in"},
    {"name": "an exchange said in a beat the scene does not show",
     "value": changed(exchanges=[{"id": "e1", "between": ["C01", "C02"],
                                  "about": "the second lantern", "achieves": "he is answered",
                                  "from": ["b5"]}]),
     "error": "cannot put anything in a frame"},
    {"name": "a scene where nobody speaks", "value": dropped("exchanges"), "error": None},
    {"name": "an exchange with no id",
     "value": changed(exchanges=[{"between": ["C01", "C02"],
                                  "about": "the second lantern", "achieves": "he is answered",
                                  "from": ["b3"]}]),
     "error": "exchanges[0].id must be a non-empty string"},
    {"name": "two exchanges that carry one id",
     "value": changed(exchanges=[{"id": "e1", "between": ["C01", "C02"],
                                  "about": "the second lantern", "achieves": "he is answered",
                                  "from": ["b3"]},
                                 {"id": "e1", "between": ["C01", "C02"],
                                  "about": "the bench", "achieves": "he sits down",
                                  "from": ["b3"]}]),
     "error": "exchanges[1].id repeats 'e1'"},
    {"name": "an exchange said twice in one beat",
     "value": changed(exchanges=[{"id": "e1", "between": ["C01", "C02"],
                                  "about": "the second lantern", "achieves": "he is answered",
                                  "from": ["b3", "b3"]}]),
     "error": "exchanges[0].from repeats a beat id"},
    {"name": "an exchange that lands",
     "value": changed(exchanges=[{"id": "e1", "between": ["C01", "C02"],
                                  "about": "the second lantern", "achieves": "he is answered rather "
                                  "than accommodated", "from": ["b3"]}]),
     "error": None},

    {"name": "a statement from a beat that does not exist",
     "value": changed(placement=[{"statement": "he is at the bench", "from": ["b9"]}]),
     "error": "names a beat that does not exist: 'b9'"},
    {"name": "a statement from a context beat",
     "value": changed(placement=[{"statement": "he is at the bench", "from": ["b5"]}]),
     "error": "cannot put anything in a frame"},
    {"name": "a statement that repeats its source",
     "value": changed(placement=[{"statement": "he is at the bench", "from": ["b1", "b1"]}]),
     "error": "repeats a beat id"},
    {"name": "a free statement that claims a source",
     "value": changed(free=[{"statement": "the weather", "from": ["b1"]}]),
     "error": "free[0] has unknown keys: ['from']"},
    {"name": "no placement at all", "value": changed(placement=[]),
     "error": "placement must be a non-empty array"},
    {"name": "nothing said about what the scene preserves", "value": dropped("must_preserve"),
     "error": "must_preserve must be a non-empty array"},
    {"name": "a state change from a beat that does not exist",
     "value": changed(state_changes=[{"target": "C01", "change": "it moved",
                                      "from": ["b99"]}]),
     "error": "state_changes[0].from names a beat that does not exist"},
    {"name": "a state change that names no beat",
     "value": changed(state_changes=[{"target": "C01", "change": "it moved"}]),
     "error": "state_changes[0].from must name the beat"},
    {"name": "a state change whose beat id is not a string",
     "value": changed(state_changes=[{"target": "C01", "change": "it moved", "from": [7]}]),
     "error": "state_changes[0].from contains a non-string beat id"},
    {"name": "a relationship move from a beat that does not exist",
     "value": changed(relationship_delta=[{"channel": "eye-contact", "between": ["C01", "C02"],
                                           "change": "it moved", "from": ["b99"]}]),
     "error": "relationship_delta[0].from names a beat that does not exist"},
    {"name": "a relationship move that names no beat",
     "value": changed(relationship_delta=[{"channel": "eye-contact", "between": ["C01", "C02"],
                                           "change": "it moved"}]),
     "error": "relationship_delta[0].from must name the beat"},
    {"name": "nothing said about what the scene leaves behind", "value": dropped("state_changes"),
     "error": "state_changes must be an array of persistent consequences"},
    {"name": "a state change that names no target",
     "value": changed(state_changes=[{"target": "  ", "change": "it moved", "from": ["b3"]}]),
     "error": "state_changes[0].target must be a non-empty string"},
    {"name": "a relationship change on no known channel",
     "value": changed(relationship_delta=[{"channel": "warmth", "between": ["C01", "C02"],
                                           "change": "it grew", "from": ["b3"]}]),
     "error": None},
    {"name": "a relationship change naming somebody the scene does not contain",
     "value": changed(relationship_delta=[{"channel": "eye-contact", "between": ["C01", "C09"],
                                           "change": "he looks up", "from": ["b3"]}]),
     "error": "names 'C09', who the scene does not say is in it"},
    {"name": "a relationship change between one person",
     "value": changed(relationship_delta=[{"channel": "eye-contact", "between": ["C01"],
                                           "change": "he looks up", "from": ["b3"]}]),
     "error": "between must name at least two characters"},

    # What the scene becomes, in the parts the medium actually has.
    {"name": "no realization", "value": dropped("realization"),
     "error": "realization must say what this scene becomes"},
    {"name": "a realization of no known kind",
     "value": changed(realization={"kind": "episodes", "units": []}),
     "error": "realization.kind must be one of"},
    {"name": "a realization with no units",
     "value": changed(realization={"kind": "shots", "units": []}),
     "error": "realization.units must be a non-empty array of shots"},
    {"name": "a unit with no id", "value": unit(0, id="  "),
     "error": "realization.units[0].id must be a non-empty string"},
    {"name": "two units with one id", "value": unit(1, id="sc01-m01"),
     "error": "realization.units[1].id repeats 'sc01-m01'"},
    {"name": "a unit that carries no beat", "value": unit(0, focal_beat="  "),
     "error": "focal_beat must name the beat this shot carries"},
    {"name": "a unit carrying a beat that does not exist", "value": unit(0, focal_beat="b9"),
     "error": "names a beat that does not exist: 'b9'"},
    {"name": "a unit carrying a beat the scene does not show",
     "value": unit(0, focal_beat="b5"), "error": "cannot put anything in a frame"},
    {"name": "a shot that shows nothing", "value": unit(0, shows=[]),
     "error": "realization.units[0].shows must be a non-empty array"},
    {"name": "a shot with no composition", "value": unit(0, composition=[]),
     "error": "realization.units[0].composition must be a non-empty array"},
    {"name": "a shot with a key shots do not have", "value": unit(0, panels=4),
     "error": "has keys 'shots' does not have: ['panels']"},

    {"name": "a scene realized as pages", "value": realized("pages", PAGES), "error": None},
    {"name": "a page with no panel count",
     "value": realized("pages", [{**PAGES[0], "panels": None}, *PAGES[1:]]),
     "error": "panels must be how many panels this page holds, from 1"},
    {"name": "a page turn that is not a yes or a no",
     "value": realized("pages", [{**PAGES[0], "ends_on_turn": "maybe"}, *PAGES[1:]]),
     "error": "ends_on_turn must be true or false"},
    {"name": "a page with a key pages do not have",
     "value": realized("pages", [{**PAGES[0], "composition": []}, *PAGES[1:]]),
     "error": "has keys 'pages' does not have: ['composition']"},

    {"name": "a scene realized as passages", "value": realized("passages", PASSAGES),
     "error": None},
    {"name": "a passage that does not say whether it is shown or told",
     "value": realized("passages", [{**PASSAGES[0], "mode": None}, *PASSAGES[1:]]),
     "error": "mode must be one of ['scene', 'summary']"},
    {"name": "a passage that covers nothing",
     "value": realized("passages", [{**PASSAGES[0], "covers": []}, *PASSAGES[1:]]),
     "error": "realization.units[0].covers must be a non-empty array"},

    {"name": "a visible beat nothing takes anything from",
     "value": changed(beats=[*plot()["beats"],
                             {"id": "b6", "beat": "The radio is on.", "visibility": "visible"}]),
     "error": "is marked visible but nothing takes anything from it"},
]

# The approval is reported apart from the contract, so a caller can tell an
# invalid plot from an unapproved one.
APPROVAL_CASES: list[dict[str, Any]] = [
    {"name": "an approval that holds", "value": approve(plot()), "approved": True, "error": None},
    {"name": "an approval that is not an object",
     "value": {**plot(), "approved": "yesterday"},
     "approved": False, "error": "approved must be an object"},
    {"name": "no approval at all", "value": plot(), "approved": False, "error": None},
    {"name": "an approval with a loose time",
     "value": {**plot(), "approved": {"by": "someone", "at": "yesterday",
                                      "content_sha256": "0" * 64}},
     "approved": False, "error": "must be an RFC3339 UTC timestamp"},
    {"name": "an approval that names nobody",
     "value": {**plot(), "approved": {"by": "  ", "at": "2026-09-11T00:00:00Z",
                                      "content_sha256": "0" * 64}},
     "approved": False, "error": "approved.by must be a non-empty string"},
    {"name": "an approval with no content hash",
     "value": {**plot(), "approved": {"by": "someone", "at": "2026-09-11T00:00:00Z"}},
     "approved": False, "error": "must be the sha256 of the plot without its approval"},
    {"name": "an approval with an unknown key",
     "value": {**plot(), "approved": {"by": "someone", "at": "2026-09-11T00:00:00Z",
                                      "content_sha256": "0" * 64, "scope": "all"}},
     "approved": False, "error": "approved has unknown keys"},
]


def beat(index: int, **edits: Any) -> dict[str, Any]:
    value = plot()
    value["beats"][index].update(copy.deepcopy(edits))
    return value


# One case per refusal the reader can make that no other case names, so that
# deleting the refusal turns a case red.
UNNAMED_CASES: list[dict[str, Any]] = [
    {"name": "a plot that is not an object", "value": "not an object",
     "error": "scene plot root must be an object"},
    {"name": "a beat that is not an object",
     "value": changed(beats=[*plot()["beats"], "not an object"]),
     "error": "beats[5] must be an object"},
    {"name": "a beat that teaches nobody", "value": beat(2, teaches=[]),
     "error": ".teaches must be a non-empty array of who learns here"},
    {"name": "a placement with nothing in it", "value": changed(placement=[]),
     "error": "must be a non-empty array; where there is nothing to say"},
    {"name": "a placement entry that is not an object",
     "value": changed(placement=["not an object"]),
     "error": "placement[0] must be an object"},
    {"name": "a placement entry that follows from no beat",
     "value": changed(placement=[{"statement": "he stands at the bench", "from": []}]),
     "error": ".from must name at least one beat"},
    {"name": "a scene context that names nothing", "value": setting(scene_context="  "),
     "error": "setting.scene_context must name a scene context snapshot"},
    {"name": "a structure that is not an object", "value": changed(structure="kishotenketsu"),
     "error": "structure must be an object naming a profile and its parts"},
    {"name": "structure parts that are not named",
     "value": changed(structure={"profile": "kishotenketsu", "parts": ["b1", "b2"]}),
     "error": "structure.parts must be a non-empty map"},
    {"name": "a unit that is not an object",
     "value": realized("shots", [*plot()["realization"]["units"], "not an object"]),
     "error": "realization.units[4] must be an object"},
    {"name": "exchanges that are not an array", "value": changed(exchanges="none"),
     "error": "exchanges must be an array of what is said"},
    {"name": "an exchange that is not an object", "value": changed(exchanges=["not an object"]),
     "error": "exchanges[0] must be an object"},
    {"name": "an exchange between nobody",
     "value": changed(exchanges=[{"id": "x1", "between": [], "about": "the lantern",
                                  "achieves": "nothing yet", "from": ["b1"]}]),
     "error": ".between must name who is speaking"},
    {"name": "a state change that is not an object",
     "value": changed(state_changes=["not an object"]),
     "error": "state_changes[0] must be an object"},
    {"name": "a relationship delta that is not an array",
     "value": changed(relationship_delta="none"),
     "error": "relationship_delta must be an array"},
    {"name": "a relationship move that is not an object",
     "value": changed(relationship_delta=["not an object"]),
     "error": "relationship_delta[0] must be an object"},
]


# A supported observation does not need a fabricated cast or event.
from world_coherence_smoke_test import observational_scene  # noqa: E402

CASES.append({"name": "unpeopled observation with no turn or persistent change",
              "value": observational_scene(), "error": None})
for _bad_turn in (None, "none", []):
    _observation = observational_scene(); _observation["turn"] = _bad_turn
    CASES.append({"name": f"present malformed turn {_bad_turn!r}", "value": _observation,
                  "error": "turn must be an object when supplied"})
_observation = observational_scene()
_observation["turn"] = {"value": "water", "from": "still", "to": "still"}
CASES.append({"name": "unpeopled explicit persistence", "value": _observation, "error": None})
for _field in ("arcs", "themes", "characters", "state_changes"):
    _missing = observational_scene(); _missing.pop(_field)
    CASES.append({"name": f"observation still requires {_field} array", "value": _missing,
                  "error": f"{_field} must be an array"})

CASES.append({'name': 'authored structure with no prescribed tradition',
              'value': changed(structure={'profile': 'held-and-revisited', 'parts': {'held': 'b1', 'revisited': 'b2'}}),
              'error': None})
for _field in ('scene_function', 'delivery_role'):
    for _invalid in ('', None, [], {}):
        CASES.append({'name': _field + ' needs authored text ' + repr(_invalid),
                      'value': changed(**{_field: _invalid}), 'error': _field + ' must be a non-empty string'})


def main() -> int:
    failures: list[str] = []
    results: list[dict[str, Any]] = []

    for case in CASES:
        report = validate_scene_plot(case["value"])
        joined = "; ".join(report["errors"])
        expected = case["error"]
        results.append({"case": case["name"], "ok": report["ok"], "errors": report["errors"]})
        if expected is None:
            if not report["ok"]:
                failures.append(f"{case['name']}: expected no error, got {joined}")
        elif expected not in joined:
            failures.append(f"{case['name']}: expected {expected!r}, got {joined or 'no error'}")

    for case in UNNAMED_CASES:
        report = validate_scene_plot(case["value"])
        joined = "; ".join(report["errors"])
        results.append({"case": case["name"], "ok": report["ok"], "errors": report["errors"]})
        if case["error"] not in joined:
            failures.append(
                f"{case['name']}: expected {case['error']!r}, got {joined or 'no error'}"
            )

    for case in APPROVAL_CASES:
        report = validate_scene_plot(case["value"])
        name = f"approval: {case['name']}"
        joined = "; ".join(report["approval_errors"])
        expected = case["error"]
        results.append({"case": name, "approved": report["approved"],
                        "approval_errors": report["approval_errors"]})
        if expected is None:
            if report["approval_errors"]:
                failures.append(f"{name}: expected no approval error, got {joined}")
        elif expected not in joined:
            failures.append(f"{name}: expected {expected!r}, got {joined or 'no error'}")
        if report["approved"] != case["approved"]:
            failures.append(f"{name}: expected approved={case['approved']}, got {report['approved']}")

    # An approval binds the bytes it was given, and an edit after it breaks it.
    signed = approve(plot())
    edited = copy.deepcopy(signed)
    edited["beats"][0]["beat"] = "Something else entirely happens."
    report = validate_scene_plot(edited)
    results.append({"case": "approval: an edit after the approval", "approved": report["approved"]})
    if report["approved"]:
        failures.append("approval: an edit after the approval still held")
    if not any("changed after it was approved" in item for item in report["approval_errors"]):
        failures.append(f"approval: an edit after the approval reported {report['approval_errors']}")

    # A submission is a shot, so the gate finds shot ids where the scene becomes
    # shots and none where it becomes pages or prose.
    for kind, units, expected in (("shots", None, 4), ("pages", PAGES, 0),
                                  ("passages", PASSAGES, 0)):
        value = plot() if units is None else realized(kind, units)
        report = validate_scene_plot(value)
        results.append({"case": f"shot ids of a scene realized as {kind}",
                        "shots": report["shots"], "units": report["units"]})
        if report["shots"] != expected:
            failures.append(
                f"shot ids of a scene realized as {kind}: expected {expected}, got {report['shots']}"
            )
        if report["units"] != 4:
            failures.append(f"units of a scene realized as {kind}: got {report['units']}")

    # What a caller reads back is what the plot actually carries.
    report = validate_scene_plot(plot())
    counted = {
        "beats": report["beats"], "visible_beats": report["visible_beats"],
        "units": report["units"], "realization": report["realization"],
        "chapter": report["chapter"], "order": report["order"], "arcs": report["arcs"],
        "characters": report["characters"], "themes": report["themes"],
        "focalization": report["focalization"], "narrative_sha256": report["narrative_sha256"],
        "location": report["setting"].get("location"), "exchanges": report["exchanges"],
        "scene_statements": report["scene_statements"], "state_changes": report["state_changes"],
        "relationship_delta": report["relationship_delta"],
    }
    results.append({"case": "what the report counts", **counted})
    expected_counts = {
        "beats": 5, "visible_beats": 4, "units": 4, "realization": "shots",
        "chapter": "ch1", "order": 1, "arcs": ["a1"], "characters": ["C01", "C02"],
        "themes": ["t1"], "focalization": {"kind": "internal", "through": "C02"},
        "narrative_sha256": NARRATIVE, "location": "riverside-boathouse", "exchanges": 0,
        "scene_statements": 3, "state_changes": 1, "relationship_delta": 1,
    }
    if counted != expected_counts:
        failures.append(f"what the report counts: got {counted}")

    print(json.dumps({
        "ok": not failures,
        "checks": len(results),
        "results": results,
        "errors": failures,
    }, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
