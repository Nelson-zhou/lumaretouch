"""Owned OneFormer input from the canonical full-resolution SDR working RGB.

Only the canonical source owner may call ``from_pixels`` after resolving the
immutable creative asset. A caller-supplied source ID alone cannot authenticate
arbitrary pixels. This packet is ephemeral transport, not retained image data
or an alternative export source. The original uint8 bilinear transform is
shared with the file decoder route and is applied exactly once.
"""
from copy import deepcopy
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import stat

from . import manifest as M, state as S

VERSION = 1
MAX_INPUT_BYTES = M.MAX_MASK_PIXELS * 3
_FILE = 'input.rgb'
_KEYS = {'version', 'contract', 'source', 'canonical_sha256',
         'input_size', 'input_sha256', 'pixels'}


def target_size(width, height):
    """The existing processor policy, including floor rounding and enlargement."""
    if (any(type(n) is not int or not 1 <= n <= 65536 for n in (width, height))
            or width * height > 64_000_000):
        raise ValueError('自动选区源照片尺寸超出预算')
    scale = min(512 / min(height, width), 1024 / max(height, width))
    return max(1, int(width * scale)), max(1, int(height * scale))


def input_digest(raw, size):
    """Preserve the existing OneFormer byte identity, not the SAM contract."""
    digest = hashlib.sha256(M.CONTRACT.encode() + b'\0' + str(tuple(size)).encode())
    digest.update(raw)
    return digest.hexdigest()


def prepare_rgb8(rgb):
    """One bounded bilinear resize, shared by original and canonical inputs."""
    import numpy as np
    from PIL import Image
    if not isinstance(rgb, np.ndarray) or rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError('自动选区预处理需要 RGB8 源图')
    target = target_size(int(rgb.shape[1]), int(rgb.shape[0]))
    if target[0] * target[1] > M.MAX_MASK_PIXELS:
        raise ValueError('自动选区输入超过明确的推理预算')
    with Image.fromarray(rgb) as original:
        with original.resize(target, Image.Resampling.BILINEAR) as resized:
            pixels = np.asarray(resized, dtype=np.uint8).copy()
    return pixels, input_digest(memoryview(pixels).cast('B'), target)


def from_pixels(pixels, source):
    """Build after canonical resolution; reject proxies, alpha and signed/HDR RGB.

    Quantize a separate full-source analysis buffer before the existing resize.
    Never resize float channels first, reuse a display proxy, or clip HDR into
    SDR. The exact full float source hash remains distinct from model pixels.
    """
    import numpy as np
    source = S.source(source)
    if (not isinstance(pixels, np.ndarray) or pixels.dtype != np.float32
            or pixels.shape != (source['height'], source['width'], 3)):
        raise ValueError('自动选区需要完整的规范 float32 工作 RGB，不能使用显示代理图')
    canonical = hashlib.sha256()
    rgb = np.empty(pixels.shape, dtype=np.uint8)
    for y in range(0, source['height'], 128):
        # The hash and quantization must inspect the same owned bounded block.
        block = np.array(pixels[y:y + 128], dtype='<f4', copy=True, order='C')
        if not np.isfinite(block).all() or np.any(block < 0) or np.any(block > 1):
            raise ValueError('自动选区仅接受 SDR 规范源；不会裁切 HDR 或非有限值')
        # Explicit little-endian identity across native host byte orders.
        canonical.update(memoryview(block).cast('B'))
        rgb[y:y + 128] = np.rint(block * np.float32(255)).astype(np.uint8)
    prepared, digest = prepare_rgb8(rgb)
    return check({'version': VERSION, 'contract': M.CONTRACT, 'source': source,
                  'canonical_sha256': canonical.hexdigest(),
                  'input_size': [int(prepared.shape[1]), int(prepared.shape[0])],
                  'input_sha256': digest, 'pixels': prepared.tobytes(order='C')})


build = from_pixels


