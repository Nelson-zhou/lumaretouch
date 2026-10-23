"""Bounded original PNG16 adapter around the already pinned imagecodecs/libpng.

No PNG pixel/filter/interlace algorithm lives here. Container checks precede the
native decoder, and ancillary metadata is kept out of its pixel-only snapshot.
The RGB photo editor accepts only opaque SDR sources, not silently flattened
alpha, APNG's first frame, or HDR relabelled as sRGB.

Colour precedence and chunk layouts: https://www.w3.org/TR/png-3/
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import stat
import struct
import time
import zlib

import numpy as np

SIGNATURE = b'\x89PNG\r\n\x1a\n'
MAX_SOURCE_BYTES = 1024 * 1024 * 1024
MAX_SOURCE_PIXELS = 120_000_000
MAX_METADATA_BYTES = 16 * 1024 * 1024
MAX_EXIF_BYTES = 1024 * 1024
MAX_CHUNKS = 65_536
_SRGB_CHRM = (31270, 32900, 64000, 33000, 30000, 60000, 15000, 6000)
_COLOUR_CHUNKS = {b'iCCP', b'sRGB', b'gAMA', b'cHRM', b'cICP', b'mDCV', b'cLLI'}


@dataclass(frozen=True)
class PNGHeader:
    width: int
    height: int
    bits: int
    color_type: int
    interlace: int


@dataclass(frozen=True)
class PNG16Source:
    rgb: np.ndarray
    source_icc: bytes | None
    source_exif: bytes | None
    orientation: int
    colour_hint: str
    open_ms: float
    decode_ms: float
    orient_ms: float
    total_ms: float


def _header(data: bytes) -> PNGHeader | None:
    if data[:8] != SIGNATURE:
        return None
    if (len(data) != 33 or data[8:16] != b'\0\0\0\rIHDR'
            or zlib.crc32(data[12:29]) & 0xffffffff != int.from_bytes(data[29:33], 'big')):
        raise ValueError('PNG header / IHDR 长度或 CRC 无效')
    w, h, bits, kind, compression, filtering, interlace = struct.unpack('>IIBBBBB', data[16:29])
    depths = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
    if (not 0 < w < 2**31 or not 0 < h < 2**31 or bits not in depths.get(kind, ())
            or compression != 0 or filtering != 0 or interlace not in (0, 1)):
        raise ValueError('PNG header 尺寸、位深、通道或压缩方式无效')
    return PNGHeader(w, h, bits, kind, interlace)


def source_header(path) -> PNGHeader | None:
    """Read only the bounded IHDR, independently of filename or Pillow RGB mode.

    This is a precision probe, not full-file approval. The load below separately
    enforces the byte/pixel/metadata budgets and refuses unsupported variants.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f'图片不存在或不是普通文件: {path}')
    with open(path, 'rb') as stream:
        return _header(stream.read(33))


def _inflate_icc(data: bytes) -> bytes:
    name, separator, rest = data.partition(b'\0')
    if (not separator or not 1 <= len(name) <= 79 or len(rest) < 2 or rest[0] != 0
            or name.startswith(b' ') or name.endswith(b' ') or b'  ' in name
            or any(not (32 <= value <= 126 or 161 <= value <= 255) for value in name)):
        raise ValueError('PNG iCCP 名称或压缩方式无效')
    try:
        inflater = zlib.decompressobj()
        profile = inflater.decompress(rest[1:], MAX_METADATA_BYTES + 1)
    except zlib.error as exc:
        raise ValueError('PNG ICC 压缩数据无效') from exc
    if (not profile or len(profile) > MAX_METADATA_BYTES or inflater.unconsumed_tail
            or not inflater.eof or inflater.unused_data):
        raise ValueError('PNG ICC 元数据超过预算、截断或包含多条压缩流')
    # Check bounded ICC container identity even on source-code passthrough. The
    # existing LittleCMS path owns actual transform validity at conversion time.
    if (len(profile) < 132 or int.from_bytes(profile[:4], 'big') != len(profile)
            or profile[36:40] != b'acsp' or profile[16:20] != b'RGB '
            or profile[20:24] not in (b'XYZ ', b'Lab ')):
        raise ValueError('PNG ICC header 无效或不是受支持的 RGB profile')
    tags = int.from_bytes(profile[128:132], 'big')
    table_end = 132 + 12 * tags
    if tags > 4096 or table_end > len(profile):
        raise ValueError('PNG ICC 标签表无效或超过预算')
    for entry in range(132, table_end, 12):
        offset, size = struct.unpack('>II', profile[entry + 4:entry + 12])
        if offset < table_end or offset % 4 or size < 8 or offset + size > len(profile):
            raise ValueError('PNG ICC 标签范围无效')
    return profile


