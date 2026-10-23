"""Immutable model-only arm input; never substitutes for full float render pixels."""
from hashlib import sha256
from copy import deepcopy
import json

TRANSFORM = 'opaque-sdr-working-srgb-f32-round-half-up-rgb8-lanczos2048-v1'
MAX_BYTES = 2048 * 2048 * 3


def _packet_identity(packet,source):
    """Pin descriptor and immutable bytes separately from their mutable cache.

    Self-consistent hashes inside a replaced descriptor cannot prove that its
    pixels were created by the canonical full-source transform. This digest is
    frozen only at that creation boundary and checked before every cache reuse.
    """
    if type(packet) is not dict or set(packet)!={'descriptor','pixels'}:
        raise ValueError('Immutable arm model-input cache packet is malformed')
    decode(packet['descriptor'],packet['pixels'],source)
    digest=sha256(b'lumaretouch-derived-arm-model-input-v1\0')
    digest.update(json.dumps(packet['descriptor'],sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8'))
    digest.update(b'\0');digest.update(packet['pixels'])
    return digest.hexdigest()


def inference_image(pixels):
    import numpy as np
    from . import prompted_mask_source as P
    value = np.asarray(pixels)
    if value.dtype != np.float32:
        return P.inference_image(value)
    if value.ndim != 3 or value.shape[2] != 3 or min(value.shape[:2]) < 1 or value.shape[0]*value.shape[1] > P.MAX_PIXELS:
        raise ValueError('Derived arm input requires bounded full working-sRGB RGB')
    rgb = np.empty(value.shape, dtype=np.uint8)
    for y in range(0, value.shape[0], 128):
        block = value[y:y+128]
        if not np.isfinite(block).all() or (block < 0).any() or (block > 1).any():
            raise ValueError('Derived arm model input refuses nonfinite or HDR values; no clipping')
        rgb[y:y+128] = np.floor(block * np.float32(255) + np.float32(.5)).astype(np.uint8)
    return P.inference_image(rgb)


def capture(engine):
    from . import creative_derived_source as D, creative_document_base as B
    from .creative_document_host import memory_budget
    record = D.record(engine)
    if record is None:
        return None
    source = D.binding(engine)
    key = (record['id'], TRANSFORM)
    cache = engine.__dict__.get('_creative_arm_model_input')
    if cache is not None:
        if (type(cache) is not tuple or len(cache)!=3 or type(cache[0]) is not tuple
                or len(cache[0])!=2 or type(cache[2]) is not str or len(cache[2])!=64
                or any(c not in '0123456789abcdef' for c in cache[2])):
            raise ValueError('Immutable arm model-input cache lacks its captured identity')
        if cache[0] == key:
            packet=cache[1]
            if _packet_identity(packet,source)!=cache[2]:
                raise ValueError('Immutable arm model-input cache changed after canonical capture')
            D.verify(source,engine)
            return {'descriptor':deepcopy(packet['descriptor']),'pixels':packet['pixels']}
    budget=memory_budget()
    # Full f32 conversion, RGB8 quantization/copy and native/resize staging.
    if record['width']*record['height']*32 + 16_777_216 > budget:
        raise ValueError('Insufficient bounded memory for immutable derived arm model input')
    # export_source explicitly refuses alpha/HDR and preserves full f32 source.
    pixels = B.export_source(record, max_bytes=budget)
    image, digest = inference_image(pixels)
    data = image.tobytes(order='C')
    descriptor = {'version':1, 'source':source, 'transform':TRANSFORM,
                  'width':int(image.shape[1]), 'height':int(image.shape[0]),
                  'bytes_sha256':sha256(data).hexdigest(), 'input_sha256':digest}
    D.verify(source, engine)
    packet={'descriptor':descriptor, 'pixels':data}
    engine._creative_arm_model_input=(key,packet,_packet_identity(packet,source))
    return {'descriptor':deepcopy(descriptor), 'pixels':data}


def check_descriptor(value, source):
    from . import body_pose_evidence as E
    if type(value) is not dict or set(value) != {'version','source','transform','width','height','bytes_sha256','input_sha256'}:
        raise ValueError('Invalid immutable arm model-input descriptor')
    expected = {k:source[k] for k in ('sha256','width','height')}
    if type(value['version']) is not int or value['version'] != 1 or value['source'] != expected or value['transform'] != TRANSFORM:
        raise ValueError('Arm model input belongs to another effective source or transform')
    E.digest(expected['sha256']); E.digest(value['bytes_sha256']); E.digest(value['input_sha256'])
    if any(type(expected[k]) is not int or expected[k] < 1 for k in ('width','height')) or expected['width']*expected['height'] > 64_000_000:
        raise ValueError('Derived arm source exceeds its dimensional budget')
    ratio = min(1., 2048 / max(expected['width'], expected['height']))
    if any(type(value[k]) is not int for k in ('width','height')) or [value['width'],value['height']] != [max(1,round(expected['width']*ratio)),max(1,round(expected['height']*ratio))]:
        raise ValueError('Arm model-input dimensions differ from the pinned whole-source transform')
    return value


def decode(descriptor, data, source):
    import numpy as np
    from . import prompted_mask_source as P
    value = check_descriptor(descriptor, source)
    if type(data) is not bytes or len(data) != value['width']*value['height']*3 or len(data) > MAX_BYTES or sha256(data).hexdigest() != value['bytes_sha256']:
        raise ValueError('Immutable arm model-input bytes changed')
    image = np.frombuffer(data, np.uint8).reshape(value['height'],value['width'],3)
    _, digest = P.inference_image(image)
    if digest != value['input_sha256']:
        raise ValueError('Arm model-input contract hash changed')
    return image
