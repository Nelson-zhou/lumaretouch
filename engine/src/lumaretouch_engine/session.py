"""底片条（M5-a）：目录扫描 + 缩略图。这层只有纯函数，线程与事件在 server 那边。

控制通道的老规矩是「像素不进 JSON lines」，这里开一个**有边界的**例外，边界写死在常量里：

* 只进缩略图（长边 ≤ `MAX_EDGE`），不进代理帧，更不进满幅；
* 单张编码后 ≤ `THUMB_MAX_BYTES`，超了就降质量重编——一行 JSON 撑到几 MB 会把宿主
  的读行缓冲一起顶大，那是要常驻的；
* 代理帧那 ≈2.3 MB/帧仍然只走 /dev/shm。底片条一两百张要是挤进同一块双缓冲，
  帧通路就没地方放了。

为什么这个例外成立：缩略图是**按张、一次性**的成本（200 张摊在几秒里，每张 7 KB），
而帧通路是每帧 16.6 ms 的循环（每秒 60 次 × 2.3 MB）。把两者混为一谈只会为了「通道统一」
把缩略图塞进 shm，然后让每帧多一次争用。

扫描不做任何「看起来像图片就收」的事：扩展名白名单之外的文件逐条报进 `skipped`，
不静默少几张。底片条少一张图用户不会来问原因，只会以为自己拍丢了。
"""

from __future__ import annotations

import base64
import io
import os
import time

import numpy as np
from PIL import Image, UnidentifiedImageError

from .decode import MIN_BUDGET, clamp_budget, load_rgb

# 扩展名白名单只列 decode.load_rgb 真能打开的那些（Pillow 认的位图族）。RAW 不在里面：
# 这一版没有 RAW 解码器，把 .CR2 收进底片条只会在点下去那一刻报「解码失败」，
# 而那已经是用户点到第 37 张了——不如在扫描时就如实说「这 12 个文件本版本打不开」。
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

EDGE = 160                    # 产品默认：底片条一格的长边
# 下限不是拍一个数：解码器把代理预算夹在 MIN_BUDGET 以上（那是 shm 与显存分配的下界），
# 而缩略图走的就是同一条 load_rgb。拿 edge·edge 去请求一个比 MIN_BUDGET 还小的预算会被
# 当场拒——上一版写 MIN_EDGE=32 时，每一张缩略图都报“代理预算越界”，而事件里
# 只说“解不开”。口径得从一个数推出来，不能各写各的。
MIN_EDGE = int(MIN_BUDGET ** 0.5)          # = 64
MAX_EDGE = 512                # 再大就不是缩略图了，是第二份预览
THUMB_QUALITY = 72
MIN_THUMB_QUALITY = 40        # 重编降质的下限：再低就糊得看不出构图，宁可不显示
THUMB_MAX_BYTES = 32_768      # 编码后上限（base64 进 JSON 约 43 KB/行）
MAX_DOCS = 512                # 一次扫描的条目上限：目录里十万张时不能把会话拖死


def valid_edge(edge) -> int:
    """长边的硬下界。与 decode 那边的像素预算下界是同一个事实的两个写法，
    所以两个数必须能乘回去：edge·edge ≥ MIN_BUDGET。"""
    e = int(edge)
    if not MIN_EDGE <= e <= MAX_EDGE:
        raise ValueError(f"缩略图长边 {e} 越界（允许 {MIN_EDGE}~{MAX_EDGE}）")
    assert e * e >= MIN_BUDGET, "MIN_EDGE 与 decode.MIN_BUDGET 漂开了：这一档会被解码层拒"
    return e


def scan_dir(directory: str, limit: int = MAX_DOCS) -> dict:
    """列出一个目录里的可读图片，按文件名（不区分大小写）稳定排序。

    返回 `{"files": [...], "skipped": [{"name","why"}], "truncated": bool}`。
    `skipped` 与 `truncated` 都必须由调用方原样报出去——它们不是日志，是产品事实。
    """
    if not isinstance(directory, str) or not directory:
        raise ValueError("scan 需要一个目录路径")
    if not os.path.isdir(directory):
        raise NotADirectoryError(f"不是目录或不存在：{directory}")
    t0 = time.perf_counter()
    found: list = []
    skipped: list = []
    with os.scandir(directory) as it:
        for entry in it:
            name = entry.name
            try:
                if not entry.is_file():        # 子目录、socket、断链都走这里
                    if entry.is_dir(follow_symlinks=False):
                        skipped.append({"name": name, "why": "是目录"})
                    else:
                        skipped.append({"name": name, "why": "不是普通文件"})
                    continue
            except OSError as e:               # 权限/proc 类文件系统上的 stat 失败
                skipped.append({"name": name, "why": f"stat 失败({type(e).__name__})"})
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext not in IMAGE_EXTS:
                skipped.append({"name": name, "why": f"扩展名 {ext or '无'} 不在本版本可打开的名单里"})
                continue
            found.append(os.path.join(directory, name))
    found.sort(key=lambda p: (os.path.basename(p).lower(), os.path.basename(p), p))
    truncated = len(found) > int(limit)
    if truncated:
        found = found[: int(limit)]
    return {"dir": os.path.abspath(directory), "files": found, "skipped": skipped,
            "truncated": truncated,
            "scan_ms": round((time.perf_counter() - t0) * 1000.0, 2)}


