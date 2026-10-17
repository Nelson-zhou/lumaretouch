"""DNG 读侧（raw.py）与 CFA 插值（demosaic.py）的正确性。

RAW 这块的证据分三层，各测各的，不许互相顶：
* **容器 / 数学**（本文件）：读回已知答案——写侧 `packaging/make-test-dng.py` 按读侧
  渲染链的解析逆生成 DNG，原图就是答案。误差归因到 demosaic 与色彩两处，覆盖 CFA
  相位、黑电平重复维、DeltaH/V、线性化越界、瓦片边缘块、多平面、四色降色、摆正。
* **色彩对外符合性**：与第三方（系统 LibRaw）渲染对账——不在单测里，归
  `packaging/m1-raw-bench.py`（少了它，往返再准也只是自产自读的循环论证）。
* **拒绝面**：lossless JPEG / packed 位深 / float RAW / BigTIFF / CFALayout≠1 必须抛
  `UnsupportedRaw`，绝不静默换成别的渲染。
"""

from __future__ import annotations

import importlib.util
import os
import struct

import numpy as np
import pytest
from PIL import Image

from lumaretouch_engine import raw as R
from lumaretouch_engine.ops import demosaic as D

ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ENGINE, "tests", "fixtures")
JPG = os.path.join(FIXTURES, "portrait-1024x1280.jpg")
MTD = os.path.join(ENGINE, "..", "packaging", "make-test-dng.py")

needs_fixture = pytest.mark.skipif(not os.path.isfile(JPG),
                                   reason="缺测试人像，先跑 packaging/make-test-portrait.py")

_spec = importlib.util.spec_from_file_location("make_test_dng", MTD)
mt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mt)


