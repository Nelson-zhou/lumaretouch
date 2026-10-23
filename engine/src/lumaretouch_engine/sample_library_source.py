# SPDX-License-Identifier: GPL-3.0-or-later
"""Sample source admission and display, using the existing full-source boundary.

No new codec or colour transform. Native PNG16 opacity and TIFF16 layout remain
owned by load_full; ICC16 reaches working sRGB before display quantization.
"""
import io
from . import sample_library_state as S

UNAVAILABLE = '原片已保留；完整精度参考暂不可用：'


def header(image, path):
    from .full_source_working import source_bits
    fmt = image.format
    if fmt not in S.FORMATS: S.fail('仅支持 JPEG、PNG、TIFF、WebP 单帧样片')
    if int(getattr(image, 'n_frames', 1)) != 1:
        S.fail('不导入多页或动画为单张样片，请先拆分')
    width, height = image.size
    if width * height > S.MAX_PIXELS: S.fail('样片超过 3200 万像素预算；不会静默缩小原片')
    orientation = image.getexif().get(274, 1)
    if type(orientation) is not int or orientation not in range(1, 9):
        S.fail('样片方向元数据无效')
    bits = source_bits(path, image)
    icc = image.info.get('icc_profile')
    if icc and (not isinstance(icc, bytes) or len(icc) > 4 * 1024 * 1024):
        S.fail('样片颜色配置文件类型无效或超过 4 MiB')
    if orientation in (5, 6, 7, 8): width, height = height, width
    return width, height, fmt, bits, icc


def admit_memory(width, height, *, native):
    from .cpu_memory_budget import available_estimate
    required = width * height * (64 if native else 32) + (256 if native else 64) * 1024**2
    if available_estimate() < required:
        S.fail('当前可验证内存不足以展开样片，未降低精度', 'memory_budget')


def working_pixels(decoded, width, height, fmt, bits):
    import numpy as np
    from .full_source_working import working_rgb
    want = 16 if bits == 16 else 8
    if ((decoded.w, decoded.h, decoded.fmt) != (width, height, fmt) or decoded.draft_used
            or (decoded.raw or {}).get('used_preview') or (decoded.raw or {}).get('half_size')
            or decoded.rgb.dtype != (np.dtype('uint16') if want == 16 else np.dtype('uint8'))
            or decoded.rgb.shape != (height, width, 3) or decoded.src_bits != bits):
        S.fail('完整样片解码精度或尺寸不符；未使用代理替代', 'asset_corrupt')
    if decoded.source_icc and len(decoded.source_icc) > 4 * 1024 * 1024:
        S.fail('样片颜色配置文件超过 4 MiB')
    # uint8 was already converted by load_full; uint16 is still source encoded.
    pixels = working_rgb(decoded)
    if pixels.shape != (height, width, 3) or pixels.dtype != decoded.rgb.dtype:
        S.fail('工作色域转换改变了样片尺寸或精度', 'asset_corrupt')
    return pixels


def load_working(path, width, height, fmt, bits):
    """Recheck source metadata and actual opacity, not a cached catalogue flag."""
    from PIL import Image
    from .decode import load_full
    from .full_source_working import require_opaque_8bit
    from .png16_source import source_header
    png = source_header(path)
    if png is not None and png.bits == 16:
        if fmt != 'PNG' or bits != 16:
            S.fail('样片目录与真实 PNG16 格式或位深不一致', 'asset_corrupt')
        # The native decoder owns eXIf before OR after IDAT. Never infer its
        # orientation or effective ICC from Pillow's initially opened metadata.
    else:
        with Image.open(path) as image:
            if header(image, path)[:4] != (width, height, fmt, bits):
                S.fail('样片目录与原片尺寸、格式或真实位深不一致', 'asset_corrupt')
            if bits <= 8: require_opaque_8bit(image)
    if bits > 8 and (bits != 16 or fmt not in ('PNG', 'TIFF')):
        raise ValueError('仅支持 RGB8、真实 PNG16 或 RGB16 TIFF；不会降位')
    if bits == 16 and fmt == 'TIFF':
        # Header-verified TIFF can arrive under a renamed staging suffix. Reuse
        # the existing genuine TIFF owner, not load_full's filename dispatch.
        from .decode import _load_16bit_tiff_full
        decoded = _load_16bit_tiff_full(str(path), S.MAX_PIXELS)
    else:
        decoded = load_full(str(path), max_px=S.MAX_PIXELS, device='cpu', want_bits=16 if bits == 16 else 8)
    return working_pixels(decoded, width, height, fmt, bits)


def jpeg(display):
    output = io.BytesIO(); display.save(output, format='JPEG', quality=86)
    result = output.getvalue()
    if len(result) > 1024 * 1024: S.fail('缩略图超过预算')
    return result


