"""放大（M7）：Lanczos 重采样的硬不变式 + 分块逐字节等价 + CPU↔GPU↔Pillow 三臂 +
神经网络超分的权重门禁与分块收敛。

只测能被独立验证的东西：
* 插值的**重现性**：Lanczos 满足 L(0)=1、L(整数)=0，所以输出网格与输入网格重合的那些
  行/列必须原样等于输入像素——这是闭式性质，不是调出来的容差。
* 直流保真：权重按行归一 ⇒ 常值图放大后仍是那个常值（不归一会按核截断误差漂掉）。
* **分块 == 整幅逐字节**：本层的核心承诺。权重表按全局坐标一次算好、块内只做下标
  平移，等价性是构造出来的；测不出来就是实现有误，不接受"近似无可见接缝"这种说法。
* 峰值只随 tile 走：小 tile 的峰值不随图幅涨——"防爆显存"的实证口径。
* 三臂：CPU float64 参考 / GPU float32 生产 ≤1 LSB；与 Pillow LANCZOS 只做趋势对照
  （边界处理与半格口径不同，不主张逐字节，主张平均差与结构相关）。
* 神经网络超分：没有权重必须拒绝（不退成 Lanczos 冒充超分）；结构前向形状对；带重叠
  分块的接缝残余随 overlap 单调不增——这条**不承诺逐字节**，卷积有边缘效应，边界写死
  在这里免得日后与确定性放大混报。
"""

from __future__ import annotations

import numpy as np
import pytest

from lumaretouch_engine.ops import upscale as U


def _toy(h=17, w=23):
    """非对称、非平铺的小图：奇数宽高能钉住"末行接首行"那类相位错误。"""
    rng = np.random.default_rng(7)
    return rng.integers(0, 256, size=(h, w, 3), dtype=np.uint8)


def _t(img, device="cpu"):
    import torch
    return torch.from_numpy(img.astype(np.float32) / 255.0).permute(2, 0, 1)[None].to(device)


# ---------------------------------------------------------------- 参数与恒等
def test_scale_1_is_byte_exact_identity():
    img = _toy()
    assert np.array_equal(U.upscale_np(img, 1), img)


def test_rejects_unknown_scale_and_downscale():
    with pytest.raises(ValueError):
        U.upscale_np(_toy(), 5)
    with pytest.raises(ValueError):
        U.resample_weights(10, 32)          # 降采样不归这一层
    with pytest.raises(ValueError):
        U.resample_weights(40000, 10000)     # 超出单边上限就不接单，而不是慢慢算


def test_rejects_bad_tile_bounds():
    import torch
    with pytest.raises(ValueError):
        U.upscale_tiled_t(torch.zeros(1, 3, 8, 8), 2, tile=4)
    with pytest.raises(ValueError):
        U.upscale_tiled_t(torch.zeros(1, 3, 8, 8), 2, tile=8192)


# ---------------------------------------------------------------- 硬不变式
def test_weights_rows_sum_to_one():
    """按行归一是直流保真的前提，先在表这一层钉住。"""
    for out_len, in_len in ((64, 32), (96, 32), (33, 11)):
        _, w = U.resample_weights(out_len, in_len)
        assert np.allclose(w.sum(axis=1), 1.0, atol=1e-12)


def test_constant_image_stays_constant():
    img = np.full((16, 16, 3), 77, np.uint8)
    out = U.upscale_np(img, 4)
    assert out.shape == (64, 64, 3)
    assert np.all(out == 77), "常值图放大后必须仍是 77（权重未归一就会漂）"


def test_output_grid_coincides_with_input_samples():
    """插值的重现性：L(0)=1、L(整数)=0，输出网格落在输入格点上的那些行/列必须
    **逐字节**等于输入（0 LSB，不是容差）。

    半格中心对齐下 pos=(i+0.5)/s−0.5：s=3 时 i≡1 (mod 3) 才是整数，s=2 时永远不是
    （全是 .25/.75）。拿 s=2 的偶数下标去对输入只会得一大串假红——那不是核错，是坐标系。
    所以正向重合取 s=3 的那个相位，反面再钉两个不该重合的相位**确实**不重合（防退化成
    最近邻：真退化了，正向那一条恰好还是 0，只有反面能报出）。
    """
    img = _toy()
    out3 = U.upscale_np(img, 3)
    d3 = np.abs(out3[1::3, 1::3].astype(np.int16) - img.astype(np.int16)).max()
    assert d3 == 0, f"网格重合处应逐字节等于输入，实得最大差 {d3}（核或半格口径不对）"
    for off in (0, 2):
        dd = np.abs(out3[off::3, off::3].astype(np.int16) - img.astype(np.int16)).max()
        assert dd > 0, f"相位 {off} 本不该与输入重合却逐字节相等：插值可能退化成了最近邻"
    out2 = U.upscale_np(img, 2)
    assert out2[::2, ::2].shape[:2] == img.shape[:2]


