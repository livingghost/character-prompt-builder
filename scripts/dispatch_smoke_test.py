#!/usr/bin/env python3
"""Exercise the dispatcher's request building and its refusals without touching a service."""
from __future__ import annotations

import base64
import contextlib
import copy
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import types
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import dispatch  # noqa: E402
import execution_contract  # noqa: E402
import studio  # noqa: E402
import transport_runware  # noqa: E402
from request_contract import MANAGEMENT_VALUE

EXPECTED_CHECKS = 47

SERVICE = {"endpoint": {"base_url": "https://example.invalid/v1", "method": "POST"}, "operations": {"imageInference": {}}, "auth": {"env_var": "EXAMPLE_KEY"}}
TEXT_KEYS = {"model": ["model"], "prompt": ["positivePrompt"], "negative prompt": ["negativePrompt"]}
OFFERING = {
    "service": "svc",
    "model_identifier": "vendor:model@1",
    "request_keys": {**TEXT_KEYS, "reference images": ["inputs.referenceImages"]},
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


def generation_request(*args, **kwargs) -> dict[str, Any]:
    return transport_runware.compile_request(*args, **kwargs)["request"]


def upscale_request(*args, **kwargs) -> dict[str, Any]:
    return transport_runware.compile_upscale(*args, **kwargs)["request"]


def refused(fn, text: str) -> bool:
    try:
        fn()
    except (SystemExit, ValueError) as exc:
        return text in str(exc)
    return False


def refusal(fn) -> str:
    """What a refused call says, or an empty string when it was not refused."""
    try:
        fn()
    except (SystemExit, ValueError) as exc:
        return str(exc)
    return ""


def raises(fn, kind) -> bool:
    try:
        fn()
    except kind:
        return True
    return False


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24


class FakeResponse(io.BytesIO):
    """A synthetic HTTP response; nothing here opens a connection."""

    def __init__(self, body: bytes, *, length: int | None = None, status: int = 200) -> None:
        super().__init__(body)
        self.status = status
        self.headers = {} if length is None else {"Content-Length": str(length)}


class FakeOpener:
    def __init__(self, body: bytes = PNG, *, length: int | None = None, status: int = 200) -> None:
        self.body, self.length, self.status, self.opened = body, length, status, []

    def open(self, request, timeout=None):
        self.opened.append(request.full_url)
        return FakeResponse(self.body, length=self.length, status=self.status)


def saved(url: str, opener: FakeOpener, folder: Path) -> tuple[str | None, str | None, list[str]]:
    """Run dispatch.save against a synthetic response: (sha256 or None, error or None, files left behind)."""
    target = folder / "result.png"
    with patch.object(dispatch, "_opener", return_value=opener):
        try:
            digest, error = dispatch.save(url, target, transport_runware.RESULT_HOSTS), None
        except (OSError, ValueError) as exc:
            digest, error = None, str(exc)
    left = sorted(path.name for path in folder.iterdir())
    for path in folder.iterdir():
        path.unlink()
    return digest, error, left


def isolated_environment(home: Path) -> dict[str, str]:
    """Subprocesses read a fresh home, never the pack state or host configuration of the person running this.

    The home's pack runtime enables commons alone, whatever personal packs sit beside it.
    """
    home.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, "HOME": str(home), "USERPROFILE": str(home), "PYTHONDONTWRITEBYTECODE": "1"}
    commons = json.loads((ROOT / "packs" / "commons" / "pack.json").read_text(encoding="utf-8"))["pack_id"]
    subprocess.run([sys.executable, str(ROOT / "scripts" / "pack_cli.py"), "ready", "--only", commons],
                   env=environment, capture_output=True, check=True)
    return environment


def credential(config: Any, variable: str = "EXAMPLE_KEY") -> tuple[str | None, str]:
    """dispatch.api_key against a synthetic ~/.claude.json in a scratch home: (key or None, everything printed)."""
    with tempfile.TemporaryDirectory(prefix="cpb-dispatch-home-") as tmp:
        home = Path(tmp)
        (home / ".claude.json").write_text(json.dumps(config), encoding="utf-8")
        output = io.StringIO()
        environment = {name: value for name, value in os.environ.items() if name != variable}
        with patch.object(Path, "home", return_value=home), patch.dict(os.environ, environment, clear=True), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            try:
                return dispatch.api_key({"auth": {"env_var": variable}}), output.getvalue()
            except SystemExit as exc:
                return None, output.getvalue() + str(exc)


