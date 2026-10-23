"""Full-source photographed-shadow extraction before replacement composition.

The completed shaded background determines display transmission. RGB8 locator
pixels, edited pixels, and proxy alpha never become extraction evidence. Export prepares once
on the exact original/derived source grid and crops the completed ID fields.
"""
from copy import deepcopy
from hashlib import sha256
import json
import re
import numpy as np

FIELD_KEYS = frozenset(('original_shadow_source',))
HASH_KEYS = ('input_sha256', 'linear_sha256', 'reviewed_alpha_sha256',
             'lit_floor_sha256', 'retention_sha256', 'opacity_sha256',
             'recipe_sha256', 'background_input_sha256', 'full_background_sha256',
             'display_background_sha256', 'reduced_background_sha256',
             'reduced_shaded_sha256', 'background_sha256')
PROOF_KEYS = frozenset(('version', 'algorithm', 'estimator', 'encoding', 'source',
                        'shape', 'render_shape', 'dtype', *HASH_KEYS))


def active(value):
    from . import id_background_state as I, original_shadow_state as S
    return I.active(value) and S.active(I.original_shadow_of(value))


def _hash(array, cancelled=lambda: False):
    result = sha256()
    for row in array:
        if cancelled():
            raise InterruptedError('Original-shadow source verification cancelled')
        result.update(memoryview(np.ascontiguousarray(row)).cast('B'))
    return result.hexdigest()


def recipe_digest(value):
    from . import id_background_state as I
    return sha256(json.dumps(I.check(value), sort_keys=True, separators=(',', ':'),
                             allow_nan=False).encode('utf-8')).hexdigest()


def source_identity(pixels, source, *, full_source=True, cancelled=lambda: False):
    from . import local_mask_state as M
    binding = M.check({'source': source, 'semantic_owner': None,
                       'recipe': M.empty()['recipe']})['source']
    if (full_source is not True or binding is None or type(pixels) is not np.ndarray
            or pixels.dtype not in (np.dtype('uint8'), np.dtype('uint16'), np.dtype('float32'))
            or pixels.shape != (binding['height'], binding['width'], 3)):
        raise ValueError('Original-shadow extraction requires exact full-source uint8/uint16/float32 encoded RGB, not a proxy or RGBA matte')
    from .original_shadow_native import memory_estimate
    memory_estimate(pixels.shape[:2])
    for row in pixels:
        if cancelled():
            raise InterruptedError('Original-shadow source verification cancelled')
        if not np.isfinite(row).all() or pixels.dtype == np.float32 and (np.any(row < 0) or np.any(row > 1)):
            raise ValueError('Original-shadow source must be finite SDR; HDR clipping is forbidden')
    return {'source': deepcopy(binding), 'shape': list(pixels.shape),
            'dtype': pixels.dtype.str, 'input_sha256': _hash(pixels, cancelled)}


def linear_source(pixels, *, cancelled=lambda: False):
    if type(pixels) is not np.ndarray or pixels.dtype not in (np.uint8, np.uint16, np.float32):
        raise ValueError('Original-shadow source dtype is unsupported')
    divisor = 255. if pixels.dtype == np.uint8 else 65535. if pixels.dtype == np.uint16 else 1.
    result = np.empty(pixels.shape, np.float32)
    for y in range(0, len(pixels), 64):
        if cancelled():
            raise InterruptedError('Original-shadow source decoding cancelled')
        block = pixels[y:y+64].astype(np.float32) / divisor
        if not np.isfinite(block).all() or np.any(block < 0) or np.any(block > 1):
            raise ValueError('Original-shadow cannot clip or reinterpret source radiance')
        result[y:y+64] = np.where(block <= .04045, block / 12.92, ((block + .055) / 1.055) ** 2.4)
    result.setflags(write=False)
    return result


