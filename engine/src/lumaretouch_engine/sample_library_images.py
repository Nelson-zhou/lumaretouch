# SPDX-License-Identifier: GPL-3.0-or-later
"""Private byte-for-byte imports and display-only thumbnails; reference bundles are lazy.

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
    from .sample_library_source import inspect_and_thumbnail as inspect
    return inspect(path)


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


_LEGACY_REFERENCE_REASONS = {
    '原片已保留；透明样片尚无受支持的参考合成语义，不会丢弃透明度',
    '原片已保留；现有完整参考解码仅支持 RGB8 或 RGB16 TIFF，不会降位',
    '原片已保留；RGB16 ICC 到工作色域转换尚未接入，不会当成 sRGB',
}


def reinspect_import(store, item, check_cancel):
    """Explicit duplicate import may upgrade only a verified, unmaterialized row.

    Never reinterpret a prior immutable reference or silently update read pages.
    An unsupported reinspection leaves all catalogue metadata unchanged.
    """
    from .sample_library_source import UNAVAILABLE
    if (item['kind'] != 'import' or item['reference'] is not None or item['reference_supported']
            or (item['reference_reason'] not in _LEGACY_REFERENCE_REASONS
                and not item['reference_reason'].startswith(UNAVAILABLE))):
        return False
    path = store.verify_object(item['object_name'], item['original_sha256'])
    cancelled(check_cancel)
    metadata, thumbnail = inspect_and_thumbnail(path)
    if any(metadata[key] != item[key] for key in ('width', 'height', 'format', 'precision')):
        S.fail('旧样片与重新验证的原片元数据不一致；未迁移目录', 'asset_corrupt')
    if not metadata['reference_supported']:
        return False
    cancelled(check_cancel)
    thumb_id = save_thumbnail(store, thumbnail)
    store.verify_object(item['object_name'], item['original_sha256'])
    cancelled(check_cancel)
    item.update(metadata, thumbnail_sha256=thumb_id)
    return True


def reference_reservation(width, height):
    # float32 RGB + boolean support, NPY/ZIP metadata and conservative deflate
    # expansion. Reserve the actual canvas, not 397 MiB for every small image.
    raw = width * height * 13
    return raw + raw // 1000 + 65536


def materialize(store, item, check_cancel, *, admit_reference):
    """Use existing working-sRGB full decoder and immutable reference asset semantics."""
    from . import reference_color_assets as assets
    from .reference_color_review import ColorInput
    from .sample_library_source import admit_memory, header, load_working
    from PIL import Image
    from .png16_source import source_header
    import numpy as np
    if not item['reference_supported']: S.fail(item['reference_reason'], 'reference_unsupported')
    path = store.verify_object(item['object_name'], item['original_sha256'])
    admit_memory(item['width'], item['height'], native=True)
    cancelled(check_cancel)
    png = source_header(path)
    if png is not None and png.bits == 16:
        width, height, fmt, bits = item['width'], item['height'], 'PNG', 16
    else:
        with Image.open(path) as image:
            width, height, fmt, bits, _ = header(image, path)
    if ((width, height, fmt) != (item['width'], item['height'], item['format'])
            or item['precision'].split('-', 1)[0] != str(bits)):
        S.fail('样片目录与完整原片元数据不同', 'asset_corrupt')
    pixels = load_working(path, width, height, fmt, bits)
    cancelled(check_cancel)
    source = {'sha256': item['original_sha256'], 'width': width, 'height': height}
    # Match an unedited document's imported-source support, not forensic camera
    # authenticity. External edits are unknown; no claim of untouched capture.
    support = np.ones((height, width), dtype=np.bool_)
    support[:2] = False; support[-2:] = False
    support[:, :2] = False; support[:, -2:] = False
    # Keep the established key for its previously supported RGB8/unprofiled
    # TIFF16 inputs. Newly supported source profiles are identified by source
    # SHA plus the actual working pixel digest; existing bundles never change.
    key = sha256(b'local-sample-import-full-working-srgb-v1').hexdigest()
    frame = ColorInput('sample-' + item['id'], '0', source, key, pixels, support)
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
