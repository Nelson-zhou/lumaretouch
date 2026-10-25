# SPDX-License-Identifier: GPL-3.0-or-later
"""Full-canvas raster coverage -> source-local creative mask, AUTHORED / UNRUN.

The existing compositor multiplies a mask into SOURCE texels before bilinear
transformation. Consequently we project canvas coverage to source pixel centers
using the existing forward affine, then review the actual unchanged compositor.
This is not an extra canvas-alpha pass and is not an inverse-image approximation.
"""
from __future__ import annotations
import base64
from copy import deepcopy
import hashlib
from io import BytesIO
from . import creative_document_state as S
from .creative_document_assets import make_asset
from .creative_selection_recipe import mask_policy, validate

DISPLAY_PIXELS = 262_144
DISPLAY_EDGE = 4096
DISPLAY_RESERVE = 32 * 1024 * 1024
PROJECTION_PIXELS = 32_768
PROJECTION_RESERVE = 16 * 1024 * 1024


def poll(cancelled):
    if cancelled():
        raise InterruptedError('Creative selection source or request changed')


def content_hash(content, cancelled=lambda: False):
    sha = hashlib.sha256()
    for offset in range(0, len(content), 1024 * 1024):
        poll(cancelled)
        sha.update(memoryview(content)[offset:offset + 1024 * 1024])
    poll(cancelled)
    return sha.hexdigest()


def image(png, width, height):
    if len(png) > 4 * 1024 * 1024:
        raise ValueError('Selection display PNG exceeds its transport budget')
    return {'mime': 'image/png', 'width': width, 'height': height,
            'sha256': hashlib.sha256(png).hexdigest(),
            'base64': base64.b64encode(png).decode('ascii')}


def display_size(width, height):
    factor = min(1.0, DISPLAY_EDGE / max(width, height), (DISPLAY_PIXELS / (width * height)) ** .5)
    return max(1, int(width * factor)), max(1, int(height * factor))


def mask_image(record, width, height, *, cancelled=lambda: False):
    """Whole source-local coverage, sampled only for the explicit display view."""
    import numpy as np
    from PIL import Image
    poll(cancelled)
    w, h = display_size(width, height)
    if record is None:
        values = np.full((h, w), 255, dtype=np.uint8)
    else:
        if record['kind'] != 'mask' or (record['width'], record['height']) != (width, height):
            raise ValueError('Selection coverage review is not the complete source mask')
        source = np.frombuffer(record['content'], dtype='<f4').reshape(height, width)
        xs = np.minimum(width - 1, ((np.arange(w) + .5) * width / w).astype(np.int64))
        ys = np.minimum(height - 1, ((np.arange(h) + .5) * height / h).astype(np.int64))
        values = np.rint(source[np.ix_(ys, xs)] * 255).astype(np.uint8)
    buffer = BytesIO()
    Image.fromarray(values, 'L').save(buffer, format='PNG')
    poll(cancelled)
    return image(buffer.getvalue(), w, h)


class OverlayAssets:
    """A candidate is private, not interned into the live creative asset store."""
    def __init__(self, assets, record):
        self.assets, self.record = assets, record

    def get(self, identity, kind=None):
        if identity != self.record['id']:
            return self.assets.get(identity, kind)
        if kind is not None and kind != self.record['kind']:
            raise ValueError('Candidate mask kind mismatch')
        return deepcopy(self.record)


def composite_image(document, assets, *, max_bytes, cancelled=lambda: False):
    from .creative_document_render import CreativeRenderer
    renderer = CreativeRenderer(document, assets, max_bytes=max_bytes, cancelled=cancelled)
    c = document['canvas']
    edge_factor = min(1.0, DISPLAY_EDGE / max(c['width'], c['height']))
    display_budget = max(1, min(DISPLAY_PIXELS, int(c['width'] * c['height'] * edge_factor ** 2)))
    png, width, height = renderer.preview_png(max_pixels=display_budget)
    poll(cancelled)
    return image(png, width, height)


