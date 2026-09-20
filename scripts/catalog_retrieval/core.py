"""Pure vocabulary, normalization, and classification helpers."""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

VALID_DOMAINS = {
    "human",
    "anthropomorphic-animal",
    "animal",
    "creature",
    "hybrid",
    "robot",
    "shared",
}


def canonical_domain(value: str) -> str:
    """Return one exact canonical domain value and reject every other input."""
    candidate = str(value)
    if candidate not in VALID_DOMAINS:
        allowed = ", ".join(sorted(VALID_DOMAINS))
        raise ValueError(f"domain must be one of: {allowed}")
    return candidate


STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "with", "in", "on", "at", "to",
    "for", "by", "into", "over",
}

# Some appearance words are not merely related terms; they select opposing
# measurable variants. A query for short claws should still be allowed to show
# the long-claw record as a nearby alternative, but that opposite variant must
# not receive the same strong relevance band merely because both share "dark",
# "curved", "claws", and "paw". Keep this list deliberately conservative and
# apply it only to label/tag/category text, where the record is naming its own
# variant rather than discussing a failure mode or an adaptable option.
CONTRASTIVE_MODIFIER_GROUPS: tuple[tuple[frozenset[str], frozenset[str]], ...] = (
    (
        frozenset({"short", "compact", "stubby"}),
        frozenset({"long", "elongated", "extended", "lengthened"}),
    ),
)


def contrastive_modifier_conflicts(
    query_tokens: Iterable[str], candidate_tokens: Iterable[str]
) -> list[tuple[str, str]]:
    """Return explicit query/candidate modifier conflicts.

    A conflict is reported only when the query chooses one side, the record's
    strong identity fields choose the other side, and those strong fields do not
    also contain the requested side. This prevents broad prose such as
    "avoid long talons" from turning into a false conflict.
    """
    query = set(query_tokens)
    candidate = set(candidate_tokens)
    conflicts: list[tuple[str, str]] = []
    for first, second in CONTRASTIVE_MODIFIER_GROUPS:
        query_first = query & first
        query_second = query & second
        candidate_first = candidate & first
        candidate_second = candidate & second
        if query_first and candidate_second and not candidate_first:
            conflicts.append((sorted(query_first)[0], sorted(candidate_second)[0]))
        elif query_second and candidate_first and not candidate_second:
            conflicts.append((sorted(query_second)[0], sorted(candidate_first)[0]))
    return conflicts

# Relevance floors on the 0..1 scale. Results below MODERATE_FLOOR are not
# returned at all: an empty category means "no strong preset support exists;
# art-direct this aspect freely" and is the honest answer.
STRONG_FLOOR = 0.30
MODERATE_FLOOR = 0.12


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Missing catalog file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc


def ascii_fold(value: Any) -> str:
    """Fold Latin diacritics while leaving other scripts detectable."""
    raw = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in raw if not unicodedata.combining(ch))


def normalize(value: Any) -> str:
    text = ascii_fold(value).lower().replace("_", "-")
    text = re.sub(r"[^a-z0-9\-]+", " ", text)
    return " ".join(text.split())


def tokens_of(value: Any) -> list[str]:
    return [t for t in normalize(value).replace("-", " ").split() if len(t) > 1]


def token_set(value: Any) -> set[str]:
    return set(tokens_of(value))


def _species_family_value(term: str) -> str | None:
    value = normalize(term)
    families = {
        "canine": ("wolf", "dog", "canine", "fox", "coyote", "jackal", "dhole", "dingo", "husky", "malamute", "akita", "doberman", "collie"),
        "feline": ("tiger", "lion", "cat", "feline", "panther", "leopard", "lynx", "cheetah", "jaguar"),
        "ursine": ("bear", "ursine"),
        "avian": ("bird", "avian", "eagle", "raven", "owl", "hawk"),
        "aquatic": ("shark", "orca", "dolphin", "fish", "aquatic", "whale"),
        "reptile": ("lizard", "dragon", "alligator", "crocodile", "snake", "reptile"),
        "ungulate": ("deer", "stag", "horse", "bull", "bison", "goat", "ram", "ungulate"),
    }
    words = set(value.replace("-", " ").split())
    for family, members in families.items():
        if words & set(members):
            return family
    return None


