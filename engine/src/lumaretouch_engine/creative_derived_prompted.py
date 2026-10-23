"""Shared immutable SAM model input for derived local-mask operands.

The arm input bridge already defines the explicit opaque SDR float-to-RGB8
model-only transform. Reusing it does not change full float rendering, source
identity, or the ordinary original RGB8/RGB16 decode contract.
"""
from copy import deepcopy
from hashlib import sha256
from . import creative_derived_arm_input as A


def capture(engine):
    return A.capture(engine)


def from_pixels(source,pixels):
    import numpy as np
    value=np.asarray(pixels)
    if value.dtype!=np.float32 or value.shape!=(source['height'],source['width'],3):
        raise ValueError('Derived prompted replay requires the actual full float source')
    image,digest=A.inference_image(value);data=image.tobytes(order='C')
    packet={'descriptor':{'version':1,'source':deepcopy(source),'transform':A.TRANSFORM,
        'width':int(image.shape[1]),'height':int(image.shape[0]),
        'bytes_sha256':sha256(data).hexdigest(),'input_sha256':digest},'pixels':data}
    validate(packet,source)
    return packet


def validate(packet,source):
    if type(packet) is not dict or set(packet)!={'descriptor','pixels'}:
        raise ValueError('Prompted derived input requires immutable owned bytes')
    return A.decode(packet['descriptor'],packet['pixels'],source)


def cache_identity(packet,source):
    validate(packet,source)
    value=packet['descriptor']
    return ('derived-model-input',source['sha256'],source['width'],source['height'],
            value['transform'],value['bytes_sha256'],value['input_sha256'])


def verify_result(result,source,packet):
    if type(result) is not dict or result.get('source')!=source:
        raise ValueError('Prompted worker result belongs to another source')
    if packet is not None:
        validate(packet,source);descriptor=packet['descriptor']
        if result.get('input_sha256')!=descriptor['input_sha256'] or result.get('inference_size')!=[descriptor['width'],descriptor['height']]:
            raise ValueError('Prompted worker did not consume the exact immutable model input')
