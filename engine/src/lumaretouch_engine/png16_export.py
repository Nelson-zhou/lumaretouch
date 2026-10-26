"""Verified opaque RGB16 PNG delivery using the pinned imagecodecs/libpng.

This is container/metadata glue, not a PNG pixel codec. The caller already owns
orientation, RGB16 rendering and source-to-target ICC conversion. No Pillow RGB8,
alpha flattening, HDR interpretation or source EXIF passthrough happens here.
Runtime/codec acceptance is AUTHORED / UNRUN until local validation.
"""
from __future__ import annotations

import os
import struct
import time
import zlib

import numpy as np

from . import png16_source as P

COMPRESSION_LEVEL = 6
_ICC_NAME = b'LumaRetouch RGB'


def _icc_chunk(target_icc: bytes | None) -> tuple[bytes | None, bytes]:
    """Validate the same bounded RGB ICC container that readback will accept."""
    if target_icc is None:
        return None, b''
    if not isinstance(target_icc, (bytes, bytearray)):
        raise ValueError('PNG16 target_icc 必须是 RGB ICC 字节或 None')
    if not target_icc:
        return None, b''
    if len(target_icc) > P.MAX_METADATA_BYTES:
        raise ValueError('PNG16 ICC 元数据超过 16 MiB 预算')
    profile = bytes(target_icc)
    payload = _ICC_NAME + b'\0\0' + zlib.compress(profile)
    # Include the iCCP framing and IEND in the source decoder's metadata budget.
    if len(payload) + 24 > P.MAX_METADATA_BYTES:
        raise ValueError('PNG16 压缩 ICC 元数据超过 16 MiB 预算')
    if P._inflate_icc(payload) != profile:
        raise ValueError('PNG16 ICC 压缩读回不一致')
    chunk = (struct.pack('>I', len(payload)) + b'iCCP' + payload
             + struct.pack('>I', zlib.crc32(payload, zlib.crc32(b'iCCP')) & 0xffffffff))
    return profile, chunk


def _attach_icc(encoded: bytes, iccp: bytes, *, width: int, height: int) -> bytes:
    """Check a bounded native RGB16 container before inserting one iCCP chunk.

    Only the encoder's IHDR/IDAT/IEND stream is accepted. Ancillary chunks from
    an unexpected codec build cannot smuggle source orientation, transparency,
    competing colour/HDR signalling or other unpromised metadata into delivery.
    Pixel data and filter/interlace algorithms remain entirely in libpng.
    """
    if not isinstance(encoded, bytes) or not 45 <= len(encoded) <= P.MAX_SOURCE_BYTES:
        raise ValueError('PNG16 编码结果类型、长度或 1 GiB 字节预算无效')
    if len(encoded) + len(iccp) > P.MAX_SOURCE_BYTES:
        raise ValueError('PNG16 编码结果和 ICC 超过 1 GiB 字节预算')
    header = P._header(encoded[:33])
    if (header is None or header.bits != 16 or header.color_type != 2
            or header.width != width or header.height != height or header.interlace != 0):
        raise ValueError('PNG16 编码结果必须为原尺寸、非交错、真实 RGB16；不会降位或写 alpha')
    view = memoryview(encoded)
    offset, count, idat_bytes = 33, 1 + bool(iccp), 0
    ended = False
    while offset < len(encoded):
        count += 1
        if count > P.MAX_CHUNKS or len(encoded) - offset < 12:
            raise ValueError('PNG16 编码块数量超过预算或块头截断')
        length = int.from_bytes(view[offset:offset + 4], 'big')
        kind = bytes(view[offset + 4:offset + 8])
        end = offset + 12 + length
        if length >= 2**31 or end > len(encoded) or kind not in (b'IDAT', b'IEND'):
            raise ValueError('PNG16 编码器返回无效块或未获支持的额外元数据')
        payload = view[offset + 8:end - 4]
        crc = zlib.crc32(payload, zlib.crc32(kind)) & 0xffffffff
        if crc != int.from_bytes(view[end - 4:end], 'big'):
            raise ValueError('PNG16 编码块 CRC 无效')
        if kind == b'IDAT':
            idat_bytes += length
        elif length != 0 or not idat_bytes or end != len(encoded):
            raise ValueError('PNG16 编码结果 IEND 无效、缺少像素或含尾随数据')
        else:
            ended = True
        offset = end
    if not ended:
        raise ValueError('PNG16 编码结果缺少完整 IEND')
    return b''.join((view[:33], iccp, view[33:])) if iccp else encoded


def _admit_memory(pixels: int, icc_bytes: int, *, encoded_bytes: int = 0) -> None:
    """Conservative admission for native encode, snapshots and full readback.

    The existing PNG source decoder checks available memory again before its
    snapshot. This is not a throughput, peak-RSS or allocation/OOM guarantee.
    """
    from .cpu_memory_budget import available_estimate
    required = max(pixels * 96 + icc_bytes * 4,
                   pixels * 64 + 2 * encoded_bytes) + 64 * 1024**2
    if required > max(0, available_estimate() - 256 * 1024**2) * .65:
        raise ValueError('PNG16 编码和完整读回内存预算不足；不会降位或缩小出片')


