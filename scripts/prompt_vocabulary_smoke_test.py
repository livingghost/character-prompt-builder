#!/usr/bin/env python3
"""Self-contained regression checks for prompt-vocabulary validation and search."""
from __future__ import annotations

import contextlib
import copy
import io
import json
import tempfile
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch

from prompt_retrieval import main as retrieval_main, mark_outcome, validate_prompt_retrieval_record
from search_prompt_vocabulary import (
    VocabularyError,
    list_categories,
    load_vocabulary,
    main as search_main,
    read_prompt,
    search_vocabularies,
    tokens,
    validate_vocabulary,
)


COMMONS_DICTIONARY = Path(__file__).resolve().parents[1] / "packs/commons/resources/prompt-vocabulary/dictionary.json"


def ranking_fixture() -> dict[str, Any]:
    """Synthetic entries where a word match competes with a longer, weaker one."""
    return {
        "format": "character-prompt-builder-prompt-vocabulary",
        "name": "Synthetic Ranking Vocabulary",
        "description": "Fictional data used only by the regression test.",
        "categories": [
            {"id": "knitwear", "name": "Knitwear", "description": "Knitted garments.", "entries": [
                {"term": "aran sweater", "description": "A wool sweater covered in raised cable and braid knit panels."},
            ]},
            {"id": "devices", "name": "Devices", "description": "Electronics.", "entries": [
                {"term": "charger cable", "aliases": ["charger_cable"], "description": "A cable for charging a device."},
                {"term": "oil can", "description": "A can with a long spout."},
            ]},
            {"id": "faces", "name": "Faces", "description": "Expressions.", "entries": [
                {"term": "pouting lips"},
                {"term": "pout"},
            ]},
        ],
    }


def words_of(row: Any, *, description: bool = True) -> set[str]:
    return set(tokens(" ".join([row.term, *row.aliases, row.description if description and row.description else ""])))


def fixture() -> dict[str, Any]:
    return {
        "format": "character-prompt-builder-prompt-vocabulary",
        "name": "Synthetic Prompt Vocabulary",
        "description": "Fictional data used only by the regression test.",
        "categories": [
            {
                "id": "camera",
                "name": "Camera",
                "description": "Camera and viewpoint vocabulary.",
                "entries": [
                    {"term": "low angle", "aliases": ["worm's-eye view"], "description": "A camera view from below the subject."},
                    {"term": "close-up"},
                    {"term": ";D", "description": "A distinct punctuation-bearing expression cue used by the fixture."},
                    {"term": ":D"},
                ],
            },
            {
                "id": "lighting",
                "name": "Lighting",
                "description": "Lighting vocabulary.",
                "entries": [
                    {"term": "soft light", "description": "Diffuse illumination with gentle shadow transitions."}
                ],
            },
            {
                "id": "eye-colors",
                "name": "Eye Colors",
                "description": "Iris colour vocabulary; one figure carries one of these.",
                "single_valued": True,
                "entries": [
                    {"term": "blue eyes", "description": "A blue iris."},
                    {"term": "green eyes", "description": "A green iris."},
                ],
            },
            {
                "id": "eye-states",
                "name": "Eye States",
                "description": "Whether the eyes are open, and how.",
                "entries": [
                    {
                        "term": "closed eyes",
                        "description": "The eyelids are shut, so no iris colour is drawn.",
                        "opposes": ["blue eyes", "green eyes"],
                    },
                ],
            },
            {
                "id": "subject-count",
                "name": "Subject Count",
                "description": "How many figures stand in the picture.",
                "multiple_figures_terms": ["2girls"],
                "entries": [
                    {"term": "solo", "description": "One figure alone."},
                    {"term": "2girls", "description": "Two figures."},
                ],
            },
        ],
    }


def expect_error(fn: Callable[[], Any]) -> bool:
    try:
        fn()
    except VocabularyError:
        return True
    return False


