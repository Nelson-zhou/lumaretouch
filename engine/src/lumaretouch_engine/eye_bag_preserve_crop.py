# SPDX-License-Identifier: GPL-3.0-or-later
"""Native spatial eye inspection, not a proxy, segmentation or export input.

AUTHORED / UNRUN. Only display encoding quantizes to RGB8. Full decode, ICC and
repair replay remain the existing canonical paths. No resize is permitted.
"""
from copy import deepcopy
from hashlib import sha256
import base64
import io
import math

MAX_EDGE = 2048
MAX_CROP_PIXELS = 4_000_000
MAX_SOURCE_PIXELS = 32_000_000
MAX_PNG_BYTES = 4 * 1024**2
MAX_TOTAL_PNG_BYTES = 8 * 1024**2


def _poll(cancelled):
    if cancelled is not None and not callable(cancelled):
        raise TypeError('cancelled must be callable')
    if cancelled is not None and cancelled():
        raise InterruptedError('Native eye source inspection cancelled')


def rectangles(face, analysis, source):
    """Tight real eye/lower-lid rectangles; not the solver's wide halo ROI."""
    import numpy as np
    from .people_render_runtime import verify_analysis
    from .third_party.rapidretouch import under_eye as E
    if (type(analysis) is not dict or type(analysis.get('skin')) is not np.ndarray
            or analysis['skin'].ndim != 2):
        raise ValueError('Native eye crop requires actual retained face semantic support')
    shape = analysis['skin'].shape
    lm = verify_analysis(face, analysis, shape)
    if (face['evidence']['source_width'], face['evidence']['source_height']) != (source['width'], source['height']):
        raise ValueError('Native eye source extent differs from retained anatomy')
    w, h = source['width'], source['height']
    points = lm[:, :2].astype(np.float64) * [w, h]
    result = {}
    for side in ('left', 'right'):
        geometry = E._eye_geometry(points, E.EYES[side])
        width = geometry['eye_w']
        if not math.isfinite(width) or width < E.MIN_EYE_PX:
            raise ValueError('Native eye crop requires independently measurable visible eye geometry')
        region = np.concatenate((geometry['contour'], geometry['bag']))
        margin = .15 * width
        x = max(0, math.floor(float(region[:, 0].min()) - margin))
        y = max(0, math.floor(float(region[:, 1].min()) - margin))
        right = min(w, math.ceil(float(region[:, 0].max()) + margin))
        bottom = min(h, math.ceil(float(region[:, 1].max()) + margin))
        cw, ch = right - x, bottom - y
        if not 1 <= cw <= MAX_EDGE or not 1 <= ch <= MAX_EDGE:
            raise ValueError('Native eye rectangle exceeds 2048 pixels; no thumbnail substitution')
        result[side] = [x, y, cw, ch]
    if sum(r[2]*r[3] for r in result.values()) > MAX_CROP_PIXELS:
        raise ValueError('Native eye rectangles exceed combined four-million-pixel admission')
    return result


def repaired_pixels(pixels, current, *, byte_budget, cancelled=None):
    """The same ordered full-source repair solver and field mapping as export.

    This source-only replay intentionally does not run portrait/tone/geometry.
    Its float input is the shared decoder's actual encoded working-sRGB source.
    No crop-local repair replay or proxy bitmap is used.
    """
    import numpy as np
    from .creative_derived_repairs import validate_stacks
    from .repair_record import RepairOp, validate_repair_ops, check_repair_params
    validate_stacks(current)
    active = current.get('_repair_ops', current.get('repair_ops', []))
    if not active:
        return pixels
    h, w = pixels.shape[:2]
    from .eye_bag_crop_memory import admit
    admit((h, w), byte_budget)
    from .export import resample_field
    from .repair_replay import replay_repair_t
    import torch
    _poll(cancelled)
    cur = torch.from_numpy(np.ascontiguousarray(pixels.transpose(2, 0, 1))[None])
    # Map one operation at a time. Numeric mapping and order match export;
    # dropping earlier mapped weights changes lifetime, never solver inputs.
    for original in active:
        _poll(cancelled)
        op = RepairOp(op_id=original.op_id,
            weight=resample_field(original.weight, (h, w), uint8=True),
            kind=original.kind, params=check_repair_params(original.kind, original.params),
            source_binding=deepcopy(original.source_binding))
        validate_repair_ops([op], shape=(h, w))
        admit((h, w), byte_budget, op)
        _poll(cancelled)
        cur, _, _ = replay_repair_t(cur, [op])
        del op
    _poll(cancelled)
    return cur[0].permute(1, 2, 0).cpu().numpy().astype(np.float32)


