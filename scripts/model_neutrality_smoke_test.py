#!/usr/bin/env python3
"""Check explicit model selection and neutral shared sources."""
from __future__ import annotations

import contextlib
import io
import json
import re
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import prepare_generation_references as references

ROOT = Path(__file__).resolve().parents[1]


# Concrete adapter documents own provider-specific guidance. Shared adapters stay scanned.
CONCRETE_ADAPTER_DOCUMENTS = frozenset({
    "references/adapters/flux.md",
    "references/adapters/gpt-image.md",
    "references/adapters/grok-imagine.md",
    "references/adapters/midjourney-niji.md",
    "references/adapters/novelai.md",
    "references/adapters/sdxl-comfyui.md",
})
TEXT_SUFFIXES = frozenset({
    ".py", ".json", ".jsonl", ".md", ".txt", ".html", ".css", ".js",
    ".mjs", ".ts", ".tsx", ".jsx", ".yaml", ".yml", ".toml", ".sh", ".svg",
})
SERVICE_ADAPTER_NAMES = {"scripts/transport_runware.py": frozenset({"Runware"})}

# Lexical fixtures are independent of enabled packs and their model records.
PROVIDER_PATTERNS = tuple(
    (label, re.compile(r"(?<![a-zA-Z0-9])(?:" + expression + r")(?![a-zA-Z])"))
    for label, expression in (
        ("OpenAI", r"(?i:open[\s_-]*ai)"),
        ("GPT Image", r"(?i:gpt[\s_-]*image)"),
        ("DALL-E", r"(?i:dall[\s_.-]*e)"),
        ("Google", r"(?i:google)"),
        ("Gemini", r"(?i:gemini)"),
        ("Imagen", r"(?i:imagen)"),
        ("Nano Banana", r"(?i:nano[\s_-]*banana)"),
        ("xAI", r"(?i:x[._-]?ai|x\.ai)"),
        ("Grok", r"(?i:grok)"),
        ("Alibaba", r"(?i:alibaba)"),
        ("Qwen", r"(?i:qwen)"),
        ("Black Forest Labs", r"(?i:black[\s_-]*forest[\s_-]*labs)"),
        ("BFL", r"(?i:bfl)"),
        ("FLUX", r'FLUX|Flux|(?i:flux)(?=[\s_./@:-]*(?:[0-9]|image\b|dev\b|schnell\b))|(?<=[\"\'\x60])(?i:flux)(?=[\"\'\x60])'),
        ("ByteDance", r"(?i:byte[\s_-]*dance)"),
        ("Seedream", r"(?i:see[\s_-]*dream)"),
        ("Stability AI", r"(?i:stability[\s_.-]*ai)"),
        ("Stable Diffusion", r"(?i:stable[\s_-]*diffusion)"),
        ("SDXL", r"(?i:sdxl)"),
        ("Midjourney", r"(?i:mid[\s_-]*journey)"),
        ("Niji", r"(?i:niji)"),
        ("NovelAI", r"(?i:novel[\s_-]*ai)"),
        ("ComfyUI", r"(?i:comfy[\s_-]*ui)"),
        ("Ideogram", r"(?i:ideogram)"),
        ("Recraft", r"(?i:recraft)"),
        ("Leonardo", r'(?i:leonardo\.ai)|(?<=[\"\'\x60])(?i:leonardo)(?=[\"\'\x60])'),
        ("Firefly", r'(?i:adobe[\s_-]*firefly|firefly[\s_.-]*[0-9]+)|(?<=[\"\'\x60])(?i:firefly)(?=[\"\'\x60])'),
        ("Runware", r"(?i:runware)"),
        ("Fal", r'(?i:fal\.ai)|(?<=[\"\'\x60])(?i:fal)(?=[\"\'\x60])'),
        ("Replicate", r'(?i:replicate\.com)|(?i:replicate)(?=\s+(?:API|model|service)\b)|(?<=[\"\'\x60])(?i:replicate)(?=[\"\'\x60])'),
    )
)