def check_model_wording_command(root: Path, add: Callable) -> None:
    """One public invocation obtains model guidance and searches only when required."""
    from model_prompt_input_fixtures import prompt_input
    import prompt_vocabulary_selection as selection

    root.mkdir()
    prompt = root / 'prompt.txt'
    prompt.write_text('low angle', encoding='utf-8')
    original = {'artifact_type': 'prompt-retrieval-record', 'elements': [{
        'element': 'staging', 'queries': ['shared support'], 'inspected_records': [],
        'outcome': 'unused', 'reason': 'The request supplies complete staging.'}]}
    raw = (json.dumps(original, separators=(', ', ': ')) + '\n\n').encode('utf-8')
    record = root / 'lookups.json'
    record.write_bytes(raw)
    model_file = root / 'model.json'
    runtime = ['--state-file', str(root / 'state.json'), '--cache-dir', str(root / 'cache'),
               '--managed-root', str(root / 'managed')]

    def choose(mode, *, forms=None):
        model = {'id': 'synthetic-' + mode, 'prompt_input': prompt_input(mode,
            vocabularies=('synthetic-vocabulary',) if mode == 'tag-based' else (), forms=forms)}
        if mode == 'tag-based':
            model['prompt_dialect'] = 'synthetic-family'
        model_file.write_text(json.dumps(model), encoding='utf-8')

    def invoke(*options):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = retrieval_main([str(record), '--model-file', str(model_file),
                                   '--prompt-file', str(prompt), *options, *runtime])
        return code, json.loads(output.getvalue())

    dictionary = root / 'dictionary.json'
    dictionary.write_text(json.dumps(fixture()), encoding='utf-8')
    dialects = root / 'dialects.json'
    dialects.write_text(json.dumps({'format': 'character-prompt-builder-prompt-dialects',
        'name': 'Synthetic command family', 'description': 'Local command test evidence.',
        'dialects': [{'id': 'synthetic-family', 'name': 'Synthetic family',
            'description': 'The fixture uses comma-separated vocabulary.',
            'vocabularies': ['synthetic-vocabulary'], 'tag_separator': 'comma and space',
            'block_order': ['content', 'optional controls']}]}), encoding='utf-8')
    choose('tag-based')
    acquire = selection._resources
    with patch.object(selection, '_resources', side_effect=lambda model, **kwargs:
            acquire(model, dictionary_path=dictionary, dialect_path=dialects)):
        code, report = invoke('--search-vocabulary')
    searched_raw = record.read_bytes()
    searched = json.loads(searched_raw)
    receipt = report.get('vocabulary') or {}
    add('one model-bound wording command performs the required actual tag search',
        code == 0 and report.get('vocabulary_searched') is True
        and report.get('prompt_authoring', {}).get('vocabulary', {}).get('required') is True
        and receipt.get('entries', [{}])[0].get('searches', [{}])[0].get('query') == 'low angle'
        and receipt.get('entries', [{}])[0].get('choice', {}).get('kind') == 'dictionary'
        and searched['elements'] == original['elements'] and searched.get('vocabulary') == receipt,
        report)

    choose('tag-based', forms=('tags', 'natural-language'))
    record.write_bytes(raw)
    with patch.object(selection, '_resources', side_effect=lambda model, **kwargs:
            acquire(model, dictionary_path=dictionary, dialect_path=dialects)):
        mixed_code, mixed_report = invoke('--search-vocabulary')
    mixed_plan = mixed_report.get('prompt_authoring', {})
    mixed_receipt = mixed_report.get('vocabulary') or {}
    add('the same command derives mixed wording availability and required lookup from the model definition',
        mixed_code == 0 and mixed_report.get('vocabulary_searched') is True
        and mixed_plan.get('preferred_wording') == 'tags'
        and mixed_plan.get('available_wording') == ['tags', 'natural-language', 'mixed']
        and mixed_plan.get('vocabulary', {}).get('required') is True
        and mixed_receipt.get('entries', [{}])[0].get('searches', [{}])[0].get('query') == 'low angle'
        and mixed_receipt.get('entries', [{}])[0].get('choice', {}).get('kind') == 'dictionary'
        and json.loads(record.read_bytes())['elements'] == original['elements'], mixed_report)

    for mode in ('descriptive', 'unresolved'):
        choose(mode)
        record.write_bytes(raw)
        with patch.object(selection, '_resources', side_effect=AssertionError('unexpected vocabulary acquisition')):
            code, report = invoke('--search-vocabulary')
            copied = root / (mode + '-copy.json')
            copy_code, copied_report = invoke('--search-vocabulary', '--out', str(copied))
            settled = root / (mode + '-settled.json')
            settle_code, settled_report = invoke('--settle', '--out', str(settled))
        add(mode + ' uses the same wording command without lookup or record changes',
            code == 0 and report.get('vocabulary') is None and report.get('vocabulary_searched') is False
            and report.get('prompt_authoring', {}).get('vocabulary', {}).get('required') is False
            and record.read_bytes() == raw and copy_code == 0 and copied.read_bytes() == raw
            and copied_report.get('vocabulary_searched') is False,
            report)
        add(mode + ' wording can settle without a model-format classification step',
            settle_code == 0 and settled_report.get('ok') is True
            and json.loads(settled.read_text(encoding='utf-8'))['elements'] == original['elements']
            and 'vocabulary' not in json.loads(settled.read_text(encoding='utf-8')), settled_report)

    choose('descriptive')
    record.write_bytes(searched_raw)
    with patch.object(selection, '_resources', side_effect=AssertionError('unexpected vocabulary acquisition')):
        code, report = invoke('--search-vocabulary')
    add('a prior vocabulary receipt survives an unrelated model selection as unused evidence',
        code == 0 and record.read_bytes() == searched_raw and report.get('vocabulary') is None
        and report.get('retained_vocabulary') == {
            'used_for_selected_model': False, 'model': 'synthetic-tag-based'}, report)
    record.write_bytes(raw)
    code, report = invoke('--retain-wording', 'low angle', '--reason', 'Keep the commissioned viewpoint.')
    add('retaining wording still requires a real previous search',
        code != 0 and record.read_bytes() == raw
        and any('run --search-vocabulary before --retain-wording' in error for error in report['errors']), report)

    choose('none')
    with patch.object(selection, '_resources', side_effect=AssertionError('unexpected vocabulary acquisition')):
        code, report = invoke('--search-vocabulary')
    add('the shared wording command preserves the declared absence of a text surface',
        code != 0 and record.read_bytes() == raw
        and any('no text prompt surface' in error for error in report['errors']), report)


