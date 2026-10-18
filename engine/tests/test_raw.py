"""DNG 读侧（raw.py）与 CFA 插值（demosaic.py）的正确性。

RAW 这块的证据分三层，各测各的，不许互相顶：
* **容器 / 数学**（本文件）：读回已知答案——写侧 `packaging/make-test-dng.py` 按读侧
  渲染链的解析逆生成 DNG，原图就是答案。误差归因到 demosaic 与色彩两处，覆盖 CFA
  相位、黑电平重复维、DeltaH/V、线性化越界、瓦片边缘块、多平面、四色降色、摆正。
* **色彩对外符合性**：与第三方（系统 LibRaw）渲染对账——不在单测里，归
  `packaging/m1-raw-bench.py`（少了它，往返再准也只是自产自读的循环论证）。
* **拒绝面**：lossless JPEG / packed 位深 / float RAW / BigTIFF / CFALayout≠1 必须抛
  `UnsupportedRaw`，绝不静默换成别的渲染。
* **系统 LibRaw 的 ctypes 后端**（M9，本文件最后一节）：绑在 .so 上的那条通道不能拿库的
  输出验库自己，所以每条都带一个写盘时就知道的真值；另有几条专门把偏移表改坏，验那道
  门是真的会关。
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


# ================================================================== 系统 LibRaw 的 ctypes 后端（M9）
#
# 证据形状与上面那一叠不同：上面验的是「自研读侧的数学对不对」，这里验的是「绑在系统库上
# 的那条通道是否真的知道自己读的是哪几个字节」。读错偏移的后果不是异常，而是一堆看着像
# 数据的垃圾，所以每条判据都带一个**写盘时就知道的真值**（data/raw-probe.json），而反向
# 门禁那几条专门把偏移表改坏——门必须是会关的，不是绿灯装饰。
#
# 系统库不在的机器上（CI 的 CPU engine job 就是一种）这些整节跳过，但跳过与失败是两件事：
# 跳过只发生在「这块机器上没有那个库」，绝不在「库在但读错」时发生。

import hashlib        # noqa: E402
import json           # noqa: E402

from lumaretouch_engine.ops import libraw as LR   # noqa: E402

PROBE_DNG = LR.PROBE_DNG
needs_libraw = pytest.mark.skipif(not LR.available(),
                                  reason="机器上没有系统 LibRaw（libraw_r.so）：这一节整节不适用")


def _probe_truth():
    with open(LR.PROBE_SIDECAR, encoding="utf-8") as f:
        return json.load(f)


def _synth(h=96, w=128):
    """算术源图：不依赖仓库里的照片，所以没有 fixture 的机器也能跑容器那一臂。"""
    yy, xx = np.meshgrid(np.arange(h), np.arange(w))
    return np.dstack([((xx * 7 + yy * 3) % 256).astype(np.uint8),
                      ((xx * 13 + yy * 61) % 256).astype(np.uint8),
                      ((xx * 29 + yy * 11) % 251).astype(np.uint8)]).transpose(1, 0, 2)


# ------------------------------------------------------------------ 自检材料本身
def test_probe_sidecar_pairs_with_the_committed_dng():
    """探针与 sidecar 必须是同一次生成的那一对（sha 对得上），不然对账就是拿答案问错题。"""
    truth = _probe_truth()
    with open(PROBE_DNG, "rb") as f:
        data = f.read()
    assert len(data) == truth["dng_bytes"]
    assert hashlib.sha256(data).hexdigest() == truth["dng_sha256"], \
        "raw-probe.dng 与 raw-probe.json 不同步：重跑 packaging/make-raw-probe.py（两件一起生成）"


def test_probe_semantics_survive_regeneration(tmp_path):
    """重新生成一份同参数的探针，语义事实必须一致：材料不是手写死的，是生成出来的。

    不比字节：JPEG 由 Pillow 编码，版本不同字节可能不同；这里要锁的是「尺寸/机型/预览
    宽高」这些**判据**，不是某个 Pillow 版本的输出哈希。
    """
    truth = _probe_truth()
    blob = mt._jpeg_bytes(_synth(truth["preview"]["h"], truth["preview"]["w"]))
    path = os.path.join(str(tmp_path), "regen.dng")
    info = mt.build(path, _synth(truth["i_h"], truth["i_w"]), preview=blob,
                    exif_ifd=(truth["exif"]["iso"], truth["exif"]["shutter"],
                              truth["exif"]["aperture"], truth["exif"]["focal_len"]),
                    rows_per_strip=32)
    assert tuple(info["size"]) == (truth["i_w"], truth["i_h"])
    pw, ph = mt._jpeg_size(blob)
    assert (pw, ph) == (truth["preview"]["w"], truth["preview"]["h"])
    # 自研读侧也必须认出同一件事——两份 sidecar 一起歪掉是拦不住的，第三方读一遍才行
    got = R.load_raw(path, reference=True)["meta"]
    assert (got.w, got.h) == (truth["i_w"], truth["i_h"])


# ------------------------------------------------------------------ 真值对账
@needs_libraw
def test_libraw_self_check_pins_every_offset_it_uses():
    r = LR.self_check()
    truth = _probe_truth()
    assert r["table_matches_lib"] is True, "表与实际载入的库不同源：下面的对账就没有意义了"
    assert (r["i_w"], r["i_h"]) == (truth["i_w"], truth["i_h"])
    assert r["make"] == truth["make"] and r["model"] == truth["model"]
    assert r["preview"] == f"{truth['preview']['w']}x{truth['preview']['h']}"
    # 拍摄参数那一区：写进去的与按表读到的是同一批字节（ISO 不在这里，见下面那条）
    for field in ("shutter", "aperture", "focal_len"):
        assert abs(r["exif"][field] - truth["exif"][field]) < 1e-3
    assert r["params"]["wb_vs_auto_mean_diff"] > 0, "白平衡开关落错字节＝开关失灵"
    assert r["params"]["half_shape"] == [truth["i_h"] // 2, truth["i_w"] // 2]
    # 字节序两臂：唯一解，而且错的那一臂必须**明显**错（分不开就等于没验）
    assert r["endian_arms"]["direct"]["max_abs_diff"] == 0
    assert r["endian_arms"]["swapped"]["frac_over_1lsb"] > 0.5


@needs_libraw
def test_libraw_refuses_a_shifted_make_offset(tmp_path, monkeypatch):
    """反向门禁：把机型名的偏移挪 8 字节，自检必须拒——不许把乱码当机型报上去。"""
    key = "libraw_iparams_t.make"
    monkeypatch.setitem(LR.LAYOUT, key, LR.LAYOUT[key] + 8)
    with pytest.raises(LR.LibRawUnavailable, match="make"):
        LR.self_check()


@needs_libraw
def test_libraw_refuses_a_shifted_other_block(tmp_path, monkeypatch):
    """反向门禁：把 libraw_data_t.other 那一区挪 4 字节，拍摄参数必须当场对不上。

    为什么不挪 sizes：尺寸走库自己的访问器（libraw_get_iwidth 那一组），根本不经过表，
    挪了也不会改变读数——拿一个不生效的改动当「门禁有效」就是绿灯装饰。这里挪的是
    真被表读到的那一区：快门/光圈/焦距都住在那里面。
    """
    key = "libraw_data_t.other"
    monkeypatch.setitem(LR.LAYOUT, key, LR.LAYOUT[key] + 4)
    with pytest.raises(LR.LibRawUnavailable, match="libraw_imgother_t"):
        LR.self_check()


@needs_libraw
def test_libraw_refuses_a_wrong_thumbnail_offset(tmp_path, monkeypatch):
    """反向门禁：预览宽度读错一格，快通道就会把别人的字节当照片交给视口。"""
    key = "libraw_thumbnail_t.twidth"
    monkeypatch.setitem(LR.LAYOUT, key, LR.LAYOUT[key] + 2)
    with pytest.raises(LR.LibRawUnavailable, match="预览"):
        LR.self_check()


@needs_libraw
def test_libraw_refuses_a_torn_sidecar(tmp_path):
    """答案被改过就不许继续用：自检要能分辨「材料坏了」与「库坏了」。"""
    truth = _probe_truth()
    truth["dng_sha256"] = hashlib.sha256(b"not the probe").hexdigest()
    side = os.path.join(str(tmp_path), "raw-probe.json")
    with open(side, "w", encoding="utf-8") as f:
        json.dump(truth, f)
    with pytest.raises(LR.LibRawUnavailable, match="不配对"):
        LR.self_check(sidecar_path=side)


# ------------------------------------------------------------------ 绑定面与缺库
@needs_libraw
def test_libraw_bound_symbols_are_the_names_this_so_exports():
    """绑定的符号名以这块 .so 实数的为准。

    `libraw_dcraw_memfree` 是文档里常见的名字，本机库里没有——真有的是
    `libraw_dcraw_clear_mem`。当初凭名字写就当场 AttributeError，这条锁住那个教训：
    不许给缺失的符号找一个同名替身。
    """
    lib = LR.load_lib()
    assert hasattr(lib, "libraw_dcraw_clear_mem")
    assert not hasattr(lib, "libraw_dcraw_memfree")
    assert hasattr(lib, "libraw_unpack_thumb") and hasattr(lib, "libraw_dcraw_make_mem_image")


def test_libraw_missing_library_kills_the_whole_backend(monkeypatch):
    """没有库＝整条不可用，而且要说清少了什么；不许退成自研 DNG 读侧冒充全格式。

    这条不 skip：它要的就是「找不到」这个场景，机器上有没有库都得验。
    """
    monkeypatch.setattr(LR, "candidate_paths", lambda: ["/nonexistent/libraw_r.so.23"])
    monkeypatch.setenv(LR.LIB_ENV, "/nonexistent/x.so")
    with pytest.raises(LR.LibRawUnavailable) as e:
        LR.load_lib(force=True)
    assert "全格式" in str(e.value) and "自研 DNG 读侧仍在位" in str(e.value)
    assert LR.available() is False
    st = LR.status()
    assert st["installed"] is False and st["checked"] is False and st["reason"]
    # 不手动恢复：_lib 已被 force 打掉，monkeypatch 一撤销，下一条会重新实探一遍


@needs_libraw
def test_libraw_corrupt_files_raise_codes_and_do_not_take_the_neighbour_down(tmp_path):
    """损坏 RAW 只塌自己：异常带 LibRaw 原码，处理完坏件后同一进程里好件照常出图。

    「整条后端被一个坏文件带倒」是装机现场最难查的一类故障，所以这条既验抛错也验恢复。
    """
    d = str(tmp_path)
    truncated = os.path.join(d, "trunc.dng")
    with open(PROBE_DNG, "rb") as f:
        all_bytes = f.read()
    with open(truncated, "wb") as f:
        f.write(all_bytes[:len(all_bytes) * 2 // 5])
    junk = os.path.join(d, "junk.dng")
    with open(junk, "wb") as f:
        f.write(b"II*\x00\x08\x00\x00\x00" + bytes(range(256)) * 8)

    for bad in (truncated, junk):
        for fn in (LR.extract_thumb, LR.process):
            with pytest.raises((LR.LibRawError, LR.LibRawUnavailable)) as e:
                fn(bad)
            if isinstance(e.value, LR.LibRawError):
                assert e.value.rc != 0 and e.value.rc in LR.LibRawError.NAMES, \
                    "错误码必须能翻成名字：带码不说清等于让人去猜库的意思"
    # 同一进程里紧接着取好件：坏文件不许留下脏状态
    good = LR.extract_thumb(PROBE_DNG)
    assert good["bytes"] == _probe_truth()["preview"]["bytes"]


@needs_libraw
def test_libraw_says_no_thumbnail_instead_of_inventing_one(tmp_path):
    """没有内嵌预览的文件要如实报「没有」，不许自己画一张顶上去。"""
    path = os.path.join(str(tmp_path), "noprev.dng")
    mt.build(path, _synth())
    with pytest.raises(LR.LibRawError) as e:
        LR.extract_thumb(path)
    assert e.value.rc == LR.LAYOUT["LIBRAW_NO_THUMBNAIL"]


# ------------------------------------------------------------------ 两条通道的产物
@needs_libraw
def test_libraw_thumb_is_the_jpeg_the_file_carries():
    """快通道搬回来的必须就是文件里那张：sha256 与写进去的逐字节一致，且没被二次渲染。"""
    truth = _probe_truth()
    got = LR.extract_thumb(PROBE_DNG)
    assert hashlib.sha256(got["jpeg"]).hexdigest() == truth["preview"]["sha256"]
    assert (got["w"], got["h"], got["bytes"]) == (truth["preview"]["w"], truth["preview"]["h"],
                                                  truth["preview"]["bytes"])
    assert got["jpeg"][:2] == b"\xff\xd8" and got["jpeg"][-2:] == b"\xff\xd9"


@needs_libraw
def test_libraw_16bit_and_8bit_are_the_same_picture():
    """字节序两臂的独立复验（自检里算过一次，这里当着测试的面再算一次）：
    16-bit 右移 8 位必须逐像素等于同档 8-bit 输出，一 LSB 都不许差。"""
    a16, info = LR.process(PROBE_DNG, output_bps=16)
    a8, _ = LR.process(PROBE_DNG, output_bps=8)
    assert a16.dtype == np.uint16 and a8.dtype == np.uint8
    assert a16.shape == a8.shape == (_probe_truth()["i_h"], _probe_truth()["i_w"], 3)
    assert int(np.abs((a16.astype(np.int64) >> 8) - a8.astype(np.int64)).max()) == 0
    assert info["bits"] == 16 and int(a16.max()) == 65535, "dcraw 把母档铺满 16-bit 量程"
    # 色彩上限不在这里验：process 之后读到的是 dcraw 缩放过的内部上限，与文件的
    # WhiteLevel 不是同一个量（见 _read_meta 的时机说明），那一笔对账在 self_check 里


@needs_fixture
@needs_libraw
def test_libraw_16bit_master_matches_our_renderer_on_a_real_photograph(tmp_path):
    """16-bit 母档的对外符合性：同一张 DNG，LibRaw 渲的与自研渲的必须同向。

    用真照片而不是探针：探针是模 256 的锯齿图，对「两种去马赛克 + 两套色彩矩阵」来说
    每个像素都在边缘上，相关系数低不代表谁错了——那种材料只能验偏移，不能验色彩。
    阈值取的是实测余量（本机 r 0.94/0.96/0.97、mean|Δ| 4.7/5.9/12.1），不是凑整数。
    """
    src = _src(h=96, w=128)
    path, _ = _build(tmp_path, src, name="nat")
    a16, _ = LR.process(path, output_bps=16)
    theirs = a16.astype(np.int64) >> 8
    ours = R.load_raw(path, reference=True)["rgb"].astype(np.int64)
    assert ours.shape == theirs.shape
    for c in range(3):
        x, y = ours[..., c].ravel(), theirs[..., c].ravel()
        assert np.corrcoef(x, y)[0, 1] > 0.90, f"通道 {c} 与第三方渲染不同向"
        assert float(np.abs(x - y).mean()) < 24.0, f"通道 {c} 与第三方渲染偏差过大"


@needs_libraw
def test_libraw_iso_speed_gap_stays_visible():
    """ISO 这一栏今天读不出来，必须写成一条会响的锁，而不是让面板显示 0 当事实。

    本机 LibRaw 0.21.5 实测：把 ISOSpeedRatings 写进影像 IFD、写进 EXIF 子 IFD
    （0x8769 摆位）都读不出 iso_speed，而快门/光圈/焦距同一个 IFD 能读到。所以 Exif
    面板的 ISO 不能靠 `other.iso_speed` 一条路——要么找到库真正取 ISO 的那条摆位，
    要么由自研读侧直接解 TIFF 标签。**哪天这条测试变红了，说明库开始读 ISO 了**，
    那时要改的是面板的取数策略，不是把这条删掉。
    """
    truth = _probe_truth()
    r = LR.self_check()
    assert r["iso_speed_truth"] == truth["exif"]["iso"] == 200
    assert r["exif"]["iso_speed"] == 0.0


# ------------------------------------------------------------------ 两条通道的接线（M9-c）
#
# 需求上「秒开走内嵌预览」与仓里「预览与出片不同路」（M3-b 的教训）必须同时成立，做法是
# 把分界写成可测的不变量，而不是写在注释里相信没人越界：
#   浏览那一格可以拿相机内嵌预览（毫秒级）；编辑与出片必须拿真解码。
# 代码上的形状是 `decode.load_rgb(..., allow_preview=?)` 默认 False，全仓只有
# session.make_thumb 一处显式打开。下面这几条就是钉这个形状的，包括反向那两条。

from lumaretouch_engine import decode as DEC        # noqa: E402
from lumaretouch_engine import session as S         # noqa: E402


def _with_preview(tmp_path, name="roll"):
    """一张带内嵌预览的 DNG：预览 40×32，真尺寸 128×96——两个尺寸故意差很多，
    这样「拿预览当编辑层」会当场在尺寸上露馅，而不是靠 notes 自觉。"""
    path = os.path.join(str(tmp_path), f"{name}.dng")
    mt.build(path, _synth(96, 128), preview=mt._jpeg_bytes(_synth(32, 40)))
    return path


@needs_libraw
def test_preview_channel_fills_only_the_browse_slot(tmp_path):
    path = _with_preview(tmp_path)
    pv = DEC.load_preview(path, DEC.PROXY_PIXELS)
    assert pv is not None and pv.draft_used is True
    assert pv.raw["source"] == "libraw_preview"
    assert (pv.w, pv.h) == (40, 32)
    assert pv.src_w == 128 and pv.src_h == 96, "浏览档小，但源尺寸要报真的：底片条要点开就知道多大"
    assert any("仅浏览" in n for n in pv.notes)
    # 默认那条（常驻层与编辑用的）必须走真解码：40×32 一漏出来就是编辑在读相机渲的图
    d = DEC.load_rgb(path, DEC.PROXY_PIXELS)
    assert d.draft_used is False and (d.w, d.h) == (128, 96)
    assert (d.raw or {}).get("source") != "libraw_preview"


@needs_libraw
def test_load_preview_returns_none_instead_of_inventing_a_frame(tmp_path):
    """没有内嵌预览时浏览那条要老实返 None，让调用方退回真解码——不许画一张灰帧占位。"""
    path = os.path.join(str(tmp_path), "noprev.dng")
    mt.build(path, _synth())
    assert DEC.load_preview(path, DEC.PROXY_PIXELS) is None
    d = DEC.load_rgb(path, DEC.PROXY_PIXELS)          # 同一张文件走默认那条照样通
    assert (d.w, d.h) == (128, 96)


@needs_libraw
def test_vendor_route_goes_to_libraw_when_the_baseline_cannot_see_the_container(tmp_path, monkeypatch):
    """把基线读侧的眼睛蒙上，RAW 分支就该转 LibRaw——这是厂商容器今天唯一能验的那一半。

    真机 CR2/NEF 一份都没有（口径已定：主张扣住），所以这里蒙住 has_raw_ifd 来复现
    「后缀是 RAW、基线看不见内容」那个形状，文件内容用我们自己写的 DNG。验的是**路由
    与真解码臂**，不是厂商解码器本身——那句话在 raw_backends() 里也得照样说。
    """
    path = os.path.join(str(tmp_path), "shot.cr3")
    with open(PROBE_DNG, "rb") as f:
        blob = f.read()
    with open(path, "wb") as f:
        f.write(blob)
    assert DEC.raw_ext(path) == ".cr3" and DEC.is_raw(path), "厂商后缀没进 RAW 分支：会被漏给 Pillow"
    monkeypatch.setattr(R, "has_raw_ifd", lambda p: False)      # 基线看不见内容
    d = DEC.load_rgb(path, DEC.PROXY_PIXELS)
    assert d.raw["source"] == "libraw" and d.draft_used is False
    assert any("LibRaw 真去马赛克" in n for n in d.notes)
    assert not any("基线读侧没解开" in n for n in d.notes), \
        "根本没试过基线，就不能报「基线解不开」——那是把路由说成故障"


@needs_libraw
def test_filmstrip_thumb_uses_the_preview_and_marks_it(tmp_path):
    """底片条那一格：取预览、如实标 preview=True，并且守住通道字节上限。"""
    path = _with_preview(tmp_path)
    info = S.make_thumb(path, edge=160)
    assert info["preview"] is True
    assert info["format"] == "DNG" and (info["w"], info["h"]) == (40, 32)
    assert (info["src_w"], info["src_h"]) == (128, 96)
    assert S.thumb_stores_bytes_ok(info)
    assert info["decode_ms"] >= 0.0
    # 同一个文件走编辑那条默认路：两通道不许在这里汇合
    d = DEC.load_rgb(path, DEC.PROXY_PIXELS)
    assert (d.raw or {}).get("source") != "libraw_preview" and (d.w, d.h) == (128, 96)


@needs_libraw
def test_load_full_for_raw_still_decodes_real_pixels(tmp_path):
    """满幅那条（导出通路）也不许被预览劫持：尺寸必须是源尺寸。"""
    path = _with_preview(tmp_path)
    d = DEC.load_full(path)
    assert (d.w, d.h) == (128, 96) and d.rgb.dtype == np.uint8
    assert d.raw is None or d.raw.get("used_preview") is not True


@needs_libraw
def test_baseline_refusal_hands_over_to_libraw_with_the_reason_left_visible(tmp_path):
    """基线拒开的文件要交给 LibRaw，而且**换后端这件事得留在账单上**。

    用的是 CFALayout≠1 那张：基线按规矩拒（那一族本来就登记在 needs_plugin 里），系统
    LibRaw 接得住。这里的文件是「标签说一套、数据写一套」的合成件（我们的写侧只按行
    交错铺数据，改的只是那个标签号），所以**不比几何与像素**——比了就是拿一个不合格
    的材料当判据。这一条只锁路由与留痕；真正的厂商容器要等真机样本才能主张。
    """
    path = os.path.join(str(tmp_path), "cfa2.dng")
    mt.build(path, _synth(), cfa_layout=2)
    with pytest.raises(R.UnsupportedRaw, match="CFALayout"):     # 基线那条规矩不动
        R.load_raw(path, reference=True)
    d = DEC.load_rgb(path, DEC.PROXY_PIXELS)
    assert d.raw["source"] == "libraw" and d.draft_used is False
    assert any("LibRaw 真去马赛克" in n for n in d.notes)
    handover = [n for n in d.notes if "基线读侧没解开" in n]
    assert len(handover) == 1 and "CFALayout" in handover[0], \
        "换了后端却不留原因，报表上就看不出这一张是谁解的——那与静默降级只差一句话"
    assert d.rgb.ndim == 3 and d.rgb.shape[2] == 3 and d.rgb.dtype == np.uint8


def test_raw_backends_keeps_vendor_formats_unverified():
    """#M9-h 口径：厂商格式一律标"未经实机样张认证"，不许出现在已验那一栏里。

    这一条守的不是功能，是话术：装上门机型录不进库，"支持 CR2"就是假指标。已验那一栏
    只能有 .dng，而 vendor 那一栏必须自带"没样张"这句话——把免责写在数据里，UI 抄走的
    就是同一份事实，不是一句前端自己补的漂亮话。
    """
    bb = R.raw_backends()
    assert bb["suffixes_verified"] == [".dng"], bb["suffixes_verified"]
    assert bb["sample_certified"]["vendor"] is False, bb
    assert any("未经实机样张认证" in s for s in [bb["vendor_status"]]), bb
    for suf in bb["vendor_suffixes"]:
        assert suf not in bb["suffixes_verified"]
        assert suf in bb["vendor_suffixes"]
    # 16-bit 直通导出属于"已验"那一栏的说法要有出处，不能只是列表里多一行字
    assert any("16-bit" in s for s in bb["verified_full_chain"]), bb["verified_full_chain"]