# Exact excerpts retain citations, declared routes and recorded examples at bounded counts.
# Masking preserves every surrounding character, including additions on the same line.
SOURCE_EXCERPTS = {'references/adapters/instruction-edit.md': {'Stable Diffusion attention syntax': 1},
 'references/comfyui-integration-notes.md': {'# ComfyUI Character Prompt Builder: Incorporated Ideas': 1,
                                             'https://github.com/euan-gwd/comfyui-character-prompt-builder': 1,
                                             '## ComfyUI routing': 1},
 'references/maintenance/presets.md': {'### OpenAI Agent Skills': 1,
                                       '- https://developers.openai.com/codex/build-skills': 1,
                                       '- https://developers.openai.com/codex/skills-and-plugins': 1,
                                       '- https://developers.openai.com/blog/eval-skills': 1,
                                       '- https://developers.openai.com/cookbook/examples/multimodal/image-gen-models-prompting-guide': 1,
                                       '- https://developers.openai.com/api/docs/guides/image-generation': 1,
                                       '- https://developers.openai.com/api/docs/models/gpt-image-2.5-flare': 1,
                                       '### OpenAI image generation': 1,
                                       '- select the exact GPT Image model and offering explicitly; the package has no implicit target model': 1,
                                       '### ComfyUI Character Prompt Builder': 1,
                                       '- https://github.com/euan-gwd/comfyui-character-prompt-builder': 1,
                                       'Vendor behavior can change. Midjourney, FLUX, SDXL, NovelAI, Firefly, Ideogram, Recraft, Leonardo, and ComfyUI adapters should be rechecked against official documentation when production behavior matters.': 1,
                                       '### Midjourney': 1,
                                       '- https://docs.midjourney.com/hc/en-us/articles/32199405667853-Version': 1,
                                       '- https://docs.midjourney.com/hc/en-us/articles/32173351982093-No': 1,
                                       '- https://docs.midjourney.com/hc/en-us/articles/36285124473997-Omni-Reference': 1,
                                       '- https://docs.midjourney.com/hc/en-us/articles/32180011136653-Style-Reference': 1,
                                       '- V8.2 is the current default Midjourney version as of the verification date': 1,
                                       '### Black Forest Labs FLUX.2': 1,
                                       '- https://docs.bfl.ai/guides/prompting_guide_flux2': 1,
                                       '- https://docs.bfl.ai/guides/prompting_guide_t2i_negative': 1,
                                       '- FLUX.2 does not support a separate negative prompt': 1,
                                       '- the full portable negative block remains in the package for traceability and later adaptation, not as a field that was transmitted to FLUX.2': 1},
 'references/model-prompt-recommendations.md': {'| `commons` | `gpt-image-2.5-flare` (OpenAI GPT Image 2.5 Flare) | No fixed reusable default adopted | Model guidance is task-specific; the core does not commit one universal positive or negative string. |': 1,
                                                '| `commons` | `gpt-image-2.5-sunburst` (OpenAI GPT Image 2.5 Sunburst) | No fixed reusable default adopted | Model guidance is task-specific; the core does not commit one universal positive or negative string. |': 1,
                                                '| `commons` | `grok-imagine-image-2.0` (xAI Grok Imagine Image 2.0) | No fixed reusable default adopted | Model guidance is task-specific; the core does not commit one universal positive or negative string. |': 1,
                                                '| `commons` | `seedream-5.0-pro` (ByteDance Seedream 5.0 Pro) | No fixed reusable default adopted | The exact Runware interface is observed; natural-language directions remain task-specific. Critical exclusions belong in the positive prompt because no negativePrompt field is exposed. |': 1,
                                                '| `commons` | `qwen-image-2.1-pro` (Alibaba Qwen-Image-2.1-Pro) | No fixed reusable default adopted | The observed Runware interface accepts task-specific natural-language instructions; no universal prompt string is committed. |': 1,
                                                '| `commons` | `flux-3-image` (Black Forest Labs FLUX 3 Image) | No fixed reusable default adopted | The observed Runware interface accepts task-specific natural-language instructions; no universal prompt string is committed. |': 1},
 'references/production-specification.md': {'python scripts/production_spec.py draft production-spec.json --root STUDIO --model grok-imagine-image-2.0 \\': 1},
 'references/runtime/batch-generation.md': {'"target_model": "flux-1-dev",': 1,
                                            '"transport": "runware-mcp",': 1,
                                            '"job_id": "scene-sdxl",': 1,
                                            '"target_model": "sdxl-base",': 1,
                                            '"transport": "comfyui-local",': 1,
                                            '"generation_package": "packages/scene-sdxl.json"': 1},
 'references/runtime/image-generation.md': {'[GPT Image](../adapters/gpt-image.md)': 1,
                                            '[Midjourney and Niji](../adapters/midjourney-niji.md)': 1,
                                            '[FLUX](../adapters/flux.md)': 1,
                                            '[SDXL and ComfyUI](../adapters/sdxl-comfyui.md)': 1,
                                            '[NovelAI](../adapters/novelai.md)': 1,
                                            '[Grok Imagine](../adapters/grok-imagine.md)': 1,
                                            'Stable Diffusion parentheses': 1,
                                            "ComfyUI is a workflow host, so use the loaded model's record or an explicit workflow-level decision.": 1,
                                            '`"transport": "runware"` selects `scripts/transport_runware.py`': 1,
                                            'Gemini or Imagen, Firefly, Ideogram, Recraft, Leonardo, and future design-oriented generators use that unlisted-interface rule. Inspect the exact active interface and model record; never infer media or negative transport from a brand family.': 1,
                                            '[Workflow Walkthrough](workflow-walkthrough.md) takes one idea to a prepared run and its exact request for `grok-imagine-image-2.0` on Runware. It sends nothing and uses no credential. State-aware example commands above name `--plot-file` and `--retrieval-record-file` for a run whose task declares neither; `examples/state-aware-pilot/build_example.py` supplies explicit illustrative lookup data for its generated package.': 1},
 'references/runtime/model-evidence.md': {'"target": {"service": "synthetic-host", "model_identifier": "gpt-image-2.5-flare", "operation": "generation"},': 1,
                                          'Provider interfaces expose different signals. OpenAI documents `error.code = moderation_blocked` in its [image-generation guide](https://developers.openai.com/api/docs/guides/image-generation).': 1,
                                          "Google's [Interactions safety guide](https://ai.google.dev/gemini-api/docs/safety-settings) documents structured error codes for blocked requests.": 1,
                                          "xAI's [image guide](https://docs.x.ai/developers/model-capabilities/images/generation) documents the `respect_moderation` response field.": 1,
                                          '"target":{"model_identifier":"vendor:offered@1","operation":"imageInference","service":"runware"}': 1},
 'references/runtime/prompt-weighting.md': {"For example, Runware's SDXL page lists `compel` and `sdEmbeds`, while its FLUX.1\nSchnell page lists only `sdEmbeds` as the actual allowed value.": 1,
                                            'a native Runware-shaped request': 1,
                                            '- [Runware prompts and weighting](https://runware.ai/docs/learn/prompts)': 1,
                                            '- [Runware SDXL native control](https://runware.ai/docs/models/sdxl)': 1,
                                            '- [Runware FLUX.1 Schnell allowed control](https://runware.ai/docs/models/flux-1-schnell)': 1},
 'references/runtime/scene-mask-planning.md': {"Runware's native inpainting mask convention is documented in\nhttps://runware.ai/docs/learn/image-inpainting.": 1},
 'references/runtime/workflow-walkthrough.md': {"2. read the generation route and the model's guidance card for `grok-imagine-image-2.0` on Runware;": 1,
                                                '"contract": "@pack/01a0043b-2250-720d-87b7-f1e6fd7ed230/resources/observed-schemas/grok-imagine-image-2.0.runware.json"},': 1,
                                                '"request": {"height": 1248, "model": "xai:grok-imagine@image-2.0", "numberResults": 1, "settings": {"quality": "medium"},': 1},
 'scripts/validate.py': {"'agents/openai.yaml'": 1,
                         'root / "agents" / "openai.yaml"': 1,
                         '"references/adapters/gpt-image.md"': 1,
                         '"# GPT Image Adapter"': 1,
                         '"references/adapters/midjourney-niji.md"': 1,
                         '"# Midjourney and Niji Adapter"': 1,
                         '"# FLUX Adapter"': 1,
                         '"references/adapters/sdxl-comfyui.md"': 1,
                         '"# SDXL and ComfyUI Adapter"': 1,
                         '"references/adapters/novelai.md"': 1,
                         '"# NovelAI Adapter"': 1}}