def project_canvas_mask(canvas, transform, width, height, *, cancelled=lambda: False):
    """Bilinear full-canvas coverage at forward-transformed source pixel centers.

    Canvas samples live at (n+.5,m+.5). Taps outside the full canvas are zero;
    source centers outside the canvas edge rectangle receive zero as well. No
    edge-clamping, display pixels, inverse-affine swap or transform duplication.
    Existing mask-before-transform compositor semantics remain untouched.
    """
    import numpy as np
    ch, cw = canvas.shape
    a, b, c, d, e, f = S.affine(transform, width, height)
    output = np.empty((height, width), dtype='<f4')
    flat = output.reshape(-1)
    for start in range(0, width * height, PROJECTION_PIXELS):
        poll(cancelled)
        end = min(width * height, start + PROJECTION_PIXELS)
        index = np.arange(start, end, dtype=np.int64)
        sx, sy = index % width + .5, index // width + .5
        cx, cy = a * sx + b * sy + c, d * sx + e * sy + f
        inside = (cx >= 0) & (cx < cw) & (cy >= 0) & (cy < ch)
        ux, uy = cx - .5, cy - .5
        ix, iy = np.floor(ux).astype(np.int64), np.floor(uy).astype(np.int64)
        fx, fy = ux - ix, uy - iy
        values = np.zeros(end - start, dtype=np.float64)
        for dx, dy, weights in ((0, 0, (1-fx)*(1-fy)), (1, 0, fx*(1-fy)),
                                (0, 1, (1-fx)*fy), (1, 1, fx*fy)):
            x, y = ix + dx, iy + dy
            valid = inside & (x >= 0) & (x < cw) & (y >= 0) & (y < ch)
            values[valid] += canvas[y[valid], x[valid]] * weights[valid]
        np.clip(values, 0, 1, out=values)
        flat[start:end] = values
    poll(cancelled)
    return output


def candidate(document, layer, assets, recipe, policy, *, max_bytes, cancelled=lambda: False):
    import numpy as np
    from .creative_selection_native import Evaluator, MAX_NATIVE_BYTES, TILE_EDGE
    recipe = validate(recipe, document['canvas'])
    policy = mask_policy(policy, layer['mask_id'])
    source = assets.get(layer['asset_id'], 'rgba')
    w, h = source['width'], source['height']
    cw, ch = document['canvas']['width'], document['canvas']['height']
    # Full canvas, local array + immutable codec bytes + validation overlap,
    # native tile scratch, projection chunks and display/review transport.
    needed = cw * ch * 4 + w * h * 12 + MAX_NATIVE_BYTES + PROJECTION_RESERVE + DISPLAY_RESERVE
    if type(max_bytes) is not int or needed > max_bytes:
        raise ValueError('Selection full-resolution coverage exceeds the memory budget; no downsampled mask is substituted')
    poll(cancelled)
    evaluator = Evaluator(recipe, cancelled=cancelled)
    canvas = np.empty((ch, cw), dtype=np.float32)
    for y in range(0, ch, TILE_EDGE):
        for x in range(0, cw, TILE_EDGE):
            poll(cancelled)
            tile = evaluator.tile(x, y, min(TILE_EDGE, cw-x), min(TILE_EDGE, ch-y))
            canvas[y:y+tile.shape[0], x:x+tile.shape[1]] = tile
    local = project_canvas_mask(canvas, layer['transform'], w, h, cancelled=cancelled)
    del canvas
    old = assets.get(layer['mask_id'], 'mask') if layer['mask_id'] is not None else None
    if old is not None and policy != 'replace':
        original = np.frombuffer(old['content'], dtype='<f4').reshape(-1)
        out = local.reshape(-1)
        for start in range(0, w*h, PROJECTION_PIXELS):
            poll(cancelled)
            dst, src = out[start:start+PROJECTION_PIXELS], original[start:start+PROJECTION_PIXELS]
            if policy == 'union':
                np.maximum(dst, src, out=dst)
            elif policy == 'intersect':
                np.minimum(dst, src, out=dst)
            elif policy == 'subtract':
                np.subtract(src, dst, out=dst); np.maximum(dst, 0, out=dst)
    poll(cancelled)
    record = make_asset('mask', w, h, local.tobytes(order='C'))
    poll(cancelled)
    after = deepcopy(document)
    target = next(item for item in after['layers'] if item['id'] == layer['id'])
    target['mask_id'] = record['id']
    if target['mask_id'] != layer['mask_id']:
        after['revision'] += 1
    overlay = OverlayAssets(assets, record)
    S.validate(after, overlay)
    return record, after, old


def prepare(document, layer, assets, recipe, policy, *, max_bytes, cancelled=lambda: False):
    record, after, old = candidate(document, layer, assets, recipe, policy,
                                   max_bytes=max_bytes, cancelled=cancelled)
    # Each renderer is released before the next one. Only four bounded PNGs and
    # the single source-local candidate remain; no full RGBA image snapshots.
    remaining = max_bytes - len(record['content']) - DISPLAY_RESERVE
    if remaining < 1_048_576:
        raise ValueError('Selection review cannot reserve complete compositor resources')
    overlay = OverlayAssets(assets, record)
    before_image = composite_image(document, assets, max_bytes=remaining, cancelled=cancelled)
    after_image = composite_image(after, overlay, max_bytes=remaining, cancelled=cancelled)
    review = {'before_mask': mask_image(old, record['width'], record['height'], cancelled=cancelled),
              'after_mask': mask_image(record, record['width'], record['height'], cancelled=cancelled),
              'before_composite': before_image, 'after_composite': after_image}
    poll(cancelled)
    return record, after, review
