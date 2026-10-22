"""Local user assets, content binding and genuine color-managed RGB8/RGB16.

No bundled/licensed stock, implicit download, model installation or remote URL.
Paths are locators; SHA-256 plus decoded geometry/ICC identity is authoritative.
"""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import os
import numpy as np
from . import sky_replacement_state as S, local_mask_state as B


@dataclass(frozen=True)
class SkyAsset:
    binding: dict
    pixels: np.ndarray
    stamp: tuple


def inspect_path(path):
    if type(path) is not str or not os.path.isabs(path) or len(path) > 4096 or '\x00' in path:
        raise ValueError('请选择本地天空素材文件')
    if Path(path).suffix.lower() not in ('.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff'):
        raise ValueError('天空素材支持 JPG、PNG、BMP 与 RGB TIFF，不接受模型或可执行文件')
    if not os.path.isfile(path) or not 0 < os.stat(path).st_size <= S.MAX_ASSET_BYTES:
        raise ValueError('天空素材缺失、不是普通文件或超过 64 MiB')
    return B.file_stamp(path)


def read(path, *, expected=None, cancelled=lambda: False):
    """Decode only after an explicit local choice. Never downcast a high-bit asset."""
    from PIL import Image
    from .decode import load_full, _source_bits, _refuse_multipage
    from .cpu_memory_budget import available_estimate
    before = inspect_path(path)
    if cancelled():
        raise InterruptedError('天空素材读取已取消')
    digest = B.source_digest(path)
    if expected is not None and (S.asset(expected)['path'] != path or expected['sha256'] != digest):
        raise ValueError('天空素材内容已变化；请重新选择，不会使用同名替代图')
    with Image.open(path) as picture:
        _refuse_multipage(picture, path)
        w, h = picture.size
        if w * h > S.MAX_ASSET_PIXELS or max(w, h) >= 32767:
            raise ValueError('天空素材超过 3200 万像素或 OpenCV 坐标预算')
        # Decode + color conversion + two float buffers have an explicit bound.
        if w * h * 64 + 32 * 1024**2 > max(0, available_estimate() - 256 * 1024**2) * .65:
            raise ValueError('读取天空素材的内存不足；不会缩小素材冒充原件')
        bits = _source_bits(picture)
        if 'A' in picture.getbands() and picture.getchannel('A').getextrema() != (255, 255):
            raise ValueError('天空素材包含透明像素，请选择完整不透明的天空照片')
        if 'transparency' in picture.info:
            raise ValueError('天空素材包含透明色，请先提供不透明天空照片')
    # Pillow can expose 16-bit RGB PNG as mode RGB without an info['bits'] key.
    # Inspect the standardized IHDR bit-depth byte before choosing the decoder.
    if Path(path).suffix.lower() == '.png':
        with open(path, 'rb') as stream:
            header = stream.read(33)
        if len(header) >= 29 and header[:8] == b'\x89PNG\r\n\x1a\n' and header[12:16] == b'IHDR':
            bits = header[24]
        if bits > 8:
            raise ValueError('16-bit PNG 天空素材暂不支持无损颜色管理，请另存为 RGB16 TIFF；不会降为 8-bit')
    decoded = load_full(path, max_px=S.MAX_ASSET_PIXELS, want_bits=16 if bits > 8 else 8)
    pixels = decoded.rgb
    if pixels.dtype not in (np.uint8, np.uint16) or pixels.shape != (decoded.src_h, decoded.src_w, 3):
        raise ValueError('天空素材解码没有保留有效 RGB 像素')
    if decoded.src_bits > 8 and pixels.dtype != np.uint16:
        raise ValueError('高位深天空素材没有真正 RGB16 解码；不能退回 RGB8')
    if pixels.dtype == np.uint16 and decoded.source_icc:
        from .color16 import convert_rgb16
        from .export import _srgb_bytes
        pixels = convert_rgb16(pixels, decoded.source_icc, _srgb_bytes())
    binding = S.asset({'path': path, 'sha256': digest, 'width': decoded.src_w, 'height': decoded.src_h,
                       'bits': 16 if pixels.dtype == np.uint16 else 8, 'working_color': 'encoded-srgb',
                       'icc_sha256': sha256(decoded.source_icc).hexdigest() if decoded.source_icc else None})
    if expected is not None and binding != expected:
        raise ValueError('天空素材尺寸、位深或颜色档身份改变')
    if cancelled():
        raise InterruptedError('天空素材读取已取消')
    if B.file_stamp(path) != before:
        raise ValueError('天空素材读取过程中发生变化')
    pixels.setflags(write=False)
    return SkyAsset(binding, pixels, before)


def verify(value):
    value = S.asset(value)
    if value is None:
        return None
    before = inspect_path(value['path'])
    if B.source_digest(value['path']) != value['sha256'] or B.file_stamp(value['path']) != before:
        raise ValueError('天空素材缺失或内容改变；请定位同一文件，或明确选择新素材')
    return before


def relink(value, path):
    """A relink may change the locator only, never silently replace content."""
    old = S.asset(value)
    if old is None:
        raise ValueError('没有需要重新定位的天空素材')
    candidate = read(path)
    if {k: v for k, v in candidate.binding.items() if k != 'path'} != {k: v for k, v in old.items() if k != 'path'}:
        raise ValueError('重新定位的天空素材与原件不同；请使用选择新素材')
    return candidate