def generic_source_paths(root: Path) -> list[Path]:
    paths = []
    for directory in ("scripts", "templates", "references"):
        for path in (root / directory).rglob("*"):
            if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
                continue
            relative = path.relative_to(root)
            if "__pycache__" in relative.parts:
                continue
            if relative.as_posix() in CONCRETE_ADAPTER_DOCUMENTS:
                continue
            if directory == "scripts":
                if relative.parts[:2] == ("scripts", "fixtures"):
                    continue
                name = path.name
                if path.suffix == ".py" and (name.startswith("test_") or name.endswith(("_test.py", "_fixtures.py"))):
                    continue
            paths.append(path)
    return sorted(paths)


def provider_name_findings(root: Path, *, check_excerpts: bool = True) -> list[str]:
    """Locate provider names outside their declared source excerpts."""
    findings = []
    for path in generic_source_paths(root):
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        for excerpt, count in SOURCE_EXCERPTS.get(relative, {}).items():
            if check_excerpts and text.count(excerpt) < count:
                findings.append(f"{relative}: missing declared provider excerpt: {excerpt[:90]!r}")
            blank = "".join("\n" if character == "\n" else " " for character in excerpt)
            text = text.replace(excerpt, blank, count)
        allowed = SERVICE_ADAPTER_NAMES.get(relative, frozenset())
        matches = sorted(
            (match.start(), match.group(), label)
            for label, pattern in PROVIDER_PATTERNS if label not in allowed
            for match in pattern.finditer(text)
        )
        for offset, value, label in matches:
            line = text.count("\n", 0, offset) + 1
            column = offset - text.rfind("\n", 0, offset)
            findings.append(f"{relative}:{line}:{column}: provider/model name {value!r} ({label})")
    return findings


class ProviderNameScanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cpb-neutral-source-scan-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, relative: str, text: str):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_shared_sources_have_no_undeclared_provider_names(self):
        for directory in ("scripts", "templates", "references"):
            self.assertTrue((ROOT / directory).is_dir())
        paths = generic_source_paths(ROOT)
        self.assertIn(ROOT / "scripts/model_suitability.py", paths)
        self.assertIn(ROOT / "templates/image-input-plan.template.json", paths)
        self.assertIn(ROOT / "references/runtime/model-evidence.md", paths)
        relative_paths = {path.relative_to(ROOT).as_posix() for path in paths}
        self.assertFalse(set(SOURCE_EXCERPTS) - relative_paths, "source excerpts must name scanned files")
        for relative, excerpts in SOURCE_EXCERPTS.items():
            for excerpt in excerpts:
                self.assertTrue(any(pattern.search(excerpt) for _, pattern in PROVIDER_PATTERNS),
                                f"{relative}: unnecessary provider excerpt: {excerpt!r}")
        findings = provider_name_findings(ROOT)
        self.assertFalse(findings, "\n".join(findings))

    def test_injected_name_fails_in_each_generic_tree(self):
        for relative in ("scripts/defaults.py", "templates/task.json", "references/runtime/guide.md"):
            with self.subTest(relative=relative):
                self.write(relative, "Neutral heading\nUse Seedream for the default model.\n")
        findings = provider_name_findings(self.root)
        self.assertEqual(3, len(findings), findings)
        for relative in ("scripts/defaults.py", "templates/task.json", "references/runtime/guide.md"):
            self.assertIn(f"{relative}:2:5: provider/model name 'Seedream' (Seedream)", findings)

    def test_aliases_case_and_identifier_separators_are_detected(self):
        for token, expected in (
            ("OPEN_AI", "OpenAI"),
            ("provider_GPT_IMAGE_2", "GPT Image"),
            ("nanobanana2", "Nano Banana"),
            ("Nano_Banana_2", "Nano Banana"),
            ("Byte-Dance:SeeDream@5.0", "Seedream"),
            ("google:gemini-image", "Gemini"),
            ("Qwen-Image-3.0", "Qwen"),
            ("bfl:flux@3-image", "BFL"),
            ("bfl:flux@3-image", "FLUX"),
            ("flux@3-image", "FLUX"),
            ("flux/3-image", "FLUX"),
            ("flux-3-image", "FLUX"),
            ('"flux"', "FLUX"),
            ("FLUX", "FLUX"),
            ("Flux", "FLUX"),
            ("Stable_Diffusion", "Stable Diffusion"),
            ("stability.ai", "Stability AI"),
            ("replicate.com", "Replicate"),
            ("fal.ai", "Fal"),
        ):
            with self.subTest(token=token):
                self.write("scripts/selection.py", token)
                findings = provider_name_findings(self.root)
                self.assertTrue(any(f"({expected})" in item for item in findings), findings)

    def test_common_words_and_name_substrings_are_unaffected(self):
        self.write("references/runtime/physics.md",
                   "Replicate immutable artwork; check lighting stability and magnetic flux.\n"
                   "Words such as seedreamer, outflux, and googled remain ordinary text.\n")
        self.assertEqual([], provider_name_findings(self.root))

    def test_fixture_and_concrete_adapter_ownership_is_excluded(self):
        for relative in (
            "packs/commons/records/models.json",
            "packs/author-owned/resources/evidence.md",
            "examples/model-evidence/observation.json",
            "scripts/fixtures/models.json",
            "scripts/model_cases_fixtures.py",
            "scripts/model_cases_smoke_test.py",
            "scripts/test_model_cases.py",
            "references/adapters/gpt-image.md",
            "references/adapters/sdxl-comfyui.md",
        ):
            self.write(relative, "Seedream GPT Image OpenAI")
        self.assertEqual([], provider_name_findings(self.root))
        self.assertEqual([], generic_source_paths(self.root))

    def test_generic_adapters_and_similarly_named_paths_stay_guarded(self):
        relatives = (
            "references/adapters/instruction-edit.md",
            "references/adapters/unlisted-interface.md",
            "references/adapters/upscale.md",
            "references/runtime/adapter-notes.md",
            "scripts/fixture_router.py",
            "scripts/fixtures_extra/router.py",
            "scripts/test_policy.json",
        )
        for relative in relatives:
            self.write(relative, "Seedream")
        findings = provider_name_findings(self.root, check_excerpts=False)
        self.assertEqual(len(relatives), len(findings), findings)

    def test_owned_transport_still_rejects_other_providers(self):
        self.write("scripts/transport_runware.py", 'SERVICE = "runware"\nMODEL = "Seedream"\n')
        self.assertEqual(
            ["scripts/transport_runware.py:2:10: provider/model name 'Seedream' (Seedream)"],
            provider_name_findings(self.root),
        )

    def test_host_metadata_reference_does_not_allow_a_model_default(self):
        self.write("scripts/validate.py", "'agents/openai.yaml' + 'Seedream'\n")
        self.assertEqual(
            ["scripts/validate.py:1:25: provider/model name 'Seedream' (Seedream)"],
            provider_name_findings(self.root, check_excerpts=False),
        )

    def test_duplicate_owned_excerpt_is_detected(self):
        self.write("scripts/validate.py", "'agents/openai.yaml'\n'agents/openai.yaml'\n")
        self.assertEqual(
            ["scripts/validate.py:2:9: provider/model name 'openai' (OpenAI)"],
            provider_name_findings(self.root, check_excerpts=False),
        )

    def test_missing_owned_excerpt_fails(self):
        self.write("references/runtime/scene-mask-planning.md", "Neutral text.\n")
        findings = provider_name_findings(self.root)
        self.assertEqual(1, len(findings), findings)
        self.assertIn("missing declared provider excerpt", findings[0])


class ModelNeutralityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cpb-model-neutrality-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "supplied.json").write_text('[]', encoding='utf-8')
        (self.root / "state.json").write_text('{}', encoding='utf-8')
        (self.root / "studio.json").write_text('[]', encoding='utf-8')
        (self.root / "edit.json").write_text(json.dumps({"model": {"catalog_model": "fixture-model"}}), encoding='utf-8')

    def invoke(self, mode: str, file_name: str, *, model: str | None = None):
        argv = [mode, str(self.root / file_name), '--output-dir', str(self.root / 'carriers'), '--out', str(self.root / 'prepared.json')]
        if mode in ('--studio-selection-file', '--image-input-plan-file'):
            argv.extend(['--studio', str(self.root)])
        if model is not None:
            argv.extend(['--model', model])
        buf = io.StringIO()
        with patch.object(references, 'resolve_pack_runtime', return_value=SimpleNamespace(settings='fixture-runtime')):
            with patch.object(references, 'configure_pack_runtime'):
                with contextlib.redirect_stdout(buf):
                    result = references.main(argv)
        return result, json.loads(buf.getvalue())

    def test_no_implicit_model_for_supplied_state_or_studio(self):
        for option, file_name in [
            ('--supplied-selection-file', 'supplied.json'),
            ('--state-selection-file', 'state.json'),
            ('--studio-selection-file', 'studio.json'),
        ]:
            with self.subTest(mode=option):
                code, report = self.invoke(option, file_name)
                self.assertEqual(code, 1)
                self.assertFalse(report['ok'])
                self.assertIn('--model is required', report['errors'][0])
                self.assertFalse((self.root / 'prepared.json').exists())

    def test_supplied_model_is_forwarded_unchanged(self):
        named = 'fixture-image-model'
        with patch.object(references, 'prepare_references', return_value={'fixture': True}) as stub:
            code, report = self.invoke('--supplied-selection-file', 'supplied.json', model=named)
        self.assertEqual(code, 0)
        self.assertTrue(report['fixture'])
        self.assertEqual(stub.call_args.kwargs['model'], named)

    def test_plan_may_supply_its_own_selected_model(self):
        with patch.object(references, 'prepare_image_input_references', return_value={'fixture': True}) as stub:
            code, report = self.invoke('--image-input-plan-file', 'edit.json')
        self.assertEqual(code, 0)
        self.assertTrue(report['fixture'])
        self.assertIsNone(stub.call_args.kwargs['model'])

    def test_cli_fixture_validation_follows_the_authored_model(self):
        from smoke_fixtures import cli_with_fixture_retrieval
        spec_path = self.root / 'production-spec.json'
        prompt_path = self.root / 'prompt.txt'
        prompt_path.write_text('Synthetic object on a table.', encoding='utf-8')
        base = ['--production-root', str(self.root), '--production-run', 'fixture-run',
                '--production-spec-file', str(spec_path), '--prompt-file', str(prompt_path),
                '--visual-continuity-file', 'supplied-visual.json',
                '--retrieval-record-file', 'supplied-retrieval.json']

        def inspect(argv):
            if '--request-validation-file' not in argv:
                return None
            return json.loads(Path(argv[argv.index('--request-validation-file') + 1]).read_text(encoding='utf-8'))

        for specification, explicit, expected in [
            ('fixture-model-from-spec', None, 'fixture-model-from-spec'),
            ('fixture-model-from-spec', 'fixture-model-from-cli', 'fixture-model-from-cli'),
            ('', None, None),
        ]:
            with self.subTest(specification=specification, explicit=explicit):
                spec_path.write_text(json.dumps({'target_model': specification}), encoding='utf-8')
                argv = base + (['--model', explicit] if explicit else [])
                with patch('catalog_retrieval.runtime.configure_pack_runtime'), \
                     patch('visual_fixtures.fixture_root', return_value=self.root), \
                     patch('request_validation_fixtures.fixture_validation',
                           side_effect=lambda root, model, **kwargs: {'selected_model': model}) as validation:
                    result = cli_with_fixture_retrieval(inspect, argv)
                if expected is None:
                    self.assertIsNone(result)
                    validation.assert_not_called()
                else:
                    self.assertEqual(result, {'selected_model': expected})
                    self.assertTrue(all(call.args[1] == expected for call in validation.call_args_list))

    def test_generic_templates_hold_no_provider_selection(self):
        brief = json.loads((ROOT / 'templates/brief-template.json').read_text(encoding='utf-8'))
        package = json.loads((ROOT / 'templates/generation-package-template.json').read_text(encoding='utf-8'))
        self.assertEqual(brief['target_model'], '')
        self.assertEqual(package['status'], 'template')
        self.assertEqual(package['model'], '')
        self.assertEqual(package['generation_payload']['prompt_recommendations']['resolved_model_id'], '')
        self.assertEqual(package['generation_payload']['negative_transport']['mode'], '')
        self.assertFalse(any(package['generation_payload']['transports'][x]['available']
                         for x in ('separate', 'integrated', 'native_subset')))

    def test_general_readme_has_no_one_model_footnote(self):
        readme = (ROOT / 'README.md').read_text(encoding='utf-8')
        self.assertNotIn('## Commons model note:', readme)
        self.assertIn('selected model', readme)

    def test_common_guide_does_not_force_one_subject_or_location(self):
        guide = json.loads((ROOT / 'packs/commons/resources/prompt-writing-guide/guide.json').read_text(encoding='utf-8'))
        rules = '\n'.join(rule for section in guide['sections'] for rule in section.get('rules', []))
        self.assertNotIn('Treat one character as the default', rules)
        self.assertIn('scene without characters', rules)
        self.assertIn('unless the task changes it', rules)
        self.assertIn('Do not invent a setting or props', rules)
        self.assertIn('do not reframe without specific authorization', rules)
        self.assertNotIn('Give every rendition a concrete situation block', rules)
        self.assertNotIn('Force a crop with three supports', rules)


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    unittest.main(verbosity=2)
