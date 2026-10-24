# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual target-owned people-transfer image evidence. Source-authored / UNRUN.

The complete owner aggregate is rendered, not an isolated face approximation.
Only display PNGs are reduced/quantized; source recipes and histories stay float.
"""
from copy import deepcopy
from hashlib import sha256
import base64
import io
import json
import re

MAX_TARGETS = 16
PREVIEW_EDGE = 1024
MAX_PNG_BYTES = 4 * 1024 * 1024
MAX_BASE64 = 5592408
MAX_TOTAL_BASE64 = 192 * 1024 * 1024  # transient preparation ceiling; session raw store has its own bound
FIELDS = {'version', 'document_id', 'revision', 'source_proof', 'before_state_sha256',
          'candidate_state_sha256', 'before_people_sha256', 'candidate_people_sha256',
          'source_size', 'before_output_size', 'after_output_size', 'coverage_sha256', 'before', 'after'}


def coverage_digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                             allow_nan=False).encode('utf-8')).hexdigest()


def _hash(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('Collarbone visual evidence requires exact SHA-256 identities')


def _size(value):
    if type(value) is not list or len(value) != 2 or any(type(x) is not int or not 1 <= x <= 2**32-1 for x in value):
        raise ValueError('Collarbone visual evidence requires exact full dimensions')


def preview_size(output):
    """Exact integer ties-even dimensions, shared with Rust/TypeScript."""
    _size(output)
    edge = max(output)
    if edge <= PREVIEW_EDGE: return tuple(output)
    def extent(value):
        quotient, remainder = divmod(value * PREVIEW_EDGE, edge)
        increment = remainder * 2 > edge or (remainder * 2 == edge and quotient % 2 == 1)
        return max(1, quotient + int(increment))
    return tuple(extent(value) for value in output)


def checked(record):
    from .creative_derived_source import check_row_proof
    if type(record) is not dict or set(record) != FIELDS or type(record['version']) is not int or record['version'] != 1:
        raise ValueError('Missing exact collarbone target visual evidence')
    if type(record['document_id']) is not str or not 1 <= len(record['document_id']) <= 128:
        raise ValueError('Invalid collarbone target document')
    revision = record['revision']
    if type(revision) is not str or re.fullmatch('(0|[1-9][0-9]{0,19})', revision) is None or int(revision) > 2**64-1:
        raise ValueError('Invalid collarbone target revision')
    proof = check_row_proof(record['source_proof'])
    for key in ('before_state_sha256', 'candidate_state_sha256', 'before_people_sha256', 'candidate_people_sha256', 'coverage_sha256'):
        _hash(record[key])
    for key in ('source_size', 'before_output_size', 'after_output_size'): _size(record[key])
    if proof['creative_source'] is not None and [proof['creative_source']['width'], proof['creative_source']['height']] != record['source_size']:
        raise ValueError('Collarbone review has a different derived canvas')
    for key, output_key in (('before', 'before_output_size'), ('after', 'after_output_size')):
        image = record[key]; output = record[output_key]
        if type(image) is not dict or set(image) != {'mime', 'width', 'height', 'sha256'} or image['mime'] != 'image/png':
            raise ValueError('Frozen collarbone evidence must not retain display pixels')
        w, h = image['width'], image['height']
        if any(type(x) is not int or not 1 <= x <= PREVIEW_EDGE for x in (w, h)):
            raise ValueError('Collarbone display exceeds bounded dimensions')
        if (w, h) != preview_size(output):
            raise ValueError('Collarbone display cannot silently reduce review detail')
        _hash(image['sha256'])
    return deepcopy(record)


def acknowledgments(raw, records):
    records = [checked(item) for item in records]
    expected = [{'document_id': r['document_id'], 'revision': r['revision'],
                 'before_sha256': r['before']['sha256'], 'after_sha256': r['after']['sha256'],
                 'coverage_sha256': r['coverage_sha256']} for r in records]
    if (type(raw) is not list or len(raw) != len(expected) or len(raw) > MAX_TARGETS
            or len({r['document_id'] for r in records}) != len(records)):
        raise ValueError('Review and acknowledge every eligible collarbone target image pair')
    for item, wanted in zip(raw, expected):
        if type(item) is not dict or set(item) != set(wanted) or item != wanted:
            raise ValueError('Collarbone acknowledgment differs from the frozen target images or coverage')
    return deepcopy(expected)


def _identities(engine, row, before, candidate, document, revision):
    from .full_candidate_render import identity
    left, _, _ = identity(engine, row, row['state'], document, revision, people_graph=before)
    right, _, _ = identity(engine, row, row['state'], document, revision, people_graph=candidate)
    if any(left[key] != right[key] for key in ('document_id', 'revision', 'source_proof', 'candidate_sha256')):
        raise ValueError('Collarbone transfer changed target source or unrelated document state')
    return left, right


def _geometry(row, proof):
    from .ops.geometry import out_size
    source = proof['creative_source']
    size = [source['width'], source['height']] if source is not None else [row.get('src_w'), row.get('src_h')]
    _size(size)
    output = list(out_size(*size, row['state']['_crop_rect'], row['state']['_crop_rotation']))
    _size(output)
    return size, output


def verify(engine, row, before, candidate, document, revision, coverage, record):
    record = checked(record)
    left, right = _identities(engine, row, before, candidate, document, revision)
    source, output = _geometry(row, left['source_proof'])
    actual = {'document_id': document, 'revision': revision, 'source_proof': left['source_proof'],
              'before_state_sha256': left['candidate_sha256'], 'candidate_state_sha256': right['candidate_sha256'],
              'before_people_sha256': left['people_sha256'], 'candidate_people_sha256': right['people_sha256'],
              'coverage_sha256': coverage_digest(coverage), 'source_size': source,
              'before_output_size': output, 'after_output_size': output}
    if any(record[key] != value for key, value in actual.items()):
        raise ValueError('Collarbone target source, complete owner candidate, coverage or edits changed; review again')
    return record


def _view(engine, row, graph, document, revision, expected):
    from .full_candidate_render import render
    from PIL import Image
    import numpy as np
    rgb, proof = render(engine, row, row['state'], document, revision, people_graph=graph)
    source, output = _geometry(row, expected['source_proof'])
    if (type(proof) is not dict or set(proof) != set(expected) | {'source_size', 'output_size'}
            or any(proof.get(key) != value for key, value in expected.items())
            or proof['source_size'] != source or proof['output_size'] != output
            or not isinstance(rgb, np.ndarray) or rgb.shape != (output[1], output[0], 3)
            or not np.issubdtype(rgb.dtype, np.floating) or not np.isfinite(rgb).all()):
        raise ValueError('Collarbone review requires the actual complete finite target render')
    size = preview_size(output)
    channels = []
    for channel in range(3):
        with Image.fromarray(rgb[:, :, channel].astype(np.float32)) as plane:
            with plane.resize(size, Image.Resampling.LANCZOS) as small:
                channels.append(np.asarray(small).copy())
    # Presentation-only quantization, never source conversion or export pixels.
    with Image.fromarray(np.rint(np.clip(np.stack(channels, axis=2), 0, 1) * 255).astype(np.uint8), 'RGB') as display:
        stream = io.BytesIO(); display.save(stream, format='PNG'); raw = stream.getvalue()
    if len(raw) > MAX_PNG_BYTES:
        raise ValueError('Collarbone visual PNG exceeds review transport budget; no lower-detail substitute')
    compact = {'mime': 'image/png', 'width': size[0], 'height': size[1], 'sha256': sha256(raw).hexdigest()}
    return compact, {**compact, 'base64': base64.b64encode(raw).decode('ascii')}, source, output


def prepare(engine, row, before, candidate, document, revision, coverage):
    left, right = _identities(engine, row, before, candidate, document, revision)
    a, public_a, source, output_a = _view(engine, row, before, document, revision, left)
    b, public_b, other, output_b = _view(engine, row, candidate, document, revision, right)
    if source != other: raise ValueError('Collarbone source changed between complete views')
    record = checked({'version': 1, 'document_id': document, 'revision': revision,
        'source_proof': left['source_proof'], 'before_state_sha256': left['candidate_sha256'],
        'candidate_state_sha256': right['candidate_sha256'], 'before_people_sha256': left['people_sha256'],
        'candidate_people_sha256': right['people_sha256'], 'source_size': source,
        'before_output_size': output_a, 'after_output_size': output_b,
        'coverage_sha256': coverage_digest(coverage), 'before': a, 'after': b})
    verify(engine, row, before, candidate, document, revision, coverage, record)
    return record, {**deepcopy(record), 'before': public_a, 'after': public_b}
