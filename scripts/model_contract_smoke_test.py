#!/usr/bin/env python3
"""Exercise core model semantics with self-contained synthetic fixtures."""
from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path
from typing import Any, Callable

from model_contract import (
    NEGATIVE_TRANSPORT_MODES,
    PLACEHOLDER_MEDIA,
    apply_prompt_recommendations,
    model_reference_limit,
    request_instance,
    select_offering,
    size_fields,
    validate_generation_parameters,
    validate_model_record,
)
from model_contract import apply_recommended_parameters  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EXPECTED_CHECKS = 62


def load_core_models() -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Load only the package-owned default pack; external/user packs are out of scope."""

    models: dict[str, dict[str, Any]] = {}
    observed_ids: list[str] = []
    for path in sorted((ROOT / "packs/commons").glob("records/**/*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("kind") != "model":
            continue
        for record in value.get("records") or []:
            model_id = str(record["id"])
            observed_ids.append(model_id)
            models[model_id] = record
    return models, observed_ids


def fixture_models() -> dict[str, dict[str, Any]]:
    """Return synthetic records that exercise the model contract without user data."""

    return {
        "fixture-separate-edit": {
            "id": "fixture-separate-edit",
            "offerings": [],
            "operation_kind": "instruction-edit",
            "supports_negative_prompt": True,
            "negative_transport_mode": "separate-field",
            "max_reference_images": 3,
            "max_positive_prompt_chars": 32000,
            "max_negative_prompt_chars": 16000,
        },
        "fixture-integrated-edit": {
            "id": "fixture-integrated-edit",
            "offerings": [],
            "operation_kind": "instruction-edit",
            "supports_negative_prompt": False,
            "negative_transport_mode": "integrated-critical",
            "max_reference_images": 14,
            "max_positive_prompt_chars": 45000,
        },
        "fixture-output-limited-edit": {
            "id": "fixture-output-limited-edit",
            "offerings": [],
            "operation_kind": "instruction-edit",
            "supports_negative_prompt": False,
            "negative_transport_mode": "integrated-critical",
            "max_reference_images": 3,
            "max_outputs": 10,
        },
        "fixture-restorative-upscaler": {
            "id": "fixture-restorative-upscaler",
            "offerings": [],
            "operation_kind": "upscale",
            "upscaler_class": "restorative",
            "supported_scale_factors": [2, 4],
            "input_image_count": 1,
            "supports_guidance_prompt": False,
            "upscale_settings": {"variant": ["general"]},
        },
        "fixture-creative-upscaler": {
            "id": "fixture-creative-upscaler",
            "offerings": [],
            "operation_kind": "upscale",
            "upscaler_class": "creative",
            "supported_scale_factors": [2, 4, 8],
            "input_image_count": 1,
            "supports_guidance_prompt": True,
            "upscale_settings": {
                "creativity": ["low", "high"],
                "plan": ["personal", "pro"],
            },
            "output_limits": {"personal_megapixels": 32, "pro_megapixels": 100},
        },
        "fixture-generative-upscaler": {
            "id": "fixture-generative-upscaler",
            "offerings": [],
            "operation_kind": "upscale",
            "upscaler_class": "generative",
            "supported_scale_factors": [2, 3, 4],
            "input_image_count": 1,
            "supports_guidance_prompt": False,
            "upscale_settings": {"enhancement_strength": ["low", "medium", "high"]},
        },
        "fixture-tag-list-generator": {
            "id": "fixture-tag-list-generator",
            "offerings": [],
            "operation_kind": "generation",
            "supports_negative_prompt": True,
            "negative_transport_mode": "separate-field",
            "recommended_positive_prompt": "masterpiece, best quality",
            "recommended_negative_prompt": "worst quality, lowres",
            "recommendation_merge_mode": "tag-list",
        },
        "fixture-advisory-generator": {
            "id": "fixture-advisory-generator",
            "offerings": [],
            "operation_kind": "generation",
            "supports_negative_prompt": True,
            "negative_transport_mode": "separate-field",
            "recommended_positive_prompt": "{best quality}, {amazing quality}",
            "recommended_negative_preset": "Synthetic provider preset",
            "recommendation_merge_mode": "advisory-only",
        },
    }


def expect_error(fn: Callable[[], Any], text: str) -> bool:
    try:
        fn()
    except (ValueError, TypeError) as exc:
        return text in str(exc)
    return False


def main() -> int:
    models, observed_ids = load_core_models()
    fixtures = fixture_models()
    results: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: Any = None) -> None:
        results.append({"name": name, "passed": bool(passed), "detail": detail})

    errors = {
        model_id: validate_model_record(record)
        for model_id, record in models.items()
        if validate_model_record(record)
    }
    check("all core model records satisfy the semantic contract", not errors, errors)
    check("core model IDs are unique", len(models) == len(observed_ids), observed_ids)
    check(
        "all core generation transports use the executable enum",
        all(
            record.get("operation_kind") == "upscale"
            or record.get("negative_transport_mode") in NEGATIVE_TRANSPORT_MODES
            for record in models.values()
        ),
    )
    separate_edit = fixtures["fixture-separate-edit"]
    check("separate-field fixture uses a separate negative field", separate_edit.get("negative_transport_mode") == "separate-field")
    check("separate-field fixture declares negative support", separate_edit.get("supports_negative_prompt") is True)
    check("separate-field fixture declares three references", model_reference_limit(separate_edit) == 3)
    check("separate-field fixture declares a positive limit", separate_edit.get("max_positive_prompt_chars") == 32000)
    check("separate-field fixture declares a negative limit", separate_edit.get("max_negative_prompt_chars") == 16000)

    integrated_edit = fixtures["fixture-integrated-edit"]
    check("integrated fixture uses critical integrated transport", integrated_edit.get("negative_transport_mode") == "integrated-critical")
    check("integrated fixture declares fourteen references", model_reference_limit(integrated_edit) == 14)
    check("integrated fixture declares its instruction limit", integrated_edit.get("max_positive_prompt_chars") == 45000)

    output_limited = fixtures["fixture-output-limited-edit"]
    check("output-limited fixture uses critical integrated transport", output_limited.get("negative_transport_mode") == "integrated-critical")
    check("output-limited fixture declares three references", model_reference_limit(output_limited) == 3)
    check("output-limited fixture declares ten outputs", output_limited.get("max_outputs") == 10)
    check(
        "output-limited fixture rejects counts above its contract",
        expect_error(lambda: validate_generation_parameters(output_limited, {}, output_count=11), "max_outputs=10"),
    )
    validate_generation_parameters(output_limited, {}, output_count=10)
    check("output-limited fixture accepts its ceiling", True)

    upscalers = [
        fixtures[model_id]
        for model_id in (
            "fixture-restorative-upscaler",
            "fixture-creative-upscaler",
            "fixture-generative-upscaler",
        )
    ]
    check("three synthetic upscaler classes are covered", len(upscalers) == 3, [r["id"] for r in upscalers])
    generation_fields = {
        "supports_negative_prompt",
        "negative_transport_mode",
        "negative_transport_notes",
        "max_positive_prompt_chars",
        "max_negative_prompt_chars",
        "max_reference_images",
        "max_outputs",
    }
    check(
        "upscaler fixtures do not declare generation transport fields",
        all(not (generation_fields & set(record)) for record in upscalers),
    )
    check(
        "upscaler fixtures declare supported scales and settings",
        all(record.get("supported_scale_factors") and record.get("upscale_settings") for record in upscalers),
    )

    tag_list = fixtures["fixture-tag-list-generator"]
    merged_positive, merged_negative, audit = apply_prompt_recommendations(
        tag_list,
        prompt="best quality, fox character",
        negative_prompt="lowres, extra limbs",
    )
    check("tag-list recommendations deduplicate authored positive tags", merged_positive.count("best quality") == 1, merged_positive)
    check("tag-list recommendations retain authored semantics", "fox character" in merged_positive, merged_positive)
    check("tag-list recommendations deduplicate authored negative tags", merged_negative.count("lowres") == 1, merged_negative)
    check("recommendation audit records application", audit["positive"]["applied"] and audit["negative"]["applied"], audit)

    advisory = fixtures["fixture-advisory-generator"]
    advisory_prompt, advisory_negative, advisory_audit = apply_prompt_recommendations(
        advisory, prompt="wolf portrait", negative_prompt=""
    )
    check("advisory recommendations do not rewrite authored text", advisory_prompt == "wolf portrait" and advisory_negative == "")
    check("provider preset remains explicit audit data", bool(advisory_audit["negative_preset"]), advisory_audit)

    limited = copy.deepcopy(tag_list)
    limited["max_positive_prompt_chars"] = len("authored semantic prompt")
    limited_prompt, _negative, limited_audit = apply_prompt_recommendations(
        limited, prompt="authored semantic prompt", negative_prompt=""
    )
    check("model limits preserve authored text before recommendations", limited_prompt == "authored semantic prompt")
    check(
        "omitted recommendation records the model-limit reason",
        limited_audit["positive"]["reason"] == "model-limit-preserved-authored-prompt",
        limited_audit,
    )

    invalid = copy.deepcopy(separate_edit)
    invalid["negative_transport_mode"] = "not-a-transport-mode"
    check(
        "semantic validation rejects a transport value outside the enum",
        any("negative_transport_mode" in row for row in validate_model_record(invalid)),
    )

    # A record states every key it carries, and every service that exposes it.
    stray = copy.deepcopy(separate_edit)
    stray["default_parameters"] = "--stylize 100"
    check("a key the record contract does not declare is refused", any("unknown keys" in row for row in validate_model_record(stray)))
    unexposed = copy.deepcopy(separate_edit)
    del unexposed["offerings"]
    check("a record that does not say which services expose it is refused", any("offerings is required" in row for row in validate_model_record(unexposed)))
    offering = {
        "service": "svc",
        "model_identifier": "vendor:model@1",
        "request_keys": {"model": ["model"], "prompt": ["positivePrompt"], "reference images": ["inputs.referenceImages"]},
        "constraints": {"reference_images": {"max": 2}},
        "observed_at": "2026-09-13",
    }
    partial = copy.deepcopy(separate_edit)
    partial["offerings"] = [{"service": "svc"}]
    check("an offering missing its required fields is refused", any("is required" in row for row in validate_model_record(partial)))
    repeated = copy.deepcopy(separate_edit)
    repeated["offerings"] = [offering, dict(offering)]
    check("two offerings on one service are refused", any("repeats the service" in row for row in validate_model_record(repeated)))
    keyed = copy.deepcopy(separate_edit)
    keyed["offerings"] = [{**offering, "setting_keys": {"strength": "settings.enhancementStrength"}}]
    check("an offering may map the record's settings to request keys", validate_model_record(keyed) == validate_model_record(separate_edit))
    unkeyed = copy.deepcopy(separate_edit)
    unkeyed["offerings"] = [{**offering, "setting_keys": {"strength": ""}}]
    check("a setting mapped to no key is refused", any("setting_keys" in row for row in validate_model_record(unkeyed)))
    advised = copy.deepcopy(separate_edit)
    advised["recommended_parameters"] = {"sampler": "Euler a", "steps": [13, 25], "guidance": 4.5}
    check("recommended parameters with a parameters source add no error",
          validate_model_record(advised) == validate_model_record(separate_edit), validate_model_record(advised))
    misnamed = copy.deepcopy(advised)
    misnamed["recommended_parameters"] = {"cfg": 7}
    check("a recommended parameter outside the neutral names is refused",
          any("recommended_parameters['cfg']" in row for row in validate_model_record(misnamed)))
    mapped = copy.deepcopy(advised)
    mapped["offerings"] = [{**offering, "parameter_keys": {"sampler": "scheduler", "steps": "steps", "guidance": "CFGScale"}}]
    check("an offering may map recommended parameters to request keys",
          validate_model_record(mapped) == validate_model_record(separate_edit), validate_model_record(mapped))
    filled = apply_recommended_parameters(mapped, mapped["offerings"][0], {"width": 1024, "CFGScale": 6})
    check("single-valued recommendations fill unset request keys and a range does not",
          filled == {"width": 1024, "CFGScale": 6, "scheduler": "Euler a"}, filled)
    nested = copy.deepcopy(advised)
    nested["recommended_parameters"] = {"hires_upscaler": "vendor:upscaler@1"}
    nested["offerings"] = [{**offering, "parameter_keys": {"hires_upscaler": "hiresFix.model"}}]
    closed = apply_recommended_parameters(nested, nested["offerings"][0], {"width": 1024})
    check("a recommendation under an envelope the package never opened stays unwritten",
          closed == {"width": 1024}, closed)
    opened = apply_recommended_parameters(nested, nested["offerings"][0], {"width": 1024, "hiresFix": {"steps": 12}})
    check("the same recommendation fills the key once the package opens that envelope",
          opened == {"width": 1024, "hiresFix": {"steps": 12, "model": "vendor:upscaler@1"}}, opened)
    kept = apply_recommended_parameters(nested, nested["offerings"][0], {"hiresFix": {"model": "vendor:other@1"}})
    check("a value the package already set inside the envelope is kept",
          kept == {"hiresFix": {"model": "vendor:other@1"}}, kept)
    unmapped = copy.deepcopy(advised)
    unmapped["offerings"] = [{**offering, "parameter_keys": {"cfg": "CFGScale"}}]
    check("parameter_keys outside the neutral names are refused",
          any("parameter_keys" in row for row in validate_model_record(unmapped)))
    promptless = copy.deepcopy(separate_edit)
    promptless["offerings"] = [{**offering, "request_keys": {"reference images": ["inputs.referenceImages"]}}]
    check("a generation offering that names no prompt key is refused",
          any("request key of the 'prompt'" in row for row in validate_model_record(promptless)), validate_model_record(promptless))
    # The image size goes on two keys, or on one key as the text size_format writes.
    sized = copy.deepcopy(separate_edit)
    sized["offerings"] = [{**offering, "request_keys": {"prompt": ["prompt"], "size": ["size"]}, "size_format": "{width}x{height}"},
                          {**offering, "service": "ratio", "request_keys": {"prompt": ["prompt"], "size": ["input.aspect_ratio"]},
                           "size_format": "{ratio_width}:{ratio_height}"},
                          {**offering, "service": "sides", "request_keys": {"prompt": ["prompt"], "width": ["image_size.width"],
                                                                             "height": ["image_size.height"]}}]
    check("an offering may take the size on two keys or as one formatted text",
          validate_model_record(sized) == validate_model_record(separate_edit), validate_model_record(sized))
    placed_sizes = [size_fields(item, 832, 1248) for item in sized["offerings"]]
    check("the size is written on the keys and in the text each offering records",
          placed_sizes == [{"size": "832x1248"}, {"input.aspect_ratio": "2:3"}, {"image_size.width": 832, "image_size.height": 1248}]
          and size_fields(sized["offerings"][1], 1360, 768, ("16", "9")) == {"input.aspect_ratio": "16:9"}
          and size_fields(offering, 832, 1248) is None, placed_sizes)
    for label, broken in (
        ("a width without a height", {"request_keys": {"prompt": ["prompt"], "width": ["width"]}}),
        ("both a size and the two sides", {"request_keys": {"prompt": ["prompt"], "size": ["size"], "width": ["w"], "height": ["h"]},
                                           "size_format": "{width}x{height}"}),
        ("a size key with no format", {"request_keys": {"prompt": ["prompt"], "size": ["size"]}}),
        ("a format with no size key", {"size_format": "{width}x{height}"}),
        ("a format naming an unknown value", {"request_keys": {"prompt": ["prompt"], "size": ["size"]}, "size_format": "{width.real}"}),
    ):
        wrong = copy.deepcopy(separate_edit)
        wrong["offerings"] = [{**offering, **broken}]
        check(f"an offering recording {label} is refused", len(validate_model_record(wrong)) > len(validate_model_record(separate_edit)),
              validate_model_record(wrong))
    # The request as the service sees it puts each input on the key the offering gives it.
    placed = request_instance({"model_identifier": "vendor:model@1", "request_keys": {
        "prompt": ["input.text"], "negative prompt": ["input.avoid"], "reference images": ["refs"]}},
        {"size": "square"}, prompt="a wolf", negative_prompt="blurry", media_counts={"reference images": 1})
    check("the request as the service sees it carries the text and media on the offering's keys, and no model key it does not name",
          placed == {"input": {"text": "a wolf", "avoid": "blurry"}, "size": "square", "refs": [PLACEHOLDER_MEDIA]}, placed)
    check("a negative for an offering with no negative key is refused",
          expect_error(lambda: request_instance({"service": "svc", "request_keys": {"prompt": ["text"]}}, {},
                                                prompt="a wolf", negative_prompt="blurry"), "'negative prompt'"))
    exposed = copy.deepcopy(separate_edit)
    exposed["offerings"] = [offering]
    check(
        "a complete offering adds no error",
        validate_model_record(exposed) == validate_model_record(separate_edit),
        validate_model_record(exposed),
    )

    # Which offering a request goes through.
    check("a record exposed on no service selects no offering", select_offering(separate_edit, None) is None)
    check("naming a service for an unexposed record is refused", expect_error(lambda: select_offering(separate_edit, "svc"), "exposed on no service"))
    check("the only offering is selected without naming it", select_offering(exposed, None)["service"] == "svc")
    both = copy.deepcopy(exposed)
    both["offerings"] = [offering, {**offering, "service": "other"}]
    check("several offerings need the service named", expect_error(lambda: select_offering(both, None), "several services"))
    check("a service the record is not exposed on is refused", expect_error(lambda: select_offering(both, "third"), "records no offering"))

    # The request as the service would see it, against the observed schema.
    with tempfile.TemporaryDirectory() as tmp:
        pack = Path(tmp)
        snapshot = pack / "resources" / "observed-schemas" / "fixture.svc.json"
        snapshot.parent.mkdir(parents=True)
        snapshot.write_text(json.dumps({
            "observed_at": "2026-09-13",
            "schema": {
                "type": "object",
                "properties": {
                    "model": {"const": "vendor:model@1"},
                    "positivePrompt": {"type": "string", "minLength": 1},
                    "width": {"type": "integer"},
                    "height": {"type": "integer"},
                    "inputs": {
                        "type": "object",
                        "properties": {"referenceImages": {"type": "array", "maxItems": 2}},
                        "additionalProperties": False,
                    },
                },
                "required": ["model", "positivePrompt"],
                "allOf": [{"dependentRequired": {"width": ["height"], "height": ["width"]}}],
                "additionalProperties": False,
            },
        }), encoding="utf-8")
        checked = copy.deepcopy(exposed)
        checked["offerings"][0]["schema_snapshot"] = "resources/observed-schemas/fixture.svc.json"
        check(
            "a request within the observed schema passes and returns the offering",
            (validate_generation_parameters(checked, {"width": 1024, "height": 1024}, pack_root=pack, prompt="a wolf", media_counts={"reference images": 2}) or {}).get("service") == "svc",
        )
        check(
            "a parameter the observed schema refuses is refused",
            expect_error(lambda: validate_generation_parameters(checked, {"width": 1024}, pack_root=pack, prompt="a wolf"), "refuses this request"),
        )
        check(
            "more media than the observed schema accepts is refused",
            expect_error(lambda: validate_generation_parameters(checked, {}, pack_root=pack, prompt="a wolf", media_counts={"reference images": 3}), "refuses this request"),
        )
        check(
            "an offering with a schema needs its pack to be known",
            expect_error(lambda: validate_generation_parameters(checked, {}, prompt="a wolf"), "pack holding the model record is unknown"),
        )

    report = {
        "ok": len(results) == EXPECTED_CHECKS and all(row["passed"] for row in results),
        "checks": len(results),
        "expected_checks": EXPECTED_CHECKS,
        "results": results,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
