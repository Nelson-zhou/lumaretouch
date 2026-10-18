"""M7 放大接入 M4 分块导出：两种强度的承诺分开写。

· 只有逐点层在场（strength=0、无笔迹无修容）时，渲染补丁与切法无关，放大又是
  "同一串 (下标, 权重) 同一累加顺序"，于是**导出分块 == 事后整幅放大 = 0 LSB**。
  这是端到端最硬的一条：它同时检查了 margin 够不够、下标平移对不对、量化只做一次。
· 滤波在场时渲染本身就带 ≤1 LSB 的求和顺序噪声（M4 那一节已说明原因：积分图前缀
  随 crop 变），放大把每个源像素的贡献摊到 s² 个输出像素上，所以差异占比应当被摊薄
  而不是放大——这一档按"≤1 LSB 且占比有界"判。写成 0 LSB 就是拿小靶碰运气恒绿。

反向门禁也在场：margin 撑不住 Lanczos 支撑时 `Plan.region` 必须响，而不是在块边界
上拿不存在的抽头悄悄出一条纹。
"""
from __future__ import annotations

import numpy as np
import pytest

from lumaretouch_engine.export import ExportError, ExportSpec, MAX_TILE, MIN_TILE, export_image
from lumaretouch_engine.ops.upscale import Plan, unsharp_np, upscale_np

H, W = 300, 470          # 与 test_export 同一靶幅：特意跨过 tile 下界，保证真切成多块


def src(h: int = H, w: int = W) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    base = (xx / w * 0.6 + yy / h * 0.3)
    r = np.hypot(xx - w * 0.5, yy - h * 0.45)
    warm = np.clip(1.0 - r / (min(h, w) * 0.35), 0.0, 1.0)
    rng = np.random.default_rng(7)
    noise = rng.random((h, w)) * 0.06
    ch0 = np.clip(base + 0.25 * warm, 0, 1)
    ch1 = np.clip(base * 0.9 + 0.10 * warm, 0, 1)
    ch2 = np.clip(base * 0.8 - 0.05 * warm, 0, 1)
    a = np.stack([ch0, ch1, ch2], axis=-1) + noise[..., None]
    return np.rint(np.clip(a, 0.0, 1.0) * 255.0).astype(np.uint8)


def _spec(**kw):
    base = dict(strength=0.0, radius=12, texture_radius=4)
    base.update(kw)
    return ExportSpec(**base)


def test_export_scale_dims_and_bill():
    # 本文件自己的规矩（见下面那几条）：要渲染就 importorskip——没有 torch 时
    # `export_image` 会报「导出需要 torch」，那是一句对的话，但它不构成本条的通过证据
    pytest.importorskip("torch")
    out, info = export_image(src(), _spec(scale=2), device="cpu", tile=MIN_TILE)
    assert out.shape == (H * 2, W * 2, 3)
    assert (info["w"], info["h"]) == (W * 2, H * 2)
    assert info["src_w"] == W and info["src_h"] == H, "账单要留源幅面，否则 2× 从哪来的说不清"
    assert info["scale"] == 2 and info["px"] == W * H * 4
    assert info["upscale_backend"] == "lanczos3"
    assert info["margin_px"] >= 3, "放大要 Lanczos 支撑半径的边，margin 必须吃到这一笔"
    assert info["upscale_ms"] >= 0.0


def test_export_scale_2_tiled_is_byte_identical_to_single_tile():
    pytest.importorskip("torch")
    s = src()
    a, ia = export_image(s, _spec(scale=2), device="cpu", tile=MIN_TILE)
    b, ib = export_image(s, _spec(scale=2), device="cpu", tile=MAX_TILE)
    assert ia["tiles"] > 1 and ib["tiles"] == 1, "两档都得真跑到：一块图的分块对拍是恒真空话"
    d = int(np.abs(a.astype(np.int16) - b.astype(np.int16)).max())
    assert d == 0, f"逐点层在场时换切法差 {d} LSB：下标平移或 margin 那一环不对"