def check_source_proof(proof, shape, source=None, value=None):
    from . import local_mask_state as M, original_shadow_state as S, original_shadow_native as N
    if (type(shape) not in (tuple, list) or len(shape) != 2
            or any(type(v) is not int or v < 1 for v in shape)
            or type(proof) is not dict or set(proof) != PROOF_KEYS
            or type(proof['version']) is not int or proof['version'] != 1
            or proof['algorithm'] != S.ALGORITHM or proof['estimator'] != N.ESTIMATOR
            or proof['encoding'] != N.ENCODING or proof['render_shape'] != [*shape, 3]
            or proof['dtype'] not in (np.dtype('uint8').str, np.dtype('uint16').str, np.dtype('float32').str)
            or any(type(proof[k]) is not str or not re.fullmatch('[0-9a-f]{64}', proof[k]) for k in HASH_KEYS)):
        raise ValueError('Original-shadow fields lack exact full-source preparation evidence')
    binding = M.check({'source': proof['source'], 'semantic_owner': None,
                       'recipe': M.empty()['recipe']})['source']
    if (binding is None or proof['shape'] != [binding['height'], binding['width'], 3]
            or shape[0] > binding['height'] or shape[1] > binding['width']
            or source is not None and binding != source
            or value is not None and proof['recipe_sha256'] != recipe_digest(value)):
        raise ValueError('Original-shadow source, render extent or reviewed recipe changed')
    if proof['shape'] == proof['render_shape'] and proof['full_background_sha256'] != proof['background_sha256']:
        raise ValueError('Original-shadow full render has inconsistent background proof')
    return json.dumps(proof, sort_keys=True, separators=(',', ':'), allow_nan=False)


def memory_estimate(shape, value):
    if not active(value):
        return 0
    from .original_shadow_native import memory_estimate as native_memory
    from . import id_background_state as I
    source = I.check(value)['source']
    # Extraction is ALWAYS full-source, even for display. Reserve exact decoded
    # source, reviewed alpha, two raster masks, conversion and resampling peak.
    h, w = source['height'], source['width']
    return native_memory((h, w)) + 40 * h * w + 16 * shape[0] * shape[1] + 64 * max(1, w) * 48


def live_source_key(engine, value):
    """Bind canonical file/asset bytes, never the quantized display locator."""
    from . import creative_derived_source as D, local_mask_state as M
    source = D.verify(value['source'], engine)
    row = engine._docs[engine._doc_index]
    before = M.file_stamp(row['path'])
    original = M.source_digest(row['path'])
    if before != M.file_stamp(row['path']) or row.get('_local_source_stamp') != before:
        raise ValueError('Original-shadow original source/provenance changed; reopen the photograph')
    base = D.record(engine)
    content = None if base is None else sha256(base['content']).hexdigest()
    return source['sha256'], original, content, before


def verify_original_format(path):
    """Reject alpha/HDR metadata before a legacy decoder can discard it.

    Genuine PNG16/TIFF16 decoders retain their stricter channel checks. Actual
    RGBA with an all-one alpha channel is opaque, not implicitly flattened.
    """
    from .decode import is_raw
    from .full_source_working import source_bits, require_opaque_8bit
    from PIL import Image
    if is_raw(path):
        return 16
    with Image.open(path) as image:
        if image.width * image.height > 32_000_000:
            raise ValueError('Original-shadow source exceeds full-source pixel budget')
        bits = source_bits(path, image)
        if bits > 16 or image.mode == 'F':
            raise ValueError('Original-shadow original-file float/HDR decoding is unsupported; no quantization fallback')
        # Explicit HDR transfer metadata cannot be treated as ordinary encoded
        # sRGB. PNG16's genuine decoder owns its richer precedence/CRC checks,
        # including supported SDR cICP and fully opaque gray/RGBA16 sources.
        if image.format != 'PNG' or bits <= 8:
            cicp = image.info.get('cicp', image.info.get('cICP'))
            if (cicp is not None and (type(cicp) not in (bytes, tuple, list)
                    or tuple(cicp) != (1, 13, 0, 1) or image.info.get('icc_profile'))
                    or any(image.info.get(key) is not None for key in ('mDCV', 'cLLI', 'mdcv', 'clli'))):
                raise ValueError('Original-shadow requires an explicitly supported SDR source encoding')
        if bits <= 8:
            require_opaque_8bit(image)
        elif image.format != 'PNG' and ('A' in image.getbands() or 'transparency' in image.info):
            raise ValueError('Original-shadow high-bit alpha source is unsupported; no channel discard')
        return 16 if bits > 8 else 8


