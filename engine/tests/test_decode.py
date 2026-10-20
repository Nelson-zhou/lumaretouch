"""真图解码与代理档的正确性。

M1-3a 的验收口径之一是「strength=0 时输出与解码原图逐字节一致」，这条在解码层
就得先成立，否则到 GPU/上屏那一段再去查一位偏移，成本要翻好几倍。
"""

from __future__ import annotations

import io
import os

import numpy as np
import pytest
from PIL import Image, ImageOps

from lumaretouch_engine.decode import (ALIGN, PROXY_PIXELS, load_rgb, proxy_size)

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(HERE, "tests", "fixtures")
JPG = os.path.join(FIXTURES, "portrait-1024x1280.jpg")
PNG = os.path.join(FIXTURES, "portrait-1024x1280.png")

needs_fixture = pytest.mark.skipif(not os.path.isfile(JPG),
                                   reason="缺测试人像，先跑 packaging/make-test-portrait.py")


# ------------------------------------------------------------------ 代理档算法
@pytest.mark.parametrize("w,h", [(1024, 1280), (4000, 3000), (6000, 4000),
                                 (1280, 1280), (300, 9000), (9000, 300)])
def test_proxy_size_respects_pixel_budget(w, h):
    ow, oh = proxy_size(w, h)
    assert ow * oh <= PROXY_PIXELS, f"{w}x{h} → {ow}x{oh} 超了字节预算"
    assert abs((ow / oh) - (w / h)) / (w / h) < 0.03, f"{w}x{h} → {ow}x{oh} 长宽比走形"
    if (ow, oh) != (w, h):               # 预算内不重采样：原尺寸不保证 8 对齐
        assert ow % ALIGN == 0 and oh % ALIGN == 0


@pytest.mark.parametrize("w,h", [(640, 480), (960, 600), (100, 100)])
def test_small_images_are_not_upsampled(w, h):
    """已在预算内的图不放大也不重采样：放大只会让每帧字节变多，不会多出一像素信息。"""
    assert proxy_size(w, h) == (w, h)


def test_proxy_size_rejects_garbage():
    with pytest.raises(ValueError):
        proxy_size(0, 100)
    with pytest.raises(ValueError):
        proxy_size(-5, 100)


# ------------------------------------------------------------------ 解码
@needs_fixture
def test_fixture_decodes_to_proxy_and_is_measurable():
    d = load_rgb(JPG)
    assert d.fmt == "JPEG"
    assert (d.src_w, d.src_h) == (1024, 1280)
    assert (d.w, d.h) == proxy_size(1024, 1280)
    assert d.rgb.shape == (d.h, d.w, 3) and d.rgb.dtype == np.uint8
    assert d.rgb.flags["C_CONTIGUOUS"]
    # 一次性成本要能分开报：解码 / 摆正 / 缩放
    assert d.t_total_ms >= d.t_decode_ms > 0
    assert d.meta()["bytes_per_frame"] == d.w * d.h * 4
    assert d.meta()["bytes_per_frame"] <= PROXY_PIXELS * 4 * 1.02


@needs_fixture
def test_png_and_jpeg_of_same_picture_land_on_same_proxy_size():
    """两种容器给出的代理尺寸必须一致，否则「换个格式就掉帧」这种问题会算到管线头上。"""
    assert (load_rgb(PNG).w, load_rgb(PNG).h) == (load_rgb(JPG).w, load_rgb(JPG).h)


@needs_fixture
def test_strength_zero_survives_decode_to_vram_byte_exact():
    """验收口径③：解码 → 常驻显存 → strength=0 渲染 → 回读，必须逐字节等于解码结果。"""
    pytest.importorskip("torch")        # 只有这一条要 torch；纯解码用例不许被它带走
    from lumaretouch_engine.vram import make_pipeline

    d = load_rgb(JPG)
    pipe = make_pipeline("cpu", d.w, d.h, d.rgb)
    pipe.render(0.0)
    got = pipe.read_back()
    assert (got[:, :, 3] == 255).all()
    diff = np.abs(got[:, :, :3].astype(np.int16) - d.rgb.astype(np.int16))
    assert diff.max() == 0, f"strength=0 却有 {int((diff > 0).sum())} 个子像素被改动"


