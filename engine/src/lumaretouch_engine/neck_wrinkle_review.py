# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded transport for genuine full-source/full-render neck review pixels.

Display reduction never supplies numerical input or a crop. Pixel crops are
sliced first at integer source/output edges and are never resized. SHA-256 on
transport images covers PNG bytes; separate private hashes cover full float
rasters. AUTHORED / UNRUN; no runtime or photographic acceptance is asserted.
"""
from hashlib import sha256
import base64
import io
from .neck_wrinkle_actions import check_rect

# 1152 squared RGB plus PNG overhead fits the UI's strict 4 MiB transport cap.
DISPLAY_EDGE = 1152
MAX_PNG_BYTES = 4 * 1024 * 1024
DISPLAY_RESERVE_BYTES = 96 * 1024 * 1024


def poll(cancelled=None):
    if cancelled is not None and cancelled():
        raise InterruptedError('Neck review was cancelled or its source changed')


def check_pixels(rgb, *, cancelled=None):
    import numpy as np
    if (type(rgb) is not np.ndarray or rgb.ndim != 3 or rgb.shape[2] != 3
            or rgb.dtype not in (np.dtype('float32'), np.dtype('float64'), np.dtype('uint8'))
            or min(rgb.shape[:2]) < 1 or max(rgb.shape[:2]) > 65536
            or rgb.shape[0] * rgb.shape[1] > 32_000_000):
        raise ValueError('Neck review requires real finite RGB pixels, never a shape carrier')
    for chunk in np.nditer(rgb, flags=['external_loop', 'buffered'], op_flags=['readonly'],
                           order='C', buffersize=262144):
        poll(cancelled)
        if not np.isfinite(chunk).all() or (rgb.dtype != np.uint8 and np.any((chunk < 0) | (chunk > 1))):
            raise ValueError('Neck review refuses non-SDR pixels rather than clipping or flattening')
    return rgb


def raster_hash(rgb, *, cancelled=None):
    from .optics_candidate_identity import fingerprint
    check_pixels(rgb, cancelled=cancelled)
    result = fingerprint(rgb)
    poll(cancelled)
    return result


def display_rgb(rgb, *, cancelled=None):
    """Display-only BOX reduction of completed pixels, in bounded stripes.

    Never allocates a complete contiguous float channel merely to display it.
    Stripes partition all source rows; no crop is ever taken from this result.
    This is not the numerical/source sampler or a render-domain replacement.
    """
    import numpy as np
    from PIL import Image
    check_pixels(rgb, cancelled=cancelled)
    height, width = rgb.shape[:2]
    scale = min(1., DISPLAY_EDGE / max(width, height))
    out_width, out_height = max(1, round(width * scale)), max(1, round(height * scale))
    output = np.empty((out_height, out_width, 3), np.uint8)
    # Each float source-channel stripe is usually <=2 MP. For a very wide
    # source one destination row may need more, bounded by the canonical 32 MP
    # and 65536-edge input contracts; its temporary copies still fit the 96 MiB display reserve.
    rows = max(1, min(out_height, (2_000_000 * out_height) // (width * height)))
    for first in range(0, out_height, rows):
        stop = min(first + rows, out_height)
        source_first = first * height // out_height
        source_stop = stop * height // out_height
        for index in range(3):
            poll(cancelled)
            with Image.fromarray(rgb[source_first:source_stop, :, index]) as plane:
                with plane.resize((out_width, stop-first), Image.Resampling.BOX) as small:
                    value = np.asarray(small, dtype=np.float32).copy()
            if rgb.dtype != np.uint8:
                value *= 255.
            output[first:stop, :, index] = np.rint(value).astype(np.uint8)
    return output


def encode_rgb(rgb, *, cancelled=None):
    import numpy as np
    from PIL import Image
    poll(cancelled)
    if (type(rgb) is not np.ndarray or rgb.dtype != np.uint8 or rgb.ndim != 3
            or rgb.shape[2] != 3 or not 1 <= min(rgb.shape[:2]) <= max(rgb.shape[:2]) <= 1280):
        raise ValueError('Neck display transport must be bounded RGB8')
    with Image.fromarray(rgb, 'RGB') as picture:
        stream = io.BytesIO(); picture.save(stream, format='PNG')
        raw = stream.getvalue()
    if len(raw) > MAX_PNG_BYTES:
        raise ValueError('Neck image exceeds its bounded PNG budget')
    poll(cancelled)
    return {'mime': 'image/png', 'base64': base64.b64encode(raw).decode('ascii'),
            'width': int(rgb.shape[1]), 'height': int(rgb.shape[0]), 'sha256': sha256(raw).hexdigest()}


def full_image(rgb, *, cancelled=None):
    return encode_rgb(display_rgb(rgb, cancelled=cancelled), cancelled=cancelled)


def crop_image(rgb, rect, *, cancelled=None):
    import numpy as np
    check_pixels(rgb, cancelled=cancelled)
    x, y, width, height = check_rect(rect, (int(rgb.shape[1]), int(rgb.shape[0])))
    # Crop actual canonical/full-render pixels, not the whole-frame thumbnail.
    crop = rgb[y:y + height, x:x + width]
    if crop.dtype != np.uint8:
        crop = np.rint(crop * 255.).astype(np.uint8)
    return encode_rgb(crop, cancelled=cancelled)


def support_image(rgb, admitted, hard_protect, eligible_mask, window_yxhw, *, cancelled=None):
    """Cyan numerical admission, magenta hard veto, orange rejected context.

    The eligibility plane comes from the exact native full-grid preparation,
    not a host-invented erosion, fake neck segmentation or changed-pixel mask.
    """
    import numpy as np
    from PIL import Image
    check_pixels(rgb, cancelled=cancelled)
    height, width = rgb.shape[:2]
    if (type(admitted) is not np.ndarray or admitted.dtype != np.float32
            or admitted.shape != (height, width) or type(hard_protect) is not np.ndarray
            or hard_protect.dtype != np.bool_ or hard_protect.shape != admitted.shape
            or type(eligible_mask) is not np.ndarray or eligible_mask.dtype != np.bool_):
        raise ValueError('Neck diagnostic masks must retain their actual full-source/native domains')
    if (type(window_yxhw) not in (tuple, list) or len(window_yxhw) != 4
            or any(type(n) is not int for n in window_yxhw)):
        raise ValueError('Neck numerical eligibility omitted its exact source window')
    y, x, h, w = window_yxhw
    if (min(y, x) < 0 or min(h, w) < 1 or y + h > height or x + w > width
            or eligible_mask.shape != (h, w)):
        raise ValueError('Neck numerical eligibility window differs from the full-source grid')
    if not np.isfinite(admitted).all() or np.any((admitted < 0) | (admitted > 1)):
        raise ValueError('Neck admitted support is not a finite weight')
    eligible_input = admitted[y:y + h, x:x + w]
    if np.any(eligible_mask & ((eligible_input <= 0) | hard_protect[y:y + h, x:x + w])):
        raise ValueError('Neck numerical eligibility cannot create positive or protected support')
    # One source-grid byte plane plus bounded display channels. Never save it.
    diagnostic = np.zeros((height, width), np.uint8)
    diagnostic[admitted > 0] = 2
    roi = diagnostic[y:y + h, x:x + w]; roi[eligible_mask] = 1
    diagnostic[hard_protect] = 3
    base = display_rgb(rgb, cancelled=cancelled).astype(np.float32) / 255.
    size = int(base.shape[1]), int(base.shape[0])
    colors = ((0., 1., 1.), (1., .55, 0.), (1., 0., 1.))
    for label, color in enumerate(colors, 1):
        poll(cancelled)
        with Image.fromarray((diagnostic == label).astype(np.uint8) * 255) as mask:
            with mask.resize(size, Image.Resampling.BOX) as small:
                alpha = np.asarray(small, dtype=np.float32)[..., None] * (.65 / 255.)
        base = base * (1. - alpha) + np.asarray(color, np.float32) * alpha
    return encode_rgb(np.rint(base * 255.).astype(np.uint8), cancelled=cancelled)
