"""抠图/换底确定性核心（ops/matting.py）：合成不变式 + 线性光证据 + CPU↔GPU 对拍 + 色键。

只测能被独立验证的东西：
* 合成的两条硬不变式（α=1 原样前景 / α=0 原样背景）——闭式解，答案就是输入本身。
* 「在线性光下合成」这一档：白底黑前景 50% 混合，线性中值 0.5 编码回 sRGB≈188，
  而 sRGB 域直接平均会得 128——这一档之差就是证据，不是装饰。
* CPU 参考（float64）与 torch 生产（float32）逐像素 ≤1 LSB。
* 色键：合成纯色底 + 已知前景块，背景区 alpha→0、前景区 alpha→1。
神经网络抠图（抠得准不准）不在这里主张——那是 birefnet 权重放行后的事。
"""

from __future__ import annotations

import numpy as np
import pytest

from lumaretouch_engine.ops import matting as M


def _fg():
    rng = np.random.default_rng(0)
    return rng.integers(0, 256, size=(24, 32, 3), dtype=np.uint8)


# ------------------------------------------------------------------ 合成不变式
def test_alpha_full_is_foreground_byte_exact():
    fg = _fg()
    alpha = np.full(fg.shape[:2], 255, np.uint8)
    bg = np.array([10, 20, 30], np.uint8)
    assert np.array_equal(M.composite_np(fg, alpha, bg), fg), "α≡255 必须逐字节等于前景"


def test_alpha_zero_is_background():
    fg = _fg()
    alpha = np.zeros(fg.shape[:2], np.uint8)
    bg = np.array([200, 120, 40], np.uint8)
    out = M.composite_np(fg, alpha, bg)
    assert np.array_equal(out, np.tile(bg, (fg.shape[0], fg.shape[1], 1))), "α≡0 必须逐字节等于背景"


def test_composite_over_bg_image():
    fg, bg = _fg(), _fg()
    alpha = np.zeros(fg.shape[:2], np.uint8)
    assert np.array_equal(M.composite_np(fg, alpha, bg), bg), "α≡0 整幅背景时应等于背景图"


# ------------------------------------------------------------------ 线性光证据（关键）
def test_composite_is_linear_light_not_srgb_average():
    """白(255) 前景 α=0.5 叠黑(0) 背景：线性光混合得 ≈188，sRGB 直平均得 128。"""
    fg = np.full((4, 4, 3), 255, np.uint8)
    bg = np.zeros((4, 4, 3), np.uint8)
    alpha = np.full((4, 4), 128, np.uint8)               # 128/255≈0.502
    out = M.composite_np(fg, alpha, bg)
    mid = int(out[0, 0, 0])
    assert 175 <= mid <= 205, f"半透明白黑合成应落在线性域≈188，实得 {mid}（那说明在 sRGB 域平均）"
    # 反向钉死：sRGB 域直接平均的错误口径（≈128）不得被用
    assert mid > 160


# ------------------------------------------------------------------ CPU↔GPU 对拍
def test_composite_np_vs_t_parity():
    torch = pytest.importorskip("torch")
    fg = _fg()
    alpha = (np.random.default_rng(1).random(fg.shape[:2]) * 255).astype(np.uint8)
    bg = np.array([30, 90, 210], np.uint8)
    ref = M.composite_np(fg, alpha, bg).astype(np.int16)
    fgt = torch.from_numpy(fg.astype(np.float32) / 255.0).permute(2, 0, 1)[None]
    at = torch.from_numpy(alpha.astype(np.float32) / 255.0)[None, None]
    out = M.composite_quantize_t(M.composite_t(fgt, at, bg.astype(np.float32) / 255.0))
    got = out[0].permute(1, 2, 0).numpy().astype(np.int16)
    assert np.abs(got - ref).max() <= 1, "GPU 生产与 CPU 参考必须逐像素 ≤1 LSB"


# ------------------------------------------------------------------ 色键
def _studio_card():
    """合成一张影楼纯色底：整幅蓝底，中间一块不相关的前景（橙）。"""
    img = np.zeros((40, 40, 3), np.float64)
    img[:, :] = [0.1, 0.2, 0.9]                           # 蓝箱背景
    img[12:28, 12:28] = [0.9, 0.4, 0.05]                  # 前景块
    return (np.clip(img, 0, 1) * 255).astype(np.uint8)


def test_key_matte_separates_bg_and_fg():
    img = _studio_card()
    a = M.key_matte_np(img)                                # 自动取边框中位数=蓝
    assert a[12:28, 12:28].mean() > 0.9, "前景块应被认成前景（alpha→1）"
    corners = np.concatenate([a[:6, :6].ravel(), a[-6:, -6:].ravel()])
    assert corners.mean() < 0.1, "纯色背景区应被抠成背景（alpha→0）"


