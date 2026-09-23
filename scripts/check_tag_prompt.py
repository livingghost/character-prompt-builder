#!/usr/bin/env python3
"""Read a finished tag rendition back and report what will silently not do what it says.

Usage:
  python scripts/check_tag_prompt.py --dictionary <prompt-vocabulary/dictionary.json>
      --prompt "<the model-facing prompt>" [--negative "<the negative>"]
      [--model <model-id>] [--dialect <dialect-id>] [--dialects <dialects.json>]

The checks are the ones a machine can settle. Each reads the vocabulary resource
rather than a list kept here: a category the resource marks as describing one
figure at a time cannot carry two terms at once, a term that declares what it
opposes cannot sit beside one of them, and a term the resource does not carry is
worth a second look before it is sent.

The rest is the grammar that fails quietly. A numeric weight binds only where the
colon and the number sit immediately before the closing parenthesis; written
anywhere else the digits are consumed as prompt text and can cancel the phrase
they sit in, and nothing in the returned image says so. A repeated tag spends
budget without adding emphasis. A term in both the prompt and the negative is the
prompt arguing with itself. A count tag does not carry across a chunk break, so a
chunk that depicts the subject without one can spawn a second figure.

A model family is checked when `--dialect` names it, or when the `--model` record
names it. Its rating, period and quality terms are read from the prompt-dialects
resource, including where one of them sits inside a longer tag as a word of its
own: `old man` carries the period term `old`.

Judgement stays with the agent: this reports, it does not rewrite. A problem is a
statement about the prompt's own grammar or about a pair the vocabulary itself
calls incompatible; a note is a reading worth confirming.

Output is JSON on stdout; `dialect` names the family checked, or is null. The
exit status is 1 when a problem is reported.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

WEIGHT = re.compile(r"(?<!\\):\s*\d+(?:\.\d+)?")
UNESCAPED = re.compile(r"(?<!\\)[\[\]]")
BREAK = re.compile(r"(?:^|[\s,])BREAK(?:[\s,]|$)")
LONG_NEGATIVE = 30


def load_vocabulary(path: Path) -> dict[str, Any]:
    """Term to category, the categories that describe one figure at a time, and what each term opposes."""

    data = json.loads(path.read_text(encoding="utf-8"))
    category_of: dict[str, str] = {}
    opposes: dict[str, list[str]] = {}
    single_valued: set[str] = set()
    counts: set[str] = set()
    for category in data.get("categories") or []:
        if category.get("single_valued"):
            single_valued.add(category["id"])
        counts.update(normalize(term) for term in (category.get("multiple_figures_terms") or []))
        for entry in category.get("entries") or []:
            for name in [entry["term"], *(entry.get("aliases") or [])]:
                category_of.setdefault(normalize(name), category["id"])
            if entry.get("opposes"):
                opposes[normalize(entry["term"])] = [normalize(row) for row in entry["opposes"]]
    return {"category_of": category_of, "opposes": opposes, "single_valued": single_valued,
            "multiple_figures": counts, "name": data.get("name")}


def normalize(term: str) -> str:
    return re.sub(r"\s+", " ", str(term).replace("_", " ")).strip().casefold()


def bare(tag: str) -> str:
    """The tag without the attention syntax wrapped around it."""

    text = tag.strip()
    while len(text) >= 2 and text[0] in "([{" and text[-1] in ")]}":
        text = text[1:-1].strip()
    text = re.sub(r":\s*\d+(?:\.\d+)?$", "", text).strip()
    return text


def chunks(prompt: str) -> list[list[str]]:
    """The prompt as chunk breaks divide it, each chunk as its comma-separated tags."""

    return [[tag.strip() for tag in part.split(",") if tag.strip()] for part in BREAK.split(prompt)]


def check(prompt: str, negative: str, vocabulary: dict[str, Any], record: dict[str, Any] | None,
          dialect: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    def report(severity: str, check_name: str, message: str, terms: list[str] | None = None) -> None:
        findings.append({"severity": severity, "check": check_name, "message": message, "terms": terms or []})

    positive_chunks = chunks(prompt)
    tags = [tag for chunk in positive_chunks for tag in chunk]
    category_of = vocabulary["category_of"]

    # A tag that is nothing but attention syntax carries no term. It is reported
    # and then set aside: left in, every check below would read the empty string
    # as a term and repeat it as a term the vocabulary does not carry.
    for tag in [tag for tag in tags if not bare(tag)]:
        report("problem", "empty tag", f"{tag!r} carries no term once the attention syntax is removed; remove it", [tag])
    tags = [tag for tag in tags if bare(tag)]

    # A weight that does not sit immediately before the closing parenthesis is
    # read as prompt text, and the image never says so.
    for tag in tags:
        for found in WEIGHT.finditer(tag):
            rest = tag[found.end():].lstrip()
            if not rest.startswith(")"):
                report("problem", "weight binding",
                       f"the weight in {tag!r} does not sit immediately before a closing parenthesis, "
                       "so its digits are read as prompt text", [tag])
        if UNESCAPED.search(tag) and not (tag.strip().startswith("[") and tag.strip().endswith("]")):
            report("note", "bracket", f"{tag!r} carries a square bracket that is not de-emphasis; escape it to mean it literally", [tag])

    seen: dict[str, int] = {}
    for tag in tags:
        key = normalize(bare(tag))
        seen[key] = seen.get(key, 0) + 1
    for term, count in seen.items():
        if count > 1:
            report("problem", "repeated tag", f"{term!r} appears {count} times; reorder or weight it once instead", [term])

    for tag in tags:
        text = bare(tag)
        if text != text.lower() and normalize(text) in category_of:
            report("note", "capitals", f"{text!r} is carried in the vocabulary in lower case", [text])

    # Categories the vocabulary itself marks as describing one figure at a time.
    by_category: dict[str, list[str]] = {}
    for tag in tags:
        key = normalize(bare(tag))
        category = category_of.get(key)
        if category in vocabulary["single_valued"]:
            by_category.setdefault(category, []).append(key)
    # The vocabulary declares which terms put more than one figure in the
    # picture so a checker knows a property named twice is expected there. With
    # two figures, two eye colours are the brief rather than a defect.
    crowded_present = {normalize(bare(tag)) for tag in tags} & vocabulary["multiple_figures"]
    if not crowded_present:
        for category, terms in by_category.items():
            unique = sorted(dict.fromkeys(terms))
            if len(unique) > 1:
                report("problem", "one at a time",
                       f"{category} describes one at a time and carries {len(unique)} terms here", unique)

    present = {normalize(bare(tag)) for tag in tags}
    # A term declares what it opposes; the other side of the pair need not
    # declare the same thing back, so both directions are read and the pair is
    # reported once.
    reported: set[frozenset[str]] = set()
    for term in sorted(present):
        for other in vocabulary["opposes"].get(term, []):
            pair = frozenset({term, other})
            if other in present and pair not in reported:
                reported.add(pair)
                report("problem", "opposed pair", f"{term!r} and {other!r} pull against each other", sorted(pair))

    # The vocabulary names the terms that put more than one figure in the
    # picture. One of those with a single-figure term is a contradiction, and two
    # of them is an unsettled count.
    crowded = sorted(present & vocabulary["multiple_figures"])
    if len(crowded) > 1:
        report("problem", "subject count", f"{len(crowded)} terms each put more than one figure in the picture", crowded)
    if crowded and "solo" in present and frozenset({"solo", crowded[0]}) not in reported:
        report("problem", "subject count", f"solo sits beside {crowded[0]!r}", ["solo", crowded[0]])

    unknown = sorted({normalize(bare(tag)) for tag in tags} - set(category_of))
    if unknown:
        report("note", "not in the vocabulary",
               f"{len(unknown)} terms are not carried by the vocabulary; confirm each is a real term for this target", unknown)

    # A count tag does not carry across a chunk break.
    if len(positive_chunks) > 1:
        counting = vocabulary["multiple_figures"] | {"solo"}
        gated = [index for index, chunk in enumerate(positive_chunks)
                 if any(category_of.get(normalize(bare(tag))) == "subject-count-and-groups"
                        or normalize(bare(tag)) in counting for tag in chunk)]
        if gated:
            for index, chunk in enumerate(positive_chunks):
                if chunk and index not in gated:
                    report("note", "count gating",
                           f"chunk {index + 1} carries no count tag; restate it there if that chunk depicts the subject")

    negative_tags = [tag for chunk in chunks(negative) for tag in chunk] if negative else []
    for tag in [tag for tag in negative_tags if not bare(tag)]:
        report("problem", "empty tag", f"{tag!r} carries no term once the attention syntax is removed; remove it", [tag])
    negative_tags = [tag for tag in negative_tags if bare(tag)]
    if negative_tags:
        both = sorted({normalize(bare(tag)) for tag in negative_tags} & present)
        for term in both:
            report("problem", "in both", f"{term!r} is in the prompt and in the negative", [term])
        if len(negative_tags) > LONG_NEGATIVE:
            report("note", "negative length",
                   f"the negative carries {len(negative_tags)} terms; past about {LONG_NEGATIVE} it turns unpredictable")

    # What the active family carries, and what it never learned.
    if dialect is not None:
        for field, label in (("rating_terms", "rating"), ("period_terms", "period")):
            carried = sorted(present & {normalize(term) for term in dialect.get(field) or []})
            if len(carried) > 1:
                report("problem", f"{label} term",
                       f"{len(carried)} {label} terms from the {dialect['id']} family, which takes one", carried)
        inert = sorted(present & {normalize(term) for term in dialect.get("inert_terms") or []})
        if inert:
            report("problem", "inert term",
                   f"the {dialect['id']} family never learned these, so they spend budget and steer nothing", inert)
        # A family term can act from inside a longer tag. Words split at spaces
        # only: an underscore spelling, which a family may use to bind a tag
        # whole, reads as one word.
        family_terms: dict[str, str] = {}
        for field, label in (("rating_terms", "rating"), ("period_terms", "period"), ("quality_terms", "quality")):
            for term in dialect.get(field) or []:
                family_terms.setdefault(normalize(term), label)
        for tag in tags:
            words = bare(tag).casefold().split()
            for term, label in family_terms.items():
                inner = term.split()
                if len(inner) < len(words) and any(words[i:i + len(inner)] == inner
                                                   for i in range(len(words) - len(inner) + 1)):
                    report("note", "family term inside a tag",
                           f"{bare(tag)!r} carries {term!r}, a {label} term of the {dialect['id']} family, "
                           "which can act on its own there; spell the tag as the family's multi_word_tags says, "
                           "or confirm the reading", [bare(tag), term])
        low, high = (dialect.get("weight_range") or [None, None])[:2] or (None, None)
        if low is not None:
            for tag in tags:
                for found in WEIGHT.finditer(tag):
                    value = float(found.group(0).lstrip(":").strip())
                    if value > 1 and not (low <= value <= high):
                        report("note", "weight range",
                               f"{tag!r} weights outside the {low} to {high} the {dialect['id']} family works in", [tag])

    if record is not None:
        limit = record.get("max_positive_prompt_chars")
        if isinstance(limit, int) and len(prompt) > limit:
            report("problem", "length", f"the prompt is {len(prompt)} characters and the record's limit is {limit}")
        limit = record.get("max_negative_prompt_chars")
        if negative and isinstance(limit, int) and len(negative) > limit:
            report("problem", "length", f"the negative is {len(negative)} characters and the record's limit is {limit}")
        if negative and record.get("supports_negative_prompt") is False:
            report("problem", "negative transport", "the record declares no negative channel for this model")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dictionary", required=True, type=Path, help="A prompt-vocabulary dictionary.json")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--negative", default="")
    parser.add_argument("--model", help="A model record, to check the rendition against its declared limits and its family")
    parser.add_argument("--dialect", help="A model family by its id, for a family with no model record")
    parser.add_argument("--dialects", help="A prompt-dialects JSON file, instead of the active pack's")
    args = parser.parse_args(argv)
    if not args.dictionary.is_file():
        raise SystemExit(f"{args.dictionary} is not a file")
    record = None
    dialect_id = args.dialect
    if args.model:
        from prepare_generation_references import resolve_model_record

        model_id, record = resolve_model_record(args.model)
        named = record.get("prompt_dialect")
        if args.dialect and named and named != args.dialect:
            raise SystemExit(f"model record {model_id!r} names the {named!r} family, not {args.dialect!r}")
        dialect_id = dialect_id or named
    dialect = None
    if dialect_id:
        from pack_manager import PackError
        from prompt_dialect import find_dialect, resolve_resource

        try:
            path = resolve_resource("prompt-dialects", args.dialects, state_file=None, cache_dir=None,
                                    managed_root=None, required=bool(args.dialect))
            dialect = find_dialect(dialect_id, path) if path is not None else None
        except PackError as exc:
            raise SystemExit(str(exc)) from None
    findings = check(args.prompt, args.negative, load_vocabulary(args.dictionary), record, dialect)
    problems = [row for row in findings if row["severity"] == "problem"]
    print(json.dumps({"ok": not problems, "problems": len(problems), "notes": len(findings) - len(problems),
                      "dialect": dialect["id"] if dialect else None, "findings": findings},
                     ensure_ascii=False, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