def full_source(engine, value, *, cancelled=lambda: False):
    """Use the same genuine original/derived decoder boundary as full export."""
    from . import creative_derived_source as D
    from .cpu_memory_budget import available_estimate
    from .creative_document_base import export_source
    from .decode import load_full
    from .full_source_working import working_rgb
    before = live_source_key(engine, value)
    shape = (value['source']['height'], value['source']['width'])
    asset = value['background']['asset'] if value['background']['kind'] == 'asset' else None
    asset_bytes = 0 if asset is None else 48 * asset['height'] * asset['width']
    if memory_estimate(shape, value) + 128 * shape[0] * shape[1] + asset_bytes + 128 * 1024**2 > available_estimate():
        raise MemoryError('Full original-shadow source and fields exceed available memory; no proxy fallback')
    if cancelled():
        raise InterruptedError('Original-shadow full source loading cancelled')
    base = D.record(engine)
    if base is not None:
        pixels = export_source(base, cancelled=cancelled, max_bytes=min(4_000_000_000, available_estimate()))
    else:
        path = engine._docs[engine._doc_index]['path']
        bits = verify_original_format(path)
        decoded = load_full(path, max_px=32_000_000, device='cpu', want_bits=bits)
        if ((decoded.h, decoded.w) != (decoded.src_h, decoded.src_w) or decoded.draft_used
                or (decoded.raw or {}).get('used_preview') or (decoded.raw or {}).get('half_size')
                or bits == 16 and decoded.rgb.dtype != np.uint16):
            raise ValueError('Original-shadow extraction cannot use reduced or lower-bit source pixels')
        pixels = working_rgb(decoded)
    source_identity(pixels, value['source'], cancelled=cancelled)
    if live_source_key(engine, value) != before:
        raise ValueError('Original-shadow source changed during full decoding')
    pixels.setflags(write=False)
    return pixels


def _display_background(background, shape, cancelled):
    if background.shape[:2] == tuple(shape):
        return background
    if any(a > b for a, b in zip(shape, background.shape[:2])):
        raise ValueError('Original-shadow cannot upsample a proxy extraction to full source')
    if cancelled():
        raise InterruptedError('Original-shadow display preparation cancelled')
    from PIL import Image
    result = np.empty((*shape, 3), np.float32)
    for channel in range(3):
        if cancelled():
            raise InterruptedError('Original-shadow display preparation cancelled')
        plane = Image.fromarray(background[:, :, channel], mode='F')
        try:
            small = plane.resize((shape[1], shape[0]), Image.Resampling.BOX)
            try:
                result[:, :, channel] = np.asarray(small, dtype=np.float32)
            finally:
                small.close()
        finally:
            plane.close()
    result.setflags(write=False)
    return result


def _display_transmission(background, full_output, display_background, cancelled):
    """Keep the ordinary display baseline exactly neutral, without clipping.

    The full shaded/unshaded ratio is a bounded preview approximation for asset
    backgrounds. It avoids an asset-resampling jump at zero/tiny strength. The
    authoritative full-source review/export uses full_output directly instead.
    """
    shape = display_background.shape[:2]
    base = _display_background(background, shape, cancelled)
    shaded = _display_background(full_output, shape, cancelled)
    output = np.empty_like(display_background)
    for y in range(shape[0]):
        if cancelled():
            raise InterruptedError('Original-shadow display preparation cancelled')
        b, s = base[y].astype(np.float64), shaded[y].astype(np.float64)
        ratio = np.ones(b.shape, np.float64)
        np.divide(s, b, out=ratio, where=b > 0)
        if (not np.isfinite(ratio).all() or np.any(ratio < 0) or np.any(ratio > 1)
                or np.any((b == 0) & (s != 0))):
            raise ValueError('Original-shadow display transmission invalid; no clipping fallback')
        output[y] = (display_background[y].astype(np.float64) * ratio).astype(np.float32)
    output.setflags(write=False)
    return output, _hash(base, cancelled), _hash(shaded, cancelled)