def test_key_matte_ref_override_and_bounds():
    img = _studio_card()
    a = M.key_matte_np(img, ref=[0.1, 0.2, 0.9], tol=0.1, softness=0.05)
    assert a.shape == img.shape[:2]
    assert a.min() >= 0.0 and a.max() <= 1.0, "alpha 必须落在 [0,1]"


def test_composite_rejects_shape_mismatch():
    fg = _fg()
    with pytest.raises(ValueError):
        M.composite_np(fg, np.zeros((8, 8), np.uint8), np.array([0, 0, 0], np.uint8))


# ------------------------------------------------------------------ birefnet 后端（结构 + 门禁）
def test_birefnet_forward_shape():
    """结构自搭的抠图网：前向产单通道 alpha logits，形状与输入一致（不主张质量）。"""
    torch = pytest.importorskip("torch")
    from lumaretouch_engine.ops import birefnet as B
    net = B.build_net(torch, base=32).eval()
    with torch.no_grad():
        out = net(torch.zeros(1, 3, 64, 64))
    assert out.shape == (1, 1, 64, 64), f"应输出 (1,1,H,W) alpha logits，实得 {tuple(out.shape)}"


def test_birefnet_missing_backend_when_no_weights():
    """权重不在就 MissingBackend，绝不静默退路（这是门禁本身也要能被测到）。"""
    pytest.importorskip("torch")
    from lumaretouch_engine.ops import birefnet as B
    with pytest.raises(B.MissingBackend):
        B.load_net(model_dir="/nonexistent-lrt-model-dir")


def test_birefnet_gates_weights_without_sha256(tmp_path):
    """权重文件在、但没给 LRT_BIREFNET_SHA256：必须拒上生产（无校验和的权重不可信）。"""
    pytest.importorskip("torch")
    import os
    from lumaretouch_engine.ops import birefnet as B
    (tmp_path / B.MODEL_FILE).write_bytes(b"pretend")
    os.environ.pop(B.MODEL_SHA256_ENV, None)
    with pytest.raises(B.MissingBackend, match="SHA256"):
        B.load_net(model_dir=str(tmp_path))


def test_matting_backends_tracks_the_gate_not_a_hardcoded_name(tmp_path, monkeypatch):
    """能力上报与装载放行是**同一个判据**（M8）：三个档位都得对得上。

    只看文件名会把"权重被换过"那一种机器报成装机可用（一提交就被 load_net 拒），
    而把名单刻成常量又会在权重真放行的机器上一直说"等权重"——两个方向都是谎。
    """
    pytest.importorskip("torch")   # load_net 进门先探 torch；没装就量不到同一句理由
    from lumaretouch_engine.ops import birefnet as B
    p = tmp_path / B.MODEL_FILE
    p.write_bytes(b"pretend-weight-bytes")
    monkeypatch.setenv("LRT_MODEL_DIR", str(tmp_path))

    # ① 权重在、没给校验和 → 不可用（与 load_net 同口径）
    monkeypatch.delenv(B.MODEL_SHA256_ENV, raising=False)
    assert B.matting_backends()["weights_gated"] == ["birefnet"]
    with pytest.raises(B.MissingBackend):
        B.load_net()

    # ② 给了校验和但**对不上**（权重被换过）→ 仍不可用，且 load_net 拒的是同一句
    import hashlib
    monkeypatch.setenv(B.MODEL_SHA256_ENV, "0" * 64)
    ok, why = B.production_check()
    assert ok is False and B.matting_backends()["weights_gated"] == ["birefnet"], why
    with pytest.raises(B.MissingBackend) as ei:
        B.load_net()
    assert str(ei.value) == why, "上报与执行两套口径就是双出处，早晚漂"

    # ③ 校验和真的对上 → 名单跟着事实变，birefnet 进 baseline
    good = hashlib.sha256(p.read_bytes()).hexdigest()
    monkeypatch.setenv(B.MODEL_SHA256_ENV, good)
    b = B.matting_backends()
    assert b["baseline"] == ["color_key", "birefnet"] and b["weights_gated"] == [], b
    assert B.production_check()[0] is True


def test_matting_backends_default_machine_has_only_color_key():
    """裸机器（权重不在）上报的名单里不许出现 birefnet 的可用主张。"""
    from lumaretouch_engine.ops import birefnet as B
    b = B.matting_backends(model_dir="/nonexistent-lrt-model-dir")
    assert b["baseline"] == ["color_key"]
    assert b["weights_gated"] == ["birefnet"]
