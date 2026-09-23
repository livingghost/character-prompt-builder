#!/usr/bin/env python3
"""Validate model records and apply provider-backed prompt recommendations.

The module is deliberately free of catalog and pack-runtime imports so it can
be used by pack validation, generation packaging, and isolated smoke tests
without creating an import cycle.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

# Every key a model record may carry: the common record fields and the model
# fields the pack record schema declares. The schema states the same set;
# validate.py holds the two to each other.
MODEL_RECORD_KEYS = frozenset(
    {
        "curation_status", "description", "domains", "id", "label", "search_profile",
        "search_terms", "tags",
        "aliases", "avoid_uses", "default_aspect_ratio_behavior",
        "input_image_count", "max_negative_prompt_chars", "max_outputs",
        "max_positive_prompt_chars", "max_reference_images", "negative_transport_mode",
        "negative_transport_notes", "offerings", "operation_kind", "ordering", "output_limits",
        "prompt_dialect", "prompt_style", "recommendation_merge_mode", "recommended_parameters",
        "recommended_negative_preset", "recommended_negative_prompt",
        "recommended_positive_prompt", "recommended_uses", "reference_input_media_types",
        "size_hints", "supported_aspect_ratios", "supported_resolutions",
        "supported_scale_factors", "supports_guidance_prompt", "supports_negative_prompt",
        "upscale_settings", "upscaler_class", "verified_on",
    }
)
# An offering is how one service exposes the model: its identifier there, the
# request key each input occupies, the limits that service enforces, and when
# that was observed. schema_snapshot points at the service's own parameter
# schema for the model, stored in the pack as observed.
OFFERING_KEYS = frozenset(
    {"service", "model_identifier", "request_keys", "constraints", "observed_at", "schema_snapshot", "setting_keys", "parameter_keys", "schema_contract", "schema_acquisition", "parameter_observations", "reference_schemas", "production_context_transport", "reference_instruction_transport"}
)
OFFERING_REQUIRED = ("service", "model_identifier", "request_keys", "constraints", "observed_at")
OBSERVED_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# The request_keys roles beside the media roles. Every generation offering names
# its prompt key. An offering with no negative key says the target has no
# negative field, and one with no model key says the address names the model.
PROMPT_ROLE = "prompt"
NEGATIVE_ROLE = "negative prompt"
MODEL_ROLE = "model"
# What stands in for an uploaded file when a request is checked before anything is uploaded.
PLACEHOLDER_MEDIA = "00000000-0000-4000-8000-000000000000"
# The roles a service can take prepared references on, best first. The offering
# says which of them this service uses; a role whose name ends in "images" holds
# a list, and the others hold one image.
GENERATION_MEDIA_ROLES = ("reference images", "seed image")

NEGATIVE_TRANSPORT_MODES = frozenset(
    {
        "separate-field",
        "integrated-critical",
        "native-subset",
        "retained-only",
    }
)
MODEL_OPERATION_KINDS = frozenset({"generation", "instruction-edit", "upscale"})
UPSCALER_CLASSES = frozenset({"restorative", "generative", "creative"})
RECOMMENDATION_MERGE_MODES = frozenset({"advisory-only", "prefix", "tag-list"})
# What a model's author recommends for sampling, by service-neutral name. An
# offering's parameter_keys says which request key each occupies on that service;
# a single value is filled into a package where the package leaves it unset, and
# a two-number range is a statement for the person choosing, never a value sent.
RECOMMENDED_PARAMETER_KEYS = frozenset(
    {"sampler", "steps", "guidance", "clip_skip", "hires_scale", "hires_denoise", "hires_steps", "hires_upscaler"}
)


def _is_positive_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_nonnegative_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_nonempty_unique_strings(
    value: Any,
    field: str,
    errors: list[str],
) -> None:
    if value is None:
        return
    if not isinstance(value, list) or not value:
        errors.append(f"{field} must be a non-empty array when declared")
        return
    normalized: list[str] = []
    for index, item in enumerate(value):
        if not _nonempty_string(item):
            errors.append(f"{field}[{index}] must be a non-empty string")
        else:
            normalized.append(item.strip().casefold())
    if len(normalized) != len(set(normalized)):
        errors.append(f"{field} must not contain case-insensitive duplicates")


def _validate_offerings(record: Mapping[str, Any], errors: list[str]) -> None:
    offerings = record.get("offerings")
    if not isinstance(offerings, list):
        errors.append(
            "offerings must be an array: one entry per service that exposes the model here, "
            "empty when none does"
        )
        return
    services: list[Any] = []
    for index, offering in enumerate(offerings):
        where = f"offerings[{index}]"
        if not isinstance(offering, Mapping):
            errors.append(f"{where} must be an object")
            continue
        unknown = sorted(set(offering) - OFFERING_KEYS)
        if unknown:
            errors.append(f"{where} has unknown keys {unknown}")
        for name in OFFERING_REQUIRED:
            if name not in offering:
                errors.append(f"{where}.{name} is required")
        for name in ("service", "model_identifier"):
            if name in offering and not _nonempty_string(offering[name]):
                errors.append(f"{where}.{name} must be a non-empty string")
        keys = offering.get("request_keys")
        if "request_keys" in offering:
            if not isinstance(keys, Mapping):
                errors.append(f"{where}.request_keys must be an object")
            else:
                for role, mapped in keys.items():
                    if (
                        not _nonempty_string(role)
                        or not isinstance(mapped, list)
                        or not mapped
                        or not all(_nonempty_string(key) for key in mapped)
                    ):
                        errors.append(
                            f"{where}.request_keys[{role!r}] must map a role to a "
                            "non-empty array of request keys"
                        )
                if record.get("operation_kind") in {"generation", "instruction-edit"} and PROMPT_ROLE not in keys:
                    errors.append(f"{where}.request_keys must name the request key of the {PROMPT_ROLE!r}")
        if "constraints" in offering and not isinstance(offering["constraints"], Mapping):
            errors.append(f"{where}.constraints must be an object")
        observed = offering.get("observed_at")
        if "observed_at" in offering and not (isinstance(observed, str) and OBSERVED_DATE.match(observed)):
            errors.append(f"{where}.observed_at must be a date written as YYYY-MM-DD")
        if "schema_snapshot" in offering and not _nonempty_string(offering["schema_snapshot"]):
            errors.append(f"{where}.schema_snapshot must be a non-empty path when declared")
        from execution_contract import exact, sha, text
        try:
            def file_reference(ref):
                exact(ref, {'path','sha256'}, 'offering evidence');text(ref['path'],'offering evidence path');sha(ref['sha256'])
            for field in ('schema_contract','schema_acquisition'):
                if field in offering:file_reference(offering[field])
            if ('schema_contract' in offering) != ('schema_acquisition' in offering):
                raise ValueError('schema contract and acquisition must be selected together')
            for ref in offering.get('reference_schemas',[]):file_reference(ref)
            for item in offering.get('parameter_observations',[]):
                exact(item, {'observation','profile','target','outcome'}, 'offering observation')
                file_reference(item['observation'])
                if item['profile'] is not None:file_reference(item['profile'])
                if item['outcome'] not in {'rejected','accepted','completed','indeterminate'}:raise ValueError('invalid observation outcome')
                if item['target']['service']!=offering['service'] or item['target']['model_identifier']!=offering['model_identifier']:
                    raise ValueError('observation belongs to another offering')
            if 'production_context_transport' in offering and offering['production_context_transport'] not in {'none','prompt-prefix'}:
                raise ValueError('unknown production context transport')
            if 'reference_instruction_transport' in offering:
                value=offering['reference_instruction_transport'];exact(value,{'mode','contract'},'reference instruction policy')
                if value['mode'] not in {'native-fields','authored-rendition','prompt-prefix','not-supported'}:raise ValueError('unknown reference instruction transport')
                file_reference(value['contract'])
        except (ValueError,KeyError,TypeError) as exc:
            errors.append(f"{where}: {exc}")
        setting_keys = offering.get("setting_keys")
        if "setting_keys" in offering and (
            not isinstance(setting_keys, Mapping)
            or not all(_nonempty_string(name) and _nonempty_string(key) for name, key in setting_keys.items())
        ):
            errors.append(f"{where}.setting_keys must map each setting name to a non-empty request key")
        parameter_keys = offering.get("parameter_keys")
        if "parameter_keys" in offering and (
            not isinstance(parameter_keys, Mapping)
            or not all(name in RECOMMENDED_PARAMETER_KEYS and _nonempty_string(key) for name, key in parameter_keys.items())
        ):
            errors.append(
                f"{where}.parameter_keys must map names from {sorted(RECOMMENDED_PARAMETER_KEYS)} to non-empty request keys"
            )
        service = offering.get("service")
        if service in services:
            errors.append(f"{where} repeats the service {service!r}")
        services.append(service)


def validate_model_record(record: Mapping[str, Any]) -> list[str]:
    """Return semantic errors not expressible in the shared schema subset."""

    errors: list[str] = []
    record_id = str(record.get("id") or "<unknown>")
    unknown = sorted(set(record) - MODEL_RECORD_KEYS)
    if unknown:
        errors.append(f"unknown keys {unknown}")
    if "offerings" not in record:
        errors.append(
            "offerings is required: one entry per service that exposes the model here, "
            "or an empty array when none does"
        )
    else:
        _validate_offerings(record, errors)
    operation_kind = record.get("operation_kind")
    if operation_kind not in MODEL_OPERATION_KINDS:
        errors.append(
            f"operation_kind must be one of {sorted(MODEL_OPERATION_KINDS)}"
        )

    _validate_nonempty_unique_strings(record.get("recommended_uses"), "recommended_uses", errors)
    _validate_nonempty_unique_strings(record.get("avoid_uses"), "avoid_uses", errors)
    for name in (
        "recommended_positive_prompt",
        "recommended_negative_prompt",
        "recommended_negative_preset",
    ):
        if name in record and not _nonempty_string(record.get(name)):
            errors.append(f"{name} must be omitted rather than empty")
    if any(name in record for name in ("recommended_positive_prompt", "recommended_negative_prompt")):
        mode = record.get("recommendation_merge_mode")
        if mode not in RECOMMENDATION_MERGE_MODES:
            errors.append(
                "recommendation_merge_mode is required for recommended prompt text and must be "
                f"one of {sorted(RECOMMENDATION_MERGE_MODES)}"
            )
    elif "recommendation_merge_mode" in record and record.get("recommendation_merge_mode") not in RECOMMENDATION_MERGE_MODES:
        errors.append(
            f"recommendation_merge_mode must be one of {sorted(RECOMMENDATION_MERGE_MODES)}"
        )
    _validate_recommended_parameters(record, errors)

    if operation_kind == "upscale":
        forbidden = sorted(
            name
            for name in (
                "supports_negative_prompt",
                "negative_transport_mode",
                "negative_transport_notes",
                "max_positive_prompt_chars",
                "max_negative_prompt_chars",
                "max_reference_images",
                "max_outputs",
                "recommended_parameters",
            )
            if name in record
        )
        if forbidden:
            errors.append(
                "upscale records must not declare generation transport fields: "
                + ", ".join(forbidden)
            )
        if record.get("upscaler_class") not in UPSCALER_CLASSES:
            errors.append(f"upscaler_class must be one of {sorted(UPSCALER_CLASSES)}")
        scales = record.get("supported_scale_factors")
        if not isinstance(scales, list) or not scales:
            errors.append("supported_scale_factors must be a non-empty array")
        else:
            normalized_scales: list[float] = []
            for index, value in enumerate(scales):
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or value <= 1
                ):
                    errors.append(
                        f"supported_scale_factors[{index}] must be a number greater than 1"
                    )
                else:
                    normalized_scales.append(float(value))
            if len(normalized_scales) != len(set(normalized_scales)):
                errors.append("supported_scale_factors must be unique")
            if normalized_scales != sorted(normalized_scales):
                errors.append("supported_scale_factors must be sorted")
        if not _is_positive_integer(record.get("input_image_count")):
            errors.append("input_image_count must be a positive integer")
        if not isinstance(record.get("supports_guidance_prompt"), bool):
            errors.append("supports_guidance_prompt must be boolean")
        settings = record.get("upscale_settings")
        if not isinstance(settings, Mapping):
            errors.append("upscale_settings must be an object")
        else:
            for name, values in settings.items():
                if not _nonempty_string(name):
                    errors.append("upscale_settings keys must be non-empty strings")
                    continue
                if not isinstance(values, list) or not values:
                    errors.append(f"upscale_settings.{name} must be a non-empty array")
                    continue
                canonical_values = []
                for index, value in enumerate(values):
                    if not isinstance(value, (str, int, float, bool)):
                        errors.append(
                            f"upscale_settings.{name}[{index}] must be a string, number, or boolean"
                        )
                        continue
                    canonical_values.append((type(value).__name__, repr(value)))
                if len(canonical_values) != len(set(canonical_values)):
                    errors.append(f"upscale_settings.{name} must contain unique values")
        output_limits = record.get("output_limits")
        if output_limits is not None:
            if not isinstance(output_limits, Mapping) or not output_limits:
                errors.append("output_limits must be a non-empty object when declared")
            else:
                for name, value in output_limits.items():
                    if not _nonempty_string(name):
                        errors.append("output_limits keys must be non-empty strings")
                    if (
                        isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or value <= 0
                    ):
                        errors.append(f"output_limits.{name} must be a positive number")
        return [f"model record {record_id!r}: {error}" for error in errors]

    if operation_kind in {"generation", "instruction-edit"}:
        supports_negative = record.get("supports_negative_prompt")
        if not isinstance(supports_negative, (bool, str)) or (
            isinstance(supports_negative, str) and not supports_negative.strip()
        ):
            errors.append("supports_negative_prompt must be boolean or a non-empty channel name")
        mode = record.get("negative_transport_mode")
        if mode not in NEGATIVE_TRANSPORT_MODES:
            errors.append(
                f"negative_transport_mode must be one of {sorted(NEGATIVE_TRANSPORT_MODES)}"
            )
        if supports_negative is False and mode == "separate-field":
            errors.append("separate-field requires a declared negative prompt channel")
        if supports_negative not in (False, None) and mode == "integrated-critical":
            errors.append(
                "integrated-critical contradicts a declared independent negative prompt channel"
            )
        if operation_kind == "instruction-edit" and mode == "retained-only":
            errors.append("instruction-edit records must characterize a usable negative transport")

        for field in (
            "max_positive_prompt_chars",
            "max_negative_prompt_chars",
            "max_outputs",
        ):
            if field in record and not _is_positive_integer(record.get(field)):
                errors.append(f"{field} must be a positive integer")
        if "max_reference_images" in record and not _is_nonnegative_integer(
            record.get("max_reference_images")
        ):
            errors.append("max_reference_images must be a non-negative integer")
        max_refs = record.get("max_reference_images")
        media_types = record.get("reference_input_media_types")
        if _is_nonnegative_integer(max_refs):
            if max_refs == 0 and media_types:
                errors.append(
                    "reference_input_media_types must be omitted when max_reference_images is 0"
                )
            if max_refs > 0 and (not isinstance(media_types, list) or not media_types):
                errors.append(
                    "reference_input_media_types is required when max_reference_images is positive"
                )
        for field in ("supported_resolutions", "supported_aspect_ratios"):
            _validate_nonempty_unique_strings(record.get(field), field, errors)
        if "default_aspect_ratio_behavior" in record and not _nonempty_string(
            record.get("default_aspect_ratio_behavior")
        ):
            errors.append("default_aspect_ratio_behavior must be omitted rather than empty")

    return [f"model record {record_id!r}: {error}" for error in errors]


def model_reference_limit(record: Mapping[str, Any]) -> int | None:
    value = record.get("max_reference_images")
    return int(value) if _is_nonnegative_integer(value) else None


def _split_tags(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def _merge_tag_lists(recommended: str, authored: str) -> str:
    result: list[str] = []
    seen: set[str] = set()
    for item in [*_split_tags(recommended), *_split_tags(authored)]:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return ", ".join(result)


def _merge_one(authored: str, recommended: str, *, mode: str, limit: int | None, field: str) -> tuple[str, dict[str, Any]]:
    authored=authored.strip();recommended=recommended.strip()
    audit={'declared':bool(recommended),'applied':False,'mode':mode,
        'reason':'not-declared' if not recommended else 'advisory-only', 'recommended_text':recommended,
        'source_text':authored,'limit':limit,'segments':[]}
    if limit is not None and len(authored)>limit:raise ValueError(f'{field} exceeds the model limit of {limit} characters')
    def original():
        audit['segments']=[{'source_kind':'authored','start':0,'end':len(authored),'text':authored}] if authored else []
        return authored,audit
    if not recommended or mode=='advisory-only':return original()
    parts=[];segments=[];length=0
    def append(text,kind):
        nonlocal length
        if text:
            parts.append(text);segments.append({'source_kind':kind,'start':length,'end':length+len(text),'text':text});length+=len(text)
    if mode=='prefix':
        append(recommended,'model-setting')
        if authored:append('\n\n','model-setting');append(authored,'authored')
    elif mode=='tag-list':
        seen=set()
        for source,kind in ((recommended,'model-setting'),(authored,'authored')):
            for item in _split_tags(source):
                key=item.casefold()
                if key in seen:continue
                seen.add(key)
                if parts:append(', ','model-setting')
                append(item,kind)
    else:raise ValueError('unsupported recommendation merge mode: '+mode)
    merged=''.join(parts)
    if limit is not None and len(merged)>limit:
        audit['reason']='model-limit-preserved-authored-prompt';return original()
    audit.update(applied=True,reason='applied',segments=segments)
    return merged,audit


def validate_recommendation_audit(entry: dict, actual: str) -> None:
    expected,audit=_merge_one(entry['source_text'],entry['recommended_text'],mode=entry['mode'],limit=entry['limit'],field='prompt')
    if actual!=expected or entry!=audit:raise ValueError('recommendation audit differs from its recorded transformation')


def apply_positive_recommendation(
    record: Mapping[str, Any],
    *,
    prompt: str,
) -> tuple[str, dict[str, Any]]:
    """Apply only the reusable positive recommendation to one prompt rendition."""

    mode = str(record.get("recommendation_merge_mode") or "advisory-only")
    if mode not in RECOMMENDATION_MERGE_MODES:
        raise ValueError(f"invalid recommendation_merge_mode: {mode!r}")
    return _merge_one(
        prompt,
        str(record.get("recommended_positive_prompt") or ""),
        mode=mode,
        limit=(
            int(record["max_positive_prompt_chars"])
            if _is_positive_integer(record.get("max_positive_prompt_chars"))
            else None
        ),
        field="prompt",
    )


def apply_prompt_recommendations(
    record: Mapping[str, Any],
    *,
    prompt: str,
    negative_prompt: str,
) -> tuple[str, str, dict[str, Any]]:
    """Merge only provider-backed reusable recommendations into authored text.

    User-authored text always wins the character budget. If adding a
    recommendation would exceed a declared model limit, the recommendation is
    omitted rather than truncating the user's semantic prompt.
    """

    if record.get("operation_kind") == "upscale":
        raise ValueError("upscale records do not use the Generation Package prompt contract")
    mode = str(record.get("recommendation_merge_mode") or "advisory-only")
    if mode not in RECOMMENDATION_MERGE_MODES:
        raise ValueError(f"invalid recommendation_merge_mode: {mode!r}")
    positive, positive_audit = _merge_one(
        prompt,
        str(record.get("recommended_positive_prompt") or ""),
        mode=mode,
        limit=(
            int(record["max_positive_prompt_chars"])
            if _is_positive_integer(record.get("max_positive_prompt_chars"))
            else None
        ),
        field="prompt",
    )
    negative, negative_audit = _merge_one(
        negative_prompt,
        str(record.get("recommended_negative_prompt") or ""),
        mode=mode,
        limit=(
            int(record["max_negative_prompt_chars"])
            if _is_positive_integer(record.get("max_negative_prompt_chars"))
            else None
        ),
        field="negative_prompt",
    )
    audit = {
        "merge_mode": mode,
        "positive": positive_audit,
        "negative": negative_audit,
        "integrated": None,
        "negative_preset": str(record.get("recommended_negative_preset") or ""),
    }
    return positive, negative, audit


def select_offering(record: Mapping[str, Any], service: str | None) -> dict[str, Any] | None:
    """The offering a request goes through: the named service's, or the only one.

    A record with no offerings is exposed on no service here, so a request for
    it can be checked against the record and nothing else.
    """

    record_id = str(record.get("id") or "<unknown>")
    offerings = [item for item in (record.get("offerings") or []) if isinstance(item, Mapping)]
    if not offerings:
        if service:
            raise ValueError(
                f"model record {record_id!r} is exposed on no service here, so {service!r} cannot carry it"
            )
        return None
    if service:
        for offering in offerings:
            if offering.get("service") == service:
                return dict(offering)
        raise ValueError(
            f"model record {record_id!r} records no offering on service {service!r}; "
            f"it records {[item.get('service') for item in offerings]}"
        )
    if len(offerings) == 1:
        return dict(offerings[0])
    raise ValueError(
        f"model record {record_id!r} is exposed on several services "
        f"{[item.get('service') for item in offerings]}; name the one the request goes through"
    )


def offering_schema(offering: Mapping[str, Any], pack_root: Path | None) -> dict[str, Any] | None:
    """The observed parameter schema an offering points at, read from its pack."""

    relative = offering.get("schema_snapshot")
    if not relative:
        return None
    if pack_root is None:
        raise ValueError(
            "the pack holding the model record is unknown, so its observed parameter schema cannot be read"
        )
    path = Path(pack_root) / str(relative)
    if not path.is_file():
        raise ValueError(f"observed parameter schema {relative!r} is not in the pack")
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    schema = snapshot.get("schema") if isinstance(snapshot, Mapping) else None
    if not isinstance(schema, dict):
        raise ValueError(f"observed parameter schema {relative!r} carries no schema")
    return {"schema": schema, "observed_at": snapshot.get("observed_at")}


def place(instance: dict[str, Any], key_path: str, value: Any) -> None:
    """Write a value at a request key, whose dots name nested objects."""

    parts = key_path.split(".")
    target = instance
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value


def request_key(offering: Mapping[str, Any], role: str) -> str | None:
    """The request key the offering gives a role, or None where it records none."""

    mapped = (offering.get("request_keys") or {}).get(role)
    return str(mapped[0]) if mapped else None


def required_request_key(offering: Mapping[str, Any], role: str) -> str:
    """The request key the offering gives a role; a role with nowhere to go is refused."""

    key = request_key(offering, role)
    if key is None:
        raise ValueError(f"the offering on {offering.get('service')!r} records no request key for the {role!r}")
    return key


def request_instance(
    offering: Mapping[str, Any],
    parameters: Mapping[str, Any],
    *,
    prompt: str | None = None,
    negative_prompt: str | None = None,
    media_counts: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """The request as the service would see it, from what the package declares.

    The model identifier, the prompt, the negative and each media role go on the
    request keys the offering gives them. Media are stood in for by placeholders,
    because the request is checked before anything is uploaded. A role whose name
    ends in "images" occupies a list.
    """

    instance: dict[str, Any] = {}
    model_key = request_key(offering, MODEL_ROLE)
    if model_key is not None:
        place(instance, model_key, offering.get("model_identifier"))
    if prompt is not None:
        place(instance, required_request_key(offering, PROMPT_ROLE), prompt)
    if negative_prompt:
        place(instance, required_request_key(offering, NEGATIVE_ROLE), negative_prompt)
    for name, value in (parameters or {}).items():
        place(instance, str(name), value)
    for role, count in (media_counts or {}).items():
        if count:
            key = required_request_key(offering, role)
            place(instance, key, [PLACEHOLDER_MEDIA] * int(count) if role.endswith("images") else PLACEHOLDER_MEDIA)
    return instance


def generation_media_counts(offering: Mapping[str, Any], count: int) -> dict[str, int]:
    """The role this offering takes prepared references on, and how many go on it.

    One answer for the builder, the verifier and the transport, so that what is
    checked is what is sent. An offering that takes one image and a package that
    selected several is refused here rather than losing the rest in transit.
    """

    if not count:
        return {}
    keys = offering.get("request_keys") or {}
    for role in GENERATION_MEDIA_ROLES:
        if not keys.get(role):
            continue
        if not role.endswith("images") and count > 1:
            raise ValueError(
                f"the offering on {offering.get('service')!r} takes prepared references as {role!r}, "
                f"which is one image, and this package selects {count}; combine them into a single board"
            )
        return {role: int(count)}
    raise ValueError(
        f"the offering on {offering.get('service')!r} records no request key for prepared references; "
        f"one of {list(GENERATION_MEDIA_ROLES)} is needed to send them"
    )


def _validate_recommended_parameters(record: Mapping[str, Any], errors: list[str]) -> None:
    if "recommended_parameters" not in record:
        return
    value = record.get("recommended_parameters")
    if not isinstance(value, Mapping) or not value:
        errors.append("recommended_parameters must be a non-empty object")
        return
    for name, item in value.items():
        if name not in RECOMMENDED_PARAMETER_KEYS:
            errors.append(f"recommended_parameters[{name!r}] is not one of {sorted(RECOMMENDED_PARAMETER_KEYS)}")
            continue
        if isinstance(item, list):
            ends_are_numbers = len(item) == 2 and all(
                isinstance(end, (int, float)) and not isinstance(end, bool) for end in item
            )
            if not ends_are_numbers or item[0] > item[1]:
                errors.append(f"recommended_parameters[{name!r}] must be a value or a two-number range [low, high]")
        elif isinstance(item, bool) or not isinstance(item, (str, int, float)) or (isinstance(item, str) and not item.strip()):
            errors.append(f"recommended_parameters[{name!r}] must be a value or a two-number range [low, high]")


def recommended_request_parameters(record: Mapping[str, Any], offering: Mapping[str, Any]) -> dict[str, Any]:
    """Each single-valued recommendation on the request key the offering gives it.

    A range is a statement for the person choosing, and a name the offering gives
    no key is not sent through that service.
    """

    keys = offering.get("parameter_keys") or {}
    placed: dict[str, Any] = {}
    for name, value in (record.get("recommended_parameters") or {}).items():
        key = keys.get(name)
        if key and not isinstance(value, list):
            placed[str(key)] = value
    return placed


def _fillable(instance: Mapping[str, Any], key_path: str) -> bool:
    """True when the key is unset and every branch above it is already there.

    A recommendation fills a value the package left out. It does not switch a
    feature on: a key under an envelope the package never asked for, such as the
    upscaler of a second pass the package does not run, stays unwritten.
    """

    parts = key_path.split(".")
    node: Any = instance
    for part in parts[:-1]:
        if not isinstance(node, Mapping) or part not in node:
            return False
        node = node[part]
    return isinstance(node, Mapping) and parts[-1] not in node


def apply_recommended_parameters(
    record: Mapping[str, Any], offering: Mapping[str, Any], parameters: Mapping[str, Any]
) -> dict[str, Any]:
    """The parameters with the record's recommendations filled in where the package leaves them unset."""

    merged: dict[str, Any] = json.loads(json.dumps(dict(parameters)))
    for key_path, value in recommended_request_parameters(record, offering).items():
        if _fillable(merged, key_path):
            place(merged, key_path, value)
    return merged