def test_export_scale_equals_post_hoc_whole_upscale_byte_exact():
    """端到端最硬一条：导出里做 2× 与"先 1× 导出再整幅放大"逐字节同一。"""
    pytest.importorskip("torch")
    s = src()
    one, _ = export_image(s, _spec(scale=1), device="cpu", tile=MIN_TILE)
    two, _ = export_image(s, _spec(scale=2), device="cpu", tile=MIN_TILE)
    assert np.array_equal(two, upscale_np(one, 2)), "导出内放大与事后整幅放大不同——两条路有一处口径漂移"
    three, _ = export_image(s, _spec(scale=3), device="cpu", tile=MIN_TILE)
    assert np.array_equal(three, upscale_np(one, 3))


def test_export_scale_with_filter_within_one_lsb():
    """磨皮在场：分块 vs 单块按 M4 那一档口径判（≤1 LSB 且差异占比有界），不写成 0。"""
    pytest.importorskip("torch")
    s = src()
    spec = dict(strength=0.7, radius=6, texture_radius=3)
    a, _ = export_image(s, _spec(scale=2, **spec), device="cpu", tile=MIN_TILE)
    b, _ = export_image(s, _spec(scale=2, **spec), device="cpu", tile=MAX_TILE)
    diff = np.abs(a.astype(np.int16) - b.astype(np.int16))
    assert int(diff.max()) <= 1, f"带滤波的分块差 {int(diff.max())} LSB，超出量化级"
    share = float((diff > 0).mean())
    assert share < 0.01, f"差异像素占比 {share:.4f} 过高：放大该摊薄滤波噪声而不是把它铺开"


def test_export_sharpen_equals_whole_image_unsharp_byte_exact():
    """出片锐化排在放大之后、切的是完整输出图 → 与整图直锐逐字节同一。"""
    pytest.importorskip("torch")
    s = src()
    plain, _ = export_image(s, _spec(scale=2), device="cpu", tile=MIN_TILE)
    sharp, info = export_image(s, _spec(scale=2, sharpen_amount=0.6, sharpen_radius=2),
                               device="cpu", tile=MIN_TILE)
    assert np.array_equal(sharp, unsharp_np(plain, radius=2.0, amount=0.6)), \
        "分带锐化与整图锐化不同：halo 或图缘 replicate 口径不一致"
    assert info["sharpen_ms"] >= 0.0 and info["sharpen_amount"] == 0.6
    assert int(np.abs(sharp.astype(int) - plain.astype(int)).max()) > 0, "锐化没动画面=没跑"


def test_export_rejects_bad_scale_sharpen_and_backend():
    s = src(64, 64)
    with pytest.raises(ExportError, match="倍率"):
        export_image(s, _spec(scale=5))
    with pytest.raises(ExportError, match="sharpen_amount"):
        export_image(s, _spec(sharpen_amount=9.0))
    with pytest.raises(ExportError, match="sharpen_radius"):
        export_image(s, _spec(sharpen_radius=0))
    # 神经网络后端：在导出这一层就整条拒，且理由要点名权重而不是含糊"不支持"
    with pytest.raises(ExportError) as e:
        export_image(s, _spec(scale=2, upscale_backend="realesrgan"))
    assert "权重" in str(e.value) and "lanczos3" in str(e.value)
    with pytest.raises(ExportError, match="未知放大后端"):
        export_image(s, _spec(upscale_backend="bicubic"))


def test_export_scale_margin_cannot_be_silently_starved():
    """反向门禁：margin 被砍到撑不住 Lanczos 时 `Plan.region` 必须响，而不是给出一条缝。

    不是假想敌——把 margin 公式里放大那一项删掉、而滤波半径又恰好很小，导出就会在块
    边界上拿不存在的抽头出值，画面上一条灰纹，账单里一个字都没有。
    """
    patch = src(64, 64)[0:8, 0:8]           # 故意只给 8×8，不带 margin
    with pytest.raises(ValueError, match="补丁不够宽"):
        Plan(64, 64, 2).region(patch, 0, 16, 0, 16, 0, 0)


def test_export_scale_1_keeps_legacy_bill_shape():
    """没要放大时一个字都不该变：倍率是可选层，不是新默认。"""
    pytest.importorskip("torch")
    out, info = export_image(src(80, 96), _spec(), device="cpu", tile=MIN_TILE)
    assert out.shape == (80, 96, 3) and info["scale"] == 1
    assert info["upscale_backend"] is None and info["upscale_ms"] == 0.0
