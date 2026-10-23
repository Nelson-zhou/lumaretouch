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
        if picture.format not in ('JPEG', 'PNG', 'TIFF', 'BMP'):
            raise ValueError('文件内容不是支持的 JPG/PNG/TIFF/BMP 天空素材')
        _refuse_multipage(picture, path)
        w, h = picture.size
        if w * h > S.MAX_ASSET_PIXELS or max(w, h) >= 32767:
            raise ValueError('天空素材超过 3200 万像素或 OpenCV 坐标预算')
        bits = _source_bits(picture)
        png_header = None
        if picture.format == 'PNG':
            # RGB16 PNG is exposed as RGB8 by Pillow; IHDR, not the suffix or
            # Pillow mode, decides whether the genuine uint16 codec is needed.
            with open(path, 'rb') as stream:
                png_header = stream.read(33)
            if (len(png_header) != 33 or png_header[:8] != b'\x89PNG\r\n\x1a\n'
                    or png_header[8:16] != b'\x00\x00\x00\rIHDR'
                    or int.from_bytes(png_header[16:20], 'big') != w
                    or int.from_bytes(png_header[20:24], 'big') != h
                    or png_header[24] not in (1, 2, 4, 8, 16)):
                raise ValueError('PNG 天空素材文件头、位深或尺寸无效')
            bits = png_header[24]
        png16 = png_header is not None and bits == 16
        # Decode + color conversion + two float buffers, plus the bounded PNG
        # snapshot. The sky asset budget remains independent of ID backgrounds.
        snapshot_bytes = before[2] if png16 else 0
        if w * h * 64 + snapshot_bytes + 32 * 1024**2 > max(0, available_estimate() - 256 * 1024**2) * .65:
            raise ValueError('读取天空素材的内存不足；不会缩小素材冒充原件')
        if not png16 and 'A' in picture.getbands() and picture.getchannel('A').getextrema() != (255, 255):
            raise ValueError('天空素材包含透明像素，请选择完整不透明的天空照片')
        if 'transparency' in picture.info:
            raise ValueError('天空素材包含透明色，请先提供不透明天空照片')
        source_icc = bytes(picture.info['icc_profile']) if picture.info.get('icc_profile') else None
        orientation = int(picture.getexif().get(274, 1) or 1)
    if png16:
        pixels = _read_png16(path, png_header, (h, w), digest, source_icc, orientation, cancelled)
        src_w, src_h = (h, w) if orientation in (5, 6, 7, 8) else (w, h)
        src_bits = bits
    else:
        # Preserve the established JPEG/BMP/PNG8/RGB16 TIFF decoder and ICC path.
        decoded = load_full(path, max_px=S.MAX_ASSET_PIXELS, want_bits=16 if bits > 8 else 8)
        pixels = decoded.rgb
        src_w, src_h, src_bits, source_icc = decoded.src_w, decoded.src_h, decoded.src_bits, decoded.source_icc
        if pixels.dtype == np.uint16 and source_icc:
            from .color16 import convert_rgb16
            from .export import _srgb_bytes
            pixels = convert_rgb16(pixels, source_icc, _srgb_bytes())
    if pixels.dtype not in (np.uint8, np.uint16) or pixels.shape != (src_h, src_w, 3):
        raise ValueError('天空素材解码没有保留有效 RGB 像素')
    if src_bits > 8 and pixels.dtype != np.uint16:
        raise ValueError('高位深天空素材没有真正 RGB16 解码；不能退回 RGB8')
    binding = S.asset({'path': path, 'sha256': digest, 'width': src_w, 'height': src_h,
                       'bits': 16 if pixels.dtype == np.uint16 else 8, 'working_color': 'encoded-srgb',
                       'icc_sha256': sha256(source_icc).hexdigest() if source_icc else None})
    if expected is not None and binding != expected:
        raise ValueError('天空素材尺寸、位深或颜色档身份改变')
    if cancelled():
        raise InterruptedError('天空素材读取已取消')
    if B.file_stamp(path) != before:
        raise ValueError('天空素材读取过程中发生变化')
    pixels.setflags(write=False)
    return SkyAsset(binding, pixels, before)


def _read_png16(path, header, shape, digest, source_icc, orientation, cancelled):
    """Opaque RGB16 adapter, reusing the ID-background codec/ICC contracts.

    Do not call the full ID-background engine: its 10 MB, alpha-preserving,
    linear-float asset representation is not the sky asset contract.
    """
    from .id_background_assets import _orient, _colour_manage
    if header[25] not in (2, 6):
        raise ValueError('16-bit PNG 天空素材要求 RGB/RGBA，不会把其它通道静默降为 RGB8')
    if orientation not in range(1, 9):
        raise ValueError('天空素材方向标签无效')
    if cancelled():
        raise InterruptedError('天空素材读取已取消')
    with open(path, 'rb') as stream:
        content = stream.read(S.MAX_ASSET_BYTES + 1)
    if (not 0 < len(content) <= S.MAX_ASSET_BYTES or content[:33] != header
            or sha256(content).hexdigest() != digest):
        raise ValueError('PNG 天空素材读取过程中内容改变或超过 64 MiB')
    # Same pinned imagecodecs/libpng path as ID backgrounds. No Pillow RGB8
    # staging, integer expansion, clipping, or fallback on codec/ICC failure.
    import imagecodecs
    pixels = imagecodecs.png_decode(content)
    channels = 4 if header[25] == 6 else 3
    if pixels.dtype != np.uint16 or pixels.shape != (*shape, channels):
        raise ValueError('PNG 天空素材解码没有保留文件头声明的 RGB16 位深、尺寸或通道')
    if channels == 4:
        # 65534 must not pass as opaque merely because Pillow rounds it to 255.
        if np.any(pixels[:, :, 3] != 65535):
            raise ValueError('天空素材包含透明像素，请选择完整不透明的天空照片')
        pixels = pixels[:, :, :3]
    if cancelled():
        raise InterruptedError('天空素材读取已取消')
    return _colour_manage(_orient(pixels, orientation), source_icc)


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