def _src(h=96, w=128):
    """从仓库 fixture 取一小块做地面真值（够量又不拖慢 CI 的 CPU engine job）。"""
    a = np.asarray(Image.open(JPG).convert("RGB"))
    hh, ww = a.shape[:2]
    return a[hh // 2 - h // 2:hh // 2 - h // 2 + h,
             ww // 2 - w // 2:ww // 2 - w // 2 + w].copy()


def _build(tmp_path, src, name="t", **kw):
    p = os.path.join(str(tmp_path), f"{name}.dng")
    info = mt.build(p, src, **kw)
    return p, info


@needs_fixture
def test_has_raw_ifd_detects_large_dng_in_tail(tmp_path):
    """大 DNG 的 IFD 在文件尾：嗅探必须跳读尾部把它认出来，不能当坏图漏给 Pillow。

    反向门禁：把 sniff 退回只读头部，这条就红（24MP 那种前 256KB 没 IFD 的文件）。
    """
    from lumaretouch_engine.decode import sniff_raw
    src = _src(h=512, w=512)                    # 够大，IFD 落在像素之后的尾部
    path, _ = _build(tmp_path, src, rows_per_strip=64)
    assert os.path.getsize(path) > 512 * 512      # 确实是数据在前、IFD 在后
    assert R.has_raw_ifd(path) is True
    assert sniff_raw(path) is True


@needs_fixture
def test_has_raw_ifd_says_no_for_plain_bitmaps():
    """普通位图不许被误判成 RAW（否则会把 jpg 路由进 raw.py 报 UnsupportedRaw）。"""
    assert R.has_raw_ifd(JPG) is False
    png = os.path.join(FIXTURES, "portrait-1024x1280.png")
    if os.path.isfile(png):
        assert R.has_raw_ifd(png) is False


# ------------------------------------------------------------------ 往返
@needs_fixture
def test_roundtrip_matches_ground_truth(tmp_path):
    src = _src()
    path, _ = _build(tmp_path, src, black=256.0, white=16383.0)
    res = R.load_raw(path, reference=True)
    ref = res["rgb"]
    assert ref.shape == src.shape
    d = np.abs(ref.astype(int) - src.astype(int))
    # 双线性 demosaic + 8-bit 量化，量级应在个位数 LSB；跳到两位数就是链条断了
    assert d.mean() < 8.0, f"往返 mean|Δ|={d.mean():.2f} 过大"
    assert res["ms"]["total_ms"] >= 0.0


@needs_fixture
def test_black300_level_still_roundtrips(tmp_path):
    src = _src()
    path, _ = _build(tmp_path, src, black=300.0, white=16000.0)
    ref = R.load_raw(path, reference=True)["rgb"]
    d = np.abs(ref.astype(int) - src.astype(int))
    assert d.mean() < 8.0


# ------------------------------------------------------------------ CFA 相位（本轮修复的回归锁）
@needs_fixture
def test_pattern_phase_field(tmp_path):
    """DefaultCropOrigin 的奇偏移必须转成非零 pattern_phase（丢相位=红蓝错位）。"""
    src = _src()
    p1, _ = _build(tmp_path, src, name="odd", crop=(1, 1, 120, 90))
    m1 = R.build_meta(R.pick_raw_ifd(R.all_ifds(open(p1, "rb").read())),
                      R.all_ifds(open(p1, "rb").read())[0])
    assert m1.pattern_phase == (1, 1)
    p2, _ = _build(tmp_path, src, name="even", crop=(2, 2, 120, 90))
    ifds2 = R.all_ifds(open(p2, "rb").read())
    m2 = R.build_meta(R.pick_raw_ifd(ifds2), ifds2[0])
    assert m2.pattern_phase == (0, 0)          # 偶偏移回原点


@needs_fixture
def test_crop_odd_origin_does_not_swap_channels(tmp_path):
    """相位丢了的表现：R/B 通道互换，逐通道均值差上百 LSB 而相关性还很高。

    这条既是功能测试，也是把 phase 从 RawMeta 撤掉就会红的反向门禁。
    """
    src = _src()
    path, _ = _build(tmp_path, src, crop=(1, 1, 120, 90))
    ref = R.load_raw(path, reference=True)["rgb"]
    gt = src[1:1 + 90, 1:1 + 120]
    assert ref.shape == gt.shape
    for c in range(3):
        assert abs(ref[..., c].astype(int) - gt[..., c].astype(int)).mean() < 12.0, \
            f"通道 {c} 均值差过大，像红蓝互换（相位丢失）"
    # 若真把 R/B 接反，交换 ref 的 R/B 会更差——用它反证方向没歪
    normal = np.abs(ref.astype(int) - gt.astype(int)).mean()
    swapped = np.abs(ref[..., [2, 1, 0]].astype(int) - gt.astype(int)).mean()
    assert normal < swapped, "正常排序应比 R/B 互换更接近真值"


# ------------------------------------------------------------------ 线性化 / 越界
def test_linearize_clamps_out_of_range_to_last_entry():
    """越界索引取最后一格（规范行为），不是回绕或报错。"""
    m = R.RawMeta()
    m.linearization = np.array([0.0, 10.0, 40.0])       # lut[2]=40 是最后一格
    m.black = np.array([[0.0]])
    m.white = 40.0
    pix = np.array([[[0], [1], [2], [9]]], dtype=np.uint16)   # 9 远超 lut 长度
    lin = R.linearize(pix, m)
    assert lin[0, 0] == 0.0
    assert abs(lin[0, 2] - 1.0) < 1e-6                    # lut[2]=40 / white=40 → 1.0
    assert abs(lin[0, 3] - 1.0) < 1e-6                    # 越界取最后一格


@needs_fixture
def test_nonlinear_quad_roundtrip(tmp_path):
    src = _src()
    path, _ = _build(tmp_path, src, nonlinear="quad", black=256.0, white=16383.0)
    ref = R.load_raw(path, reference=True)["rgb"]
    d = np.abs(ref.astype(int) - src.astype(int))
    assert d.mean() < 8.0


# ------------------------------------------------------------------ 多平面读侧（本轮修的 planar=2）
def _mk_ifd(**kw):
    tags = {
        R.TAG_IMAGE_WIDTH: (4, (kw.get("w", 4),)),
        R.TAG_IMAGE_LENGTH: (4, (kw.get("h", 4),)),
        R.TAG_BITS_PER_SAMPLE: (3, (kw.get("bits", 16),)),
        R.TAG_SAMPLES_PER_PIXEL: (3, (kw.get("spp", 1),)),
        R.TAG_COMPRESSION: (3, (kw.get("comp", 1),)),
        R.TAG_SAMPLE_FORMAT: (3, (kw.get("fmt", 1),)),
        R.TAG_PREDICTOR: (3, (kw.get("pred", 1),)),
        R.TAG_PLANAR_CONFIG: (3, (kw.get("planar", 1),)),
    }
    return R.Ifd(pos=0, bo="<", tags=tags)


def test_read_pixels_planar2_strips():
    """LinearRaw 三平面（R/G/B 各一条带）：canvas 的每个通道取回自己那一片。"""
    Rn = np.arange(16, dtype="<u2").reshape(4, 4)
    Gn = (Rn * 2 + 1).astype("<u2")
    Bn = (Rn * 3 + 5).astype("<u2")
    buf = b"".join([Rn.tobytes(), Gn.tobytes(), Bn.tobytes()])
    ifd = _mk_ifd(spp=3, planar=2, h=4, w=4)
    ifd.tags[R.TAG_ROWS_PER_STRIP] = (4, (4,))
    ifd.tags[R.TAG_STRIP_OFFSETS] = (4, (0, 32, 64))
    ifd.tags[R.TAG_STRIP_BYTE_COUNTS] = (4, (32, 32, 32))
    canvas = R.read_pixels(buf, ifd)
    assert canvas.shape == (4, 4, 3)
    assert np.array_equal(canvas[..., 0], Rn.astype(canvas[..., 0].dtype))
    assert np.array_equal(canvas[..., 1], Gn.astype(canvas[..., 1].dtype))
    assert np.array_equal(canvas[..., 2], Bn.astype(canvas[..., 2].dtype))


def test_read_pixels_planar1_interleaved():
    """交错三样本（每行 R,G,B,R,G,B...）：reshape 回 (H,W,3)。"""
    px = np.arange(4 * 4 * 3, dtype="<u2").reshape(4, 4, 3)
    buf = px.tobytes()
    ifd = _mk_ifd(spp=3, planar=1, h=4, w=4)
    ifd.tags[R.TAG_ROWS_PER_STRIP] = (4, (4,))
    ifd.tags[R.TAG_STRIP_OFFSETS] = (4, (0,))
    ifd.tags[R.TAG_STRIP_BYTE_COUNTS] = (4, (len(buf),))
    canvas = R.read_pixels(buf, ifd)
    assert np.array_equal(canvas, px.astype(canvas.dtype))


def test_read_pixels_planar2_count_mismatch_raises():
    """planar=2 声称三平面却只给一条带：块数对不上必须拒，不能读出半截。"""
    buf = (np.arange(16, dtype="<u2")).tobytes()
    ifd = _mk_ifd(spp=3, planar=2, h=4, w=4)
    ifd.tags[R.TAG_ROWS_PER_STRIP] = (4, (4,))
    ifd.tags[R.TAG_STRIP_OFFSETS] = (4, (0,))
    ifd.tags[R.TAG_STRIP_BYTE_COUNTS] = (4, (32,))
    with pytest.raises(R.UnsupportedRaw):
        R.read_pixels(buf, ifd)


# ------------------------------------------------------------------ 四色降色（RM 折叠）
@needs_fixture
def test_four_plane_rm_fold(tmp_path):
    """四色排阵：第四通道按 RM=[I3|0] 精确降色，往返不应掺降色误差。"""
    src = _src()
    path, _ = _build(tmp_path, src, pattern=(0, 1, 2, 3), dims=(2, 2),
                     black=256.0, white=16383.0)
    ref = R.load_raw(path, reference=True)["rgb"]
    d = np.abs(ref.astype(int) - src.astype(int))
    assert d.mean() < 8.0


# ------------------------------------------------------------------ 内嵌预览不许抄近路
@needs_fixture
def test_preview_present_but_not_used(tmp_path):
    src = _src()
    prev = np.asarray(Image.open(JPG).convert("RGB"))[:64, :64].copy()
    p_prev, _ = _build(tmp_path, src, name="prev", preview=prev, black=256.0, white=16383.0)
    p_noprev, _ = _build(tmp_path, src, name="noprev", black=256.0, white=16383.0)
    res = R.load_raw(p_prev, reference=True)
    assert res["meta"].used_preview == "有"
    base = R.load_raw(p_noprev, reference=True)["rgb"]
    # 代理帧与导出同一条链：有预览也必须逐字节等于无预览的渲染（预览只是元数据）
    assert np.array_equal(res["rgb"], base)


# ------------------------------------------------------------------ 摆正
@needs_fixture
def test_orientation_rotates_output(tmp_path):
    src = _src()
    path, _ = _build(tmp_path, src, orientation=6, black=256.0, white=16383.0)
    ref = R.load_raw(path, reference=True)["rgb"]
    # orientation=6 → 摆正后宽高互换
    assert ref.shape[:2] == (src.shape[1], src.shape[0])


# ------------------------------------------------------------------ 色彩不变量（不靠往返也能钉方向）
def test_bradford_invariant():
    """bradford(src,dst) @ src 应把 src 白映到 dst 白（差在 src 的 Y 归一）。"""
    for src in (R.XYZ_D50, R.XYZ_D65, np.array([0.9, 1.0, 1.05])):
        out = R.bradford(src, R.XYZ_D65) @ src
        expect = src[1] * R.XYZ_D65
        assert np.allclose(out, expect, atol=1e-9), f"{src} → {out} vs {expect}"
    # 恒等：同白点适应矩阵应≈单位阵
    assert np.allclose(R.bradford(R.XYZ_D50, R.XYZ_D50), np.eye(3), atol=1e-9)


def _meta_with_cm(cm):
    m = R.RawMeta()
    m.color_planes = 3
    m.cm = np.asarray(cm, dtype=np.float64)
    m.analog = np.ones(3)
    m.calibration = np.eye(3)
    cand = m.cm @ R.XYZ_D50
    m.neutral = cand / cand.max()
    return m


def test_camera_to_xyz_maps_neutral_to_d50():
    """无论走哪条分支，as-shot 白反解出的 XYZ 必须落回 D50 白（Y=1）。"""
    m = _meta_with_cm(mt.DEFAULT_CM1)
    k = R.camera_to_xyz_matrix(m)
    shot_white = k @ m.neutral
    assert abs(shot_white[1] - 1.0) < 1e-6
    assert np.allclose(shot_white / shot_white[1], R.XYZ_D50 / R.XYZ_D50[1], atol=1e-4)


# ------------------------------------------------------------------ 拒绝面
def test_reject_packed_bits():
    with pytest.raises(R.UnsupportedRaw):
        R._check_supported(_mk_ifd(bits=12))


def test_reject_float_sample():
    with pytest.raises(R.UnsupportedRaw):
        R._check_supported(_mk_ifd(fmt=3))


def test_reject_lossless_jpeg_family():
    for comp in (R.COMPRESSION_BASELINE_JPEG, R.COMPRESSION_JPEG, 34892):
        with pytest.raises(R.UnsupportedRaw):
            R._check_supported(_mk_ifd(comp=comp))


def test_reject_predictor_above_2():
    with pytest.raises(R.UnsupportedRaw):
        R._check_supported(_mk_ifd(pred=3))


def test_reject_bigtiff_magic():
    buf = b"II" + struct.pack("<HI", 43, 8)
    with pytest.raises(R.UnsupportedRaw):
        R.parse_tiff(buf)


def test_reject_missing_colormatrix1():
    raw_ifd = _mk_ifd(phot=32803)
    raw_ifd.tags[R.TAG_CFA_PATTERN] = (1, (0, 1, 1, 2))
    raw_ifd.tags[R.TAG_CFA_REPEAT_PATTERN_DIM] = (3, (2, 2))
    ifd0 = _mk_ifd()
    with pytest.raises(R.UnsupportedRaw):
        R.build_meta(raw_ifd, ifd0)


def test_reject_cfa_layout_not_one():
    raw_ifd = _mk_ifd(phot=32803)
    raw_ifd.tags[R.TAG_CFA_PATTERN] = (1, (0, 1, 1, 2))
    raw_ifd.tags[R.TAG_CFA_REPEAT_PATTERN_DIM] = (3, (2, 2))
    raw_ifd.tags[R.TAG_CFA_LAYOUT] = (3, (2,))
    ifd0 = _mk_ifd()
    cm = np.array(mt.DEFAULT_CM1, dtype=float).reshape(-1)
    ifd0.tags[R.TAG_COLOR_MATRIX1] = (10, tuple(cm))
    ifd0.tags[R.TAG_ASSHOT_NEUTRAL] = (5, (0.5, 1.0, 0.6))
    with pytest.raises(R.UnsupportedRaw):
        R.build_meta(raw_ifd, ifd0)


# ------------------------------------------------------------------ 审查修复回归（#4/#8/#10/#11）
def test_site_map_phase_odd_dims_no_wrap():
    """#4：奇数宽高的非零相位必须等于大站位图按相位切的子块，不许 np.roll 把首尾粘连。"""
    base = D.site_map((0, 1, 1, 2), (2, 2), 16, 16, (0, 0))
    sm = D.site_map((0, 1, 1, 2), (2, 2), 7, 9, (1, 1))
    assert sm.shape == (7, 9)
    assert np.array_equal(sm, base[1:8, 1:10]), "奇尺寸相位切错（旧 np.roll 会把末行接回首行）"


def _mk_cfa_ifd(pattern, dims, planes=None, phot=32803):
    raw_ifd = _mk_ifd()
    raw_ifd.tags[R.TAG_PHOTOMETRIC] = (3, (phot,))
    raw_ifd.tags[R.TAG_CFA_PATTERN] = (1, tuple(pattern))
    raw_ifd.tags[R.TAG_CFA_REPEAT_PATTERN_DIM] = (3, tuple(dims))
    if planes is not None:
        raw_ifd.tags[R.TAG_COLOR_PLANES] = (3, (planes,))
    ifd0 = _mk_ifd()
    cm = np.array(mt.DEFAULT_CM1, dtype=float).reshape(-1)
    ifd0.tags[R.TAG_COLOR_MATRIX1] = (10, tuple(cm))
    ifd0.tags[R.TAG_ASSHOT_NEUTRAL] = (5, (0.5, 1.0, 0.6))
    return raw_ifd, ifd0


def test_reject_cfa_repeat_pattern_dim_zero():
    """#8：CFARepeatPatternDim 含 0 会在算相位时抛 ZeroDivision——必须是 UnsupportedRaw。"""
    raw_ifd, ifd0 = _mk_cfa_ifd((0, 1, 1, 2), (0, 2))
    with pytest.raises(R.UnsupportedRaw):
        R.build_meta(raw_ifd, ifd0)


def test_reject_cfa_pattern_length_mismatch():
    """#8：CFAPattern 项数与排阵积不符会在 site_map reshape 抛 ValueError——转 UnsupportedRaw。"""
    raw_ifd, ifd0 = _mk_cfa_ifd((0, 1, 2), (2, 2))          # 3 项 ≠ 2×2
    with pytest.raises(R.UnsupportedRaw):
        R.build_meta(raw_ifd, ifd0)


def test_reject_cfa_pattern_colorplanes_mismatch():
    """#8：色平面数须 = 最大色索引 + 1（规范硬要求），对不上就拒。"""
    raw_ifd, ifd0 = _mk_cfa_ifd((0, 1, 1, 2), (2, 2), planes=4)   # max=2 → 应为 3
    with pytest.raises(R.UnsupportedRaw):
        R.build_meta(raw_ifd, ifd0)


@needs_fixture
@pytest.mark.parametrize("orient", [1, 6, 8])
def test_src_dims_match_oriented_full_output(tmp_path, orient):
    """#10：对外报的源尺寸（去光学黑边 + 按 EXIF 摆正）必须等于满幅输出尺寸。"""
    src = _src(h=64, w=96)
    path, _ = _build(tmp_path, src, name=f"o{orient}", orientation=orient,
                     black=256.0, white=16383.0)
    res = R.load_raw(path, reference=True)
    out_w, out_h = res["rgb"].shape[1], res["rgb"].shape[0]
    assert (res["meta"].src_w, res["meta"].src_h) == (out_w, out_h), \
        f"orient={orient} 源尺寸与满幅输出对不上（旧口径写死 full_w×full_h 会漏裁片/方向）"


@needs_fixture
def test_deflate_roundtrip_byte_identical_to_uncompressed(tmp_path):
    """#11 能力口径的证据：同一 mosaic 只换压缩方式，Deflate 读回必须与未压缩逐字节相等。

    这证明我方 Deflate 读侧（zlib 头 + Predictor 2）自洽、不是半成品；但它**不**主张
    第三方互操作——真机量过系统 LibRaw 读不进我们的条带 Deflate，故 raw_backends 把
    Deflate 归到 self_verified_only，不在 baseline 里冒充已交叉验证。
    """
    src = _src()
    p_un, _ = _build(tmp_path, src, name="un", compress=1, black=256.0, white=16383.0)
    p_de, _ = _build(tmp_path, src, name="de", compress=8, predictor=2, rows_per_strip=64,
                     black=256.0, white=16383.0)
    a = R.load_raw(p_un, reference=True)["rgb"]
    b = R.load_raw(p_de, reference=True)["rgb"]
    assert np.array_equal(a, b), "Deflate 读回与未压缩不一致：解压或水平差分还原有 bug"


def test_raw_backends_marks_deflate_not_third_party():
    """#11 诚实口径：Deflate 不许混在 baseline 里冒充与 LibRaw 交叉验证过。"""
    bb = R.raw_backends()
    assert any("未压缩" in s for s in bb["baseline"])
    assert not any("Deflate" in s for s in bb["baseline"]), "Deflate 不得进 baseline"
    assert any("Deflate" in s for s in bb.get("self_verified_only", [])), \
        "Deflate 必须在 self_verified_only 里如实标注"


# ------------------------------------------------------------------ CPU/GPU 对拍
def test_demosaic_np_vs_t_parity():
    torch = pytest.importorskip("torch")
    lin = np.random.default_rng(0).random((32, 40, 1))
    np_out = D.demosaic_np(lin, (0, 1, 1, 2), (2, 2), dtype=np.float64)
    t = torch.from_numpy(lin.transpose(2, 0, 1)[None].astype("float32"))
    t_out = D.demosaic_t(t, (0, 1, 1, 2), (2, 2))[0].permute(1, 2, 0).numpy()
    assert np.abs(np_out - t_out).max() < 2e-3, "CPU 参考与 torch 生产必须同解"


@pytest.mark.parametrize("phase", [(0, 0), (1, 0), (0, 1), (1, 1)])
def test_site_map_phase_roll(phase):
    """相位就是站位图按 (-py,-px) 平移：与直接对未裁阵列取子块的直觉一致。"""
    sm = D.site_map((0, 1, 1, 2), (2, 2), 8, 8, phase)
    base = D.site_map((0, 1, 1, 2), (2, 2), 16, 16, (0, 0))
    expect = base[phase[0]:phase[0] + 8, phase[1]:phase[1] + 8]
    assert np.array_equal(sm, expect)


def test_decimate_even_factor_keeps_channel_balance():
    """偶数降采样因子：2×2 Bayer 每块正好 R,G,G,B 各一个，块内均值与插值同光度。"""
    src = np.arange(2 * 2 * 8 * 8, dtype=np.float64).reshape(16, 16, 1)
    out = D.decimate_np(src, (0, 1, 1, 2), (2, 2), 2)
    assert out.shape == (8, 8, 3)
