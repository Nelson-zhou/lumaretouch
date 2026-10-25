# SPDX-License-Identifier: GPL-3.0-or-later
"""Display-only complete crop review and immutable candidate proof.

Full canonical rendering precedes every display reduction. This does not own a
sampler, recipe, source overwrite, history stack, or export pipeline.
AUTHORED / UNRUN, including real image, detector and integration acceptance.
"""
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import base64
import io
import uuid

PREVIEW_EDGE = 1400
MAX_PNG_BYTES = 8 * 1024 * 1024


def poll(cancelled):
    if cancelled():
        raise InterruptedError('Portrait crop source or review is stale/cancelled')


def raster_hash(rgb):
    from .optics_candidate_identity import fingerprint
    return fingerprint(rgb)


def display_rgb(rgb, *, cancelled=lambda: False):
    """A whole-frame projection, never an input to the canonical crop sampler."""
    import numpy as np
    from PIL import Image
    if type(rgb) is not np.ndarray or rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype.kind != 'f':
        raise ValueError('Portrait crop requires genuine complete float RGB output')
    h, w = rgb.shape[:2]
    if w < 1 or h < 1:
        raise ValueError('Portrait crop source has no complete raster')
    scale = min(1., PREVIEW_EDGE / max(w, h))
    size = max(1, round(w * scale)), max(1, round(h * scale))
    channels = []
    for channel in range(3):
        poll(cancelled)
        # Float-to-RGB8 clipping is display/inference only, never source state.
        with Image.fromarray(rgb[:, :, channel].astype(np.float32)) as plane:
            with plane.resize(size, Image.Resampling.LANCZOS) as small:
                channels.append(np.asarray(small).copy())
    proxy = np.rint(np.clip(np.stack(channels, axis=2), 0, 1) * 255).astype(np.uint8)
    proxy = np.ascontiguousarray(proxy)
    proxy.setflags(write=False)
    poll(cancelled)
    return proxy


def encode_image(proxy, source_size, *, cancelled=lambda: False):
    from PIL import Image
    poll(cancelled)
    with Image.fromarray(proxy, 'RGB') as display:
        stream = io.BytesIO()
        display.save(stream, format='PNG')
        raw = stream.getvalue()
    if len(raw) > MAX_PNG_BYTES:
        raise ValueError('Portrait crop full image exceeds bounded review transport')
    poll(cancelled)
    return {'mime': 'image/png', 'width': int(proxy.shape[1]), 'height': int(proxy.shape[0]),
            'sha256': sha256(raw).hexdigest(), 'base64': base64.b64encode(raw).decode('ascii'),
            'source_width': source_size[0], 'source_height': source_size[1],
            'mapping': 'normalized_full_frame'}


def image(engine, row, state, document_id, revision, *, cancelled=lambda: False):
    from .full_candidate_render import render
    rgb, proof = render(engine, row, state, document_id, revision, cancelled=cancelled)
    full_sha = raster_hash(rgb)
    proxy = display_rgb(rgb, cancelled=cancelled)
    shown = encode_image(proxy, proof['output_size'], cancelled=cancelled)
    return shown, {**proof, 'raster_sha256': full_sha, 'image_sha256': shown['sha256']}


@dataclass(frozen=True)
class Candidate:
    state: dict
    proof: dict
    preview: dict


def prepare(engine, capture, request, *, cancelled=lambda: False):
    from .portrait_crop_planner import plan
    from .portrait_crop_project import non_crop_hash, compact_proof
    from .optics_candidate_identity import fingerprint
    from .scope import OP_CROP, check_params
    from .ops.geometry import out_size, _cut
    capture.verify(engine, cancelled=cancelled)
    if request['capture_sha256'] != capture.capture_sha256:
        raise ValueError('Portrait crop source capture changed after anchor review')
    face = next((row for row in capture.source['faces'] if row['face_id'] == request['face_id']), None)
    if face is None:
        raise ValueError('Select a face actually measured on this complete edited source')
    review = request['anchor_review']
    if (type(review) is not dict or set(review) != {'image_sha256', 'crown_confirmed', 'chin_confirmed', 'center_confirmed'}
            or review['image_sha256'] != capture.source['image']['sha256']
            or any(review[key] is not True for key in ('crown_confirmed', 'chin_confirmed', 'center_confirmed'))):
        raise ValueError('Mark and confirm the real crown, chin and face center on the captured photograph')
    # Crown is user-supplied, never landmark 10, a face box or a hair-segmentation guess.
    result = plan(capture.source['width'], capture.source['height'], request['anchors'], request['rules'])
    if (result['source_size'] != [capture.source['width'], capture.source['height']]
            or result['operation_id'] != OP_CROP or result['rotation_degrees'] != 0):
        raise ValueError('Portrait crop planner changed the canonical source grid or rotation')
    parameters = check_params(OP_CROP, {'rect_normalized': result['rect_normalized'], 'rotation_degrees': 0.})
    state = dict(capture.state)
    state['_crop_rect'] = tuple(parameters['rect_normalized'])
    # Preserve the exact existing value, including signed zero. Never reset a rotation.
    state['_crop_rotation'] = capture.state['_crop_rotation']
    if non_crop_hash(state) != capture.binding['non_crop_sha256']:
        raise ValueError('Portrait crop candidate changed an unrelated edit')
    w, h = result['source_size']
    left, right = _cut(w, *parameters['rect_normalized'][::2])
    top, bottom = _cut(h, *parameters['rect_normalized'][1::2])
    if ([left, top, right, bottom] != result['pixel_bounds']
            or list(out_size(w, h, state['_crop_rect'], state['_crop_rotation'])) != result['output_size']):
        raise ValueError('Portrait crop solver and unchanged canonical sampler disagree')
    after, after_proof = image(engine, capture.row, state, capture.binding['document_id'],
                               capture.binding['revision'], cancelled=cancelled)
    if after_proof['source_size'] != result['source_size'] or after_proof['output_size'] != result['output_size']:
        raise ValueError('Complete portrait crop candidate differs from reviewed full source extent')
    capture.verify(engine, cancelled=cancelled)
    proof = compact_proof(capture, state, result, request, after_proof)
    preview = {'preview_token': uuid.uuid4().hex, 'capture_sha256': capture.capture_sha256,
               'candidate_sha256': fingerprint(state), 'preview_request_id': request['request_id'],
               'plan': deepcopy(result), 'before': deepcopy(capture.before), 'after': after}
    return Candidate(state, proof, preview)
