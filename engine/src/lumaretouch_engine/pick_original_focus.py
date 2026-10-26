# SPDX-License-Identifier: GPL-3.0-or-later
"""Original-pixel local evidence, not a focus classifier. SOURCE ONLY / UNRUN.

Reuse the authenticated full-source owner; never use load_rgb or camera previews.
Only the selected crop is measured. No ranking, flags, source writes or model use.
"""
from __future__ import annotations

import base64
import io
import math

CROP_EDGE = 256
MAX_TARGETS = 8
# Crop arithmetic, PNG and eight retained display crops; not process RSS.
REVIEW_RESERVE = 32 * 1024**2
MAX_DECODE_BUDGET = 4 * 1024**3
VERSION = 1


def point(x=.5, y=.5):
    if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1
           for v in (x, y)):
        raise ValueError('Original review point must contain finite coordinates in [0,1]')
    return float(x), float(y)


def crop_rect(width, height, position):
    if any(type(v) is not int or v < 3 for v in (width, height)):
        raise ValueError('Original crop needs at least 3 by 3 source pixels')
    x, y = point(*position)
    w, h = min(CROP_EDGE, width), min(CROP_EDGE, height)
    left = max(0, min(width-w, int(x*(width-1)) - w//2))
    top = max(0, min(height-h, int(y*(height-1)) - h//2))
    return left, top, w, h


def measures(rgb):
    """Native crop encoded-sRGB luma derivatives, without resize or denoising.

    These are uncalibrated local texture/contrast readings, not probabilities.
    Noise, JPEG ringing, sharpening and subject texture all affect them.
    """
    import numpy as np
    if (type(rgb) is not np.ndarray or rgb.dtype != np.float32 or rgb.ndim != 3
            or rgb.shape[2] != 3 or min(rgb.shape[:2]) < 3
            or max(rgb.shape[:2]) > CROP_EDGE or not np.isfinite(rgb).all()
            or np.any(rgb < 0) or np.any(rgb > 1)):
        raise ValueError('Focus evidence requires bounded native SDR float32 RGB crop')
    gray = rgb[..., 0]*.2126 + rgb[..., 1]*.7152 + rgb[..., 2]*.0722
    center = gray[1:-1, 1:-1]
    dx = (gray[1:-1, 2:] - gray[1:-1, :-2]) * .5
    dy = (gray[2:, 1:-1] - gray[:-2, 1:-1]) * .5
    lap = (gray[1:-1, 2:] + gray[1:-1, :-2] + gray[2:, 1:-1]
           + gray[:-2, 1:-1] - 4*center)
    variance = float(np.var(gray, dtype=np.float64))
    lapvar = float(np.var(lap, dtype=np.float64))
    # Explicit numerical comparability guard, NOT an in-focus/out-of-focus line.
    low = variance < 1e-6
    return {'contrast': math.sqrt(variance),
            'gradient_energy': float(np.mean(dx*dx + dy*dy, dtype=np.float64)),
            'laplacian_variance': lapvar,
            'detail_to_contrast': None if low else lapvar/variance,
            'low_contrast': low}


def dimensions(path, known_size):
    from .decode import is_raw, EXIF_ORIENTATION, SWAPPED_ORIENTATIONS
    if is_raw(path):
        # Existing LibRaw identify does not expose oriented dimensions. Do not
        # guess axes from its unrotated extent or an embedded JPEG thumbnail.
        if (type(known_size) not in (tuple, list) or len(known_size) != 2
                or any(type(v) is not int or v < 3 for v in known_size)):
            raise ValueError('Open RAW in the editor first to establish full oriented source dimensions')
        return tuple(known_size)
    from PIL import Image
    with Image.open(path) as image:
        orientation = image.getexif().get(EXIF_ORIENTATION, 1) or 1
        if type(orientation) is not int or orientation not in range(1, 9):
            raise ValueError('Original source orientation is invalid')
        return (image.height, image.width) if orientation in SWAPPED_ORIENTATIONS else image.size


def review(path, *, known_size=None, position=(.5, .5), cancelled=lambda: False):
    from . import local_mask_state as identity
    from .portrait_fit_source import capture_original, MAX_PIXELS, MAX_SOURCE_BYTES
    from .cpu_memory_budget import available_estimate
    from PIL import Image
    import numpy as np
    position = point(*position)
    stamp = identity.file_stamp(path)
    if not 0 < stamp[2] <= MAX_SOURCE_BYTES:
        raise ValueError('Original focus source exceeds canonical compressed-file bound')
    if cancelled():
        raise InterruptedError('Original focus review cancelled')
    width, height = dimensions(path, known_size)
    if width*height > MAX_PIXELS:
        raise ValueError('Original focus review exceeds canonical 32MP bound; no proxy fallback')
    rect = crop_rect(width, height, position)
    # Budget snapshot accounts for already resident engine allocations; keep
    # half available for other owners. Native codecs/allocator RSS is not proven.
    budget = min(MAX_DECODE_BUDGET, available_estimate()//2) - REVIEW_RESERVE
    if budget <= 0:
        raise MemoryError('Insufficient memory for original focus review')
    source = {'sha256': identity.source_digest(path), 'width': width, 'height': height}
    frozen = capture_original(path, expected_source=source, expected_stamp=stamp,
                              byte_budget=budget, cancelled=cancelled)
    if cancelled():
        raise InterruptedError('Original focus review cancelled')
    x, y, w, h = rect
    crop = frozen.pixels[y:y+h, x:x+w]
    result = measures(crop)
    # Only display is quantized to RGB8; metrics above keep full-source float.
    display = np.floor(crop*255 + .5).astype(np.uint8)
    with Image.fromarray(display, 'RGB') as image, io.BytesIO() as stream:
        image.save(stream, format='PNG')
        preview = 'data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode('ascii')
    if cancelled():
        raise InterruptedError('Original focus review cancelled')
    if identity.file_stamp(path) != stamp or identity.source_digest(path) != source['sha256']:
        raise ValueError('Original source changed during review; discard the crop')
    return {'version': VERSION, 'scope': 'original-source-crop', 'source': source,
            'source_stamp': list(stamp), 'source_bits': frozen.source_bits,
            'input_sha256': frozen.input_sha256, 'point': list(position),
            'rect': list(rect), **result, 'preview_png': preview,
            'notes': [
                'Only this original-pixel crop was measured; not whole-image or detected-face focus.',
                'Unedited full decoded source in encoded sRGB, not sensor mosaic or edited output.',
                'RAW development, noise, sharpening, compression, texture and contrast affect these readings; no universal focus threshold.',
                'Compare corresponding subjects at the same source sampling; a common normalized point may select different subjects.',
                'Low contrast suppresses the normalized ratio; it does not certify blur.',
                'RGB8 PNG display is quantized; measurements retain canonical source precision. No crop resize; CSS/device scaling may vary.',
                'Capture authenticated before/after by digest and stat; later display freshness uses best-effort stat, not an atomic filesystem snapshot.',
                'No automatic ratings, flags, deletion or best-photo decision.']}


def visible(row):
    """Do not serialize a known-stale snapshot; no full-file hashing on repaint."""
    result = row.get('pick_focus')
    error = row.get('pick_focus_error')
    if result is not None:
        from .local_mask_state import file_stamp
        try:
            if list(file_stamp(row['path'])) != result.get('source_stamp'):
                return None, 'Original changed after review; capture again'
        except OSError:
            return None, 'Original unavailable after review; capture again'
    return result, error