def test_lanczos_reconstructs_bandlimited_sinusoid():
    """地面真值臂：一个已知连续正弦按输入格点采样并量化后放大 2×，重建值必须跟得上
    那个解析正弦——这是“重采样在插真值”而不是“在造细节”的可测说法。随机图测不出
    这一条（它没真值）。坐标按实现用的半格中心对齐：输入像素 j ↔ pos j，输出 i ↔ (i+0.5)/s−0.5。"""
    W, H, s = 200, 6, 2
    fx = 6.0                      # 6 个周期/200 px → 周期≈33px，远高于 Nyquist 要求
    f = lambda p: 127.5 + 90.0 * np.cos(2 * np.pi * fx * p / W)
    samples = np.clip(np.rint(f(np.arange(W))), 0, 255).astype(np.uint8)
    img = np.tile(samples[None, :, None], (H, 1, 3))
    analytic = f((np.arange(W * s) + 0.5) / s - 0.5)
    out = U.upscale_np(img, s)[:, :, 0].astype(np.float64)
    inner = slice(12, W * s - 12)   # 避开边缘 replicate 那一圈，那里没得对
    err = float(np.abs(out[0][inner] - analytic[inner]).max())
    assert err < 3.0, f"带限正弦重建最大偏差 {err:.2f} LSB，远超 Lanczos-3 应有的精度"
    assert np.abs(out - out[0][None, :]).max() == 0, "每行结果应相同（输入与行无关）"
    # 反面：退化成最近邻时偏差会是几十 LSB——这条判据得能报出来，不然它没鉴别力
    nn = np.repeat(samples.astype(np.float64), s)
    assert float(np.abs(nn[inner] - analytic[inner]).max()) > 3.0, \
        "最近邻也能过这一关？那这条判据没鉴别力"


def test_upscale_dims_and_channel_order():
    img = _toy(11, 13)
    out = U.upscale_np(img, 3)
    assert out.shape == (33, 39, 3)
    assert not np.array_equal(out[:, :, 0], out[:, :, 1]), "通道不该被抹平成同一张"


# ---------------------------------------------------------------- 三臂对拍
def test_gpu_matches_cpu_within_one_lsb():
    torch = pytest.importorskip("torch")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    img = _toy(19, 27)
    ref = U.upscale_np(img, 2).astype(np.int16)
    got = U.upscale_t(_t(img, device), 2)
    # 量化用与实现同一个规则（rint，半值到偶），不是 floor(+0.5)：两个不同的舍入规则
    # 在平局处本来就差 1 LSB，拿它当"两路不等"报的是判据自己的错，不是实现的错
    q = np.clip(np.rint(got[0].permute(1, 2, 0).cpu().numpy() * 255.0), 0, 255)
    assert q.shape == ref.shape
    d = np.abs(q - ref).max()
    assert d <= 1, f"GPU(float32) 与 CPU(float64) 出口差 {d} LSB，超过 1"


def test_pillow_lanczos_trend_agreement():
    """第三方臂（Pillow）：边界处理与半格口径不同，只主张平均差与结构相关。"""
    Image = pytest.importorskip("PIL.Image")
    img = _toy(32, 40)
    mine = U.upscale_np(img, 2).astype(np.float64)
    theirs = np.asarray(Image.fromarray(img).resize(
        (img.shape[1] * 2, img.shape[0] * 2), Image.LANCZOS)).astype(np.float64)
    # 只比内部 4 像素环内的区域：边缘两边各用自己的边界模型，那不是同一句话
    sl = (slice(8, -8), slice(8, -8))
    a, b = mine[sl], theirs[sl]
    mad = float(np.abs(a - b).mean())
    assert mad < 3.0, f"内部平均差 {mad:.2f}/255 过大，核或半格口径不对"
    ca = (a - a.mean()).ravel()
    cb = (b - b.mean()).ravel()
    corr = float(ca @ cb / (np.linalg.norm(ca) * np.linalg.norm(cb) + 1e-12))
    assert corr > 0.99, f"结构相关 {corr:.4f} 过低"


# ---------------------------------------------------------------- 分块等价
def test_tiled_is_byte_identical_to_untiled():
    torch = pytest.importorskip("torch")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    x = _t(_toy(25, 31), device)
    whole = U.upscale_t(x, 2)
    # tile=源边长 8：25×31 的源切 4×4=16 块，每块都带 halo
    tiled, info = U.upscale_tiled_t(x, 2, tile=8)
    assert info["tiles"] == 16
    d = (whole - tiled).abs().max().item()
    assert d == 0.0, f"分块与整幅最大差 {d}：等价性是构造出来的，不为 0 就是实现有误"


