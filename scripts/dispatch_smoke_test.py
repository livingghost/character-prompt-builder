#!/usr/bin/env python3
"""Exercise the dispatcher's request building and its refusals without touching a service."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import dispatch  # noqa: E402
import studio  # noqa: E402
import transport_runware  # noqa: E402

EXPECTED_CHECKS = 26

SERVICE = {"endpoint": {"base_url": "https://example.invalid/v1", "method": "POST"}, "operations": {"imageInference": {}}, "auth": {"env_var": "EXAMPLE_KEY"}}
OFFERING = {
    "service": "svc",
    "model_identifier": "vendor:model@1",
    "request_keys": {"reference images": ["inputs.referenceImages"]},
    "constraints": {"as_written": {"settings": {"promptExpansion": "disabled"}}},
    "observed_at": "2026-09-13",
}
SNAPSHOT = "resources/observed-schemas/fixture.svc.json"
# A service that takes a count and no seed at all: what a dispatch adds is as
# refusable as anything the package carries.
ADDED_SCHEMA = {
    "type": "object",
    "properties": {
        "model": {"type": "string", "const": "vendor:model@1"},
        "positivePrompt": {"type": "string", "minLength": 1},
        "negativePrompt": {"type": "string", "minLength": 1},
        "width": {"type": "integer"},
        "height": {"type": "integer"},
        "settings": {"type": "object"},
        "numberResults": {"type": "integer", "minimum": 1, "maximum": 4},
    },
    "required": ["model", "positivePrompt"],
    "additionalProperties": False,
}


def verified(mode: str, negative: str, references: int) -> dict[str, Any]:
    return {
        "model": "fixture",
        "host_forwarding": {
            "effective_prompt": "a heron on a post",
            "parameters": {"width": 1024, "height": 1024, "settings": {"quality": "medium"}},
            "selected_transport": {"mode": mode, "rendition": {"negative": negative}},
            "selected_references": [
                {"role": "identity", "resolved_path": f"C:/refs/ref-{index}.png", "media_type": "image/png", "sha256": "0" * 64}
                for index in range(references)
            ],
        },
    }


def refused(fn, text: str) -> bool:
    try:
        fn()
    except (SystemExit, ValueError) as exc:
        return text in str(exc)
    return False


def main() -> int:
    results: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: Any = None) -> None:
        results.append({"name": name, "passed": bool(passed), "detail": detail})

    task = transport_runware.build(verified("separate-field", "blurry", 2), OFFERING, SERVICE, {"C:/refs/ref-0.png": "u0", "C:/refs/ref-1.png": "u1"}, seed=7, count=2)
    check("the request carries the model identifier, the effective prompt, and the parameters as sent",
          task["model"] == "vendor:model@1" and task["positivePrompt"] == "a heron on a post" and task["width"] == 1024 and task["settings"]["quality"] == "medium", task)
    check("a separate-field negative travels on negativePrompt", task.get("negativePrompt") == "blurry")
    check("references are placed under the offering's request key by uploaded id", task["inputs"]["referenceImages"] == ["u0", "u1"])
    check("seed and count are sent", task["seed"] == 7 and task["numberResults"] == 2)
    check("the offering's as_written keys are set where the parameters left them unset", task["settings"]["promptExpansion"] == "disabled")
    integrated = transport_runware.build(verified("integrated-critical", "blurry", 0), OFFERING, SERVICE, {}, None, 1)
    check("an integrated rendition sends no negative field and no media", "negativePrompt" not in integrated and "inputs" not in integrated and "seed" not in integrated and "numberResults" not in integrated)
    dry = transport_runware.build(verified("native-subset", "low quality", 1), OFFERING, SERVICE, {}, None, 1)
    check("the dry run shows a placeholder where an upload id will go", dry["inputs"]["referenceImages"] == ["<C:/refs/ref-0.png>"] and dry["negativePrompt"] == "low quality")
    keyless = copy.deepcopy(OFFERING)
    keyless["request_keys"] = {}
    check("an offering with no key for the media is refused before anything is sent", refused(lambda: transport_runware.build(verified("separate-field", "", 1), keyless, SERVICE, {}, None, 1), "no request key"))
    # An offering that takes the prepared references as one seed image rather
    # than a list: the same role selection the builder and the verifier made.
    seeded = {**OFFERING, "request_keys": {"seed image": ["seedImage"]}}
    seeded_task = transport_runware.build(verified("separate-field", "", 1), seeded, SERVICE, {"C:/refs/ref-0.png": "u0"}, None, 1)
    check("an offering that takes a seed image gets the one reference there, not in a list",
          seeded_task["seedImage"] == "u0" and "inputs" not in seeded_task, seeded_task)
    check("an offering that takes one image refuses a package that selected two",
          refused(lambda: transport_runware.build(verified("separate-field", "", 2), seeded, SERVICE, {}, None, 1), "one image"))
    check("the credential is found by its variable name inside the host configuration and nowhere else",
          dispatch._find_env({"mcpServers": {"x": {"env": {"EXAMPLE_KEY": "k"}}}}, "EXAMPLE_KEY") == "k" and dispatch._find_env({"other": "k"}, "EXAMPLE_KEY") is None)

    # The seed and the count come from the command line, so the package was never
    # checked carrying them. The transport names them and the dispatcher puts them
    # to the record and to the service's observed schema before anything is sent.
    check("the transport names what a dispatch adds, and names nothing when it adds nothing",
          transport_runware.added_parameters(OFFERING, None, 1) == {}
          and transport_runware.added_parameters(OFFERING, 7, 2) == {"seed": 7, "numberResults": 2},
          transport_runware.added_parameters(OFFERING, 7, 2))
    with tempfile.TemporaryDirectory() as tmp:
        pack = Path(tmp)
        (pack / SNAPSHOT).parent.mkdir(parents=True)
        (pack / SNAPSHOT).write_text(json.dumps({
            "artifact_type": "observed-parameter-schema", "model_id": "fixture-model", "service": "svc",
            "model_identifier": "vendor:model@1", "observed_at": "2026-09-13",
            "source": "the fixture service's model schema endpoint", "unenforced": [], "schema": ADDED_SCHEMA,
        }), encoding="utf-8")
        offered = {**OFFERING, "schema_snapshot": SNAPSHOT}
        fixture_record = {"id": "fixture-model", "max_outputs": 4, "offerings": [offered]}
        sent = verified("separate-field", "blurry", 0)

        def checked_request(seed: int | None, count: int) -> None:
            # The record is a fixture rather than a pack record, so the pack that
            # holds its observed schema is the temporary one, not a resolved root.
            original = dispatch.model_pack_root
            dispatch.model_pack_root = lambda _model_id: pack
            try:
                dispatch.check_request(sent, fixture_record, offered, "fixture-model", transport_runware, seed, count)
            finally:
                dispatch.model_pack_root = original

        check("a seed the observed schema does not take is refused before anything is sent",
              refused(lambda: checked_request(7, 1), "unexpected properties"))
        check("a count past the record's max_outputs is refused before anything is sent",
              refused(lambda: checked_request(None, 50), "max_outputs"))
        for count in (2, 1):
            try:
                checked_request(None, count)
                check(f"a request the record and the schema accept passes (count {count})", True)
            except ValueError as exc:
                check(f"a request the record and the schema accept passes (count {count})", False, str(exc))

    # An upscale: the source on the input key, the factor as the service takes it, each setting on its key.
    upscaler = {"id": "fixture-upscaler", "upscale_settings": {"strength": ["low", "high"], "variant": ["general"]}}
    up_offering = {**OFFERING, "request_keys": {"input image": ["inputs.image"]}, "setting_keys": {"strength": "settings.enhancementStrength"}}
    up_service = {**SERVICE, "operations": {"imageUpscale": {}}}
    placed = dispatch.mapped_settings(upscaler, up_offering, {"strength": "high"})
    task = transport_runware.build_upscale("vendor:up@1", "C:/src/a.png", 2.0, placed, up_offering, up_service, {"C:/src/a.png": "u9"})
    check("an upscale request carries the source by the input key, an integer factor, and the setting on its request key",
          task["taskType"] == "imageUpscale" and task["inputs"]["image"] == "u9" and task["upscaleFactor"] == 2 and task["settings"]["enhancementStrength"] == "high" and task["outputFormat"] == "PNG", task)
    check("a declared setting with no request key is refused before anything is sent",
          refused(lambda: dispatch.mapped_settings(upscaler, up_offering, {"variant": "general"}), "no request key for the setting"))
    check("a setting outside the record's contract is refused by the record first",
          refused(lambda: dispatch.mapped_settings(upscaler, up_offering, {"strength": "extreme"}), "outside the model contract"))

    # A guidance prompt travels on the offering's own key, and one with nowhere to go is refused.
    guided_offering = {**up_offering, "request_keys": {"input image": ["inputs.image"], "guidance prompt": ["guidancePrompt"]}}
    guided = transport_runware.build_upscale("vendor:up@1", "C:/src/a.png", 2.0, placed, guided_offering, up_service, {}, "keep the scar")
    check("a guidance prompt is placed on the request key the offering records for it",
          guided["guidancePrompt"] == "keep the scar" and dispatch.guidance_key(guided_offering) == "guidancePrompt", guided)
    check("an offering with no guidance key refuses a guidance prompt before anything is uploaded",
          dispatch.guidance_key(up_offering) is None
          and refused(lambda: dispatch.require_guidance_key(up_offering, "keep the scar"), "no request key for a guidance prompt")
          and dispatch.require_guidance_key(up_offering, None) is None)
    unguided = transport_runware.build_upscale("vendor:up@1", "C:/src/a.png", 2.0, placed, guided_offering, up_service, {})
    check("an upscale sent without guidance carries no guidance key", "guidancePrompt" not in unguided, unguided)

    # The worked example's model is exposed on no service here, so the dispatcher
    # refuses to send it. The studio is a real one, so what the run reaches is the
    # refusal about the record and not the one about the directory.
    example = ROOT / "examples" / "state-aware-pilot" / "generated" / "generation-package.json"
    with tempfile.TemporaryDirectory() as tmp:
        home = studio.init(Path(tmp) / "studio", "dispatch-smoke", "Dispatch smoke studio")
        studio.add_character(home, "C01", "")

        def dispatched(*arguments: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "dispatch.py"), *arguments,
                 "--studio", str(home), "--character", "C01", "--slot", "base.front"],
                capture_output=True, text=True, encoding="utf-8", check=False,
            )

        run = dispatched(str(example))
        check("a package for a model exposed on no service is refused with the way to record by hand",
              run.returncode != 0 and "exposed on no service" in run.stderr, run.stderr[-400:])
        # The pack-runtime selectors are the same three everywhere, and they go together.
        partial = dispatched(str(example), "--state-file", str(Path(tmp) / "pack-state.json"))
        check("one runtime selector without the others is refused",
              partial.returncode != 0 and "must be supplied together" in partial.stderr, partial.stderr[-300:])
        runtime = Path(tmp) / "runtime"
        made = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "pack_cli.py"),
             "--state-file", str(runtime / "pack-state.json"), "--cache-dir", str(runtime / "cache"),
             "--managed-root", str(runtime / "managed"), "state-init"],
            capture_output=True, text=True, encoding="utf-8", check=False,
        )
        chosen = dispatched(str(example), "--state-file", str(runtime / "pack-state.json"),
                            "--cache-dir", str(runtime / "cache"), "--managed-root", str(runtime / "managed"))
        check("a runtime named on the command line resolves the record the same way the default one does",
              made.returncode == 0 and chosen.returncode != 0 and "exposed on no service" in chosen.stderr,
              {"state_init": made.stderr[-200:], "dispatch": chosen.stderr[-300:]})
        broken = Path(tmp) / "broken-package.json"
        broken.write_text(json.dumps({"status": "ok"}), encoding="utf-8")
        bad = dispatched(str(broken))
        check("a package of the wrong shape is one line of error rather than a traceback",
              bad.returncode == 1 and bad.stderr.startswith("error: ") and "Traceback" not in bad.stderr, bad.stderr[-300:])

    passed = sum(1 for row in results if row["passed"])
    report = {"ok": len(results) == EXPECTED_CHECKS and passed == len(results), "checks": len(results), "expected_checks": EXPECTED_CHECKS,
              "passed": passed, "failures": [row for row in results if not row["passed"]]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
