"""float→uint8 的量化口径。

这一节是 M2-a2 的 D&B 探针顶出来的：GPU 与 CPU 参考之间有 −0.686 LSB 的**平均**偏移
（68.6% 像素差 1 级，连续域只差 3e-07）。平均偏移不是噪声——噪声的均值是 0。根因是
收尾用了向零截断（`.to(torch.uint8)` / `astype(np.uint8)`）。

**既有 150 项测试一条都没抓住它**，因为它们的比对两侧都用同一个截断，偏差在相减里
抵消了。所以这里最重要的不是"quantize 等于 round"这一句，而是那条反向门禁：
必须证明"用截断会红"，否则这个测试是空的。
"""

from __future__ import annotations

import numpy as np
import pytest

from lumaretouch_engine.quant import dequantize, quantize_np

RNG = np.random.default_rng(20261016)


def trunc_np(a: np.ndarray) -> np.ndarray:
    """产品曾经的写法，保留下来只为一条反向门禁：证明本文件的判据抓得住它。"""
    return (np.clip(a, 0, 1) * 255).astype(np.uint8)


def ramp(n: int = 4096) -> np.ndarray:
    """一条覆盖全部 256 档、且每档都带不同小数余量的斜坡。"""
    return np.linspace(0.0, 1.0, n, dtype=np.float64)


# ---------------------------------------------------------------- 反向门禁
def test_truncation_would_fail_this_gate():
    """先证明"截断"会被本文件的判据抓住——否则下面的断言是恒真的。

    量法：把斜坡整体乘一个不等于 1 的系数（模拟任何一次调色/磨皮/修容），
    再看量化结果相对 float64 真值差多少。截断只会往下掉，所以均值必然显著为负；
    舍入的均值应当回到 0 附近。
    """
    x = ramp()
    want = np.rint(x * 0.9875 * 255.0)
    bias_trunc = float(trunc_np(x * 0.9875).astype(np.float64).mean() - want.mean())
    bias_round = float(quantize_np(x * 0.9875).astype(np.float64).mean() - want.mean())
    assert bias_trunc < -0.3, f"截断的偏暗量只有 {bias_trunc} LSB，本门禁的空洞化检测失效"
    assert abs(bias_round) < 0.02, f"舍入仍偏 {bias_round} LSB，收尾不是 round-to-nearest"


# ---------------------------------------------------------------- 基本语义
def test_quantize_is_round_to_nearest():
    """逐点核对照：.5 两侧各归各的档，不是"取整数部分"。"""
    for k in range(255):
        c = (k + 0.49) / 255.0
        assert int(quantize_np(np.array([c]))[0]) == k
        c = (k + 0.51) / 255.0
        assert int(quantize_np(np.array([c]))[0]) == k + 1


def test_quantize_clamps_out_of_gamut_to_the_ends():
    """越界不许回绕：uint8 回绕会把 -0.01 变成 255（负值变最亮，最坏的一种错）。"""
    x = np.array([-0.5, -1.0 / 255.0, 0.0, 1.0, 1.0 + 1.0 / 255.0, 3.0])
    got = quantize_np(x)
    assert got.tolist() == [0, 0, 0, 255, 255, 255]


def test_roundtrip_on_native_uint8_is_byte_exact():
    """解码原图走一遍 dequantize→quantize 必须逐字节回来（strength=0 那条承诺的地基）。"""
    v = np.arange(256, dtype=np.uint8)
    for dtype in (np.float32, np.float64):
        assert np.array_equal(quantize_np(dequantize(v, dtype)), v), f"{dtype} 往返掉了级"


def test_quantize_accepts_float32_without_losing_a_level():
    """float32 入参不能悄悄降级：(v/255)*255 在 float32 里可能差 1e-7，方向不定。"""
    v = RNG.integers(0, 256, size=(64, 64, 3), dtype=np.uint8)
    got = quantize_np(dequantize(v, np.float32))
    assert np.array_equal(got, v)


# ---------------------------------------------------------------- torch 侧
def test_torch_quantize_matches_numpy():
    """10 万点随机（含越界）：两侧收尾必须无系统性偏移。

    为什么判据是“均值偏移”而不是“逐字节相等”：CPU 侧升 float64、GPU 侧 float32，
    真值恰好落在半档上的像素（概率不为 0）两版可能各往一边取偶，差 1 LSB。
    那是无方向的，不是病；**有方向才是病**——本文件开头那个 −0.686 LSB 就是
    拿“最大 1 LSB”这条口径放过去的。所以这里卡均值，不卡逐字节。
    """
    torch = pytest.importorskip("torch")
    from lumaretouch_engine.quant import quantize_t

    x = RNG.random((100, 32, 32), dtype=np.float32) * 1.2 - 0.1     # 故意越界，两边都得夹
    got = quantize_t(torch.from_numpy(x.copy())).cpu().numpy().astype(np.int32)
    want = quantize_np(x).astype(np.int32)
    d = got - want
    assert int(np.abs(d).max()) <= 1, f"两版收尾差到 {d.max()} LSB，不是半档取偶能解释的"
    assert abs(float(d.mean())) <= 0.02, f"收尾存在 {d.mean():+.4f} LSB 的系统偏移"
    assert float((d != 0).mean()) < 0.001, f"{(d != 0).mean():.2%} 的像素在差，半档解释不了这么多"


def test_pack_does_not_mutate_the_caller_tensor():
    """pack 里的 clamp 不能是就地的：入参常常就是常驻缓存本身。

    就地 clamp 会把缓存的 [0,1] 之外部分永久削掉，而缓存的键里没有任何东西
    记录"这份已经被削过"——下一帧拿到的就是被上一帧改脏的底片。
    """
    torch = pytest.importorskip("torch")
    from lumaretouch_engine.vram import make_pipeline

    rgb = RNG.integers(0, 256, size=(96, 128, 3), dtype=np.uint8)
    pipe = make_pipeline("cpu", 128, 96, rgb)
    out = pipe.retouch(0.5)
    before = out.clone()
    pipe.pack(out)
    assert torch.equal(out, before), "pack 就地改了调用方张量"
    assert np.array_equal(pipe.read_back()[..., :3], quantize_np(out[0].numpy().transpose(1, 2, 0)))