def make_thumb(path: str, *, edge: int = EDGE, quality: int = THUMB_QUALITY) -> dict:
    """解一张缩略图出来（JPEG + base64），带逐段耗时。

    两步缩放不是冗余：`load_rgb` 锁的是**像素预算**（代理档那条实测口径），竖构图会把
    长边放到 196 这种数；底片条要的是**长边固定在格子里**，所以再过一道 `thumbnail`
    （只缩不放）。多一次重采样对 160 px 的格子看不见，而少一次就会让底片条被一张
    竖图撑破行高。
    """
    edge = valid_edge(edge)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"图片不存在或不是普通文件：{path}")
    t0 = time.perf_counter()
    try:
        d = load_rgb(path, clamp_budget(edge * edge))
    except UnidentifiedImageError as e:
        # 扩展名骗人（把 PDF 改名成 .jpg）是最常见的一类：报得具体，别只说「解码失败」
        raise ValueError(f"扩展名是图片但解不开：{e}") from e
    t_dec = time.perf_counter()

    def encode(px: int, q: int):
        im = Image.fromarray(d.rgb)
        if max(im.size) > px:                    # thumbnail 只缩不放
            im.thumbnail((px, px), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=q, optimize=True)
        return im, buf.getvalue()

    q = max(int(MIN_THUMB_QUALITY), min(int(quality), 100))
    im, raw = encode(edge, q)
    reencoded = resized = 0
    # 上限必须真守住：一张 512 长的细节图能编出几百 KB，base64 后一行就是几百 KB，
    # 200 张会把控制通道当成可牺牲的那一个。先降质量，到质量下限还守不住就缩尺寸
    # （守不住尺寸总比撑爆一行好）。上一版只降质量不缩尺寸，而质量是有下限的：
    # 纯噪声图在 q40 上能编到 90 KB，那个 while 会带着超限的字节数直接退出去。
    while len(raw) > THUMB_MAX_BYTES:
        if q > MIN_THUMB_QUALITY:
            q = max(int(MIN_THUMB_QUALITY), q - 10)
            reencoded += 1
        elif edge > MIN_EDGE:
            edge = max(MIN_EDGE, int(edge * 3 // 4))
            resized += 1
        else:
            break                                # 已到尺寸与质量的双重下限：如实带出去
        im, raw = encode(edge, q)
    t_enc = time.perf_counter()
    return {"path": path, "name": os.path.basename(path),
            "w": int(im.size[0]), "h": int(im.size[1]),
            "src_w": d.src_w, "src_h": d.src_h, "format": d.fmt,
            "bytes": len(raw), "quality": q, "reencoded": reencoded, "resized": resized,
            "jpeg_b64": base64.b64encode(raw).decode("ascii"),
            "decode_ms": round((t_dec - t0) * 1000.0, 2),
            "encode_ms": round((t_enc - t_dec) * 1000.0, 2),
            "total_ms": round((t_enc - t0) * 1000.0, 2)}


def thumb_stores_bytes_ok(info: dict) -> bool:
    """给测试与自证用：一份缩略图是否守住通道上限（含 base64 后的行宽）。

    质量与尺寸都到了下限还超限的图在真照片里不存在，但存在也不能默默发出去：
    这里返 False，用例把它当失败。
    """
    return (info["bytes"] <= THUMB_MAX_BYTES
            and len(info["jpeg_b64"]) <= (THUMB_MAX_BYTES + 2) // 3 * 4 + 4)


def doc_meta(path: str) -> dict:
    """底片条一格里的非像素信息（文件名/磁盘大小）。不解码，所以能很便宜地先摆出格子。"""
    try:
        size = os.path.getsize(path)
    except OSError:
        size = -1
    return {"path": path, "name": os.path.basename(path), "bytes_on_disk": int(size)}


def pixel_count_ok(rgb: np.ndarray, edge: int) -> bool:
    """断言缩略图真的被夹住了（给跑靶与测试用，不在生产路径上调用）。"""
    return int(max(rgb.shape[0], rgb.shape[1])) <= valid_edge(edge)