def write_verified_png16(arr: np.ndarray, out_path: str, *, target_icc: bytes | None,
                         conflict_policy: str = 'skip_and_report',
                         metadata_include_gps: bool = False) -> dict:
    """Publish already-target-encoded RGB16, then verify exact pixels and ICC.

    The public export dispatcher owns format selection and ICC conversion. A
    source EXIF blob is intentionally not an accepted input, matching TIFF16's
    ICC-only policy; requesting GPS retention is explicitly refused. Pixels
    must already have their final orientation, so no orientation tag is written.
    Destination ownership, creation permission and no-clobber races are enforced
    only by the shared resolve_target/_atomic_write path, never a local mkdir or
    alternate replacement writer. A failed committed readback stays available
    for inspection and is never returned as a successful image.
    """
    from . import export as E

    if (not isinstance(arr, np.ndarray) or arr.dtype != np.uint16
            or arr.ndim != 3 or arr.shape[2] != 3):
        raise E.ExportError('PNG16 导出需要真实 (H,W,3) uint16 RGB；不接受 RGB8、浮点或 alpha')
    height, width = map(int, arr.shape[:2])
    if (not 0 < width < 2**31 or not 0 < height < 2**31
            or width * height > P.MAX_SOURCE_PIXELS):
        raise E.ExportError('PNG16 导出尺寸无效或超过真实源 120 MP 像素预算')
    path = os.fspath(out_path)
    if os.path.splitext(path)[1].lower() != '.png':
        raise E.ExportError('PNG16 编码器只写 .png；不会以其它扩展名冒充容器')
    if metadata_include_gps:
        raise E.ExportError('16-bit PNG 不写源 EXIF/GPS：当前仅携带目标 ICC，'
                            '源元数据透传尚未实现，不能承诺保留 GPS。')
    policy = E._check_policy(conflict_policy)
    try:
        icc, iccp = _icc_chunk(target_icc)
    except ValueError as exc:
        raise E.ExportError(str(exc)) from exc

    # Frozen skip/conflict decisions occur before codec work and are never
    # replaced with this module's own path policy.
    target, reason = E.resolve_target(path, policy)
    common = {'format': 'png', 'bits': 16, 'w': width, 'h': height,
              'conflict_policy': policy, 'quality_mapping_version': E.QUALITY_MAPPING_VERSION,
              'encoder_quality': None, 'compress_level': COMPRESSION_LEVEL,
              'png_compress_level': COMPRESSION_LEVEL,
              'tiff_compression': None, 'tiff_compression_tag': None,
              'icc_source': 'source' if icc else 'none', **E._icc_facts(icc),
              'gps_written': False, 'exif_bytes': 0,
              'metadata_policy': 'target_icc_only_no_source_exif',
              'orientation_tag_written': False}
    if target is None:
        return {**common, 'path': path, 'skipped': True, 'reason': reason,
                'bytes': 0, 'write_ms': 0.0, 'encode_ms': 0.0, 'renamed_from': None,
                'readback_max_diff': None, 'levels_per_channel': None,
                'low8_nonzero_px': None, 'readback_ms': 0.0, 'verification_ms': 0.0,
                'icc_readback_bytes': None, 'icc_readback_matches': None}

    started = time.perf_counter()
    try:
        _admit_memory(width * height, len(icc) if icc else 0)
        import imagecodecs
        # The pinned native codec receives uint16, never a Pillow RGB image or
        # a promoted RGB8 staging plane. PNG compression is lossless at level 6.
        rgb = np.ascontiguousarray(arr)
        encoded = imagecodecs.png_encode(rgb, level=COMPRESSION_LEVEL)
        blob = _attach_icc(encoded, iccp, width=width, height=height)
        # Re-admit the actual encoded size while staging buffers are still
        # charged to available memory, before publishing any destination file.
        _admit_memory(width * height, len(icc) if icc else 0, encoded_bytes=len(blob))
    except Exception as exc:
        raise E.ExportError(f'PNG16 原生编码失败，未提交输出：{exc}') from exc
    encoded_at = time.perf_counter()
    from hashlib import sha256
    encoded_sha256 = sha256(blob).hexdigest()
    E._atomic_write(target, blob)
    written_at = time.perf_counter()
    # Release compressed buffers before the full-file readback admission.
    size = len(blob)
    del blob, encoded, iccp
    try:
        back = P.load_opaque_rgb16(target, max_px=P.MAX_SOURCE_PIXELS)
        read_at = time.perf_counter()
        facts = E._rgb16_readback_facts(rgb, back.rgb)
        icc_back, icc_want = back.source_icc or b'', icc or b''
        metadata_matches = back.source_exif is None and back.orientation == 1
        verified_at = time.perf_counter()
        if facts['readback_max_diff'] != 0 or icc_back != icc_want or not metadata_matches:
            raise ValueError(f"像素最大差={facts['readback_max_diff']}，"
                             f'ICC一致={icc_back == icc_want}，无源EXIF/方向标签={metadata_matches}')
    except Exception as exc:
        failure = E.ExportError(f'16-bit PNG 导出读回验证失败：{exc}。'
                                f'文件保留供检查，不作为成功出片：{target}')
        failure.outputs = [{**common, 'path':target, 'bytes':size, 'encoded_sha256':encoded_sha256, 'committed':True,
                            'verification_failed':True, 'error':str(exc), 'skipped':False}]
        raise failure from exc
    return {**common, **facts, 'path': target, 'bytes': size, 'encoded_sha256':encoded_sha256, 'skipped': False,
            'renamed_from': None if target == path else path,
            'encode_ms': round((encoded_at - started) * 1000, 2),
            'write_ms': round((written_at - encoded_at) * 1000, 2),
            'readback_ms': round((read_at - written_at) * 1000, 2),
            'verification_ms': round((verified_at - read_at) * 1000, 2),
            'icc_readback_bytes': len(icc_back),
            'icc_readback_matches': (icc_back == icc_want) if icc_want else None}