def _branches(nodes: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    out: list[Mapping[str, Any]] = []
    queue = list(nodes)
    while queue:
        node = queue.pop(0)
        out.append(node)
        for word in ("oneOf", "anyOf", "allOf"):
            queue.extend(branch for branch in (node.get(word) or []) if isinstance(branch, Mapping))
    return out


def property_schemas(schema: Mapping[str, Any], key_path: str) -> list[Mapping[str, Any]]:
    """The schema nodes a request key lands on, through every oneOf, anyOf, and allOf branch on the way."""

    nodes: list[Mapping[str, Any]] = [schema]
    for part in key_path.split("."):
        found = [
            child
            for node in _branches(nodes)
            for child in [(node.get("properties") or {}).get(part)]
            if isinstance(child, Mapping)
        ]
        if not found:
            return []
        nodes = found
    return nodes


def recommended_parameter_issues(
    record: Mapping[str, Any], offering: Mapping[str, Any], pack_root: Path | None
) -> list[str]:
    """What the service's observed schema refuses among the record's recommendations on this offering."""

    keys = offering.get("parameter_keys") or {}
    if not keys:
        return []
    try:
        found = offering_schema(offering, pack_root)
    except ValueError as exc:
        return [str(exc)]
    if found is None:
        return []
    from state_protocol import validate_against_schema

    issues: list[str] = []
    service = offering.get("service")
    for name, value in (record.get("recommended_parameters") or {}).items():
        key = keys.get(name)
        if not key:
            continue
        nodes = property_schemas(found["schema"], str(key))
        if not nodes:
            issues.append(f"offering on {service!r}: the observed schema has no request key {key!r} for the recommended {name}")
            continue
        for candidate in (value if isinstance(value, list) else [value]):
            if all(validate_against_schema(candidate, dict(node)) for node in nodes):
                issues.append(f"offering on {service!r}: the observed schema refuses {candidate!r} at {key!r} for the recommended {name}")
    return issues


def validate_generation_parameters(
    record: Mapping[str, Any],
    parameters: Mapping[str, Any],
    *,
    service: str | None = None,
    pack_root: Path | None = None,
    prompt: str | None = None,
    negative_prompt: str | None = None,
    media_counts: Mapping[str, int] | None = None,
    output_count: int | None = None,
) -> dict[str, Any] | None:
    """Refuse parameters the record or the service's observed schema refuses.

    The record's own limits are checked first, the output count among them when
    the caller knows it. Then the offering the request goes through is selected,
    the request is built as the service would see it, and when the offering
    points at an observed parameter schema it is evaluated against that schema.
    Returns the offering, or None when the record is exposed on no service here.
    """

    limit = record.get("max_outputs")
    if output_count is not None:
        if not _is_positive_integer(output_count):
            raise ValueError("the output count must be a positive integer")
        if _is_positive_integer(limit) and output_count > limit:
            raise ValueError(f"an output count of {output_count} exceeds model max_outputs={limit}")
    offering = select_offering(record, service)
    if offering is None:
        return None
    instance = request_instance(
        offering, parameters, prompt=prompt, negative_prompt=negative_prompt, media_counts=media_counts
    )
    validate_request_instance(offering, instance, pack_root)
    return offering


def validate_request_instance(offering: Mapping[str, Any], instance: Mapping[str, Any], pack_root: Path | None) -> None:
    """Refuse a request the offering's observed parameter schema refuses; an offering without one refuses nothing."""

    found = offering_schema(offering, pack_root)
    if found is None:
        return
    from state_protocol import validate_against_schema

    violations = list(dict.fromkeys(validate_against_schema(dict(instance), found["schema"])))
    if violations:
        raise ValueError(
            f"the service's parameter schema for {offering.get('model_identifier')!r} "
            f"(observed {found.get('observed_at') or 'undated'}) refuses this request: "
            + "; ".join(violations)
        )