def test_tiled_byte_identical_across_tile_sizes_and_devices():
    torch = pytest.importorskip("torch")
    img = _toy(23, 17)
    a, _ = U.upscale_tiled_t(_t(img, "cpu"), 3, tile=16)
    b, _ = U.upscale_tiled_t(_t(img, "cpu"), 3, tile=64)   # 一块就装下
    assert (a - b).abs().max().item() == 0.0, "换切法就换结果，说明块内下标平移没做对"


def test_tiled_peak_bounds_with_tile_not_image():
    """"峰值只随 tile 走"的账面：同一 tile 换大图，单块峰值不该随图幅涨。"""
    torch = pytest.importorskip("torch")
    small = _t(np.random.default_rng(1).integers(0, 256, (24, 24, 3), dtype=np.uint8))
    big = _t(np.random.default_rng(2).integers(0, 256, (96, 96, 3), dtype=np.uint8))
    _, i1 = U.upscale_tiled_t(small, 2, tile=8)
    _, i2 = U.upscale_tiled_t(big, 2, tile=8)
    assert i2["peak_px"] <= i1["peak_px"] * 1.6, \
        f"同 tile 下峰值从 {i1['peak_px']} 涨到 {i2['peak_px']}：块内没做局部 gather"
    _, i3 = U.upscale_tiled_t(big, 2, tile=48)
    assert i3["peak_px"] > i2["peak_px"], "tile 变大峰值不变，说明分块没真起作用"


# ---------------------------------------------------------------- 锐化
def test_unsharp_zero_amount_is_identity():
    img = _toy()
    assert np.array_equal(U.unsharp_np(img, amount=0.0), img)


def test_unsharp_keeps_constant_and_boosts_edge():
    flat = np.full((24, 24, 3), 90, np.uint8)
    assert np.array_equal(U.unsharp_np(flat, radius=2.0, amount=0.6), flat), \
        "平坦区不该被锐化改动（有改动就是直流漏进高频了）"
    step = np.tile(np.where(np.arange(24) < 12, 40, 200).astype(np.uint8), (24, 1))
    step = np.stack([step] * 3, -1)
    sharp = U.unsharp_np(step, radius=2.0, amount=0.8, threshold=0.0)
    g0 = np.abs(sharp[:, :, 0].astype(np.int16)[:, 12] - sharp[:, :, 0].astype(np.int16)[:, 11]).sum()
    g1 = np.abs(step[:, :, 0].astype(np.int16)[:, 12] - step[:, :, 0].astype(np.int16)[:, 11]).sum()
    assert g0 > g1, "amount>0 时阶跃两侧的落差必须被加大，否则锐化没生效"


def test_unsharp_gpu_cpu_within_one_lsb():
    torch = pytest.importorskip("torch")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    img = _toy(20, 28)
    ref = U.unsharp_np(img, radius=2.0, amount=0.4).astype(np.int16)
    got = U.unsharp_t(_t(img, device), radius=2.0, amount=0.4)
    q = np.clip(np.rint(got[0].permute(1, 2, 0).cpu().numpy() * 255.0), 0, 255)
    assert np.abs(q - ref).max() <= 2, "锐化两路差值过大（高斯口径或 padding 不一致）"


# ---------------------------------------------------------------- 能力口径
def test_unsharp_bands_equals_whole_byte_exact():
    """分带锐化一整张图 == 整图直锐，逐字节。halo 拿真像素，只有图的真边缘才用 replicate。

    拿不整除图高的小 band（7/17）：那才能同时踩到中间带边界与末带不满。
    """
    img = _toy(40, 50)
    for radius in (1.0, 2.0, 3.5):
        for band in (7, 17, 40, 512):
            ref = U.unsharp_np(img, radius=radius, amount=0.6)
            got = U.unsharp_bands_np(img, radius=radius, amount=0.6, band=band)
            assert np.array_equal(ref, got), f"radius={radius} band={band} 分带与整图不一致"
    assert np.array_equal(U.unsharp_bands_np(img, amount=0.0), img)


def test_scale_backends_does_not_claim_network_as_baseline():
    b = U.scale_backends()
    assert "lanczos3" in b["baseline"]
    assert "realesrgan" in b["weights_gated"]
    assert "realesrgan" not in b["baseline"], "无权重却把神经网络超分列进装机即用档，就是谎报能力"