def _write_oriented_jpg(tmp_path, orientation: int) -> tuple[str, tuple[int, int]]:
    """造一张带 EXIF 方向的 JPEG：存储是横的 1200×600，靠 orientation 才立起来。

    故意选大到需要缩的尺寸：只验「转了」不够，得验「先转后缩」的代理档算术对不对。
    """
    base = Image.new("RGB", (1200, 600), (30, 90, 200))
    for x in range(0, 240):                      # 左上角一块红，旋转后落在哪能反推方向
        for y in range(0, 240):
            base.putpixel((x, y), (230, 20, 20))
    exif = Image.Exif()
    exif[0x0112] = orientation
    buf = io.BytesIO()
    base.save(buf, format="JPEG", quality=95, exif=exif)
    p = tmp_path / "oriented.jpg"
    p.write_bytes(buf.getvalue())
    return str(p), base.size


@pytest.mark.parametrize("orientation", [1, 6, 8])
def test_exif_orientation_is_applied_before_proxy_math(tmp_path, orientation):
    """方向必须在算代理档之前读出来：先缩后转会得到错比例的预览。"""
    path, stored = _write_oriented_jpg(tmp_path, orientation)
    # 显式给 576 kpx 的小预算：产品默认已抬到 4K，1200×600 在默认档下不缩，
    # 这条验的"先摆正后缩"就落不到实处。
    d = load_rgb(path, 576_000)
    expect = (stored[1], stored[0]) if orientation in (5, 6, 7, 8) else stored
    assert (d.src_w, d.src_h) == expect
    assert (d.w, d.h) == proxy_size(*expect, 576_000), "代理档不是按摆正后的比例算的"
    # 与「规范做法」（先 exif_transpose 再缩）逐像素一致
    with Image.open(path) as im:
        ref = ImageOps.exif_transpose(im).convert("RGB").resize((d.w, d.h), Image.LANCZOS)
    assert np.abs(np.asarray(ref, np.int16) - d.rgb.astype(np.int16)).max() <= 1


