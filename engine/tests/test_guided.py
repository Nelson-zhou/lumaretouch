"""算子正确性：numpy 参考实现 vs torch 生产实现。

M0 只要求「GPU 与 CPU 数值一致」——不一致就不许把 GPU 内核接进交互链路。
"""

from __future__ import annotations

import numpy as np
import pytest

from lumaretouch_engine.ops.guided import (guided_np, _box_np, retouch_np,
                                           frequency_split_np)

RNG = np.random.default_rng(20261016)


def box_bruteforce(x: np.ndarray, r: int) -> np.ndarray:
    """朴素窗口循环，作为 _box_np 的绝对参照（小图才跑得动）。"""
    b, c, h, w = x.shape
    p = np.pad(x, ((0, 0), (0, 0), (r, r), (r, r)), mode="reflect")
    out = np.empty_like(x)
    k = 2 * r + 1
    for i in range(h):
        for j in range(w):
            out[:, :, i, j] = p[:, :, i:i + k, j:j + k].sum(axis=(2, 3)) / float(k * k)
    return out


@pytest.mark.parametrize("r", [1, 3, 6])
def test_box_matches_bruteforce(r):
    x = RNG.random((1, 3, 24, 32), dtype=np.float32)
    assert np.abs(_box_np(x, r) - box_bruteforce(x, r)).max() < 1e-5


def test_guided_with_huge_eps_equals_double_box():
    """eps→∞ 时 a→0、b→mean，输出应退化为对均值再滤一次。"""
    x = RNG.random((1, 3, 48, 64), dtype=np.float32)
    got = guided_np(x, 4, eps=1e6)
    want = _box_np(_box_np(x, 4), 4)
    assert np.abs(got - want).max() < 1e-4


def test_guided_preserves_hard_edge():
    """保边是本算法的立身之本：阶跃边界两侧必须仍然分明。"""
    x = np.zeros((1, 3, 64, 64), np.float32)
    x[:, :, :, 32:] = 0.8
    out = guided_np(x, 8, eps=1e-4)
    jump = out[0, 0, 32, 32] - out[0, 0, 32, 31]
    flat = out[0, 0, 10, 50] - out[0, 0, 10, 40]
    assert jump > 0.6, f"边缘被抹平了：jump={jump:.3f}"
    assert abs(flat) < 1e-3


def test_retouch_strength_zero_is_identity():
    x = RNG.random((1, 3, 40, 40), dtype=np.float32)
    assert np.abs(retouch_np(x, 0.0) - x).max() < 1e-7


def test_frequency_split_reconstructs_original():
    x = RNG.random((1, 3, 40, 40), dtype=np.float32)
    low, high = frequency_split_np(x, 5, 1e-3)
    assert np.abs((low + high) - x).max() < 1e-6


def test_slider_actually_changes_the_image():
    """滑块必须真有效——防住 low+high*1.0 这种恒等空操作。"""
    x = RNG.random((1, 3, 64, 64), dtype=np.float32)
    delta = np.abs(retouch_np(x, 1.0, radius=6) - x).mean()
    assert delta > 1e-3, f"强度拉几乎没变化（delta={delta:.2e}），滑块是空的"


def test_strength_is_monotonic():
    x = RNG.random((1, 3, 64, 64), dtype=np.float32)
    d1 = np.abs(retouch_np(x, 0.3, radius=6) - x).mean()
    d2 = np.abs(retouch_np(x, 0.9, radius=6) - x).mean()
    assert d2 > d1 > 0, f"强度不单调：s=0.3→{d1:.4f}, s=0.9→{d2:.4f}"


def test_detail_gain_zero_yields_lowpass_only():
    """精确组成关系：detail_gain=0 且强度 1 时，输出必须恰好等二次均化低频。

    （白噪声上用“方差必须下降”断言是错的：噪声局部方差远大于 eps，
    导向滤波的 a=var/(var+eps)≈1，本来就不会平滑它。）
    """
    x = RNG.random((1, 3, 64, 64), dtype=np.float32)
    low = guided_np(x, 6, 6e-4)
    low2 = guided_np(low, 12, 2.4e-3)
    out = retouch_np(x, 1.0, radius=6, detail_gain=0.0)
    assert np.abs(out - low2).max() < 1e-5


def test_partial_detail_gain_keeps_partial_texture():
    x = RNG.random((1, 3, 64, 64), dtype=np.float32)
    low = guided_np(x, 6, 6e-4)
    high = x - low
    for g in (0.25, 0.5, 0.75):
        out = retouch_np(x, 1.0, radius=6, detail_gain=g)
        assert np.abs(out - (guided_np(low, 12, 2.4e-3) + high * g)).max() < 1e-5


def test_torch_matches_numpy_within_tolerance():
    torch = pytest.importorskip("torch")
    if not torch.cuda.is_available():
        pytest.skip("无 GPU 可用")
    from lumaretouch_engine.ops.guided import make_tensor, retouch_t, to_numpy_chw

    x = RNG.random((128, 160, 3), dtype=np.float32)
    chw = x.transpose(2, 0, 1)[None]
    ref = retouch_np(chw, strength=0.6, radius=10, eps=6e-4)

    t = make_tensor(x, "cuda")
    out = to_numpy_chw(retouch_t(t, strength=0.6, radius=10, eps=6e-4))
    diff = np.abs(out.transpose(2, 0, 1)[None] - ref).max()
    assert diff < 2e-3, f"GPU 与 CPU 结果不一致，max diff={diff:.2e}"