def main() -> int:
    results: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: Any = None) -> None:
        results.append({"name": name, "passed": bool(passed), "detail": detail})

    task = generation_request(verified("separate-field", "blurry", 2), OFFERING, SERVICE, {"C:/refs/ref-0.png": "u0", "C:/refs/ref-1.png": "u1"}, seed=7, count=2)
    check("the request carries the model identifier, the effective prompt, and the parameters as sent",
          task["model"] == "vendor:model@1" and task["positivePrompt"] == "a heron on a post" and task["width"] == 1024 and task["settings"]["quality"] == "medium", task)
    check("a separate-field negative travels on negativePrompt", task.get("negativePrompt") == "blurry")
    check("references are placed under the offering's request key by uploaded id", task["inputs"]["referenceImages"] == ["u0", "u1"])
    check("seed and count are sent", task["seed"] == 7 and task["numberResults"] == 2)
    check("the offering's as_written keys are set where the parameters left them unset", task["settings"]["promptExpansion"] == "disabled")
    integrated = generation_request(verified("integrated-critical", "blurry", 0), OFFERING, SERVICE, {}, None, 1)
    check("an integrated rendition sends no negative field and no media", "negativePrompt" not in integrated and "inputs" not in integrated and "seed" not in integrated and integrated["numberResults"] == 1)
    dry = generation_request(verified("native-subset", "low quality", 1), OFFERING, SERVICE, {}, None, 1)
    check("the dry run shows a placeholder where an upload id will go", dry["inputs"]["referenceImages"] == [MANAGEMENT_VALUE] and dry["negativePrompt"] == "low quality")
    keyless = copy.deepcopy(OFFERING)
    keyless["request_keys"] = dict(TEXT_KEYS)
    check("an offering with no key for the media is refused before anything is sent", refused(lambda: generation_request(verified("separate-field", "", 1), keyless, SERVICE, {}, None, 1), "no request key"))
    # The prompt and the negative travel on the keys the offering gives them, and
    # an offering with no negative key has no field for a separate negative.
    renamed = {**OFFERING, "request_keys": {"prompt": ["input.text"], "negative prompt": ["input.avoid"]}}
    moved = generation_request(verified("separate-field", "blurry", 0), renamed, SERVICE, {}, None, 1)
    check("the prompt and the negative go on the request keys the offering names",
          moved["input"] == {"text": "a heron on a post", "avoid": "blurry"} and "positivePrompt" not in moved, moved)
    unnegated = {**OFFERING, "request_keys": {"prompt": ["positivePrompt"]}}
    check("an offering with no negative key refuses a separate negative before anything is sent",
          refused(lambda: generation_request(verified("separate-field", "blurry", 0), unnegated, SERVICE, {}, None, 1), "'negative prompt'")
          and "negativePrompt" not in generation_request(verified("integrated-critical", "blurry", 0), unnegated, SERVICE, {}, None, 1))
    # An offering that takes the prepared references as one seed image rather
    # than a list: the same role selection the builder and the verifier made.
    seeded = {**OFFERING, "request_keys": {**TEXT_KEYS, "seed image": ["seedImage"]}}
    seeded_task = generation_request(verified("separate-field", "", 1), seeded, SERVICE, {"C:/refs/ref-0.png": "u0"}, None, 1)
    check("an offering that takes a seed image gets the one reference there, not in a list",
          seeded_task["seedImage"] == "u0" and "inputs" not in seeded_task, seeded_task)
    check("an offering that takes one image refuses a package that selected two",
          refused(lambda: generation_request(verified("separate-field", "", 2), seeded, SERVICE, {}, None, 1), "one image"))

    # The seed and the count come from the command line, so the package was never
    # checked carrying them. The transport names them and the dispatcher puts them
    # to the record and to the service's observed schema before anything is sent.
    check("the transport declares the exact output count and any selected seed",
          transport_runware.added_parameters(OFFERING, None, 1) == {"numberResults": 1}
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
    task = upscale_request("vendor:up@1", "C:/src/a.png", 2.0, placed, up_offering, up_service, {"C:/src/a.png": "u9"})
    check("an upscale request carries the source by the input key, an integer factor, and the setting on its request key",
          task["taskType"] == "imageUpscale" and task["inputs"]["image"] == "u9" and task["upscaleFactor"] == 2 and task["settings"]["enhancementStrength"] == "high" and task["outputFormat"] == "PNG", task)
    check("a declared setting with no request key is refused before anything is sent",
          refused(lambda: dispatch.mapped_settings(upscaler, up_offering, {"variant": "general"}), "no request key for the setting"))
    check("a setting outside the record's contract is refused by the record first",
          refused(lambda: dispatch.mapped_settings(upscaler, up_offering, {"strength": "extreme"}), "outside the model contract"))

    # A guidance prompt travels on the offering's own key, and one with nowhere to go is refused.
    guided_offering = {**up_offering, "request_keys": {"input image": ["inputs.image"], "guidance prompt": ["guidancePrompt"]}}
    guided = upscale_request("vendor:up@1", "C:/src/a.png", 2.0, placed, guided_offering, up_service, {}, "keep the scar")
    check("a guidance prompt is placed on the request key the offering records for it",
          guided["guidancePrompt"] == "keep the scar" and dispatch.guidance_key(guided_offering) == "guidancePrompt", guided)
    check("an offering with no guidance key refuses a guidance prompt before anything is uploaded",
          dispatch.guidance_key(up_offering) is None
          and refused(lambda: dispatch.require_guidance_key(up_offering, "keep the scar"), "no request key for a guidance prompt")
          and dispatch.require_guidance_key(up_offering, None) is None)
    unguided = upscale_request("vendor:up@1", "C:/src/a.png", 2.0, placed, guided_offering, up_service, {})
    check("an upscale sent without guidance carries no guidance key", "guidancePrompt" not in unguided, unguided)

    # A returned image is fetched only over https from a host the transport
    # declares, streamed through a temporary file and kept only when it is an image.
    with tempfile.TemporaryDirectory(prefix="cpb-dispatch-save-") as tmp:
        folder = Path(tmp)
        untouched = FakeOpener()
        refusals = [saved(url, untouched, folder) for url in (
            "file:///C:/Windows/win.ini", "http://im.runware.ai/image/a.png", "https://example.invalid/a.png",
            "https://im.runware.ai.example.invalid/a.png", "https://user:pw@im.runware.ai/a.png")]
        check("a result URL that is not https on a declared result host is refused before anything is opened",
              all(digest is None and error and "refused to download" in error and not left for digest, error, left in refusals)
              and not untouched.opened, refusals)
        digest, error, left = saved("https://im.runware.ai/image/a.png", FakeOpener(PNG, length=len(PNG)), folder)
        check("an image from the declared result host is saved whole, with its hash",
              digest == hashlib.sha256(PNG).hexdigest() and error is None and left == ["result.png"], (digest, error, left))
        digest, error, left = saved("https://im.runware.ai/image/a.png", FakeOpener(b"<html>not an image</html>"), folder)
        check("bytes that are not an image are refused and leave no file",
              digest is None and "did not return a PNG, JPEG or WebP image" in (error or "") and not left, (error, left))
        digest, error, left = saved("https://im.runware.ai/image/a.png", FakeOpener(PNG, length=len(PNG) + 10), folder)
        check("a body shorter than its declared Content-Length is refused and leaves no file",
              digest is None and "Content-Length" in (error or "") and not left, (error, left))
    handler = dispatch._ResultRedirect(transport_runware.RESULT_HOSTS)
    original = urllib.request.Request("https://im.runware.ai/image/a.png")
    check("a download follows a redirect only to https on a declared result host",
          refused(lambda: handler.redirect_request(original, None, 302, "Found", {}, "https://example.invalid/a.png"), "refused to download")
          and handler.redirect_request(original, None, 302, "Found", {}, "https://im.runware.ai/image/b.png").full_url
          == "https://im.runware.ai/image/b.png")

    # The credential comes from the environment, or from an MCP server's env
    # block in the host configuration, and from nowhere else in that file.
    top = {"mcpServers": {"runware": {"command": "x", "env": {"EXAMPLE_KEY": "top-level-secret"}}}}
    project = {"projects": {"C:/work": {"mcpServers": {"runware": {"env": {"EXAMPLE_KEY": "project-secret"}}}}}}
    stray = {"EXAMPLE_KEY": "stray-secret", "projects": {"C:/work": {"env": {"EXAMPLE_KEY": "stray-secret"}}},
             "other": {"deep": {"EXAMPLE_KEY": "stray-secret"}}}
    found = [credential(top), credential(project), credential(stray)]
    check("the credential is read from a top-level or per-project MCP server env block and nowhere else in the host configuration",
          found[0][0] == "top-level-secret" and found[1][0] == "project-secret" and found[2][0] is None
          and "Set EXAMPLE_KEY" in found[2][1], [row[1] for row in found])
    conflicting = credential({**top, **project})
    check("MCP servers that give the variable different values are refused, and no value is printed",
          conflicting[0] is None and "different values" in conflicting[1]
          and not any(secret in conflicting[1] for secret in ("top-level-secret", "project-secret"))
          and not any(secret in row[1] for row in found for secret in ("top-level-secret", "project-secret", "stray-secret")),
          conflicting[1])

    # The transport sends the credential only to https on the Runware API host.
    check("the Runware transport accepts only https on its API host as the endpoint",
          transport_runware.endpoint({"endpoint": {"base_url": "https://api.runware.ai/v1"}}) == "https://api.runware.ai/v1"
          and all(refused(lambda url=url: transport_runware.endpoint({"endpoint": {"base_url": url}}), "is not https://api.runware.ai")
                  for url in ("http://api.runware.ai/v1", "https://example.invalid/v1", "https://api.runware.ai.example.invalid/v1",
                              "https://user:pw@api.runware.ai/v1", "https://api.runware.ai:8443/v1", "")))
    sender = FakeOpener()
    with patch.object(transport_runware.urllib.request, "build_opener", return_value=sender):
        check("a record naming another server is refused before the credential leaves the machine",
              refused(lambda: transport_runware.send({"taskType": "imageInference"}, SERVICE, "KEY"), "is not https://api.runware.ai")
              and not sender.opened)
    runware = {"endpoint": {"base_url": "https://api.runware.ai/v1"}}
    for body, name in ((b"<html>502 Bad Gateway</html>", "a 200 answer that is not JSON"),
                       (b'["not", "an", "object"]', "a 200 answer that is JSON but not an object")):
        with patch.object(transport_runware.urllib.request, "build_opener", return_value=FakeOpener(body)):
            answer = transport_runware.send({"taskType": "imageInference"}, runware, "KEY")
        check(f"{name} is kept as an error answer with its body",
              transport_runware.rejections(answer) == [{"code": "http200-not-json-object", "message": body.decode()}]
              and transport_runware.observation_outcome(answer) == "rejected", answer)
    check("the transport refuses to follow a redirect with the credential",
          raises(lambda: transport_runware._NoRedirect().redirect_request(
              urllib.request.Request("https://api.runware.ai/v1", data=b"[]", method="POST"), None, 302, "Found", {},
              "https://example.invalid/v1"), urllib.error.HTTPError))

    # The transport contract is the dispatcher's docstring, which names exactly
    # what the dispatcher, its renderer and the package builder use.
    documented = {line.split("(")[0].strip() for line in (dispatch.__doc__ or "").splitlines()
                  if line.startswith("    ") and not line.startswith("     ")}
    called = {*dispatch.TRANSPORT_NAMES, "compile_upscale"}
    check("the dispatcher's docstring lists exactly the names a transport defines, and the Runware transport has each",
          documented == called and all(hasattr(transport_runware, name) for name in called), sorted(documented ^ called))
    check("the Runware transport's docstring restates no part of the contract",
          not any(line.startswith("    ") for line in (transport_runware.__doc__ or "").splitlines()))
    # A transport is found by the service's key and refused, in one line, for each name it lacks.
    partial = types.ModuleType("transport_partial_fixture")
    partial.OPERATIONS = {"generation": "make", "upscale": "enlarge"}
    partial.endpoint = lambda service: ""
    with patch.dict(sys.modules, {"transport_partial_fixture": partial}):
        lacking = refusal(lambda: dispatch.load_transport("partial-fixture"))
    check("a transport that lacks contract names is refused in one line naming each missing one",
          all(name in lacking for name in ("RESULT_HOSTS", "compile_request", "compile_upscale", "observation_outcome"))
          and "endpoint" not in lacking and "OPERATIONS" not in lacking and len(lacking.splitlines()) == 1, lacking)
    absent = refusal(lambda: dispatch.load_transport("absent-fixture"))
    check("a service with no transport names the module to write and where its contract is",
          "scripts/transport_absent_fixture.py" in absent and "scripts/dispatch.py docstring" in absent
          and "transport_runware" not in absent, absent)
    # A refusal is kept under the hash of the request, whatever fields the service's request has.
    with tempfile.TemporaryDirectory(prefix="cpb-dispatch-refusal-") as tmp:
        plain = {"prompt": "a heron on a post", "num_images": 1}
        with contextlib.redirect_stdout(io.StringIO()):
            kept = dispatch.record_refusal(Path(tmp), "package", plain, [{"code": "refused"}])
            again = dispatch.record_refusal(Path(tmp), "package", plain, [{"code": "refused again"}])
        check("a refusal is recorded under the request's hash for a request with no service identifier",
              kept.name == f"package-{execution_contract.content_id(plain)[:8]}-refused.json" and kept.is_file(), kept.name)
        check("a second refusal of the same request keeps its own file beside the first",
              again != kept and again.is_file()
              and json.loads(kept.read_text(encoding="utf-8"))["refused"] == [{"code": "refused"}]
              and json.loads(again.read_text(encoding="utf-8"))["refused"] == [{"code": "refused again"}], [kept.name, again.name])
    # An image an answer carries inline is decoded and kept only when it is an image.
    check("an image carried inline as base64 text is decoded, and anything else is refused",
          dispatch.inline_image(base64.b64encode(PNG).decode("ascii")) == PNG and dispatch.image_suffix(PNG) == ".png"
          and refused(lambda: dispatch.inline_image("not base64 at all!"), "")
          and refused(lambda: dispatch.inline_image(base64.b64encode(b"<html>no</html>").decode("ascii")), "not a PNG, JPEG or WebP image")
          and refused(lambda: dispatch.inline_image(PNG), "base64 text"))

    # The worked example's model is exposed on no service here, so the dispatcher
    # refuses to send it. The studio is a real one, so what the run reaches is the
    # refusal about the record and not the one about the directory.
    example = ROOT / "examples" / "state-aware-pilot" / "generated" / "generation-package.json"
    with tempfile.TemporaryDirectory() as tmp:
        environment = isolated_environment(Path(tmp) / "person")
        home = studio.init(Path(tmp) / "studio", "dispatch-smoke", "Dispatch smoke studio")
        studio.add_character(home, "C01", "")
        package_data = json.loads(example.read_text(encoding="utf-8"))
        for relative, snapshot in package_data["input_snapshots"].items():
            if relative.startswith("@"):
                continue
            path = home / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(base64.b64decode(snapshot["base64"], validate=True))


        def dispatched(*arguments: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "dispatch.py"), *arguments,
                 "--studio", str(home), "--character", "C01", "--slot", "base.front"],
                capture_output=True, text=True, encoding="utf-8", check=False, env=environment,
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
             "--managed-root", str(runtime / "managed"), "ready", "--only",
             json.loads((ROOT / "packs" / "commons" / "pack.json").read_text(encoding="utf-8"))["pack_id"]],
            capture_output=True, text=True, encoding="utf-8", check=False, env=environment,
        )
        chosen = dispatched(str(example), "--state-file", str(runtime / "pack-state.json"),
                            "--cache-dir", str(runtime / "cache"), "--managed-root", str(runtime / "managed"))
        check("a runtime named on the command line resolves the record the same way the default one does",
              (runtime / "pack-state.json").is_file() and chosen.returncode != 0 and "exposed on no service" in chosen.stderr,
              {"state_init": made.stderr[-200:], "dispatch": chosen.stderr[-300:]})
        broken = Path(tmp) / "broken-package.json"
        broken.write_text(json.dumps({"status": "ok"}), encoding="utf-8")
        bad = dispatched(str(broken))
        check("a package of the wrong shape is one line of error rather than a traceback",
              bad.returncode == 1 and bad.stderr.startswith("error: ") and "Traceback" not in bad.stderr, bad.stderr[-300:])
        mistyped = dispatched(str(Path(tmp) / "generation-pakage.json"))
        check("a mistyped package path is one sentence naming the path",
              mistyped.returncode == 1 and mistyped.stderr.startswith("error: there is no Generation Package at ")
              and "generation-pakage.json" in mistyped.stderr and "Errno" not in mistyped.stderr
              and len(mistyped.stderr.strip().splitlines()) == 1, mistyped.stderr[-300:])

    passed = sum(1 for row in results if row["passed"])
    report = {"ok": len(results) == EXPECTED_CHECKS and passed == len(results), "checks": len(results), "expected_checks": EXPECTED_CHECKS,
              "passed": passed, "failures": [row for row in results if not row["passed"]]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