def _png(pixels, rect, cancelled=None):
    import numpy as np
    from PIL import Image
    if (type(rect) is not list or len(rect) != 4 or any(type(n) is not int for n in rect)
            or rect[0] < 0 or rect[1] < 0 or not 1 <= rect[2] <= MAX_EDGE or not 1 <= rect[3] <= MAX_EDGE
            or rect[0]+rect[2] > pixels.shape[1] or rect[1]+rect[3] > pixels.shape[0]):
        raise ValueError('Native eye crop must use integer source-pixel edge bounds')
    x, y, w, h = rect
    crop = pixels[y:y+h, x:x+w]
    display = np.empty((h, w, 3), np.uint8)
    for start in range(0, h, 64):
        _poll(cancelled)
        row = crop[start:start+64]
        if not np.isfinite(row).all() or np.any(row < 0) or np.any(row > 1):
            raise ValueError('Native eye display cannot clip nonfinite or HDR source pixels')
        display[start:start+64] = np.floor(row * np.float32(255) + np.float32(.5)).astype(np.uint8)
    with Image.fromarray(display, 'RGB') as image:
        out = io.BytesIO(); image.save(out, format='PNG'); raw = out.getvalue()
    _poll(cancelled)
    if len(raw) > MAX_PNG_BYTES:
        raise ValueError('Native eye PNG exceeds four-MiB transport admission; no resize fallback')
    return {'mime': 'image/png', 'width': w, 'height': h,
            'sha256': sha256(raw).hexdigest(), 'base64': base64.b64encode(raw).decode('ascii')}, len(raw)


def prepare(engine, state, target, current, source, snapshot_sha256, *, cancelled=None):
    """Called inside the host's before/after complete snapshot identity fence."""
    from .creative_document_host import memory_budget
    from .spill_removal_paint_source import source_pixels
    from .creative_derived_source import verify
    source = deepcopy(source)
    if source['width']*source['height'] > MAX_SOURCE_PIXELS:
        raise ValueError('Native eye source exceeds 32-million-pixel decode admission')
    analysis = engine._people_analyses.get(source['sha256'], {}).get(target['target_id'])
    if analysis is None:
        raise ValueError('Native eye inspection requires the selected source-owned face analysis')
    rects = rectangles(state['faces'][target['target_id']], analysis, source)
    budget = memory_budget()
    active = current.get('_repair_ops', current.get('repair_ops', []))
    if active:
        from .eye_bag_crop_memory import admit
        admit((source['height'], source['width']), budget)
    _poll(cancelled)
    pixels = source_pixels(engine, source)
    _poll(cancelled)
    pixels = repaired_pixels(pixels, current, byte_budget=budget, cancelled=cancelled)
    eyes, total = {}, 0
    for side, rect in rects.items():
        image, length = _png(pixels, rect, cancelled)
        total += length
        if total > MAX_TOTAL_PNG_BYTES:
            raise ValueError('Native eye PNGs exceed combined transport admission; no detail reduction')
        eyes[side] = {'rect': rect, 'image': image}
    del pixels
    verify(source, engine)
    _poll(cancelled)
    return {'version': 1, 'mapping': 'source_pixel_edges', 'orientation': 'exif_normalized_once',
            'display_encoding': 'srgb_rgb8', 'sampling': 'one_source_pixel_per_image_pixel',
            'source_sha256': source['sha256'], 'source_width': source['width'], 'source_height': source['height'],
            'input_stage': 'committed_repair' if current.get('_repair_ops', current.get('repair_ops', [])) else 'source',
            'snapshot_sha256': snapshot_sha256, 'eyes': eyes}
