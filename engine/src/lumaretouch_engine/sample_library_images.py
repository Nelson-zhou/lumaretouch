# SPDX-License-Identifier: GPL-3.0-or-later
"""Private byte-for-byte imports and display-only thumbnails; full decode is lazy.

No commercial photos, cloud fetch, embedded camera preview, permanent float copy
per imported item, or lower-precision fallback. Unsupported full-reference formats
can remain as intact catalogue originals with an explicit selection limitation.
"""
from hashlib import sha256
from pathlib import Path
import io
import os
import stat
import tempfile
from . import sample_library_state as S

EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.webp'}
MAX_WALK_ENTRIES = 10000
MAX_WALK_DEPTH = 16


def cancelled(check):
    if check(): S.fail('操作已取消；尚未提交的内容未加入样片目录', 'cancelled')


def expand_paths(paths):
    """Bounded deterministic folder traversal. Refuse overflow before any import."""
    if type(paths) is not list or not 1 <= len(paths) <= S.MAX_IMPORT:
        S.fail('每次请选择 1 至 1000 个文件或目录', 'import_limit')
    found = []; seen = set(); visited = 0
    def add(path, depth=0):
        nonlocal visited
        visited += 1
        if visited > MAX_WALK_ENTRIES or depth > MAX_WALK_DEPTH:
            S.fail('目录过大或嵌套过深；请分批选择子目录', 'import_limit')
        if path.is_symlink():
            # Keep as one per-file rejection, never traverse or resolve its target.
            key = os.path.abspath(path)
            if key not in seen:
                seen.add(key); found.append(path)
                if len(found) > S.MAX_IMPORT: S.fail('单次导入超过 1000 个条目', 'import_limit')
            return
        if path.is_dir():
            with os.scandir(path) as entries:
                children = []
                for entry in entries:
                    if len(children) >= MAX_WALK_ENTRIES:
                        S.fail('目录条目过多，请缩小选择范围', 'import_limit')
                    children.append(entry.name)
            for child in sorted(children):
                if not child.startswith('.'): add(path / child, depth + 1)
        elif path.suffix.lower() in EXTENSIONS or depth == 0:
            key = os.path.abspath(path)
            if key not in seen:
                seen.add(key); found.append(path)
                if len(found) > S.MAX_IMPORT:
                    S.fail('单次导入超过 1000 张；此次尚未导入，请分批选择', 'import_limit')
    for value in paths:
        if type(value) is not str or not value or len(value) > 4096 or '\0' in value:
            S.fail('导入路径无效')
        path = Path(value)
        if not path.is_absolute(): S.fail('导入必须使用文件选择器返回的绝对路径')
        add(path)
    if not found: S.fail('所选目录没有 JPEG、PNG、TIFF 或 WebP 图片')
    return found


def copy_original(store, source, check_cancel):
    """Read one regular file through one descriptor; reject concurrent replacement."""
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    temp = None
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= S.MAX_OBJECT_BYTES:
            S.fail('原片必须是 256 MiB 以内的非空普通文件')
        store.admit_bytes(before.st_size + 1024 * 1024)
        out_fd, temp = tempfile.mkstemp(prefix='import-', suffix=source.suffix.lower(), dir=store.root / 'staging')
        digest = sha256(); total = 0
        with os.fdopen(out_fd, 'wb') as target:
            while True:
                cancelled(check_cancel)
                block = os.read(fd, 1024 * 1024)
                if not block: break
                total += len(block)
                if total > before.st_size or total > S.MAX_OBJECT_BYTES: S.fail('导入期间原片大小改变')
                digest.update(block); target.write(block)
            target.flush(); os.fsync(target.fileno())
        after = os.fstat(fd)
        stamp = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if stamp(before) != stamp(after) or total != before.st_size:
            S.fail('导入期间原片改变，请停止外部编辑后重试')
        if source.is_symlink() or stamp(source.stat()) != stamp(before):
            S.fail('导入期间原片路径被替换')
        result = Path(temp); temp = None
        return result, digest.hexdigest(), total
    finally:
        os.close(fd)
        if temp and os.path.exists(temp): os.unlink(temp)


