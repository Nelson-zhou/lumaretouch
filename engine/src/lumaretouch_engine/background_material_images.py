# SPDX-License-Identifier: GPL-3.0-or-later
"""Original-byte copying and display thumbnails; existing ID decoder owns colour."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import os
import stat
import time
from . import background_material_state as S
from .background_material_store import _sync_dir

SUFFIXES = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp'}
MAX_WALK_ENTRIES = 10000
MAX_DEPTH = 8


def expand_paths(values):
    if type(values) is not list or not 1 <= len(values) <= S.MAX_IMPORT:
        S.fail('请选择 1 至 1000 个本地背景文件或文件夹')
    paths, seen, visited = [], set(), 0

    def add(path):
        key = str(path)
        if key not in seen:
            seen.add(key); paths.append(path)
            if len(paths) > S.MAX_IMPORT: S.fail('单次背景导入超过 1000 个文件', 'capacity')

    def walk(path, depth):
        nonlocal visited
        if depth > MAX_DEPTH: S.fail('背景文件夹层数超过 8 层', 'capacity')
        # lstat, not resolve: a source symlink is not an explicit original file.
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode): S.fail('背景导入文件夹不是实际目录', 'unsafe_path')
        with os.scandir(path) as entries:
            bounded = []
            for entry in entries:
                visited += 1
                if visited > MAX_WALK_ENTRIES: S.fail('背景文件夹扫描超过 10000 项', 'capacity')
                bounded.append(entry)
        for entry in sorted(bounded, key=lambda e: e.name):
            if entry.is_symlink(): continue
            if entry.is_dir(follow_symlinks=False): walk(Path(entry.path), depth + 1)
            elif entry.is_file(follow_symlinks=False) and Path(entry.name).suffix.lower() in SUFFIXES:
                add(Path(entry.path))

    for value in values:
        if type(value) is not str or not os.path.isabs(value) or len(value) > 4096 or '\x00' in value:
            S.fail('背景导入只接受本地绝对路径')
        path = Path(os.path.normpath(value))
        try: info = path.lstat()
        except OSError:
            add(path); continue  # Per-file failure is reported by the import owner.
        if stat.S_ISDIR(info.st_mode): walk(path, 0)
        else: add(path)
    if not paths: S.fail('所选文件夹没有 JPG、PNG、TIF 或 BMP 背景')
    return paths


def display_name(path):
    value = path.stem.encode('utf-8', 'replace').decode('utf-8')
    value = ''.join(c for c in value if ord(c) >= 32 and not 127 <= ord(c) <= 159).strip()[:120]
    return value or '背景素材'


def copy_original(store, path, check):
    S.cancelled(check)
    if path.suffix.lower() not in SUFFIXES: S.fail('背景仅支持 JPG、PNG、TIF、BMP')
    source = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    staged = store.staging / (S.new_id() + path.suffix.lower())
    try:
        before = os.fstat(source)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= S.MAX_OBJECT_BYTES:
            S.fail('背景必须是普通文件且不超过 10,000,000 字节')
        store.check_budget(before.st_size + S.MAX_THUMB_BYTES)
        fd = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        digest = sha256(); count = 0
        with os.fdopen(fd, 'wb') as out:
            while True:
                S.cancelled(check); data = os.read(source, 1024 * 1024)
                if not data: break
                count += len(data)
                if count > S.MAX_OBJECT_BYTES: S.fail('背景原件读取时超过 10 MB')
                digest.update(data); out.write(data)
            out.flush(); os.fchmod(out.fileno(), 0o400); os.fsync(out.fileno())
        after = os.fstat(source)
        stamp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if stamp(before) != stamp(after) or count != before.st_size:
            S.fail('背景原件在复制期间变化', 'changed')
        # Explicit path identity must still name the exact descriptor copied.
        if stamp(path.lstat()) != stamp(before): S.fail('背景原件路径在复制期间变化', 'changed')
        S.cancelled(check)
        return staged, digest.hexdigest(), count
    except BaseException:
        try: staged.unlink(missing_ok=True)
        except OSError: pass
        raise
    finally: os.close(source)


def source_format(staged):
    from PIL import Image
    with Image.open(staged) as image:
        if image.format not in S.FORMATS: S.fail('文件内容不是受支持的背景格式')
        if image.width * image.height > S.MAX_PIXELS or max(image.size) >= 32767:
            S.fail('背景素材超过实际解码像素预算', 'capacity')
        return image.format


def publish_original(store, staged, digest, size, image_format):
    """No replace: an existing hash object must match or import stops."""
    target = store.objects / (digest + S.FORMATS[image_format])
    store.check_layout()
    try:
        os.link(staged, target, follow_symlinks=False)
    except FileExistsError:
        raw = store.read_file(target, S.MAX_OBJECT_BYTES)
        if len(raw) != size or sha256(raw).hexdigest() != digest:
            S.fail('已有背景对象与摘要不一致；未覆盖它', 'changed')
    store.sync_file(target); _sync_dir(store.objects)
    return target


def thumbnail(asset):
    """Quantize only a separate <=256px display image, never the source/bundle."""
    import numpy as np
    from PIL import Image
    h, w = asset.pixels.shape[:2]; scale = min(1., 256 / max(w, h))
    shape = max(1, round(w * scale)), max(1, round(h * scale))
    rgb = np.empty((shape[1], shape[0], 3), dtype=np.float32)
    for channel in range(3):
        with Image.fromarray(asset.pixels[:, :, channel], mode='F') as plane:
            with plane.resize(shape, Image.Resampling.BOX) as small:
                rgb[:, :, channel] = np.asarray(small, dtype=np.float32)
    rgb = np.where(rgb <= .0031308, rgb * 12.92, 1.055 * np.maximum(rgb, 0) ** (1 / 2.4) - .055)
    rgb = np.clip(np.rint(rgb * 255), 0, 255).astype(np.uint8)
    if asset.alpha is None:
        image = Image.fromarray(rgb, 'RGB')
    else:
        with Image.fromarray(asset.alpha, mode='F') as plane:
            with plane.resize(shape, Image.Resampling.BOX) as small:
                alpha = np.clip(np.rint(np.asarray(small) * 255), 0, 255).astype(np.uint8)
        image = Image.fromarray(np.dstack((rgb, alpha)), 'RGBA')
    try:
        out = BytesIO(); image.save(out, format='PNG'); raw = out.getvalue()
    finally: image.close()
    if not 0 < len(raw) <= S.MAX_THUMB_BYTES: S.fail('背景缩略图超过显示预算', 'capacity')
    return raw


def publish_thumbnail(store, raw):
    digest = sha256(raw).hexdigest(); path = store.thumbnails / (digest + '.png')
    store.check_layout()
    if path.exists() or path.is_symlink():
        if store.read_file(path, S.MAX_THUMB_BYTES) != raw:
            S.fail('已有背景缩略图摘要冲突', 'changed')
        store.sync_file(path); _sync_dir(store.thumbnails)
        return path.name, digest
    tmp = store.staging / (S.new_id() + '.png')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw); stream.flush(); os.fchmod(stream.fileno(), 0o400); os.fsync(stream.fileno())
        try:
            os.link(tmp, path, follow_symlinks=False)
        except FileExistsError:
            if store.read_file(path, S.MAX_THUMB_BYTES) != raw: S.fail('背景缩略图摘要冲突', 'changed')
        store.sync_file(path); _sync_dir(store.thumbnails)
    finally:
        try: tmp.unlink(missing_ok=True)
        except OSError: pass
    return path.name, digest


def make_row(store, staged, digest, size, path, group_id, check):
    from . import id_background_assets as A
    fmt = source_format(staged)
    owned = publish_original(store, staged, digest, size, fmt)
    S.cancelled(check)
    asset = A.read(str(owned), cancelled=check)
    if asset.binding['sha256'] != digest or len(asset.content) != size:
        S.fail('背景原件内容与完整解码身份不符', 'changed')
    raw = thumbnail(asset); S.cancelled(check)
    # The staging name and already-published object both count conservatively.
    store.check_budget(len(raw))
    thumbnail_name, thumb_digest = publish_thumbnail(store, raw)
    binding = asset.binding
    return {'id': S.new_id(), 'name': display_name(path), 'group_id': group_id,
            'sha256': digest, 'bytes': size, 'width': binding['width'], 'height': binding['height'],
            'bits': binding['bits'], 'format': fmt, 'has_alpha': asset.alpha is not None,
            'created_at': int(time.time() * 1000), 'deleted_at': None,
            'object_name': owned.name, 'thumbnail_name': thumbnail_name,
            'thumbnail_sha256': thumb_digest, 'binding': binding}
