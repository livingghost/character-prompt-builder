#!/usr/bin/env python3
"""Decode actual production artifacts and validate explicit observation ranges.

Media recognition is not a finding about aesthetics or physical plausibility.
No OCR, automatic emotion score, black-frame fault rule or model call is used.
"""
from __future__ import annotations

import io
import json
import math
from decimal import Decimal, InvalidOperation
from pathlib import Path
import subprocess
import tempfile
from typing import Any
import execution_contract as c
from io_budget import environment_seconds

KINDS = {'text', 'json', 'image', 'video', 'audio', 'binary'}


def seconds(value: Any) -> Decimal:
    if not isinstance(value, str):
        raise ValueError('time is a finite decimal string in seconds')
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('invalid time') from exc
    if not result.is_finite() or result < 0:
        raise ValueError('time must be finite and nonnegative')
    return result


def inspect(raw: bytes, kind: str) -> dict:
    if kind not in KINDS:
        raise ValueError('unknown artifact medium')
    if not raw:
        raise ValueError('empty artifact')
    result = {'kind': kind, 'bytes': len(raw)}
    if kind in {'text', 'json'}:
        text = raw.decode('utf-8')
        if kind == 'json':
            c.decode(raw)
        result['lines'] = len(text.splitlines())
    elif kind == 'image':
        try:
            from PIL import Image
            with Image.open(io.BytesIO(raw)) as im:
                im.verify()
            with Image.open(io.BytesIO(raw)) as im:
                im.load()
                result.update(width=im.width, height=im.height, format=im.format,
                              frames=getattr(im, 'n_frames', 1))
        except ImportError as exc:
            raise ValueError('image observation requires the declared Pillow dependency') from exc
        except (OSError, ValueError) as exc:
            raise ValueError('candidate does not decode as an actual image') from exc
    elif kind in {'video', 'audio'}:
        # Probe the pinned bytes, never an arbitrary URL or user-provided command.
        with tempfile.TemporaryDirectory(prefix='production-probe-') as temporary:
            path = Path(temporary) / 'artifact'
            path.write_bytes(raw)
            try:
                completed = subprocess.run(
                    ['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe',
                     '-show_streams', '-show_format', '-of', 'json', str(path)],
                    capture_output=True, timeout=environment_seconds('MEDIA_PROBE_TIMEOUT_SECONDS'), check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ValueError('temporal observation requires a working ffprobe') from exc
        if completed.returncode:
            raise ValueError('candidate does not probe as actual temporal media')
        try:
            info = json.loads(completed.stdout)
        except (ValueError, UnicodeError) as exc:
            raise ValueError('invalid media probe result') from exc
        streams = []
        for stream in info.get('streams', []):
            medium = stream.get('codec_type')
            if medium not in {'audio', 'video'}:
                continue
            duration = stream.get('duration')
            if duration is None and stream.get('duration_ts') is not None and stream.get('time_base'):
                from fractions import Fraction
                duration = str(float(int(stream['duration_ts']) * Fraction(stream['time_base'])))
            # A container's overall duration can exceed an individual stream.
            # Do not substitute it and silently permit unobserved stream ranges.
            if duration is None or seconds(str(duration)) <= 0:
                continue
            streams.append({'index': stream['index'], 'kind': medium,
                            'duration_seconds': str(duration),
                            'width': stream.get('width'), 'height': stream.get('height'),
                            'frame_rate': stream.get('avg_frame_rate')})
        if not any(x['kind'] == kind for x in streams):
            raise ValueError('required media stream has no measured positive duration')
        result['streams'] = streams
    return result


def locator(value: Any, media: dict, raw: bytes) -> set[str]:
    if not isinstance(value, dict):
        raise ValueError('observation locator must be an object')
    kind = value.get('kind')
    supported = {'artifact'}
    if kind == 'whole':
        c.exact(value, {'kind'}, 'whole locator')
    elif kind == 'description':
        c.exact(value, {'kind', 'text'}, 'description locator')
        c.text(value['text'], 'observation location')
    elif kind in {'lines', 'bytes'}:
        c.exact(value, {'kind', 'start', 'end'}, 'range locator')
        limit = len(raw) if kind == 'bytes' else len(raw.decode('utf-8').splitlines())
        if type(value['start']) is not int or type(value['end']) is not int or not 1 <= value['start'] <= value['end'] <= limit:
            raise ValueError('observation range exceeds the artifact')
        if kind == 'lines':
            supported.add('text')
    elif kind == 'image-region':
        c.exact(value, {'kind', 'x', 'y', 'width', 'height'}, 'image region')
        if media['kind'] != 'image':
            raise ValueError('image region requires an actual decoded image')
        for key in ('x', 'y', 'width', 'height'):
            number = value[key]
            if type(number) not in {int, float} or not math.isfinite(number) or not 0 <= number <= 1:
                raise ValueError('image region uses finite normalized coordinates')
        if value['width'] <= 0 or value['height'] <= 0 or value['x'] + value['width'] > 1 or value['y'] + value['height'] > 1:
            raise ValueError('image region is outside the image')
        supported.add('image')
    elif kind == 'time':
        c.exact(value, {'kind', 'stream', 'start_seconds', 'end_seconds'}, 'time range')
        streams = [s for s in media.get('streams', []) if s['index'] == value['stream'] and type(value['stream']) is int]
        if len(streams) != 1:
            raise ValueError('time range must identify an actual stream index')
        stream = streams[0]
        start, end = seconds(value['start_seconds']), seconds(value['end_seconds'])
        if not 0 <= start < end <= seconds(stream['duration_seconds']):
            raise ValueError('time range exceeds the measured stream')
        if stream['kind'] == 'video':
            from fractions import Fraction
            rate = stream.get('frame_rate')
            if not rate or Fraction(rate) <= 0 or float(end - start) * float(Fraction(rate)) < 1:
                raise ValueError('motion evidence requires an interval spanning distinct frames')
            supported.add('motion')
        else:
            supported.add('audio')
    else:
        raise ValueError('unknown observation locator')
    if kind in {'whole', 'description'}:
        if media['kind'] in {'text', 'json'}:
            supported.add('text')
        if media['kind'] == 'image':
            supported.add('image')
    return supported
