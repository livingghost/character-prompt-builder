"""Read explicitly selected prompt syntax without rewriting the transmitted text.

A model's learned tag family and a service's weighting grammar are independent.
The native promptWeighting control selects compel or sdEmbeds. Without that
control, CPB treats punctuation literally rather than guessing a backend parser.
This module inspects text and clause boundaries; the service builds embeddings.
"""
from __future__ import annotations

import math
import re
from typing import Any, Mapping

SYNTAXES = ('literal', 'sdEmbeds', 'compel')
NUMBER = re.compile(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?')
METHOD = re.compile(r'\.([A-Za-z_][A-Za-z_0-9]*)\s*\(')
BREAK = re.compile(r'(?<![\w\\])BREAK(?!\w)')
MAX_DEPTH = 64


class SyntaxError(ValueError):
    """A bounded syntax diagnostic located in the original author text."""
    def __init__(self, code: str, message: str, start: int, end: int | None = None):
        self.code, self.start, self.end = code, start, start + 1 if end is None else end
        super().__init__(f'{code} at characters {self.start}:{self.end}: {message}')

    def finding(self, channel: str) -> dict:
        return {'severity': 'problem', 'check': self.code, 'message': str(self),
                'terms': [], 'channel': channel, 'range': {'start': self.start, 'end': self.end}}


def selected(parameters: Mapping[str, Any]) -> str:
    """Read the resolved native control; offering/mode schemas authorize its use."""
    if not isinstance(parameters, Mapping):
        raise ValueError('weighting selection requires resolved parameter values')
    if 'promptWeighting' not in parameters:
        return 'literal'
    value = parameters['promptWeighting']
    if value not in ('compel', 'sdEmbeds'):
        raise ValueError('promptWeighting must name a supported grammar: compel or sdEmbeds')
    return value


def _number(text: str, offset: int) -> float:
    if not NUMBER.fullmatch(text.strip()):
        raise SyntaxError('weight value', 'expected one finite numeric weight', offset, offset + len(text))
    value = float(text)
    if not math.isfinite(value):
        raise SyntaxError('weight value', 'a weight must be finite', offset, offset + len(text))
    return value


def _matching(text: str, opening: int, end: int) -> int:
    """Find a balanced group, honoring escaped delimiters and quoted clauses."""
    pair = {'(': ')', '[': ']'}
    stack = [pair[text[opening]]]
    quote = False
    index = opening + 1
    while index < end:
        char = text[index]
        if char == '\\':
            index += 2
            continue
        if char == '"':
            quote = not quote
        elif not quote:
            if char in pair:
                stack.append(pair[char])
                if len(stack) > MAX_DEPTH:
                    raise SyntaxError('syntax depth', f'group nesting exceeds {MAX_DEPTH}', index)
            elif char in ')]':
                if char != stack[-1]:
                    raise SyntaxError('bracket', 'mismatched closing delimiter', index)
                stack.pop()
                if not stack:
                    return index
        index += 1
    raise SyntaxError('bracket', 'unclosed group', opening, end)


def _quoted_end(text: str, opening: int, end: int) -> int:
    index = opening + 1
    while index < end:
        if text[index] == '\\':
            index += 2
        elif text[index] == '"':
            return index
        else:
            index += 1
    raise SyntaxError('quote', 'unclosed quoted phrase', opening, end)


def split_top_level(text: str, start: int = 0, end: int | None = None) -> list[tuple[int, int]]:
    """Comma-separated slices; commas inside groups, quotes and escapes stay put."""
    end = len(text) if end is None else end
    index = first = start
    result = []
    while index < end:
        char = text[index]
        if char == '\\': index += 2; continue
        if char in '([': index = _matching(text, index, end) + 1; continue
        if char == '"': index = _quoted_end(text, index, end) + 1; continue
        if char == ',': result.append((first, index)); first = index + 1
        index += 1
    result.append((first, end))
    return result


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace(): start += 1
    while end > start and text[end - 1].isspace(): end -= 1
    return start, end


class _Reader:
    def __init__(self, text: str, syntax: str):
        self.text, self.syntax = text, syntax
        self.weights: list[dict] = []
        self.notes: list[dict] = []

    def _weight(self, value: float, start: int, end: int, spelling: str) -> None:
        if not math.isfinite(value):
            raise SyntaxError('weight value', 'nested or repeated weights are not finite', start, end)
        self.weights.append({'range': {'start': start, 'end': end}, 'value': value, 'spelling': spelling})

    def suffix(self, index: int, end: int, *, numeric: bool) -> tuple[float, int]:
        text = self.text
        method_start = index
        while method_start < end and text[method_start].isspace(): method_start += 1
        method = METHOD.match(text, method_start, end)
        if method:
            if method[1] != 'attend':
                raise SyntaxError('unsupported operator', 'only .attend may weight a fragment; '
                                  '.blend/.and belong to the complete conditioning expression', index, method.end())
            close = _matching(text, method.end() - 1, end)
            value = text[method.end():close].strip()
            if re.fullmatch(r'\++|-+', value):
                try: amount = (1.1 if value[0] == '+' else .9) ** len(value)
                except OverflowError: raise SyntaxError('weight value', 'weight is not finite', index, close + 1) from None
            else: amount = _number(value, method.end())
            self._weight(amount, index, close + 1, text[index:close + 1])
            return amount, close + 1
        match = NUMBER.match(text, index, end) if numeric else None
        if match:
            value = _number(match[0], index)
            self._weight(value, index, match.end(), match[0])
            return value, match.end()
        if index < end and text[index] in '+-':
            sign = text[index]; last = index
            while last < end and text[last] == sign: last += 1
            if last < end and text[last] in '+-':
                raise SyntaxError('weight value', 'mixed + and - suffixes are not one weight', index, last + 1)
            try: value = (1.1 if sign == '+' else .9) ** (last - index)
            except OverflowError: raise SyntaxError('weight value', 'weight is not finite', index, last) from None
            self._weight(value, index, last, text[index:last])
            return value, last
        return 1.0, index

    def fragments(self, start: int, end: int, depth: int = 0) -> list[dict]:
        if depth > MAX_DEPTH:
            raise SyntaxError('syntax depth', f'group nesting exceeds {MAX_DEPTH}', start, end)
        result: list[dict] = []
        text = self.text
        def add(value: str, a: int, b: int, weight: float = 1.0, separator: bool = False):
            result.append({'text': value, 'start': a, 'end': b, 'weight': weight, 'separator': separator})
        index = start
        while index < end:
            char = text[index]
            if char == '\\':
                if index + 1 == end:
                    raise SyntaxError('escape', 'trailing escape has no character', index)
                add(text[index + 1], index, index + 2); index += 2; continue
            if char == ',' or (self.syntax == 'sdEmbeds' and (m := BREAK.match(text, index, end))):
                size = 1 if char == ',' else len(m[0])
                add(char if size == 1 else 'BREAK', index, index + size, separator=True); index += size; continue
            if char in ')]':
                raise SyntaxError('bracket', 'unexpected closing delimiter', index)
            if self.syntax == 'compel' and char in '[]':
                raise SyntaxError('syntax mismatch', 'square-bracket de-emphasis belongs to sdEmbeds; '
                                  'use a Compel suffix or escape literal brackets', index)
            if char == '"' and self.syntax == 'compel':
                close = _quoted_end(text, index, end)
                child = self.fragments(index + 1, close, depth + 1)
                weight, following = self.suffix(close + 1, end, numeric=True)
                for fragment in child:
                    fragment['weight'] *= weight
                    if not math.isfinite(fragment['weight']): raise SyntaxError('weight value', 'nested weight is not finite', index, following)
                result.extend(child); index = following; continue
            if char in '([':
                close = _matching(text, index, end)
                content_end = close
                if self.syntax == 'sdEmbeds':
                    weight = 1.1 if char == '(' else 1 / 1.1
                    match = re.search(r'(?<!\\):\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*$', text[index + 1:close]) if char == '(' else None
                    if match:
                        a = index + 1 + match.start()
                        # A weight belongs only to this group's outermost trailing suffix.
                        if len(split_top_level(text, index + 1, a)) >= 1:
                            content_end = a; weight = _number(match[1], a + 1)
                    self._weight(weight, index, close + 1, text[index:close + 1])
                    following = close + 1
                    if NUMBER.match(text, following, end) or (following < end and text[following] in '+-'):
                        raise SyntaxError('syntax mismatch', 'postfix weights belong to Compel; use (term:weight) for sdEmbeds', following)
                else:
                    weight, following = self.suffix(close + 1, end, numeric=True)
                child = self.fragments(index + 1, content_end, depth + 1)
                if not any(row['text'].strip() and not row['separator'] for row in child):
                    raise SyntaxError('empty tag', 'weighted/grouped text contains no term', index, close + 1)
                for fragment in child:
                    fragment['weight'] *= weight
                    if not math.isfinite(fragment['weight']): raise SyntaxError('weight value', 'nested weight is not finite', index, following)
                result.extend(child); index = following; continue
            if METHOD.match(text, index, end):
                raise SyntaxError('unsupported operator', 'operator has no valid target or is outside the supported hosted grammar', index)
            if text.startswith(('withLora(', 'useLora('), index):
                raise SyntaxError('unsupported operator', 'use the target service LoRA controls, not an embedding-parser macro', index)
            if char == ':' and NUMBER.match(text, index + 1, end):
                raise SyntaxError('weight binding' if self.syntax == 'sdEmbeds' else 'syntax mismatch',
                                  'colon weights belong immediately before the sdEmbeds closing parenthesis; '
                                  'Compel uses (term)weight', index)
            # Whitespace is preserved for exact lexical reconstruction.
            if char.isspace(): add(char, index, index + 1); index += 1; continue
            first = index
            while index < end and not text[index].isspace() and text[index] not in '\\,()[]"':
                if METHOD.match(text, index, end): break
                if text[index] == ':' and NUMBER.match(text, index + 1, end): break
                index += 1
            if index == first:
                add(text[index], index, index + 1); index += 1; continue
            value = text[first:index]; weight = 1.0
            if self.syntax == 'compel':
                match = re.search(r'(\++|-+)$', value)
                if match and match.start() > 0:
                    weight, ignored = self.suffix(first + match.start(), index, numeric=False)
                    value = value[:match.start()]
                else:
                    following = index
                    while following < end and text[following].isspace(): following += 1
                    if METHOD.match(text, following, end):
                        weight, index = self.suffix(index, end, numeric=False)
            add(value, first, index, weight)
        return result

    def clause(self, start: int, end: int, index: int, weight: float = 1.0) -> dict:
        start, end = _trim(self.text, start, end)
        if self.syntax == 'compel' and start < end and self.text[start] == '"' and _quoted_end(self.text, start, end) == end - 1:
            body_start, body_end = start + 1, end - 1
        else: body_start, body_end = start, end
        fragments = self.fragments(body_start, body_end) if self.syntax != 'literal' else [
            {'text': self.text[a:b], 'start': a, 'end': b, 'weight': 1.0, 'separator': False}
            for a, b in [(body_start, body_end)]]
        tags: list[dict] = []; current: list[dict] = []; chunk = 0
        def finish():
            nonlocal current
            value = ''.join(item['text'] for item in current).strip()
            if value:
                tags.append({'text': value, 'range': {'start': current[0]['start'], 'end': current[-1]['end']},
                             'weights': sorted({item['weight'] for item in current if item['text'].strip()}),
                             'chunk': chunk})
            current = []
        if self.syntax == 'literal':
            # No weighting semantics are assumed for commas/parentheses on a plain backend.
            for a, b in split_literal(self.text, body_start, body_end):
                value = self.text[a:b].strip()
                if value: tags.append({'text': value, 'range': {'start': a, 'end': b}, 'weights': [1.0], 'chunk': 0})
        else:
            for fragment in fragments:
                if fragment['separator']:
                    finish()
                    if fragment['text'] == 'BREAK': chunk += 1
                else: current.append(fragment)
            finish()
        return {'index': index, 'range': {'start': start, 'end': end}, 'weight': weight, 'tags': tags,
                'text': ''.join(item['text'] for item in fragments)}


def split_literal(text: str, start: int, end: int) -> list[tuple[int, int]]:
    positions = [start - 1, *[i for i in range(start, end) if text[i] == ','], end]
    return [(a + 1, b) for a, b in zip(positions, positions[1:])]


def parse(text: str, syntax: str = 'literal') -> dict:
    """Return independent conditioning clauses and lexical spans for inspection."""
    if syntax not in SYNTAXES or not isinstance(text, str):
        raise ValueError('an explicit supported syntax and text string are required')
    reader = _Reader(text, syntax)
    start, end = _trim(text, 0, len(text))
    operation, normalize, clauses = 'prompt', None, None
    if syntax == 'compel' and start < end and text[start] == '(':
        close = _matching(text, start, end)
        suffix = close + 1
        while suffix < end and text[suffix].isspace(): suffix += 1
        match = METHOD.match(text, suffix, end)
        if match and match[1] in {'blend', 'and', 'add'}:
            operation = 'and' if match[1] == 'add' else match[1]
            last = _matching(text, match.end() - 1, end)
            if text[last + 1:end].strip():
                raise SyntaxError('compound scope', 'a conditioning expression must consume the whole prompt; '
                                  'place shared instructions in its authored clauses', last + 1, end)
            pieces = split_top_level(text, start + 1, close)
            if any(not text[a:b].strip() for a, b in pieces):
                raise SyntaxError('clause', 'a prompt list contains a missing clause', start, close + 1)
            arguments = [text[a:b].strip() for a, b in split_top_level(text, match.end(), last)]
            normalize = operation == 'blend'
            if operation == 'blend' and arguments[-1] == 'no_normalize':
                normalize = False; arguments.pop()
            if arguments == ['']: arguments = []
            weights = [_number(value, match.end()) for value in arguments] or [1.0] * len(pieces)
            if len(weights) != len(pieces):
                raise SyntaxError('clause weights', 'the number of weights differs from the number of conditioning prompts', match.end(), last)
            if normalize:
                try: total = math.fsum(weights)
                except OverflowError: total = float('inf')
                if not math.isfinite(total) or total == 0:
                    raise SyntaxError('blend normalization', 'normalized blend weights must have a finite nonzero sum', match.end(), last)
            for a, b in pieces:
                left, right = _trim(text, a, b)
                if text[left] not in '"(' and any(char.isspace() for char in text[left:right]):
                    raise SyntaxError('clause', 'quote or parenthesize a multi-word conditioning clause', left, right)
            clauses = [reader.clause(a, b, i, weights[i]) for i, (a, b) in enumerate(pieces)]
    if clauses is None:
        clauses = [reader.clause(start, end, 0)]
    return {'syntax': syntax, 'operator': operation, 'normalize': normalize, 'clauses': clauses,
            'weights': reader.weights, 'notes': reader.notes}


def inspect_pair(prompt: str, negative: str, syntax: str) -> dict:
    result = {'syntax': syntax, 'channels': {}, 'findings': []}
    for channel, text in [('positive', prompt), ('negative', negative)]:
        try: result['channels'][channel] = parse(text, syntax)
        except SyntaxError as exc:
            result['channels'][channel] = None; result['findings'].append(exc.finding(channel))
    return result


def require_pair(prompt: str, negative: str, syntax: str) -> dict:
    result = inspect_pair(prompt, negative, syntax)
    if result['findings']:
        raise ValueError('PROMPT_SYNTAX_INVALID: ' + '; '.join(row['message'] for row in result['findings']))
    return result


def wire_selection(rendered: dict) -> str:
    """Use the actual native field and its declared parameter layout, not prompt guessing."""
    import request_contract as rc
    request, layout = rendered['request'], rendered['layout']
    declared = [row for row in layout['fields'] if row['field'] == ['promptWeighting']]
    if 'promptWeighting' not in request: return 'literal'
    if len(declared) != 1 or declared[0]['kind'] != 'parameter':
        raise ValueError('promptWeighting must be an explicitly declared parameter in the sealed wire layout')
    return selected({'promptWeighting': rc.get(request, ['promptWeighting'])})


def guide(syntax: str) -> dict:
    if syntax not in SYNTAXES: raise ValueError('unknown prompt syntax')
    return {'syntax': syntax, 'control': None if syntax == 'literal' else {'promptWeighting': syntax},
        'meaning': {'literal': 'No native weighting control is selected; CPB does not infer punctuation semantics.',
                    'sdEmbeds': 'Parenthesized or bracketed emphasis, with explicit (term:weight).',
                    'compel': 'Suffix weights and independent .blend() or .and() conditioning clauses.'}[syntax],
        'examples': {'literal': ['blue eyes, long hair'],
                     'sdEmbeds': ['(blue eyes:1.2), [long hair]'],
                     'compel': ['(blue eyes)1.2, long hair+', '(long hair, blue eyes)++',
                                '("blue eyes, long hair", "green eyes, short hair").blend(1, 0.8)',
                                '("solo, blue eyes", "forest, soft lighting").and()']}[syntax],
        'scope': 'A syntax description is not evidence that every model exposes that control.',
        'embedding_execution': 'provider', 'automatic_conversion': False}
