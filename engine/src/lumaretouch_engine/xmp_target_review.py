"""Frozen XMP before/after review of the actual complete edited target.

This owner does not parse XMP, choose mappings, install recipes, or touch history.
Both views use full_candidate_render, including its original/derived source and
portrait ownership checks. Only completed float output is quantized for display.
Private review records retain compact evidence, never display pixels or analysis.
"""
from copy import deepcopy
import base64
import hashlib
import io
import re


PREVIEW_EDGE = 640
MAX_PNG_BYTES = 1024 * 1024
MAX_BASE64 = ((MAX_PNG_BYTES + 2) // 3) * 4
FIELDS = {
    'version', 'document_id', 'revision', 'xmp_sha256', 'source_proof',
    'before_sha256', 'candidate_sha256', 'before_people_sha256',
    'candidate_people_sha256', 'source_size', 'before_output_size',
    'after_output_size', 'before', 'after',
}
IMAGE_FIELDS = {'mime', 'width', 'height', 'sha256'}
IDENTITY_FIELDS = {
    'document_id', 'revision', 'source_proof', 'candidate_sha256', 'people_sha256',
}


def _hash(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('XMP review requires a lowercase SHA-256 identity')
    return value


def _context(document_id, revision, xmp_sha256):
    if type(document_id) is not str or not 1 <= len(document_id) <= 128:
        raise ValueError('XMP review document identity is invalid')
    if (type(revision) is not str or re.fullmatch('[0-9]{1,20}', revision) is None
            or str(int(revision)) != revision or int(revision) > 2**64 - 1):
        raise ValueError('XMP review document revision is invalid')
    _hash(xmp_sha256)


def _size(value):
    if (type(value) is not list or len(value) != 2
            or any(type(v) is not int or not 1 <= v <= 2**32 - 1 for v in value)):
        raise ValueError('XMP review requires exact positive source/output dimensions')
    return value


def _image(value, output_size):
    if type(value) is not dict or set(value) != IMAGE_FIELDS or value['mime'] != 'image/png':
        raise ValueError('Private XMP review must retain compact PNG evidence only')
    if any(type(value[k]) is not int or not 1 <= value[k] <= PREVIEW_EDGE for k in ('width', 'height')):
        raise ValueError('XMP preview exceeds its display extent')
    width, height = value['width'], value['height']
    if (width > output_size[0] or height > output_size[1]
            or abs(width * output_size[1] - height * output_size[0]) > max(output_size)):
        raise ValueError('XMP preview dimensions do not match the completed target')
    _hash(value['sha256'])


def checked(record):
    """Validate private JSON evidence. Public image bytes cannot enter history."""
    from .creative_derived_source import check_row_proof
    if (type(record) is not dict or set(record) != FIELDS
            or type(record['version']) is not int or record['version'] != 1):
        raise ValueError('XMP target review is incomplete or has an unsupported version')
    _context(record['document_id'], record['revision'], record['xmp_sha256'])
    source = check_row_proof(record['source_proof'])['creative_source']
    for key in ('before_sha256', 'candidate_sha256', 'before_people_sha256', 'candidate_people_sha256'):
        _hash(record[key])
    _size(record['source_size'])
    _size(record['before_output_size'])
    _size(record['after_output_size'])
    if source is not None and [source['width'], source['height']] != record['source_size']:
        raise ValueError('XMP review belongs to another creative source extent')
    _image(record['before'], record['before_output_size'])
    _image(record['after'], record['after_output_size'])
    return deepcopy(record)


def _identities(engine, row, before, candidate, document_id, revision):
    from .full_candidate_render import identity
    prior, _, _ = identity(engine, row, before, document_id, revision)
    proposed, _, _ = identity(engine, row, candidate, document_id, revision)
    if set(prior) != IDENTITY_FIELDS or set(proposed) != IDENTITY_FIELDS:
        raise ValueError('Full target renderer did not provide complete XMP review identities')
    for key in ('document_id', 'revision', 'source_proof'):
        if prior[key] != proposed[key]:
            raise ValueError('XMP before/after views do not belong to one frozen target')
    if prior['document_id'] != document_id or prior['revision'] != revision:
        raise ValueError('XMP review target changed during identity capture')
    return prior, proposed


def _geometry(row, state, source_proof):
    from .ops.geometry import out_size
    creative = source_proof['creative_source']
    source = ([creative['width'], creative['height']] if creative is not None
              else [row.get('src_w'), row.get('src_h')])
    _size(source)
    # These are the same canonical state fields consumed by the full exporter.
    output = list(out_size(*source, state['_crop_rect'], state['_crop_rotation']))
    _size(output)
    return source, output


def verify(engine, row, before, candidate, document_id, revision, xmp_sha256, record):
    """Recheck both full recipe identities and exact effective source ownership.

    No render, source swap, recipe install or history mutation occurs here. The
    caller also binds its mapping/report identity and owns the commit transaction.
    """
    record = checked(record)
    _context(document_id, revision, xmp_sha256)
    if any(record[key] != value for key, value in (
            ('document_id', document_id), ('revision', revision), ('xmp_sha256', xmp_sha256))):
        raise ValueError('XMP file, target document or revision differs from the review')
    prior, proposed = _identities(engine, row, before, candidate, document_id, revision)
    actual = {
        'source_proof': prior['source_proof'],
        'before_sha256': prior['candidate_sha256'],
        'candidate_sha256': proposed['candidate_sha256'],
        'before_people_sha256': prior['people_sha256'],
        'candidate_people_sha256': proposed['people_sha256'],
    }
    if any(record[key] != value for key, value in actual.items()):
        raise ValueError('XMP target source, prior edits, proposed edits or people ownership changed')
    source, before_output = _geometry(row, before, prior['source_proof'])
    proposed_source, after_output = _geometry(row, candidate, proposed['source_proof'])
    if (source != proposed_source or record['source_size'] != source
            or record['before_output_size'] != before_output or record['after_output_size'] != after_output):
        raise ValueError('XMP target source or completed output extent changed after review')
    return record


def _display(rgb, output_size):
    """Quantization is display-only; never modifies the canonical float result."""
    import numpy as np
    from PIL import Image
    if (not isinstance(rgb, np.ndarray) or rgb.ndim != 3 or rgb.shape[2] != 3
            or [rgb.shape[1], rgb.shape[0]] != output_size
            or not np.issubdtype(rgb.dtype, np.floating) or not np.isfinite(rgb).all()):
        raise ValueError('XMP preview requires the actual finite full-output float RGB image')
    display = Image.fromarray(np.rint(np.clip(rgb, 0., 1.) * 255.).astype(np.uint8), 'RGB')
    try:
        display.thumbnail((PREVIEW_EDGE, PREVIEW_EDGE), Image.Resampling.LANCZOS)
        while True:
            stream = io.BytesIO()
            display.save(stream, format='PNG')
            raw = stream.getvalue()
            if len(raw) <= MAX_PNG_BYTES:
                break
            # Reduce only the already rendered display image, never the source or
            # canonical render resolution. The longest dimension strictly drops.
            edge = max(display.size) - 32
            if edge < 1:
                raise ValueError('XMP preview exceeds its bounded PNG transport')
            scale = min(edge / output_size[0], edge / output_size[1], 1.)
            smaller = display.resize((max(1, round(output_size[0] * scale)),
                                      max(1, round(output_size[1] * scale))), Image.Resampling.LANCZOS)
            display.close()
            display = smaller
        compact = {'mime': 'image/png', 'width': display.width, 'height': display.height,
                   'sha256': hashlib.sha256(raw).hexdigest()}
        return compact, {**compact, 'base64': base64.b64encode(raw).decode('ascii')}
    finally:
        display.close()


def _render_view(engine, row, state, document_id, revision, expected):
    from .full_candidate_render import render
    rgb, proof = render(engine, row, state, document_id, revision)
    if (type(proof) is not dict or set(proof) != IDENTITY_FIELDS | {'source_size', 'output_size'}
            or any(proof[key] != value for key, value in expected.items())):
        raise ValueError('XMP target changed between identity capture and full rendering')
    source, output = _geometry(row, state, expected['source_proof'])
    if proof['source_size'] != source or proof['output_size'] != output:
        raise ValueError('Full XMP render did not preserve the exact target dimensions')
    compact, public = _display(rgb, output)
    # Each full float result is released before rendering the second view.
    return compact, public, source, output


def prepare(engine, row, before, candidate, document_id, revision, xmp_sha256):
    """Render before and candidate independently; return (private, public).

    Both arguments must be this target's states. No source analysis is borrowed,
    no candidate is installed, and no apply/undo simulation is used for preview.
    The owner must keep the private record and require its exact one-use review.
    """
    _context(document_id, revision, xmp_sha256)
    prior, proposed = _identities(engine, row, before, candidate, document_id, revision)
    before_image, before_public, source, before_output = _render_view(
        engine, row, before, document_id, revision, prior)
    after_image, after_public, after_source, after_output = _render_view(
        engine, row, candidate, document_id, revision, proposed)
    if source != after_source:
        raise ValueError('XMP before/after rendering changed the effective source extent')
    private = checked({
        'version': 1, 'document_id': document_id, 'revision': revision,
        'xmp_sha256': xmp_sha256, 'source_proof': prior['source_proof'],
        'before_sha256': prior['candidate_sha256'], 'candidate_sha256': proposed['candidate_sha256'],
        'before_people_sha256': prior['people_sha256'], 'candidate_people_sha256': proposed['people_sha256'],
        'source_size': source, 'before_output_size': before_output, 'after_output_size': after_output,
        'before': before_image, 'after': after_image,
    })
    # Recheck both inputs after both complete renders, including any edits made
    # while the other view was preparing. Read-only preparation has no fence bump.
    verify(engine, row, before, candidate, document_id, revision, xmp_sha256, private)
    public = deepcopy(private)
    public['before'] = before_public
    public['after'] = after_public
    return private, public