def test_rejects_missing_path_and_non_image(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_rgb(str(tmp_path / "根本没有这个文件.jpg"))
    with pytest.raises(FileNotFoundError):
        load_rgb(str(tmp_path))                      # 目录不是普通文件
    junk = tmp_path / "不是图片.jpg"
    junk.write_bytes(b"pretend this is a jpeg" * 40)
    with pytest.raises(Exception) as ei:             # Pillow 的 UnidentifiedImageError
        load_rgb(str(junk))
    assert "Unidentified" in type(ei.value).__name__ or "cannot identify" in str(ei.value).lower()


def test_decompression_bomb_guard_is_left_on():
    """解压炸弹保护不许被关掉：这里验 MAX_IMAGE_PIXELS 仍是 Pillow 默认值而不是 None。"""
    assert Image.MAX_IMAGE_PIXELS, "MAX_IMAGE_PIXELS 被禁用，超大图会直接吃满内存"


# ------------------------------------------------------------------ 预算与哈希清单
def test_budget_is_rejected_not_silently_clamped():
    """max_px 由外部一路传进来，它直接决定 /dev/shm 与显存分配量。

    写满 tmpfs 是 SIGBUS 硬死，不是可报的错误，所以越界必须报错而不是默默夹。"""
    from lumaretouch_engine.decode import MAX_BUDGET, MIN_BUDGET, clamp_budget

    assert clamp_budget(PROXY_PIXELS) == PROXY_PIXELS
    for bad in (MIN_BUDGET - 1, MAX_BUDGET + 1, 10 ** 9, 0):
        with pytest.raises(ValueError):
            clamp_budget(bad)


def test_fixture_hash_manifest_is_verified_not_just_recorded():
    """sha256.txt 不能只是一份没人读的文书。

    不一致只有两种可能：有人改了图没重跑生成器，或生成器变了没重生图——两种都是测试资产
    变更，必须红。注意这**不是**跨环境可复现承诺（JPEG/PNG 字节取决于 Pillow 构建），
    它是“入库资产不许被悄悄换”的回扣点，因此不能 skip。"""
    import hashlib

    manifest = os.path.join(FIXTURES, "portrait-1024x1280.sha256.txt")
    assert os.path.isfile(manifest), "缺哈希清单，重跑 packaging/make-test-portrait.py"
    want = {}
    with open(manifest) as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                continue
            digest, name = line.split()
            want[name] = digest
    assert want, "哈希清单里一条记录都没有"
    for name, digest in want.items():
        path = os.path.join(FIXTURES, name)
        assert os.path.isfile(path), f"清单里有 {name} 但文件不存在"
        got = hashlib.sha256(open(path, "rb").read()).hexdigest()
        assert got == digest, f"{name} 与清单不符（资产被改过）：\n  清单 {digest}\n  实际 {got}"


# ------------------------------------------------------------------ DCT 预缩
def _write_rotated_jpeg(tmp_path, stored=(3200, 2400), orientation=6) -> str:
    """手机直出的典型形状：大横图 + orientation=6（摆正后是竖构图）。"""
    base = Image.new("RGB", stored, (120, 120, 120))
    exif = Image.Exif()
    exif[0x0112] = orientation
    buf = io.BytesIO()
    base.save(buf, format="JPEG", quality=90, exif=exif)
    p = tmp_path / "phone.jpg"
    p.write_bytes(buf.getvalue())
    return str(p)


def test_draft_target_uses_stored_orientation(tmp_path):
    """draft() 的目标尺寸必须传**存储态**方向。

    libjpeg 选档是按存储宽高与目标两维都 ≥ 来定的，拿摆正后的竖构图去请求会把可用档
    拉低一级。实测 4000×3000 + orientation=6：传 (656,872) 只能降到 1/2（解码 12.07 ms），
    传 (872,656) 能降到 1/4（6.43 ms）。"""
    d = load_rgb(_write_rotated_jpeg(tmp_path, (3200, 2400), 6), 576_000)
    assert (d.src_w, d.src_h) == (2400, 3200), "摆正后尺寸不对"
    assert d.draft_used, "大图 + EXIF 旋转的通路没吃到 DCT 预缩，导入耗时会被系统性高估"
    assert d.draft_size is not None and d.draft_size != (3200, 2400)
    assert d.draft_size == (1600, 1200) or d.draft_size == (800, 600), \
        f"DCT 档不是 1/2 或 1/4，而是 {d.draft_size}（目标方向又传错了）"


@needs_fixture
def test_draft_used_is_false_when_libjpeg_did_not_scale():
    """draft_used 只能表示“真缩了”。

    im.draft() 返的是 (mode, (x0, y0, x1, y1))，不是尺寸元组；直接拿它跟 (raw_w, raw_h)
    比会永远“不等”，于是报表上每一张都写着“已吃到 DCT 缩放”——上一版就是这样，F 轮
    那个 draft=true 是假的。产品默认 4K 预算下这张 1024×1280 的 fixture 原幅不缩，
    libjpeg 自然不预缩，所以这里必须是 False。"""
    d = load_rgb(JPG)
    assert d.draft_size in (None, (1024, 1280)), f"意外拿到了预缩档 {d.draft_size}"
    assert not d.draft_used, "draft_used 恒为 True 的回归：它又在报假消息"



def test_proxy_budget_accepts_the_product_4k_tier():
    """产品档代理是 8_294_400（4K UHD）：这个数必须被接受，且落成 ~8.2MP 的尺寸。

    这条判据的来由：引擎原来的上限是 8_000_000，UI 把默认值提到 4K 之后，
    打开任何大图都会被一条“代理预算越界”整条拒——用户在屏幕上看到的只是
    “图打不开”。上限与产品档必须同一个数。
    """
    from lumaretouch_engine.decode import MAX_BUDGET, clamp_budget, proxy_size

    assert MAX_BUDGET >= 8_294_400
    assert clamp_budget(8_294_400) == 8_294_400
    w, h = proxy_size(4000, 3000, 8_294_400)
    assert w * h <= 8_294_400
    assert w * h >= 8_000_000, (w, h, w * h)     # 别悄悄退回低清档


def test_default_proxy_budget_is_the_product_4k_tier():
    """默认预算必须就是产品档：不允许再退回 960×600 的跑靶预算。

    UI 的 maxPx 与引擎默认必须是同一个数，否则“界面上写 4K、引擎里掉回低清”
    这种账只有把两处钉死才查得到。
    """
    assert PROXY_PIXELS == 8_294_400