def native_thumbnail(pixels):
    """Working RGB16 -> float-plane LANCZOS -> RGB8, display only."""
    from PIL import Image
    import numpy as np
    if pixels.dtype != np.uint16 or pixels.ndim != 3 or pixels.shape[2] != 3:
        raise ValueError('高位深缩略图必须来自真实工作 RGB16')
    height, width = pixels.shape[:2]
    scale = min(1., 384 / max(width, height))
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    output = np.empty((size[1], size[0], 3), dtype=np.uint8)
    for channel in range(3):
        with Image.fromarray(pixels[:, :, channel].astype(np.float32)) as plane:
            with plane.resize(size, Image.Resampling.LANCZOS) as resized:
                output[:, :, channel] = np.clip(np.rint(np.asarray(resized) / 257.), 0, 255).astype(np.uint8)
    with Image.fromarray(output, 'RGB') as display:
        return jpeg(display)


def unavailable_thumbnail():
    """Never approximate unsupported high-bit colour/alpha through Pillow RGB8."""
    from PIL import Image, ImageDraw
    with Image.new('RGB', (384, 256), (48, 48, 48)) as display:
        ImageDraw.Draw(display).multiline_text((24, 100), 'REFERENCE UNAVAILABLE\nOriginal retained', fill=(220, 220, 220), spacing=10)
        return jpeg(display)


def inspect_png16(path, png):
    from .decode import load_full
    width, height, icc = png.width, png.height, None
    if width * height > S.MAX_PIXELS: S.fail('样片超过 3200 万像素预算；不会静默缩小原片')
    admit_memory(width, height, native=True)
    supported = True; reason = ''; placeholder = False
    try:
        decoded = load_full(str(path), max_px=S.MAX_PIXELS, device='cpu', want_bits=16)
        width, height, icc = decoded.w, decoded.h, decoded.source_icc
        thumb = native_thumbnail(working_pixels(decoded, width, height, 'PNG', 16))
    except S.LibraryError:
        raise
    except (ValueError, RuntimeError, ImportError) as error:
        supported = False; reason = UNAVAILABLE + str(error)[:440]
        thumb = unavailable_thumbnail(); placeholder = True
    return metadata(width, height, 'PNG', 16, icc, supported, reason, placeholder), thumb


def inspect_and_thumbnail(path):
    from PIL import Image, ImageOps
    from .decode import _to_working_srgb
    from .full_source_working import require_opaque_8bit
    from .png16_source import source_header
    png = source_header(path)
    if png is not None and png.bits == 16: return inspect_png16(path, png)
    with Image.open(path) as image:
        width, height, fmt, bits, icc = header(image, path)
        if bits > 8: admit_memory(width, height, native=True)
        supported = True; reason = ''; placeholder = False
        if bits > 8:
            try:
                pixels = load_working(path, width, height, fmt, bits)
                thumb = native_thumbnail(pixels)
            except S.LibraryError:
                raise
            except (ValueError, RuntimeError, ImportError) as error:
                supported = False; reason = UNAVAILABLE + str(error)[:440]
                thumb = unavailable_thumbnail(); placeholder = True
        else:
            # JPEG draft affects only the display, never the retained source.
            if fmt == 'JPEG': image.draft('RGB', (384, 384))
            admit_memory(image.width, image.height, native=False)
            try:
                require_opaque_8bit(image)
            except ValueError:
                supported = False
                reason = '原片已保留；包含真实透明像素，完整 RGB 参考不会丢弃透明度'
            image.load()
            display = ImageOps.exif_transpose(image)
            alpha = display.convert('RGBA').getchannel('A') if not supported else None
            display = _to_working_srgb(display, icc)
            if alpha is not None:
                rgba = display.convert('RGBA'); rgba.putalpha(alpha)
                backdrop = Image.new('RGBA', rgba.size, (96, 96, 96, 255)); backdrop.alpha_composite(rgba)
                display = backdrop.convert('RGB')
            display.thumbnail((384, 384), Image.Resampling.LANCZOS)
            thumb = jpeg(display)
    return metadata(width, height, fmt, bits, icc, supported, reason, placeholder), thumb


def metadata(width, height, fmt, bits, icc, supported, reason, placeholder):
    if supported and min(width, height) < 64:
        supported = False; reason = '原片已保留；现有完整参考资源要求宽高至少 64 像素'
    notes = ['原文件逐字节保存；缩略图仅用于浏览，不参与参考计算',
             '外部导入来源：保留源文件像素支持，不证明相机原始真实性，也不代表 AI 追色已执行']
    if placeholder:
        notes.append('完整精度参考验证未通过；仅显示占位卡片，未用 RGB8 近似高位深原片')
        notes.append('原片颜色元数据逐字节保留；完整验证未通过，不承诺已转 ICC 或可按 sRGB 解释')
    else:
        notes.append('原片未嵌 ICC：按 sRGB 输入假设处理' if not icc else
                     ('原片 ICC 在真实 RGB16 上转换至工作 sRGB 后才缩放、量化为浏览图' if bits == 16 else '原片 ICC 已保留；浏览图为 8 位颜色管理显示'))
    return {'width': width, 'height': height, 'format': fmt,
            'precision': f'{bits}-bit source; 8-bit display thumbnail',
            'reference_supported': supported, 'reference_reason': reason,
            'notes': notes}
