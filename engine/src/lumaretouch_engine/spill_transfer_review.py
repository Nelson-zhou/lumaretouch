"""Target-owned full before/after evidence for dedicated scalar spill transfer.

No candidate installation, live row swap or apply/undo simulation. Only compact
proofs enter histories; PNGs are display reductions of complete float renders.
"""
from copy import deepcopy
from hashlib import sha256
import base64
import io
import re

MAX_TARGETS = 8
PREVIEW_EDGE = 256
MAX_PNG_BYTES = 150000
MAX_BASE64 = 200000
FIELDS = {'version', 'document_id', 'revision', 'source_proof', 'before_sha256',
          'candidate_sha256', 'before_people_sha256', 'candidate_people_sha256',
          'source_size', 'before_output_size', 'after_output_size', 'parameters', 'before', 'after'}
IDENTITY_FIELDS = {'document_id', 'revision', 'source_proof', 'candidate_sha256', 'people_sha256'}


def _hash(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('Spill review requires a SHA-256 identity')


def _size(value):
    if type(value) is not list or len(value) != 2 or any(type(n) is not int or not 1 <= n <= 2**32-1 for n in value):
        raise ValueError('Spill review requires exact full-source/output dimensions')


def _context(document, revision):
    if type(document) is not str or not 1 <= len(document) <= 128:
        raise ValueError('Invalid spill review target identity')
    if (type(revision) is not str or re.fullmatch('(0|[1-9][0-9]{0,19})', revision) is None
            or int(revision) > 2**64-1):
        raise ValueError('Invalid spill review target revision')


def _image(value, output):
    if type(value) is not dict or set(value) != {'mime', 'width', 'height', 'sha256'} or value['mime'] != 'image/png':
        raise ValueError('Private spill proof must not retain display pixels')
    w, h = value['width'], value['height']
    if any(type(n) is not int or not 1 <= n <= PREVIEW_EDGE for n in (w, h)):
        raise ValueError('Spill display exceeds its bounded extent')
    if w > output[0] or h > output[1] or abs(w*output[1]-h*output[0]) > max(output):
        raise ValueError('Spill display does not match its completed target geometry')
    _hash(value['sha256'])


def checked(record):
    from .creative_derived_source import check_row_proof
    from .spill_removal_state import check_portable
    if type(record) is not dict or set(record) != FIELDS or type(record['version']) is not int or record['version'] != 1:
        raise ValueError('Missing exact target spill visual review')
    _context(record['document_id'], record['revision'])
    source = check_row_proof(record['source_proof'])['creative_source']
    for key in ('before_sha256', 'candidate_sha256', 'before_people_sha256', 'candidate_people_sha256'):
        _hash(record[key])
    if check_portable(record['parameters']) != record['parameters']:
        raise ValueError('Noncanonical spill review parameters')
    for key in ('source_size', 'before_output_size', 'after_output_size'): _size(record[key])
    if source is not None and [source['width'], source['height']] != record['source_size']:
        raise ValueError('Spill proof belongs to a different derived canvas')
    _image(record['before'], record['before_output_size'])
    _image(record['after'], record['after_output_size'])
    return deepcopy(record)


def rollback_record(record, before, revision):
    """Frozen expectation, never a newly observed/rebased people identity."""
    from .spill_removal_scope import params_of
    value = checked(record)
    value.update(revision=str(revision), candidate_sha256=value['before_sha256'],
                 candidate_people_sha256=value['before_people_sha256'],
                 after_output_size=value['before_output_size'][:],
                 after=deepcopy(value['before']), parameters=params_of(before))
    return checked(value)


def acknowledgments(raw, records):
    """Exact ordered image acknowledgments, not a generic approve-all boolean."""
    records = [checked(record) for record in records]
    expected = [{'document_id': r['document_id'], 'revision': r['revision'],
                 'before_sha256': r['before']['sha256'], 'after_sha256': r['after']['sha256']} for r in records]
    if (type(raw) is not list or len(raw) != len(expected) or len(raw) > MAX_TARGETS
            or len({r['document_id'] for r in records}) != len(records)):
        raise ValueError('Review every eligible target spill image pair before applying')
    for item, wanted in zip(raw, expected):
        if type(item) is not dict or set(item) != set(wanted) or item != wanted:
            raise ValueError('Spill acknowledgment does not match the frozen target image pair')
    return deepcopy(expected)


def _require_retained_people_candidate(before, candidate, graph, asset):
    """Legacy preset face overrides are installed only by replay, not this view.

    Refuse that unadapted mixed operation before displaying the wrong candidate.
    A separately committed portrait edit remains part of both full spill views.
    """
    if not any(face.get('asset_sha256') == asset for face in graph.get('faces', {}).values()):
        return
    from .optics_candidate_identity import fingerprint
    from . import facial_wrinkle_state as wrinkles
    for state in (before, candidate):
        defaults = state.get('_deform_default') or {}
        amounts = (state.get('_deform') or {}).get('amounts') or {}
        if (not any(abs(float(v)) > 0 for v in defaults.values())
                and not state.get('_deform_overrides') and any(abs(float(v)) > 0 for v in amounts.values())):
            raise ValueError('人物形变镜像仍会触发旧默认值迁移，尚不能冻结可靠祛反光重放；未显示候选或修改照片')
    fields = ('_brow_shape', '_nose_shape', '_eye_shape', '_mouth_shape', '_lip_makeup',
              '_eye_light_preset', '_face_decoration_preset', '_blush_makeup_preset', '_lipstick_preset',
              '_eyeliner_preset', '_eyelash_preset', '_brow_makeup_preset', '_iris_makeup_preset')
    changed = any(fingerprint(before.get(key)) != fingerprint(candidate.get(key)) for key in fields)
    left = wrinkles.check((before.get('_enhance') or {}).get('amounts', {}))
    right = wrinkles.check((candidate.get('_enhance') or {}).get('amounts', {}))
    if changed or left != right:
        raise ValueError('受管理人物参数与祛反光的混合预设尚无候选人物图审核；请先单独应用人物参数，再逐图审核祛反光，不会显示旧人物图冒充候选')


def _require_stable_live_people(engine, row, graph, asset):
    """Do not let spill publication become the first people migration/binding.

    Read only; _people_bind itself is intentionally never called by preflight.
    Parked rows are not activated here. Unexpected external drift is detected,
    not overwritten under the guise of rolling back an unrelated spill edit.
    """
    from .virtual_copy_people import current_row
    if current_row(engine) is not row or getattr(engine, '_vram', None) is None:
        return
    pc = getattr(engine, '_precompute', None)
    owner = engine.__dict__.get('_people_graph_owner')
    if pc is not None:
        if owner is None or engine.__dict__.get('_people_analysis_key') != (asset, id(pc), owner.fence):
            raise ValueError('当前人物分析尚未稳定绑定；请完成打开/分析后重新审核祛反光，不会在应用阶段迁移人物数据')
    elif owner is not None and not any(item.get('legacy_key') == '_migration_complete'
            and item.get('asset_sha256') == asset for item in graph.get('unresolved_legacy', [])):
        raise ValueError('当前人物历史尚未完成来源迁移；请先完成打开流程，再审核祛反光')


def _identities(engine, row, before, candidate, document, revision):
    from .full_candidate_render import identity
    _context(document, revision)
    left, graph, _ = identity(engine, row, before, document, revision)
    _require_stable_live_people(engine, row, graph, left['source_proof']['asset_sha256'])
    _require_retained_people_candidate(before, candidate, graph, left['source_proof']['asset_sha256'])
    right, _, _ = identity(engine, row, candidate, document, revision)
    if set(left) != IDENTITY_FIELDS or set(right) != IDENTITY_FIELDS:
        raise ValueError('Incomplete full-target spill identities')
    if any(left[k] != right[k] for k in ('document_id', 'revision', 'source_proof')):
        raise ValueError('Spill views must share one immutable target source')
    return left, right


def _geometry(row, state, proof):
    from .ops.geometry import out_size
    source = proof['creative_source']
    size = [source['width'], source['height']] if source is not None else [row.get('src_w'), row.get('src_h')]
    _size(size)
    output = list(out_size(*size, state['_crop_rect'], state['_crop_rotation']))
    _size(output)
    return size, output


def verify(engine, row, before, candidate, document, revision, record):
    from .spill_removal_scope import params_of
    record = checked(record)
    left, right = _identities(engine, row, before, candidate, document, revision)
    actual = {'document_id': document, 'revision': revision, 'source_proof': left['source_proof'],
              'before_sha256': left['candidate_sha256'], 'candidate_sha256': right['candidate_sha256'],
              'before_people_sha256': left['people_sha256'], 'candidate_people_sha256': right['people_sha256'],
              'parameters': params_of(candidate)}
    if any(record[k] != value for k, value in actual.items()):
        raise ValueError('Spill target source, edits, people or parameters changed after review')
    source, prior_size = _geometry(row, before, left['source_proof'])
    other, after_size = _geometry(row, candidate, right['source_proof'])
    if source != other or record['source_size'] != source or record['before_output_size'] != prior_size or record['after_output_size'] != after_size:
        raise ValueError('Spill target geometry changed after review')
    return record


def _view(engine, row, state, document, revision, expected):
    from .full_candidate_render import render
    from PIL import Image
    import numpy as np
    rgb, proof = render(engine, row, state, document, revision)
    source, output = _geometry(row, state, expected['source_proof'])
    if (type(proof) is not dict or set(proof) != IDENTITY_FIELDS | {'source_size', 'output_size'}
            or any(proof.get(k) != v for k, v in expected.items())
            or proof['source_size'] != source or proof['output_size'] != output
            or not isinstance(rgb, np.ndarray) or rgb.shape != (output[1], output[0], 3)
            or not np.issubdtype(rgb.dtype, np.floating) or not np.isfinite(rgb).all()):
        raise ValueError('Spill view requires the actual complete finite target render')
    scale = min(1., PREVIEW_EDGE / max(output))
    size = tuple(max(1, round(n*scale)) for n in output)
    channels = []
    for channel in range(3):
        with Image.fromarray(rgb[:, :, channel].astype(np.float32)) as plane:
            with plane.resize(size, Image.Resampling.LANCZOS) as small:
                channels.append(np.asarray(small).copy())
    # This clipping/quantization is presentation only, after full-source edits.
    display = Image.fromarray(np.rint(np.clip(np.stack(channels, axis=2), 0, 1)*255).astype(np.uint8), 'RGB')
    try:
        while True:
            stream = io.BytesIO(); display.save(stream, format='PNG'); raw = stream.getvalue()
            if len(raw) <= MAX_PNG_BYTES: break
            edge = max(display.size) - 16
            if edge < 1: raise ValueError('Spill display exceeds transport budget; no target omitted')
            scale = min(1., edge/max(output))
            smaller = display.resize(tuple(max(1, round(n*scale)) for n in output), Image.Resampling.LANCZOS)
            display.close(); display = smaller
        size = display.size
    finally:
        display.close()
    compact = {'mime': 'image/png', 'width': size[0], 'height': size[1], 'sha256': sha256(raw).hexdigest()}
    return compact, {**compact, 'base64': base64.b64encode(raw).decode('ascii')}, source, output


def prepare(engine, row, before, candidate, document, revision):
    from .spill_removal_scope import params_of
    left, right = _identities(engine, row, before, candidate, document, revision)
    a, public_a, source, size_a = _view(engine, row, before, document, revision, left)
    b, public_b, other, size_b = _view(engine, row, candidate, document, revision, right)
    if source != other: raise ValueError('Spill target source changed between views')
    record = checked({'version': 1, 'document_id': document, 'revision': revision,
        'source_proof': left['source_proof'], 'before_sha256': left['candidate_sha256'],
        'candidate_sha256': right['candidate_sha256'], 'before_people_sha256': left['people_sha256'],
        'candidate_people_sha256': right['people_sha256'], 'source_size': source,
        'before_output_size': size_a, 'after_output_size': size_b, 'parameters': params_of(candidate),
        'before': a, 'after': b})
    verify(engine, row, before, candidate, document, revision, record)
    return record, {**deepcopy(record), 'before': public_a, 'after': public_b}