_SPECIES_TAXON_MEMBERS: Mapping[str, tuple[str, ...]] = {
    "fox": ("fox", "fennec", "vixen"),
    "wolf": ("wolf",),
    "dog": ("dog", "husky", "malamute", "akita", "doberman", "collie", "shepherd", "retriever", "terrier", "hound", "corgi", "shiba", "great dane"),
    "coyote": ("coyote",), "jackal": ("jackal",), "dhole": ("dhole",), "dingo": ("dingo",),
    "tiger": ("tiger",), "lion": ("lion",), "panther": ("panther",),
    "leopard": ("snow leopard", "leopard"), "jaguar": ("jaguar",),
    "lynx": ("lynx", "bobcat"), "cheetah": ("cheetah",), "cat": ("cat",),
    "bear": ("polar bear", "bear"), "eagle": ("eagle",),
    "raven": ("raven", "crow"), "owl": ("owl",), "hawk": ("hawk", "falcon"),
    "bird": ("bird",), "shark": ("shark",), "orca": ("killer whale", "orca"),
    "dolphin": ("dolphin",), "whale": ("whale",), "fish": ("fish",),
    "dragon": ("dragon", "draconic"), "lizard": ("lizard",),
    "crocodile": ("crocodile", "alligator"), "snake": ("snake", "serpent"),
    "deer": ("deer", "stag", "doe"), "horse": ("horse", "equine"),
    "bull": ("bull", "bovine", "cow"), "bison": ("bison", "buffalo"),
    "goat": ("goat",), "ram": ("ram", "sheep"),
}
_BROAD_SPECIES_FAMILIES = frozenset({"canine", "feline", "ursine", "avian", "aquatic", "reptile", "ungulate"})
_GENERIC_SPECIES_MODIFIERS = frozenset({"adult", "anthropomorphic", "animal", "feral", "female", "male", "natural", "young"})


def _species_taxon_value(term: str) -> str | None:
    value = normalize(term)
    if not value:
        return None
    words = set(value.replace("-", " ").split())
    ranked = sorted(_SPECIES_TAXON_MEMBERS.items(), key=lambda item: max(len(member.split()) for member in item[1]), reverse=True)
    for taxon, members in ranked:
        for member in members:
            normalized_member = normalize(member)
            if (" " in normalized_member and normalized_member in value) or (" " not in normalized_member and normalized_member in words):
                return taxon
    return None


def _species_anchor_scope(term: str) -> tuple[str, str] | None:
    value = normalize(term)
    if not value:
        return None
    if value in _BROAD_SPECIES_FAMILIES:
        return "family", value
    taxon = _species_taxon_value(value)
    if taxon:
        return "taxon", taxon
    family = _species_family_value(value)
    return ("family", family) if family else None


def _species_anchor_requests_specific_variant(values: Sequence[str]) -> bool:
    for value in values:
        scope = _species_anchor_scope(value)
        if scope is None or scope[0] != "taxon":
            continue
        remaining = set(tokens_of(value))
        remaining.difference_update(tokens_of(scope[1]))
        remaining.difference_update(_GENERIC_SPECIES_MODIFIERS)
        if remaining:
            return True
    return False


def _field_text(record: Mapping[str, Any], keys: Iterable[str]) -> str:
    pieces: list[str] = []
    for key in keys:
        value = record.get(key)
        if isinstance(value, (dict, list)):
            pieces.append(json.dumps(value, ensure_ascii=False))
        elif value not in (None, ""):
            pieces.append(str(value))
    return normalize(" ".join(pieces))


def _normalized_domains(record: Mapping[str, Any]) -> tuple[str, ...]:
    raw = record.get("domains")
    if isinstance(raw, list):
        items = [str(item) for item in raw]
    else:
        items = []
    single = record.get("domain")
    if single not in (None, ""):
        items.append(str(single))
    cleaned = []
    for item in items:
        value = canonical_domain(item)
        if value and value not in cleaned:
            cleaned.append(value)
    if not cleaned:
        cleaned = ["shared"]
    return tuple(cleaned)


def _domain_compatible(wanted: str | None, entry_domains: Sequence[str]) -> bool:
    if not wanted:
        return True
    wanted_n = canonical_domain(wanted)
    domains = {canonical_domain(item) for item in entry_domains}
    return bool(domains & {wanted_n, "shared", ""})


def relevance_band(value: float, strong_eligible: bool = True) -> str | None:
    if value >= STRONG_FLOOR and strong_eligible:
        return "strong"
    if value >= MODERATE_FLOOR:
        return "moderate"
    return None


def record_tier(record: Mapping[str, Any]) -> str:
    """Two roles, not a quality ranking. `curated` records carry the full
    authoring standard and work as complete production knowledge. `vocabulary`
    records do a different job: they supply names, options, and model-legible
    phrasing (species, colors, props, camera terms) so the agent recalls
    choices it would not invent. Their brevity is the design, not a summary
    of something richer."""
    return "curated" if record.get("curation_status") == "curated" else "vocabulary"


VALID_TIERS = {"any", "curated", "vocabulary"}


def normalize_tier(value: str | None) -> str:
    candidate = str(value or "any")
    if candidate not in VALID_TIERS:
        raise ValueError("tier must be one of: any, curated, vocabulary")
    return candidate


def canonical_category(name: str) -> str:
    return str(name)


def parse_csv(value: str | None) -> set[str]:
    return {item.strip() for item in str(value or "").split(",") if item.strip()}
