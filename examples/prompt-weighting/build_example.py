#!/usr/bin/env python3
"""Regenerate a deterministic, synthetic syntax report and native request preview.

No provider is contacted, no model is selected from private content, and no
approval or executable Generation Package is fabricated by this example.
"""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import prompt_weighting
import transport_runware
from model_contract import apply_prompt_recommendations

POSITIVE = '("solo, (blue eyes)1.2, long hair+", "forest, soft lighting").and(1, 0.8)'
NEGATIVE = '("lettering+, watermark", "signature").blend(1, 0.5)'


def outputs() -> dict[str, bytes]:
    parameters = {'width': 1024, 'height': 1024, 'steps': 30, 'promptWeighting': 'compel'}
    inspection = prompt_weighting.require_pair(POSITIVE, NEGATIVE, 'compel')
    offering = {'service': 'runware', 'model_identifier': 'synthetic:not-a-deployable-model',
                'request_keys': {'prompt': ['positivePrompt'], 'negative prompt': ['negativePrompt']}}
    forwarding = {'effective_prompt': POSITIVE, 'selected_transport': {'mode': 'separate-field', 'rendition': {'negative': NEGATIVE}},
                  'parameters': parameters}
    with patch.object(transport_runware.uuid, 'uuid4', return_value='00000000-0000-4000-8000-000000000001'):
        request = transport_runware.compile_request({'host_forwarding': forwarding}, offering, {'operations': {'imageInference': {}}})
    _, _, recommendations = apply_prompt_recommendations({'recommendation_merge_mode': 'tag-list', 'recommended_positive_prompt': 'masterpiece'},
        prompt=POSITIVE, negative_prompt=NEGATIVE, weighting='compel')
    value = {'purpose': 'Synthetic syntax and wire-layout demonstration; not executable provider capability or author approval.',
             'inspection': inspection, 'recommendation_audit': recommendations, 'native_preview': request,
             'sdembeds_comparison': prompt_weighting.require_pair('solo, (blue eyes:1.2), [long hair]', '(lettering:1.2), watermark', 'sdEmbeds')}
    data = {'inspection.json': value, 'parameters.json': parameters}
    result = {key: (json.dumps(item, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8') for key, item in data.items()}
    result.update({'positive.txt': (POSITIVE + '\n').encode('utf-8'), 'negative.txt': (NEGATIVE + '\n').encode('utf-8')})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--out', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    expected = outputs()
    differences = []
    for name, raw in expected.items():
        target = args.out / name
        if args.check:
            if not target.is_file() or target.read_bytes() != raw: differences.append(name)
        else:
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
    print(json.dumps({'ok': not differences, 'files': list(expected), 'differences': differences, 'network': False}, indent=2))
    return 1 if differences else 0


if __name__ == '__main__':
    import stdio_utf8
    stdio_utf8.configure()
    raise SystemExit(main())
