#!/usr/bin/env python3
"""Validate and search one or more CPB prompt-vocabulary resources.

The dictionary supplies candidate wording. The calling agent remains
responsible for selecting, combining, adapting, or ignoring every result.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from state_protocol import unsupported_schema_keywords, validate_against_schema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "prompt-vocabulary.schema.json"


class VocabularyError(ValueError):
    """Raised when a prompt-vocabulary resource violates its contract."""


@dataclass(frozen=True)
class SearchRow:
    term: str
    category_id: str
    category: str
    aliases: tuple[str, ...]
    description: str | None
    score: int

    def as_json(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "term": self.term,
            "category_id": self.category_id,
            "category": self.category,
            "score": self.score,
        }
        if self.aliases:
            value["aliases"] = list(self.aliases)
        if self.description:
            value["description"] = self.description
        return value


def normalize_identity(value: str) -> str:
    """Normalize case and spacing while retaining meaningful punctuation."""
    value = unicodedata.normalize("NFKC", value).casefold()
    value = value.replace("\u2018", "'").replace("\u2019", "'")
    value = value.replace("\u201c", '"').replace("\u201d", '"')
    value = value.replace("\u2013", "-").replace("\u2014", "-")
    return re.sub(r"\s+", " ", value).strip()


def normalize_lexical(value: str) -> str:
    value = normalize_identity(value)
    value = re.sub(r"[^a-z0-9{}]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _stem_token(token: str) -> str:
    if len(token) > 4 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokens(value: str) -> tuple[str, ...]:
    result: list[str] = []
    for token in normalize_lexical(value).split():
        if len(token) < 2:
            continue
        result.append(_stem_token(token))
    return tuple(dict.fromkeys(result))


def load_schema() -> dict[str, Any]:
    value = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise VocabularyError("prompt-vocabulary schema must be a JSON object")
    unsupported = unsupported_schema_keywords(value)
    if unsupported:
        raise VocabularyError(
            "prompt-vocabulary schema contains unsupported keywords: "
            + ", ".join(unsupported)
        )
    return value


def validate_vocabulary(value: Any, *, path: Path | None = None) -> dict[str, Any]:
    label = str(path) if path is not None else "prompt vocabulary"
    if not isinstance(value, dict):
        raise VocabularyError(f"{label} must contain a JSON object")
    errors = validate_against_schema(value, load_schema())
    if errors:
        raise VocabularyError(f"{label} failed schema validation: " + "; ".join(errors))

    category_ids: set[str] = set()
    category_names: set[str] = set()
    for category_index, category in enumerate(value["categories"]):
        category_id = str(category["id"])
        category_name = normalize_identity(str(category["name"]))
        if category_id in category_ids:
            raise VocabularyError(f"{label} contains duplicate category id {category_id!r}")
        if category_name in category_names:
            raise VocabularyError(f"{label} contains duplicate category name {category['name']!r}")
        category_ids.add(category_id)
        category_names.add(category_name)

        term_keys: set[str] = set()
        for entry_index, entry in enumerate(category["entries"]):
            key = normalize_identity(str(entry["term"]))
            if not key:
                raise VocabularyError(
                    f"{label} categories[{category_index}].entries[{entry_index}] normalizes to an empty term"
                )
            if key in term_keys:
                raise VocabularyError(
                    f"{label} category {category_id!r} contains duplicate term {entry['term']!r}"
                )
            term_keys.add(key)
            alias_keys: set[str] = set()
            for alias in entry.get("aliases") or []:
                alias_key = normalize_identity(str(alias))
                if not alias_key:
                    raise VocabularyError(f"{label} category {category_id!r} contains an empty alias")
                if alias_key == key:
                    raise VocabularyError(
                        f"{label} category {category_id!r} repeats term {entry['term']!r} as an alias"
                    )
                if alias_key in alias_keys:
                    raise VocabularyError(
                        f"{label} category {category_id!r} contains duplicate alias {alias!r}"
                    )
                alias_keys.add(alias_key)
    return value


def load_vocabulary(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve(strict=True)
    if resolved.is_symlink() or not resolved.is_file():
        raise VocabularyError(f"dictionary must be a regular file: {path}")
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VocabularyError(f"cannot read prompt vocabulary {path}: {exc}") from exc
    return validate_vocabulary(value, path=resolved)


def _words(value: str) -> str:
    """Lexical words with plural and -ing endings removed, padded for whole-word tests."""
    return " " + " ".join(_stem_token(word) for word in normalize_lexical(value).split()) + " "


@dataclass(frozen=True)
class _Entry:
    row: SearchRow
    term_identity: str
    term_words: str
    alias_identities: tuple[str, ...]
    alias_words: tuple[str, ...]
    description_words: str
    term_tokens: frozenset[str]
    alias_tokens: frozenset[str]
    description_tokens: frozenset[str]
    category_tokens: frozenset[str]
    category_identity: str
    category_lexical: str


@dataclass(frozen=True)
class _Query:
    identity: str
    words: str
    tokens: frozenset[str]


def _entry_score(query: _Query, entry: _Entry) -> int:
    """Rank one entry: the term itself first, then whole words, then partial matches.

    Each tier outranks every lower tier. A phrase counts only on word boundaries,
    so "pout" finds "pouting" and not "spout". Within a tier, query words found in
    the term count most and words found only in the description least.
    """

    phrase = query.words if len(query.words.strip()) >= 2 else ""
    inside = query.identity if len(query.identity) >= 2 else ""
    term_and_alias = entry.term_tokens | entry.alias_tokens
    every_field = term_and_alias | entry.description_tokens
    if query.identity == entry.term_identity:
        tier = 1000
    elif phrase and phrase == entry.term_words:
        tier = 980
    elif query.identity in entry.alias_identities or (phrase and phrase in entry.alias_words):
        tier = 950
    elif phrase and entry.term_words.startswith(phrase):
        tier = 900
    elif phrase and phrase in entry.term_words:
        tier = 880
    elif phrase and any(phrase in alias for alias in entry.alias_words):
        tier = 850
    elif query.tokens and query.tokens <= entry.term_tokens:
        tier = 800
    elif query.tokens and query.tokens <= term_and_alias:
        tier = 780
    elif inside and inside in entry.term_identity:
        tier = 700
    elif inside and any(inside in alias for alias in entry.alias_identities):
        tier = 680
    elif phrase and phrase in entry.description_words:
        tier = 600
    elif query.tokens and query.tokens <= every_field:
        tier = 500
    else:
        found = query.tokens & every_field
        if not found:
            return 0
        tier = 100 + 380 * len(found) // len(query.tokens)
    bonus = (4 * len(query.tokens & entry.term_tokens)
             + 2 * len(query.tokens & (entry.alias_tokens - entry.term_tokens))
             + len(query.tokens & entry.description_tokens)
             + (1 if query.tokens & entry.category_tokens else 0))
    return tier + min(bonus, 19)


class VocabularyIndex:
    """Dictionaries prepared once, so one process answers many searches."""

    def __init__(self, vocabularies: Iterable[Mapping[str, Any]]) -> None:
        self.entries: list[_Entry] = []
        for vocabulary in vocabularies:
            for category in vocabulary["categories"]:
                category_identity = normalize_identity(
                    f"{category['id']} {category['name']} {category['description']}"
                )
                category_lexical = normalize_lexical(category_identity)
                category_tokens = frozenset(tokens(category_lexical))
                for entry in category["entries"]:
                    aliases = tuple(str(v) for v in entry.get("aliases") or [])
                    description = str(entry["description"]) if entry.get("description") else None
                    term_tokens = frozenset(tokens(str(entry["term"])))
                    self.entries.append(_Entry(
                        row=SearchRow(term=str(entry["term"]), category_id=str(category["id"]),
                                      category=str(category["name"]), aliases=aliases,
                                      description=description, score=0),
                        term_identity=normalize_identity(str(entry["term"])),
                        term_words=_words(str(entry["term"])),
                        alias_identities=tuple(normalize_identity(v) for v in aliases),
                        alias_words=tuple(_words(v) for v in aliases),
                        description_words=_words(description or ""),
                        term_tokens=term_tokens,
                        alias_tokens=frozenset(tokens(" ".join(aliases))) - term_tokens,
                        description_tokens=frozenset(tokens(description or "")),
                        category_tokens=category_tokens,
                        category_identity=category_identity,
                        category_lexical=category_lexical,
                    ))

    @staticmethod
    def _category_matches(entry: _Entry, filters: Sequence[str]) -> bool:
        for raw in filters:
            identity_filter = normalize_identity(raw)
            lexical_filter = normalize_lexical(raw)
            if identity_filter and identity_filter in entry.category_identity:
                continue
            if lexical_filter and lexical_filter in entry.category_lexical:
                continue
            return False
        return True

    def search(self, query: str, *, category_filters: Sequence[str] = (), limit: int = 20) -> list[SearchRow]:
        identity = normalize_identity(query)
        if not identity:
            raise VocabularyError("query must not be empty")
        if type(limit) is not int or limit < 1:
            raise VocabularyError("limit must be a positive integer")
        prepared = _Query(identity=identity, words=_words(query), tokens=frozenset(tokens(query)))
        scored: list[tuple[int, int, str, str, SearchRow]] = []
        for entry in self.entries:
            if category_filters and not self._category_matches(entry, category_filters):
                continue
            score = _entry_score(prepared, entry)
            if score > 0:
                row = entry.row
                scored.append((-score, len(entry.term_words.split()), entry.term_identity,
                               row.category_id, row))
        scored.sort(key=lambda item: item[:4])
        return [SearchRow(term=row.term, category_id=row.category_id, category=row.category,
                          aliases=row.aliases, description=row.description, score=-negative)
                for negative, _, _, _, row in scored[:limit]]


def search_vocabularies(
    vocabularies: Iterable[Mapping[str, Any]],
    query: str,
    *,
    category_filters: Sequence[str] = (),
    limit: int = 20,
) -> list[SearchRow]:
    return VocabularyIndex(vocabularies).search(query, category_filters=category_filters, limit=limit)


def list_categories(vocabularies: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for vocabulary in vocabularies:
        for category in vocabulary["categories"]:
            key = (str(category["id"]), normalize_identity(str(category["name"])))
            rows[key] = {
                "id": str(category["id"]),
                "name": str(category["name"]),
                "description": str(category["description"]),
                "entry_count": len(category["entries"]),
            }
    return [rows[k] for k in sorted(rows, key=lambda k: (k[1], k[0]))]


def _term_index(vocabularies: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for vocabulary in vocabularies:
        for category in vocabulary.get("categories") or []:
            for entry in category.get("entries") or []:
                record = {
                    "category": category.get("id"),
                    "term": entry.get("term"),
                    "description": entry.get("description"),
                    "single_valued": bool(category.get("single_valued")),
                    "fragile_at_close_scale": bool(entry.get("fragile_at_close_scale")),
                    "opposes": [normalize_identity(str(x)) for x in entry.get("opposes") or []],
                }
                index.setdefault(normalize_identity(str(entry.get("term") or "")), record)
                for alias in entry.get("aliases") or []:
                    index.setdefault(normalize_identity(str(alias)), record)
    return index


def _split_terms(text: str) -> list[tuple[str, int | None]]:
    """Split a written prompt into terms in reading order, brackets included.

    A word inside square brackets still reaches the model, so it is returned
    rather than discarded. One bracketed run is one choice group and carries a
    group number; every term outside brackets carries ``None``. Numeric
    fragments of the scheduling syntax (``[from:to:0.4]``) are dropped, because
    they are timing rather than wording.
    """

    results: list[tuple[str, int | None]] = []
    group = 0
    for piece in re.split(r"(\[[^\]]*\])", text.replace("\n", ",")):
        if not piece:
            continue
        if piece.startswith("[") and piece.endswith("]"):
            group += 1
            for fragment in re.split(r"[|:]", piece[1:-1]):
                written = fragment.strip()
                if not written or re.fullmatch(r"[0-9.]+", written):
                    continue
                results.append((written, group))
            continue
        for fragment in piece.split(","):
            written = fragment.strip()
            if written:
                results.append((written, None))
    return results


def _bare_term(written: str) -> tuple[str, str | None]:
    """A written tag reduced to the term, with its weight if one was applied."""
    weight = None
    match = re.search(r":\s*([0-9.]+)\s*\)?$", written)
    if match and written.lstrip().startswith("("):
        weight = match.group(1)
    term = written.strip()
    term = re.sub(r"^\(+|\)+$", "", term)
    term = re.sub(r":\s*[0-9.]+$", "", term)
    return normalize_identity(term.replace("_", " ")), weight


def read_prompt(vocabularies: Sequence[Mapping[str, Any]], text: str, negative: str = "") -> dict[str, Any]:
    """Walk a finished prompt term by term and say what each term draws.

    The dictionary is what a prompt is checked against before it is sent: a term it
    knows comes back with the category and the description of what it draws, so the
    writer confirms the picture they meant against the picture the word makes; a term
    it does not know comes back marked, since that is where the writer is on their own.
    The notices are the statements the text makes against itself: a weight on a term
    the dictionary does not know, which is force without binding; a term written in the
    primary field and the negative field at once; one single-valued property named
    twice; a pair recorded as opposing; and a part these models draw badly asked for at
    close scale.
    """

    index = _term_index(vocabularies)
    close_terms: set[str] = set()
    multiple_figures: set[str] = set()
    for vocabulary in vocabularies:
        for category in vocabulary.get("categories") or []:
            for term in category.get("close_scale_terms") or []:
                close_terms.add(normalize_identity(str(term)))
            for term in category.get("multiple_figures_terms") or []:
                multiple_figures.add(normalize_identity(str(term)))

    def rows_for(source: str) -> list[dict[str, Any]]:
        rows = []
        for written, group in _split_terms(source):
            term, weight = _bare_term(written)
            hit = index.get(term)
            rows.append({
                "written": written,
                "term": term,
                "group": group,
                "weight": weight,
                "known": hit is not None,
                "category": (hit or {}).get("category"),
                "description": (hit or {}).get("description"),
            })
        return rows

    text_rows = rows_for(text)
    negative_rows = rows_for(negative) if negative else []
    notices: list[str] = []

    weighted_unknown = [row["term"] for row in text_rows if row["weight"] and not row["known"]]
    if weighted_unknown:
        notices.append(
            "weight on a term the dictionary does not know: " + ", ".join(weighted_unknown)
            + "; a weight raises the term's tokens without binding them to the thing meant")

    negative_terms = {row["term"] for row in negative_rows}
    both = [row["term"] for row in text_rows if row["term"] in negative_terms]
    for term in dict.fromkeys(both):
        notices.append("asked for and asked against: " + term)

    by_category: dict[str, list[str]] = {}
    counted_groups: set[tuple[str, int]] = set()
    for row in text_rows:
        hit = index.get(row["term"])
        if hit and hit["single_valued"]:
            category_id = str(hit["category"])
            group = row["group"]
            # One bracketed run is one choice, so its alternatives are one
            # value of the property rather than the property named twice.
            if group is not None:
                if (category_id, group) in counted_groups:
                    continue
                counted_groups.add((category_id, group))
            by_category.setdefault(category_id, [])
            if row["term"] not in by_category[category_id]:
                by_category[category_id].append(row["term"])
    # The dictionary declares which terms put more than one figure in the
    # picture. Two figures carry two eye colours, so a property named twice is
    # what was asked for rather than a defect to report.
    crowded = [row["term"] for row in text_rows if row["term"] in multiple_figures]
    if not crowded:
        for category_id, terms in by_category.items():
            if len(terms) > 1:
                notices.append("one property named twice (" + category_id + "): " + ", ".join(terms))

    present = [row["term"] for row in text_rows]
    seen_pairs: set[tuple[str, str]] = set()
    for row in text_rows:
        hit = index.get(row["term"])
        for other in (hit or {}).get("opposes") or []:
            pair = tuple(sorted((row["term"], other)))
            if other in present and pair not in seen_pairs:
                seen_pairs.add(pair)
                notices.append("terms that cannot both hold: " + pair[0] + " and " + pair[1])

    fragile = [row["term"] for row in text_rows if (index.get(row["term"]) or {}).get("fragile_at_close_scale")]
    close = [term for term in present if term in close_terms]
    if fragile and close:
        notices.append("parts drawn badly at this scale: " + ", ".join(dict.fromkeys(fragile))
                       + " at " + ", ".join(dict.fromkeys(close)))

    return {"text": text_rows, "negative": negative_rows, "notices": notices}


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [key for key, _ in pairs]
    repeated = sorted({key for key in keys if keys.count(key) > 1})
    if repeated:
        raise VocabularyError(f"--queries repeats element {repeated[0]!r}; put its queries in one list")
    return dict(pairs)


def load_queries(source: str) -> list[tuple[str, str]]:
    """Read {"element": ["query", ...]} from literal JSON, a JSON file, or '-' for stdin."""
    text = source.strip()
    if text == "-":
        payload = json.load(sys.stdin, object_pairs_hook=_unique_keys)
    elif text.startswith("{"):
        payload = json.loads(text, object_pairs_hook=_unique_keys)
    else:
        payload = json.loads(Path(text).read_text(encoding="utf-8"), object_pairs_hook=_unique_keys)
    example = '{"pose": ["arms crossed"], "lighting": ["soft light", "rim light"]}'
    if not isinstance(payload, dict) or not payload:
        raise VocabularyError("--queries takes a JSON object of element names and queries, such as " + example)
    pairs: list[tuple[str, str]] = []
    for element, queries in payload.items():
        items = [queries] if isinstance(queries, str) else queries
        if (not element.strip() or not isinstance(items, list) or not items
                or any(not isinstance(query, str) or not query.strip() for query in items)):
            raise VocabularyError(f"--queries {element!r}: give a query or a list of queries, as in " + example)
        pairs.extend((element, query) for query in items)
    return pairs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?", help="English term or concept to search")
    parser.add_argument("--queries", metavar="JSON_OR_PATH",
                        help='Several searches in one run: {"ELEMENT": ["QUERY", ...]} as literal JSON, '
                             "a JSON file, or - for stdin. With --record, each query is recorded under its element.")
    parser.add_argument(
        "--dictionary",
        action="append",
        type=Path,
        required=True,
        help="Path to a prompt-vocabulary dictionary. Repeat to search several dictionaries.",
    )
    parser.add_argument("--category", action="append", default=[], help="Category fragment filter")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--list-categories", action="store_true")
    parser.add_argument("--read", type=Path, help="A file holding a finished prompt: report every term with what it draws")
    parser.add_argument("--negative", type=Path, help="A file holding the negative text, read beside --read")
    parser.add_argument("--record", type=Path, metavar="PATH",
                        help="Append this search and the terms it returned to a prompt retrieval record")
    parser.add_argument("--element", help="Visual element this search serves, such as pose or lighting")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.queries is not None:
        if args.query is not None:
            parser.error("give one query or --queries, not both")
        if args.element is not None:
            parser.error("--queries names the element of each query")
    elif (args.record is None) != (args.element is None):
        parser.error("--record and --element go together")
    if (args.record is not None or args.queries is not None) and (args.read is not None or args.list_categories):
        parser.error("--record and --queries run searches")
    try:
        if args.record is not None:
            from prompt_retrieval import check_recordable
            check_recordable(args.record, None)
        searches = load_queries(args.queries) if args.queries is not None else None
        vocabularies = [load_vocabulary(path) for path in args.dictionary]
        if searches is not None:
            index = VocabularyIndex(vocabularies)
            results = [(element, query, index.search(query, category_filters=args.category, limit=args.limit))
                       for element, query in searches]
            output = {
                "ok": True,
                "mode": "searches",
                "category_filters": args.category,
                "searches": [{"element": element, "query": query, "result_count": len(rows),
                              "results": [row.as_json() for row in rows]}
                             for element, query, rows in results],
            }
            if args.record is not None:
                from prompt_retrieval import record_lookups
                record_lookups(args.record, [(element, [query], [row.term for row in rows])
                                             for element, query, rows in results])
        elif args.read is not None:
            report = read_prompt(
                vocabularies,
                args.read.read_text(encoding="utf-8"),
                args.negative.read_text(encoding="utf-8") if args.negative else "",
            )
            output = {"ok": True, "mode": "read", **report}
        elif args.list_categories:
            categories = list_categories(vocabularies)
            output = {
                "ok": True,
                "mode": "categories",
                "category_count": len(categories),
                "categories": categories,
            }
        else:
            if args.query is None:
                raise VocabularyError("give a query, --queries, --read or --list-categories")
            rows = search_vocabularies(
                vocabularies,
                args.query,
                category_filters=args.category,
                limit=args.limit,
            )
            output = {
                "ok": True,
                "mode": "search",
                "query": args.query,
                "category_filters": args.category,
                "result_count": len(rows),
                "results": [row.as_json() for row in rows],
            }
            if args.record is not None:
                from prompt_retrieval import record_lookup
                record_lookup(args.record, args.element, queries=[args.query],
                              inspected=[row.term for row in rows])
    except (OSError, ValueError, VocabularyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
