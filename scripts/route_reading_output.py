"""Display complete reading bodies while retaining the full JSON response.

Presentation changes neither source selection nor delivery coverage. The
reader still flushes its bodies before publishing successful delivery.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import secrets
from typing import TextIO

from execution_contract import assert_public_path


class TextReadingOutput:
    """Own one new response file and the text shown by one public read."""

    def __init__(self, directory: Path, stream: TextIO):
        self.stream = stream
        reconfigure = getattr(stream, 'reconfigure', None)
        if reconfigure is not None:
            # Plain source text keeps its own CR/LF bytes on every host. The
            # CLI's standard-stream owner already selects UTF-8 encoding.
            reconfigure(newline='\n')
        self.directory = directory.absolute()
        assert_public_path(self.directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / ('reading-' + secrets.token_hex(16) + '.json')
        self.response = self.path.open('x', encoding='utf-8', newline='\n')
        self.begun = False
        self.finished = False
        self.metadata = {}
        self.response_digest = hashlib.sha256()
        self.response_size = 0

    def _retain(self, text: str) -> None:
        self.response.write(text)
        raw = text.encode('utf-8')
        self.response_digest.update(raw)
        self.response_size += len(raw)

    def begin(self, body: list[dict], metadata: dict) -> None:
        self.metadata = metadata
        self._retain('{"metadata": ' + json.dumps(metadata, ensure_ascii=False)
                     + ', "body": ' + json.dumps(body, ensure_ascii=False))
        self.response.flush()
        self.begun = True
        for row in body:
            source, text = row['metadata'], row['text']
            raw = text.encode('utf-8')
            start, end = source.get('start', 0), source.get('end', len(raw))
            if len(raw) != end - start:
                raise ValueError('The displayed reading body differs from its declared byte range.')
            origin = source.get('source_start', 0)
            self.stream.write('\n=== ' + source.get('path', source['kind'])
                + ' | source bytes ' + str(origin + start) + ':' + str(origin + end) + ' ===\n')
            self.stream.write(text)
        # Successful delivery still depends on the actual host output, not
        # merely the retained response file accepting these bytes.
        self.stream.flush()

    def _actions(self, value):
        """Carry presentation through read actions without changing their scope."""
        result = copy.deepcopy(value)
        def visit(item):
            if isinstance(item, dict):
                argv = item.get('argv')
                if isinstance(argv, list):
                    scripts = [number for number, word in enumerate(argv)
                               if isinstance(word, str) and Path(word).name == 'execution_routes.py']
                    if scripts and argv[scripts[0] + 1:scripts[0] + 2] == ['read']:
                        for option, selected in (('--view', 'text'), ('--response-dir', str(self.directory))):
                            if option in argv:
                                argv[argv.index(option) + 1] = selected
                            else:
                                argv.extend((option, selected))
                for child in item.values():
                    visit(child)
            elif isinstance(item, list):
                for child in item:
                    visit(child)
        for name in ('actions', 'context_reuse', 'section_selection', 'source_navigation'):
            if name in result:
                visit(result[name])
        return result

    def finish(self, value: dict) -> None:
        visible = self._actions(value)
        if not self.finished:
            self._retain(', ' + json.dumps(visible, ensure_ascii=False)[1:] + '\n')
            self.response.flush()
            self.response.close()
            self.finished = True
            from operation_context import current
            if current() is not None:
                current().artifact(self.path, content_sha256=self.response_digest.hexdigest(), size=self.response_size)
        failed = (visible.get('ok') is False or visible.get('error') is not None
                  or (visible.get('choices_binding') or {}).get('bound') is False)
        if visible.get('mode') == 'index':
            fields = ('selector', 'path', 'kind', 'source_start', 'source_end', 'size',
                      'selected_by', 'selection_reason_ids', 'selection_scope')
            sections = ('selector', 'heading', 'source_start', 'source_end', 'bytes', 'selection_reason_ids')
            sources = [{**{key: row[key] for key in fields if key in row},
                        'sections': [{key: part[key] for key in sections if key in part}
                                     for part in row.get('sections', [])]}
                       for row in visible.get('index', [])]
            self.stream.write(json.dumps({'scope': self.metadata, 'sources': sources,
                'selection_reasons': visible.get('selection_reasons', {})}, ensure_ascii=False) + '\n')
        if failed:
            # Exceptional responses retain every diagnostic and repair action.
            controls = visible
        else:
            actions = visible.get('actions') or {}
            next_action = next((actions[name] for name in ('continue', 'next', 'all') if actions.get(name)), None)
            if visible.get('reading') is not None:
                next_action = None
            controls = {key: visible[key] for key in ('ok', 'same_context_required', 'reading_context') if key in visible}
            controls.update(progress={key: visible.get('progress', {}).get(key) for key in
                ('required_bytes', 'reused_bytes', 'delivered_bytes', 'remaining_bytes')},
                reading=visible.get('reading'), choices_binding=visible.get('choices_binding'),
                next_action=next_action)
            for key in ('warnings', 'warning', 'diagnostics', 'notices', 'limitations'):
                if key in visible:
                    controls[key] = visible[key]
        controls['response_file'] = str(self.path)
        self.stream.write('\n=== READING CONTROL ===\n' + json.dumps(controls, ensure_ascii=False) + '\n')
        self.stream.flush()

    def close(self) -> None:
        if not self.response.closed:
            self.response.close()