def main() -> int:
    value = fixture()
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: Any = None) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    add("valid synthetic vocabulary passes validation", validate_vocabulary(value) is value)
    exact = search_vocabularies([value], "low angle", limit=1)
    add("exact term search ranks the exact term first", bool(exact and exact[0].term == "low angle"), [r.as_json() for r in exact])
    alias = search_vocabularies([value], "worm's-eye view", limit=1)
    add("alias search resolves the canonical term", bool(alias and alias[0].term == "low angle"), [r.as_json() for r in alias])
    close = search_vocabularies([value], "close-up", limit=1)
    add("entry descriptions are optional and omitted when absent", bool(close and close[0].description is None), [r.as_json() for r in close])
    desc = search_vocabularies([value], "diffuse illumination", limit=1)
    add("description text participates in retrieval", bool(desc and desc[0].term == "soft light"), [r.as_json() for r in desc])
    filtered = search_vocabularies([value], "angle", category_filters=["Camera"])
    add("category filters return matching rows and exclude unrelated categories", bool(filtered and all(r.category == "Camera" for r in filtered)), [r.as_json() for r in filtered])
    punctuation = search_vocabularies([value], ";D", limit=5)
    add("punctuation-bearing terms remain distinct and searchable", bool(punctuation and punctuation[0].term == ";D" and all(r.term != ":D" for r in punctuation)), [r.as_json() for r in punctuation])
    categories = list_categories([value])
    add("category listing is deterministic", [r["name"] for r in categories] == ["Camera", "Eye Colors", "Eye States", "Lighting", "Subject Count"], categories)
    add("distinct punctuation-bearing terms pass uniqueness validation", validate_vocabulary(copy.deepcopy(value)) is not None)
    dup = copy.deepcopy(value); dup["categories"][0]["entries"].append({"term": "LOW ANGLE"})
    add("duplicate terms in one category are rejected", expect_error(lambda: validate_vocabulary(dup)))
    bad_alias = copy.deepcopy(value); bad_alias["categories"][0]["entries"][0]["aliases"] = ["Low Angle"]
    add("an alias cannot repeat its canonical term", expect_error(lambda: validate_vocabulary(bad_alias)))
    with tempfile.TemporaryDirectory(prefix="cpb-prompt-vocabulary-") as temp:
        path = Path(temp) / "dictionary.json"
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        add("a UTF-8 dictionary round-trips through the file loader", load_vocabulary(path) == value)
        record = Path(temp) / "lookups.json"
        with contextlib.redirect_stdout(io.StringIO()):
            code = search_main(["low angle", "--dictionary", str(path), "--limit", "1",
                                "--record", str(record), "--element", "camera"])
        recorded = json.loads(record.read_text(encoding="utf-8")) if record.is_file() else None
        add("a recorded search appends its query and returned terms in the catalog lookup shape",
            code == 0 and recorded == {"artifact_type": "prompt-retrieval-record", "elements": [
                {"element": "camera", "queries": ["low angle"], "inspected_records": ["low angle"]}]}, recorded)
        marked = recorded and mark_outcome(recorded, "camera", adopted="low angle")
        add("a returned term can be marked adopted",
            bool(marked) and validate_prompt_retrieval_record(marked)["ok"], marked)

        single, many = Path(temp) / "single.json", Path(temp) / "many.json"
        queries = {"camera": ["low angle", "close-up"], "lighting": "soft light"}
        with contextlib.redirect_stdout(io.StringIO()):
            for element, query in (("camera", "low angle"), ("camera", "close-up"), ("lighting", "soft light")):
                search_main([query, "--dictionary", str(path), "--record", str(single), "--element", element])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = search_main(["--dictionary", str(path), "--queries", json.dumps(queries), "--record", str(many)])
        report = json.loads(output.getvalue())
        add("one run answers several queries and records each under its element exactly as single searches do",
            code == 0 and many.read_text(encoding="utf-8") == single.read_text(encoding="utf-8")
            and [(row["element"], row["query"]) for row in report["searches"]]
            == [("camera", "low angle"), ("camera", "close-up"), ("lighting", "soft light")],
            report)
        repeated = Path(temp) / "repeated.json"
        with contextlib.redirect_stdout(io.StringIO()):
            code = search_main(["--dictionary", str(path), "--record", str(repeated),
                                "--queries", '{"camera": ["low angle"], "camera": ["close-up"]}'])
        add("a queries object that names one element twice is refused before anything is recorded",
            code == 2 and not repeated.exists())

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = retrieval_main([str(many), "--element", "camera", "--adopted", "low angle", "--adopted", "close-up"])
        report = json.loads(output.getvalue())
        kept = json.loads(many.read_text(encoding="utf-8"))["elements"][0].get("adopted_records")
        add("several --adopted records for one element are all kept",
            code == 0 and kept == ["low angle", "close-up"]
            and report["marked"]["adopted_records"] == ["low angle", "close-up"], report)
        add("remaining work names the element rather than its position",
            len(report["remaining"]) == 1
            and "element 'lighting' has no outcome" in report["remaining"][0]
            and "--unused REASON" in report["remaining"][0],
            report["remaining"])

        failed_record = Path(temp) / "failed-lookup.json"
        with contextlib.redirect_stdout(io.StringIO()):
            code = search_main(["local construction", "--dictionary", str(Path(temp) / "missing-dictionary.json"),
                                "--record", str(failed_record), "--element", "construction"])
        failed_value = json.loads(failed_record.read_text(encoding="utf-8"))
        failed_report = validate_prompt_retrieval_record(failed_value)
        add("a failed needed vocabulary lookup remains an unfinished investigation",
            code == 2 and failed_value["elements"] == [
                {"element": "construction", "queries": [], "inspected_records": []}]
            and not failed_report["ok"]
            and any("has no outcome" in error for error in failed_report["errors"]), failed_report)

        check_model_wording_command(Path(temp) / 'model-wording', add)

    ranking = ranking_fixture()
    knit = search_vocabularies([ranking], "cable knit")
    add("an entry holding every query word ranks above entries holding one of them",
        [row.term for row in knit] == ["aran sweater", "charger cable"], [r.as_json() for r in knit])
    pout = search_vocabularies([ranking], "pout")
    add("a query matches whole words, so 'pout' finds 'pouting' and not the 'spout' of a description",
        [row.term for row in pout] == ["pout", "pouting lips"], [r.as_json() for r in pout])

    commons = [load_vocabulary(COMMONS_DICTIONARY)]
    solo = search_vocabularies(commons, "solo", limit=40)
    named = ["solo" in words_of(row, description=False) for row in solo]
    add("commons 'solo': the exact term first, and every term naming solo above entries that only mention it",
        bool(solo) and solo[0].term == "solo" and named == sorted(named, reverse=True),
        [r.as_json() for r in solo[:8]])
    cable = search_vocabularies(commons, "cable knit", limit=40)
    both = [{"cable", "knit"} <= words_of(row) for row in cable]
    add("commons 'cable knit': entries holding both words rank above entries holding one",
        bool(cable) and both[0] and both == sorted(both, reverse=True), [r.as_json() for r in cable[:8]])
    literal = copy.deepcopy(value)
    literal['categories'][3]['entries'].append({
        'term': '[edition:2025]', 'description': 'A printed edition label including brackets and its year.'})
    reading = read_prompt([literal], '[edition:2025], closed eyes')
    add('literal punctuation and numeric content remain part of the lookup phrase',
        reading['text'][0]['written'] == '[edition:2025]'
        and reading['text'][0]['term'] == '[edition:2025]'
        and reading['text'][0]['definitions'][0]['entry'] == literal['categories'][3]['entries'][-1], reading)
    add('dictionary opposition remains complete source evidence',
        reading['text'][1]['definitions'][0]['entry'] == value['categories'][3]['entries'][0], reading)
    repeated = read_prompt([value], "blue eyes, green eyes")
    add(
        "each authored property receives its own dictionary evidence",
        [row["definitions"][0]["entry"]["description"] for row in repeated["text"]]
        == ["A blue iris.", "A green iris."],
        repeated,
    )
    crowded = read_prompt([value], "2girls, blue eyes, green eyes")
    add(
        "multiple-figure guidance remains attached to the dictionary definition",
        crowded["text"][0]["definitions"][0]["category_definition"]["multiple_figures_terms"] == ["2girls"],
        crowded["text"][0],
    )
    alone = read_prompt([value], "solo, blue eyes, green eyes")
    add(
        "scene scope does not change retrieved property definitions",
        alone["text"][1:] == crowded["text"][1:],
        alone,
    )
    alternate = copy.deepcopy(value)
    alternate["name"] = "Second authored dictionary"
    alternate["categories"][2]["entries"][0].update({
        "description": "A second source's description of blue eyes.",
        "usage_notes": ["Review subject-specific markings."],
        "part": "eyes", "hides": ["upper iris"], "fragile_at_close_scale": True,
    })
    evidence = read_prompt([value, alternate], "blue eyes, an unlisted term", "blue eyes")
    definitions = evidence["text"][0]["definitions"]
    add("multiple dictionary definitions and all authored entry fields survive lookup",
        len(definitions) == 2 and definitions[1]["entry"] == alternate["categories"][2]["entries"][0]
        and definitions[0]["entry"] == value["categories"][2]["entries"][0], definitions)
    add("overlapping channels retain equal dictionary evidence without a semantic verdict",
        evidence["negative"][0]["definitions"] == definitions and set(evidence) == {"text", "negative"}, evidence)
    add("unlisted text remains visible without inferred meaning",
        evidence["text"][1]["known"] is False and evidence["text"][1]["definitions"] == []
        and evidence["text"][1]["written"] == "an unlisted term", evidence["text"][1])

    forbidden = {"source", "source_id", "source_section", "disposition", "blocked_from_search", "requires_review"}
    fields = {key for category in value["categories"] for entry in category["entries"] for key in entry}
    add("the fixture contains no per-entry provenance or policy-control fields", not bool(fields & forbidden), sorted(fields & forbidden))

    output = {"ok": all(row["passed"] for row in checks), "checks": len(checks), "results": checks}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["ok"] else 1


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