def _exif_metadata(data: bytes | None) -> tuple[bytes | None, int]:
    if data is None:
        return None, 1
    if not 8 <= len(data) <= MAX_EXIF_BYTES or data[:4] not in (b'II*\0', b'MM\0*'):
        raise ValueError('PNG EXIF 元数据无效或超过预算')
    from PIL import Image
    source_exif = b'Exif\0\0' + data
    try:
        exif = Image.Exif()
        exif.load(source_exif)
        orientation = exif.get(274, 1)
        if type(orientation) is not int or orientation not in range(1, 9):
            raise ValueError('PNG EXIF orientation 无效')
    except (OSError, SyntaxError, ValueError, TypeError, OverflowError, struct.error) as exc:
        raise ValueError('PNG EXIF 元数据或 orientation 无效') from exc
    return source_exif, orientation


def _colour_metadata(chunks: dict[bytes, bytes], kind: int) -> tuple[bytes | None, str]:
    """Keep source ICC, but never ignore higher-priority unsupported colour data."""
    if b'mDCV' in chunks or b'cLLI' in chunks:
        raise ValueError('PNG HDR/显示亮度元数据暂不支持；不会静默套用 SDR sRGB')
    if b'cICP' in chunks:
        if chunks[b'cICP'] != b'\x01\x0d\x00\x01':
            raise ValueError('PNG cICP HDR、非 sRGB 或窄范围颜色编码暂不支持')
        # cICP outranks iCCP. The current source-ICC contract cannot safely keep
        # a lower-priority profile and later apply it as the effective encoding.
        if b'iCCP' in chunks:
            raise ValueError('PNG 同时含 cICP 与 ICC；当前源 ICC 通路不能忽略颜色优先级')
    if b'sRGB' in chunks and (len(chunks[b'sRGB']) != 1 or chunks[b'sRGB'][0] > 3):
        raise ValueError('PNG sRGB 元数据无效')
    if b'gAMA' in chunks and (len(chunks[b'gAMA']) != 4 or int.from_bytes(chunks[b'gAMA'], 'big') == 0):
        raise ValueError('PNG gAMA 元数据无效')
    if b'cHRM' in chunks and len(chunks[b'cHRM']) != 32:
        raise ValueError('PNG cHRM 元数据无效')
    if b'iCCP' in chunks:
        if kind in (0, 4):
            raise ValueError('16-bit 灰度 PNG ICC 转换暂不支持；不会当作 RGB ICC 或静默降位')
        # ICC takes precedence over optional legacy gAMA/cHRM/sRGB chunks.
        return _inflate_icc(chunks[b'iCCP']), 'icc'
    if b'cICP' in chunks or b'sRGB' in chunks:
        return None, 'srgb'
    if b'gAMA' in chunks and int.from_bytes(chunks[b'gAMA'], 'big') != 45455:
        raise ValueError('PNG 无 ICC 且 gAMA 不是常规 sRGB 近似；不猜测工作颜色空间')
    if b'cHRM' in chunks and struct.unpack('>8I', chunks[b'cHRM']) != _SRGB_CHRM:
        raise ValueError('PNG 无 ICC 且 cHRM 不是 sRGB 色度；不猜测工作颜色空间')
    return None, 'assumed-srgb'