def prepare(value, pixels, reviewed_alpha, background, *, render_shape=None,
            display_background=None, cancelled=lambda: False):
    if not active(value):
        return background, None
    from . import id_background_state as I, original_shadow_native as N, original_shadow_state as S
    value = I.check(value)
    intent = I.original_shadow_of(value)
    before = source_identity(pixels, value['source'], cancelled=cancelled)
    shape = tuple(pixels.shape[:2])
    N._validate(background, (*shape, 3), 'full-source replacement background', cancelled)
    if render_shape is None:
        render_shape = shape
    if (type(render_shape) not in (tuple, list) or len(render_shape) != 2
            or any(type(v) is not int or v < 1 for v in render_shape)):
        raise ValueError('Original-shadow display extent is invalid')
    if display_background is None:
        display_background = background if tuple(render_shape) == shape else _display_background(background, render_shape, cancelled)
    N._validate(display_background, (*render_shape, 3), 'display replacement background', cancelled)
    display_hash = _hash(display_background, cancelled)
    N._validate(reviewed_alpha, shape, 'reviewed full-source subject alpha', cancelled)
    alpha_hash = _hash(reviewed_alpha, cancelled)
    lit = S.raster(intent['lit_floor'], shape, source=value['source'], full_source=True, cancelled=cancelled)
    retained = S.raster(intent['retention'], shape, source=value['source'], full_source=True, cancelled=cancelled)
    lit_hash, retention_hash = _hash(lit, cancelled), _hash(retained, cancelled)
    linear = linear_source(pixels, cancelled=cancelled)
    linear_hash = _hash(linear, cancelled)
    opacity = N.prepare(linear, reviewed_alpha, lit, retained, cancelled=cancelled)
    opacity_hash = _hash(opacity, cancelled)
    bg_hash = _hash(background, cancelled)
    full_output = N.apply(background, opacity, strength=intent['strength'] / 100., blend=intent['blend'], cancelled=cancelled)
    full_output_hash = _hash(full_output, cancelled)
    if tuple(render_shape) == shape:
        output, reduced_base_hash, reduced_shaded_hash = full_output, bg_hash, full_output_hash
    else:
        output, reduced_base_hash, reduced_shaded_hash = _display_transmission(background, full_output, display_background, cancelled)
    if (source_identity(pixels, value['source'], cancelled=cancelled) != before
            or _hash(reviewed_alpha, cancelled) != alpha_hash or _hash(linear, cancelled) != linear_hash
            or _hash(lit, cancelled) != lit_hash or _hash(retained, cancelled) != retention_hash
            or _hash(background, cancelled) != bg_hash or _hash(display_background, cancelled) != display_hash):
        raise ValueError('Original-shadow source, reviewed alpha, masks or background changed during preparation')
    proof = {'version': 1, 'algorithm': intent['algorithm'], 'estimator': N.ESTIMATOR, 'encoding': N.ENCODING,
             **before, 'render_shape': list(output.shape), 'linear_sha256': linear_hash,
             'reviewed_alpha_sha256': alpha_hash, 'lit_floor_sha256': lit_hash,
             'retention_sha256': retention_hash, 'opacity_sha256': opacity_hash,
             'recipe_sha256': recipe_digest(value), 'full_background_sha256': full_output_hash,
             'background_input_sha256': bg_hash, 'display_background_sha256': display_hash,
             'reduced_background_sha256': reduced_base_hash, 'reduced_shaded_sha256': reduced_shaded_hash,
             'background_sha256': _hash(output, cancelled)}
    check_source_proof(proof, output.shape[:2], value['source'], value)
    return output, proof