def inspect_and_thumbnail(path):
    from PIL import Image, ImageOps
    from .decode import _source_bits, _to_working_srgb
    from .cpu_memory_budget import available_estimate
    with Image.open(path) as image:
        fmt = image.format
        if fmt not in S.FORMATS: S.fail('仅支持 JPEG、PNG、TIFF、WebP 单帧样片')
        if int(getattr(image, 'n_frames', 1)) != 1:
            S.fail('不导入多页或动画为单张样片，请先拆分')
        width, height = image.size
        if width * height > S.MAX_PIXELS: S.fail('样片超过 3200 万像素预算；不会静默缩小原片')
        orientation = int(image.getexif().get(274, 1))
        if orientation not in range(1, 9): S.fail('样片方向元数据无效')
        bits = _source_bits(image)
        if fmt == 'PNG':
            # Pillow may expose RGB16 PNG as mode RGB without info['bits'].
            with open(path, 'rb') as stream: header = stream.read(29)
            if len(header) < 29 or header[:8] != b'\x89PNG\r\n\x1a\n' or header[12:16] != b'IHDR':
                S.fail('PNG 图像头无效')
            bits = int(header[24])
        icc = image.info.get('icc_profile')
        if icc and len(icc) > 4 * 1024 * 1024: S.fail('样片颜色配置文件过大')
        transparent = 'A' in image.getbands() or 'transparency' in image.info
        supported = True; reason = ''
        if min(width, height) < 64:
            supported = False; reason = '原片已保留；现有完整参考资源要求宽高至少 64 像素'
        elif transparent:
            supported = False; reason = '原片已保留；透明样片尚无受支持的参考合成语义，不会丢弃透明度'
        elif bits > 8 and (fmt != 'TIFF' or bits != 16 or image.mode != 'RGB'):
            supported = False; reason = '原片已保留；现有完整参考解码仅支持 RGB8 或 RGB16 TIFF，不会降位'
        elif bits == 16 and icc:
            supported = False; reason = '原片已保留；RGB16 ICC 到工作色域转换尚未接入，不会当成 sRGB'
        # JPEG draft reduces only the display thumbnail, never the retained file.
        if fmt == 'JPEG': image.draft('RGB', (384, 384))
        required = image.width * image.height * 12 + 64 * 1024 * 1024
        if available_estimate() < required:
            S.fail('当前可验证内存不足以生成样片缩略图，原片未改动', 'memory_budget')
        image.load()
        display = ImageOps.exif_transpose(image)
        display.thumbnail((384, 384), Image.Resampling.LANCZOS)
        if transparent:
            rgba = display.convert('RGBA')
            backdrop = Image.new('RGBA', rgba.size, (96, 96, 96, 255)); backdrop.alpha_composite(rgba)
            display = backdrop.convert('RGB')
        display = _to_working_srgb(display, bytes(icc) if icc else None)
        output = io.BytesIO(); display.save(output, format='JPEG', quality=86)
        thumb = output.getvalue()
        if len(thumb) > 1024 * 1024: S.fail('缩略图超过预算')
    if orientation in (5, 6, 7, 8): width, height = height, width
    return {'width': width, 'height': height, 'format': fmt,
            'precision': f'{bits}-bit source; 8-bit display thumbnail',
            'reference_supported': supported, 'reference_reason': reason,
            'notes': ['原文件逐字节保存；缩略图仅用于浏览，不参与参考计算',
                      '外部导入来源：保留源文件像素支持，不证明相机原始真实性，也不代表 AI 追色已执行',
                      '原片未嵌 ICC：按 sRGB 输入假设处理' if not icc else '原片 ICC 已保留；浏览图为 8 位颜色管理显示']}, thumb


def save_thumbnail(store, raw):
    store.admit_bytes(len(raw))
    digest = sha256(raw).hexdigest()
    fd, name = tempfile.mkstemp(prefix='thumb-', dir=store.root / 'staging')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        store.install(name, digest, '.jpg', thumbnail=True)
    finally:
        if os.path.exists(name): os.unlink(name)
    return digest


def reference_reservation(width, height):
    # float32 RGB + boolean support, NPY/ZIP metadata and conservative deflate
    # expansion. Reserve the actual canvas, not 397 MiB for every small image.
    raw = width * height * 13
    return raw + raw // 1000 + 65536


def materialize(store, item, check_cancel, *, admit_reference):
    """Use existing working-sRGB full decoder and immutable reference asset semantics."""
    from . import reference_color_assets as assets
    from .reference_color_review import ColorInput
    from .decode import load_full
    from .cpu_memory_budget import available_estimate
    import numpy as np
    if not item['reference_supported']: S.fail(item['reference_reason'], 'reference_unsupported')
    path = store.verify_object(item['object_name'], item['original_sha256'])
    required = item['width'] * item['height'] * 64 + 256 * 1024 * 1024
    if available_estimate() < required: S.fail('当前可验证内存不足以完整展开样片，未降低精度', 'memory_budget')
    cancelled(check_cancel)
    bits = 16 if item['precision'].startswith('16-') else 8
    decoded = load_full(str(path), max_px=S.MAX_PIXELS, device='cpu', want_bits=bits)
    if ((decoded.w, decoded.h) != (item['width'], item['height']) or decoded.draft_used
            or (decoded.raw or {}).get('used_preview') or (decoded.raw or {}).get('half_size')
            or decoded.rgb.dtype != (np.dtype('uint16') if bits == 16 else np.dtype('uint8'))):
        S.fail('完整样片解码精度或尺寸不符；未使用代理替代')
    cancelled(check_cancel)
    source = {'sha256': item['original_sha256'], 'width': decoded.w, 'height': decoded.h}
    # Match an unedited document's imported-source support, not forensic camera
    # authenticity. External edits are unknown; no claim of untouched capture.
    support = np.ones((decoded.h, decoded.w), dtype=np.bool_)
    support[:2] = False; support[-2:] = False
    support[:, :2] = False; support[:, -2:] = False
    key = sha256(b'local-sample-import-full-working-srgb-v1').hexdigest()
    frame = ColorInput('sample-' + item['id'], '0', source, key, decoded.rgb, support)
    store.verify_object(item['object_name'], item['original_sha256'])
    admit_reference()
    reference = assets.save(assets.cache_root(), frame)
    from .sample_library_store import _sync_dir
    _sync_dir(assets.cache_root())  # Durable immutable resource before catalogue publication.
    store.require_space(0, assets.cache_root())
    cancelled(check_cancel)
    return reference


def render_thumbnail(frame):
    from PIL import Image
    import numpy as np
    from .reference_color_review import validate
    rgb = validate(frame)
    # A strided display-only view avoids allocating a full extra RGB8 canvas.
    step = max(1, (max(rgb.shape[:2]) + 383) // 384)
    sample = rgb[::step, ::step]
    display = Image.fromarray(np.rint(np.clip(sample, 0, 1) * 255).astype(np.uint8), 'RGB')
    display.thumbnail((384, 384), Image.Resampling.LANCZOS)
    output = io.BytesIO(); display.save(output, format='JPEG', quality=86)
    return output.getvalue()