def _snapshot(path, max_px: int):
    """Freeze one bounded regular file, then retain only pixel-bearing chunks."""
    limit = min(int(max_px), MAX_SOURCE_PIXELS)
    if limit < 1:
        raise ValueError('PNG16 像素预算必须为正数')
    with open(path, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_SOURCE_BYTES:
            raise ValueError('PNG16 原件不是普通文件或超过 1 GiB 字节预算')
        header_bytes = stream.read(33)
        header = _header(header_bytes)
        if header is None or header.bits != 16:
            raise ValueError('需要真实 16-bit PNG 原件；不能将 8-bit 补零冒充')
        if header.width * header.height > limit:
            raise ValueError(f'PNG16 原件 {header.width}×{header.height} 超过 {limit} 像素预算')
        from .cpu_memory_budget import available_estimate
        # Two compressed snapshots/read assembly plus native RGBA16, opacity
        # predicates, grayscale expansion, orientation, ICC and display-plane
        # staging. This is conservative admission, not an allocation guarantee.
        required = 2 * before.st_size + header.width * header.height * 64 + 64 * 1024**2
        if required > max(0, available_estimate() - 256 * 1024**2) * .65:
            raise ValueError('PNG16 完整解码内存预算不足；不会以 RGB8 或缩小原件替代')
        content = header_bytes + stream.read(before.st_size - len(header_bytes) + 1)
        after = os.fstat(stream.fileno())
    stamp = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
    if len(content) != before.st_size or stamp(before) != stamp(after) or stamp(after) != stamp(os.stat(path)):
        raise ValueError('PNG16 原件在读取期间发生变化')
    view = memoryview(content)
    kept = [view[:33]]
    metadata: dict[bytes, bytes] = {}
    singleton = {b'PLTE', b'tRNS', b'eXIf'} | _COLOUR_CHUNKS
    seen = set()
    offset, count, meta_bytes = 33, 1, 0
    idat_seen = idat_closed = ended = False
    transparency = None
    while offset < len(content):
        count += 1
        if count > MAX_CHUNKS or len(content) - offset < 12:
            raise ValueError('PNG 块数量超过预算或块头截断')
        length = int.from_bytes(view[offset:offset + 4], 'big')
        kind = bytes(view[offset + 4:offset + 8])
        end = offset + 12 + length
        if length >= 2**31 or end > len(content) or any(not (65 <= c <= 90 or 97 <= c <= 122) for c in kind):
            raise ValueError('PNG 块类型、长度或数据无效')
        payload = view[offset + 8:end - 4]
        crc = zlib.crc32(payload, zlib.crc32(kind)) & 0xffffffff
        if crc != int.from_bytes(view[end - 4:end], 'big'):
            raise ValueError('PNG 块 CRC 无效')
        if kind in (b'acTL', b'fcTL', b'fdAT'):
            raise ValueError('APNG 动画/多帧容器不支持；不会只取第 0 帧')
        if kind == b'IHDR' or kind[2] & 32 or (not kind[0] & 32 and kind not in (b'PLTE', b'IDAT', b'IEND')):
            raise ValueError('PNG 含重复 IHDR、无效保留位或未知关键块')
        if kind != b'IDAT':
            meta_bytes += length + 12
            if meta_bytes > MAX_METADATA_BYTES:
                raise ValueError('PNG 元数据超过 16 MiB 预算')
            if idat_seen:
                idat_closed = True
        elif idat_closed:
            raise ValueError('PNG IDAT 块不连续')
        if kind in singleton:
            if kind in seen:
                raise ValueError('PNG 元数据或透明度块重复')
            seen.add(kind)
        if kind in _COLOUR_CHUNKS:
            if idat_seen or b'PLTE' in seen:
                raise ValueError('PNG 颜色元数据必须位于 PLTE/IDAT 之前')
            metadata[kind] = bytes(payload)
        elif kind == b'eXIf':
            if length > MAX_EXIF_BYTES:
                raise ValueError('PNG EXIF 元数据超过 1 MiB 预算')
            metadata[kind] = bytes(payload)
        elif kind == b'PLTE':
            if idat_seen or header.color_type in (0, 4) or not 0 < length <= 768 or length % 3:
                raise ValueError('PNG 调色板布局或位置无效')
            kept.append(view[offset:end])
        elif kind == b'tRNS':
            if idat_seen or header.color_type not in (0, 2) or length != (2 if header.color_type == 0 else 6):
                raise ValueError('PNG16 tRNS 透明度布局或位置无效')
            transparency = tuple(int.from_bytes(payload[i:i + 2], 'big') for i in range(0, length, 2))
            kept.append(view[offset:end])
        elif kind == b'IDAT':
            idat_seen = True
            kept.append(view[offset:end])
        elif kind == b'IEND':
            if length != 0 or not idat_seen or end != len(content):
                raise ValueError('PNG IEND 无效、缺少像素或含尾随数据/其它图像')
            kept.append(view[offset:end])
            ended = True
        offset = end
    if not ended:
        raise ValueError('PNG 缺少完整 IEND')
    icc, colour_hint = _colour_metadata(metadata, header.color_type)
    exif, orientation = _exif_metadata(metadata.get(b'eXIf'))
    # Compressed text and other unused ancillary chunks never reach libpng.
    # Their original bytes were bounded/CRC-checked, but never decompressed.
    pixels_only = b''.join(kept)
    return header, pixels_only, transparency, icc, exif, orientation, colour_hint


def _orient(array: np.ndarray, orientation: int) -> np.ndarray:
    if orientation == 2: return array[:, ::-1]
    if orientation == 3: return array[::-1, ::-1]
    if orientation == 4: return array[::-1]
    if orientation == 5: return array.swapaxes(0, 1)
    if orientation == 6: return np.rot90(array, -1)
    if orientation == 7: return array.swapaxes(0, 1)[::-1, ::-1]
    if orientation == 8: return np.rot90(array, 1)
    return array


def load_opaque_rgb16(path, *, max_px: int = MAX_SOURCE_PIXELS) -> PNG16Source:
    """True native samples, exactly-once orientation, retained source encoding."""
    started = time.perf_counter()
    header, content, trns, icc, exif, orientation, colour_hint = _snapshot(path, max_px)
    opened = time.perf_counter()
    import imagecodecs
    try:
        pixels = imagecodecs.png_decode(content)
    except Exception as exc:
        raise ValueError(f'无法读取真实 16-bit PNG（imagecodecs/libpng）：{exc}') from exc
    if (not isinstance(pixels, np.ndarray) or pixels.dtype != np.uint16
            or pixels.shape[:2] != (header.height, header.width)):
        raise ValueError('PNG 解码位深或尺寸与真实 uint16 文件头不符')
    grey = header.color_type in (0, 4)
    if pixels.ndim == 2 and grey:
        pixels = pixels[:, :, None]
    native_channels = 1 if grey else 3
    expected_alpha = header.color_type in (4, 6)
    allowed = (native_channels + 1,) if expected_alpha else (
        (native_channels, native_channels + 1) if trns is not None else (native_channels,))
    if pixels.ndim != 3 or pixels.shape[2] not in allowed:
        raise ValueError('PNG16 解码通道布局与文件头不符')
    if pixels.shape[2] == native_channels + 1:
        if np.any(pixels[:, :, -1] != 65535):
            raise ValueError('PNG16 包含真实透明像素；RGB 精修不能丢弃 transparency/alpha')
        pixels = pixels[:, :, :-1]
    if trns is not None and np.any(np.all(pixels == np.asarray(trns, dtype=np.uint16), axis=2)):
        raise ValueError('PNG16 tRNS 命中真实透明像素；RGB 精修不能丢弃 transparency')
    if grey:
        pixels = np.repeat(pixels, 3, axis=2)
    decoded = time.perf_counter()
    rgb = np.ascontiguousarray(_orient(pixels, orientation))
    finished = time.perf_counter()
    return PNG16Source(rgb, icc, exif, orientation, colour_hint,
                       (opened - started) * 1000, (decoded - opened) * 1000,
                       (finished - decoded) * 1000, (finished - started) * 1000)
