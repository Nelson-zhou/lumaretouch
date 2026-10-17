"""M2-b 478 点 TPS 形变：算子语义 + 常驻层接入。

判据口径来自 gpuspike/m2b4.py 的实测，不是许愿值。这一节最要紧的还是**反向门禁**：
几何形变特别容易写成"看着在动、其实动的是别的地方"，画面永远"有变化"，只有
"错实现必须让某条断言变红"才拦得住。本轮真抓到两个：affine 项转置写反（纯 y 请求
冒出 1.19 px 的 x 位移）与像素单位直接加到归一化网格上（整幅糊成边缘色）。
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from lumaretouch_engine.ops.deform import (
    CHIN, FACE_OVAL_LEFT, FACE_OVAL_RIGHT, KINDS, KIND_LIMIT, IRIS_LEFT,
    DeformGeometryError, analytic_frontal_landmarks, check_amounts, controls,
    dedupe_controls, face_frame, identity_grid, support_radii, tps_field_np,
    tps_field_t, unit_field, warp_np, warp_t)

H, W = 240, 192          # 测试档：CPU 参考实现跑得动，又能容下一张完整的脸


def sample_bilinear(f: np.ndarray, x: float, y: float) -> np.ndarray:
    """在整格点场 f 上双线性取样。控制点不在格点上，直接 round 索引会带进
    最多 0.5 px 的位置误差（小位移、大梯度的眼睛周圈上能到 0.1 px，比位移本身
    还显眼），那就测不出算子精度了。"""
    h, w = f.shape[:2]
    x0 = min(max(int(math.floor(x)), 0), w - 1)
    y0 = min(max(int(math.floor(y)), 0), h - 1)
    x1, y1 = min(x0 + 1, w - 1), min(y0 + 1, h - 1)
    wx, wy = x - x0, y - y0
    return (f[y0, x0] * (1 - wx) * (1 - wy) + f[y0, x1] * wx * (1 - wy)
            + f[y1, x0] * (1 - wx) * wy + f[y1, x1] * wx * wy)


# --------------------------------------------------------------------- 夹具
def landmarks(**kw):
    return analytic_frontal_landmarks(**kw)


def field(lm, kind, amount=1.0, h=H, w=W):
    """CPU 参考场：与产品同一条路径（controls → tps_field_np + 窗）。"""
    P, D, meta = controls(lm, kind, amount, h, w)
    cx, cy, R, _fw, _fh = meta["frame"]
    r0, r1 = support_radii(R)
    return tps_field_np(P, D, h, w, cx=cx, cy=cy, R=r1, r0=r0), P, D, meta


# ============================================================= 关键点契约
def test_short_landmark_set_is_rejected():
    """477 点必须拒。少一个点不会报错，只会让某个语义下标拿到别的部位——画面照样动。"""
    lm = landmarks()
    with pytest.raises(DeformGeometryError, match="478"):
        controls(lm[:477], "slim_face", 1.0, H, W)
    with pytest.raises(DeformGeometryError, match="478"):
        face_frame(lm[:100], H, W)


def test_pixel_unit_landmarks_are_rejected():
    """单位约定也得当场拒：像素坐标当归一化传进来，差 672 倍，画面会糊成一坨。

    不拒的话它不会报错——控制点全跑到图像外，border padding 之下得到一张
    "看起来动过了"的废图。这是最坏的一类 bug：有变化、无异常、指标全绿。
    """
    bad = landmarks()
    bad[:, :2] *= [W, H]
    with pytest.raises(DeformGeometryError, match="归一化"):
        controls(bad, "slim_face", 1.0, H, W)


def test_unknown_kind_and_out_of_range_amount_are_rejected():
    lm = landmarks()
    with pytest.raises(DeformGeometryError, match="未知形变类型"):
        controls(lm, "bigger_forehead", 1.0, H, W)
    for bad in (1.0001, -1.0001, float("nan"), float("inf")):
        with pytest.raises(DeformGeometryError):
            controls(lm, "slim_face", bad, H, W)


def test_check_amounts_rejects_the_whole_dict_not_just_the_bad_key():
    """半应用是本轮之前几个里程碑付过钱的形状：一个非法值不许把其他两个带下水。"""
    with pytest.raises(ValueError, match="未知形变类型"):
        check_amounts({"slim_face": 0.5, "nope": 0.5})
    with pytest.raises(ValueError, match="形变量非法"):
        check_amounts({"slim_face": 0.5, "big_eye": 3.0})
    with pytest.raises(ValueError, match="至少要给一个"):
        check_amounts({})
    got = check_amounts({"slim_face": "0.5"})       # 字符串数值仍收（IPC 传的是 JSON）
    assert got == {"slim_face": 0.5}


# ============================================================= 场本身的性质
def test_control_point_displacement_matches_request():
    """控制点处的位移必须等于请求值——紧支撑窗在 r0 内恒为 1 才成立。

    上一版窗半径给错（r0 = 0.84R < R），控制点落进过渡带，瘦脸在控制点处差 13.4 px
    而请求才 36.4 px：窗把请求的位移自己削掉了，画面照样"动了"，只是动得不够。
    """
    lm = landmarks()
    for kind in KINDS:
        f, P, D, meta = field(lm, kind)
        n = len(P) - 8                            # 末尾 8 个是边框零锚点
        req = D[:n]
        got = np.stack([sample_bilinear(f, p[0], p[1]) for p in P[:n]])
        peak = float(np.abs(req).max())
        assert peak > 1.0, f"{kind} 请求位移太小，这条判据退化了"
        err = float(np.abs(got - req).max())
        assert err < 0.02 * peak, f"{kind} 控制点误差 {err} px / 峰值 {peak} px"


def test_field_is_exactly_zero_outside_the_support():
    """紧支撑：r ≥ R 的位移必须逐点为 0，不是"很小"。

    瘦脸不许把背景拖走。这条与下一条（纯轴）是两套独立口径——窗写错会红第一条，
    affine 写错会红第二条。
    """
    lm = landmarks()
    cx, cy, R, _fw, _fh = face_frame(lm, H, W)
    _r0, r1 = support_radii(R)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    outside = np.hypot(xx - cx, yy - cy) >= r1
    assert outside.sum() > 0, "窗外没有像素，这条判据退化了"
    for kind in KINDS:
        f, *_ = field(lm, kind)
        assert np.count_nonzero(np.abs(f[outside]).max(axis=1)) == 0


def test_unit_field_reports_its_own_support_footprint():
    """作用面账单：报出的像素数必须就是场里非零的那些，且与窗口解析面积对得上。

    为什么必须有这个数：2026-10-17 拿一张真人照片跑端到端，肤色盒模板被红发、
    脖子与画面左下角一只手撑到整幅，slim_face=0.9 当场改了 98.6% 的画幅、其中
    57.6% 落在脸外——而事件里只有圆心与半径，看不出来。算子没错，几何错了；
    要看得见只能靠这一笔。

    它不是通过线而是量：作用面占多少画幅本身就随“脸在画面里多大”变（紧构图
    大头照可以合法地接近 1），所以拿它卡一个固定阈值就是许愿。能用的是它的
    **一致性**：非零区就是半径 r1 的圆盘，像素数与 π·r1² 对不上就是账单在谎报。
    """
    lm = landmarks()
    torch = pytest.importorskip("torch")     # unit_field 走 tps_field_t，没 torch 就跳
    # 三档：前两份脸占满画幅，支撑圆盘溢出画面（非零区 = 圆盘 ∩ 画面，与 π r²
    # 对不上是正常的）；第三份把脸缩小到画面一角，圆盘装得下——只有它能真证
    # "非零区就是那个圆盘"而不是"反正全盖上了"。
    small = landmarks(half_w=0.06, top=0.42, bottom=0.58,
                      eye_y=0.46, eye_half=0.024, iris_r=0.007)
    checked = 0
    for lm_case, h, w in ((lm, H, W), (lm, 600, 480), (small, 600, 480)):
        for kind in KINDS:
            t, meta = unit_field(lm_case, kind, h, w, device="cpu")
            moved = (t.abs().amax(dim=-1) > 1e-6).numpy()
            assert meta["support_px"] == int(moved.sum()), "账单与实际场得出自同一次归约"
            assert abs(meta["support_share"] - float(moved.mean())) <= 1e-4
            # 窗外逐点为零已由 test_field_is_exactly_zero_outside_the_support 钉住，
            # 这里补的是反向：窗内必须有真位移，否则 share=0 也能对上任意公式
            assert meta["support_px"] > 0
            cx, cy, _R, _r0, r1 = meta["window"]
            if min(cx, w - 1 - cx, cy, h - 1 - cy) >= r1:
                analytic = math.pi * r1 * r1 / (h * w)
                assert abs(meta["support_share"] - analytic) <= 0.10 * analytic, (
                    f"{h}x{w}/{kind} 非零区不是那个支撑圆盘："
                    f"报了 {meta['support_share']}，解析值 {analytic:.4f}")
                checked += 1
    assert checked >= 1, "圆盘对账一条都没跑上（三档都太大），这条判据已经退化"


def test_pure_axis_request_leaves_the_other_component_exactly_zero():
    """反向门禁（本轮真抓到 bug 的那条）：只请求 y 位移时 x 分量必须精确为 0。

    TPS 的两个输出分量各解一次同一个矩阵，右端项为 0 的分量必须全零——不是"误差小"。
    把 `X @ aff[1:]` 写成 `X @ aff[1:].T` 时这里量到 1.19 px，而"控制点误差"那条
    判据当时还是绿的（因为误差被摊到了两个分量上）。
    """
    rng = np.random.default_rng(11)
    P = rng.uniform([20.0, 40.0], [W - 20.0, H - 40.0], (12, 2))
    D = np.zeros((12, 2))
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    X = np.stack([xx.ravel(), yy.ravel()], 1)
    from lumaretouch_engine.ops.deform import _tps_field
    for axis in (0, 1):
        D[:] = 0.0
        D[:, axis] = rng.uniform(-20.0, 20.0, 12)
        f = _tps_field(P, D, X, 1e-8, scale=float(max(H, W))).reshape(H, W, 2)
        other = 1 - axis
        assert np.abs(f[..., other]).max() == 0.0, f"纯 {'xy'[axis]} 请求冒出 x 位移"


def test_field_is_exactly_linear_in_amount():
    """field(0.5) == 0.5·field(1) 必须是**恒等**，这是"拖滑块只缩放不重算"的全部依据。

    不成立的话拖一下滑块就得重解一次 (n+3)×(n+3)——GPU float64 实测 34–79 ms，
    60 fps 的预算当场碎。线性来自"解对右端项线性 + 请求位移与 amount 成正比"，
    所以只要 controls 里不用 amount 去做非线性的事（比如按 amount 改控制点位置）就成立。
    """
    lm = landmarks()
    f1, *_ = field(lm, "slim_face", 1.0)
    f5, *_ = field(lm, "slim_face", 0.5)
    assert np.abs(f5 - 0.5 * f1).max() == 0.0
    fn, *_ = field(lm, "slim_face", -1.0)
    assert np.abs(fn + f1).max() == 0.0, "负 amount 应当是反向等幅，不是另一种形变"


def test_gpu_field_matches_cpu_reference():
    """两条路径必须同阶。float64 求值 + 各向同性长度归一之后实测 < 1e-6 px。

    没做 scale 归一时这里能差出 0.77 px（U 元素到 1e7、λ=1e-8 等于没正则，
    cusolver 与 LAPACK 在这种条件数下分道扬镳），而位移本身才 37 px。
    """
    torch = pytest.importorskip("torch")
    lm = landmarks()
    P, D, meta = controls(lm, "slim_face", 1.0, H, W)
    cx, cy, R, _fw, _fh = meta["frame"]
    r0, r1 = support_radii(R)
    ref = tps_field_np(P, D, H, W, cx=cx, cy=cy, R=r1, r0=r0)
    for dev in (["cpu"] if not torch.cuda.is_available() else ["cpu", "cuda"]):
        got = tps_field_t(torch.from_numpy(P), torch.from_numpy(D), H, W,
                          cx=cx, cy=cy, R=r1, r0=r0, device=dev).cpu().numpy()
        # float32 落盘本身有 1e-4 量级的表示误差，判据按位移峰值给相对容差
        assert np.abs(got - ref.astype(np.float32)).max() < 1e-3


def test_boxed_field_is_the_same_field_exactly():
    """切带求值必须与整幅求值**逐元素相等**——M4 那句"显存峰值只随 tile 走"全靠这一条。

    这不是"足够接近"的判据：TPS 的稠密求值是采样点位置的解析函数，而 `scale` 仍按
    整幅 max(h,w) 归一，所以切出来的就是同一张场的对应切片。写 0 容差是故意的：一旦
    有人把 scale 改成带高（那才是真正的"逐 tile 各解各的"错），这里当场红。
    """
    lm = landmarks()
    P, D, meta = controls(lm, "slim_face", 1.0, H, W)
    cx, cy, R, _fw, _fh = meta["frame"]
    r0, r1 = support_radii(R)
    full = tps_field_np(P, D, H, W, cx=cx, cy=cy, R=r1, r0=r0)
    for box in ((0, 7, 0, W), (7, 20, 0, W), (20, H, 0, W), (3, 9, 5, W - 2), (0, H, 0, W)):
        part = tps_field_np(P, D, H, W, cx=cx, cy=cy, R=r1, r0=r0, box=box)
        assert part.shape == (box[1] - box[0], box[3] - box[2], 2)
        assert np.array_equal(part, full[box[0]:box[1], box[2]:box[3]]), \
            f"box={box} 的切片与整幅不一致：求值网格被动了几何参数"
    torch = pytest.importorskip("torch")
    kw = dict(cx=cx, cy=cy, R=r1, r0=r0, device="cpu")
    gt = tps_field_t(torch.from_numpy(P), torch.from_numpy(D), H, W, **kw).numpy()
    assert gt.shape == (H, W, 2) and gt.dtype == np.float32
    for box in ((0, 11, 0, W), (11, 40, 30, 90), (40, H, 0, W)):
        part = tps_field_t(torch.from_numpy(P), torch.from_numpy(D), H, W,
                           box=box, **kw).numpy()
        assert np.array_equal(part, gt[box[0]:box[1], box[2]:box[3]]), \
            f"GPU 臂 box={box} 与整幅切片不等：带循环不能当成整幅解的等价物"


def test_displacement_scales_with_face_not_with_frame():
    """同一张脸放大到不同代理档，位移与脸宽之比必须不变——否则换档就换了个效果。"""
    lm = landmarks()
    P1, D1, m1 = controls(lm, "slim_face", 1.0, H, W)
    P2, D2, m2 = controls(lm, "slim_face", 1.0, H * 2, W * 2)
    assert float(np.abs(D2).max()) == pytest.approx(float(np.abs(D1).max()) * 2, rel=1e-9)
    assert m2["frame"][3] == pytest.approx(m1["frame"][3] * 2, rel=1e-9)   # face_w


# ============================================================= 控制点合并
def test_coincident_controls_are_merged_and_counted():
    """两个位置重合、请求相反的控制点必须合并（取均值）并**报数**。

    不合并的话 TPS 会把它静默压成 ~0：不报错，只是"瘦脸推了没反应"。计数写成
    `len(keep_d[i]) + 1` 会恒为 3（那是个二维向量），所以合并数还得单独测一条。
    """
    P = np.array([[10.0, 10.0], [10.0, 10.4], [50.0, 60.0], [90.0, 20.0]])
    D = np.array([[-5.0, 0.0], [5.0, 0.0], [0.0, -3.0], [2.0, 1.0]])
    Pk, Dk, merged = dedupe_controls(P, D, tol=0.5)
    assert merged == 1
    assert len(Pk) == 3
    assert np.allclose(Dk[0], [0.0, 0.0]), "重合点取均值才是可解释的合并"
    # 三点共位：合并数必须是 2，不是恒 3 的那个写法
    P3 = np.array([[10.0, 10.0]] * 3 + [[80.0, 80.0]])
    D3 = np.array([[3.0, 0.0], [0.0, 3.0], [-3.0, 0.0], [1.0, 1.0]])
    _, Dk3, m3 = dedupe_controls(P3, D3, tol=0.5)
    assert m3 == 2 and len(Dk3) == 2
    assert np.allclose(Dk3[0], [0.0, 1.0]), "三点均值应当是 (0, 1)"


def test_dedupe_is_wired_into_controls():
    """接线检查：把两条轮廓的底端强行收到同一个点上，controls 必须报 merged>0。"""
    lm = landmarks()
    lm[FACE_OVAL_LEFT[-1]] = lm[FACE_OVAL_RIGHT[-1]]
    _P, _D, meta = controls(lm, "slim_face", 1.0, H, W)
    assert meta["merged"] >= 1, "dedupe 没接进 controls，重合点会静默抵消请求位移"


# ============================================================= 采样
def test_identity_grid_uses_pixel_centers():
    """恒等网格必须是 (2i+1)/n − 1。写成 linspace(±(1−2/n)) 会把整幅重采样。"""
    torch = pytest.importorskip("torch")
    g = identity_grid(H, W)[0]
    assert float(g[0, 0, 1]) == pytest.approx(1.0 / H - 1.0, abs=1e-6)
    assert float(g[0, 0, 0]) == pytest.approx(1.0 / W - 1.0, abs=1e-6)
    ys = g[:, 0, 1]
    assert torch.allclose(ys[1] - ys[0], torch.tensor(2.0 / H), atol=1e-6)


def test_zero_field_short_circuits_without_running_any_kernel():
    """CPU 参考臂：空场与 s=0 必须直接返回同一个对象，连算子都不进。

    上一版这条叫“恒等网格 + 零位移逐字节还原”，但 warp_np 在全零场上直接
    `return img`（vram 那边也有 has_deform 门），所以那句逐字节断言**对任何采样公式
    都成立** —— 连 `plane[y0, x0]` 写错都不会红。恒真判据比没判据更贵：它让人以为
    采样段被测过。采样公式本身由 test_fractional_translation 与
    test_warp_np_and_warp_t_agree 钉。这一条拆成不依赖 torch 的一份，CI 的 CPU job
    也能跑（否则“短路”这个承诺在无 GPU 变体上根本不验）。
    """
    rng = np.random.default_rng(7)
    img = rng.integers(0, 256, (1, 3, H, W)).astype(np.uint8)
    d = np.zeros((1, H, W, 2), dtype=np.float32)
    # 身份相等就是结构性质最硬的证法：不是“算出来恰好一样”，是一个字节也没动过
    assert warp_np(img, d, 0.0) is img
    assert warp_np(img, d, 1.0) is img


def test_zero_field_with_identity_grid_is_byte_exact():
    """GPU 臂：恒等网格 + 零位移必须逐字节等于输入（identity_grid 与 grid_sample 对齐）。"""
    torch = pytest.importorskip("torch")
    rng = np.random.default_rng(7)
    img = rng.integers(0, 256, (1, 3, H, W)).astype(np.uint8)
    d = np.zeros((1, H, W, 2), dtype=np.float32)
    tf = torch.from_numpy(img).float().div_(255.0)
    out = warp_t(tf, torch.from_numpy(d), 1.0, base=identity_grid(H, W))
    assert torch.equal(out, tf), "零位移不得改变任何一个字节"


def test_fractional_translation_matches_analytic_bilinear():
    """分数位移的采样必须是解析双线性（这一条才真的在验采样公式）。

    整数平移下双线性权重落到格点上，四个抽头写成什么都是对的；只有 0.5 px 能把
    “拿错抽头”从看起来差不多变成错得离谱。与 GPU 臂同输同对拍。"""
    torch = pytest.importorskip("torch")
    rng = np.random.default_rng(11)
    img = rng.integers(0, 256, (1, 3, H, W)).astype(np.uint8)
    tf = torch.from_numpy(img).float().div_(255.0)
    d = np.zeros((1, H, W, 2), dtype=np.float32)
    d[..., 0] = 0.5
    ref = tf.numpy()
    # 采样坐标 x+0.5：左右两个抽头各一半（取 interior 列，不碰 border 延拓那一列）
    want = np.concatenate([(ref[..., :-1] + ref[..., 1:]) * 0.5, ref[..., -1:]], axis=-1)
    got_np = warp_np(tf.numpy(), d, 1.0)
    got_t = warp_t(tf, torch.from_numpy(d), 1.0).numpy()
    for name, got in (("CPU", got_np), ("GPU", got_t)):
        inner = got[:, :, 2:-2, 1:-1]
        w = want[:, :, 2:-2, 1:-1]
        err = np.abs(inner - w).max()
        assert err < 1.5e-3, f"{name} 臂 0.5px 采样与解析双线性差 {err}：抽头或权重不对"


def test_translation_moves_by_exact_pixels():
    """反向门禁（本轮真抓到第二个 bug 的那条）：平移 k 像素就得恰好搬 k 像素。

    "像素单位的位移场直接加到归一化网格上"这个错不会被上面那条恒等测试抓到
    （s=0 时两边都是恒等），只有整数位移的平移能抓：grid_sample 在 border padding
    下会把超出边界的整幅糊成边缘色，偏差是 200 LSB 级而不是 1 LSB 级。
    """
    torch = pytest.importorskip("torch")
    rng = np.random.default_rng(3)
    img = rng.integers(0, 256, (1, 3, H, W)).astype(np.uint8)
    tf = torch.from_numpy(img).float().div_(255.0)
    for k in (3, -5):
        d = np.zeros((1, H, W, 2), dtype=np.float32)
        d[..., 0] = k
        want = img[0][:, :, np.clip(np.arange(W) + k, 0, W - 1)]
        got_np = np.round(warp_np(tf.numpy(), d, 1.0)[0] * 255.0).astype(np.uint8)
        got_t = torch.round(warp_t(tf, torch.from_numpy(d), 1.0)[0] * 255.0).to(torch.uint8).numpy()
        assert np.abs(got_np.astype(int) - want.astype(int)).max() == 0, f"CPU 参考平移 {k} 不对"
        assert np.abs(got_t.astype(int) - want.astype(int)).max() == 0, f"GPU 路径平移 {k} 不对"


def test_warp_np_refuses_a_batch_it_cannot_map():
    """批量图 + 单份位移场必须当场拒，不许交一张带未初始化内存的图。

    上一版 `out = np.empty_like(src)` 而循环只写 out[0]，其余批次是脏内存；
    `np.where(zero, src, out)` 在非零位移区会把那些脏字节拷进输出，而报表全绿。
    """
    rng = np.random.default_rng(5)
    img = rng.integers(0, 256, (2, 3, H, W)).astype(np.float32)
    d = np.ones((1, H, W, 2), dtype=np.float32)      # 非零场，不走短路
    with pytest.raises(ValueError):
        warp_np(img, d, 1.0)
    # 场的空间尺寸对不上也不靠 reshape “自动对齐”
    with pytest.raises(ValueError):
        warp_np(img[:1], np.ones((H + 7, W, 2), dtype=np.float32), 1.0)


def test_warp_np_and_warp_t_agree_on_a_real_field():
    """CPU 参考与 GPU 生产在真形变场上同值（量化到 uint8 后逐字节）。"""
    torch = pytest.importorskip("torch")
    lm = landmarks()
    f, *_ = field(lm, "slim_face", 0.8)
    rng = np.random.default_rng(9)
    img = rng.integers(0, 256, (1, 3, H, W)).astype(np.uint8)
    tf = torch.from_numpy(img).float().div_(255.0)
    a = np.round(warp_np(tf.numpy(), f[None], 1.0)[0] * 255.0).astype(np.int32)
    b = torch.round(warp_t(tf, torch.from_numpy(f[None].astype(np.float32)), 1.0)[0] * 255.0) \
        .to(torch.int32).numpy()
    d = np.abs(a - b).max()
    assert d <= 1, f"两条采样路径差 {d} LSB"


def test_strength_out_of_range_is_rejected_by_warp():
    torch = pytest.importorskip("torch")
    t = torch.zeros(1, 3, 8, 8)
    d = torch.ones(1, 8, 8, 2)
    for bad in (1.5, float("nan"), -2.0):
        with pytest.raises(ValueError, match="形变强度非法"):
            warp_t(t, d, bad)


# ============================================================= 常驻层
def _pipe(device="cpu"):
    torch = pytest.importorskip("torch")
    from lumaretouch_engine.vram import make_pipeline
    rng = np.random.default_rng(21)
    return make_pipeline(device, W, H, rng.integers(0, 256, (H, W, 3), dtype=np.uint8))


def test_deform_layer_is_byte_identical_when_unlit():
    """建了单但三个滑块全零 ⇒ 与没建单逐字节一致。产品承诺"不推就不动"。"""
    p = _pipe()
    p.prepare()
    p.render(0.5)
    a = p.read_back().copy()
    p.build_deform(landmarks())
    info = p.set_deform_amounts({k: 0.0 for k in KINDS})
    assert info["lit"] is False and p.has_deform() is False
    p.render(0.5)
    assert np.array_equal(p.read_back(), a)


def test_deform_changes_pixels_inside_and_freezes_pixels_outside():
    """形变必须真的改到画面，而且窗外一个字节都不许动（背景不被拖走）。"""
    p = _pipe()
    p.prepare()
    p.render(0.5)
    a = p.read_back()[..., :3].astype(np.int32)
    p.build_deform(landmarks())
    p.set_deform_amounts({"slim_face": 0.8})
    assert p.has_deform() is True
    p.render(0.5)
    b = p.read_back()[..., :3].astype(np.int32)
    d = np.abs(b - a).max(axis=2)
    assert (d > 0).sum() > 1000, "瘦脸 0.8 没改到画面，形变层是空的"
    lm = landmarks()
    cx, cy, R, _fw, _fh = face_frame(lm, H, W)
    _r0, r1 = support_radii(R)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    outside = np.hypot(xx - cx, yy - cy) >= r1
    assert outside.sum() > 0 and d[outside].max() == 0, "窗外有像素被拖走"


def test_dragging_the_slider_never_rebuilds_the_field():
    """拖滑块只缩放不重算：deform_builds 必须一分不增。

    这条是"零推理"的直接口径。每帧的 deform ms 无论如何都 > 0（grid_sample 真在跑），
    拿它当"有没有重算"的判据会恒真——所以计数字段只能由解算那一层递增。
    """
    p = _pipe()
    p.prepare()
    p.build_deform(landmarks())
    assert p.deform_builds == 1
    for i in range(12):
        p.set_deform_amounts({"slim_face": i / 20.0, "big_eye": (12 - i) / 40.0})
        p.render(0.5)
    assert p.deform_builds == 1, "拖滑块期间重解了 TPS，零推理失效"


def test_bad_amount_leaves_the_layer_untouched():
    """先校验后提交：越界值不许把其他两个滑块带下水，也不许改已提交的值。"""
    p = _pipe()
    p.prepare()
    p.build_deform(landmarks())
    p.set_deform_amounts({"slim_face": 0.4})
    with pytest.raises(ValueError, match="形变量非法"):
        p.set_deform_amounts({"slim_face": 0.9, "big_eye": 5.0})
    assert p.deform_amounts["slim_face"] == pytest.approx(0.4)
    assert p.deform_amounts["big_eye"] == 0.0
    with pytest.raises(ValueError, match="未知形变类型"):
        p.set_deform_amounts({"nose": 0.5})
    assert "nose" not in p.deform_amounts


def test_build_deform_is_atomic_when_landmarks_are_bad():
    """关键点不够 ⇒ 一层也不建：不许留下"两个单位场已常驻、第三个失败"的跳状态。"""
    p = _pipe()
    p.prepare()
    with pytest.raises(DeformGeometryError):
        p.build_deform(landmarks()[:400])
    assert p.deform_units == {} and p.deform_grid_base is None
    assert p.deform_builds == 0


def test_build_deform_rejects_a_field_with_non_finite_values(monkeypatch):
    """非有限值不进常驻（M1-3c 那条教训的原样复用）。"""
    from lumaretouch_engine import vram
    p = _pipe()
    p.prepare()
    real = vram.unit_field

    def poison(lm, kind, h, w, **kw):
        t, meta = real(lm, kind, h, w, **kw)
        if kind == "big_eye":
            t = t.clone()
            t[0, 0, 0, 0] = float("nan")
        return t, meta

    monkeypatch.setattr(vram, "unit_field", poison)
    with pytest.raises(ValueError, match="非有限值"):
        p.build_deform(landmarks())
    assert p.deform_units == {}, "含 NaN 的场被写进了常驻"


def test_reloading_the_image_drops_the_deform_layer():
    """换图必须清层：上一张脸的单位场对这一张没有任何关系。"""
    p = _pipe()
    p.prepare()
    p.build_deform(landmarks())
    p.set_deform_amounts({"slim_face": 0.5})
    rng = np.random.default_rng(22)
    p.load_rgb_u8(rng.integers(0, 256, (H, W, 3), dtype=np.uint8))
    assert p.deform_units == {} and not p.has_deform()
    assert p.deform_amounts == {k: 0.0 for k in KINDS}


def test_clear_face_also_clears_deform():
    """关键点一走，单位场就成了无源之水：clear_face 必须连着清形变层。"""
    p = _pipe()
    p.prepare()
    p.build_deform(landmarks())
    p.set_deform_amounts({"small_chin": 0.6})
    p.clear_face()
    assert p.deform_units == {} and p.deform_grid_base is None
    assert p.has_deform() is False


def test_resident_bytes_counts_units_and_grid():
    """显存账单：三个单位场 + 恒等网格。不报就等于藏了一笔显存账。"""
    p = _pipe()
    p.prepare()
    assert p.deform_resident_bytes() == 0
    info = p.build_deform(landmarks())
    want = sum(u.numel() * u.element_size() for u in p.deform_units.values()) \
        + p.deform_grid_base.numel() * p.deform_grid_base.element_size()
    assert info["bytes_deform"] == want == p.deform_resident_bytes()
    assert want == 4 * H * W * 2 * 4, "应当是 3 份位移场 + 1 份恒等网格，每份 (H,W,2) float32"
    assert p.clear_deform()["bytes_deform"] == 0
    assert p.deform_resident_bytes() == 0


def test_warm_device_actually_runs_the_deform_kernels():
    """预热必须真跑形变链：首拖白付一次 grid_sample 内核加载是修容第一笔的前车。"""
    torch = pytest.importorskip("torch")
    if not torch.cuda.is_available():
        pytest.skip("没有 GPU，预热路径整体返回 0.0，测不到内核加载")
    from lumaretouch_engine import vram
    calls = []
    real = vram.unit_field

    def spy(lm, kind, h, w, **kw):
        t, meta = real(lm, kind, h, w, **kw)
        calls.append(kind)
        return t, meta

    monkey = pytest.MonkeyPatch()
    monkey.setattr(vram, "unit_field", spy)
    try:
        ms = vram.warm_device("cuda")
    finally:
        monkey.undo()
    assert ms > 0.0
    assert sorted(calls) == sorted(KINDS), f"预热没覆盖全部三种形变：{calls}"
    # 不再加一句 `assert vram.PreviewPipeline.__init__`：那断言的是方法对象，恒真，
    # 而注释却声称在“防有人把预热整段注释掉”。上面那个 spy 已经证了这件事：
    # 单位场没真解过就不会有三次调用，而 warm_device 里不建会话根本走不到那里。


def test_warm_device_leaves_no_deform_references():
    """预热会话的形变层必须在 finally 里清干净：临时会话不能泄显存。"""
    torch = pytest.importorskip("torch")
    if not torch.cuda.is_available():
        pytest.skip("没有 GPU")
    from lumaretouch_engine import vram
    made = {}
    real = vram.PreviewPipeline

    class Track(real):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            made["pipe"] = self

    monkey = pytest.MonkeyPatch()
    monkey.setattr(vram, "PreviewPipeline", Track)
    try:
        vram.warm_device("cuda", side=32)
    finally:
        monkey.undo()
    p = made["pipe"]
    assert p.deform_units == {} and p.deform_grid_base is None and p.deform_meta == {}
