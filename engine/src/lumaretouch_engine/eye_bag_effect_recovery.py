# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact full-source review of an existing eye-bag v2 contribution recovery.

No solver, preservation support, history owner or alternate mask space is added.
The existing source-owned face recovery bank attenuates this stage only. Both
review images use the canonical full export graph before display-only reduction.
AUTHORED / UNRUN.
"""
from copy import deepcopy
import base64
import io

TARGET = 'eye_bag_preserve'
MAX_EDGE = 800
MAX_REVIEW_BYTES = 6 * 1024 * 1024


def reject_global(value):
    if any(row['target'] == TARGET for row in value['targets']):
        raise ValueError('Eye-bag v2 recovery requires its canonical face-local immutable asset, not a global row')


def live(engine, *, _alias_admission=None):
    from . import people_recovery as PEOPLE
    from .eye_bag_preserve_host import _live
    source, graph, face, ref = PEOPLE.selection(engine, editing=True)
    target = {'scope': 'face', 'target_id': ref['face_instance_id'], 'face_ref': ref}
    if _alias_admission is not None:
        from .eye_bag_recovery_alias_review import validate_admission
        validate_admission(engine, _alias_admission, graph, ref)
    owner, row, current, proof, version = _live(engine, graph, target, strict=_alias_admission is None)
    if source['sha256'] != proof['asset_sha256']:
        raise ValueError('Eye-bag recovery source identity changed')
    return row, current, version


def _context(engine, row, transaction):
    from .full_candidate_render import people_context
    from . import people_support_assets as ASSETS
    context = people_context(engine, row)
    ASSETS.check_store(transaction['assets'])
    context['people_graph'] = deepcopy(transaction['candidate'])
    context['people_support_assets'] = deepcopy(transaction['assets'])
    return context


def _identity(engine, transaction):
    from .full_candidate_render import identity
    from .local_mask_state import file_stamp
    from .people_recovery import assert_context
    assert_context(engine, transaction['context'])
    row, current, version = live(engine)
    context = _context(engine, row, transaction)
    args = (engine, row, current, version.document_id, str(version.revision))
    before, _, _ = identity(*args, people_graph=transaction['before'])
    after, _, _ = identity(*args, people_graph=transaction['candidate'], staged_people_context=context)
    return {'before': before, 'after': after, 'path_stamp': list(file_stamp(row['path']))}, (row, current, version, context)


def _display(rgb, proof, *, _size=None):
    from PIL import Image
    import numpy as np
    width, height = proof['output_size']
    factor = min(1., MAX_EDGE / max(width, height))
    size = (max(1, round(width * factor)), max(1, round(height * factor))) if _size is None else _size
    channels = []
    for channel in range(3):
        with Image.fromarray(rgb[:, :, channel].astype(np.float32)) as plane:
            with plane.resize(size, Image.Resampling.LANCZOS) as small:
                channels.append(np.asarray(small).copy())
    # Display bytes only; no replacement source, persisted raster or RGB8 export.
    pixels = np.rint(np.clip(np.stack(channels, axis=2), 0, 1) * 255).astype(np.uint8)
    with Image.fromarray(pixels, 'RGB') as display:
        stream = io.BytesIO(); display.save(stream, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode('ascii'), size


def render(engine, transaction):
    from .full_candidate_render import render as full_render
    if transaction is None or transaction['target'] != TARGET:
        raise ValueError('Eye-bag recovery needs its exact independently owned candidate')
    frozen, (row, current, version, context) = _identity(engine, transaction)
    args = (engine, row, current, version.document_id, str(version.revision))
    before_rgb, before_proof = full_render(*args, people_graph=transaction['before'])
    before, size = _display(before_rgb, before_proof)
    del before_rgb
    after_rgb, after_proof = full_render(*args, people_graph=transaction['candidate'], staged_people_context=context)
    after, other_size = _display(after_rgb, after_proof)
    del after_rgb
    if size != other_size or before_proof['source_size'] != after_proof['source_size']:
        raise ValueError('Eye-bag recovery full-source framing changed')
    for key, rendered in (('before', before_proof), ('after', after_proof)):
        if {name: rendered[name] for name in frozen[key]} != frozen[key]:
            raise ValueError('Eye-bag recovery rendered another source, repair stack or graph')
    if _identity(engine, transaction)[0] != frozen:
        raise ValueError('Eye-bag recovery source changed during complete rendering')
    if len(before) + len(after) > MAX_REVIEW_BYTES:
        raise ValueError('Eye-bag recovery full-render display exceeds transport budget')
    review = {'identity': frozen, 'transaction': deepcopy({key: transaction[key] for key in
        ('context', 'before', 'candidate', 'assets', 'target', 'no_change')})}
    result = {'before': before, 'after': after, 'width': size[0], 'height': size[1],
        'domain': 'production-output', 'quality': 'full-source-render-srgb8',
        'note': '真实完整源图混合效果渲染后缩小显示；只恢复眼袋 v2 的贡献，不抹掉其他效果。显示为 RGB8，非原生像素验收。'}
    return result, review


def verify(engine, review, transaction=None):
    if type(review) is not dict or set(review) != {'identity', 'transaction'}:
        raise ValueError('Eye-bag recovery is missing its exact full-render proof')
    retained = review['transaction']
    if transaction is not None and any(transaction[key] != retained[key] for key in retained):
        raise ValueError('Eye-bag recovery candidate differs from the displayed full render')
    if _identity(engine, retained)[0] != review['identity']:
        raise ValueError('Eye-bag recovery full-render source, repair, support or graph changed')
