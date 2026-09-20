#!/usr/bin/env python3
"""Facet-aware discovery helpers for the Character Prompt Builder catalog.

This module intentionally performs deterministic lexical analysis. It does not
replace the agent's semantic judgment. Its job is to keep ordinary descriptive
phrases useful even when the caller does not know preset labels or IDs, and to
separate ambiguous words such as "blue" by what they modify (coat, eyes,
lighting, environment, or wardrobe).
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from state_protocol import unsupported_schema_keywords, validate_against_schema

ROOT = Path(__file__).resolve().parents[1]
CATALOG_QUERY_SCHEMA_PATH = ROOT / "schemas" / "catalog-query.schema.json"
_CATALOG_QUERY_SCHEMA: dict[str, Any] | None = None

STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "with", "in", "on", "at", "to",
    "for", "by", "into", "over", "from", "as", "is", "are", "be", "being",
}

COLOR_TERMS = (
    "blue gray", "blue grey", "blue black", "blue white", "black white",
    "red orange", "teal blue", "navy blue", "ice blue", "steel blue",
    "electric blue", "royal blue", "sky blue", "pale blue", "deep blue",
    "warm gray", "cool gray", "warm grey", "cool grey", "off white",
    "blue", "navy", "cyan", "teal", "turquoise", "azure", "indigo",
    "violet", "purple", "magenta", "pink", "red", "crimson", "scarlet",
    "orange", "amber", "gold", "golden", "yellow", "lime", "green",
    "olive", "brown", "tan", "beige", "cream", "ivory", "white", "black",
    "charcoal", "gray", "grey", "silver", "bronze", "copper", "rust",
)
COLOR_TERMS_SORTED = tuple(sorted(COLOR_TERMS, key=lambda value: (-len(value.split()), -len(value))))

COLOR_FAMILY = {
    "navy": "blue",
    "cyan": "blue",
    "teal": "blue",
    "turquoise": "blue",
    "azure": "blue",
    "indigo": "blue",
    "steel blue": "blue",
    "ice blue": "blue",
    "electric blue": "blue",
    "royal blue": "blue",
    "sky blue": "blue",
    "pale blue": "blue",
    "deep blue": "blue",
    "navy blue": "blue",
    "teal blue": "blue",
    "blue gray": "blue",
    "blue grey": "blue",
    "blue black": "blue",
    "blue white": "blue",
    "crimson": "red",
    "scarlet": "red",
    "magenta": "pink",
    "amber": "orange",
    "golden": "gold",
    "lime": "green",
    "olive": "green",
    "tan": "brown",
    "beige": "brown",
    "cream": "white",
    "ivory": "white",
    "off white": "white",
    "charcoal": "black",
    "warm gray": "gray",
    "cool gray": "gray",
    "warm grey": "gray",
    "cool grey": "gray",
    "grey": "gray",
    "silver": "gray",
    "bronze": "brown",
    "copper": "brown",
    "rust": "brown",
}

BUILD_TERMS = {
    "muscular", "muscled", "musclebound", "massive", "bulky", "powerful",
    "broad", "broad built", "broad-built", "heavy built", "heavily built",
    "thick", "stocky", "bodybuilder", "athletic", "lean", "slender", "slim",
    "heavyset", "giant", "towering", "compact", "round", "soft", "lanky",
}
BUILD_CANONICAL = {
    "muscled": "muscular",
    "musclebound": "muscular",
    "broad-built": "broad built",
    "heavy built": "heavily built",
}

# A build adjective is not a body-build anchor merely because the catalog also
# indexes that word under body-build. An explicit local head noun owns the
# modifier first. This keeps phrases such as ``broad crown clumps`` and
# ``athletic shorts`` in their authored semantic roles while preserving
# ``muscular black panther`` as a body-build statement.
_EXPLICIT_MODIFIER_HEAD_FACETS = {
    # Permanent hair and head construction.
    "hair": "identity_detail",
    "hairstyle": "hair_style",
    "forelock": "hair_style",
    "forelocks": "hair_style",
    "bang": "hair_style",
    "bangs": "hair_style",
    "fringe": "hair_style",
    "mane": "mane",
    "manes": "mane",
    "ruff": "ruff",
    "ruffs": "ruff",
    "tuft": "identity_detail",
    "tufts": "identity_detail",
    "clump": "identity_detail",
    "clumps": "identity_detail",
    "strand": "identity_detail",
    "strands": "identity_detail",
    "lock": "identity_detail",
    "locks": "identity_detail",
    # Wardrobe.
    "shorts": "wardrobe",
    "trousers": "wardrobe",
    "pants": "wardrobe",
    "shirt": "wardrobe",
    "jersey": "wardrobe",
    "jacket": "wardrobe",
    "uniform": "wardrobe",
    "outfit": "wardrobe",
    "clothes": "wardrobe",
    "clothing": "wardrobe",
    "apron": "wardrobe",
    "robe": "wardrobe",
    "hoodie": "wardrobe",
    "armor": "wardrobe",
    "dress": "wardrobe",
    "skirt": "wardrobe",
    "sock": "wardrobe",
    "socks": "wardrobe",
    "shoe": "wardrobe",
    "shoes": "wardrobe",
    "boot": "wardrobe",
    "boots": "wardrobe",
    "beard": "facial_hair",
    "beards": "facial_hair",
    "goatee": "facial_hair",
    "mustache": "facial_hair",
    "moustache": "facial_hair",
    # Other explicit craft and scene heads that must not become physique.
    "eye": "eye_feature",
    "eyes": "eye_feature",
    "fur": "subject_surface",
    "coat": "subject_surface",
    "pelt": "subject_surface",
    "feathers": "subject_surface",
    "plumage": "subject_surface",
    "scales": "subject_surface",
    "light": "lighting",
    "lighting": "lighting",
    "glow": "lighting",
    "shadow": "lighting",
    "shadows": "lighting",
    "room": "environment",
    "wall": "environment",
    "background": "environment",
    "interior": "environment",
    "environment": "environment",
    "pose": "pose",
    "stance": "pose",
    "action": "pose",
    "gesture": "gesture",
    "style": "style",
    "rendering": "style",
    "treatment": "style",
    # Explicit anatomical heads retain body-build meaning.
    "body": "body_build",
    "build": "body_build",
    "torso": "body_build",
    "frame": "body_build",
    "figure": "body_build",
    "figures": "body_build",
    "physique": "body_build",
    "shoulder": "body_build",
    "shoulders": "body_build",
    "chest": "body_build",
    "limb": "body_build",
    "limbs": "body_build",
}

_MODIFIER_LOCATION_TOKENS = frozenset({
    "head", "crown", "brow", "temple", "temples", "cheek", "cheeks",
    "ear", "ears", "neck", "chest", "facial",
})

_MODIFIER_SCOPE_BARRIERS = frozenset({
    "and", "or", "with", "wearing", "while", "under", "against",
    "beside", "near", "inside", "outside", "from", "into", "over",
    "of", "in", "on", "at", "to", "for", "by", "as", "behind",
    "before", "after", "around", "through", "across", "between",
    "among", "within", "without", "above", "below", "beyond",
})

# Only a canonical species name or an authored species synonym may establish
# a species identity anchor.  Descriptive tags on a species record remain
# searchable, but words such as ``tall`` (Great Dane) or ``bold`` (honey
# badger) are not themselves species names.  Cache generation prefixes the
# generated equivalents with ``pack-``; both authored and generated forms are
# listed explicitly so this rule does not depend on one pack's authoring style.
SPECIES_NAME_SOURCES = frozenset({
    "label",
    "pack-label",
    "author-alias",
    "pack-author-alias",
    "generated-label-alias",
})

# A taxonomic head can be shared by several canonical species names without
# being repeated as a standalone label.  In a synthetic fixture, for example,
# ``canid`` may be an authored tag on two compound species records.  Such a tag
# is a species name only when it is the terminal name segment of the associated
# record.  This keeps the taxonomic head while rejecting descriptive tags such
# as ``tall`` or ``bold`` that happen to be indexed on a species record.
SPECIES_NAME_SUFFIX_SOURCES = frozenset({"author", "tag", "catalog-alias"})

# A modifier immediately before an established species phrase can be routed
# through catalog facets without hard-coding an English adjective list.  A
# height word such as ``tall`` may be indexed by both body-build and proportion
# records; proportion is the more precise identity axis and wins that tie.
SPECIES_MODIFIER_FACET_PRIORITY = ("proportion", "body_build")

PROPORTION_TERMS = {
    "small head", "compact head", "large head", "broad body",
    "broad shoulders", "massive chest", "large chest", "wide torso",
    "narrow waist", "long legs", "short legs", "long arms",
    "large hands", "large paws", "oversized hands", "thick neck",
    "short muzzle", "long muzzle", "broad muzzle",
}

DOMAIN_TERMS = {
    "anthro": "anthropomorphic-animal",
    "anthropomorphic": "anthropomorphic-animal",
    "beastman": "anthropomorphic-animal",
    "beast person": "anthropomorphic-animal",
    "animal person": "anthropomorphic-animal",
    "kemono": "anthropomorphic-animal",
    "human": "human",
    "ordinary animal": "animal",
    "quadruped animal": "animal",
    "creature": "creature",
    "monster": "creature",
    "hybrid": "hybrid",
    "robot": "robot",
    "android": "robot",
    "mecha": "robot",
}

QUERY_SYNONYMS = {
    "grey": "gray",
    "muscled": "muscular",
    "musclebound": "muscular",
    "beastman": "anthropomorphic",
    "kemono": "anthropomorphic",
    "closeup": "close portrait",
    "close-up": "close portrait",
    "lowangle": "low angle",
    "wideangle": "wide angle",
    "pelt": "fur",
}

FACET_BY_CATEGORY = {
    "species": "species",
    "subject-domain": "domain",
    "body-build": "body_build",
    "body-form": "body_build",
    "proportion": "proportion",
    "coat-palette": "coat_palette",
    "animal-surface": "subject_surface",
    "marking": "marking",
    "head-hair": "head_hair",
    "hair-color": "hair_color",
    "hair-style": "hair_style",
    "hair-texture": "hair_texture",
    "eye-feature": "eye_feature",
    "skin-tone": "skin_tone",
    "skin-detail": "skin_detail",
    "human-body-detail": "body_detail",
    "face-feature": "face_feature",
    "head-feature": "head_feature",
    "facial-hair": "facial_hair",
    "mane": "mane",
    "ruff": "ruff",
    "head-fur-placement": "head_fur_placement",
    "creature-anatomy": "species",
    "hybrid-feature": "species",
    "robot-form": "species",
    "robot-surface": "subject_surface",
    "outfit": "wardrobe",
    "fashion-aesthetic": "wardrobe",
    "footwear": "wardrobe",
    "accessory": "accessory",
    "occupation": "role",
    "pose-action": "pose",
    "movement": "pose",
    "gesture": "gesture",
    "hand-placement": "gesture",
    "leg-placement": "pose",
    "head-gaze": "performance",
    "expression": "performance",
    "emotion-nuance": "performance",
    "body-language-cue": "performance",
    "composition": "composition",
    "camera": "camera",
    "lens": "camera",
    "shot-type": "camera",
    "lighting": "lighting",
    "environment": "environment",
    "mood-palette": "mood",
    "color-role": "color_design",
    "time-of-day": "atmosphere",
    "weather": "atmosphere",
    "season": "atmosphere",
    "effect": "effect",
    "material": "material",
    "rendering": "style",
    "illustration-medium": "style",
    "photography-style": "style",
    "aesthetic-touch": "style",
    "negative-failure": "diagnostic",
    "constraint": "constraint",
    "distinctive-detail": "identity_detail",
    "prop": "prop",
    "age-appearance": "age",
    "gender-presentation": "presentation",
    "color-role": "color_design",
    "concrete-style-family": "style",
    "visual-evidence": "reference",
}

KIND_PRIMARY_FACET = {
    "profile": "style",
    "aesthetic-core": "aesthetic",
    "style-family": "style",
    "domain-realization": "domain_realization",
    "scene": "scene",
    "recipe": "scene",
    "archetype": "identity",
    "correction": "diagnostic",
    "model": "model",
    "asset": "reference",
}

DEFAULT_FIELD_FACETS = {
    "subject": "species",
    "species": "species",
    "morphology": "species",
    "body": "body_build",
    "surface": "subject_surface",
    # A generic palette can include clothing, effects, or environment colors.
    # Subject coat colors are extracted contextually below instead of treating
    # every palette color as fur.
    "palette": "color_design",
    "markings": "marking",
    "head_hair": "head_hair",
    "hair": "head_hair",
    "hair_style": "hair_style",
    "hair_texture": "hair_texture",
    "hair_color": "hair_color",
    "facial_hair": "facial_hair",
    "mane": "mane",
    "ruff": "ruff",
    "head_fur": "head_fur_placement",
    "head_fur_placement": "head_fur_placement",
    "head_feature": "head_feature",
    "head_features": "head_feature",
    "eyes": "eye_feature",
    "eye": "eye_feature",
    "features": "species",
    "proportions": "proportion",
    "role": "role",
    "signature_equipment": "accessory",
    "presentation_examples": "scene",
    "outfit": "wardrobe",
    "pose": "pose",
    "expression": "performance",
    "composition": "composition",
    "camera": "camera",
    "lighting": "lighting",
    "environment": "environment",
    "mood": "mood",
    "effects": "effect",
    "constraints": "constraint",
}


STAGING_FIELD_FACETS = {
    "body_geometry": "proportion",
    "action_geometry": "pose",
    "gaze_and_expression": "performance",
    "prop_or_contact_geometry": "contact",
    "focal_hierarchy": "composition",
    "depth_order": "composition",
}

DISCOVERY_AXES = (
    "identity",
    "scene",
    "role",
    "wardrobe",
    "pose",
    "performance",
    "camera",
    "lighting",
    "environment",
    "mood",
    "style",
)

# These facets describe repeatable character identity rather than the current
# performance or presentation. This set intentionally says nothing about the
# inverse category: scene-specific character state remains open-class and must
# be rebuilt from the requested scene rather than reduced to a finite checklist.
PERMANENT_HAIR_HEAD_FACETS = frozenset({
    "head_hair",
    "hair_style",
    "hair_texture",
    "hair_color",
    "facial_hair",
    "mane",
    "ruff",
    "head_fur_placement",
    "head_feature",
})

PERMANENT_IDENTITY_FACETS = frozenset({
    "domain",
    "species",
    "body_build",
    "proportion",
    "subject_surface",
    "coat_palette",
    "marking",
    "eye_feature",
    "skin_tone",
    "skin_detail",
    "body_detail",
    "face_feature",
    "identity",
    "identity_detail",
}) | PERMANENT_HAIR_HEAD_FACETS

# Facets that may be promoted from an exact ordinary-language lexical match
# into an explicit brief anchor. These are deliberately narrower than every
# searchable facet. A query mentioning a prop or a rendering adjective should
# not silently become a permanent identity lock, but age, role, clothing,
# camera, lighting, and other directly stated choices must not be overwritten
# by exploratory direction cards.
LEXICAL_ANCHOR_FACETS = {
    "age",
    "presentation",
    "role",
    "wardrobe",
    "accessory",
    "gesture",
    "pose",
    "performance",
    "camera",
    "composition",
    "lighting",
    "environment",
    "mood",
    "style",
} | set(PERMANENT_HAIR_HEAD_FACETS)

# Tokens that explain modifier scope but are not meaningful unresolved
# requirements by themselves. They are omitted from `terms_without_alias` after
# they have done their parsing job.
DISCOVERY_CUE_TOKENS = {
    "fur", "coat", "pelt", "fleece", "hide", "skin", "hair", "eye",
    "eyes", "feather", "feathers", "plumage", "scale", "scales", "shell",
    "carapace", "marking", "markings", "pattern", "patterns", "colored",
    "color", "light", "lighting", "glow", "background", "room", "wall",
    "interior", "environment", "outfit", "clothing", "clothes", "wearing",
    "shorts", "trousers", "pants", "shirt", "jersey", "jacket", "uniform",
    "socks", "shoes", "boots", "crown", "clump", "clumps", "beard",
    "camera", "angle", "view", "portrait", "body", "built", "build",
}

AXIS_FACETS = {
    "identity": {
        "domain", "species", "body_build", "proportion", "coat_palette",
        "marking", "identity", "identity_detail", "head_hair", "hair_style",
        "hair_texture", "hair_color", "facial_hair", "mane", "ruff",
        "head_fur_placement", "head_feature",
    },
    "scene": {"scene"},
    "role": {"role"},
    "wardrobe": {"wardrobe", "accessory"},
    "pose": {"pose", "gesture", "contact"},
    "performance": {"performance"},
    "camera": {"camera", "composition"},
    "lighting": {"lighting", "color_design"},
    "environment": {"environment", "atmosphere", "effect"},
    "mood": {"mood", "aesthetic"},
    "style": {"style"},
}

# Facet names a structured query may name as an anchor. The canonical set lives
# in the tables above, so a misspelling such as ``age_appearance`` is refused at
# the door rather than silently scoring nothing.
ANCHOR_FACETS = frozenset(
    set(FACET_BY_CATEGORY.values())
    | set(KIND_PRIMARY_FACET.values())
    | {facet for group in AXIS_FACETS.values() for facet in group}
)


def normalize(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in raw if not unicodedata.combining(ch)).lower().replace("_", "-")
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"[^a-z0-9\-]+", " ", text)
    text = " ".join(text.split())
    for source, target in QUERY_SYNONYMS.items():
        text = re.sub(rf"\b{re.escape(source)}\b", target, text)
    return " ".join(text.split())


def normalize_query(value: Any) -> str:
    """Normalize canonical English retrieval text.

    Language understanding and translation belong to the calling agent. The
    deterministic catalog receives either English descriptive wording or a
    structured query whose facets have already been normalized.
    """
    return normalize(value)


def association_names_species(
    phrase: str,
    association: Mapping[str, Any],
    index: "SearchIndex",
) -> bool:
    """Return whether one lexical association identifies a species name."""

    if not (
        index.association_facet(association) == "species"
        or str(association.get("category") or "") == "species"
    ):
        return False
    source = str(association.get("source") or "")
    if source in SPECIES_NAME_SOURCES:
        return True
    if source not in SPECIES_NAME_SUFFIX_SOURCES:
        return False
    phrase_parts = re.findall(r"[a-z0-9]+", normalize(phrase))
    record_parts = re.findall(
        r"[a-z0-9]+",
        str(association.get("id") or "").lower(),
    )
    return bool(
        phrase_parts
        and len(phrase_parts) <= len(record_parts)
        and record_parts[-len(phrase_parts):] == phrase_parts
    )


def tokens_of(value: Any) -> list[str]:
    return [token for token in normalize(value).replace("-", " ").split() if len(token) > 1]


def color_family(value: Any) -> str:
    normalized = normalize(value).replace("-", " ")
    return COLOR_FAMILY.get(normalized, normalized)


def color_families_in_text(value: Any) -> set[str]:
    text = normalize(value).replace("-", " ")
    found: set[str] = set()
    for term in COLOR_TERMS_SORTED:
        normalized = normalize(term).replace("-", " ")
        if re.search(rf"\b{re.escape(normalized)}\b", text):
            found.add(color_family(normalized))
    return found


def _subject_color_terms(value: Any) -> list[str]:
    """Extract colors that describe the subject surface rather than the scene.

    A color is accepted when it sits near a surface cue, a marking cue, or a
    species name. This prevents a blue uniform or blue hall from becoming a
    blue coat in identity retrieval.
    """
    text = normalize(value).replace("-", " ")
    if not text:
        return []
    words = text.split()
    surface_cues = {
        "fur", "coat", "pelt", "fleece", "hide", "skin", "feather",
        "feathers", "plumage", "scale", "scales", "shell", "carapace",
        "marking", "markings", "pattern", "patterns", "muzzle", "cheek",
        "chest", "throat", "ventral", "dorsal", "paw", "paws", "tail",
        "surface", "panels", "panel",
    }
    species_cues = {
        "wolf", "dog", "fox", "coyote", "jackal", "tiger", "lion", "cat",
        "leopard", "panther", "lynx", "bear", "shark", "orca", "dragon",
        "lizard", "crocodile", "alligator", "stag", "deer", "horse", "rabbit",
        "canine", "feline", "avian", "reptile", "animal", "creature",
    }
    output: list[str] = []
    term_tokens = [
        (term, normalize(term).replace("-", " ").split())
        for term in COLOR_TERMS_SORTED
    ]
    for raw_term, tokens in term_tokens:
        width = len(tokens)
        for start in range(0, len(words) - width + 1):
            if words[start:start + width] != tokens:
                continue
            left = max(0, start - 4)
            right = min(len(words), start + width + 5)
            window = set(words[left:right])
            # Color immediately before a species label is also coat evidence,
            # as in "blue and white wolf" or "black tiger".
            after = set(words[start + width:min(len(words), start + width + 4)])
            if window & surface_cues or after & species_cues:
                family = color_family(raw_term)
                if family and family not in output:
                    output.append(family)
                break
    return output


def flatten_text(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, Mapping):
        output: list[str] = []
        for child in value.values():
            output.extend(flatten_text(child))
        return output
    if isinstance(value, (list, tuple, set)):
        output = []
        for child in value:
            output.extend(flatten_text(child))
        return output
    return [str(value)]


def _add_facet(facets: dict[str, list[str]], facet: str, value: Any) -> None:
    if not facet:
        return
    for raw in flatten_text(value):
        text = normalize(raw)
        if not text or text in facets.setdefault(facet, []):
            continue
        facets[facet].append(text)


def _color_terms_in(value: Any) -> list[str]:
    text = normalize(" ".join(flatten_text(value)))
    found: list[str] = []
    for color in COLOR_TERMS_SORTED:
        if re.search(rf"\b{re.escape(color)}\b", text) and color not in found:
            found.append(color)
    return found


def _primary_subject_colors(record: Mapping[str, Any]) -> list[str]:
    """Infer subject-defining colors, excluding light, eyes, trim, and accents.

    Sources are consulted in priority order. A color-bearing label such as
    `Blue-and-white Wolf` is already the strongest declaration and prevents a
    later mention of blue-gray shadow or blue eyes from becoming a false coat
    anchor. When the label carries no color, species and surface descriptions
    provide the fallback.
    """
    sources: list[Any] = [record.get("label")]
    defaults = record.get("defaults")
    if isinstance(defaults, Mapping):
        sources.extend(defaults.get(key) for key in ("species", "surface", "skin"))
    construction = record.get("identity_construction")
    if isinstance(construction, Mapping):
        sources.extend(construction.get(key) for key in ("surface_and_palette", "surface", "palette"))
    elif construction not in (None, ""):
        sources.append(construction)
    if isinstance(defaults, Mapping):
        palette = defaults.get("palette")
        if isinstance(palette, str):
            sources.append(re.split(
                r"\b(?:shadow|lighting|light|rim|background|cloth|fabric|trim|hardware|metal|accent|eyes?|iris)\b",
                palette, maxsplit=1, flags=re.I,
            )[0])

    for source in sources:
        text = normalize(" ".join(flatten_text(source)))
        if not text:
            continue
        colors = _color_terms_in(text)
        if colors:
            # Composite terms are retained, followed by their useful atomic
            # colors. Five entries cover combinations such as blue-white-gray
            # without admitting unrelated later accent colors.
            return colors
    return []


def _classify_identity_invariant(value: Any) -> set[str]:
    text = normalize(value)
    facets: set[str] = set()
    if not text:
        return facets
    if any(term in text for term in BUILD_TERMS) or any(term in text for term in ("shoulder", "torso", "thigh", "waist", "proportion")):
        facets.update({"body_build", "proportion"})
    if any(term in text for term in ("fur", "coat", "pelt", "skin", "scale", "feather", "palette", "color")):
        facets.update({"subject_surface", "coat_palette"})
    if any(term in text for term in ("wolf", "canine", "feline", "muzzle", "ears", "tail", "paw", "hoof", "beak", "fin", "gill", "horn")):
        facets.add("species")
    if "eye" in text or "iris" in text or "pupil" in text:
        facets.add("eye_feature")
    if "marking" in text or "stripe" in text or "patch" in text or "pattern" in text:
        facets.add("marking")

    # Anthropomorphic characters may use human-like head hair as part of their
    # recognition topology. Keep it distinct from the body coat and from a
    # temporary grooming response caused by the current scene.
    head_hair = bool(re.search(
        r"\b(?:head hair|hairstyle|hair style|hair topology|forelocks?|bangs?|fringe|"
        r"pompadour|mohawk|topknot|ponytail|pigtails?|side tuft|crown tuft)\b",
        text,
    ))
    if head_hair:
        facets.add("head_hair")
        facets.add("hair_style")
    hair_noun = (
        r"(?:head hair|hair|forelocks?|bangs?|fringe|manes?|beards?|goatees?|"
        r"moustaches?|mustaches?|sideburns?)"
    )
    texture_term = (
        r"(?:coarse|coily|curly|fine|kinky|silky|smooth|straight|wavy|wiry|"
        r"woolly|textured|crimped|fluffy|sleek|tousled|wispy)"
    )
    if re.search(
        rf"\b(?:{texture_term}(?: [a-z0-9-]+){{0,2}} {hair_noun}|"
        rf"{hair_noun}(?: [a-z0-9-]+){{0,2}} {texture_term}|hair texture)\b",
        text,
    ):
        facets.add("hair_texture")
    facial_hair = bool(re.search(
        r"\b(?:facial hair|beards?|goatees?|moustaches?|mustaches?|sideburns?|"
        r"soul patch|chin whiskers?)\b",
        text,
    ))
    if facial_hair:
        facets.add("facial_hair")
    if re.search(r"\bmanes?\b", text):
        facets.add("mane")
    if re.search(r"\bruffs?\b", text):
        facets.add("ruff")
    if re.search(
        r"\b(?:head fur|crown fur|brow fur|cheek fur|ear fur|ear tufts?|"
        r"cheek tufts?|crown tufts?|head-fur placement|fur placement)\b",
        text,
    ):
        facets.add("head_fur_placement")
    if re.search(
        r"\b(?:(?:head|cranial|skull) (?:horns?|antlers?|crests?)|brows?|"
        r"head shape|facial architecture)\b",
        text,
    ):
        facets.add("head_feature")
    if head_hair or facial_hair or "mane" in facets:
        for color in _color_terms_in(text):
            escaped = re.escape(normalize(color))
            if re.search(
                rf"\b(?:{escaped}(?: [a-z0-9-]+){{0,2}} {hair_noun}|"
                rf"{hair_noun}(?: [a-z0-9-]+){{0,2}} {escaped})\b",
                text,
            ):
                facets.add("hair_color")
                break
    return facets


def _add_classified_identity_facets(
    facets: dict[str, list[str]],
    value: Any,
) -> None:
    """Add focused invariant clauses instead of broad unrelated prose."""
    for raw in flatten_text(value):
        clauses = [
            clause.strip()
            for clause in re.split(r"[;,\.\n]+", raw)
            if clause.strip()
        ] or [raw]
        for clause in clauses:
            for facet in _classify_identity_invariant(clause):
                _add_facet(facets, facet, clause)



def project_performance_language_facets(record: Mapping[str, Any]) -> dict[str, list[str]]:
    """Project structured performance language into searchable semantic facets.

    Canonical performance records remain complete production knowledge. This
    projection exposes ordinary-language discovery evidence while preserving
    alternate interpretations and content intensity.
    """
    value = record.get("performance_language")
    if not isinstance(value, Mapping):
        return {}
    facets: dict[str, list[str]] = {}

    def add(facet: str, raw: Any) -> None:
        _add_facet(facets, facet, raw)

    add("emotion", value.get("felt_emotion"))
    add("emotion", value.get("displayed_emotion"))
    add("emotion", value.get("masked_or_conflicted_emotion"))
    add("performance_intent", value.get("intent"))
    add("viewer_relationship", value.get("viewer_or_partner_relationship"))
    add("relationship", value.get("viewer_or_partner_relationship"))

    channel_map = {
        "gaze": ("gaze", "performance"),
        "eyes-lids-brows": ("gaze", "expression"),
        "mouth-jaw-tongue": ("mouth_action", "expression"),
        "cheeks-skin-color": ("physiology", "expression"),
        "head-neck": ("body_language", "pose"),
        "torso-posture": ("body_language", "pose"),
        "arms-hands-manipulators": ("hand_action", "body_language"),
        "legs-feet-locomotion": ("leg_action", "body_language"),
        "distance-contact": ("contact", "relationship"),
        "breath-voice": ("physiology", "performance"),
        "physiology": ("physiology", "performance"),
        "ears": ("appendage_action", "body_language"),
        "tail": ("appendage_action", "body_language"),
        "whiskers": ("appendage_action", "expression"),
        "crest-feathers": ("appendage_action", "body_language"),
        "wings": ("appendage_action", "body_language"),
        "horns-antennae-tentacles": ("appendage_action", "body_language"),
        "surface-response": ("physiology", "effect"),
        "optics-sensors": ("mechanical_signal", "gaze"),
        "panels-fins": ("mechanical_signal", "body_language"),
        "actuators-servos": ("mechanical_signal", "body_language"),
        "indicators-emissives": ("mechanical_signal", "effect"),
        "ventilation-sound": ("mechanical_signal", "physiology"),
        "other": ("performance", "body_language"),
    }
    for cue in value.get("channel_cues") or []:
        if not isinstance(cue, Mapping):
            continue
        channel = str(cue.get("channel") or "other")
        primary, secondary = channel_map.get(channel, ("performance", "body_language"))
        evidence = [cue.get("observation"), cue.get("visual_instruction"), cue.get("direction_or_target"), cue.get("notes")]
        add(primary, evidence)
        add(secondary, evidence)

    for candidate in value.get("interpretation_candidates") or []:
        if not isinstance(candidate, Mapping):
            continue
        add("interpretation", candidate.get("meaning"))
        add("content_intensity", candidate.get("content_intensity"))
        add("performance", candidate.get("context"))
    selected = value.get("selected_interpretation")
    if isinstance(selected, Mapping):
        add("interpretation", selected.get("meaning"))
        add("content_intensity", selected.get("content_intensity"))
    projection = value.get("prompt_projection")
    if isinstance(projection, Mapping):
        add("performance", projection.get("primary_clause"))
        add("performance", projection.get("supporting_clauses"))
        add("performance", projection.get("search_facets"))
    return {facet: values for facet, values in facets.items() if values}

def extract_record_facets(kind: str, category: str | None, record: Mapping[str, Any]) -> dict[str, list[str]]:
    """Project one canonical record into searchable semantic facets.

    The projection is intentionally redundant: the same phrase may belong to
    both identity and coat-palette when that accurately reflects the canonical
    record. Facet-aware scoring decides which occurrence is relevant to a
    scoped query.
    """
    facets: dict[str, list[str]] = {}
    category_text = str(category or record.get("category") or "")
    primary = (
        "hair_texture"
        if category_text == "hair-texture"
        else FACET_BY_CATEGORY.get(category_text) or KIND_PRIMARY_FACET.get(kind) or "subject"
    )

    _add_facet(facets, primary, record.get("label"))
    _add_facet(facets, primary, record.get("tags"))
    _add_facet(facets, primary, record.get("prompt"))
    _add_facet(facets, "domain", record.get("domain"))
    _add_facet(facets, "domain", record.get("domains"))

    defaults = record.get("defaults")
    if isinstance(defaults, Mapping):
        for key, value in defaults.items():
            _add_facet(facets, DEFAULT_FIELD_FACETS.get(str(key), primary), value)

    # Packs may author permanent hair/head identity either in defaults or as
    # explicit record fields. Project both forms into the same facets; none of
    # these fields imply a closed list of scene-specific state.
    identity_field_facets = {
        "head_hair": "head_hair",
        "hair": "head_hair",
        "hair_style": "hair_style",
        "hair_texture": "hair_texture",
        "hair_color": "hair_color",
        "facial_hair": "facial_hair",
        "mane": "mane",
        "ruff": "ruff",
        "head_fur": "head_fur_placement",
        "head_fur_placement": "head_fur_placement",
        "head_feature": "head_feature",
        "head_features": "head_feature",
    }
    for key, facet in identity_field_facets.items():
        _add_facet(facets, facet, record.get(key))

    staging = record.get("staging")
    if isinstance(staging, Mapping):
        for key, value in staging.items():
            _add_facet(facets, STAGING_FIELD_FACETS.get(str(key), "scene"), value)

    if kind == "archetype":
        _add_facet(facets, "species", record.get("species_module_id"))
        _add_facet(facets, "species", record.get("species_group"))
        _add_facet(facets, "role", record.get("role_id"))
        _add_facet(facets, "identity", record.get("character_lock"))
        _add_classified_identity_facets(facets, record.get("character_lock"))
        _add_facet(facets, "marking", record.get("marking_logic"))
        _add_facet(facets, "proportion", record.get("proportion_logic"))

        construction = record.get("identity_construction")
        if isinstance(construction, Mapping):
            construction_map = {
                "morphology": "species",
                "proportions": "proportion",
                "body": "body_build",
                "surface_and_palette": "coat_palette",
                "surface": "subject_surface",
                "palette": "coat_palette",
                "marking_logic": "marking",
                "markings": "marking",
                "eyes": "eye_feature",
                "head_hair": "head_hair",
                "hair": "head_hair",
                "hair_style": "hair_style",
                "hair_texture": "hair_texture",
                "hair_color": "hair_color",
                "facial_hair": "facial_hair",
                "mane": "mane",
                "ruff": "ruff",
                "head_fur": "head_fur_placement",
                "head_fur_placement": "head_fur_placement",
                "head_feature": "head_feature",
                "head_features": "head_feature",
            }
            for key, value in construction.items():
                facet = construction_map.get(str(key), "identity")
                _add_facet(facets, facet, value)
                _add_classified_identity_facets(facets, value)
                if key == "surface_and_palette":
                    _add_facet(facets, "subject_surface", value)
        else:
            _add_facet(facets, "identity", construction)
            _add_classified_identity_facets(facets, construction)

        for invariant in record.get("identity_invariants") or []:
            _add_facet(facets, "identity", invariant)
            _add_classified_identity_facets(facets, invariant)

        primary_colors = _primary_subject_colors(record)
        _add_facet(facets, "primary_coat_color", primary_colors)
        # Species phrases such as `blue-and-white wolf` are also legitimate
        # coat evidence, while still remaining species evidence.
        if primary_colors:
            _add_facet(facets, "coat_palette", primary_colors)
    elif kind == "scene" or kind == "recipe":
        _add_facet(facets, "scene", record.get("image_promise"))
        _add_facet(facets, "scene", record.get("category"))
        _add_facet(facets, "scene", record.get("adaptable_fields"))
    elif kind == "style-family":
        for key in (
            "medium_family", "style_promise", "visual_signature", "line_system",
            "form_system", "value_and_shadow_system", "highlight_system",
            "color_system", "surface_system", "background_system",
            "detail_hierarchy", "touch_policy", "integration_prompt",
        ):
            _add_facet(facets, "style", record.get(key))
        _add_facet(facets, "use_case", record.get("best_for"))
        _add_facet(facets, "avoid", record.get("avoid_for"))
    elif kind == "profile":
        for key in (
            "medium_family", "visual_intent", "linework", "shape_language",
            "value_structure", "color_logic", "surface_policy",
            "lighting_response", "background_policy", "detail_hierarchy",
            "rendering", "positive_prompt",
        ):
            _add_facet(facets, "style", record.get(key))
    elif kind == "aesthetic-core":
        for key in (
            "aesthetic_promise", "appeal_center", "viewer_relationship_strategy",
            "composition_and_focal_strategy", "shape_and_rhythm_strategy",
            "surface_and_tactility_strategy", "color_and_light_strategy",
            "finish_and_detail_hierarchy", "integration_prompt",
        ):
            _add_facet(facets, "aesthetic", record.get(key))
    elif kind == "domain-realization":
        _add_facet(facets, "domain", record.get("subject_domain"))
        for key in (
            "realization_promise", "identity_and_silhouette", "performance_channels",
            "anatomy_and_weight", "surface_and_materials", "viewer_relationship",
            "motion_and_environment", "translation_rules", "integration_prompt",
        ):
            _add_facet(facets, "domain_realization", record.get(key))
    elif kind == "correction":
        _add_facet(facets, "diagnostic", record.get("trigger"))
        _add_facet(facets, "diagnostic", record.get("diagnosis"))
        _add_facet(facets, "diagnostic", record.get("positive_correction"))


    performance_facets = project_performance_language_facets(record)
    for facet, values in performance_facets.items():
        _add_facet(facets, facet, values)

    search_profile = record.get("search_profile")
    if isinstance(search_profile, Mapping):
        profile_facets = search_profile.get("facets")
        if isinstance(profile_facets, Mapping):
            for facet, values in profile_facets.items():
                _add_facet(facets, str(facet), values)

    # Subject color is intentionally extracted from identity-bearing surface
    # language rather than a generic palette. This keeps "blue fur" separate
    # from blue lighting, blue clothing, blue magic, and blue environments.
    color_sources: list[Any] = [
        record.get("label"),
        record.get("character_lock"),
        record.get("identity_invariants"),
        record.get("marking_logic"),
    ]
    if isinstance(defaults, Mapping):
        color_sources.extend([
            defaults.get("subject"), defaults.get("species"),
            defaults.get("surface"), defaults.get("markings"),
        ])
    identity_construction = record.get("identity_construction")
    if isinstance(identity_construction, Mapping):
        color_sources.extend([
            identity_construction.get("surface_and_palette"),
            identity_construction.get("marking_logic"),
            identity_construction.get("morphology"),
        ])
    elif identity_construction:
        color_sources.append(identity_construction)
    for source in color_sources:
        _add_facet(facets, "coat_palette", _subject_color_terms(source))

    return {facet: values for facet, values in facets.items() if values}


def infer_outcome_summary(kind: str, record: Mapping[str, Any]) -> str:
    profile = record.get("search_profile")
    if isinstance(profile, Mapping) and profile.get("outcome_summary"):
        return str(profile["outcome_summary"]).strip()
    label = str(record.get("label") or record.get("id") or kind).strip()
    if kind == "archetype":
        lock = str(record.get("character_lock") or "").strip()
        if lock:
            return f"Identity blueprint for {label}. {lock}"
        invariants = [str(value).strip() for value in record.get("identity_invariants") or [] if str(value).strip()]
        if invariants:
            return f"Identity blueprint for {label}, preserving " + "; ".join(invariants) + "."
    for key in (
        "image_promise", "style_promise", "aesthetic_promise", "realization_promise",
        "visual_function", "positive_correction", "description", "rendering", "prompt",
    ):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    defaults = record.get("defaults")
    if isinstance(defaults, Mapping):
        pieces = []
        for key in ("subject", "body", "pose", "composition", "camera", "lighting", "environment", "mood"):
            value = defaults.get(key)
            if isinstance(value, str) and value.strip():
                pieces.append(value.strip())
        if pieces:
            return "; ".join(pieces)
    return f"A reusable {kind} direction centered on {label}."


def infer_discovery_group(kind: str, record: Mapping[str, Any]) -> str:
    profile = record.get("search_profile")
    if isinstance(profile, Mapping) and profile.get("discovery_group"):
        return normalize(profile["discovery_group"]).replace(" ", "-")
    rid = str(record.get("id") or "")
    if kind == "archetype":
        if "--" in rid:
            return rid.split("--", 1)[0]
        role = str(record.get("role_id") or "")
        if role and rid.endswith("-" + role):
            return rid[: -(len(role) + 1)]
        label = str(record.get("label") or "")
        if ":" in label:
            return normalize(label.split(":", 1)[0]).replace(" ", "-")
    variant_of = None
    if isinstance(profile, Mapping):
        variant_of = profile.get("variant_of")
    return str(variant_of or rid)


def infer_variant_of(kind: str, record: Mapping[str, Any]) -> str | None:
    profile = record.get("search_profile")
    if isinstance(profile, Mapping) and profile.get("variant_of"):
        return str(profile["variant_of"])
    group = infer_discovery_group(kind, record)
    rid = str(record.get("id") or "")
    return group if group and group != rid else None


def _compact_variations(value: Any, limit: int | None = None) -> list[str]:
    output: list[str] = []
    if isinstance(value, Mapping):
        candidates: Iterable[Any] = value.keys()
    elif isinstance(value, (list, tuple, set)):
        candidates = value
    elif value not in (None, ""):
        candidates = [value]
    else:
        candidates = []
    for item in candidates:
        text = str(item).strip()
        if text and text not in output:
            output.append(text)
        if limit is not None and len(output) >= limit:
            break
    return output


def build_search_profile(kind: str, category: str | None, record: Mapping[str, Any], aliases: Sequence[str]) -> dict[str, Any]:
    explicit = record.get("search_profile") if isinstance(record.get("search_profile"), Mapping) else {}
    alias_values: list[str] = []
    for value in list(explicit.get("aliases") or []) + list(aliases):
        text = normalize(value)
        if text and text not in alias_values:
            alias_values.append(text)
    variations = _compact_variations(explicit.get("variation_examples"))
    if not variations:
        for key in ("variation_axes", "adaptable_fields", "best_for", "extension_points"):
            variations = _compact_variations(record.get(key))
            if variations:
                break
    facets = extract_record_facets(kind, category, record)
    anchor_signature: dict[str, list[str]] = {}
    for facet in (
        "domain", "species", "body_build", "proportion", "coat_palette",
        "eye_feature", "head_hair", "hair_style", "hair_texture",
        "hair_color", "facial_hair", "mane", "ruff",
        "head_fur_placement", "head_feature", "wardrobe", "role",
    ):
        values = facets.get(facet) or []
        if values:
            anchor_signature[facet] = values
    return {
        "kind": kind,
        "category": category,
        "tier": "curated" if record.get("curation_status") == "curated" else "vocabulary",
        "discovery_group": infer_discovery_group(kind, record),
        "variant_of": infer_variant_of(kind, record),
        "outcome_summary": infer_outcome_summary(kind, record),
        "aliases": alias_values,
        "facets": facets,
        "anchor_signature": anchor_signature,
        "variation_examples": variations,
        "compatible_with": _compact_variations(explicit.get("compatible_with") or record.get("compatible_render_profile_ids")),
        "avoid_with": _compact_variations(explicit.get("avoid_with") or record.get("avoid_for")),
    }


@dataclass
class PhraseMatch:
    phrase: str
    associations: list[dict[str, Any]]


@dataclass
class CatalogQueryInput:
    """Canonical-English retrieval request prepared by the calling agent.

    ``canonical_query`` is concise English craft language used by the lexical
    ranker. ``source_brief`` is retained only for audit and may be written in
    any language. Explicit facets are authoritative and do not depend on a
    maintained translation dictionary.
    """

    canonical_query: str
    domain: str | None = None
    anchors: dict[str, list[str]] = field(default_factory=dict)
    source_brief: str | None = None
    source_language: str | None = None
    unresolved_terms: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_query": self.canonical_query,
            "domain": self.domain,
            "anchors": self.anchors,
            "source_brief": self.source_brief,
            "source_language": self.source_language,
            "unresolved_terms": self.unresolved_terms,
        }


def catalog_query_from_mapping(data: Mapping[str, Any]) -> CatalogQueryInput:
    """Parse one structured query without translating the source brief."""
    global _CATALOG_QUERY_SCHEMA
    if _CATALOG_QUERY_SCHEMA is None:
        raw_schema = json.loads(CATALOG_QUERY_SCHEMA_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw_schema, dict):
            raise ValueError("catalog query schema must be an object")
        unsupported = unsupported_schema_keywords(raw_schema)
        if unsupported:
            raise ValueError(
                f"{CATALOG_QUERY_SCHEMA_PATH.name} uses schema keywords this validator "
                "does not implement: " + ", ".join(unsupported)
            )
        _CATALOG_QUERY_SCHEMA = raw_schema
    schema_errors = validate_against_schema(dict(data), _CATALOG_QUERY_SCHEMA)
    if schema_errors:
        raise ValueError(
            "catalog query schema validation failed: " + "; ".join(schema_errors)
        )
    raw_anchors = data.get("anchors") or {}
    if not isinstance(raw_anchors, Mapping):
        raise ValueError("catalog query anchors must be an object")
    anchors: dict[str, list[str]] = {}
    for facet, raw_values in raw_anchors.items():
        values = raw_values if isinstance(raw_values, list) else [raw_values]
        normalized_values: list[str] = []
        for value in values:
            raw_text = str(value or "").strip()
            folded_text = "".join(
                ch for ch in unicodedata.normalize("NFKD", raw_text)
                if not unicodedata.combining(ch)
            )
            if any(
                ord(ch) > 127 and unicodedata.category(ch).startswith("L")
                for ch in folded_text
            ):
                raise ValueError(
                    f"catalog query anchor `{facet}` must use canonical English wording: {raw_text!r}"
                )
            text = normalize(raw_text)
            if raw_text and not text:
                raise ValueError(
                    f"catalog query anchor `{facet}` has no canonical searchable terms: {raw_text!r}"
                )
            if text and text not in normalized_values:
                normalized_values.append(text)
        if normalized_values:
            anchors[str(facet)] = normalized_values
    canonical_query = str(data.get("canonical_query") or "").strip()
    if not canonical_query:
        canonical_query = " ".join(
            value for values in anchors.values() for value in values
        ).strip()
    unresolved = data.get("unresolved_terms") or []
    if not isinstance(unresolved, list):
        unresolved = [unresolved]
    unresolved_terms = [str(value).strip() for value in unresolved if str(value).strip()]
    return CatalogQueryInput(
        canonical_query=canonical_query,
        domain=str(data.get("domain") or "").strip() or None,
        anchors=anchors,
        source_brief=str(data.get("source_brief") or "").strip() or None,
        source_language=str(data.get("source_language") or "").strip() or None,
        unresolved_terms=unresolved_terms,
    )


@dataclass
class QueryAnalysis:
    query: str
    normalized_query: str
    domain: str | None
    source_brief: str | None = None
    source_language: str | None = None
    anchors: dict[str, list[str]] = field(default_factory=dict)
    anchor_evidence: list[dict[str, Any]] = field(default_factory=list)
    modifier_scope_evidence: list[dict[str, Any]] = field(default_factory=list)
    scoped_terms: dict[str, set[str]] = field(default_factory=dict)
    phrase_matches: list[PhraseMatch] = field(default_factory=list)
    associations_by_id: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    open_axes: list[str] = field(default_factory=list)
    terms_without_alias: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "canonical_query": self.query,
            "normalized_query": self.normalized_query,
            "source_brief": self.source_brief,
            "source_language": self.source_language,
            "domain": self.domain,
            "normalized_anchors": self.anchors,
            "anchor_evidence": self.anchor_evidence,
            "modifier_scope_evidence": self.modifier_scope_evidence,
            "open_axes": self.open_axes,
            "matched_alias_phrases": [match.phrase for match in self.phrase_matches],
            "terms_without_alias": self.terms_without_alias,
        }


class SearchIndex:
    """Runtime view of the canonical many-to-many lexical index."""

    def __init__(self, data: Mapping[str, Any]):
        self.records: dict[str, dict[str, Any]] = {
            str(key): dict(value)
            for key, value in (data.get("records") or {}).items()
            if isinstance(value, Mapping)
        }
        self.phrases: dict[str, list[dict[str, Any]]] = {}
        raw_phrases = data.get("phrases") or {}
        if not isinstance(raw_phrases, Mapping):
            raw_phrases = {}
        for phrase, values in raw_phrases.items():
            if isinstance(values, Mapping):
                values = [values]
            if not isinstance(values, list):
                continue
            normalized = normalize(phrase)
            if not normalized:
                continue
            rows = [dict(value) for value in values if isinstance(value, Mapping) and value.get("id")]
            if rows:
                self.phrases[normalized] = rows
        phrases_by_width: dict[int, set[str]] = {}
        for phrase in self.phrases:
            width = len(phrase.split())
            if width:
                phrases_by_width.setdefault(width, set()).add(phrase)
        self.phrase_widths = tuple(sorted(phrases_by_width, reverse=True))
        self._phrases_by_width = {
            width: frozenset(phrases)
            for width, phrases in phrases_by_width.items()
        }
        self.aliases_by_id: dict[str, list[str]] = {}
        for phrase, associations in self.phrases.items():
            for association in associations:
                rid = str(association.get("id") or "")
                if rid and phrase not in self.aliases_by_id.setdefault(rid, []):
                    self.aliases_by_id[rid].append(phrase)
        fingerprint_payload = json.dumps(
            {"records": self.records, "phrases": self.phrases},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        self.fingerprint = hashlib.sha256(
            fingerprint_payload.encode("utf-8")
        ).hexdigest()

    @classmethod
    def load(cls, path: Path) -> "SearchIndex":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            data = {"phrases": {}, "records": {}}
        return cls(data)

    def record_category(
        self,
        record_id: str,
        association: Mapping[str, Any] | None = None,
    ) -> str | None:
        """Return authored category context for one lexical association.

        Runtime cache rows deliberately preserve authored lexical tuples and
        therefore do not rewrite their facet. Category is read from explicit
        row/profile metadata when present. Vocabulary record IDs use their
        canonical category namespace, which supplies the same context when no
        runtime profile is materialized for that record.
        """
        if association:
            category = str(association.get("category") or "").strip()
            if category:
                return category
        profile = self.records.get(str(record_id), {})
        category = str(profile.get("category") or "").strip()
        if category:
            return category
        rid = str(record_id)
        for candidate in sorted(FACET_BY_CATEGORY, key=lambda value: (-len(value), value)):
            if rid == candidate or rid.startswith(candidate + "-"):
                return candidate
        return None

    def association_facet(self, association: Mapping[str, Any]) -> str:
        """Return the canonical facet authored on one lexical association."""
        return str(association.get("facet") or "")

    def association_for_analysis(self, association: Mapping[str, Any]) -> dict[str, Any]:
        return dict(association)

    def match_phrases(self, query: str) -> list[PhraseMatch]:
        tokens = normalize_query(query).split()
        seen: set[str] = set()
        matches: list[PhraseMatch] = []
        # Scan only widths present in the index, avoiding empty work for
        # nonexistent widths without imposing a phrase-length ceiling.
        for width in self.phrase_widths:
            if width > len(tokens):
                continue
            phrases_at_width = self._phrases_by_width[width]
            for start in range(0, len(tokens) - width + 1):
                phrase = " ".join(tokens[start:start + width])
                if phrase in seen or phrase not in phrases_at_width:
                    continue
                seen.add(phrase)
                matches.append(PhraseMatch(phrase, self.phrases[phrase]))
        return matches


def _record_anchor(
    analysis: QueryAnalysis,
    facet: str,
    value: str,
    source: str,
    confidence: str = "explicit",
    *,
    source_span: tuple[int, int] | None = None,
    governed_noun: str | None = None,
) -> None:
    normalized = normalize(value)
    if not normalized:
        return
    values = analysis.anchors.setdefault(facet, [])
    if normalized not in values:
        values.append(normalized)
    evidence: dict[str, Any] = {
        "facet": facet,
        "value": normalized,
        "source": source,
        "reason": source,
        "confidence": confidence,
    }
    if source_span is not None:
        start, end = source_span
        if 0 <= start <= end <= len(analysis.normalized_query):
            evidence["source_span"] = {
                "start": start,
                "end": end,
                "text": analysis.normalized_query[start:end],
            }
    if governed_noun:
        evidence["governed_noun"] = normalize(governed_noun)
    if evidence not in analysis.anchor_evidence:
        analysis.anchor_evidence.append(evidence)
    for token in tokens_of(normalized):
        analysis.scoped_terms.setdefault(token, set()).add(facet)


def _normalized_sentence_boundaries(query: Any) -> tuple[int, ...]:
    """Map hard sentence/clause punctuation into normalized-query offsets."""
    raw = str(query or "")
    positions = {
        len(normalize(raw[:match.start()]))
        for match in re.finditer(r"[.!?;:\r\n]+", raw)
    }
    return tuple(sorted(position for position in positions if position >= 0))


def _span_crosses_boundary(
    span: tuple[int, int],
    boundaries: Sequence[int],
) -> bool:
    start, end = span
    return any(start < boundary < end for boundary in boundaries)


def _governed_noun_after(
    query_norm: str,
    modifier_end: int,
    species_phrases: Sequence[str],
    scope_boundaries: Sequence[int] = (),
) -> tuple[str | None, str | None, int | None]:
    """Return the explicit local head noun and its facet, if one is present.

    Species phrases take precedence over generic noun cues. Otherwise the
    scan is deliberately short and stops at a clause barrier. Location words
    such as ``crown`` are retained only as fallbacks so ``crown clumps`` is
    governed by ``clumps`` rather than being mistaken for physique wording.
    """
    tail_limit = min(
        (
            boundary
            for boundary in scope_boundaries
            if boundary >= modifier_end
        ),
        default=len(query_norm),
    )
    raw_tail = query_norm[modifier_end:tail_limit]
    leading_space = len(raw_tail) - len(raw_tail.lstrip())
    tail_offset = modifier_end + leading_space
    tail = raw_tail.lstrip()
    if not tail:
        return None, None, None

    ordered_species = sorted(
        {normalize(value) for value in species_phrases if normalize(value)},
        key=lambda value: (-len(value.split()), -len(value), value),
    )
    for species in ordered_species:
        species_match = re.match(rf"{re.escape(species)}(?:\s|$)", tail)
        if species_match:
            return species, "species", tail_offset + len(species)

    fallback: tuple[str, str, int] | None = None
    unknown_heads: list[tuple[str, None, int]] = []
    unknown_starts: list[int] = []
    for index, match in enumerate(re.finditer(r"\b[a-z0-9-]+\b", tail)):
        if index >= 3:
            break
        token = match.group(0)
        if token in _MODIFIER_SCOPE_BARRIERS:
            break
        facet = _EXPLICIT_MODIFIER_HEAD_FACETS.get(token)
        if not facet:
            unknown_heads.append((token, None, tail_offset + match.end()))
            unknown_starts.append(match.start())
            continue
        if token in _MODIFIER_LOCATION_TOKENS:
            fallback = fallback or (token, facet, tail_offset + match.end())
            continue
        if facet == "identity_detail" and token in {"hair", "clump", "clumps", "strand", "strands", "lock", "locks", "tuft", "tufts"}:
            local_phrase = tail[:match.end()]
            if re.search(r"\b(?:head|scalp|crown)\b", local_phrase):
                facet = "head_hair"
        return token, facet, tail_offset + match.end()
    if fallback:
        return fallback
    # A species may sit behind one or two unknown words (``muscular young
    # wolf``). Re-match the species phrases at each unknown head position
    # before settling for a head noun that carries no facet at all.
    for start in unknown_starts:
        for species in ordered_species:
            if re.match(rf"{re.escape(species)}(?:\s|$)", tail[start:]):
                return species, "species", tail_offset + start + len(species)
    if unknown_heads:
        return unknown_heads[-1]
    return None, None, None


def _nearest_governed_species(
    query_norm: str,
    modifier_end: int,
    species_phrases: Sequence[str],
    scope_boundaries: Sequence[int],
) -> str | None:
    """Return the nearest locally governed species without crossing a barrier."""
    candidates: list[tuple[int, str]] = []
    for species in {normalize(value) for value in species_phrases if normalize(value)}:
        for match in re.finditer(rf"\b{re.escape(species)}\b", query_norm):
            if match.start() < modifier_end:
                continue
            if _span_crosses_boundary(
                (modifier_end, match.end()), scope_boundaries
            ):
                continue
            intervening = tokens_of(query_norm[modifier_end:match.start()])
            if len(intervening) > 5 or any(
                token in _MODIFIER_SCOPE_BARRIERS for token in intervening
            ):
                continue
            candidates.append((match.start(), species))
    return min(candidates, default=(0, None), key=lambda row: row[0])[1]


def _species_modifier_stack(
    query_norm: str,
    species: str,
    index: SearchIndex,
    scope_boundaries: Sequence[int],
) -> list[tuple[str, str, tuple[int, int]]]:
    """Return contiguous, locally governed physique modifiers for a species."""
    output: list[tuple[str, str, tuple[int, int]]] = []
    domain_terms = {
        normalize(term)
        for term in (*DOMAIN_TERMS.keys(), *DOMAIN_TERMS.values())
    }
    color_tokens = {
        token for color in COLOR_TERMS_SORTED for token in tokens_of(color)
    }
    normalized_species = normalize(species)
    for species_match in re.finditer(
        rf"\b{re.escape(normalized_species)}\b", query_norm
    ):
        if _span_crosses_boundary(species_match.span(), scope_boundaries):
            continue
        clause_start = max(
            (
                boundary
                for boundary in scope_boundaries
                if boundary <= species_match.start()
            ),
            default=0,
        )
        prefix = query_norm[clause_start:species_match.start()]
        token_matches = list(re.finditer(r"\b[a-z0-9-]+\b", prefix))
        for local_match in reversed(token_matches[-6:]):
            token = local_match.group(0)
            if token in _MODIFIER_SCOPE_BARRIERS:
                break
            if token in domain_terms or token in color_tokens:
                continue
            associations = index.phrases.get(token, [])
            facets = {
                index.association_facet(row)
                for row in associations
                if index.association_facet(row)
            }
            if token in BUILD_TERMS:
                selected_facet = "body_build"
            else:
                selected_facet = next(
                    (
                        facet
                        for facet in SPECIES_MODIFIER_FACET_PRIORITY
                        if facet in facets
                    ),
                    None,
                )
            if selected_facet:
                absolute_span = (
                    clause_start + local_match.start(),
                    clause_start + local_match.end(),
                )
                value = BUILD_CANONICAL.get(token, token)
                row = (selected_facet, value, absolute_span)
                if row not in output:
                    output.append(row)
                continue
            if facets & {"age", "presentation", "coat_palette", "marking"}:
                # Other locally recognized subject adjectives may coexist in
                # the same stack. They are anchored by their own lexical
                # rules and must not prevent an earlier physique modifier
                # from reaching the species head.
                continue
            # An unknown noun breaks the modifier stack. This is what keeps
            # `athletic socks <species>` from reclassifying athletic as body.
            break
    return sorted(output, key=lambda row: row[2])


_PERMANENT_TRAIT_NOUNS = frozenset({
    "hair", "hairstyle", "forelock", "forelocks", "bang", "bangs",
    "fringe", "mane", "manes", "ruff", "ruffs", "beard", "beards",
    "goatee", "goatees", "moustache", "moustaches", "mustache",
    "mustaches", "sideburn", "sideburns", "muzzle", "muzzles", "ear",
    "ears", "horn", "horns", "antler", "antlers", "crest", "crests",
    "whisker", "whiskers", "tuft", "tufts",
})

_PERMANENT_CONTEXT_BARRIERS = frozenset({
    "and", "or", "with", "wearing", "while", "under", "against",
    "beside", "near", "inside", "outside", "from", "into", "over",
    "scene", "camera", "lighting", "background", "outfit",
})


def _permanent_trait_context_tokens(query_norm: str) -> set[str]:
    """Return words locally describing a permanent hair/head trait.

    The result protects an unresolved trait adjective from being declared
    covered merely because the same word has a generic style or scene match.
    It is a local scope detector, not an enumeration of possible traits.
    """
    words = tokens_of(query_norm)
    cue_positions: set[int] = {
        index for index, word in enumerate(words)
        if word in _PERMANENT_TRAIT_NOUNS
    }
    for index, word in enumerate(words[:-1]):
        if word == "head" and words[index + 1] in {"hair", "fur", "feature", "features"}:
            cue_positions.update({index, index + 1})
        if word in {"crown", "brow", "cheek", "ear"} and words[index + 1] in {
            "fur", "tuft", "tufts", "clump", "clumps",
        }:
            cue_positions.update({index, index + 1})

    output: set[str] = set()
    for position in cue_positions:
        output.add(words[position])
        for direction in (-1, 1):
            for distance in range(1, 5):
                candidate_index = position + direction * distance
                if candidate_index < 0 or candidate_index >= len(words):
                    break
                candidate = words[candidate_index]
                if candidate in _PERMANENT_CONTEXT_BARRIERS:
                    break
                if candidate in STOPWORDS and candidate not in {"back", "forward"}:
                    break
                output.add(candidate)
    return output


def _record_permanent_hair_head_presence(
    analysis: QueryAnalysis,
    query_norm: str,
) -> None:
    """Preserve named structures without supplying an undeclared location.

    The old function name is kept for callers. A category is retrieval evidence,
    never an anatomical assertion. Explicit head location is needed for head
    facets; an unlocated structure remains an identity detail.
    """
    patterns = (
        ("facial_hair", r"\b(?:facial hair|beards?|goatees?|moustaches?|mustaches?|sideburns?|soul patch)\b"),
        ("mane", r"\bmanes?\b"),
        ("ruff", r"\b(?:neck |cheek |chest )?ruffs?\b"),
        ("head_fur_placement", r"\b(?:head|crown|brow|cheek|ear) fur\b|\b(?:ear|cheek|crown) tufts?\b"),
        ("head_feature", r"\b(?:head|cranial|skull) (?:[a-z-]+ ){0,2}(?:horns?|antlers?|crests?|features?)\b"),
        ("head_hair", r"\b(?:head hair|scalp hair|hairstyle|hair style|forelocks?|bangs?)\b"),
    )
    for facet, pattern in patterns:
        for match in re.finditer(pattern, query_norm):
            _record_anchor(analysis, facet, match.group(0),
                           "explicitly located or named structure; no anatomy inferred",
                           source_span=match.span(), governed_noun=match.group(0))
    # Bare hair/strands and projections are searchable without making them a
    # head part. Local noun phrases preserve even locations unknown to CPB.
    for match in re.finditer(r"\b(?:[a-z-]+ )?(?:hair|horns?|antlers?|crests?|strands?|tufts?|clumps?)\b", query_norm):
        phrase = match.group(0)
        if re.search(r"\b(?:head|scalp|crown|cranial|facial|ear|cheek|brow)\b", phrase):
            continue
        _record_anchor(analysis, "identity_detail", phrase,
                       "structure mention retained without assuming location or function",
                       source_span=match.span(), governed_noun=phrase)


def _find_color_contexts(
    query_norm: str,
    scope_boundaries: Sequence[int] = (),
) -> list[tuple[str, str, str, tuple[int, int], str]]:
    """Return color, facet, evidence, span, and governed noun tuples."""
    results: list[tuple[str, str, str, tuple[int, int], str]] = []
    target_patterns = (
        ("coat_palette", r"(?:fur|pelt|fleece)"),
        ("ambiguous_coat", r"coat"),
        ("eye_feature", r"eyes?"),
        ("hair_color", r"hair"),
        ("skin_tone", r"skin"),
        ("subject_surface", r"(?:feathers?|plumage|scales?|shell|carapace)"),
        ("lighting", r"(?:light|lighting|glow|rim light|backlight|illumination)"),
        ("environment", r"(?:background|room|wall|sky|field|interior|environment)"),
        (
            "wardrobe",
            r"(?:shorts|trousers|pants|shirt|jersey|jacket|uniform|outfit|"
            r"clothes|clothing|apron|robe|hoodie|armor|dress|skirt|socks?|"
            r"shoes?|boots?)",
        ),
    )
    # A color can sit a word or two away from the noun it actually governs, as
    # in ``blue field jacket`` or ``blue head hair``. Allow up to two
    # intervening modifiers, refuse a second color among them, and refuse a
    # target that is itself followed by another target word, because such a
    # target is not the head of the noun phrase.
    any_target = "(?:" + "|".join(target for _facet, target in target_patterns) + ")"
    any_color = "(?:" + "|".join(re.escape(color) for color in COLOR_TERMS_SORTED) + ")"
    modifier_run = rf"((?: (?!{any_color}\b)[a-z][a-z-]+){{0,2}})"
    head_guard = rf"(?!\s+{any_target}\b)"
    for color in COLOR_TERMS_SORTED:
        escaped = re.escape(color)
        for facet, target in target_patterns:
            patterns = (
                rf"\b{escaped}(?: colored)?{modifier_run} {target}\b{head_guard}",
                rf"\b{target} (?:in |with )?{escaped}\b",
                rf"\b{target} (?:is|are) {escaped}\b",
            )
            for position, pattern in enumerate(patterns):
                accepted = False
                for match in re.finditer(pattern, query_norm):
                    if _span_crosses_boundary(match.span(), scope_boundaries):
                        continue
                    if position == 0:
                        offset = match.start(1) - match.start(0)
                        governed_noun = normalize(match.group(0)[offset:])
                    else:
                        target_match = re.search(rf"\b{target}\b", match.group(0))
                        governed_noun = (
                            normalize(target_match.group(0)) if target_match else ""
                        )
                    resolved_facet = facet
                    if facet == "ambiguous_coat":
                        clause_start = max((b for b in scope_boundaries if b <= match.start()), default=0)
                        prefix = query_norm[max(clause_start, match.start() - 55):match.start()]
                        suffix = query_norm[match.end():match.end() + 35]
                        if re.search(r"\b(?:wearing|wears?|wore|dressed in|puts? on)\b[^,;]*$", prefix) or re.match(r" (?:with sleeves|with buttons|jacket)\b", suffix):
                            resolved_facet = "wardrobe"
                        elif re.match(r" (?:of |made of )?(?:fur|pelt|fleece)\b", suffix):
                            resolved_facet = "coat_palette"
                        else:
                            # Keep original wording available to retrieval, but
                            # do not assert garment or body-covering ownership.
                            continue
                    if facet == "hair_color" and not re.search(r"\b(?:head|scalp|hairstyle|hair style)\b", governed_noun):
                        resolved_facet = "subject_surface"
                    row = (
                        normalize(color),
                        resolved_facet,
                        match.group(0),
                        match.span(),
                        governed_noun,
                    )
                    if row not in results:
                        results.append(row)
                    accepted = True
                    break
                if accepted:
                    break
    return results


def analyze_query(
    query: str,
    index: SearchIndex,
    domain: str | None = None,
    *,
    explicit_anchors: Mapping[str, Sequence[str]] | None = None,
    source_brief: str | None = None,
    source_language: str | None = None,
    unresolved_terms: Sequence[str] | None = None,
) -> QueryAnalysis:
    """Analyze canonical English retrieval text plus optional explicit facets.

    The caller, normally the agent, performs language understanding and
    translation. Structured facets are authoritative and are applied before
    lexical inference so a compact canonical query does not lose user anchors.
    """
    query_norm = normalize(query)
    scope_boundaries = _normalized_sentence_boundaries(query)
    permanent_trait_tokens = _permanent_trait_context_tokens(query_norm)
    explicit_anchors = explicit_anchors or {}
    inferred_domain = domain
    if not inferred_domain:
        domain_values = explicit_anchors.get("domain") or []
        if domain_values:
            inferred_domain = str(next(iter(domain_values)))
    if not inferred_domain:
        for term, value in sorted(DOMAIN_TERMS.items(), key=lambda item: -len(item[0])):
            if re.search(rf"\b{re.escape(term)}\b", query_norm):
                inferred_domain = value
                break
    analysis = QueryAnalysis(
        query=str(query),
        normalized_query=query_norm,
        domain=inferred_domain,
        source_brief=source_brief,
        source_language=source_language,
    )
    for facet, values in explicit_anchors.items():
        for value in values:
            _record_anchor(analysis, str(facet), str(value), "structured query facet")
    if inferred_domain:
        _record_anchor(analysis, "domain", inferred_domain, "domain argument, structured facet, or explicit domain term")
        # Scope the wording that declared the domain as well as the canonical
        # domain value. This prevents the same surface word from contributing
        # to an unrelated indexed facet during ranking.
        for term, value in DOMAIN_TERMS.items():
            normalized_term = normalize(term)
            if (
                normalize(value) == normalize(inferred_domain)
                and re.search(rf"\b{re.escape(normalized_term)}\b", query_norm)
            ):
                for token in tokens_of(normalized_term):
                    analysis.scoped_terms.setdefault(token, set()).add("domain")
    _record_permanent_hair_head_presence(analysis, query_norm)

    analysis.phrase_matches = index.match_phrases(query_norm)
    for match in analysis.phrase_matches:
        for association in match.associations:
            rid = str(association.get("id") or "")
            if rid:
                projected = index.association_for_analysis(association)
                analysis.associations_by_id.setdefault(rid, []).append({
                    **projected,
                    "phrase": match.phrase,
                })

    # Species terms are taken from category-scoped lexical associations, not
    # from arbitrary prose occurrences. Prefer the longest visible species
    # phrase so "gray wolf" does not collapse to just "wolf".
    species_phrases: list[str] = []
    for match in analysis.phrase_matches:
        if any(
            association_names_species(match.phrase, row, index)
            for row in match.associations
        ):
            if match.phrase not in COLOR_TERMS and match.phrase not in BUILD_TERMS:
                species_phrases.append(match.phrase)
    selected_species_count = 0
    for phrase in sorted(
        set(species_phrases),
        key=lambda value: (-len(value.split()), -len(value), value),
    ):
        visible_spans = [
            match.span()
            for match in re.finditer(rf"\b{re.escape(phrase)}\b", query_norm)
            if not _span_crosses_boundary(match.span(), scope_boundaries)
        ]
        if not visible_spans:
            continue
        for span in visible_spans:
            _record_anchor(
                analysis,
                "species",
                phrase,
                "species lexical association in the canonical query",
                source_span=span,
                governed_noun=phrase,
            )
        selected_species_count += 1
        if selected_species_count >= 2:
            break

    # Broad family names are intentional species-scope requests even when no
    # concrete species record uses the family word as its label.
    for family_term in (
        "canine", "feline", "ursine", "avian", "aquatic",
        "reptile", "ungulate",
    ):
        for match in re.finditer(rf"\b{re.escape(family_term)}\b", query_norm):
            if _span_crosses_boundary(match.span(), scope_boundaries):
                continue
            _record_anchor(
                analysis,
                "species",
                family_term,
                "explicit broad species-family term in the canonical query",
                source_span=match.span(),
                governed_noun=family_term,
            )

    # Structured species anchors remain authoritative, but query-local
    # evidence must still augment them when their wording is visible.
    for species in analysis.anchors.get("species", []):
        if any(
            row.get("facet") == "species"
            and row.get("value") == normalize(species)
            and "source_span" in row
            for row in analysis.anchor_evidence
        ):
            continue
        for match in re.finditer(rf"\b{re.escape(species)}\b", query_norm):
            if _span_crosses_boundary(match.span(), scope_boundaries):
                continue
            _record_anchor(
                analysis,
                "species",
                species,
                "structured species wording present in the canonical query",
                source_span=match.span(),
                governed_noun=species,
            )

    # Record exact domain wording and its locally governed species even when
    # the canonical domain anchor was already supplied structurally.
    if inferred_domain:
        for term, value in DOMAIN_TERMS.items():
            if normalize(value) != normalize(inferred_domain):
                continue
            normalized_term = normalize(term)
            for match in re.finditer(
                rf"\b{re.escape(normalized_term)}\b", query_norm
            ):
                governed_species = _nearest_governed_species(
                    query_norm,
                    match.end(),
                    analysis.anchors.get("species", []),
                    scope_boundaries,
                )
                _record_anchor(
                    analysis,
                    "domain",
                    inferred_domain,
                    "explicit domain term in the canonical query",
                    source_span=match.span(),
                    governed_noun=governed_species,
                )

    # Route a locally attached stature/build modifier to its own identity
    # facet.  For ``tall maintenance robot``, ``maintenance robot`` remains the
    # species/form anchor while ``tall`` becomes proportion evidence.  The
    # same word in ``tall soda float`` remains available to the prop facet
    # because there is no adjacent species phrase.
    species_modifier_spans: set[tuple[str, int, int]] = set()
    for species in analysis.anchors.get("species", []):
        for facet, modifier, source_span in _species_modifier_stack(
            query_norm,
            species,
            index,
            scope_boundaries,
        ):
            _record_anchor(
                analysis,
                facet,
                modifier,
                f"{facet} modifier in the local species modifier stack",
                source_span=source_span,
                governed_noun=species,
            )
            species_modifier_spans.add((facet, *source_span))

    # Resolve explicit color governors before general lexical promotion. A
    # broad index association for ``blue`` must not outrank ``fur``, ``eyes``,
    # ``lighting``, ``clothing``, or ``room`` in the user's actual phrase.
    contextual_colors = _find_color_contexts(query_norm, scope_boundaries)
    for color, facet, evidence, source_span, governed_noun in contextual_colors:
        _record_anchor(
            analysis,
            facet,
            color,
            evidence,
            source_span=source_span,
            governed_noun=governed_noun,
        )

    # Explicit build language is an identity anchor even when the exact phrase
    # is absent from a preset label. Explicit local head nouns take priority:
    # ``athletic shorts`` scopes athletic to wardrobe, while ``muscular black
    # panther`` retains the intended body-build anchor.
    ambiguous_modifier_terms: list[str] = []
    consumed_build_spans = [
        (start, end)
        for facet, start, end in species_modifier_spans
        if facet == "body_build"
    ]
    for term in sorted(BUILD_TERMS, key=lambda value: (-len(value.split()), -len(value))):
        for match in re.finditer(rf"\b{re.escape(term)}\b", query_norm):
            if ("body_build", *match.span()) in species_modifier_spans:
                continue
            # ``broad built`` is scanned before ``broad``. A shorter build term
            # wholly inside an already consumed one is the same wording read
            # twice, not a second anchor.
            if any(
                start <= match.start() and match.end() <= end
                for start, end in consumed_build_spans
            ):
                continue
            consumed_build_spans.append(match.span())
            governed_noun, governed_facet, governed_end = _governed_noun_after(
                query_norm,
                match.end(),
                analysis.anchors.get("species", []),
                scope_boundaries,
            )
            if governed_facet and governed_facet not in {"species", "body_build"}:
                scoped_end = governed_end or match.end()
                _record_anchor(
                    analysis,
                    governed_facet,
                    query_norm[match.start():scoped_end],
                    f"explicit modifier governed by {governed_noun}",
                    source_span=(match.start(), scoped_end),
                    governed_noun=governed_noun,
                )
                continue
            if governed_noun and governed_facet is None:
                canonical = BUILD_CANONICAL.get(term, term)
                evidence = {
                    "value": canonical,
                    "facet": None,
                    "reason": (
                        "local governed noun has no deterministic facet; "
                        "modifier was not promoted to physique"
                    ),
                    "source_span": {
                        "start": match.start(),
                        "end": match.end(),
                        "text": query_norm[match.start():match.end()],
                    },
                    "governed_noun": governed_noun,
                }
                if evidence not in analysis.modifier_scope_evidence:
                    analysis.modifier_scope_evidence.append(evidence)
                if canonical not in ambiguous_modifier_terms:
                    ambiguous_modifier_terms.append(canonical)
                continue
            _record_anchor(
                analysis,
                "body_build",
                BUILD_CANONICAL.get(term, term),
                "explicit build descriptor",
                source_span=match.span(),
                governed_noun=governed_noun,
            )
    for term in sorted(PROPORTION_TERMS, key=lambda value: (-len(value.split()), -len(value))):
        for match in re.finditer(rf"\b{re.escape(term)}\b", query_norm):
            if _span_crosses_boundary(match.span(), scope_boundaries):
                continue
            _record_anchor(
                analysis,
                "proportion",
                term,
                "explicit proportion descriptor",
                source_span=match.span(),
                governed_noun=term.split()[-1],
            )

    # Scope explicit craft cue words before promoting lexical associations.
    # This prevents an ordinary word with several catalog meanings from being
    # adopted in the wrong role. In "ball near camera, low angle", camera and
    # low angle describe viewpoint; they must not become a physical camera
    # accessory or a body pose merely because such records also exist.
    cue_facets = {
        "head_hair": ("head hair", "hairstyle", "hair style", "forelock", "bangs", "fringe", "crown clump", "crown clumps"),
        "hair_style": ("head hair", "hairstyle", "hair style", "forelock", "bangs", "fringe", "crown clump", "crown clumps"),
        "hair_texture": ("head hair", "hair texture", "hairstyle", "hair style"),
        "hair_color": ("hair", "head hair", "hair color"),
        "facial_hair": ("facial hair", "beard", "goatee", "moustache", "mustache", "sideburns"),
        "mane": ("mane",),
        "ruff": ("ruff", "neck ruff", "cheek ruff", "chest ruff"),
        "head_fur_placement": ("head fur", "crown fur", "brow fur", "cheek fur", "ear fur", "ear tuft", "cheek tuft", "crown tuft"),
        "head_feature": ("head feature", "head horn", "head horns", "cranial crest"),
        "camera": ("camera", "angle", "close portrait", "wide angle", "low angle", "high angle", "overhead", "profile view", "bust", "full body"),
        "lighting": ("light", "lighting", "rim light", "backlight", "key light", "shadow", "highlight", "glow"),
        "environment": ("background", "room", "interior", "exterior", "street", "court", "forest", "studio", "water", "beach"),
        "wardrobe": ("outfit", "clothing", "clothes", "shorts", "trousers", "pants", "shirt", "jersey", "jacket", "uniform", "apron", "robe", "hoodie", "armor", "dress", "skirt", "socks", "shoes", "boots"),
        "pose": ("pose", "running", "standing", "seated", "reclining", "crouching", "jumping", "action"),
        "performance": ("expression", "gaze", "smile", "grin", "shy", "confident", "stern", "blushing"),
        "style": ("style", "cel", "anime", "cartoon", "painterly", "matte", "gloss", "photoreal", "3d"),
        "mood": ("mood", "warm", "intimate", "dramatic", "quiet", "playful", "regal", "nocturne"),
    }
    for facet, cues in cue_facets.items():
        for cue in cues:
            if re.search(rf"\b{re.escape(cue)}\b", query_norm):
                if facet == "hair_texture" and cue == "hair texture":
                    for token in permanent_trait_tokens:
                        analysis.scoped_terms.setdefault(token, set()).add("hair_texture")
                for token in tokens_of(cue):
                    analysis.scoped_terms.setdefault(token, set()).add(facet)

    # Promote exact lexical choices such as "elderly", "researcher",
    # "baseball cap", "low angle", or "soft window light" into scoped
    # anchors. Prefer longer phrases and high-authority label/author aliases.
    # This is what lets a sparse brief remain open without allowing discovery
    # lanes to replace the few choices the user actually supplied.
    lexical_candidates: list[tuple[int, float, str, str, str]] = []
    authoritative_sources = {
        "label", "pack-label", "author-alias", "pack-author-alias",
        "generated-label-alias",
    }
    for match in analysis.phrase_matches:
        words = match.phrase.split()
        for association in match.associations:
            facet = index.association_facet(association)
            source = str(association.get("source") or "")
            if facet not in LEXICAL_ANCHOR_FACETS:
                continue
            phrase_tokens = set(tokens_of(match.phrase))
            if (
                phrase_tokens & permanent_trait_tokens
                and facet not in PERMANENT_IDENTITY_FACETS
            ):
                continue
            # A bare color row from the hair-color category must not turn
            # `black panther` or `blue room` into character hair. It becomes a
            # hair-color anchor only when the query itself puts that color in
            # local hair/head context; `_find_color_contexts` handles the
            # explicit color-hair construction below.
            if facet == "hair_color" and not (
                phrase_tokens & permanent_trait_tokens
            ):
                continue
            # Single texture adjectives are useful focused lookups. In a
            # larger brief they need local hair/head context so `fluffy wolf`
            # is not silently interpreted as a hairstyle.
            if (
                facet == "hair_texture"
                and query_norm != match.phrase
                and not (phrase_tokens & permanent_trait_tokens)
            ):
                continue
            existing_scope = set().union(
                *(analysis.scoped_terms.get(token, set()) for token in words)
            ) if words else set()
            if match.phrase in COLOR_TERMS and not existing_scope:
                # A bare color with no local governor remains ambiguous. Do
                # not let one indexed label arbitrarily choose wardrobe,
                # lighting, environment, eyes, or another color-bearing facet.
                continue
            if existing_scope and facet not in existing_scope:
                continue
            # Single-word anchors need a canonical label or authored alias;
            # multiword associations are specific enough to preserve scope.
            if len(words) < 2 and source not in authoritative_sources:
                continue
            lexical_candidates.append((
                len(words),
                float(association.get("weight", 0.0)),
                facet,
                match.phrase,
                source,
            ))
    seen_lexical_facets: set[str] = set()
    for _width, _weight, facet, phrase, source in sorted(
        lexical_candidates,
        key=lambda row: (-row[0], -row[1], row[2], row[3]),
    ):
        if facet in seen_lexical_facets:
            continue
        _record_anchor(analysis, facet, phrase, f"{facet} lexical association ({source})")
        seen_lexical_facets.add(facet)

    # In animal-domain briefs, a color directly modifying a species is a coat
    # anchor unless the same phrase explicitly names eyes, light, environment,
    # or wardrobe. This covers compact briefs such as "blue wolf".
    if analysis.anchors.get("species") and not any(
        facet in analysis.anchors for facet in ("coat_palette", "eye_feature", "hair_color", "skin_tone", "lighting", "environment", "wardrobe")
    ):
        for color in COLOR_TERMS_SORTED:
            for species in analysis.anchors["species"]:
                match = re.search(
                    rf"\b{re.escape(color)} {re.escape(species)}\b",
                    query_norm,
                )
                if match and not _span_crosses_boundary(
                    match.span(), scope_boundaries
                ):
                    _record_anchor(
                        analysis,
                        "coat_palette",
                        normalize(color),
                        f"color modifies species: {color} {species}",
                        "contextual",
                        source_span=match.span(),
                        governed_noun=species,
                    )
                    break
            if "coat_palette" in analysis.anchors:
                break

    # Multiword lexical phrases are useful facet evidence. Single ambiguous
    # words are admitted only when a cue already scoped them.
    for match in analysis.phrase_matches:
        words = match.phrase.split()
        existing = set().union(*(analysis.scoped_terms.get(token, set()) for token in words)) if words else set()
        for association in match.associations:
            facet = index.association_facet(association)
            if not facet:
                continue
            if (
                set(tokens_of(match.phrase)) & permanent_trait_tokens
                and facet not in PERMANENT_IDENTITY_FACETS
            ):
                continue
            # Context already assigned words such as blue, wolf, and muscular
            # to coat/species/build. Do not let a generic lexical association
            # broaden them back into lighting, scene, eye color, or unrelated
            # role facets. Unscoped multiword phrases may introduce a facet.
            if existing and facet not in existing:
                continue
            if len(words) >= 2 or existing:
                for token in words:
                    analysis.scoped_terms.setdefault(token, set()).add(facet)

    present_facets = set(analysis.anchors)
    present_facets.update(facet for facets in analysis.scoped_terms.values() for facet in facets)
    analysis.open_axes = [
        axis for axis in DISCOVERY_AXES
        if not (AXIS_FACETS[axis] & present_facets)
    ]

    # Report wording that the deterministic catalog could not normalize. The
    # caller may preserve it verbatim, translate it semantically, add an alias,
    # or author a missing preset. It must never be silently discarded.
    covered_tokens: set[str] = set(DISCOVERY_CUE_TOKENS) - permanent_trait_tokens
    covered_tokens.update(_MODIFIER_SCOPE_BARRIERS)
    for match in analysis.phrase_matches:
        for token in tokens_of(match.phrase):
            if token not in permanent_trait_tokens:
                covered_tokens.add(token)
    for facet, values in analysis.anchors.items():
        for value in values:
            for token in tokens_of(value):
                if (
                    token not in permanent_trait_tokens
                    or facet in PERMANENT_IDENTITY_FACETS
                ):
                    covered_tokens.add(token)
    inferred_unmatched = [
        token for token in tokens_of(query_norm)
        if token not in STOPWORDS and token not in covered_tokens
    ]
    analysis.terms_without_alias = []
    for value in (
        list(unresolved_terms or [])
        + inferred_unmatched
        + ambiguous_modifier_terms
    ):
        text = str(value).strip()
        if text and text not in analysis.terms_without_alias:
            analysis.terms_without_alias.append(text)
    return analysis


def profile_aliases(index: SearchIndex, record_id: str) -> list[str]:
    profile = index.records.get(str(record_id), {})
    values = list(profile.get("aliases") or []) + list(index.aliases_by_id.get(str(record_id), []))
    output: list[str] = []
    for value in values:
        normalized = normalize(value)
        if normalized and normalized not in output:
            output.append(normalized)
    return output


def profile_for(index: SearchIndex, record_id: str) -> dict[str, Any]:
    return dict(index.records.get(str(record_id), {}))