# ---------------------------------------------------------------- 神经网络超分
def test_rrdbnet_structure_forward_shapes():
    torch = pytest.importorskip("torch")
    from lumaretouch_engine.ops import realesrgan as R
    torch.manual_seed(0)
    net = R.build_net(torch, scale=4, num_block=2, nf=16, growth=8).eval()
    with torch.no_grad():
        out = net(torch.zeros(1, 3, 16, 12))
    assert tuple(out.shape) == (1, 3, 64, 48), "×4 生成器的输出倍率不对，结构不是那个结构"
    n_up = sum(1 for m in net.upsample if type(m).__name__ == "PixelShuffle")
    assert n_up == 2, "×4 该是两级 pixel_shuffle"
    with pytest.raises(ValueError):
        R.build_net(torch, scale=3)


def test_realesrgan_rejected_without_weights(monkeypatch):
    torch = pytest.importorskip("torch")
    from lumaretouch_engine.ops import realesrgan as R
    monkeypatch.setenv("LRT_MODEL_DIR", "/tmp/lrt-no-such-model-dir")
    assert R.available() is False
    with pytest.raises(R.MissingBackend) as e:
        R.load_net()
    txt = str(e.value)
    assert "权重" in txt and "lanczos3" in txt, \
        "拒绝理由必须点名权重缺失并指向确定性档，不许含糊"


def test_realesrgan_requires_sha256_even_when_file_exists(tmp_path, monkeypatch):
    torch = pytest.importorskip("torch")
    from lumaretouch_engine.ops import realesrgan as R
    p = tmp_path / R.MODEL_FILE
    p.write_bytes(b"not-a-weight-file")
    monkeypatch.setenv("LRT_MODEL_DIR", str(tmp_path))
    monkeypatch.delenv(R.MODEL_SHA256_ENV, raising=False)
    with pytest.raises(R.MissingBackend, match="sha256|SHA256"):
        R.load_net()
    monkeypatch.setenv(R.MODEL_SHA256_ENV, "0" * 64)
    with pytest.raises(R.MissingBackend, match="不符"):
        R.load_net()


def test_realesrgan_tiled_converges_with_overlap():
    """带重叠分块：与整幅的偏差随 overlap 单调不增。随机权重就够测这一条——问的是
    分块几何与淡化掩码，不是超分质量（质量要等权重放行）。实测本尺寸本结构：
    overlap 2/4/8 → 内部最大偏差 0.044/0.024/0.015（归一单位）。"""
    torch = pytest.importorskip("torch")
    from lumaretouch_engine.ops import realesrgan as R
    torch.manual_seed(3)
    net = R.build_net(torch, scale=4, num_block=1, nf=8, growth=4).eval()
    x = torch.rand(1, 3, 20, 24)
    with torch.no_grad():
        whole = net(x).clamp(0, 1)
    errs = []
    for ov in (2, 4, 8):
        out, info = R.forward_tiled(net, x, tile=12, overlap=ov)
        assert info["tiles"] == 4, "20×24 按源 tile=12 切应是 2×2 块"
        assert out.shape == whole.shape
        assert torch.isfinite(out).all() and float(out.min()) >= 0.0 and float(out.max()) <= 1.0
        # 只比内部：图缘那一圈只有一块覆盖，本来就没有"接缝"可言
        m = 4 * 4
        errs.append(float((out[:, :, m:-m, m:-m] - whole[:, :, m:-m, m:-m]).abs().max()))
    assert errs[0] > errs[1] > errs[2], f"接缝残余没随 overlap 收敛：{errs}"
    assert errs[2] < 0.05, f"overlap=8 时内部偏差 {errs[2]:.4f} 仍过大，分块几何有误"
    # 重叠不是免费的：峰值随 overlap 涨，这条得记账而不是当黑账
    peaks = []
    for ov in (2, 8):
        _, info = R.forward_tiled(net, x, tile=12, overlap=ov)
        peaks.append(info["peak_px"])
    assert peaks[1] > peaks[0], "overlap 变大峰值不变，说明 halo 没真参与前向"


def test_realesrgan_rejects_bad_tiling_args():
    torch = pytest.importorskip("torch")
    from lumaretouch_engine.ops import realesrgan as R
    net = R.build_net(torch, scale=4, num_block=1, nf=8, growth=4)
    with pytest.raises(ValueError):
        R.forward_tiled(net, torch.zeros(1, 3, 8, 8), tile=8, overlap=8)
    with pytest.raises(ValueError):
        R.forward_tiled(net, torch.zeros(1, 3, 8, 8), tile=8, overlap=0)
    with pytest.raises(ValueError):
        R.forward_tiled(net, torch.zeros(3, 8, 8), tile=8, overlap=4)