def _metadata(value, source=None):
    if (type(value) is not dict or set(value) != _KEYS - {'pixels'}
            or type(value['version']) is not int or value['version'] != VERSION
            or value['contract'] != M.CONTRACT):
        raise ValueError('自动选区不可变输入格式或变换版本无效')
    binding = S.source(value['source'])
    if source is not None and binding != S.source(source):
        raise ValueError('自动选区输入属于另一个规范源')
    S.sha(value['canonical_sha256']); S.sha(value['input_sha256'])
    size = value['input_size']
    if (type(size) is not list or len(size) != 2
            or any(type(n) is not int or not 1 <= n <= 1024 for n in size)
            or size != list(target_size(binding['width'], binding['height']))
            or size[0] * size[1] > M.MAX_MASK_PIXELS):
        raise ValueError('自动选区输入没有保持固定的完整源变换尺寸')
    return deepcopy(value)


def check(packet, source=None):
    """Validate actual immutable bytes as well as all source/transform fields."""
    if type(packet) is not dict or set(packet) != _KEYS:
        raise ValueError('自动选区缺少完整的不可变输入包')
    value = _metadata({key: packet[key] for key in _KEYS - {'pixels'}}, source)
    raw = packet['pixels']
    if (type(raw) is not bytes or len(raw) > MAX_INPUT_BYTES
            or len(raw) != value['input_size'][0] * value['input_size'][1] * 3
            or input_digest(raw, value['input_size']) != value['input_sha256']):
        raise ValueError('自动选区输入字节、尺寸或校验身份已变化')
    return {**value, 'pixels': raw}


def metadata(packet):
    value = check(packet)
    del value['pixels']
    return value


def key(packet):
    """A hashable cache key includes verified bytes, not merely a source label."""
    return hashlib.sha256(json.dumps(metadata(packet), sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def array(packet):
    """A bounded owned model array; no re-quantization or second resize."""
    import numpy as np
    packet = check(packet)
    width, height = packet['input_size']
    return np.frombuffer(packet['pixels'], dtype=np.uint8).reshape(height, width, 3).copy()


def write_packet(directory, packet):
    packet = check(packet)
    with (Path(directory) / _FILE).open('xb') as stream:
        stream.write(packet['pixels'])
    return metadata(packet)


def read_regular_bytes(path, limit):
    """No-follow, nonblocking, bounded reads from the job's owned directory."""
    if type(limit) is not int or not 1 <= limit <= M.MAX_RESULT_BYTES:
        raise ValueError('自动选区传输读取预算无效')
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    with os.fdopen(os.open(path, flags), 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ValueError('自动选区传输文件格式或大小无效')
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        if (len(raw) != before.st_size or len(raw) > limit
                or (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            raise ValueError('自动选区传输文件在读取期间发生变化')
    return raw


def read_packet(directory, value, source=None):
    """Read one fixed, bounded raw file, never a caller path or pickle/archive."""
    value = _metadata(value, source)
    expected = value['input_size'][0] * value['input_size'][1] * 3
    raw = read_regular_bytes(Path(directory) / _FILE, expected)
    return check({**value, 'pixels': raw}, source)


def validate_result(packet, result):
    """Bind the returned inference identity and displayed locator to real bytes."""
    from PIL import Image
    packet = check(packet)
    if type(result) is not dict:
        raise ValueError('自动选区结果格式无效')
    returned_source = S.source(result.get('source'))
    returned_metadata = _metadata(result.get('_immutable_input'), packet['source'])
    size = result.get('input_size')
    if (returned_source != packet['source']
            or type(size) is not list or any(type(n) is not int for n in size)
            or size != packet['input_size']
            or result.get('input_sha256') != packet['input_sha256']
            or returned_metadata != metadata(packet)):
        raise ValueError('自动选区结果不属于送入模型的规范输入')
    image = result.get('source_image')
    prefix = 'data:image/png;base64,'
    if (type(image) is not str or not image.startswith(prefix)
            or len(image) > 4 * (MAX_INPUT_BYTES + 65536) // 3 + len(prefix) + 4):
        raise ValueError('自动选区显示输入无效或超出预算')
    raw = base64.b64decode(image[len(prefix):], validate=True)
    if len(raw) > MAX_INPUT_BYTES + 65536:
        raise ValueError('自动选区显示输入超过预算')
    with Image.open(io.BytesIO(raw)) as decoded:
        if (decoded.format != 'PNG' or decoded.mode != 'RGB'
                or list(decoded.size) != packet['input_size'] or getattr(decoded, 'n_frames', 1) != 1
                or decoded.tobytes() != packet['pixels']):
            raise ValueError('自动选区定位图不是实际送入模型的输入像素')
    return result
