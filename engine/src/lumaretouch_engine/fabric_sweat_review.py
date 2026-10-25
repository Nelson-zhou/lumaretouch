# SPDX-License-Identifier: GPL-3.0-or-later
"""Display-only actual eligibility and protection, never numerical input. UNRUN."""
import numpy as np



def display_image(encoded_rgb):
    from PIL import Image
    from .neck_wrinkle_review import display_rgb, encode_rgb
    pixels = display_rgb(encoded_rgb)
    h, w = pixels.shape[:2]
    scale = min(1., 768 / max(h, w))
    if scale < 1:
        with Image.fromarray(pixels, 'RGB') as picture:
            with picture.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.Resampling.BOX) as small:
                pixels = np.asarray(small).copy()
    result = encode_rgb(pixels)
    if len(result['base64']) > 4 * ((2 * 1024**2 + 2) // 3):
        raise ValueError('Fabric sweat display exceeds 2 MiB PNG transport budget')
    return result


def mask_image(encoded_rgb, prepared):
    from PIL import Image
    from .neck_wrinkle_review import display_rgb, encode_rgb
    from .fabric_sweat_measure import Prepared
    if not isinstance(prepared, Prepared) or encoded_rgb.shape != (prepared.height, prepared.width, 3):
        raise ValueError('Fabric sweat mask display needs the exact prepared source grid')
    display = display_rgb(encoded_rgb).astype(np.float32) / 255.
    size = (display.shape[1], display.shape[0])
    # Green = real native eligible target; orange = insufficient local context;
    # magenta = manual hard protection. This is not an automatic stain detector.
    roles = ((prepared.eligible > 0, (0., 1., .4)),
             ((prepared.target > 0) & (prepared.eligible == 0), (1., .55, 0.)),
             (prepared.protect > 0, (1., 0., 1.)))
    for mask, color in roles:
        with Image.fromarray(mask.astype(np.uint8) * 255) as plane:
            with plane.resize(size, Image.Resampling.BOX) as small:
                alpha = np.asarray(small, dtype=np.float32)[..., None] * (.6 / 255.)
        display = display * (1 - alpha) + np.asarray(color, np.float32) * alpha
    return display_image(np.rint(display * 255).astype(np.uint8))
